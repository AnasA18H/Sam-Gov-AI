"""
Convert Microsoft Word (.doc, .docx) to PDF using LibreOffice headless.

Requires LibreOffice installed on the server, e.g.:
  Ubuntu/Debian: sudo apt install libreoffice-writer
  macOS: brew install libreoffice

If LibreOffice is not available, conversion is skipped and the Word file is kept as-is.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Common executable names for LibreOffice
_LIBREOFFICE_NAMES = ("libreoffice", "soffice")


def _find_libreoffice() -> Optional[str]:
    """Return path to LibreOffice executable or None if not found."""
    for name in _LIBREOFFICE_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def convert_word_to_pdf(word_path: Path, delete_original: bool = False) -> Optional[Path]:
    """
    Convert a Word document (.doc or .docx) to PDF in the same directory.

    Args:
        word_path: Absolute path to the .doc or .docx file.
        delete_original: If True, remove the Word file after successful conversion.

    Returns:
        Path to the generated PDF file, or None if conversion failed or LibreOffice not found.
    """
    word_path = Path(word_path).resolve()
    if not word_path.is_file():
        logger.warning("word_to_pdf: not a file: %s", word_path)
        return None
    name_lower = word_path.name.lower()
    if not (name_lower.endswith(".doc") or name_lower.endswith(".docx")):
        logger.warning("word_to_pdf: not a Word file: %s", word_path)
        return None

    exe = _find_libreoffice()
    if not exe:
        logger.warning("word_to_pdf: LibreOffice not found; install it to auto-convert Word to PDF")
        return None

    out_dir = word_path.parent
    try:
        # --headless --convert-to pdf --outdir <dir> <file>
        # Output is <stem>.pdf in out_dir
        result = subprocess.run(
            [exe, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(word_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(out_dir),
        )
        if result.returncode != 0:
            logger.warning(
                "word_to_pdf: LibreOffice failed code=%s stderr=%s stdout=%s",
                result.returncode,
                result.stderr or "",
                result.stdout or "",
            )
            return None
    except subprocess.TimeoutExpired:
        logger.warning("word_to_pdf: LibreOffice timed out for %s", word_path)
        return None
    except Exception as e:
        logger.warning("word_to_pdf: %s", e, exc_info=True)
        return None

    pdf_path = out_dir / (word_path.stem + ".pdf")
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        logger.warning("word_to_pdf: no PDF produced at %s", pdf_path)
        return None

    if delete_original:
        try:
            word_path.unlink()
            logger.info("word_to_pdf: removed original %s", word_path)
        except OSError as e:
            logger.warning("word_to_pdf: could not remove original: %s", e)

    logger.info("word_to_pdf: converted %s -> %s (%s bytes)", word_path.name, pdf_path.name, pdf_path.stat().st_size)
    return pdf_path
