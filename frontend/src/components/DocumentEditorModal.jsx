/**
 * In-app document editor modal: PDF (form fields) and Word (replace file).
 * Edit opens in a window; save overwrites the document in data.
 */
import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { HiOutlineX, HiOutlineSave, HiOutlineDocumentText, HiOutlineChevronLeft, HiOutlineChevronRight, HiOutlinePlus, HiOutlineTrash, HiOutlineCursorClick, HiOutlinePencil, HiOutlineClipboardList } from 'react-icons/hi';
import * as pdfjsLib from 'pdfjs-dist';
import api, { opportunitiesAPI } from '../utils/api';

// Set PDF.js worker so getDocument can run (Vite resolves worker URL)
import pdfjsWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
if (pdfjsWorkerUrl) pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

const isPdf = (doc) => {
  const t = (doc?.file_type ?? '').toString().toLowerCase();
  const name = (doc?.file_name ?? '').toLowerCase();
  return t.includes('pdf') || name.endsWith('.pdf');
};

const isWord = (doc) => {
  const t = (doc?.file_type ?? '').toString().toLowerCase();
  const name = (doc?.file_name ?? '').toLowerCase();
  return t.includes('word') || name.endsWith('.docx') || name.endsWith('.doc');
};

/** Normalize API error detail (string, array of {msg}, or object) to a string for display. */
function detailToMessage(detail) {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first.msg === 'string') return first.msg;
    return JSON.stringify(detail);
  }
  if (typeof detail === 'object' && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}

/** Return a friendly message for PDF parse/load errors so we never show raw "No PDF header found". */
function friendlyPdfErrorMessage(err) {
  const m = err?.message ?? String(err ?? '');
  if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(m)) {
    return 'The file is not a valid PDF or the server did not return document data.';
  }
  return m || 'Failed to load PDF.';
}

