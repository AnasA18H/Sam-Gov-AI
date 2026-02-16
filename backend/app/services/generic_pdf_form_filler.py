"""
Generic PDF Form Filler for government/commercial AcroForms (SF1449, AF30, VA, etc.).
Uses, in order: Google Document AI Form Parser (best), PyPDF2 AcroForm, then OCR fallback.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import PyPDF2

from .form_field_mappings import get_data_key_for_form_field

logger = logging.getLogger(__name__)

# Google Document AI Form Parser (optional)
try:
    from google.cloud import documentai
    from google.oauth2 import service_account
    _DOCAI_AVAILABLE = True
except ImportError:
    _DOCAI_AVAILABLE = False

# Optional OCR/imaging (same as text_extractor)
try:
    from pdf2image import convert_from_path
    import pytesseract
    import cv2
    import numpy as np
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


class GenericPDFFormFiller:
    """
    Generic PDF Form Filler that works with any PDF form including:
    - SF1449 (Standard Form 1449)
    - AF30 (Air Force Form 30)
    - VA Forms
    - Any government/commercial Acroforms
    """

    def __init__(self, template_mapping_file: Optional[str] = None) -> None:
        """
        Initialize the form filler with optional template mappings.

        Args:
            template_mapping_file: JSON file with field mappings for different form types
        """
        self.field_mappings: Dict[str, Any] = {}
        self.form_fields: Dict[str, Any] = {}
        self.current_form_type: Optional[str] = None
        # Set by extract_form_fields: "docai_form_parser" | "acroform" | "ocr" | None
        self.extraction_source: Optional[str] = None

        if template_mapping_file and os.path.exists(template_mapping_file):
            with open(template_mapping_file, "r") as f:
                self.field_mappings = json.load(f)

    def detect_form_type(self, pdf_path: str) -> str:
        """Automatically detect the type of form based on content."""
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                if len(pdf_reader.pages) == 0:
                    return "UNKNOWN"
                first_page = pdf_reader.pages[0].extract_text() or ""

                form_patterns = {
                    "SF1449": [r"SF\s*1449", r"Standard Form 1449", r"REQUEST FOR QUOTATIONS"],
                    "AF30": [r"AF\s*30", r"Air Force Form 30", r"AF30"],
                    "VA": [r"Department of Veterans Affairs", r"VA Form", r"36C247"],
                    "DD254": [r"DD\s*254", r"Contract Security Classification"],
                    "OF347": [r"OF\s*347", r"Order for Supplies or Services"],
                    "GSA": [r"GSA Form", r"General Services Administration"],
                }

                for form_type, patterns in form_patterns.items():
                    for pattern in patterns:
                        if re.search(pattern, first_page, re.IGNORECASE):
                            self.current_form_type = form_type
                            return form_type

                return "GENERIC"

        except Exception as e:
            logger.exception("Error detecting form type: %s", e)
            return "UNKNOWN"

    def _extract_form_fields_with_docai(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract form fields using Google Document AI Form Parser.
        Returns fields with rect_normalized (0-1) and entity type for robust mapping.
        """
        if not _DOCAI_AVAILABLE:
            return {}
        from ..core.config import settings
        processor_id = (settings.GOOGLE_FORM_PARSER_PROCESSOR_ID or "").strip()
        if not processor_id or not settings.GOOGLE_PROJECT_ID or not settings.GOOGLE_LOCATION:
            logger.debug("Form Parser processor ID not set; skipping Document AI form extraction")
            return {}
        json_path = Path(settings.GOOGLE_SERVICE_ACCOUNT_JSON) if settings.GOOGLE_SERVICE_ACCOUNT_JSON else None
        if not json_path or not json_path.exists():
            json_path = getattr(settings, "PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent.parent) / "extras" / "resolute-planet-485419-f8-f543cf0a64b5.json"
        if not json_path.exists():
            logger.debug("Google service account JSON not found; skipping Form Parser")
            return {}
        try:
            creds = service_account.Credentials.from_service_account_file(
                str(json_path), scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            client = documentai.DocumentProcessorServiceClient(credentials=creds)
            with open(pdf_path, "rb") as f:
                file_content = f.read()
            name = f"projects/{settings.GOOGLE_PROJECT_ID}/locations/{settings.GOOGLE_LOCATION}/processors/{processor_id}"
            raw_document = documentai.RawDocument(content=file_content, mime_type="application/pdf")
            request = documentai.ProcessRequest(name=name, raw_document=raw_document)
            response = client.process_document(request=request)
            doc = response.document
            fields: Dict[str, Any] = {}
            for i, entity in enumerate(doc.entities or []):
                mention = (entity.mention_text or "").strip() if hasattr(entity, "mention_text") else ""
                if not mention and hasattr(entity, "type_") and "key" in (entity.type_ or "").lower():
                    continue
                entity_type = getattr(entity, "type_", None) or ""
                if isinstance(entity_type, str):
                    pass
                else:
                    entity_type = str(getattr(entity_type, "value", entity_type) or "")
                page_idx = 0
                rect_normalized = [0.0, 0.0, 0.1, 0.1]
                if hasattr(entity, "page_anchor") and entity.page_anchor and entity.page_anchor.page_refs:
                    ref = entity.page_anchor.page_refs[0]
                    page_idx = getattr(ref, "page", 0) or 0
                    if isinstance(page_idx, str) and page_idx.isdigit():
                        page_idx = int(page_idx)
                    if hasattr(ref, "bounding_poly") and ref.bounding_poly and ref.bounding_poly.normalized_vertices:
                        verts = ref.bounding_poly.normalized_vertices
                        xs = [v.x for v in verts]
                        ys = [v.y for v in verts]
                        rect_normalized = [min(xs), min(ys), max(xs), max(ys)]
                field_id = f"docai_{entity_type}_{page_idx}_{i}" if entity_type else f"docai_{page_idx}_{i}"
                fields[field_id] = {
                    "name": entity_type or field_id,
                    "mapping_name": field_id,
                    "type": entity_type or "/Tx",
                    "rect": [],  # filled at fill time from rect_normalized
                    "rect_normalized": rect_normalized,
                    "page": page_idx,
                    "required": False,
                    "value": mention,
                    "mapping_key": self._generate_mapping_key(entity_type or field_id),
                    "entity_type": entity_type,
                }
            return fields
        except Exception as e:
            logger.warning("Document AI Form Parser extraction failed: %s", e)
            return {}

    def extract_form_fields(self, pdf_path: str) -> Dict[str, Any]:
        """Extract all fillable fields: try Form Parser (Doc AI) first, then AcroForm, then OCR."""
        fields: Dict[str, Any] = {}

        try:
            # 1) Google Document AI Form Parser (best for flattened/SF1449)
            if _DOCAI_AVAILABLE:
                docai_fields = self._extract_form_fields_with_docai(pdf_path)
                if docai_fields:
                    self.extraction_source = "docai_form_parser"
                    self.form_fields = docai_fields
                    logger.info("Extracted %d fields from Document AI Form Parser", len(docai_fields))
                    return docai_fields

            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # 2) PyPDF2 AcroForm
                form_fields = pdf_reader.get_fields()
                if form_fields:
                    for mapping_name, field in form_fields.items():
                        if field is None:
                            continue
                        name = getattr(field, "name", None) or mapping_name
                        field_type = getattr(field, "field_type", None)
                        if hasattr(field_type, "get_object"):
                            type_str = str(field_type.get_object()) if field_type else "Tx"
                        else:
                            type_str = str(field_type) if field_type else "Tx"
                        flags = getattr(field, "flags", 0) or 0
                        is_required = bool(flags & 0x0002)
                        rect = [0, 0, 0, 0]
                        page_idx = 0
                        # Try to get rect and page from first widget (kid)
                        kids = getattr(field, "kids", None)
                        if kids and len(kids) > 0:
                            try:
                                first_kid = kids[0].get_object() if hasattr(kids[0], "get_object") else kids[0]
                                if hasattr(first_kid, "get"):
                                    rect = list(first_kid.get("/Rect", [0, 0, 0, 0]))
                                    page_ref = first_kid.get("/P")
                                    if page_ref is not None and hasattr(pdf_reader, "pages"):
                                        for i, p in enumerate(pdf_reader.pages):
                                            if getattr(p, "indirect_reference", None) == page_ref:
                                                page_idx = i
                                                break
                            except Exception:
                                pass
                        value = getattr(field, "value", None)
                        fields[mapping_name] = {
                            "name": name,
                            "mapping_name": mapping_name,
                            "type": type_str,
                            "rect": rect,
                            "required": is_required,
                            "page": page_idx,
                            "alternate_name": getattr(field, "alternate_name", "") or "",
                            "mapping_key": self._generate_mapping_key(str(name)),
                            "value": value,
                        }

                if fields:
                    self.extraction_source = "acroform"
                    logger.info("Extracted %d fields from AcroForm (fillable PDF)", len(fields))
                elif _OCR_AVAILABLE:
                    logger.info("No AcroForm fields found; using OCR fallback (slower)")
                    fields = self._extract_fields_with_ocr(pdf_path)
                    if fields:
                        self.extraction_source = "ocr"
                        logger.info("Extracted %d field regions from OCR", len(fields))
                else:
                    self.extraction_source = None

                self.form_fields = fields
                return fields

        except Exception as e:
            logger.exception("Error extracting fields: %s", e)
            self.extraction_source = None
            return {}

    def _extract_fields_with_ocr(self, pdf_path: str) -> Dict[str, Any]:
        """Fallback: detect form field labels using OCR for non-fillable PDFs."""
        fields: Dict[str, Any] = {}

        if not _OCR_AVAILABLE:
            return fields

        try:
            images = convert_from_path(pdf_path)
            for page_num, image in enumerate(images):
                img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                ocr_data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

                field_patterns = [
                    (r"(Name|NAME):?\s*$", "name"),
                    (r"(Address|ADDRESS):?\s*$", "address"),
                    (r"(Date|DATE):?\s*$", "date"),
                    (r"(Signature|SIGNATURE):?\s*$", "signature"),
                    (r"(Contract|CONTRACT)\s*(No|Number|#)", "contract_no"),
                    (r"(Phone|PHONE|Telephone):?\s*$", "phone"),
                    (r"(Email|EMAIL):?\s*$", "email"),
                    (r"(Company|COMPANY):?\s*$", "company"),
                    (r"(Title|TITLE):?\s*$", "title"),
                ]

                for i, text in enumerate(ocr_data["text"]):
                    for pattern, field_type in field_patterns:
                        if re.search(pattern, (text or "").strip(), re.IGNORECASE):
                            field_name = f"{field_type}_{page_num}_{i}"
                            fields[field_name] = {
                                "name": field_name,
                                "type": "/Tx",
                                "rect": [
                                    ocr_data["left"][i],
                                    ocr_data["top"][i],
                                    ocr_data["left"][i] + ocr_data["width"][i],
                                    ocr_data["top"][i] + ocr_data["height"][i],
                                ],
                                "required": True,
                                "page": page_num,
                                "label": text,
                            }
                            break
        except Exception as e:
            logger.warning("OCR extraction error: %s", e)

        return fields

    def _generate_mapping_key(self, field_name: str) -> str:
        """Generate a normalized mapping key for field matching."""
        key = re.sub(r"[^a-zA-Z0-9]", "", field_name.lower())
        patterns = {
            "name": r"name|fullname",
            "address": r"address|addr",
            "phone": r"phone|telephone|tel",
            "email": r"email|mail",
            "date": r"date|dt",
            "signature": r"sign|signature",
            "contract": r"contract|cont|cn|contractno",
            "solicitation": r"solicitation|sol|solno",
            "company": r"company|org|organization",
            "title": r"title|position",
            "amount": r"amount|price|total",
            "quantity": r"quantity|qty",
            "description": r"description|desc|item",
        }
        for standard_key, pattern in patterns.items():
            if re.search(pattern, key):
                return standard_key
        return key

    def fill_form(
        self,
        pdf_path: str,
        data: Dict[str, Any],
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fill the PDF form with provided data.

        Args:
            pdf_path: Path to input PDF
            data: Dictionary of field values to fill (keys: field names or mapping keys)
            output_path: Path for filled PDF (optional)

        Returns:
            Path to filled PDF, or None on failure
        """
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"filled_form_{timestamp}.pdf"

        logger.info("fill_form pdf_path=%s data_keys=%s output_path=%s", pdf_path, len(data), output_path)
        try:
            if self._fill_acroform(pdf_path, data, output_path):
                logger.info("fill_form method=acroform pdf_path=%s", pdf_path)
                return output_path
            if _OCR_AVAILABLE:
                out = self._fill_with_images(pdf_path, data, output_path)
                if out:
                    logger.info("fill_form method=image_overlay pdf_path=%s", pdf_path)
                return out
            logger.warning("fill_form no fill method available pdf_path=%s", pdf_path)
            return None
        except Exception as e:
            logger.exception("Error filling form: %s", e)
            return None

    def _fill_acroform(self, pdf_path: str, data: Dict[str, Any], output_path: str) -> bool:
        """Fill AcroForm fields using PyPDF2."""
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                pdf_writer = PyPDF2.PdfWriter()

                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)

                form_fields = pdf_reader.get_fields()
                if not form_fields:
                    return False

                # Build field name -> value for each page (PyPDF2 updates per page)
                page_updates: Dict[int, Dict[str, str]] = {}
                for field_name, field_value in data.items():
                    if field_value is None:
                        continue
                    str_value = str(field_value)
                    # Exact match
                    if field_name in form_fields:
                        field_info = self.form_fields.get(field_name, {})
                        page_idx = field_info.get("page", 0)
                        page_updates.setdefault(page_idx, {})[field_name] = str_value
                        continue
                    # Fuzzy match by mapping name
                    for form_field_name in form_fields:
                        if self._fields_match(field_name, form_field_name):
                            field_info = self.form_fields.get(form_field_name, {})
                            page_idx = field_info.get("page", 0)
                            page_updates.setdefault(page_idx, {})[form_field_name] = str_value
                            break

                if not page_updates:
                    return False

                pdf_writer.set_need_appearances_writer(True)
                for page_idx, updates in page_updates.items():
                    if 0 <= page_idx < len(pdf_writer.pages):
                        pdf_writer.update_page_form_field_values(pdf_writer.pages[page_idx], updates)

                with open(output_path, "wb") as output_file:
                    pdf_writer.write(output_file)
                logger.debug("_fill_acroform success path=%s", output_path)
                return True

        except Exception as e:
            logger.warning("AcroForm filling failed: %s", e)
            return False

    def _fill_with_images(self, pdf_path: str, data: Dict[str, Any], output_path: str) -> Optional[str]:
        """
        Fallback for flattened/no-AcroForm PDFs: render pages to images,
        draw text at OCR field positions, then write a new PDF.
        Uses Pillow + img2pdf (no reportlab required).
        """
        try:
            images = convert_from_path(pdf_path)
            page_width = images[0].width if images else 0
            page_height = images[0].height if images else 0
            if page_width <= 0 or page_height <= 0:
                logger.warning("Invalid page dimensions from pdf2image")
                return None

            try:
                import img2pdf
            except ImportError:
                logger.warning(
                    "img2pdf not installed. Install with: pip install img2pdf. "
                    "Required for filling flattened/OCR-detected forms."
                )
                return None

            from PIL import Image, ImageDraw, ImageFont
            import tempfile

            font_size = max(8, min(24, page_height // 80))
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except (OSError, IOError):
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", font_size)
                except (OSError, IOError):
                    font = ImageFont.load_default()

            temp_paths: List[str] = []

            for page_num, image in enumerate(images):
                # Work on a copy; convert to RGB if necessary
                img = image.copy()
                if img.mode != "RGB":
                    img = img.convert("RGB")
                draw = ImageDraw.Draw(img)

                page_w, page_h = image.size[0], image.size[1]
                for field_name, field_info in self.form_fields.items():
                    if field_info.get("page") != page_num:
                        continue
                    # Support both pixel rect (OCR) and normalized rect (Document AI)
                    rect_normalized = field_info.get("rect_normalized")
                    if rect_normalized and len(rect_normalized) >= 4:
                        x0, y0, x1, y1 = rect_normalized[0], rect_normalized[1], rect_normalized[2], rect_normalized[3]
                        x = max(0, int(x0 * page_w))
                        y = max(0, int(y0 * page_h))
                    else:
                        rect = field_info.get("rect", [0, 0, 0, 0])
                        if len(rect) < 4:
                            continue
                        x = max(0, int(rect[0]))
                        y = max(0, int(rect[1]))
                    # Prefer canonical data key from form field mapping, then fuzzy match
                    value = None
                    entity_type = field_info.get("entity_type") or field_info.get("type", "")
                    preferred_key = get_data_key_for_form_field(field_name, entity_type if isinstance(entity_type, str) else None)
                    if preferred_key and preferred_key in data and data[preferred_key] not in (None, ""):
                        value = str(data[preferred_key]).strip()
                    if value is None or value == "":
                        for key, val in data.items():
                            if self._fields_match(key, field_name):
                                value = str(val) if val is not None else ""
                                break
                    if value is None or value == "":
                        continue
                    draw.text((x, y), value, fill=(0, 0, 0), font=font)

                fd, path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                temp_paths.append(path)
                img.save(path, "PNG")

            try:
                with open(output_path, "wb") as out:
                    # img2pdf.convert(*images, outputstream=...) expects variadic paths
                    if temp_paths:
                        out.write(img2pdf.convert(*temp_paths))
                logger.info("Filled PDF written using OCR positions: %s", output_path)
                return output_path
            finally:
                for p in temp_paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        except Exception as e:
            logger.warning("Image-based filling failed: %s", e)
            return None

    def _fields_match(self, field1: str, field2: str) -> bool:
        """Check if two field names match (fuzzy)."""
        f1 = re.sub(r"[^a-zA-Z0-9]", "", field1.lower())
        f2 = re.sub(r"[^a-zA-Z0-9]", "", field2.lower())
        if f1 == f2:
            return True
        if f1 in f2 or f2 in f1:
            return True
        common = ["name", "address", "phone", "email", "date", "signature", "contract", "solicitation", "company"]
        for field in common:
            if field in f1 and field in f2:
                return True
        return False

    def save_field_mapping(self, mapping_file: str) -> None:
        """Save field mapping for future use."""
        mapping_data = {
            "form_type": self.current_form_type,
            "fields": self.form_fields,
            "timestamp": datetime.now().isoformat(),
        }
        with open(mapping_file, "w") as f:
            json.dump(mapping_data, f, indent=2)

    def load_field_mapping(self, mapping_file: str) -> None:
        """Load previously saved field mapping."""
        with open(mapping_file, "r") as f:
            mapping_data = json.load(f)
            self.current_form_type = mapping_data.get("form_type")
            self.form_fields = mapping_data.get("fields", {})
