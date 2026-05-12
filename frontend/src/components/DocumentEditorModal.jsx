/**
 * In-app document editor modal: PDF (form fields, text boxes, signatures) and Word (replace file).
 * No zoom: single scale from ResizeObserver (fit-to-width). Same scale for render and overlays.
 */
import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  HiOutlineX,
  HiOutlineSave,
  HiOutlineDocumentText,
  HiOutlineChevronLeft,
  HiOutlineChevronRight,
  HiOutlinePlus,
  HiOutlineTrash,
  HiOutlineCursorClick,
  HiOutlinePencil,
  HiOutlineSparkles,
  HiOutlinePhone,
  HiOutlineOfficeBuilding,
  HiOutlineLocationMarker,
  HiOutlineCalendar,
  HiOutlineHand,
  HiOutlineColorSwatch,
  HiOutlinePencilAlt,
  HiOutlineDocumentDuplicate,
  HiOutlineCheck,
  HiOutlineBadgeCheck,
} from 'react-icons/hi';
import { PDFDocument } from 'pdf-lib';
import * as pdfjsLib from 'pdfjs-dist';
import api, { opportunitiesAPI, authAPI } from '../utils/api';

import pdfjsWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
if (pdfjsWorkerUrl) pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

import {
  isPdf,
  isWord,
  pdfBytesContainXfa,
  detailToMessage,
  friendlyPdfErrorMessage,
  getFieldDisplayLabel,
  boxWidthFromSize,
  boxHeightFromSize,
  computeTextBoxSize,
  buildPdfBytes,
  PREVIEW_DEBOUNCE_MS,
  DEFAULT_PDF_WIDTH_PT,
  DEFAULT_PDF_HEIGHT_PT,
  TEXT_BOX_COLORS,
  TEXT_SUB_TOOLS,
  HIGHLIGHT_SUB_TOOLS,
  DRAW_SUB_TOOLS,
  DRAW_SHAPE_SUBTOOLS,
  DRAW_HIT_PADDING,
  SIGNATURE_BOX_W,
  SIGNATURE_BOX_H,
  SIGNATURE_SIZE_MIN_W,
  SIGNATURE_SIZE_MAX_W,
  SIGNATURE_SIZE_MIN_H,
  SIGNATURE_SIZE_MAX_H,
  CROSSOUT_BOX_W,
  CROSSOUT_BOX_H,
  DRAW_PEN_COLOR,
  PDF_HEADER_BYTES,
  EditorAddedItemTooltip,
} from './documentEditor';

