/**
 * Edit tooltip for an added item (signature, markup, draw, or text box) in the document editor.
 */
import React from 'react';
import { HiOutlineTrash } from 'react-icons/hi';
import {
  TEXT_BOX_COLORS,
  SIGNATURE_BOX_W,
  SIGNATURE_BOX_H,
  SIGNATURE_SIZE_MIN_W,
  SIGNATURE_SIZE_MAX_W,
  SIGNATURE_SIZE_MIN_H,
  SIGNATURE_SIZE_MAX_H,
} from './constants';

export default function EditorAddedItemTooltip({
  item,
  anchor,
  tooltipRef,
  onRemove,
  onUpdate,
  onClose,
}) {
  if (!item || !anchor) return null;

  const isSignature = item.type === 'signature';
  const isMarkup = item.type === 'markup';
  const isDraw = item.type === 'draw';
  const markupLabel =
    isMarkup && item.subtype
      ? item.subtype === 'crossout'
        ? 'Crossout'
        : item.subtype === 'highlight'
          ? 'Highlight'
          : item.subtype === 'underline'
            ? 'Underline'
            : item.subtype === 'strikethrough'
              ? 'Strikethrough'
              : 'Markup'
      : 'Markup';

  const style = {
    left: Math.min(anchor.x, typeof window !== 'undefined' ? window.innerWidth - 296 : anchor.x),
    top: Math.min(anchor.y + 10, typeof window !== 'undefined' ? window.innerHeight - 320 : anchor.y + 10),
  };

  return (
    <div
      ref={tooltipRef}
      className="fixed z-[60] w-72 rounded-xl shadow-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated p-3"
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      {isSignature ? (
        <>
          <p className="text-xs font-medium text-gray-500 dark:text-dark-muted mb-2">Saved signature</p>
          {item.imageDataUrl && (
            <img
              src={item.imageDataUrl}
              alt="Signature"
              className="mb-3 max-h-16 w-full object-contain bg-gray-50 dark:bg-dark-hover rounded border border-gray-200 dark:border-dark-border"
            />
          )}
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div>
              <label className="text-[10px] font-medium text-gray-500 dark:text-dark-muted block mb-0.5">Width</label>
              <input
                type="number"
                min={SIGNATURE_SIZE_MIN_W}
                max={SIGNATURE_SIZE_MAX_W}
                value={Math.round(Number(item.box?.width) || SIGNATURE_BOX_W)}
                onChange={(e) => {
                  const w = Math.max(
                    SIGNATURE_SIZE_MIN_W,
                    Math.min(SIGNATURE_SIZE_MAX_W, Number(e.target.value) || SIGNATURE_BOX_W)
                  );
                  onUpdate(item.id, { box: { ...item.box, width: w, height: item.box?.height ?? SIGNATURE_BOX_H } });
                }}
                className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-dark-border rounded bg-white dark:bg-dark-hover text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="text-[10px] font-medium text-gray-500 dark:text-dark-muted block mb-0.5">Height</label>
              <input
                type="number"
                min={SIGNATURE_SIZE_MIN_H}
                max={SIGNATURE_SIZE_MAX_H}
                value={Math.round(Number(item.box?.height) || SIGNATURE_BOX_H)}
                onChange={(e) => {
                  const h = Math.max(
                    SIGNATURE_SIZE_MIN_H,
                    Math.min(SIGNATURE_SIZE_MAX_H, Number(e.target.value) || SIGNATURE_BOX_H)
                  );
                  onUpdate(item.id, { box: { ...item.box, width: item.box?.width ?? SIGNATURE_BOX_W, height: h } });
                }}
                className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-dark-border rounded bg-white dark:bg-dark-hover text-gray-900 dark:text-white"
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm rounded-lg bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/60 border border-red-200 dark:border-red-800"
              title="Delete this signature from the PDF"
              aria-label="Delete this signature from the PDF"
            >
              <HiOutlineTrash className="w-4 h-4" />
              Delete
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-2.5 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
              title="Close edit panel"
              aria-label="Close edit panel"
            >
              Close
            </button>
          </div>
        </>
      ) : isMarkup || isDraw ? (
        <>
          <p className="text-xs font-medium text-gray-500 dark:text-dark-muted mb-2">
            {isDraw ? 'Draw' : markupLabel}
          </p>
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm rounded-lg bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/60 border border-red-200 dark:border-red-800"
              title="Remove from PDF"
              aria-label={`Remove ${isDraw ? 'draw' : markupLabel}`}
            >
              <HiOutlineTrash className="w-4 h-4" />
              Delete
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-2.5 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
              title="Close"
              aria-label="Close"
            >
              Close
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-xs font-medium text-gray-500 dark:text-dark-muted mb-2">Edit text box</p>
          <textarea
            value={item.text}
            onChange={(e) => onUpdate(item.id, { text: e.target.value })}
            rows={3}
            className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-dark-border rounded-lg bg-white dark:bg-dark-hover text-gray-900 dark:text-white resize-y mb-3"
            placeholder="Text content…"
          />
          <div className="flex items-center gap-3 mb-3">
            <div>
              <label className="text-[10px] font-medium text-gray-500 dark:text-dark-muted block mb-0.5">Size</label>
              <input
                type="number"
                min={6}
                max={72}
                value={Number(item.size) ?? 11}
                onChange={(e) => {
                  const val = Math.max(6, Math.min(72, Number(e.target.value) || 11));
                  onUpdate(item.id, { size: val });
                }}
                className="w-16 px-2 py-1 text-sm border border-gray-300 dark:border-dark-border rounded-lg bg-white dark:bg-dark-hover text-gray-900 dark:text-white"
                title="Font size (6–72)"
                aria-label="Font size"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-gray-500 dark:text-dark-muted">Style</span>
              <button
                type="button"
                onClick={() => onUpdate(item.id, { bold: !item.bold })}
                className={`px-2 py-1 text-xs font-bold rounded border ${item.bold ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border'}`}
                title="Bold text"
                aria-label="Bold text"
              >
                B
              </button>
              <button
                type="button"
                onClick={() => onUpdate(item.id, { italic: !item.italic })}
                className={`px-2 py-1 text-xs italic rounded border ${item.italic ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border'}`}
                title="Italic text"
                aria-label="Italic text"
              >
                I
              </button>
              <button
                type="button"
                onClick={() => onUpdate(item.id, { underline: !item.underline })}
                className={`px-2 py-1 text-xs rounded border ${item.underline ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border'}`}
                title="Underline text"
                aria-label="Underline text"
                style={{ textDecoration: 'underline' }}
              >
                U
              </button>
              <button
                type="button"
                onClick={() => onUpdate(item.id, { strikethrough: !item.strikethrough })}
                className={`px-2 py-1 text-xs rounded border ${item.strikethrough ? 'bg-gray-800 dark:bg-teal-dm text-white dark:text-dark-elevated border-gray-800 dark:border-teal-dm' : 'bg-white dark:bg-dark-hover border-gray-300 dark:border-dark-border'}`}
                title="Strikethrough text"
                aria-label="Strikethrough text"
                style={{ textDecoration: 'line-through' }}
              >
                S
              </button>
            </div>
          </div>
          <div className="mb-3">
            <p className="text-xs font-medium text-gray-500 dark:text-dark-muted mb-1.5">Color</p>
            <div className="flex flex-wrap gap-1.5 items-center">
              {TEXT_BOX_COLORS.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  onClick={() => onUpdate(item.id, { color: hex })}
                  className={`w-5 h-5 rounded-full border-2 hover:scale-110 transition-transform ${hex === '#ffffff' ? 'border-gray-300 dark:border-dark-border' : ''}`}
                  style={{
                    backgroundColor: hex,
                    ...(item.color === hex ? { borderColor: '#14B8A6', borderWidth: 2 } : {}),
                  }}
                  title={hex}
                  aria-label={`Color ${hex}`}
                />
              ))}
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="color"
                  value={item.color || '#000000'}
                  onChange={(e) => onUpdate(item.id, { color: e.target.value })}
                  className="w-5 h-5 rounded cursor-pointer border border-gray-300 dark:border-dark-border"
                  title="Custom color"
                  aria-label="Custom color"
                />
              </label>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm rounded-lg bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/60 border border-red-200 dark:border-red-800"
              title="Delete this text box from the PDF"
              aria-label="Delete this text box from the PDF"
            >
              <HiOutlineTrash className="w-4 h-4" />
              Delete
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-2.5 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
              title="Close edit panel"
              aria-label="Close edit panel"
            >
              Close
            </button>
          </div>
        </>
      )}
    </div>
  );
}
