/**
 * In-app document editor modal: PDF (form fields) and Word (replace file).
 * Edit opens in a window; save overwrites the document in data.
 */
import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { PDFDocument, StandardFonts } from 'pdf-lib';
import { HiOutlineX, HiOutlineSave, HiOutlineDocumentText, HiOutlineChevronLeft, HiOutlineChevronRight, HiOutlinePlus, HiOutlineTrash } from 'react-icons/hi';
import api, { opportunitiesAPI } from '../utils/api';

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

export default function DocumentEditorModal({ open, onClose, opportunityId, document: doc, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pdfFields, setPdfFields] = useState([]);
  const [fieldValues, setFieldValues] = useState({});
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);
  const [pdfBytes, setPdfBytes] = useState(null);
  const [wordReplaceFile, setWordReplaceFile] = useState(null);
  const [formFieldsExpanded, setFormFieldsExpanded] = useState(true);
  const [pdfPageCount, setPdfPageCount] = useState(0);
  const [addedTexts, setAddedTexts] = useState([]);
  const [newAddText, setNewAddText] = useState('');
  const [newAddPage, setNewAddPage] = useState(1);
  const [newAddPosition, setNewAddPosition] = useState('top-left');
  const [newAddSize, setNewAddSize] = useState(11);
  const iframeRef = useRef(null);

  const POSITIONS = [
    { value: 'top-left', label: 'Top left' },
    { value: 'top-center', label: 'Top center' },
    { value: 'top-right', label: 'Top right' },
    { value: 'bottom-left', label: 'Bottom left' },
    { value: 'bottom-center', label: 'Bottom center' },
    { value: 'bottom-right', label: 'Bottom right' },
  ];

  const isPDF = doc && isPdf(doc);
  const isWORD = doc && isWord(doc);

  useEffect(() => {
    if (!open || !doc || !opportunityId) return;
    setError('');
    setPdfFields([]);
    setFieldValues({});
    setPdfPreviewUrl(null);
    setPdfBytes(null);
    setWordReplaceFile(null);
    setFormFieldsExpanded(true);
    setAddedTexts([]);
    setNewAddText('');
    setNewAddPage(1);
    setNewAddPosition('top-left');
    setNewAddSize(11);
    setPdfPageCount(0);
    setLoading(true);

    if (isPDF) {
      (async () => {
        try {
          const res = await api.get(
            `/api/v1/opportunities/${opportunityId}/documents/${doc.id}/view`,
            { responseType: 'arraybuffer' }
          );
          const buf = res.data;
          const bytes = new Uint8Array(buf);
          setPdfBytes(bytes);
          const pdfDoc = await PDFDocument.load(bytes);
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
          const blob = new Blob([bytes], { type: 'application/pdf' });
          setPdfPreviewUrl(URL.createObjectURL(blob));
        } catch (e) {
          const detail = e?.response?.data;
          let msg = 'Failed to load document.';
          if (e?.response?.status === 404) {
            try {
              const text = detail instanceof ArrayBuffer ? new TextDecoder().decode(detail) : (typeof detail === 'string' ? detail : null);
              const parsed = text ? JSON.parse(text) : null;
              if (parsed?.detail) msg = parsed.detail;
            } catch (_) {
              if (typeof detail === 'string') msg = detail;
            }
          } else if (e?.response?.data?.detail) {
            msg = typeof e.response.data.detail === 'string' ? e.response.data.detail : JSON.stringify(e.response.data.detail);
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

  const addTextToPdf = (text, pageNum, position, size) => {
    if (!text.trim() || pageNum < 1) return;
    setAddedTexts((prev) => [
      ...prev,
      { id: Date.now().toString(36) + Math.random().toString(36).slice(2), text: text.trim(), pageNum, position, size: size || 11 },
    ]);
  };

  const removeAddedText = (id) => setAddedTexts((prev) => prev.filter((t) => t.id !== id));

  const handleSavePdf = async () => {
    if (!pdfBytes || !doc || saving) return;
    setSaving(true);
    setError('');
    try {
      const pdfDoc = await PDFDocument.load(pdfBytes);
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
          const { width, height } = page.getSize();
          const size = Math.max(6, Math.min(72, Number(item.size) || 11));
          const textWidth = font.widthOfTextAtSize(item.text, size);
          let x = margin;
          let y = height - margin;
          if (item.position.includes('bottom')) y = margin;
          if (item.position.includes('center')) x = (width - textWidth) / 2;
          else if (item.position.includes('right')) x = width - margin - textWidth;
          page.drawText(item.text, { font, size, x, y });
        }
      }
      const saved = await pdfDoc.save();
      const blob = new Blob([saved], { type: 'application/pdf' });
      const filename = doc.original_file_name || doc.file_name || 'document.pdf';
      await opportunitiesAPI.overwriteDocument(opportunityId, doc.id, blob, filename);
      onSaved?.();
      onClose?.();
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to save');
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
      setError(e?.response?.data?.detail || e?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const overlay = (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-[95vw] sm:max-w-7xl h-[90vh] sm:h-[95vh] max-h-[95vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <HiOutlineDocumentText className="w-5 h-5 text-[#14B8A6]" />
            Edit document {doc?.file_name && `— ${doc.file_name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Close"
          >
            <HiOutlineX className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          {error && (
            <div className="mx-4 mt-2 px-3 py-2 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200">
              {error}
            </div>
          )}

          {loading && (
            <div className="flex-1 flex items-center justify-center text-gray-500">Loading document…</div>
          )}

          {!loading && isPDF && (
            <div className="flex-1 flex min-h-0">
              <div className="flex-1 min-w-0 flex flex-col border-r border-gray-200">
                <div className="text-xs text-gray-500 px-2 py-1 border-b border-gray-100">Preview</div>
                <div className="flex-1 min-h-0 p-2">
                  {pdfPreviewUrl && (
                    <iframe
                      ref={iframeRef}
                      src={pdfPreviewUrl}
                      title="PDF preview"
                      className="w-full h-full min-h-[50vh] rounded border border-gray-200"
                    />
                  )}
                </div>
              </div>
              <div
                className={`flex flex-col bg-gray-50 overflow-hidden shrink-0 border-l border-gray-200 transition-[width] duration-200 ease-out ${formFieldsExpanded ? 'w-80 sm:w-96' : 'w-12'}`}
              >
                <button
                  type="button"
                  onClick={() => setFormFieldsExpanded((e) => !e)}
                  className={`flex items-center border-b border-gray-200 hover:bg-gray-100/80 transition-colors ${formFieldsExpanded ? 'justify-between w-full px-3 py-2' : 'flex-col justify-start gap-2 w-full py-4 px-1'}`}
                  aria-expanded={formFieldsExpanded}
                  title={formFieldsExpanded ? 'Collapse form fields' : 'Expand form fields'}
                >
                  <span
                    className="text-sm font-medium text-gray-700 select-none"
                    style={!formFieldsExpanded ? { writingMode: 'vertical-rl', textOrientation: 'mixed', transform: 'rotate(-180deg)' } : undefined}
                  >
                    Form fields
                  </span>
                  {formFieldsExpanded ? (
                    <HiOutlineChevronRight className="w-4 h-4 text-gray-500 shrink-0" aria-hidden />
                  ) : (
                    <HiOutlineChevronLeft className="w-4 h-4 text-gray-500 shrink-0" aria-hidden />
                  )}
                </button>
                {formFieldsExpanded && (
                  <>
                    <div className="p-3 space-y-2 overflow-auto flex-1 min-h-0">
                      {pdfFields.length === 0 ? (
                        <p className="text-sm text-gray-500">
                          No fillable form fields in this PDF. You can replace the file from the opportunity attachments.
                        </p>
                      ) : (
                        pdfFields.map(({ name, type }) => (
                          <label key={name} className="block">
                            <span className="text-xs text-gray-600 block truncate" title={name}>
                              {name}
                            </span>
                            {type === 'checkbox' ? (
                              <input
                                type="checkbox"
                                checked={Boolean(fieldValues[name])}
                                onChange={(e) => setFieldValues((prev) => ({ ...prev, [name]: e.target.checked }))}
                                className="mt-1 h-4 w-4 rounded border-gray-300 text-[#14B8A6] focus:ring-[#14B8A6]"
                              />
                            ) : (
                              <input
                                type="text"
                                value={fieldValues[name] ?? ''}
                                onChange={(e) => setFieldValues((prev) => ({ ...prev, [name]: e.target.value }))}
                                className="mt-0.5 w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6]"
                              />
                            )}
                          </label>
                        ))
                      )}

                      <div className="border-t border-gray-200 pt-3 mt-3">
                        <p className="text-xs font-medium text-gray-700 mb-2">Add text to page</p>
                        <textarea
                          value={newAddText}
                          onChange={(e) => setNewAddText(e.target.value)}
                          placeholder="Text to add…"
                          rows={2}
                          className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] resize-y"
                        />
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <label className="block">
                            <span className="text-xs text-gray-600">Page</span>
                            <select
                              value={newAddPage}
                              onChange={(e) => setNewAddPage(Number(e.target.value))}
                              className="mt-0.5 w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-[#14B8A6]"
                            >
                              {Array.from({ length: Math.max(1, pdfPageCount) }, (_, i) => (
                                <option key={i} value={i + 1}>
                                  {i + 1}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block">
                            <span className="text-xs text-gray-600">Size</span>
                            <input
                              type="number"
                              min={6}
                              max={72}
                              value={newAddSize}
                              onChange={(e) => setNewAddSize(Number(e.target.value) || 11)}
                              className="mt-0.5 w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-[#14B8A6]"
                            />
                          </label>
                        </div>
                        <label className="block mt-2">
                          <span className="text-xs text-gray-600">Position</span>
                          <select
                            value={newAddPosition}
                            onChange={(e) => setNewAddPosition(e.target.value)}
                            className="mt-0.5 w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-[#14B8A6]"
                          >
                            {POSITIONS.map((p) => (
                              <option key={p.value} value={p.value}>
                                {p.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            addTextToPdf(newAddText, newAddPage, newAddPosition, newAddSize);
                            setNewAddText('');
                          }}
                          disabled={!newAddText.trim()}
                          className="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-[#14B8A6] text-[#0D9488] rounded-lg hover:bg-[#14B8A6]/10 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <HiOutlinePlus className="w-4 h-4" />
                          Add text
                        </button>
                        {addedTexts.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {addedTexts.map((t) => (
                              <li
                                key={t.id}
                                className="flex items-center gap-2 text-xs bg-white border border-gray-200 rounded px-2 py-1.5"
                              >
                                <span className="flex-1 truncate" title={t.text}>
                                  “{t.text}” p{t.pageNum}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => removeAddedText(t.id)}
                                  className="p-1 text-gray-400 hover:text-red-600 rounded"
                                  aria-label="Remove"
                                >
                                  <HiOutlineTrash className="w-3.5 h-3.5" />
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                    {(pdfFields.length > 0 || addedTexts.length > 0) && (
                      <div className="p-3 border-t border-gray-200 shrink-0">
                        <button
                          type="button"
                          onClick={handleSavePdf}
                          disabled={saving}
                          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-[#14B8A6] text-white rounded-lg hover:bg-[#0D9488] disabled:opacity-50"
                        >
                          <HiOutlineSave className="w-4 h-4" />
                          {saving ? 'Saving…' : 'Save (overwrite document)'}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {!loading && isWORD && (
            <div className="flex-1 p-4">
              <p className="text-sm text-gray-700 mb-4">
                Edit the Word document in your preferred editor, then upload the revised file below. It will replace the
                current document.
              </p>
              <div className="flex flex-col gap-3">
                <label className="block">
                  <span className="text-sm font-medium text-gray-700 block mb-1">Revised file (PDF or Word)</span>
                  <input
                    type="file"
                    accept=".doc,.docx,.pdf"
                    onChange={(e) => setWordReplaceFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-3 file:rounded file:border file:border-[#14B8A6] file:bg-[#14B8A6]/10 file:text-[#0D9488]"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleSaveWord}
                  disabled={saving || !wordReplaceFile}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-[#14B8A6] text-white rounded-lg hover:bg-[#0D9488] disabled:opacity-50 w-fit"
                >
                  <HiOutlineSave className="w-4 h-4" />
                  {saving ? 'Saving…' : 'Save (overwrite document)'}
                </button>
              </div>
            </div>
          )}

          {!loading && !isPDF && !isWORD && doc && (
            <div className="flex-1 p-4 text-sm text-gray-500">
              This document type cannot be edited here. Use View to open it.
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
