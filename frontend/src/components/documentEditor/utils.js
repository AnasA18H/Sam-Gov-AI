/**
 * Document editor: pure helpers and field/size utilities.
 */
import { PDF_FIELD_LABELS, PDF_FIELD_BASE_LABELS } from './constants';

export function isPdf(doc) {
  const t = (doc?.file_type ?? '').toString().toLowerCase();
  const name = (doc?.file_name ?? '').toLowerCase();
  return t.includes('pdf') || name.endsWith('.pdf');
}

export function isWord(doc) {
  const t = (doc?.file_type ?? '').toString().toLowerCase();
  const name = (doc?.file_name ?? '').toLowerCase();
  return t.includes('word') || name.endsWith('.docx') || name.endsWith('.doc');
}

export function pdfBytesContainXfa(bytes) {
  if (!bytes?.length) return false;
  try {
    const s = new TextDecoder('latin1').decode(bytes.slice(0, Math.min(bytes.length, 1024 * 1024)));
    return /\/XFA\s|\/XFA</.test(s) || /\bXFA\b/.test(s);
  } catch {
    return false;
  }
}

export function detailToMessage(detail) {
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

export function friendlyPdfErrorMessage(err) {
  const m = err?.message ?? String(err ?? '');
  if (/No PDF header|Invalid PDF|Failed to parse PDF/i.test(m)) {
    return 'The file is not a valid PDF or the server did not return document data.';
  }
  return m || 'Failed to load PDF.';
}

export function pdfFieldLeafName(fullName) {
  if (!fullName || typeof fullName !== 'string') return fullName ?? '';
  const parts = fullName.split('.');
  const last = parts[parts.length - 1];
  if (!last) return fullName.toLowerCase();
  const leaf = last.replace(/\[\d*\]/g, '').trim();
  return leaf ? leaf.toLowerCase() : fullName.toLowerCase();
}

export function humanizeLeaf(leaf) {
  if (!leaf) return 'Field';
  const numMatch = leaf.match(/^([a-z]+)(\d+)$/);
  if (numMatch) {
    const base = numMatch[1];
    const num = numMatch[2];
    const baseLabel = PDF_FIELD_BASE_LABELS[base];
    if (baseLabel) return `${baseLabel} ${num}`;
    const name = base.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[\s_\-]+/g, ' ').trim();
    return (name.replace(/\b\w/g, (c) => c.toUpperCase()) + ' ' + num).trim();
  }
  const s = leaf.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[\s_\-]+/g, ' ').trim();
  return s.replace(/\b\w/g, (c) => c.toUpperCase()) || leaf;
}

export function getFieldDisplayLabel(fieldName) {
  const leaf = pdfFieldLeafName(fieldName);
  const key = leaf.replace(/[\s_\-]+/g, '');
  return PDF_FIELD_LABELS[key] || PDF_FIELD_LABELS[leaf] || humanizeLeaf(leaf) || 'Field';
}

export function boxWidthFromSize(size) {
  const s = Math.max(6, Math.min(72, Number(size) || 11));
  return Math.round(Math.max(100, Math.min(500, 60 + s * 10)));
}

export function boxHeightFromSize(size) {
  const s = Math.max(6, Math.min(72, Number(size) || 11));
  return Math.round(Math.max(28, Math.min(180, 16 + s * 2.2)));
}

export function computeTextBoxSize(text, size, scale) {
  const s = Math.max(6, Math.min(72, Number(size) || 11));
  const sc = Number(scale) || 1;
  const lines = (text || '').trim().split('\n');
  const nonEmpty = lines.filter((l) => l.length > 0);
  const lineCount = nonEmpty.length || 1;
  const longest = nonEmpty.length ? Math.max(...nonEmpty.map((l) => l.length)) : 1;
  const charW = (s * sc) * 0.58;
  const lineH = (s * sc) * 1.25;
  const padH = 16;
  const padV = 10;
  return {
    width: Math.round(Math.max(40, Math.min(800, longest * charW + padH))),
    height: Math.round(Math.max(20, Math.min(600, lineCount * lineH + padV))),
  };
}

export function hexToRgb(hex) {
  const n = parseInt((hex || '#000000').replace(/^#/, ''), 16);
  return {
    r: ((n >> 16) & 0xff) / 255,
    g: ((n >> 8) & 0xff) / 255,
    b: (n & 0xff) / 255,
  };
}