export default function DocumentEditorModal({ open, onClose, opportunityId, document: doc, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pdfFields, setPdfFields] = useState([]);
  const [fieldValues, setFieldValues] = useState({});
  const [apiFormFields, setApiFormFields] = useState([]); // server fields with mapping_key for prefill
  const [saveAsNewDocument, setSaveAsNewDocument] = useState(false);
  const [fillingFromOpportunity, setFillingFromOpportunity] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);
  const [pdfBytes, setPdfBytes] = useState(null);
  const [wordReplaceFile, setWordReplaceFile] = useState(null);
  const [formFieldsExpanded, setFormFieldsExpanded] = useState(true);
  const [pdfPageCount, setPdfPageCount] = useState(0);
  const [pdfPageHeightPoints, setPdfPageHeightPoints] = useState(null);
  const [pdfPageWidthPoints, setPdfPageWidthPoints] = useState(null);
  const [pdfCanvasScale, setPdfCanvasScale] = useState(null);
  const [pdfPreviewKey, setPdfPreviewKey] = useState(0);
  const [addedTexts, setAddedTexts] = useState([]);
  const pdfScrollContainerRef = useRef(null);
  const pdfPageRefs = useRef([]);
  const pdfCanvasRefs = useRef([]);
  const [newAddText, setNewAddText] = useState('');
  const [newAddPage, setNewAddPage] = useState(1);
  const [newAddSize, setNewAddSize] = useState(11);
  const [newAddBoxX, setNewAddBoxX] = useState(50);
  const [newAddBoxY, setNewAddBoxY] = useState(50);
  const [newAddColor, setNewAddColor] = useState('#000000');
  const [textAddLog, setTextAddLog] = useState([]);
  const DEFAULT_BOX_W = 200;
  const DEFAULT_BOX_H = 40;

  /** Hex #rrggbb to { r,g,b } in 0..1 for pdf-lib */
  const hexToRgb = (hex) => {
    const n = parseInt((hex || '#000000').replace(/^#/, ''), 16);
    return { r: ((n >> 16) & 0xff) / 255, g: ((n >> 8) & 0xff) / 255, b: (n & 0xff) / 255 };
  };
  const [textBoxModeActive, setTextBoxModeActive] = useState(false);
  const [mousePreview, setMousePreview] = useState({ x: null, y: null });
  const previewContainerRef = useRef(null);
  const addTextContentRef = useRef(null);

  const addLog = (message) => {
    const entry = { id: Date.now().toString(36) + Math.random().toString(36).slice(2), message, time: new Date().toLocaleTimeString() };
    setTextAddLog((prev) => [entry, ...prev].slice(0, 50));
  };

  const isPDF = doc && isPdf(doc);
  const isWORD = doc && isWord(doc);

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
    setApiFormFields([]);
    setSaveAsNewDocument(false);
    setFillingFromOpportunity(false);
    setPdfPreviewUrl(null);
    setPdfBytes(null);
    setWordReplaceFile(null);
    setFormFieldsExpanded(true);
    setAddedTexts([]);
    setTextAddLog([]);
    setMousePreview({ x: null, y: null });
    setTextBoxModeActive(false);
    setNewAddText('');
    setNewAddPage(1);
    setNewAddSize(11);
    setNewAddBoxX(50);
    setNewAddBoxY(50);
    setPdfPageCount(0);
    setLoading(true);

    if (isPDF) {
      (async () => {
        try {
          const res = await api.get(
            `/api/v1/opportunities/${oid}/documents/${docId}/view?t=${Date.now()}`,
            { responseType: 'arraybuffer' }
          );
          const buf = res.data;
          const bytes = new Uint8Array(buf);
          // Keep a copy in state so the buffer is never transferred to PDF.js worker (which detaches it)
          const bytesCopy = bytes.slice(0);
          if (bytesCopy.length === 0) {
            setError('Document is empty or the server returned no data.');
            setLoading(false);
            return;
          }
          // PDF must start with %PDF- (0x25 0x50 0x44 0x46 0x2D)
          const pdfHeader = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]);
          const isPdfBytes = bytesCopy.length >= 5 && pdfHeader.every((b, i) => bytesCopy[i] === b);
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
                msg = 'Document file is missing or not a valid PDF.';
              }
            }
            setError(msg);
            setLoading(false);
            return;
          }
          setPdfBytes(bytesCopy);
          let pdfDoc;
          try {
            pdfDoc = await PDFDocument.load(bytesCopy);
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
          setPdfPageCount(pdfDoc.getPageCount());
          const firstPage = pdfDoc.getPage(0);
          const { width: w, height: h } = firstPage.getSize();
          setPdfPageWidthPoints(w);
          setPdfPageHeightPoints(h);
          const blob = new Blob([bytesCopy], { type: 'application/pdf' });
          setPdfPreviewUrl(URL.createObjectURL(blob));
          setLoading(false);
          // Defer server form-fields so editor shows fast; "Fill from opportunity" will use when ready or fetch on click
          opportunitiesAPI.getFormFields(oid, docId).then((ffRes) => {
            if (ffRes?.data?.fields) setApiFormFields(ffRes.data.fields);
          }).catch(() => {});
        } catch (e) {
          const detail = e?.response?.data;
          let msg = 'Failed to load document.';
          if (e?.response?.status === 404) {
            try {
              const text = detail instanceof ArrayBuffer ? new TextDecoder().decode(detail) : (typeof detail === 'string' ? detail : null);
              const parsed = text ? JSON.parse(text) : null;
              if (parsed?.detail != null) msg = detailToMessage(parsed.detail);
            } catch (_) {
              if (typeof detail === 'string') msg = detail;
            }
          } else if (e?.response?.data?.detail != null) {
            msg = detailToMessage(e.response.data.detail);
          } else if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(e?.message ?? '')) {
            msg = friendlyPdfErrorMessage(e);
            if (detail) {
              try {
                const ab = detail instanceof ArrayBuffer ? detail : detail?.buffer;
                const text = ab ? new TextDecoder().decode(new Uint8Array(ab).slice(0, 500)) : null;
                if (text) {
                  const parsed = JSON.parse(text);
                  if (parsed?.detail) msg = detailToMessage(parsed.detail);
                }
              } catch (_) {}
            }
          } else if (e?.message) {
            msg = e.message;
          }
          setError(msg);
        } finally {
          setLoading(false);
        }
      })();
    } else if (isWORD) {
      setLoading(false);
    } else {
      setError('Only PDF and Word documents can be edited here.');
      setLoading(false);
    }

    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
    };
  }, [open, opportunityId, doc?.id, isPDF, isWORD]);

  // ResizeObserver: compute scale for canvas preview from container width
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

  // Render PDF pages to canvases when we have bytes and scale
  useEffect(() => {
    if (!pdfBytes?.length || pdfPageCount < 1 || !pdfCanvasScale || pdfCanvasScale <= 0) return;
    const pdfHeader = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]);
    const isPdf = pdfBytes.length >= 5 && pdfHeader.every((b, i) => pdfBytes[i] === b);
    if (!isPdf) return;
    const container = pdfScrollContainerRef.current;
    if (!container) return;
    const scale = Math.min(pdfCanvasScale, 2);
    let cancelled = false;
    // Pass a copy so PDF.js worker can transfer/detach it without affecting our state (used for save)
    pdfjsLib.getDocument({ data: pdfBytes.slice(0) }).promise.then((pdf) => {
      if (cancelled) return;
      const renderPage = (i) => {
        if (cancelled) return;
        pdf.getPage(i + 1).then((page) => {
          if (cancelled) return;
          const viewport = page.getViewport({ scale });
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
            page.render({ canvasContext: ctx, viewport });
          }
        }).catch(() => {});
      };
      for (let i = 0; i < pdf.numPages; i++) renderPage(i);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [pdfBytes, pdfPageCount, pdfCanvasScale]);

  // IntersectionObserver: update "Page" selector when user scrolls
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
  }, [pdfPageCount, pdfCanvasScale]);

  // Keyboard: Shift+Enter or Ctrl+Enter = add text box, Ctrl+S = save
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        if (loading || saving) return;
        if (isPDF && doc && (pdfBytes || saveAsNewDocument)) handleSavePdf();
        else if (isWORD && wordReplaceFile) handleSaveWord();
        return;
      }
      if ((e.shiftKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!loading && isPDF && newAddText.trim()) {
          const scrollEl = pdfScrollContainerRef.current;
          const wrapper = scrollEl?.querySelector(`[data-pdf-page="${newAddPage}"]`);
          const rect = wrapper?.getBoundingClientRect();
          addTextBoxToPdf(newAddText, newAddPage, newAddSize, {
            x: newAddBoxX,
            y: newAddBoxY,
            width: DEFAULT_BOX_W,
            height: DEFAULT_BOX_H,
            previewW: rect?.width ?? 0,
            previewH: rect?.height ?? 0,
          }, true, newAddColor);
          setNewAddText('');
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, loading, isPDF, isWORD, pdfBytes, doc, saving, wordReplaceFile, newAddText, newAddPage, newAddSize, newAddBoxX, newAddBoxY, newAddColor, saveAsNewDocument]);

  const addTextBoxToPdf = (text, pageNum, size, box, drawBorder, color) => {
    if (!text.trim() || pageNum < 1) return;
    const short = text.trim().length > 30 ? text.trim().slice(0, 30) + '…' : text.trim();
    setAddedTexts((prev) => [
      ...prev,
      { id: Date.now().toString(36) + Math.random().toString(36).slice(2), type: 'box', text: text.trim(), pageNum, size: size || 11, box: { ...box }, drawBorder: !!drawBorder, color: color || '#000000' },
    ]);
    addLog(`Added text box "${short}" to page ${pageNum}`);
  };

  const removeAddedText = (id) => {
    const item = addedTexts.find((t) => t.id === id);
    const short = item?.text?.length > 30 ? item.text.slice(0, 30) + '…' : item?.text ?? 'item';
    setAddedTexts((prev) => prev.filter((t) => t.id !== id));
    addLog(`Removed "${short}" from list`);
  };

  const wrapTextLines = (font, text, size, maxWidth) => {
    const lines = [];
    const paragraphs = text.split(/\n/);
    for (const para of paragraphs) {
      const words = para.trim() ? para.split(/\s+/) : [];
      let current = '';
      for (const word of words) {
        const candidate = current ? current + ' ' + word : word;
        if (font.widthOfTextAtSize(candidate, size) <= maxWidth) {
          current = candidate;
        } else {
          if (current) lines.push(current);
          current = word;
          while (font.widthOfTextAtSize(current, size) > maxWidth) {
            let fit = '';
            for (const ch of current) {
              if (font.widthOfTextAtSize(fit + ch, size) <= maxWidth) fit += ch;
              else break;
            }
            if (fit) {
              lines.push(fit);
              current = current.slice(fit.length);
            } else {
              lines.push(current);
              current = '';
              break;
            }
          }
        }
      }
      if (current) lines.push(current);
    }
    return lines;
  };

  const handleSavePdf = async () => {
    if (!doc || saving) return;
    setSaving(true);
    setError('');
    try {
      if (saveAsNewDocument) {
        await opportunitiesAPI.fillForm(opportunityId, doc.id, {
          fields: fieldValues,
          use_opportunity_data: false,
          save_as_new: true,
        });
        addLog('Saved as new document (form fields only)');
        onSaved?.();
        onClose?.();
        return;
      }
      if (!pdfBytes) return;
      const bytesToSave = pdfBytes;
      const pdfHeader = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]);
      const hasPdfHeader = bytesToSave.length >= 5 && pdfHeader.every((b, i) => bytesToSave[i] === b);
      if (!hasPdfHeader) {
        setError('The file is not a valid PDF or the server did not return document data.');
        return;
      }
      const pdfDoc = await PDFDocument.load(bytesToSave);
      const form = pdfDoc.getForm();
      const fields = form.getFields();
      for (const f of fields) {
        const name = f.getName();
        const v = fieldValues[name];
        if (v === undefined) continue;
        try {
          if (f.constructor.name === 'PDFTextField') f.setText(String(v ?? ''));
          else if (f.constructor.name === 'PDFCheckBox') f.setChecked(Boolean(v));
        } catch (_) {}
      }
      const pages = pdfDoc.getPages();
      const margin = 50;
      if (addedTexts.length > 0) {
        const font = await pdfDoc.embedStandardFont(StandardFonts.Helvetica);
        for (const item of addedTexts) {
          const pageIndex = Math.min(Math.max(0, item.pageNum - 1), pages.length - 1);
          const page = pages[pageIndex];
          const { width: pageWidth, height: pageHeight } = page.getSize();
          const size = Math.max(6, Math.min(72, Number(item.size) || 11));
          const lineHeight = size * 1.2;

          if (item.type === 'box' && item.box) {
            const { x: px, y: pyTop, width: pw, height: ph, previewW, previewH } = item.box;
            let bx, by, bw, bh;
            if (previewW > 0 && previewH > 0) {
              const scaleX = pageWidth / previewW;
              const scaleY = pageHeight / previewH;
              bx = Number(px) * scaleX;
              const pdfYFromTop = Number(pyTop) * scaleY;
              bw = Number(pw) * scaleX;
              bh = Number(ph) * scaleY;
              by = pageHeight - pdfYFromTop - bh;
            } else {
              bx = Number(px);
              bw = Number(pw);
              bh = Number(ph);
              by = pageHeight - Number(pyTop) - bh;
            }
            const textColor = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : undefined;
            const lines = wrapTextLines(font, item.text, size, Math.max(20, bw - 8));
            let lineY = by + bh - size;
            for (const line of lines) {
              if (lineY < by + 4) break;
              page.drawText(line, { font, size, x: bx + 4, y: lineY, color: textColor });
              lineY -= lineHeight;
            }
          } else {
            const textWidth = font.widthOfTextAtSize(item.text, size);
            let x = margin;
            let y = pageHeight - margin;
            if (item.position?.includes('bottom')) y = margin;
            if (item.position?.includes('center')) x = (pageWidth - textWidth) / 2;
            else if (item.position?.includes('right')) x = pageWidth - margin - textWidth;
            page.drawText(item.text, { font, size, x, y });
          }
        }
      }
      const saved = await pdfDoc.save();
      const baseName = doc.original_file_name || doc.file_name || 'document';
      const filename = baseName.toLowerCase().endsWith('.pdf') ? baseName : `${baseName.replace(/\.pdf$/i, '')}.pdf`;
      const file = new File([saved], filename, { type: 'application/pdf' });
      await opportunitiesAPI.overwriteDocument(opportunityId, doc.id, file, filename);
      addLog(`Saved document with ${addedTexts.length} text item(s)`);
      onSaved?.();
      // Reload PDF in modal so preview shows saved content without closing or full page reload
      try {
        const res = await api.get(
          `/api/v1/opportunities/${opportunityId}/documents/${doc.id}/view?t=${Date.now()}`,
          { responseType: 'arraybuffer' }
        );
        const buf = res.data;
        const bytes = new Uint8Array(buf);
        if (bytes.length >= 5 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46 && bytes[4] === 0x2d) {
          const copy = bytes.slice(0);
          setPdfBytes(copy);
          if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
          setPdfPreviewUrl(URL.createObjectURL(new Blob([copy], { type: 'application/pdf' })));
          setPdfPreviewKey((k) => k + 1);
          setAddedTexts([]);
        }
      } catch (_) {}
      // Modal stays open; only the PDF inside reloads to show saved data
    } catch (e) {
      const apiMsg = detailToMessage(e?.response?.data?.detail);
      if (apiMsg) {
        setError(apiMsg);
      } else if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(e?.message ?? '')) {
        setError('Document data was lost or invalid. Close this editor, reopen the document, then try saving again.');
      } else {
        setError(e?.message || 'Failed to save');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSaveWord = async () => {
    if (!wordReplaceFile || !doc || saving) return;
    setSaving(true);
    setError('');
    try {
      await opportunitiesAPI.overwriteDocument(
        opportunityId,
        doc.id,
        wordReplaceFile,
        wordReplaceFile.name
      );
      onSaved?.();
      onClose?.();
    } catch (e) {
      setError(detailToMessage(e?.response?.data?.detail) || e?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const overlay = (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/50" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-[95vw] sm:max-w-7xl h-[90vh] sm:h-[95vh] max-h-[95vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-600">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <HiOutlineDocumentText className="w-5 h-5 text-[#14B8A6] dark:text-teal-dm" />
            Edit document {doc?.file_name && `— ${doc.file_name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-600 hover:text-gray-700 dark:hover:text-gray-200"
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

          {loading && (
            <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">Loading document…</div>
          )}

          {!loading && isPDF && (
            <div className="flex-1 flex min-h-0">
              <div className="flex-1 min-w-0 flex flex-col border-r border-gray-200 dark:border-gray-600">
                <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 border-b border-gray-100 dark:border-gray-600 flex items-center justify-between gap-2 flex-wrap">
                  <span>{textBoxModeActive ? 'Click on preview to place text box' : 'Preview — scroll to view PDF'}</span>
                  {textBoxModeActive && mousePreview.x != null && mousePreview.y != null && (
                    <span className="font-mono text-[10px] bg-gray-100 dark:bg-gray-600 px-1.5 py-0.5 rounded tabular-nums">
                      X: {Math.round(mousePreview.x)} Y: {Math.round(mousePreview.y)}
                    </span>
                  )}
                </div>
                <div
                  ref={previewContainerRef}
                  className={`flex-1 min-h-0 p-2 relative ${textBoxModeActive ? 'cursor-crosshair' : ''}`}
                >
                  {pdfPreviewUrl && (
                    <div
                      key={pdfPreviewKey}
                      ref={pdfScrollContainerRef}
                      className="w-full h-full min-h-[50vh] overflow-auto rounded border border-gray-200 dark:border-gray-600 flex flex-col items-center gap-2 p-2"
                      onMouseMove={textBoxModeActive ? (e) => {
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
                      } : undefined}
                      onMouseLeave={textBoxModeActive ? () => setMousePreview({ x: null, y: null }) : undefined}
                      onClick={textBoxModeActive ? (e) => {
                        const scrollEl = pdfScrollContainerRef.current;
                        if (!scrollEl) return;
                        const wrappers = scrollEl.querySelectorAll('[data-pdf-page]');
                        for (const w of wrappers) {
                          const r = w.getBoundingClientRect();
                          if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
                            const page = parseInt(w.getAttribute('data-pdf-page'), 10);
                            const x = e.clientX - r.left;
                            const y = e.clientY - r.top;
                            setNewAddPage(page);
                            setNewAddBoxX(Math.round(x));
                            setNewAddBoxY(Math.round(y));
                            addLog(`Text box placed on page ${page} at X=${Math.round(x)}, Y=${Math.round(y)}`);
                            setTimeout(() => addTextContentRef.current?.focus(), 0);
                            return;
                          }
                        }
                      } : undefined}
                    >
                      {Array.from({ length: Math.max(0, pdfPageCount) }, (_, i) => (
                        <div key={i} data-pdf-page={i + 1} className="shadow-sm bg-white dark:bg-gray-800 relative">
                          <canvas className="block" />
                          {addedTexts
                            .filter((t) => t.pageNum === i + 1)
                            .map((t) => (
                              <div
                                key={t.id}
                                className="absolute pointer-events-none rounded-xl px-1.5 py-1 min-w-[80px] min-h-[1em] bg-transparent overflow-visible"
                                style={{
                                  left: t.box?.x ?? 0,
                                  top: t.box?.y ?? 0,
                                  fontSize: Math.max(10, Math.min(24, t.size ?? 11)),
                                  color: t.color || '#000000',
                                }}
                              >
                                <span className="whitespace-pre-wrap break-words block">{t.text}</span>
                              </div>
                            ))}
                          {textBoxModeActive && newAddPage === i + 1 && (
                            <div
                              className="absolute pointer-events-none rounded-xl px-1.5 py-1 min-w-[200px] min-h-[40px] border-[3px] border-dashed border-gray-600 dark:border-gray-300 bg-transparent overflow-visible"
                              style={{
                                left: newAddBoxX,
                                top: newAddBoxY,
                                fontSize: Math.max(10, Math.min(24, newAddSize)),
                                color: newAddColor,
                              }}
                            >
                              <span className="whitespace-pre-wrap break-words block">
                                {newAddText.trim() || <span className="text-gray-400 dark:text-gray-500 italic">Type in the box to the right →</span>}
                              </span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div
                className={`flex flex-col bg-gray-50 dark:bg-gray-700 overflow-hidden shrink-0 border-l border-gray-200 dark:border-gray-600 transition-[width] duration-200 ease-out ${formFieldsExpanded ? 'w-80 sm:w-96' : 'w-12'}`}
              >
                <button
                  type="button"
                  onClick={() => setFormFieldsExpanded((e) => !e)}
                  className={`flex items-center border-b border-gray-200 dark:border-gray-600 hover:bg-gray-100/80 dark:hover:bg-gray-600 transition-colors ${formFieldsExpanded ? 'justify-between w-full px-3 py-2' : 'flex-col justify-start gap-2 w-full py-4 px-1'}`}
                  aria-expanded={formFieldsExpanded}
                  title={formFieldsExpanded ? 'Collapse form fields' : 'Expand form fields'}
                >
                  <span
                    className="text-sm font-medium text-gray-700 dark:text-gray-200 select-none"
                    style={!formFieldsExpanded ? { writingMode: 'vertical-rl', textOrientation: 'mixed', transform: 'rotate(-180deg)' } : undefined}
                  >
                    Form fields
                  </span>
                  {formFieldsExpanded ? (
                    <HiOutlineChevronRight className="w-4 h-4 text-gray-500 dark:text-gray-400 shrink-0" aria-hidden />
                  ) : (
                    <HiOutlineChevronLeft className="w-4 h-4 text-gray-500 dark:text-gray-400 shrink-0" aria-hidden />
                  )}
                </button>
                {formFieldsExpanded && (
                  <React.Fragment>
                    <div className="flex flex-col flex-1 min-h-0">
                    <div className="p-3 space-y-4 overflow-auto flex-1 min-h-0">
                      {pdfFields.length === 0 ? (
                        <div className="rounded-xl border border-gray-200 dark:border-gray-600 bg-white/60 dark:bg-gray-600/40 p-4 text-center">
                          <HiOutlineDocumentText className="w-10 h-10 mx-auto text-gray-400 dark:text-gray-500 mb-2" />
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">No fillable form fields</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">This PDF has no fillable fields. You can add text boxes below or replace the file from the opportunity attachments.</p>
                        </div>
                      ) : (
                        <>
                        <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/80 dark:bg-emerald-900/20 p-3 space-y-2">
                          <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Fill from opportunity</p>
                          <button
                            type="button"
                            onClick={async () => {
                              if (!opportunityId || !doc?.id || fillingFromOpportunity) return;
                              setFillingFromOpportunity(true);
                              setError('');
                              try {
                                const [formDataRes, _fieldsRes] = await Promise.all([
                                  opportunitiesAPI.getFormData(opportunityId),
                                  apiFormFields.length ? Promise.resolve(null) : opportunitiesAPI.getFormFields(opportunityId, doc.id),
                                ]);
                                const formData = formDataRes?.data ?? {};
                                let fields = apiFormFields;
                                if (!fields.length && _fieldsRes?.data?.fields) {
                                  fields = _fieldsRes.data.fields;
                                  setApiFormFields(fields);
                                }
                                setFieldValues((prev) => {
                                  const next = { ...prev };
                                  for (const { name } of pdfFields) {
                                    const apiField = fields.find((f) => f.name === name);
                                    const dataKey = apiField?.mapping_key ?? name;
                                    if (formData[dataKey] != null) next[name] = String(formData[dataKey]);
                                    else if (formData[name] != null) next[name] = String(formData[name]);
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
                            disabled={fillingFromOpportunity}
                            title="Pre-fill form fields with this opportunity's data (live update)"
                            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border-2 border-emerald-500 dark:border-emerald-400 bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-200 hover:bg-emerald-500/20 dark:hover:bg-emerald-500/30 disabled:opacity-50 text-sm font-medium transition-colors"
                          >
                            <HiOutlineClipboardList className="w-4 h-4 shrink-0" />
                            {fillingFromOpportunity ? 'Loading…' : 'Fill from opportunity'}
                          </button>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-600 bg-white/60 dark:bg-gray-600/40 p-3">
                          <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2">Form values</p>
                          <div className="text-xs text-gray-700 dark:text-gray-300 space-y-1.5 max-h-24 overflow-y-auto">
                            {pdfFields.map(({ name, type }) => {
                              const v = fieldValues[name];
                              const disp = type === 'checkbox' ? (v ? 'Yes' : 'No') : (v ?? '');
                              return (
                                <div key={name} className="truncate" title={name}>
                                  <span className="text-gray-500 dark:text-gray-400">{name}:</span>{' '}
                                  <span className="font-medium">{disp || '—'}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                        {pdfFields.map(({ name, type }) => (
                          <label key={name} className="block">
                            <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block truncate mb-0.5" title={name}>{name}</span>
                            {type === 'checkbox' ? (
                              <input
                                type="checkbox"
                                checked={Boolean(fieldValues[name])}
                                onChange={(e) => setFieldValues((prev) => ({ ...prev, [name]: e.target.checked }))}
                                className="h-4 w-4 rounded border-gray-300 dark:border-gray-500 text-[#14B8A6] dark:text-teal-dm focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm bg-white dark:bg-gray-600"
                              />
                            ) : (
                              <input
                                type="text"
                                value={fieldValues[name] ?? ''}
                                onChange={(e) => setFieldValues((prev) => ({ ...prev, [name]: e.target.value }))}
                                className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-[#14B8A6] dark:focus:border-teal-dm bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100"
                              />
                            )}
                          </label>
                        ))}
                        </>
                      )}

                      <div className="rounded-xl border border-[#14B8A6]/30 dark:border-teal-dm/30 bg-[#14B8A6]/5 dark:bg-teal-dm/5 p-3.5 space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <HiOutlinePencil className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Add text box</h3>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setTextBoxModeActive((v) => {
                                const next = !v;
                                if (next) setTimeout(() => addTextContentRef.current?.focus(), 0);
                                return next;
                              });
                            }}
                            title={textBoxModeActive ? 'Exit text box mode (scroll PDF)' : 'Add text box (click on PDF to place)'}
                            className={`p-1.5 rounded border transition-colors ${textBoxModeActive ? 'bg-[#14B8A6]/20 dark:bg-teal-dm/20 border-[#14B8A6] dark:border-teal-dm text-[#0D9488] dark:text-teal-dm' : 'border-gray-300 dark:border-gray-500 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-600'}`}
                          >
                            <HiOutlineCursorClick className="w-4 h-4" />
                          </button>
                        </div>

                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <label className="text-xs font-bold italic text-gray-600 dark:text-gray-400 shrink-0">Page</label>
                            <select
                              value={newAddPage}
                              onChange={(e) => setNewAddPage(Number(e.target.value))}
                              className="w-14 px-1.5 py-1 text-xs border border-gray-300 dark:border-gray-500 rounded focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100"
                            >
                              {Array.from({ length: Math.max(1, pdfPageCount) }, (_, i) => (
                                <option key={i} value={i + 1}>{i + 1}</option>
                              ))}
                            </select>
                            <label className="text-xs font-bold italic text-gray-600 dark:text-gray-400 shrink-0 ml-2">Color</label>
                            <input
                              type="color"
                              value={newAddColor}
                              onChange={(e) => setNewAddColor(e.target.value)}
                              className="h-6 w-8 cursor-pointer rounded border border-gray-300 dark:border-gray-500 bg-white dark:bg-gray-600 overflow-hidden"
                            />
                            <input
                              type="text"
                              value={newAddColor}
                              onChange={(e) => setNewAddColor(e.target.value)}
                              className="w-16 px-1.5 py-0.5 text-xs border border-gray-300 dark:border-gray-500 rounded focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 font-mono"
                            />
                          </div>
                          <span className="text-[10px] text-gray-500 dark:text-gray-500 block">Updates as you scroll</span>
                        </div>

                        <div>
                          <label className="text-xs font-bold italic text-gray-600 dark:text-gray-400 block mb-1">Size</label>
                          <input
                            type="number"
                            min={6}
                            max={72}
                            value={newAddSize}
                            onChange={(e) => setNewAddSize(Number(e.target.value) || 11)}
                            className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100"
                          />
                        </div>

                        <p className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-400 bg-white/50 dark:bg-gray-600/30 rounded-lg px-2 py-1.5">
                          <HiOutlineCursorClick className="w-3.5 h-3.5 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                          <span>Click on the PDF preview to place the text box, then type below.</span>
                        </p>

                        <div>
                          <label className="text-xs font-bold italic text-gray-600 dark:text-gray-400 block mb-1">Content</label>
                          <textarea
                            ref={addTextContentRef}
                            value={newAddText}
                            onChange={(e) => setNewAddText(e.target.value)}
                            placeholder="Enter the text to add to the PDF…"
                            rows={3}
                            className="w-full px-2.5 py-2 text-sm border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-[#14B8A6] dark:focus:border-teal-dm resize-y bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                          />
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              const scrollEl = pdfScrollContainerRef.current;
                              const wrapper = scrollEl?.querySelector(`[data-pdf-page="${newAddPage}"]`);
                              const rect = wrapper?.getBoundingClientRect();
                              addTextBoxToPdf(newAddText, newAddPage, newAddSize, {
                                x: newAddBoxX,
                                y: newAddBoxY,
                                width: DEFAULT_BOX_W,
                                height: DEFAULT_BOX_H,
                                previewW: rect?.width ?? 0,
                                previewH: rect?.height ?? 0,
                              }, true, newAddColor);
                              setNewAddText('');
                              setTimeout(() => addTextContentRef.current?.focus(), 0);
                            }}
                            disabled={!newAddText.trim()}
                            title={`Add to page ${newAddPage} (Shift+Enter)`}
                            className="inline-flex items-center justify-center p-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white hover:bg-[#0d9488] dark:hover:bg-teal-dm/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            <HiOutlinePlus className="w-4 h-4" />
                          </button>
                          <span className="text-[10px] text-gray-500 dark:text-gray-400">Add to page {newAddPage}</span>
                        </div>

                        {addedTexts.length > 0 && (
                          <div className="pt-2 border-t border-gray-200 dark:border-gray-600">
                            <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">Added text boxes</p>
                            <ul className="space-y-1.5">
                              {addedTexts.map((t) => (
                                <li
                                  key={t.id}
                                  className="flex items-center gap-2 text-xs bg-white dark:bg-gray-600 border border-gray-200 dark:border-gray-500 rounded-lg px-2.5 py-2 text-gray-900 dark:text-gray-100"
                                >
                                  <span className="flex-1 truncate" title={t.text}>"{t.text}"</span>
                                  <span className="shrink-0 text-gray-500 dark:text-gray-400">p{t.pageNum}</span>
                                  <button
                                    type="button"
                                    onClick={() => removeAddedText(t.id)}
                                    className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                    aria-label="Remove"
                                  >
                                    <HiOutlineTrash className="w-3.5 h-3.5" />
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                        {textAddLog.length > 0 && (
                          <div className="border-t border-gray-200 dark:border-gray-600 pt-3 mt-3">
                            <p className="text-xs font-medium text-gray-700 dark:text-gray-200 mb-1.5">Activity log</p>
                            <ul className="max-h-28 overflow-y-auto space-y-1 text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-600 rounded px-2 py-1.5 border border-gray-100 dark:border-gray-500">
                              {textAddLog.map((entry) => (
                                <li key={entry.id} className="flex gap-2">
                                  <span className="text-gray-400 dark:text-gray-500 shrink-0">{entry.time}</span>
                                  <span>{entry.message}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="p-3 border-t border-gray-200 dark:border-gray-600 shrink-0 flex items-center justify-between gap-2 flex-wrap">
                      <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={saveAsNewDocument}
                          onChange={(e) => setSaveAsNewDocument(e.target.checked)}
                          className="h-4 w-4 rounded border-gray-300 dark:border-gray-500 text-[#14B8A6] dark:text-teal-dm focus:ring-[#14B8A6] dark:focus:ring-teal-dm"
                        />
                        <span>Save as new document</span>
                      </label>
                      {(pdfFields.length > 0 || addedTexts.length > 0 || saveAsNewDocument) && (
                        <button
                          type="button"
                          onClick={handleSavePdf}
                          disabled={saving}
                          title={saving ? 'Saving…' : saveAsNewDocument ? 'Save form fields as new attachment' : 'Save (overwrite document) — Ctrl+S'}
                          className="inline-flex items-center justify-center p-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-gray-900 hover:bg-[#0D9488] dark:hover:bg-teal-600 disabled:opacity-50 transition-colors"
                        >
                          <HiOutlineSave className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </React.Fragment>
                )}
              </div>
            </div>
          )}

          {!loading && isWORD && (
            <div className="flex-1 p-4">
              <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
                Edit the Word document in your preferred editor, then upload the revised file below. It will replace the
                current document.
              </p>
              <div className="flex flex-col gap-3">
                <label className="block">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-200 block mb-1">Revised file (PDF or Word)</span>
                  <input
                    type="file"
                    accept=".doc,.docx,.pdf"
                    onChange={(e) => setWordReplaceFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:py-2 file:px-3 file:rounded file:border file:border-[#14B8A6] file:dark:border-teal-dm file:bg-[#14B8A6]/10 file:dark:bg-teal-dm/20 file:text-[#0D9488] file:dark:text-teal-dm"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleSaveWord}
                  disabled={saving || !wordReplaceFile}
                  title={saving ? 'Saving…' : 'Save (overwrite document) — Ctrl+S'}
                  className="inline-flex items-center justify-center p-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-gray-900 hover:bg-[#0D9488] dark:hover:bg-teal-600 disabled:opacity-50 transition-colors"
                >
                  <HiOutlineSave className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {!loading && !isPDF && !isWORD && doc && (
            <div className="flex-1 p-4 text-sm text-gray-500 dark:text-gray-400">
              This document type cannot be edited here. Use View to open it.
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