// ——— Component ———
export default function DocumentEditorModal({ open, onClose, opportunityId, document: doc, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pdfFields, setPdfFields] = useState([]);
  const [fieldValues, setFieldValues] = useState({});
  const [apiFormFields, setApiFormFields] = useState([]);
  const [fillingFromOpportunity, setFillingFromOpportunity] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);
  const [pdfBytes, setPdfBytes] = useState(null);
  const [wordReplaceFile, setWordReplaceFile] = useState(null);
  const [formFieldsExpanded, setFormFieldsExpanded] = useState(true);
  const [pdfPageCount, setPdfPageCount] = useState(0);
  const [pdfPageHeightPoints, setPdfPageHeightPoints] = useState(null);
  const [pdfPageWidthPoints, setPdfPageWidthPoints] = useState(null);
  const [pdfCanvasScale, setPdfCanvasScale] = useState(null);
  const [addedTexts, setAddedTexts] = useState([]);
  const [newAddText, setNewAddText] = useState('');
  const [newAddPage, setNewAddPage] = useState(1);
  const [newAddSize, setNewAddSize] = useState(11);
  const [newAddBoxX, setNewAddBoxX] = useState(50);
  const [newAddBoxY, setNewAddBoxY] = useState(50);
  const [newAddColor, setNewAddColor] = useState('#000000');
  const [newAddBold, setNewAddBold] = useState(false);
  const [newAddItalic, setNewAddItalic] = useState(false);
  const [newAddUnderline, setNewAddUnderline] = useState(false);
  const [newAddStrikethrough, setNewAddStrikethrough] = useState(false);
  const [textAddLog, setTextAddLog] = useState([]);
  /** Main tool: pointer | text | highlight | draw | signature. Sub-tools define specific mode. */
  const [editorTool, setEditorTool] = useState('pointer');
  const [textSubTool, setTextSubTool] = useState('text');
  const [highlightSubTool, setHighlightSubTool] = useState('highlight');
  const [drawSubTool, setDrawSubTool] = useState('pen');
  const textBoxModeActive = editorTool === 'text';
  const textBoxPlacementMode =
    editorTool === 'text' && textSubTool === 'check'
      ? 'checkmark'
      : editorTool === 'text' && textSubTool === 'cross'
      ? 'xmark'
      : editorTool === 'text' && (textSubTool === 'dot' || textSubTool === 'circle-around' || textSubTool === 'crossout')
      ? textSubTool
      : 'text';
  const signaturePlaceModeActive = editorTool === 'signature' || editorTool === 'stamp' || (editorTool === 'draw' && drawSubTool === 'stamp');
  const highlightModeActive = editorTool === 'highlight';
  const drawModeActive = editorTool === 'draw';
  /** Cursor for current tool (front-end only for now) */
  const editorCursor =
    editorTool === 'pointer'
      ? 'default'
      : editorTool === 'text'
      ? textSubTool === 'text'
        ? 'text'
        : 'crosshair'
      : editorTool === 'highlight'
      ? 'crosshair'
      : editorTool === 'draw'
      ? 'crosshair'
      : editorTool === 'signature' || editorTool === 'stamp'
      ? 'crosshair'
      : 'default';
  /** Custom cursor icon for non-pointer tools; when set, we show cursor: none and this icon follows the mouse */
  const customCursorIcon =
    editorTool === 'pointer'
      ? null
      : editorTool === 'text'
      ? textSubTool === 'text'
        ? HiOutlineCursorClick
        : textSubTool === 'check'
        ? HiOutlineCheck
        : textSubTool === 'cross'
        ? HiOutlineX
        : HiOutlineCursorClick
      : editorTool === 'highlight'
      ? HiOutlineColorSwatch
      : editorTool === 'draw'
      ? drawSubTool === 'stamp'
        ? HiOutlineBadgeCheck
        : HiOutlinePencilAlt
      : editorTool === 'signature'
      ? HiOutlineDocumentDuplicate
      : editorTool === 'stamp'
      ? HiOutlineBadgeCheck
      : null;
  const [mousePreview, setMousePreview] = useState({ x: null, y: null });
  /** Position of custom cursor icon (clientX, clientY); null when mouse is outside preview area */
  const [customCursorPos, setCustomCursorPos] = useState(null);
  /** When set, this added-text id is selected and the edit tooltip is shown */
  const [selectedAddedTextId, setSelectedAddedTextId] = useState(null);
  const [tooltipAnchor, setTooltipAnchor] = useState(null);
  const [activeTab, setActiveTab] = useState('form');
  const [profileSuggestions, setProfileSuggestions] = useState({});
  /** User's saved signatures (up to 3 from profile); used in Signature tool flyout */
  const [savedSignatures, setSavedSignatures] = useState([]);
  /** Which signature is selected for placement when using Sign tool */
  const [selectedSignatureDataUrl, setSelectedSignatureDataUrl] = useState(null);
  /** User's custom stamps from profile (Settings workbench); used in Stamp tool flyout */
  const [savedStamps, setSavedStamps] = useState([]);
  /** Which stamp is selected for placement when using Stamp tool */
  const [selectedStampDataUrl, setSelectedStampDataUrl] = useState(null);
  const [xfaWarning, setXfaWarning] = useState(false);
  /** When set, show this as the rendered PDF (preview of unsaved changes). Cleared on save. */
  const [previewPdfBytes, setPreviewPdfBytes] = useState(null);
  const [autoPreviewEnabled, setAutoPreviewEnabled] = useState(false);
  /** Which main tool button is hovered (for showing tooltip panel on hover) */
  const [hoveredMainTool, setHoveredMainTool] = useState(null);
  /** Timeout to hide tooltip panel on mouse leave (keep open briefly) */
  const tooltipHideTimeoutRef = useRef(null);
  /** Highlight/underline/strikethrough: active drag { pageNum, startX, startY, endX, endY, previewW, previewH } */
  const [highlightDrag, setHighlightDrag] = useState(null);
  /** Draw pen: active path while drawing { pageNum, points: [{x,y}], previewW, previewH } */
  const [drawPath, setDrawPath] = useState(null);
  const drawPathRef = useRef(null);
  drawPathRef.current = drawPath;
  /** Draw shapes (line/arrow/rectangle/circle): drag { pageNum, startX, startY, endX, endY, previewW, previewH, subtype } */
  const [drawShapeDrag, setDrawShapeDrag] = useState(null);
  /** Drag to move an added item (signature, stamp, shape, etc.) */
  const [addedItemMoveDrag, setAddedItemMoveDrag] = useState(null);
  /** Drag to resize an added item (handle: n|s|e|w|ne|nw|se|sw) */
  const [addedItemResizeDrag, setAddedItemResizeDrag] = useState(null);
  const didAddedItemDragRef = useRef(false);

  const pdfScrollContainerRef = useRef(null);
  const pdfPageRefs = useRef([]);
  const pdfCanvasRefs = useRef([]);
  const previewContainerRef = useRef(null);
  const addTextContentRef = useRef(null);
  const formSourceBytesRef = useRef(null);
  const addedTextsRef = useRef([]);
  const fieldValuesRef = useRef({});
  /** Snapshot of field values when PDF was loaded (for highlight: yellow = already filled, green = user/autofill) */
  const initialFieldValuesRef = useRef({});
  const savingRef = useRef(false);
  const addedTextTooltipRef = useRef(null);
  /** In-flight pdf.js render tasks; cancelled when effect re-runs so same canvas is not used twice */
  const pdfRenderTasksRef = useRef([]);
  /** Highlight/underline/strikethrough: drag state (pageNum, start, end, preview size) */
  const highlightDragRef = useRef({
    active: false,
    pageNum: 0,
    startX: 0,
    startY: 0,
    endX: 0,
    endY: 0,
    previewW: 0,
    previewH: 0,
  });

  const isPDF = doc && isPdf(doc);
  const isWORD = doc && isWord(doc);

  const addLog = (message) => {
    const entry = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      message,
      time: new Date().toLocaleTimeString(),
    };
    setTextAddLog((prev) => [entry, ...prev].slice(0, 50));
  };

  addedTextsRef.current = addedTexts;
  fieldValuesRef.current = fieldValues;
  savingRef.current = saving;

  // ——— Load document ———
  useEffect(() => {
    if (!open || !doc || !opportunityId) return;
    const oid = Number(opportunityId);
    const docId = doc?.id != null ? Number(doc.id) : NaN;
    if (!Number.isInteger(oid) || oid < 1 || !Number.isInteger(docId) || docId < 1) {
      setError('Invalid opportunity or document.');
      setLoading(false);
      return;
    }
    setError('');
    setPdfFields([]);
    setFieldValues({});
    initialFieldValuesRef.current = {};
    setApiFormFields([]);
    setFillingFromOpportunity(false);
    setPdfPreviewUrl(null);
    setPdfBytes(null);
    setWordReplaceFile(null);
    setFormFieldsExpanded(true);
    setAddedTexts([]);
    setTextAddLog([]);
    setMousePreview({ x: null, y: null });
    setEditorTool('pointer');
    setNewAddText('');
    setNewAddPage(1);
    setNewAddSize(11);
    setNewAddBoxX(50);
    setNewAddBoxY(50);
    setPdfPageCount(0);
    setXfaWarning(false);
    setProfileSuggestions({});
    formSourceBytesRef.current = null;
    setLoading(true);

    const pdfForEditUrl = isPDF
      ? `/api/v1/opportunities/${oid}/documents/${docId}/view?t=${Date.now()}`
      : isWORD
        ? `/api/v1/opportunities/${oid}/documents/${docId}/pdf-for-editing?t=${Date.now()}`
        : null;
    if (pdfForEditUrl) {
      (async () => {
        try {
          const res = await api.get(pdfForEditUrl, { responseType: 'arraybuffer' });
          const buf = res.data;
          const bytes = new Uint8Array(buf);
          const bytesCopy = bytes.slice(0);
          if (bytesCopy.length === 0) {
            setError('Document is empty or the server returned no data.');
            setLoading(false);
            return;
          }
          const isPdfBytes = bytesCopy.length >= 5 && PDF_HEADER_BYTES.every((b, i) => bytesCopy[i] === b);
          if (!isPdfBytes) {
            const decoded = new TextDecoder().decode(bytesCopy.slice(0, 500));
            let msg = 'Document is not a valid PDF.';
            try {
              const json = JSON.parse(decoded);
              if (json?.detail) msg = detailToMessage(json.detail);
            } catch (_) {
              if (decoded.startsWith('<!') || decoded.includes('<!DOCTYPE')) {
                msg = 'Server returned an error page. Check that the API URL is correct and the document exists.';
              } else if (decoded.trim().length < 100) {
                msg = isWORD
                  ? 'Word to PDF conversion failed or is unavailable. Install LibreOffice on the server to edit Word documents.'
                  : 'Document file is missing or not a valid PDF.';
              }
            }
            setError(msg);
            setLoading(false);
            return;
          }
          setXfaWarning(pdfBytesContainXfa(bytesCopy));
          setPdfBytes(bytesCopy);
          formSourceBytesRef.current = bytesCopy;
          let pdfDoc;
          try {
            pdfDoc = await PDFDocument.load(bytesCopy, { ignoreEncryption: true });
          } catch (loadErr) {
            setError(friendlyPdfErrorMessage(loadErr));
            setLoading(false);
            return;
          }
          const form = pdfDoc.getForm();
          const fields = form.getFields();
          const fieldList = [];
          const initial = {};
          for (const f of fields) {
            const name = f.getName();
            const isCheck = f.constructor.name === 'PDFCheckBox';
            try {
              if (isCheck) {
                initial[name] = f.isChecked();
                fieldList.push({ name, type: 'checkbox' });
              } else {
                initial[name] = f.getText?.() ?? '';
                fieldList.push({ name, type: 'text' });
              }
            } catch (_) {
              initial[name] = isCheck ? false : '';
              fieldList.push({ name, type: isCheck ? 'checkbox' : 'text' });
            }
          }
          setPdfFields(fieldList);
          setFieldValues(initial);
          initialFieldValuesRef.current = { ...initial };
          setPdfPageCount(pdfDoc.getPageCount());
          const firstPage = pdfDoc.getPage(0);
          const { width: w, height: h } = firstPage.getSize();
          setPdfPageWidthPoints(w);
          setPdfPageHeightPoints(h);
          const blob = new Blob([bytesCopy], { type: 'application/pdf' });
          setPdfPreviewUrl(URL.createObjectURL(blob));
          setLoading(false);

          opportunitiesAPI
            .autofillPreview(oid, docId, fieldList.map((f) => f.name), Object.fromEntries(fieldList.map((f) => [f.name, f.type])))
            .then((previewRes) => {
              if (previewRes?.data?.fields) setApiFormFields(fieldList.map((f) => ({ name: f.name, mapping_key: f.name })));
            })
            .catch(() => {});

          authAPI.getProfile().then((profileRes) => {
            const p = profileRes?.data;
            if (!p) return;
            const today = new Date().toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' });
            const sigs = [p.digital_signature, p.digital_signature_2, p.digital_signature_3]
              .filter((s) => s && String(s).startsWith('data:image'));
            setSavedSignatures(sigs);
            setSelectedSignatureDataUrl(sigs.length > 0 ? sigs[0] : null);
            const stamps = Array.isArray(p.custom_stamps) ? p.custom_stamps.filter((s) => s?.dataUrl && String(s.dataUrl).startsWith('data:image')) : [];
            setSavedStamps(stamps);
            setSelectedStampDataUrl(stamps.length > 0 ? stamps[0].dataUrl : null);
            const sigDataUrl = sigs.length > 0 ? sigs[0] : null;
            setProfileSuggestions({
              'Company Name': p.company_name || '-',
              'Company Address': p.company_address || '-',
              Phone: p.phone || '-',
              Email: p.email || '-',
              UEI: p.uei || '-',
              CAGE: p.cage || '-',
              'Contract Officer Name': p.contract_officer_name || '-',
              Signature: sigDataUrl ? '(saved signature)' : '-',
              Date: today,
            });
          }).catch(() => {});
        } catch (e) {
          const detail = e?.response?.data;
          let msg = 'Failed to load document.';
          if (e?.response?.status === 503 && isWORD) {
            try {
              const text = detail instanceof ArrayBuffer ? new TextDecoder().decode(detail) : typeof detail === 'string' ? detail : null;
              const parsed = text ? JSON.parse(text) : null;
              if (parsed?.detail != null) msg = detailToMessage(parsed.detail);
            } catch (_) {
              if (typeof detail === 'string') msg = detail;
            }
          } else if (e?.response?.status === 404) {
            try {
              const text = detail instanceof ArrayBuffer ? new TextDecoder().decode(detail) : typeof detail === 'string' ? detail : null;
              const parsed = text ? JSON.parse(text) : null;
              if (parsed?.detail != null) msg = detailToMessage(parsed.detail);
            } catch (_) {
              if (typeof detail === 'string') msg = detail;
            }
          } else if (e?.response?.data?.detail != null) {
            msg = detailToMessage(e.response.data.detail);
          } else if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(e?.message ?? '')) {
            msg = friendlyPdfErrorMessage(e);
          }
          setError(msg);
          setLoading(false);
        }
      })();
    } else if (doc) {
      setLoading(false);
    }
    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
    };
  }, [open, opportunityId, doc?.id, isPDF, isWORD]);

  // ResizeObserver: single scale (fit-to-width) for canvas and overlays
  useEffect(() => {
    if (!pdfPageWidthPoints || pdfPageWidthPoints <= 0) return;
    const el = pdfScrollContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w > 0) setPdfCanvasScale(w / pdfPageWidthPoints);
    });
    ro.observe(el);
    if (el.clientWidth > 0) setPdfCanvasScale(el.clientWidth / pdfPageWidthPoints);
    return () => ro.disconnect();
  }, [pdfPageWidthPoints, pdfPreviewUrl]);

  const pdfScale = pdfCanvasScale;

  const bytesToRender = (previewPdfBytes && previewPdfBytes.length > 0) ? previewPdfBytes : pdfBytes;
  /** When true, the canvas shows the built PDF with added text baked in — do not draw overlay divs to avoid double text */
  const showingPreviewPdf = !!(previewPdfBytes && previewPdfBytes.length > 0);

  // Render PDF pages to canvases (single scale). Cancel in-flight renders when effect re-runs.
  // pdfPreviewUrl is included so this re-runs once the scroll container is mounted (it only
  // renders when pdfPreviewUrl is truthy) and its canvas children are in the DOM.
  useEffect(() => {
    if (!bytesToRender?.length || pdfPageCount < 1 || !pdfScale || pdfScale <= 0) return;
    const isPdf = bytesToRender.length >= 5 && PDF_HEADER_BYTES.every((b, i) => bytesToRender[i] === b);
    if (!isPdf) return;
    let cancelled = false;
    pdfRenderTasksRef.current = [];

    // Defer one animation frame so React has committed the canvas elements to the DOM
    // before pdf.js tries to query them via querySelector.
    let rafId = requestAnimationFrame(() => {
      if (cancelled) return;
      const container = pdfScrollContainerRef.current;
      if (!container) return;
      pdfjsLib
        .getDocument({ data: bytesToRender.slice(0) })
        .promise.then((pdf) => {
          if (cancelled) return;
          const renderPage = (i) => {
            if (cancelled) return;
            pdf
              .getPage(i + 1)
              .then((page) => {
                if (cancelled) return;
                const viewport = page.getViewport({ scale: pdfScale });
                const wrapper = container.querySelector(`[data-pdf-page="${i + 1}"]`);
                const canvas = wrapper?.querySelector('canvas');
                if (!canvas) return;
                const dpr = window.devicePixelRatio || 1;
                canvas.width = Math.floor(viewport.width * dpr);
                canvas.height = Math.floor(viewport.height * dpr);
                canvas.style.width = `${viewport.width}px`;
                canvas.style.height = `${viewport.height}px`;
                const ctx = canvas.getContext('2d');
                if (ctx) {
                  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
                  const task = page.render({ canvasContext: ctx, viewport });
                  if (task && typeof task.cancel === 'function') pdfRenderTasksRef.current.push(task);
                }
              })
              .catch(() => {});
          };
          for (let i = 0; i < pdf.numPages; i++) renderPage(i);
        })
        .catch(() => {});
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      pdfRenderTasksRef.current.forEach((task) => {
        try { task.cancel(); } catch (_) {}
      });
      pdfRenderTasksRef.current = [];
    };
  }, [bytesToRender, pdfPageCount, pdfScale, pdfPreviewUrl]);

  // IntersectionObserver: update page selector on scroll
  useEffect(() => {
    const container = pdfScrollContainerRef.current;
    if (!container || pdfPageCount < 1) return;
    const wrappers = container.querySelectorAll('[data-pdf-page]');
    if (wrappers.length === 0) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const page = parseInt(entry.target.getAttribute('data-pdf-page'), 10);
          if (page >= 1) setNewAddPage(page);
        });
      },
      { root: container, rootMargin: '-20% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] }
    );
    wrappers.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [pdfPageCount, pdfScale]);

  // Keyboard: Shift+Enter / Ctrl+Enter = add text box, Ctrl+S = save
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        if (loading || savingRef.current) return;
        if ((isPDF || (isWORD && pdfBytes)) && doc && (pdfBytes || formSourceBytesRef.current)) handleSavePdf(false);
        else if (isWORD && !pdfBytes && wordReplaceFile) handleSaveWord();
        return;
      }
      if ((e.shiftKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!loading && (isPDF || isWORD) && pdfBytes && newAddText.trim()) {
          doAddTextBox(newAddPage, newAddBoxX, newAddBoxY, newAddText, newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
          setNewAddText('');
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, loading, isPDF, isWORD, doc, pdfBytes, newAddText, newAddPage, newAddSize, newAddBoxX, newAddBoxY, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale]);

  // Auto-focus text content when Text tool + textbox tab so user can type immediately
  useEffect(() => {
    if (!open || !pdfBytes || activeTab !== 'textbox' || !formFieldsExpanded || editorTool !== 'text' || textBoxPlacementMode !== 'text') return;
    const t = setTimeout(() => addTextContentRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open, pdfBytes, activeTab, formFieldsExpanded, editorTool, textBoxPlacementMode]);

  // Close added-text tooltip on outside click
  useEffect(() => {
    if (!selectedAddedTextId) return;
    const onMouseDown = (e) => {
      const el = addedTextTooltipRef.current;
      if (el && !el.contains(e.target) && !e.target.closest('[data-added-text-id]')) {
        setSelectedAddedTextId(null);
        setTooltipAnchor(null);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [selectedAddedTextId]);

  // Highlight/underline/strikethrough: window mousemove and mouseup while dragging
  useEffect(() => {
    if (!highlightDrag) return;
    const scrollEl = pdfScrollContainerRef.current;
    const onMove = (e) => {
      if (!scrollEl || !highlightDrag) return;
      const wrapper = scrollEl.querySelector(`[data-pdf-page="${highlightDrag.pageNum}"]`);
      if (!wrapper) return;
      const r = wrapper.getBoundingClientRect();
      const endX = e.clientX - r.left;
      const endY = e.clientY - r.top;
      setHighlightDrag((prev) => (prev ? { ...prev, endX, endY } : null));
    };
    const onUp = () => {
      if (!highlightDrag) return;
      const { pageNum, startX, startY, endX, endY, previewW, previewH } = highlightDrag;
      const minX = Math.min(startX, endX);
      const minY = Math.min(startY, endY);
      const width = Math.abs(endX - startX);
      const height = Math.abs(endY - startY);
      if (width >= 4 && height >= (highlightSubTool === 'highlight' ? 6 : 2)) {
        doAddHighlightMarkup(pageNum, {
          x: minX,
          y: minY,
          width,
          height,
          previewW,
          previewH,
        }, highlightSubTool);
      }
      setHighlightDrag(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [highlightDrag, highlightSubTool]);

  // Draw pen: window mousemove and mouseup while drawing (use ref so mouseup always sees latest path)
  useEffect(() => {
    if (!drawPath) return;
    const scrollEl = pdfScrollContainerRef.current;
    const pageNum = drawPath.pageNum;
    const onMove = (e) => {
      if (!scrollEl) return;
      const wrapper = scrollEl.querySelector(`[data-pdf-page="${pageNum}"]`);
      if (!wrapper) return;
      const r = wrapper.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      setDrawPath((prev) => (prev ? { ...prev, points: [...prev.points, { x, y }] } : null));
    };
    const onUp = () => {
      const current = drawPathRef.current;
      if (!current || current.points.length < 2) {
        setDrawPath(null);
        return;
      }
      doAddDrawPath(current.pageNum, current.points, current.previewW, current.previewH);
      setDrawPath(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [drawPath]);

  // Draw shapes (line/arrow/rectangle/circle): window mousemove and mouseup while dragging
  useEffect(() => {
    if (!drawShapeDrag) return;
    const scrollEl = pdfScrollContainerRef.current;
    const onMove = (e) => {
      if (!scrollEl || !drawShapeDrag) return;
      const wrapper = scrollEl.querySelector(`[data-pdf-page="${drawShapeDrag.pageNum}"]`);
      if (!wrapper) return;
      const r = wrapper.getBoundingClientRect();
      const endX = e.clientX - r.left;
      const endY = e.clientY - r.top;
      setDrawShapeDrag((prev) => (prev ? { ...prev, endX, endY } : null));
    };
    const onUp = () => {
      if (!drawShapeDrag) return;
      const { pageNum, startX, startY, endX, endY, previewW, previewH, subtype } = drawShapeDrag;
      doAddDrawShape(pageNum, startX, startY, endX, endY, subtype, previewW, previewH);
      setDrawShapeDrag(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [drawShapeDrag]);

  const addTextBoxToPdf = (text, pageNum, size, box, drawBorder, color, bold, italic, underline, strikethrough) => {
    if (!text.trim() || pageNum < 1) return;
    const short = text.trim().length > 30 ? text.trim().slice(0, 30) + '…' : text.trim();
    const newItem = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      type: 'box',
      text: text.trim(),
      pageNum,
      size: size || 11,
      box: { ...box },
      drawBorder: !!drawBorder,
      color: color || '#000000',
      bold: !!bold,
      italic: !!italic,
      underline: !!underline,
      strikethrough: !!strikethrough,
    };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog(`Added text box "${short}" to page ${pageNum}`);
  };

  function doAddTextBox(pageNum, x, y, text, size, color, bold, italic, underline, strikethrough, pdfScaleForSize) {
    if (!text?.trim() || pageNum < 1) return;
    const s = size || 11;
    const scrollEl = pdfScrollContainerRef.current;
    const wrapper = scrollEl?.querySelector(`[data-pdf-page="${pageNum}"]`);
    const rect = wrapper?.getBoundingClientRect();
    const previewW = rect?.width ?? 0;
    const previewH = rect?.height ?? 0;
    const isSymbol = ['✓', '✗', '•', '○'].includes(text.trim());
    const scale = pdfScaleForSize ?? pdfScale ?? 1;
    const contentSize = isSymbol ? null : computeTextBoxSize(text.trim(), s, scale);
    const boxW = isSymbol ? Math.min(28, Math.max(10, s * 2.2)) : (contentSize?.width ?? boxWidthFromSize(s));
    const boxH = isSymbol ? Math.min(28, Math.max(10, s * 2.2)) : (contentSize?.height ?? boxHeightFromSize(s));
    const boxX = x - boxW / 2;
    const boxY = y - boxH / 2;
    addTextBoxToPdf(text.trim(), pageNum, s, {
      x: boxX,
      y: boxY,
      width: boxW,
      height: boxH,
      previewW,
      previewH,
    }, false, color || '#000000', bold, italic, underline, strikethrough);
  }

  const addSignatureToPdf = (pageNum, box, imageDataUrl) => {
    if (!imageDataUrl?.startsWith('data:image') || pageNum < 1) return;
    const newItem = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      type: 'signature',
      imageDataUrl,
      pageNum,
      box: { ...box },
    };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog('Added signature to page ' + pageNum);
  };

  function doAddSignature(pageNum, x, y, imageDataUrl) {
    if (!imageDataUrl?.startsWith('data:image') || pageNum < 1) return;
    const scrollEl = pdfScrollContainerRef.current;
    const wrapper = scrollEl?.querySelector(`[data-pdf-page="${pageNum}"]`);
    const rect = wrapper?.getBoundingClientRect();
    const previewW = rect?.width ?? 0;
    const previewH = rect?.height ?? 0;
    addSignatureToPdf(pageNum, {
      x,
      y,
      width: SIGNATURE_BOX_W,
      height: SIGNATURE_BOX_H,
      previewW,
      previewH,
    }, imageDataUrl);
  }

  function doAddMarkup(pageNum, x, y, subtype, pdfScaleForSize) {
    if (pageNum < 1 || subtype !== 'crossout') return;
    const scrollEl = pdfScrollContainerRef.current;
    const wrapper = scrollEl?.querySelector(`[data-pdf-page="${pageNum}"]`);
    const rect = wrapper?.getBoundingClientRect();
    const previewW = rect?.width ?? 0;
    const previewH = rect?.height ?? 0;
    const boxX = x - CROSSOUT_BOX_W / 2;
    const boxY = y - CROSSOUT_BOX_H / 2;
    const newItem = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      type: 'markup',
      subtype: 'crossout',
      pageNum,
      box: { x: boxX, y: boxY, width: CROSSOUT_BOX_W, height: CROSSOUT_BOX_H, previewW, previewH },
      color: newAddColor || '#000000',
    };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog(`Crossout placed on page ${pageNum}`);
  }

  function doAddHighlightMarkup(pageNum, box, subtype) {
    if (pageNum < 1 || !['highlight', 'underline', 'strikethrough'].includes(subtype)) return;
    const { width, height } = box;
    const minW = 4;
    const minH = subtype === 'highlight' ? 6 : 2;
    if (width < minW || height < minH) return;
    const newItem = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      type: 'markup',
      subtype,
      pageNum,
      box: { ...box },
      color: subtype === 'highlight' ? '#ffff00' : '#000000',
    };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog(`${subtype === 'highlight' ? 'Highlight' : subtype === 'underline' ? 'Underline' : 'Strikethrough'} placed on page ${pageNum}`);
  }

  function doAddDrawPath(pageNum, points, previewW, previewH) {
    if (pageNum < 1 || !Array.isArray(points) || points.length < 2) return;
    const newItem = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2),
      type: 'draw',
      subtype: 'pen',
      pageNum,
      path: points.map((p) => ({ x: p.x, y: p.y })),
      previewW,
      previewH,
      color: DRAW_PEN_COLOR,
    };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog(`Draw (pen) on page ${pageNum}`);
  }

  function doAddDrawShape(pageNum, startX, startY, endX, endY, subtype, previewW, previewH) {
    if (pageNum < 1 || !DRAW_SHAPE_SUBTOOLS.includes(subtype)) return;
    const minX = Math.min(startX, endX);
    const minY = Math.min(startY, endY);
    const width = Math.abs(endX - startX);
    const height = Math.abs(endY - startY);
    const minSize = 4;
    if (subtype === 'line' || subtype === 'arrow') {
      if (width < 2 && height < 2) return;
    } else {
      if (width < minSize || height < minSize) return;
    }
    const newItem =
      subtype === 'line' || subtype === 'arrow'
        ? {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2),
            type: 'draw',
            subtype,
            pageNum,
            start: { x: startX, y: startY },
            end: { x: endX, y: endY },
            previewW,
            previewH,
            color: DRAW_PEN_COLOR,
          }
        : {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2),
            type: 'draw',
            subtype,
            pageNum,
            box: { x: minX, y: minY, width, height, previewW, previewH },
            previewW,
            previewH,
            color: DRAW_PEN_COLOR,
          };
    setAddedTexts((prev) => {
      const next = [...prev, newItem];
      addedTextsRef.current = next;
      return next;
    });
    addLog(`Draw (${subtype}) on page ${pageNum}`);
  }

  const removeAddedText = (id) => {
    const item = addedTexts.find((t) => t.id === id);
    const short =
      item?.type === 'markup'
        ? (item.subtype === 'crossout' ? 'Crossout' : item.subtype === 'highlight' ? 'Highlight' : item.subtype === 'underline' ? 'Underline' : item.subtype === 'strikethrough' ? 'Strikethrough' : 'Markup')
        : item?.type === 'draw'
        ? 'Draw'
        : item?.text?.length > 30
        ? item.text.slice(0, 30) + '…'
        : item?.text ?? 'item';
    setAddedTexts((prev) => {
      const next = prev.filter((t) => t.id !== id);
      addedTextsRef.current = next;
      return next;
    });
    setPreviewPdfBytes(null);
    setSelectedAddedTextId(null);
    setTooltipAnchor(null);
    addLog(`Removed "${short}" from list`);
  };

  const updateAddedText = (id, updates) => {
    setAddedTexts((prev) => {
      const next = prev.map((t) => {
        if (t.id !== id) return t;
        const merged = { ...t, ...updates };
        const isTextContent = merged.type === 'box' && !['✓', '✗', '•', '○'].includes(merged.text);
        const contentChanged =
          updates.text !== undefined || updates.size !== undefined || updates.bold !== undefined || updates.italic !== undefined || updates.underline !== undefined || updates.strikethrough !== undefined;
        if (isTextContent && contentChanged) {
          const dims = computeTextBoxSize((merged.text || '').trim(), merged.size ?? 11, pdfScale ?? 1);
          const oldBox = merged.box || {};
          const oldW = oldBox.width ?? boxWidthFromSize(merged.size ?? 11);
          const oldH = oldBox.height ?? boxHeightFromSize(merged.size ?? 11);
          const centerX = (oldBox.x ?? 0) + oldW / 2;
          const centerY = (oldBox.y ?? 0) + oldH / 2;
          merged.box = {
            ...oldBox,
            x: Math.round(centerX - dims.width / 2),
            y: Math.round(centerY - dims.height / 2),
            width: dims.width,
            height: dims.height,
          };
        }
        return merged;
      });
      addedTextsRef.current = next;
      return next;
    });
  };

  const startAddedItemMove = (item, clientX, clientY) => {
    if (editorTool !== 'pointer' || showingPreviewPdf) return;
    didAddedItemDragRef.current = false;
    if (item.box) {
      setAddedItemMoveDrag({
        id: item.id,
        pageNum: item.pageNum,
        startBox: { ...item.box },
        pointerStartX: clientX,
        pointerStartY: clientY,
      });
    } else if (item.start && item.end) {
      setAddedItemMoveDrag({
        id: item.id,
        pageNum: item.pageNum,
        startStart: { ...item.start },
        startEnd: { ...item.end },
        pointerStartX: clientX,
        pointerStartY: clientY,
      });
    } else if (Array.isArray(item.path) && item.path.length > 0) {
      setAddedItemMoveDrag({
        id: item.id,
        pageNum: item.pageNum,
        startPath: item.path.map((p) => ({ ...p })),
        pointerStartX: clientX,
        pointerStartY: clientY,
      });
    }
  };

  const startAddedItemResize = (item, handle, clientX, clientY) => {
    if (editorTool !== 'pointer' || showingPreviewPdf || !item.box) return;
    didAddedItemDragRef.current = false;
    setAddedItemResizeDrag({
      id: item.id,
      pageNum: item.pageNum,
      handle,
      startBox: { x: item.box.x, y: item.box.y, width: item.box.width, height: item.box.height },
      pointerStartX: clientX,
      pointerStartY: clientY,
    });
  };

  useEffect(() => {
    const move = addedItemMoveDrag;
    if (!move) return;
    const onMove = (e) => {
      const deltaX = e.clientX - move.pointerStartX;
      const deltaY = e.clientY - move.pointerStartY;
      if (Math.hypot(deltaX, deltaY) > 4) didAddedItemDragRef.current = true;
      const scrollEl = pdfScrollContainerRef.current;
      const wrapper = scrollEl?.querySelector(`[data-pdf-page="${move.pageNum}"]`);
      const rect = wrapper?.getBoundingClientRect();
      const maxX = rect ? rect.width : 9999;
      const maxY = rect ? rect.height : 9999;
      if (move.startBox) {
        const w = move.startBox.width ?? 0;
        const h = move.startBox.height ?? 0;
        const x = Math.max(0, Math.min(move.startBox.x + deltaX, maxX - w));
        const y = Math.max(0, Math.min(move.startBox.y + deltaY, maxY - h));
        updateAddedText(move.id, { box: { ...move.startBox, x, y } });
      } else if (move.startStart && move.startEnd) {
        updateAddedText(move.id, {
          start: { x: move.startStart.x + deltaX, y: move.startStart.y + deltaY },
          end: { x: move.startEnd.x + deltaX, y: move.startEnd.y + deltaY },
        });
      } else if (move.startPath && move.startPath.length > 0) {
        const path = move.startPath.map((p) => ({ x: p.x + deltaX, y: p.y + deltaY }));
        updateAddedText(move.id, { path });
      }
    };
    const onUp = (e) => {
      setAddedItemMoveDrag(null);
      if (!didAddedItemDragRef.current) {
        setSelectedAddedTextId(move.id);
        setTooltipAnchor({ x: e.clientX, y: e.clientY });
      }
      didAddedItemDragRef.current = false;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [addedItemMoveDrag]);

  useEffect(() => {
    const resize = addedItemResizeDrag;
    if (!resize) return;
    const { handle, startBox } = resize;
    const onMove = (e) => {
      const deltaX = e.clientX - resize.pointerStartX;
      const deltaY = e.clientY - resize.pointerStartY;
      if (Math.hypot(deltaX, deltaY) > 2) didAddedItemDragRef.current = true;
      const minSize = 16;
      let x = startBox.x;
      let y = startBox.y;
      let width = startBox.width;
      let height = startBox.height;
      if (handle.includes('e')) width = Math.max(minSize, startBox.width + deltaX);
      if (handle.includes('w')) {
        width = Math.max(minSize, startBox.width - deltaX);
        x = startBox.x + deltaX;
      }
      if (handle.includes('s')) height = Math.max(minSize, startBox.height + deltaY);
      if (handle.includes('n')) {
        height = Math.max(minSize, startBox.height - deltaY);
        y = startBox.y + deltaY;
      }
      updateAddedText(resize.id, { box: { ...startBox, x, y, width, height } });
    };
    const onUp = () => {
      setAddedItemResizeDrag(null);
      didAddedItemDragRef.current = false;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [addedItemResizeDrag]);

  const setPlacementMode = (mode) => {
    if (mode === 'text' || mode === 'checkmark' || mode === 'xmark') {
      const sub = mode === 'text' ? 'text' : mode === 'checkmark' ? 'check' : 'cross';
      if (editorTool === 'text' && textSubTool === sub) {
        setEditorTool('pointer');
      } else {
        setEditorTool('text');
        setTextSubTool(sub);
      }
    } else {
      setEditorTool(editorTool === mode ? 'pointer' : mode);
    }
  };

  const handleSavePdf = async (asNew = false) => {
    if (!doc || savingRef.current) return;
    const sourceBytes = formSourceBytesRef.current || pdfBytes;
    if (!sourceBytes && !asNew) return;
    setSaving(true);
    savingRef.current = true;
    setError('');
    try {
      if (asNew) {
        const fv = fieldValuesRef.current ?? fieldValues;
        const added = addedTextsRef.current;
        const bytesToUse = sourceBytes || (await buildPdfBytes(pdfBytes || new Uint8Array(0), fv, []));
        const built = await buildPdfBytes(bytesToUse, fv, added);
        const baseName = doc.original_file_name || doc.file_name || 'document';
        const filename = baseName.toLowerCase().endsWith('.pdf') ? baseName : `${baseName.replace(/\.pdf$/i, '')}.pdf`;
        const file = new File([built], filename, { type: 'application/pdf' });
        await opportunitiesAPI.uploadNewDocument(opportunityId, file, filename);
        addLog('Saved as new document');
        onSaved?.();
        onClose?.();
        return;
      }
      if (!sourceBytes) {
        setError('No document data to save.');
        return;
      }
      const fv = fieldValuesRef.current ?? fieldValues;
      const added = addedTextsRef.current;
      const built = await buildPdfBytes(sourceBytes, fv, added);
      const baseName = doc.original_file_name || doc.file_name || 'document';
      const filename = baseName.toLowerCase().endsWith('.pdf') ? baseName : `${baseName.replace(/\.pdf$/i, '')}.pdf`;
      const file = new File([built], filename, { type: 'application/pdf' });
      await opportunitiesAPI.overwriteDocument(opportunityId, doc.id, file, filename);
      addLog(`Saved document with ${added.length} added item(s)`);
      const copy = built.slice(0);
      setPdfBytes(copy);
      formSourceBytesRef.current = copy;
      setPreviewPdfBytes(null);
      setAddedTexts([]);
      addedTextsRef.current = [];
      onSaved?.();
    } catch (e) {
      const apiMsg = detailToMessage(e?.response?.data?.detail);
      if (apiMsg) setError(apiMsg);
      else if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(e?.message ?? '')) {
        setError('Document data was lost or invalid. Close this editor, reopen the document, then try saving again.');
      } else {
        setError(e?.message || 'Failed to save');
      }
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  };

  const handleSaveWord = async (asNew = false) => {
    if (!wordReplaceFile || !doc || savingRef.current) return;
    setSaving(true);
    savingRef.current = true;
    setError('');
    try {
      if (asNew) {
        await opportunitiesAPI.uploadNewDocument(opportunityId, wordReplaceFile, wordReplaceFile.name);
        onSaved?.();
        onClose?.();
      } else {
        await opportunitiesAPI.overwriteDocument(opportunityId, doc.id, wordReplaceFile, wordReplaceFile.name);
        onSaved?.();
        onClose?.();
      }
    } catch (e) {
      setError(detailToMessage(e?.response?.data?.detail) || e?.message || 'Failed to save');
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  };

  // Debounced preview when form fields or added texts change (so autofill shows in PDF and text boxes/signatures do too).
  useEffect(() => {
    if (!isPDF || !formSourceBytesRef.current || !autoPreviewEnabled) {
      // When preview is disabled, always show the fast overlay view.
      setPreviewPdfBytes(null);
      return;
    }
    const hasFormFields = pdfFields.length > 0;
    const hasAddedTexts = addedTexts.length > 0;
    if (!hasFormFields && !hasAddedTexts) {
      setPreviewPdfBytes(null);
      return;
    }
    const t = setTimeout(() => {
      const texts = addedTextsRef.current || [];
      const fv = fieldValuesRef.current || {};
      if (pdfFields.length === 0 && texts.length === 0) {
        setPreviewPdfBytes(null);
        return;
      }
      buildPdfBytes(formSourceBytesRef.current, fv, texts, {
        highlightFilledFormFields: true,
        initialFieldValues: initialFieldValuesRef.current || undefined,
      })
        .then((built) => setPreviewPdfBytes(built))
        .catch(() => {});
    }, PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [isPDF, addedTexts, fieldValues, pdfFields.length, autoPreviewEnabled]);

  if (!open) return null;

  const overlay = (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/60 dark:bg-black/70" onClick={onClose}>
      <div
        className="bg-white dark:bg-dark-elevated rounded-[25px] shadow-2xl w-full max-w-[99vw] h-[96vh] max-h-[96vh] flex flex-col border-[7px] border-[#14B8A6] dark:border-teal-dm overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-dark-border">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <HiOutlineDocumentText className="w-5 h-5 text-[#14B8A6] dark:text-teal-dm" />
            Edit document {doc?.file_name && `— ${doc.file_name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 dark:text-dark-muted hover:bg-gray-100 dark:hover:bg-dark-hover hover:text-gray-700 dark:hover:text-white transition-colors"
            title="Close"
            aria-label="Close"
          >
            <HiOutlineX className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          {error && (
            <div className="mx-4 mt-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-sm border border-red-200 dark:border-red-800">
              {error}
            </div>
          )}
          {xfaWarning && isPDF && (
            <div className="mx-4 mt-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 text-sm border border-amber-200 dark:border-amber-800 flex items-center justify-between gap-2">
              <span>This PDF may use XFA forms. Saving could cause data loss. Consider keeping a backup.</span>
              <button
                type="button"
                onClick={() => setXfaWarning(false)}
                className="shrink-0 px-2 py-0.5 rounded hover:bg-amber-200/50 dark:hover:bg-amber-800/50 text-amber-800 dark:text-amber-200"
                aria-label="Dismiss warning"
              >
                Dismiss
              </button>
            </div>
          )}

          {loading && (
            <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-dark-muted">
              Loading document…
            </div>
          )}

          {!loading && (isPDF || isWORD) && pdfBytes && (
            <div className="flex-1 flex min-h-0 relative">
              {/* Professional floating tool strip: separators, spacing, translucent active */}
              <div className="absolute left-3 top-3 z-10 flex flex-col items-center gap-0 py-3 px-2 rounded-xl bg-white/90 dark:bg-dark-elevated/90 backdrop-blur-md border border-gray-200/80 dark:border-dark-border/80 shadow-lg">
                {[
                  { id: 'pointer', icon: HiOutlineHand, label: 'Pointer', title: 'Free pointer (select)', activeTitle: 'Pointer (active)' },
                  { id: 'text', icon: HiOutlineCursorClick, label: 'Text', title: 'Text tools: click to open', activeTitle: 'Text (active)' },
                  { id: 'highlight', icon: HiOutlineColorSwatch, label: 'Highlight', title: 'Highlight tools: click to open', activeTitle: 'Highlight (active)' },
                  { id: 'draw', icon: HiOutlinePencilAlt, label: 'Draw', title: 'Draw tools: click to open', activeTitle: 'Draw (active)' },
                  {
                    id: 'signature',
                    icon: HiOutlineDocumentDuplicate,
                    label: 'Sign',
                    title: savedSignatures.length === 0 ? 'Add signature (save in Settings first)' : 'Signature: click to pick',
                    activeTitle: 'Signature (active)',
                  },
                  {
                    id: 'stamp',
                    icon: HiOutlineBadgeCheck,
                    label: 'Stamp',
                    title: savedStamps.length === 0 ? 'Add stamps in Settings first' : 'Stamp: click to pick',
                    activeTitle: 'Stamp (active)',
                  },
                ].map((tool, index) => {
                  const active = editorTool === tool.id;
                  const Icon = tool.icon;
                  const showFlyout = (tool.id === 'text' && hoveredMainTool === 'text')
                    || (tool.id === 'highlight' && hoveredMainTool === 'highlight')
                    || (tool.id === 'draw' && hoveredMainTool === 'draw')
                    || (tool.id === 'signature' && hoveredMainTool === 'signature')
                    || (tool.id === 'stamp' && hoveredMainTool === 'stamp');
                  return (
                    <React.Fragment key={tool.id}>
                      {index > 0 && (
                        <div className="w-8 border-t border-gray-200/90 dark:border-dark-border/90 my-0.5" aria-hidden />
                      )}
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => {
                            if (tool.id === 'signature' && savedSignatures.length === 0) {
                              addLog('Save your signature in Settings first, then use this tool.');
                            }
                            if (tool.id === 'stamp' && savedStamps.length === 0) {
                              addLog('Create stamps in Settings first, then use this tool.');
                            }
                            setEditorTool(tool.id);
                          }}
                          title={active ? tool.activeTitle : tool.title}
                          aria-label={tool.label}
                          onMouseEnter={() => {
                            if (tooltipHideTimeoutRef.current) {
                              clearTimeout(tooltipHideTimeoutRef.current);
                              tooltipHideTimeoutRef.current = null;
                            }
                            setHoveredMainTool(tool.id);
                          }}
                          onMouseLeave={() => {
                            if (['text', 'highlight', 'draw', 'signature', 'stamp'].includes(tool.id)) {
                              tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 200);
                            } else {
                              setHoveredMainTool(null);
                            }
                          }}
                          className={`relative flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-all duration-150 ${
                            active
                              ? 'bg-[#14B8A6]/20 dark:bg-teal-dm/25 text-[#0D9488] dark:text-teal-dm ring-2 ring-[#14B8A6]/50 dark:ring-teal-dm/50'
                              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/80 dark:hover:bg-dark-hover hover:text-gray-900 dark:hover:text-gray-100'
                          }`}
                        >
                          <Icon className="w-5 h-5 shrink-0" aria-hidden />
                          <span className="text-[9px] font-medium mt-1 leading-tight">{tool.label}</span>
                          {active && hoveredMainTool === tool.id && (
                            <span className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-0.5 text-[10px] font-medium rounded border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated text-gray-700 dark:text-gray-200 shadow-sm whitespace-nowrap z-20" role="tooltip">
                              Active
                            </span>
                          )}
                        </button>
                      {/* Tooltip panel: positioned next to this button */}
                      {tool.id === 'text' && showFlyout && (
                        <div
                          className="absolute left-full top-0 ml-3 py-1.5 px-1.5 rounded-lg shadow-lg border border-gray-200/90 dark:border-dark-border bg-white dark:bg-dark-elevated min-w-[136px] max-h-[70vh] overflow-y-auto scrollbar-hidden z-20"
                          onMouseEnter={() => { if (tooltipHideTimeoutRef.current) clearTimeout(tooltipHideTimeoutRef.current); setHoveredMainTool('text'); }}
                          onMouseLeave={() => { tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 150); }}
                        >
                          {TEXT_SUB_TOOLS.map((sub) => {
                            const isSelected = textSubTool === sub.id;
                            return (
                              <button
                                key={sub.id}
                                type="button"
                                onClick={() => { setEditorTool('text'); setTextSubTool(sub.id); if (sub.id === 'text') setActiveTab('textbox'); setHoveredMainTool(null); }}
                                title={sub.title}
                                aria-label={sub.label}
                                className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-left text-sm transition-all duration-200 ${
                                  isSelected ? 'bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#14B8A6] dark:text-teal-dm' : 'text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover'
                                }`}
                                style={{ cursor: sub.cursor }}
                              >
                                <span className="w-5 text-center text-base shrink-0" aria-hidden>{sub.symbol}</span>
                                <span className="flex-1 font-medium">{sub.label}</span>
                                {isSelected && <span className="text-[#14B8A6] dark:text-teal-dm font-bold" aria-hidden>✓</span>}
                              </button>
                            );
                          })}
                        </div>
                      )}
                      {tool.id === 'highlight' && showFlyout && (
                        <div
                          className="absolute left-full top-0 ml-3 py-1.5 px-1.5 rounded-lg shadow-lg border border-gray-200/90 dark:border-dark-border bg-white dark:bg-dark-elevated min-w-[136px] z-20"
                          onMouseEnter={() => { if (tooltipHideTimeoutRef.current) clearTimeout(tooltipHideTimeoutRef.current); setHoveredMainTool('highlight'); }}
                          onMouseLeave={() => { tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 150); }}
                        >
                          {HIGHLIGHT_SUB_TOOLS.map((sub) => {
                            const isSelected = highlightSubTool === sub.id;
                            return (
                              <button
                                key={sub.id}
                                type="button"
                                onClick={() => { setEditorTool('highlight'); setHighlightSubTool(sub.id); setHoveredMainTool(null); }}
                                title={sub.title}
                                aria-label={sub.label}
                                className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-left text-sm transition-all duration-200 ${
                                  isSelected ? 'bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#14B8A6] dark:text-teal-dm' : 'text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover'
                                }`}
                                style={{ cursor: sub.cursor }}
                              >
                                <span className="w-5 text-center text-base shrink-0" aria-hidden>{sub.symbol}</span>
                                <span className="flex-1 font-medium">{sub.label}</span>
                                {isSelected && <span className="text-[#14B8A6] dark:text-teal-dm font-bold" aria-hidden>✓</span>}
                              </button>
                            );
                          })}
                        </div>
                      )}
                      {tool.id === 'draw' && showFlyout && (
                        <div
                          className="absolute left-full top-0 ml-3 py-1.5 px-1.5 rounded-lg shadow-lg border border-gray-200/90 dark:border-dark-border bg-white dark:bg-dark-elevated min-w-[136px] max-h-[70vh] overflow-y-auto scrollbar-hidden z-20"
                          onMouseEnter={() => { if (tooltipHideTimeoutRef.current) clearTimeout(tooltipHideTimeoutRef.current); setHoveredMainTool('draw'); }}
                          onMouseLeave={() => { tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 150); }}
                        >
                          {DRAW_SUB_TOOLS.map((sub) => {
                            const isSelected = drawSubTool === sub.id;
                            return (
                              <button
                                key={sub.id}
                                type="button"
                                onClick={() => { setEditorTool('draw'); setDrawSubTool(sub.id); setHoveredMainTool(null); }}
                                title={sub.title}
                                aria-label={sub.label}
                                className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-left text-sm transition-all duration-200 ${
                                  isSelected ? 'bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#14B8A6] dark:text-teal-dm' : 'text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover'
                                }`}
                                style={{ cursor: sub.cursor }}
                              >
                                <span className="w-5 text-center text-base shrink-0" aria-hidden>{sub.symbol}</span>
                                <span className="flex-1 font-medium">{sub.label}</span>
                                {isSelected && <span className="text-[#14B8A6] dark:text-teal-dm font-bold" aria-hidden>✓</span>}
                              </button>
                            );
                          })}
                          {drawSubTool === 'stamp' && (
                            <div className="mt-2 pt-2 border-t border-gray-200/90 dark:border-dark-border">
                              <p className="text-[10px] font-medium text-gray-500 dark:text-dark-muted px-1 mb-1.5">Stamp palette</p>
                              {savedStamps.length === 0 ? (
                                <p className="text-[10px] text-gray-500 dark:text-dark-muted px-1.5 py-2">Create stamps in Settings.</p>
                              ) : (
                                <div className="flex flex-col gap-1">
                                  {savedStamps.map((stamp, idx) => {
                                    const selected = selectedStampDataUrl === stamp.dataUrl;
                                    return (
                                      <button
                                        key={idx}
                                        type="button"
                                        onClick={() => setSelectedStampDataUrl(stamp.dataUrl)}
                                        title={`Place "${stamp.name}" on PDF`}
                                        aria-label={stamp.name}
                                        className={`flex items-center gap-2 rounded-lg border-2 p-1.5 w-full min-w-[100px] transition-all ${
                                          selected ? 'border-[#14B8A6] dark:border-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20' : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover'
                                        }`}
                                      >
                                        <img src={stamp.dataUrl} alt={stamp.name} className="w-14 h-10 object-contain rounded bg-white shrink-0" />
                                        <span className="text-[9px] font-medium text-gray-600 dark:text-gray-300 truncate flex-1 text-left">{stamp.name}</span>
                                      </button>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                      {tool.id === 'signature' && showFlyout && (
                        <div
                          className="absolute left-full top-0 ml-3 py-1.5 px-1.5 rounded-lg shadow-lg border border-gray-200/90 dark:border-dark-border bg-white dark:bg-dark-elevated gap-1 max-h-[70vh] overflow-y-auto scrollbar-hidden min-w-[120px] z-20"
                          onMouseEnter={() => { if (tooltipHideTimeoutRef.current) clearTimeout(tooltipHideTimeoutRef.current); setHoveredMainTool('signature'); }}
                          onMouseLeave={() => { tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 150); }}
                        >
                          {savedSignatures.length === 0 ? (
                            <p className="text-[10px] text-gray-500 dark:text-dark-muted px-1.5 py-2">Save a signature in Settings.</p>
                          ) : (
                            savedSignatures.map((dataUrl, idx) => {
                              const selected = selectedSignatureDataUrl === dataUrl;
                              return (
                                <button
                                  key={idx}
                                  type="button"
                                  onClick={() => { setEditorTool('signature'); setSelectedSignatureDataUrl(dataUrl); setHoveredMainTool(null); }}
                                  title="Use signature to place on PDF"
                                  aria-label="Signature"
                                  className={`flex flex-col items-center rounded-lg border-2 p-1.5 w-full min-w-[100px] transition-all ${
                                    selected ? 'border-[#14B8A6] dark:border-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20' : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover'
                                  }`}
                                >
                                  <img src={dataUrl} alt="" className="w-24 h-14 object-contain rounded bg-white" />
                                </button>
                              );
                            })
                          )}
                        </div>
                      )}
                      {tool.id === 'stamp' && showFlyout && (
                        <div
                          className="absolute left-full top-0 ml-3 py-1.5 px-1.5 rounded-lg shadow-lg border border-gray-200/90 dark:border-dark-border bg-white dark:bg-dark-elevated gap-1 max-h-[70vh] overflow-y-auto scrollbar-hidden min-w-[120px] z-20"
                          onMouseEnter={() => { if (tooltipHideTimeoutRef.current) clearTimeout(tooltipHideTimeoutRef.current); setHoveredMainTool('stamp'); }}
                          onMouseLeave={() => { tooltipHideTimeoutRef.current = setTimeout(() => setHoveredMainTool(null), 150); }}
                        >
                          {savedStamps.length === 0 ? (
                            <p className="text-[10px] text-gray-500 dark:text-dark-muted px-1.5 py-2">Create stamps in Settings.</p>
                          ) : (
                            savedStamps.map((stamp, idx) => {
                              const selected = selectedStampDataUrl === stamp.dataUrl;
                              return (
                                <button
                                  key={idx}
                                  type="button"
                                  onClick={() => { setEditorTool('stamp'); setSelectedStampDataUrl(stamp.dataUrl); setHoveredMainTool(null); }}
                                  title={`Use "${stamp.name}" on PDF`}
                                  aria-label={stamp.name}
                                  className={`flex flex-col items-center rounded-lg border-2 p-1.5 w-full min-w-[100px] transition-all ${
                                    selected ? 'border-[#14B8A6] dark:border-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20' : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover'
                                  }`}
                                >
                                  <img src={stamp.dataUrl} alt={stamp.name} className="w-24 h-14 object-contain rounded bg-white" />
                                  <span className="text-[9px] font-medium text-gray-600 dark:text-gray-300 mt-0.5 truncate max-w-full px-0.5">{stamp.name}</span>
                                </button>
                              );
                            })
                          )}
                        </div>
                      )}
                      </div>
                    </React.Fragment>
                  );
                })}
                </div>
              <div className="flex-1 min-w-0 flex flex-col border-r border-gray-200 dark:border-dark-border pl-20">
                {previewPdfBytes && previewPdfBytes.length > 0 && (
                  <div className="text-xs font-medium bg-amber-200 dark:bg-amber-800/60 text-amber-900 dark:text-amber-100 px-3 py-2 border-b border-amber-300 dark:border-amber-700 flex items-center gap-3 flex-wrap">
                    <span className="inline-block w-2 h-2 rounded-full bg-amber-500 dark:bg-amber-400 animate-pulse" aria-hidden />
                    Preview: form fill and edits shown. Save to write to PDF.
                    <span className="flex items-center gap-1.5 text-amber-800 dark:text-amber-200">
                      <span className="inline-block w-2.5 h-2.5 rounded border border-amber-600/50 bg-amber-200/90" title="Already filled" aria-hidden />
                      Yellow = already filled
                    </span>
                    <span className="flex items-center gap-1.5 text-amber-800 dark:text-amber-200">
                      <span className="inline-block w-2.5 h-2.5 rounded border border-green-600/50 bg-green-400/90" title="Edited or autofilled" aria-hidden />
                      Green = edited or autofilled
                    </span>
                  </div>
                )}
                <div className="text-[11px] text-gray-500 dark:text-dark-muted px-2 py-1 border-b border-gray-100 dark:border-dark-border flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="truncate">
                      {editorTool === 'signature'
                        ? (editorTool === 'stamp'
                            ? (selectedStampDataUrl ? 'Click on preview to place stamp' : savedStamps.length === 0 ? 'Create stamps in Settings first' : 'Pick a stamp from the list')
                            : (selectedSignatureDataUrl ? 'Click on preview to place your signature' : savedSignatures.length === 0 ? 'Save your signature in Settings first' : 'Pick a signature from the list'))
                        : textBoxModeActive
                        ? (textBoxPlacementMode === 'checkmark'
                            ? `Text: ${textSubTool} — click to place checkmark (✓)`
                            : textBoxPlacementMode === 'xmark'
                            ? `Text: ${textSubTool} — click to place X mark (✗)`
                            : `Text: ${textSubTool} — click to place`)
                        : editorTool === 'highlight'
                        ? `Highlight: ${highlightSubTool} — drag on the PDF to add`
                        : editorTool === 'draw'
                        ? drawSubTool === 'stamp'
                          ? (selectedStampDataUrl ? 'Click on preview to place stamp' : savedStamps.length === 0 ? 'Create stamps in Settings first' : 'Pick a stamp from the palette above, then click on PDF')
                          : (DRAW_SHAPE_SUBTOOLS.includes(drawSubTool) ? `Draw: ${drawSubTool} — drag on the PDF to place` : drawSubTool === 'pen' ? 'Draw: pen — drag on the PDF to draw' : `Draw: ${drawSubTool}`)
                        : 'Preview — scroll to view PDF'}
                  </span>
                    {(textBoxModeActive || signaturePlaceModeActive || highlightModeActive || drawModeActive) && mousePreview.x != null && mousePreview.y != null && (
                    <span className="font-mono text-[10px] bg-gray-100 dark:bg-dark-hover text-gray-700 dark:text-gray-300 px-1.5 py-0.5 rounded tabular-nums">
                      X: {Math.round(mousePreview.x)} Y: {Math.round(mousePreview.y)}
                    </span>
                  )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setAutoPreviewEnabled((v) => !v)}
                    className="inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-border"
                    title="Toggle building a full PDF preview while editing"
                  >
                    <span
                      className={`inline-flex h-3 w-3 items-center justify-center rounded-full border ${
                        autoPreviewEnabled
                          ? 'bg-[#14B8A6] dark:bg-teal-dm border-[#14B8A6] dark:border-teal-dm'
                          : 'bg-transparent border-gray-300 dark:border-dark-border'
                      }`}
                      aria-hidden="true"
                    >
                      {autoPreviewEnabled && <span className="h-1.5 w-1.5 rounded-full bg-white dark:bg-black" />}
                    </span>
                    <span>{autoPreviewEnabled ? 'Live PDF preview: On' : 'Live PDF preview: Off'}</span>
                  </button>
                </div>
                <div
                  ref={previewContainerRef}
                  className="flex-1 min-h-0 p-2 relative"
                  style={
                    customCursorIcon
                      ? { cursor: 'none' }
                      : editorTool !== 'pointer'
                      ? { cursor: editorCursor }
                      : undefined
                  }
                  onMouseMove={customCursorIcon ? (e) => setCustomCursorPos({ x: e.clientX, y: e.clientY }) : undefined}
                  onMouseLeave={customCursorIcon ? () => setCustomCursorPos(null) : undefined}
                >
                  {customCursorIcon && customCursorPos && (() => {
                    const CursorIcon = customCursorIcon;
                    return (
                      <div
                        className="pointer-events-none fixed z-[9999] flex items-center justify-center"
                        style={{
                          left: customCursorPos.x,
                          top: customCursorPos.y,
                          transform: 'translate(-50%, -50%)',
                        }}
                        aria-hidden
                      >
                        <CursorIcon className="w-6 h-6 text-black drop-shadow-sm" />
                      </div>
                    );
                  })()}
                  {pdfPreviewUrl && (
                    <div
                      key={doc?.id}
                      ref={pdfScrollContainerRef}
                      className="w-full h-full min-h-[50vh] overflow-auto scrollbar-hidden rounded border border-gray-200 dark:border-dark-border flex flex-col items-center gap-2 p-2"
                      onMouseMove={
                        textBoxModeActive || signaturePlaceModeActive || highlightModeActive || drawModeActive
                          ? (e) => {
                              const scrollEl = pdfScrollContainerRef.current;
                              if (!scrollEl) return;
                              const wrappers = scrollEl.querySelectorAll('[data-pdf-page]');
                              for (const w of wrappers) {
                                const r = w.getBoundingClientRect();
                                if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
                                  setMousePreview({ x: e.clientX - r.left, y: e.clientY - r.top });
                                  return;
                                }
                              }
                              setMousePreview({ x: null, y: null });
                            }
                          : undefined
                      }
                      onMouseLeave={
                        textBoxModeActive || signaturePlaceModeActive || highlightModeActive || drawModeActive
                          ? () => setMousePreview({ x: null, y: null })
                          : undefined
                      }
                    >
                      {Array.from({ length: Math.max(0, pdfPageCount) }, (_, i) => (
                        <div
                          key={i}
                          data-pdf-page={i + 1}
                          className="shadow-sm bg-white dark:bg-dark-surface relative"
                          onMouseDown={
                            highlightModeActive
                              ? (e) => {
                                  if (e.target.closest('[data-added-text-id]')) return;
                                  e.preventDefault();
                                  const w = e.currentTarget;
                                  const r = w.getBoundingClientRect();
                                  const page = parseInt(w.getAttribute('data-pdf-page'), 10);
                                  const x = e.clientX - r.left;
                                  const y = e.clientY - r.top;
                                  setHighlightDrag({ pageNum: page, startX: x, startY: y, endX: x, endY: y, previewW: r.width, previewH: r.height });
                                }
                              : drawModeActive && drawSubTool === 'pen'
                              ? (e) => {
                                  if (e.target.closest('[data-added-text-id]')) return;
                                  e.preventDefault();
                                  const w = e.currentTarget;
                                  const r = w.getBoundingClientRect();
                                  const page = parseInt(w.getAttribute('data-pdf-page'), 10);
                                  const x = e.clientX - r.left;
                                  const y = e.clientY - r.top;
                                  setSelectedAddedTextId(null);
                                  setTooltipAnchor(null);
                                  setDrawPath({ pageNum: page, points: [{ x, y }], previewW: r.width, previewH: r.height });
                                }
                              : drawModeActive && DRAW_SHAPE_SUBTOOLS.includes(drawSubTool)
                              ? (e) => {
                                  if (e.target.closest('[data-added-text-id]')) return;
                                  e.preventDefault();
                                  setSelectedAddedTextId(null);
                                  setTooltipAnchor(null);
                                  const w = e.currentTarget;
                                  const r = w.getBoundingClientRect();
                                  const page = parseInt(w.getAttribute('data-pdf-page'), 10);
                                  const x = e.clientX - r.left;
                                  const y = e.clientY - r.top;
                                  setDrawShapeDrag({ pageNum: page, startX: x, startY: y, endX: x, endY: y, previewW: r.width, previewH: r.height, subtype: drawSubTool });
                                }
                              : undefined
                          }
                      onClick={
                        textBoxModeActive || signaturePlaceModeActive
                          ? (e) => {
                                  if (e.target.closest('[data-added-text-id]')) return;
                                  e.stopPropagation();
                                  const w = e.currentTarget;
                                const r = w.getBoundingClientRect();
                                  const page = parseInt(w.getAttribute('data-pdf-page'), 10);
                                  const x = e.clientX - r.left;
                                  const y = e.clientY - r.top;
                                  const placeImageUrl = (editorTool === 'stamp' || (editorTool === 'draw' && drawSubTool === 'stamp')) ? selectedStampDataUrl : selectedSignatureDataUrl;
                                  if (signaturePlaceModeActive && placeImageUrl) {
                                    doAddSignature(page, Math.round(x), Math.round(y), placeImageUrl);
                                    if (editorTool !== 'draw') setEditorTool('pointer');
                                    addLog((editorTool === 'stamp' || (editorTool === 'draw' && drawSubTool === 'stamp')) ? 'Stamp placed on page ' + page : 'Signature placed on page ' + page);
                                  } else if (textBoxModeActive) {
                                    if (textBoxPlacementMode === 'checkmark') {
                                      doAddTextBox(page, Math.round(x), Math.round(y), '✓', newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
                                      addLog(`Checkmark placed on page ${page}`);
                                    } else if (textBoxPlacementMode === 'xmark') {
                                      doAddTextBox(page, Math.round(x), Math.round(y), '✗', newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
                                      addLog(`X mark placed on page ${page}`);
                                    } else if (textBoxPlacementMode === 'dot') {
                                      doAddTextBox(page, Math.round(x), Math.round(y), '•', newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
                                      addLog(`Dot placed on page ${page}`);
                                    } else if (textBoxPlacementMode === 'circle-around') {
                                      doAddTextBox(page, Math.round(x), Math.round(y), '○', newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
                                      addLog(`Circle placed on page ${page}`);
                                    } else if (textBoxPlacementMode === 'crossout') {
                                      doAddMarkup(page, Math.round(x), Math.round(y), 'crossout', pdfScale);
                                      addLog(`Crossout placed on page ${page}`);
                                    } else {
                                    setNewAddPage(page);
                                    setNewAddBoxX(Math.round(x));
                                    setNewAddBoxY(Math.round(y));
                                    addLog(`Text box placed on page ${page} at X=${Math.round(x)}, Y=${Math.round(y)}`);
                                    setTimeout(() => addTextContentRef.current?.focus(), 0);
                                  }
                                }
                              }
                              : undefined
                            }
                          style={
                            customCursorIcon
                              ? { cursor: 'none' }
                              : editorTool !== 'pointer'
                              ? { cursor: editorCursor }
                          : undefined
                      }
                    >
                          <canvas
                            className="block"
                            style={drawModeActive ? { pointerEvents: 'none' } : undefined}
                          />
                          {highlightDrag && highlightDrag.pageNum === i + 1 && (() => {
                            const minX = Math.min(highlightDrag.startX, highlightDrag.endX);
                            const minY = Math.min(highlightDrag.startY, highlightDrag.endY);
                            const w = Math.abs(highlightDrag.endX - highlightDrag.startX);
                            const h = Math.abs(highlightDrag.endY - highlightDrag.startY);
                            return (
                              <div
                                className="absolute pointer-events-none border-2 border-yellow-500 dark:border-yellow-400 bg-yellow-400/40 dark:bg-yellow-500/40"
                                style={{ left: minX, top: minY, width: Math.max(2, w), height: Math.max(2, h) }}
                                aria-hidden
                              />
                            );
                          })()}
                          {drawPath && drawPath.pageNum === i + 1 && drawPath.points.length >= 2 && (
                            <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none" aria-hidden>
                              <path
                                d={`M ${drawPath.points.map((p) => `${p.x},${p.y}`).join(' L ')}`}
                                stroke="#000000"
                                fill="none"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          )}
                          {drawShapeDrag && drawShapeDrag.pageNum === i + 1 && (() => {
                            const minX = Math.min(drawShapeDrag.startX, drawShapeDrag.endX);
                            const minY = Math.min(drawShapeDrag.startY, drawShapeDrag.endY);
                            const w = Math.abs(drawShapeDrag.endX - drawShapeDrag.startX);
                            const h = Math.abs(drawShapeDrag.endY - drawShapeDrag.startY);
                            return (
                              <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none" aria-hidden>
                                {drawShapeDrag.subtype === 'line' || drawShapeDrag.subtype === 'arrow' ? (
                                  <line
                                    x1={drawShapeDrag.startX}
                                    y1={drawShapeDrag.startY}
                                    x2={drawShapeDrag.endX}
                                    y2={drawShapeDrag.endY}
                                    stroke="#000000"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                  />
                                ) : drawShapeDrag.subtype === 'rectangle' ? (
                                  <rect x={minX} y={minY} width={Math.max(1, w)} height={Math.max(1, h)} fill="none" stroke="#000000" strokeWidth="2" />
                                ) : drawShapeDrag.subtype === 'circle' ? (
                                  <ellipse cx={minX + w / 2} cy={minY + h / 2} rx={Math.max(1, w / 2)} ry={Math.max(1, h / 2)} fill="none" stroke="#000000" strokeWidth="2" />
                                ) : drawShapeDrag.subtype === 'polygon' ? (
                                  (() => {
                                    const cx = minX + w / 2; const cy = minY + h / 2;
                                    const r = Math.max(2, Math.min(w, h) / 2);
                                    const pts = Array.from({ length: 6 }, (_, i) => {
                                      const a = (i * 60 - 90) * (Math.PI / 180);
                                      return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
                                    });
                                    return <path d={`M ${pts[0]} L ${pts.slice(1).join(' L ')} Z`} fill="none" stroke="#000000" strokeWidth="2" />;
                                  })()
                                ) : null}
                              </svg>
                            );
                          })()}
                          {addedTexts
                            .filter((t) => t.pageNum === i + 1)
                            .map((t) =>
                              t.type === 'signature' ? (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onMouseDown={(e) => {
                                    e.stopPropagation();
                                    startAddedItemMove(t, e.clientX, e.clientY);
                                  }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (didAddedItemDragRef.current) return;
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute cursor-move rounded overflow-visible ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'hover:ring-2 hover:ring-[#14B8A6] dark:hover:ring-teal-dm'}`}
                                  style={{
                                    left: t.box?.x ?? 0,
                                    top: t.box?.y ?? 0,
                                    width: t.box?.width ?? SIGNATURE_BOX_W,
                                    height: t.box?.height ?? SIGNATURE_BOX_H,
                                  }}
                                >
                                  {t.imageDataUrl && (
                                    <img src={t.imageDataUrl} alt="Signature" className="w-full h-full object-contain pointer-events-none" draggable={false} />
                                  )}
                                  {selectedAddedTextId === t.id && !showingPreviewPdf && (
                                    <div className="absolute -inset-1 border-2 border-[#14B8A6] dark:border-teal-dm rounded pointer-events-none" aria-hidden />
                                  )}
                                  {selectedAddedTextId === t.id && !showingPreviewPdf && (() => {
                                    const handlePos = { n: { left: '50%', top: 0 }, s: { left: '50%', top: '100%' }, e: { left: '100%', top: '50%' }, w: { left: 0, top: '50%' }, ne: { left: '100%', top: 0 }, nw: { left: 0, top: 0 }, se: { left: '100%', top: '100%' }, sw: { left: 0, top: '100%' } };
                                    return (
                                      <>
                                        {Object.keys(handlePos).map((h) => (
                                          <div
                                            key={h}
                                            className="absolute w-2.5 h-2.5 rounded-full bg-[#14B8A6] dark:bg-teal-dm border-2 border-white dark:border-gray-800 cursor-pointer z-10"
                                            style={{ ...handlePos[h], transform: 'translate(-50%, -50%)', width: 10, height: 10 }}
                                            onMouseDown={(ev) => { ev.stopPropagation(); startAddedItemResize(t, h, ev.clientX, ev.clientY); }}
                                            title={`Resize ${h}`}
                                            aria-label={`Resize handle ${h}`}
                                          />
                                        ))}
                                      </>
                                    );
                                  })()}
                                </div>
                              ) : t.type === 'markup' && t.subtype === 'crossout' ? (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute cursor-pointer overflow-visible ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'hover:ring-2 hover:ring-[#14B8A6] dark:hover:ring-teal-dm'}`}
                                  style={{
                                    left: t.box?.x ?? 0,
                                    top: t.box?.y ?? 0,
                                    width: t.box?.width ?? CROSSOUT_BOX_W,
                                    height: t.box?.height ?? CROSSOUT_BOX_H,
                                  }}
                                >
                                  <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
                                    <line x1="0" y1="100" x2="100" y2="0" stroke={t.color || '#000000'} strokeWidth="8" strokeLinecap="round" />
                                  </svg>
                                </div>
                              ) : t.type === 'markup' && (t.subtype === 'highlight' || t.subtype === 'underline' || t.subtype === 'strikethrough') ? (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onMouseDown={(e) => { e.stopPropagation(); startAddedItemMove(t, e.clientX, e.clientY); }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (didAddedItemDragRef.current) return;
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute cursor-move overflow-hidden ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'hover:ring-2 hover:ring-[#14B8A6] dark:hover:ring-teal-dm'} ${selectedAddedTextId === t.id ? 'ring-2 ring-[#14B8A6] dark:ring-teal-dm' : ''}`}
                                  style={{
                                    left: t.box?.x ?? 0,
                                    top: t.box?.y ?? 0,
                                    width: t.box?.width ?? 40,
                                    height: t.box?.height ?? 12,
                                  }}
                                >
                                  {t.subtype === 'highlight' && (
                                    <div className="absolute inset-0 bg-yellow-400/50 dark:bg-yellow-500/50 pointer-events-none" />
                                  )}
                                  {(t.subtype === 'underline' || t.subtype === 'strikethrough') && (
                                    <div
                                      className="absolute left-0 right-0 h-0.5 bg-black dark:bg-gray-200 pointer-events-none"
                                      style={{
                                        top: t.subtype === 'underline' ? '100%' : '50%',
                                        marginTop: t.subtype === 'underline' ? '-2px' : '-1px',
                                      }}
                                    />
                                  )}
                                  {selectedAddedTextId === t.id && !showingPreviewPdf && (() => {
                                    const handlePos = { n: { left: '50%', top: 0 }, s: { left: '50%', top: '100%' }, e: { left: '100%', top: '50%' }, w: { left: 0, top: '50%' }, ne: { left: '100%', top: 0 }, nw: { left: 0, top: 0 }, se: { left: '100%', top: '100%' }, sw: { left: 0, top: '100%' } };
                                    return (
                                      <>
                                        {Object.keys(handlePos).map((h) => (
                                          <div key={h} className="absolute w-2.5 h-2.5 rounded-full bg-[#14B8A6] dark:bg-teal-dm border-2 border-white dark:border-gray-800 cursor-pointer z-10" style={{ ...handlePos[h], transform: 'translate(-50%, -50%)', width: 10, height: 10 }} onMouseDown={(ev) => { ev.stopPropagation(); startAddedItemResize(t, h, ev.clientX, ev.clientY); }} title={`Resize ${h}`} aria-label={`Resize ${h}`} />
                                        ))}
                                      </>
                                    );
                                  })()}
                                </div>
                              ) : t.type === 'draw' && (t.start && t.end ? ['line', 'arrow'].includes(t.subtype) : ['rectangle', 'circle', 'polygon'].includes(t.subtype)) ? (() => {
                                const pad = DRAW_HIT_PADDING;
                                let left, top, w, h;
                                if (t.start && t.end) {
                                  left = Math.min(t.start.x, t.end.x) - pad;
                                  top = Math.min(t.start.y, t.end.y) - pad;
                                  w = Math.abs(t.end.x - t.start.x) + 2 * pad;
                                  h = Math.abs(t.end.y - t.start.y) + 2 * pad;
                                  if (w < 24) { left -= (24 - w) / 2; w = 24; }
                                  if (h < 24) { top -= (24 - h) / 2; h = 24; }
                                } else if (t.box) {
                                  left = (t.box.x ?? 0) - pad;
                                  top = (t.box.y ?? 0) - pad;
                                  w = (t.box.width ?? 40) + 2 * pad;
                                  h = (t.box.height ?? 40) + 2 * pad;
                                } else return null;
                                return (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onMouseDown={(e) => { if (editorTool !== 'draw') { e.stopPropagation(); startAddedItemMove(t, e.clientX, e.clientY); } }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (editorTool === 'draw') return;
                                    if (didAddedItemDragRef.current) return;
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute ${editorTool === 'draw' ? 'pointer-events-none' : 'cursor-move'} ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'hover:ring-2 hover:ring-[#14B8A6] dark:hover:ring-teal-dm'} ${selectedAddedTextId === t.id ? 'ring-2 ring-[#14B8A6] dark:ring-teal-dm' : ''}`}
                                  style={{ left, top, width: w, height: h }}
                                  aria-label={`Draw ${t.subtype}`}
                                >
                                  <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none" viewBox={`${left} ${top} ${w} ${h}`}>
                                    {t.start && t.end ? (
                                      <>
                                        <line
                                          x1={t.start.x}
                                          y1={t.start.y}
                                          x2={t.end.x}
                                          y2={t.end.y}
                                          stroke={t.color || '#000000'}
                                          strokeWidth="2"
                                          strokeLinecap="round"
                                        />
                                        {t.subtype === 'arrow' && (() => {
                                          const dx = t.end.x - t.start.x;
                                          const dy = t.end.y - t.start.y;
                                          const len = Math.hypot(dx, dy) || 1;
                                          const ux = dx / len;
                                          const uy = dy / len;
                                          const al = Math.min(len * 0.25, 10);
                                          const h1x = t.end.x - ux * al + uy * al * 0.5;
                                          const h1y = t.end.y - uy * al - ux * al * 0.5;
                                          const h2x = t.end.x - ux * al - uy * al * 0.5;
                                          const h2y = t.end.y - uy * al + ux * al * 0.5;
                                          return (
                                            <>
                                              <line x1={t.end.x} y1={t.end.y} x2={h1x} y2={h1y} stroke={t.color || '#000000'} strokeWidth="2" strokeLinecap="round" />
                                              <line x1={t.end.x} y1={t.end.y} x2={h2x} y2={h2y} stroke={t.color || '#000000'} strokeWidth="2" strokeLinecap="round" />
                                            </>
                                          );
                                        })()}
                                      </>
                                    ) : t.box ? (
                                      t.subtype === 'rectangle' ? (
                                        <rect
                                          x={t.box.x}
                                          y={t.box.y}
                                          width={t.box.width}
                                          height={t.box.height}
                                          fill="none"
                                          stroke={t.color || '#000000'}
                                          strokeWidth="2"
                                        />
                                      ) : t.subtype === 'circle' ? (
                                        <ellipse
                                          cx={t.box.x + t.box.width / 2}
                                          cy={t.box.y + t.box.height / 2}
                                          rx={t.box.width / 2}
                                          ry={t.box.height / 2}
                                          fill="none"
                                          stroke={t.color || '#000000'}
                                          strokeWidth="2"
                                        />
                                      ) : t.subtype === 'polygon' ? (
                                        (() => {
                                          const cx = t.box.x + t.box.width / 2;
                                          const cy = t.box.y + t.box.height / 2;
                                          const r = Math.min(t.box.width, t.box.height) / 2;
                                          const pts = Array.from({ length: 6 }, (_, i) => {
                                            const a = (i * 60 - 90) * (Math.PI / 180);
                                            return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
                                          });
                                          return <path d={`M ${pts[0]} L ${pts.slice(1).join(' L ')} Z`} fill="none" stroke={t.color || '#000000'} strokeWidth="2" />;
                                        })()
                                      ) : null
                                    ) : null}
                                  </svg>
                                  {t.box && selectedAddedTextId === t.id && !showingPreviewPdf && editorTool !== 'draw' && (() => {
                                    const handlePos = { n: { left: '50%', top: 0 }, s: { left: '50%', top: '100%' }, e: { left: '100%', top: '50%' }, w: { left: 0, top: '50%' }, ne: { left: '100%', top: 0 }, nw: { left: 0, top: 0 }, se: { left: '100%', top: '100%' }, sw: { left: 0, top: '100%' } };
                                    return (
                                      <div className="absolute pointer-events-auto z-10" style={{ left: pad, top: pad, width: t.box.width ?? 40, height: t.box.height ?? 40 }}>
                                        <div className="absolute -inset-1 border-2 border-[#14B8A6] dark:border-teal-dm rounded pointer-events-none" aria-hidden />
                                        {Object.keys(handlePos).map((h) => (
                                          <div key={h} className="absolute w-2.5 h-2.5 rounded-full bg-[#14B8A6] dark:bg-teal-dm border-2 border-white dark:border-gray-800 cursor-pointer" style={{ ...handlePos[h], transform: 'translate(-50%, -50%)', width: 10, height: 10 }} onMouseDown={(ev) => { ev.stopPropagation(); startAddedItemResize(t, h, ev.clientX, ev.clientY); }} title={`Resize ${h}`} aria-label={`Resize ${h}`} />
                                        ))}
                                      </div>
                                    );
                                  })()}
                                </div>
                                );
                              })() : t.type === 'draw' && t.subtype === 'pen' && Array.isArray(t.path) && t.path.length >= 2 ? (() => {
                                const pad = DRAW_HIT_PADDING;
                                const xs = t.path.map((p) => p.x);
                                const ys = t.path.map((p) => p.y);
                                const minX = Math.min(...xs);
                                const minY = Math.min(...ys);
                                const maxX = Math.max(...xs);
                                const maxY = Math.max(...ys);
                                const left = minX - pad;
                                const top = minY - pad;
                                const w = Math.max(24, maxX - minX + 2 * pad);
                                const h = Math.max(24, maxY - minY + 2 * pad);
                                return (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onMouseDown={(e) => { if (editorTool !== 'draw') { e.stopPropagation(); startAddedItemMove(t, e.clientX, e.clientY); } }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (editorTool === 'draw') return;
                                    if (didAddedItemDragRef.current) return;
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute ${editorTool === 'draw' ? 'pointer-events-none' : 'cursor-move'} ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'hover:ring-2 hover:ring-[#14B8A6] dark:hover:ring-teal-dm'} ${selectedAddedTextId === t.id ? 'ring-2 ring-[#14B8A6] dark:ring-teal-dm' : ''}`}
                                  style={{ left, top, width: w, height: h }}
                                  aria-label="Drawn path"
                                >
                                  <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none" viewBox={`${left} ${top} ${w} ${h}`}>
                                    <path
                                      d={`M ${t.path.map((p) => `${p.x},${p.y}`).join(' L ')}`}
                                      stroke={t.color || '#000000'}
                                      fill="none"
                                      strokeWidth="2"
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                    />
                                  </svg>
                                </div>
                                );
                              })(                              ) : (
                                (() => {
                                  const isTextSubToolSymbol = t.type === 'box' && ['✓', '✗', '•', '○'].includes(t.text);
                                  return (
                                <div
                                  key={t.id}
                                  data-added-text-id={t.id}
                                  role="button"
                                  tabIndex={0}
                                  onMouseDown={isTextSubToolSymbol ? undefined : (e) => { e.stopPropagation(); startAddedItemMove(t, e.clientX, e.clientY); }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (!isTextSubToolSymbol && didAddedItemDragRef.current) return;
                                    setSelectedAddedTextId(t.id);
                                    setTooltipAnchor({ x: e.clientX, y: e.clientY });
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setSelectedAddedTextId(t.id);
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      setTooltipAnchor({ x: rect.left + rect.width / 2, y: rect.bottom });
                                    }
                                  }}
                                  className={`absolute px-1.5 py-1 overflow-visible ${isTextSubToolSymbol ? 'cursor-pointer' : 'cursor-move'} ${showingPreviewPdf ? 'opacity-0 hover:opacity-0' : 'bg-transparent hover:bg-black/5 dark:hover:bg-white/10'} ${selectedAddedTextId === t.id ? 'ring-2 ring-[#14B8A6] dark:ring-teal-dm' : ''}`}
                                  style={{
                                    left: t.box?.x ?? 0,
                                    top: t.box?.y ?? 0,
                                    width: Math.max(20, t.box?.width ?? boxWidthFromSize(t.size)),
                                    height: Math.max(14, t.box?.height ?? boxHeightFromSize(t.size)),
                                    fontSize: pdfScale ? Math.max(8, Math.min(200, (t.size ?? 11) * pdfScale)) : (t.size ?? 11),
                                    color: t.color || '#000000',
                                    fontWeight: t.bold ? 'bold' : 'normal',
                                    fontStyle: t.italic ? 'italic' : 'normal',
                                    textDecoration: (t.underline && t.strikethrough) ? 'underline line-through' : t.underline ? 'underline' : t.strikethrough ? 'line-through' : 'none',
                                  }}
                                >
                                  <span className="whitespace-pre-wrap break-words block pointer-events-none">{t.text}</span>
                                  {selectedAddedTextId === t.id && !showingPreviewPdf && !isTextSubToolSymbol && (() => {
                                    const handlePos = { n: { left: '50%', top: 0 }, s: { left: '50%', top: '100%' }, e: { left: '100%', top: '50%' }, w: { left: 0, top: '50%' }, ne: { left: '100%', top: 0 }, nw: { left: 0, top: 0 }, se: { left: '100%', top: '100%' }, sw: { left: 0, top: '100%' } };
                                    return (
                                      <>
                                        {Object.keys(handlePos).map((h) => (
                                          <div key={h} className="absolute w-2.5 h-2.5 rounded-full bg-[#14B8A6] dark:bg-teal-dm border-2 border-white dark:border-gray-800 cursor-pointer z-10" style={{ ...handlePos[h], transform: 'translate(-50%, -50%)', width: 10, height: 10 }} onMouseDown={(ev) => { ev.stopPropagation(); startAddedItemResize(t, h, ev.clientX, ev.clientY); }} title={`Resize ${h}`} aria-label={`Resize ${h}`} />
                                        ))}
                                      </>
                                    );
                                  })()}
                                </div>
                                  );
                                })()
                              )
                            )}
                          {textBoxModeActive && newAddPage === i + 1 && (() => {
                            const phText = (newAddText || '').trim();
                            const phDims = phText
                              ? computeTextBoxSize(phText, newAddSize, pdfScale ?? 1)
                              : { width: Math.max(60, boxWidthFromSize(newAddSize)), height: Math.max(24, boxHeightFromSize(newAddSize)) };
                            return (
                            <div
                              key="placeholder"
                              className="absolute pointer-events-none rounded-xl px-1.5 py-1 bg-transparent overflow-visible"
                              style={{
                                left: newAddBoxX - phDims.width / 2,
                                top: newAddBoxY - phDims.height / 2,
                                width: phDims.width,
                                height: phDims.height,
                                fontSize: pdfScale ? Math.max(8, Math.min(200, newAddSize * pdfScale)) : newAddSize,
                                color: newAddColor,
                                fontWeight: newAddBold ? 'bold' : 'normal',
                                fontStyle: newAddItalic ? 'italic' : 'normal',
                                textDecoration: (newAddUnderline && newAddStrikethrough) ? 'underline line-through' : newAddUnderline ? 'underline' : newAddStrikethrough ? 'line-through' : 'none',
                              }}
                            >
                              <span className="whitespace-pre-wrap break-words block">
                                {newAddText.trim() || (
                                  <span className="text-gray-400 dark:text-dark-muted italic">Type in the box to the right →</span>
                                )}
                              </span>
                            </div>
                            );
                          })()}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div
                className={`flex flex-col bg-gray-50 dark:bg-dark-surface overflow-hidden shrink-0 border-l border-gray-200 dark:border-dark-border transition-[width] duration-200 ease-out ${formFieldsExpanded ? 'w-80 sm:w-96' : 'w-12'}`}
              >
                <button
                  type="button"
                  onClick={() => setFormFieldsExpanded((e) => !e)}
                  className={`flex items-center border-b border-gray-200 dark:border-dark-border hover:bg-gray-100/80 dark:hover:bg-dark-hover transition-colors ${formFieldsExpanded ? 'justify-between w-full px-3 py-2' : 'flex-col justify-start gap-2 w-full py-4 px-1'}`}
                  aria-expanded={formFieldsExpanded}
                  title={formFieldsExpanded ? 'Collapse Form & tools panel' : 'Expand Form & tools panel'}
                  aria-label={formFieldsExpanded ? 'Collapse Form & tools panel' : 'Expand Form & tools panel'}
                >
                  <span
                    className="text-sm font-medium text-gray-700 dark:text-white select-none"
                    style={!formFieldsExpanded ? { writingMode: 'vertical-rl', textOrientation: 'mixed', transform: 'rotate(-180deg)' } : undefined}
                  >
                    Form &amp; tools
                  </span>
                  {formFieldsExpanded ? (
                    <HiOutlineChevronRight className="w-4 h-4 text-gray-500 dark:text-dark-muted shrink-0" aria-hidden />
                  ) : (
                    <HiOutlineChevronLeft className="w-4 h-4 text-gray-500 dark:text-dark-muted shrink-0" aria-hidden />
                  )}
                </button>
                {formFieldsExpanded && (
                  <>
                    <div className="flex border-b border-gray-200 dark:border-dark-border">
                      {['form', 'suggestions', 'textbox'].map((tab) => (
                        <button
                          key={tab}
                          type="button"
                          onClick={() => setActiveTab(tab)}
                          className={`flex-1 px-2 py-2 text-xs font-medium capitalize ${
                            activeTab === tab
                              ? 'text-[#14B8A6] dark:text-teal-dm border-b-2 border-[#14B8A6] dark:border-teal-dm bg-white/50 dark:bg-dark-hover/50'
                              : 'text-gray-600 dark:text-dark-muted hover:bg-gray-100 dark:hover:bg-dark-hover'
                          }`}
                        >
                          {tab === 'form' && <HiOutlineDocumentText className="w-4 h-4 inline mr-1" />}
                          {tab === 'suggestions' && <HiOutlineSparkles className="w-4 h-4 inline mr-1" />}
                          {tab === 'textbox' && <HiOutlinePencil className="w-4 h-4 inline mr-1" />}
                          {tab === 'form' ? 'Form' : tab === 'suggestions' ? 'Suggestions' : 'Text box'}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-col flex-1 min-h-0 overflow-auto scrollbar-hidden">
                      {activeTab === 'form' && (
                        <div className="p-3">
                          <p className="text-xs font-semibold text-gray-600 dark:text-dark-muted uppercase mb-1">Fill from opportunity</p>
                          <p className="text-xs text-gray-500 dark:text-dark-muted mb-3">
                            Autofill from opportunity data or edit each field below.
                          </p>
                          {pdfFields.length === 0 ? (
                            <div className="rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover p-4 text-center">
                              <HiOutlineDocumentText className="w-10 h-10 mx-auto text-gray-400 dark:text-dark-muted mb-2" />
                              <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">No fillable form fields</p>
                              <p className="text-xs text-gray-500 dark:text-dark-muted mb-3">
                                This PDF has no fillable fields. Use the Suggestions tab to add profile data or the Text box tab to add text.
                              </p>
                              <button
                                type="button"
                                onClick={() => setActiveTab('suggestions')}
                                className="text-xs text-[#14B8A6] dark:text-teal-dm font-medium"
                              >
                                Open Suggestions →
                              </button>
                            </div>
                          ) : (
                            <ul className="rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover overflow-hidden">
                              <li className="flex flex-col gap-2 px-3 py-2.5">
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    disabled={fillingFromOpportunity}
                                    title="Fill form fields from opportunity data"
                                    aria-label="Autofill form from opportunity data"
                                    onClick={async () => {
                                      if (!opportunityId || !doc?.id || fillingFromOpportunity) return;
                                      setFillingFromOpportunity(true);
                                      setError('');
                                      try {
                                        const fieldNames = pdfFields.map((f) => f.name);
                                        const fieldTypes = Object.fromEntries(pdfFields.map((f) => [f.name, f.type]));
                                        const currentValues = fieldValuesRef.current ?? {};
                                        const res = await opportunitiesAPI.autofillPreview(opportunityId, doc.id, fieldNames, fieldTypes, currentValues);
                                        const fieldsData = res?.data?.fields ?? {};
                                        setFieldValues((prev) => {
                                          const next = { ...prev };
                                          for (const f of pdfFields) {
                                            if (fieldsData[f.name] == null) continue;
                                            next[f.name] = f.type === 'checkbox'
                                              ? Boolean(fieldsData[f.name])
                                              : String(fieldsData[f.name]);
                                          }
                                          return next;
                                        });
                                        addLog('Filled form fields from opportunity data');
                                      } catch (e) {
                                        setError(detailToMessage(e?.response?.data?.detail) || e?.message || 'Failed to load opportunity data');
                                      } finally {
                                        setFillingFromOpportunity(false);
                                      }
                                    }}
                                    className="flex-1 px-3 py-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated text-sm font-medium hover:bg-[#0d9488] dark:hover:bg-teal-dm/90 disabled:opacity-50 transition-colors"
                                  >
                                    {fillingFromOpportunity ? 'Filling…' : 'Autofill'}
                                  </button>
                                  <button
                                    type="button"
                                    disabled={fillingFromOpportunity}
                                    onClick={() => setFieldValues((prev) => Object.fromEntries(Object.keys(prev).map((k) => [k, pdfFields.find((f) => f.name === k)?.type === 'checkbox' ? false : ''])))}
                                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 text-sm bg-white dark:bg-dark-surface hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors disabled:opacity-50"
                                    title="Clear all form field values"
                                    aria-label="Clear all form field values"
                                  >
                                    Clear
                                  </button>
                                </div>
                                {fillingFromOpportunity && (
                                  <div className="flex flex-col gap-1 w-full" role="progressbar" aria-valuetext="Filling form fields">
                                    <p className="text-xs font-medium text-gray-600 dark:text-gray-400">Matching fields…</p>
                                    <div className="h-1.5 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                                      <div className="h-full w-1/3 rounded-full bg-[#14B8A6] dark:bg-teal-dm animate-autofill-progress origin-left" />
                                    </div>
                                  </div>
                                )}
                              </li>
                              {pdfFields.map((f) => {
                                const raw = fieldValues[f.name];
                                const hasValue = f.type === 'checkbox'
                                  ? (raw === true || String(raw).toLowerCase() === 'yes')
                                  : (raw != null && String(raw).trim() !== '' && String(raw).trim() !== '-');
                                return (
                                <li
                                  key={f.name}
                                  className={`flex items-center gap-2 px-3 py-1.5 border-t border-gray-200/80 dark:border-dark-border/80 min-h-[28px] ${hasValue ? 'bg-amber-50 dark:bg-amber-900/20' : ''}`}
                                >
                                  <label className="text-[11px] font-medium text-gray-600 dark:text-dark-muted shrink-0 min-w-[88px] truncate" title={f.name}>
                                    {getFieldDisplayLabel(f.name)}
                                  </label>
                                  {f.type === 'checkbox' ? (
                                    <input
                                      type="checkbox"
                                      checked={!!fieldValues[f.name]}
                                      onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.name]: e.target.checked }))}
                                      className="h-3 w-3 rounded border-gray-300 dark:border-dark-border text-[#14B8A6] dark:text-teal-dm shrink-0"
                                    />
                                  ) : (
                                    <input
                                      type="text"
                                      value={fieldValues[f.name] ?? ''}
                                      onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                                      placeholder="—"
                                      className="flex-1 min-w-0 text-[11px] py-0.5 px-1.5 bg-transparent border-0 border-b border-gray-300/80 dark:border-dark-border/80 rounded-none text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-muted focus:ring-0 focus:border-[#14B8A6] dark:focus:border-teal-dm focus:outline-none"
                                    />
                                  )}
                                </li>
                              ); })}
                            </ul>
                          )}
                        </div>
                      )}

                      {activeTab === 'suggestions' && (
                        <div className="p-3">
                          <p className="text-xs font-semibold text-gray-600 dark:text-dark-muted uppercase mb-1">Suggested from your profile</p>
                          <p className="text-xs text-gray-500 dark:text-dark-muted mb-3">
                            Click a suggestion to add it to the PDF.
                          </p>
                          {Object.keys(profileSuggestions).length === 0 ? (
                            <p className="text-xs text-gray-500 dark:text-dark-muted">Load your profile in Settings to see suggestions.</p>
                          ) : (
                            <ul className="rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover overflow-hidden">
                              {Object.entries(profileSuggestions).map(([label, value], index) => {
                                const isSignature = label === 'Signature';
                                const useSavedSignature = isSignature && selectedSignatureDataUrl;
                                return (
                                  <li key={label}>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        if (isSignature && savedSignatures.length === 0) {
                                          addLog('Save your signature in Settings first, then use it here.');
                                          return;
                                        }
                                        if (useSavedSignature) {
                                          setEditorTool('signature');
                                          addLog('Click on the PDF to place your saved signature.');
                                        } else {
                                          setActiveTab('textbox');
                                          setNewAddText(String(value));
                                          setTextSubTool('text');
                                          setEditorTool('text');
                                          addLog('Text box tool selected. Click on the PDF to place "' + (String(value).length > 20 ? String(value).slice(0, 20) + '…' : value) + '".');
                                        }
                                      }}
                                      className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors ${index > 0 ? 'border-t border-gray-200/80 dark:border-dark-border/80' : ''}`}
                                    >
                                      <span className="text-xs font-medium text-gray-700 dark:text-gray-200 flex items-center gap-1.5">
                                        {label === 'Phone' && <HiOutlinePhone className="w-3.5 h-3.5 shrink-0" />}
                                        {label === 'Company Name' && <HiOutlineOfficeBuilding className="w-3.5 h-3.5 shrink-0" />}
                                        {label === 'Company Address' && <HiOutlineLocationMarker className="w-3.5 h-3.5 shrink-0" />}
                                        {label === 'Date' && <HiOutlineCalendar className="w-3.5 h-3.5 shrink-0" />}
                                        {label}
                                      </span>
                                      {isSignature && selectedSignatureDataUrl ? (
                                        <img src={selectedSignatureDataUrl} alt="Your signature" className="h-6 max-w-[100px] object-contain object-right" />
                                      ) : (
                                        <span className="text-xs text-gray-600 dark:text-gray-300 truncate max-w-[140px]" title={String(value)}>
                                          {String(value).length > 20 ? String(value).slice(0, 20) + '…' : value}
                                        </span>
                                      )}
                                    </button>
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                        </div>
                      )}

                      {activeTab === 'textbox' && (
                        <div className="p-3 space-y-4">
                          <div>
                            <label className="text-xs font-medium text-gray-600 dark:text-dark-muted block mb-1.5">Place on PDF</label>
                            <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                                onClick={() => setPlacementMode('text')}
                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors ${textBoxPlacementMode === 'text' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated border-[#14B8A6] dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-border'}`}
                                title="Click on PDF to place text"
                                aria-label="Place text on PDF"
                            >
                              <HiOutlineCursorClick className="w-4 h-4" />
                                Text
                              </button>
                              <button
                                type="button"
                                onClick={() => setPlacementMode('checkmark')}
                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors ${textBoxPlacementMode === 'checkmark' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated border-[#14B8A6] dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-border'}`}
                                title="Click on PDF to place a checkmark (✓)"
                                aria-label="Place checkmark on PDF"
                              >
                                <span className="font-bold text-lg leading-none" style={{ color: textBoxPlacementMode === 'checkmark' ? undefined : 'currentColor' }}>✓</span>
                                Checkmark
                              </button>
                              <button
                                type="button"
                                onClick={() => setPlacementMode('xmark')}
                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors ${textBoxPlacementMode === 'xmark' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated border-[#14B8A6] dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-border'}`}
                                title="Click on PDF to place an X mark (✗)"
                                aria-label="Place X mark on PDF"
                              >
                                <span className="font-bold text-lg leading-none" style={{ color: textBoxPlacementMode === 'xmark' ? undefined : 'currentColor' }}>✗</span>
                                X mark
                            </button>
                          </div>
                          </div>
                          {(textBoxPlacementMode === 'checkmark' || textBoxPlacementMode === 'xmark') && (
                            <div className="rounded-lg bg-[#14B8A6]/10 dark:bg-teal-dm/20 border border-[#14B8A6]/30 dark:border-teal-dm/40 p-2.5 text-xs text-gray-800 dark:text-gray-200">
                              <p className="font-semibold mb-1">How to place {textBoxPlacementMode === 'checkmark' ? '✓' : '✗'}:</p>
                              <ol className="list-decimal list-inside space-y-0.5 text-[11px]">
                                <li>Click <strong>Checkmark</strong> or <strong>X mark</strong> above.</li>
                                <li>With the pointer now active, click on the PDF preview (left) where you want the symbol. You can click multiple times to add more.</li>
                              </ol>
                              <p className="mt-1.5 text-[11px] text-gray-600 dark:text-gray-300">Use <strong>Size</strong> and <strong>Color</strong> below to change how they look.</p>
                            </div>
                          )}
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className="text-xs font-medium text-gray-600 dark:text-dark-muted block mb-0.5">Page</label>
                              <input
                                type="number"
                                min={1}
                                max={Math.max(1, pdfPageCount)}
                                value={newAddPage}
                                onChange={(e) => setNewAddPage(Math.max(1, parseInt(e.target.value, 10) || 1))}
                                className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-dark-border rounded-lg bg-white dark:bg-dark-hover text-gray-900 dark:text-white"
                              />
                            </div>
                            <div>
                              <label className="text-xs font-medium text-gray-600 dark:text-dark-muted block mb-0.5">Size</label>
                              <input
                                type="number"
                                min={6}
                                max={72}
                                value={newAddSize}
                                onChange={(e) => setNewAddSize(Number(e.target.value) || 11)}
                                className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-dark-border rounded-lg bg-white dark:bg-dark-hover text-gray-900 dark:text-white"
                              />
                            </div>
                          </div>
                          <div>
                            <label className="text-xs font-medium text-gray-600 dark:text-dark-muted block mb-1">Color</label>
                            <div className="flex flex-wrap gap-1.5 items-center">
                              {TEXT_BOX_COLORS.map((hex) => (
                                <button
                                  key={hex}
                                  type="button"
                                  onClick={() => setNewAddColor(hex)}
                                  className={`w-6 h-6 rounded-full border-2 hover:scale-110 transition-transform ${hex === '#ffffff' ? 'border-gray-300 dark:border-dark-border' : ''}`}
                                  style={{
                                    backgroundColor: hex,
                                    ...(newAddColor === hex ? { borderColor: '#14B8A6', borderWidth: 2 } : {}),
                                  }}
                                  title={hex}
                                  aria-label={`Color ${hex}`}
                                />
                              ))}
                              <label className="flex items-center gap-1 cursor-pointer">
                                <input
                                  type="color"
                                  value={newAddColor}
                                  onChange={(e) => setNewAddColor(e.target.value)}
                                  className="w-6 h-6 rounded cursor-pointer border border-gray-300 dark:border-dark-border"
                                  title="Custom color"
                                />
                                <span className="text-[10px] text-gray-500 dark:text-dark-muted">Custom</span>
                              </label>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium text-gray-600 dark:text-dark-muted">Style</span>
                            <button
                              type="button"
                              onClick={() => setNewAddBold((b) => !b)}
                              className={`px-2.5 py-1.5 text-sm font-bold rounded-lg border transition-colors ${
                                newAddBold
                                  ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm'
                                  : 'bg-white dark:bg-dark-hover text-gray-700 dark:text-gray-200 border-gray-300 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border'
                              }`}
                              title="Bold text"
                              aria-label="Bold text"
                            >
                              B
                            </button>
                            <button
                              type="button"
                              onClick={() => setNewAddItalic((i) => !i)}
                              className={`px-2.5 py-1.5 text-sm rounded-lg border transition-colors italic ${
                                newAddItalic
                                  ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm'
                                  : 'bg-white dark:bg-dark-hover text-gray-700 dark:text-gray-200 border-gray-300 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border'
                              }`}
                              title="Italic text"
                              aria-label="Italic text"
                            >
                              I
                            </button>
                            <button
                              type="button"
                              onClick={() => setNewAddUnderline((u) => !u)}
                              className={`px-2.5 py-1.5 text-sm rounded-lg border transition-colors ${newAddUnderline ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-border'}`}
                              title="Underline text"
                              aria-label="Underline text"
                              style={{ textDecoration: 'underline' }}
                            >
                              U
                            </button>
                            <button
                              type="button"
                              onClick={() => setNewAddStrikethrough((s) => !s)}
                              className={`px-2.5 py-1.5 text-sm rounded-lg border transition-colors ${newAddStrikethrough ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-border'}`}
                              title="Strikethrough text"
                              aria-label="Strikethrough text"
                              style={{ textDecoration: 'line-through' }}
                            >
                              S
                            </button>
                          </div>
                          {textBoxPlacementMode === 'text' && (
                          <p className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-dark-muted bg-white/50 dark:bg-dark-hover/30 rounded-lg px-2 py-1.5">
                            <HiOutlineCursorClick className="w-3.5 h-3.5 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                              <span>Type below, then click on the PDF to place. Or click on the PDF first to set position.</span>
                          </p>
                          )}
                          <div>
                            <label className="text-xs font-bold italic text-gray-600 dark:text-dark-muted block mb-1">Content</label>
                            <textarea
                              ref={addTextContentRef}
                              value={newAddText}
                              onChange={(e) => setNewAddText(e.target.value)}
                              placeholder="Enter the text to add to the PDF…"
                              rows={3}
                              className="w-full px-2.5 py-2 text-sm border border-gray-300 dark:border-dark-border rounded-lg focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-[#14B8A6] dark:focus:border-teal-dm resize-y bg-white dark:bg-dark-hover text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-muted"
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
          doAddTextBox(newAddPage, newAddBoxX, newAddBoxY, newAddText, newAddSize, newAddColor, newAddBold, newAddItalic, newAddUnderline, newAddStrikethrough, pdfScale);
          setNewAddText('');
          setTimeout(() => addTextContentRef.current?.focus(), 0);
                              }}
                              disabled={!newAddText.trim()}
                              title={`Add text to page ${newAddPage} (Shift+Enter)`}
                              aria-label={`Add text to page ${newAddPage}`}
                              className="inline-flex items-center justify-center p-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white hover:bg-[#0d9488] dark:hover:bg-teal-dm/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              <HiOutlinePlus className="w-4 h-4" />
                            </button>
                            <span className="text-[10px] text-gray-500 dark:text-dark-muted">Add to page {newAddPage}</span>
                          </div>
                          {addedTexts.length > 0 && (
                            <div className="pt-2 border-t border-gray-200 dark:border-dark-border">
                              <p className="text-xs font-semibold text-gray-600 dark:text-dark-muted mb-2">Added text &amp; signatures</p>
                              <ul className="space-y-1.5">
                                {addedTexts.map((t) => (
                                  <li
                                    key={t.id}
                                    className="flex items-center gap-2 text-xs bg-white dark:bg-dark-hover border border-gray-200 dark:border-dark-border rounded-lg px-2.5 py-2 text-gray-900 dark:text-white"
                                  >
                                    <span
                                      className="flex-1 truncate"
                                      title={t.type === 'signature' ? 'Signature' : t.type === 'markup' ? (t.subtype === 'crossout' ? 'Crossout' : t.subtype === 'highlight' ? 'Highlight' : t.subtype === 'underline' ? 'Underline' : t.subtype === 'strikethrough' ? 'Strikethrough' : 'Markup') : t.type === 'draw' ? 'Draw' : t.text}
                                      style={{
                                        fontWeight: t.bold ? 'bold' : 'normal',
                                        fontStyle: t.italic ? 'italic' : 'normal',
                                        textDecoration: (t.underline && t.strikethrough) ? 'underline line-through' : t.underline ? 'underline' : t.strikethrough ? 'line-through' : 'none',
                                      }}
                                    >
                                      {t.type === 'signature' ? 'Signature' : t.type === 'markup' ? (t.subtype === 'crossout' ? 'Crossout' : t.subtype === 'highlight' ? 'Highlight' : t.subtype === 'underline' ? 'Underline' : t.subtype === 'strikethrough' ? 'Strikethrough' : 'Markup') : t.type === 'draw' ? 'Draw' : `"${t.text}"`}
                                    </span>
                                    <span className="shrink-0 text-gray-500 dark:text-dark-muted">p{t.pageNum}</span>
                                    <button
                                      type="button"
                                      onClick={() => removeAddedText(t.id)}
                                      className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                      title="Remove this item from the PDF"
                                      aria-label="Remove this item from the PDF"
                                    >
                                      <HiOutlineTrash className="w-3.5 h-3.5" />
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {textAddLog.length > 0 && (
                            <div className="border-t border-gray-200 dark:border-dark-border pt-3 mt-3">
                              <p className="text-xs font-medium text-gray-700 dark:text-gray-200 mb-1.5">Activity log</p>
                              <ul className="max-h-28 overflow-y-auto scrollbar-hidden space-y-1 text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-dark-hover rounded px-2 py-1.5 border border-gray-100 dark:border-dark-border">
                                {textAddLog.map((entry) => (
                                  <li key={entry.id} className="flex gap-2">
                                    <span className="text-gray-400 dark:text-dark-muted shrink-0">{entry.time}</span>
                                    <span>{entry.message}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="p-3 border-t border-gray-200 dark:border-dark-border shrink-0 flex items-center justify-end gap-2 flex-wrap">
                      <button
                        type="button"
                        onClick={() => handleSavePdf(false)}
                        disabled={saving}
                        title={saving ? 'Saving…' : 'Save (overwrite current document) — Ctrl+S'}
                        aria-label={saving ? 'Saving…' : 'Save document'}
                        className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated hover:bg-[#0D9488] dark:hover:bg-teal-dm/90 disabled:opacity-50 transition-colors text-sm font-medium"
                      >
                        {saving ? (
                          <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                        ) : (
                          <HiOutlineSave className="w-4 h-4" />
                        )}
                        {saving ? 'Saving…' : 'Save'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSavePdf(true)}
                        disabled={saving}
                        title={saving ? 'Saving…' : 'Save as new document (keeps current file, adds new attachment)'}
                        aria-label={saving ? 'Saving…' : 'Save as new document'}
                        className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border-2 border-[#14B8A6] dark:border-teal-dm text-[#14B8A6] dark:text-teal-dm bg-transparent hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/10 disabled:opacity-50 transition-colors text-sm font-medium"
                      >
                        {saving ? (
                          <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                        ) : (
                          <HiOutlineSave className="w-4 h-4" />
                        )}
                        {saving ? 'Saving…' : 'Save as new'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {!loading && isWORD && !pdfBytes && (
            <div className="flex-1 p-4">
              <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
                This Word document could not be converted to PDF for editing (LibreOffice may be missing on the server). Edit the document in your preferred editor, then upload the revised file below. Word files are automatically converted to PDF when you save. Choose <strong>Save</strong> to replace the current document or <strong>Save as new</strong> to add a new attachment.
              </p>
              <div className="flex flex-col gap-3">
                <label className="block">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-200 block mb-1">Revised file (PDF or Word; Word is converted to PDF)</span>
                  <input
                    type="file"
                    accept=".doc,.docx,.pdf"
                    onChange={(e) => setWordReplaceFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:py-2 file:px-3 file:rounded file:border file:border-[#14B8A6] file:dark:border-teal-dm file:bg-[#14B8A6]/10 file:dark:bg-teal-dm/20 file:text-[#0D9488] file:dark:text-teal-dm"
                  />
                </label>
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => handleSaveWord(false)}
                    disabled={saving || !wordReplaceFile}
                    title={saving ? 'Saving…' : 'Save (overwrite current document) — Ctrl+S'}
                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-dark-elevated hover:bg-[#0D9488] dark:hover:bg-teal-dm/90 disabled:opacity-50 transition-colors text-sm font-medium"
                  >
                    {saving ? (
                      <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    ) : (
                      <HiOutlineSave className="w-4 h-4" />
                    )}
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSaveWord(true)}
                    disabled={saving || !wordReplaceFile}
                    title={saving ? 'Saving…' : 'Save as new document (adds new attachment)'}
                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border-2 border-[#14B8A6] dark:border-teal-dm text-[#14B8A6] dark:text-teal-dm bg-transparent hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/10 disabled:opacity-50 transition-colors text-sm font-medium"
                  >
                    {saving ? (
                      <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    ) : (
                      <HiOutlineSave className="w-4 h-4" />
                    )}
                    {saving ? 'Saving…' : 'Save as new'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {!loading && !isPDF && !isWORD && doc && (
            <div className="flex-1 p-4 text-sm text-gray-500 dark:text-dark-muted">This document type cannot be edited here. Use View to open it.</div>
          )}
        </div>
      </div>

      {selectedAddedTextId && tooltipAnchor && (
        <EditorAddedItemTooltip
          item={addedTexts.find((t) => t.id === selectedAddedTextId)}
          anchor={tooltipAnchor}
          tooltipRef={addedTextTooltipRef}
          onRemove={removeAddedText}
          onUpdate={updateAddedText}
          onClose={() => {
            setSelectedAddedTextId(null);
            setTooltipAnchor(null);
          }}
        />
      )}
    </div>
  );

  return createPortal(overlay, document.body);
}
