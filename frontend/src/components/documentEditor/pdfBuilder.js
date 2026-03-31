/**
 * Document editor: PDF byte building (form fill + added items) via pdf-lib.
 */
import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import {
  PDF_HEADER_BYTES,
  DEFAULT_BOX_W,
  DEFAULT_BOX_H,
  PDF_TEXT_MARGIN,
  PDF_BOX_CLAMP_PAD,
  PDF_BOX_CLAMP_RIGHT,
} from './constants';
import { hexToRgb } from './utils';

export function wrapTextLines(font, text, size, maxWidth) {
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
}

export async function buildPdfBytes(sourceBytes, fv, added, options = {}) {
  const { highlightFilledFormFields = false, initialFieldValues = null } = options;
  const hasHeader = sourceBytes?.length >= 5 && PDF_HEADER_BYTES.every((b, i) => sourceBytes[i] === b);
  if (!hasHeader) throw new Error('Invalid PDF source.');
  const pdfDoc = await PDFDocument.load(sourceBytes, { ignoreEncryption: true });
  const form = pdfDoc.getForm();
  const fields = form.getFields();
  const pages = pdfDoc.getPages();

  const isFilledValue = (v, isCheck) => {
    if (v === undefined || v === null) return false;
    if (isCheck) return v === true || String(v).toLowerCase() === 'yes';
    const s = String(v).trim();
    return s !== '' && s !== '-';
  };

  const isSignatureDataUrl = (v) => {
    if (v == null || typeof v !== 'string') return false;
    const s = v.trim();
    return s.toLowerCase().startsWith('data:image');
  };

  const signaturesToDraw = [];
  for (const f of fields) {
    const name = f.getName();
    const v = fv[name];
    if (v === undefined) continue;
    try {
      if (isSignatureDataUrl(v)) {
        const acro = f.acroField;
        if (acro && acro.getWidgets) {
          for (const w of acro.getWidgets()) {
            const rect = w.getRectangle?.();
            if (!rect || rect.width <= 0 || rect.height <= 0) continue;
            let pageIndex = 0;
            if (typeof w.P === 'function') {
              const pref = w.P();
              if (pref != null) {
                const idx = pages.findIndex((p) => p.ref && p.ref.toString() === (pref && pref.toString()));
                if (idx >= 0) pageIndex = idx;
              }
            } else if (typeof pdfDoc.findPageForAnnotationRef === 'function' && f.ref) {
              try {
                const pageRef = pdfDoc.findPageForAnnotationRef(f.ref);
                if (pageRef) {
                  const idx = pages.findIndex((p) => p.ref && pageRef && p.ref.toString() === pageRef.toString());
                  if (idx >= 0) pageIndex = idx;
                }
              } catch (_) {}
            }
            signaturesToDraw.push({ pageIndex, rect, imageDataUrl: String(v).trim() });
            break;
          }
        }
        continue;
      }
      if (typeof f.setText === 'function') f.setText(String(v ?? ''));
      else if (typeof f.setChecked === 'function') f.setChecked(Boolean(v));
    } catch (_) {}
  }

  let formFont = null;
  try {
    formFont = form.getDefaultFont?.() ?? (await pdfDoc.embedFont(StandardFonts.Helvetica));
  } catch (_) {
    formFont = await pdfDoc.embedFont(StandardFonts.Helvetica);
  }
  try {
    form.updateFieldAppearances(formFont);
  } catch (_) {}

  for (const { pageIndex, rect, imageDataUrl } of signaturesToDraw) {
    const page = pages[pageIndex];
    if (!page || !imageDataUrl) continue;
    try {
      const isJpeg = /data:image\/jpe?g;/i.test(imageDataUrl);
      const img = isJpeg
        ? await pdfDoc.embedJpg(imageDataUrl)
        : await pdfDoc.embedPng(imageDataUrl);
      page.drawImage(img, {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      });
    } catch (_) {}
  }

  const sameAsInitial = (name, isCheck, currentVal) => {
    if (initialFieldValues == null || !Object.prototype.hasOwnProperty.call(initialFieldValues, name))
      return false;
    const init = initialFieldValues[name];
    if (isCheck)
      return (Boolean(currentVal) || String(currentVal).toLowerCase() === 'yes') === (Boolean(init) || String(init).toLowerCase() === 'yes');
    return String(currentVal ?? '').trim() === String(init ?? '').trim();
  };
  const highlightRectsByPage = {};
  for (const f of fields) {
    const name = f.getName();
    const isCheck = typeof f.setChecked === 'function';
    const isFilled = isFilledValue(fv[name], isCheck);
    if (!isFilled) continue;
    const fill = initialFieldValues != null && sameAsInitial(name, isCheck, fv[name]) ? 'yellow' : 'green';
    try {
      const acro = f.acroField;
      if (!acro || !acro.getWidgets) continue;
      const widgets = acro.getWidgets();
      for (const w of widgets) {
        const rect = w.getRectangle?.();
        if (!rect || rect.width <= 0 || rect.height <= 0) continue;
        let pageIndex = 0;
        if (typeof w.P === 'function') {
          const pref = w.P();
          if (pref != null) {
            const idx = pages.findIndex((p) => p.ref && p.ref.toString() === (pref && pref.toString()));
            if (idx >= 0) pageIndex = idx;
          }
        } else if (typeof pdfDoc.findPageForAnnotationRef === 'function' && f.ref) {
          try {
            const pageRef = pdfDoc.findPageForAnnotationRef(f.ref);
            if (pageRef) {
              const idx = pages.findIndex((p) => p.ref && pageRef && p.ref.toString() === pageRef.toString());
              if (idx >= 0) pageIndex = idx;
            }
          } catch (_) {}
        }
        if (!highlightRectsByPage[pageIndex]) highlightRectsByPage[pageIndex] = [];
        highlightRectsByPage[pageIndex].push({ rect, fill });
      }
    } catch (_) {}
  }

  if (highlightFilledFormFields && fields.length > 0) {
    try {
      form.flatten({ updateFieldAppearances: false });
    } catch (_) {}
  }

  if (highlightFilledFormFields && pages.length > 0) {
    const yellow = rgb(1, 1, 0.4);
    const lightGreen = rgb(0.55, 0.88, 0.55);
    for (let i = 0; i < pages.length; i++) {
      const items = highlightRectsByPage[i] || [];
      const page = pages[i];
      for (const it of items) {
        const r = it.rect ?? it;
        const color = it.fill === 'green' ? lightGreen : yellow;
        try {
          page.drawRectangle({
            x: r.x,
            y: r.y,
            width: r.width,
            height: r.height,
            color,
            opacity: 0.35,
          });
        } catch (_) {}
      }
    }
  }

  if (added?.length > 0) {
    const [fontRegular, fontBold, fontItalic, fontBoldItalic] = await Promise.all([
      pdfDoc.embedStandardFont(StandardFonts.Helvetica),
      pdfDoc.embedStandardFont(StandardFonts.HelveticaBold),
      pdfDoc.embedStandardFont(StandardFonts.HelveticaOblique),
      pdfDoc.embedStandardFont(StandardFonts.HelveticaBoldOblique),
    ]);
    const getFont = (bold, italic) => {
      if (bold && italic) return fontBoldItalic;
      if (bold) return fontBold;
      if (italic) return fontItalic;
      return fontRegular;
    };
    for (const item of added) {
      const pageIndex = Math.min(Math.max(0, (item.pageNum || 1) - 1), pages.length - 1);
      const page = pages[pageIndex];
      if (!page) continue;
      const { width: pageWidth, height: pageHeight } = page.getSize();
      const size = Math.max(6, Math.min(72, Number(item.size) || 11));
      const lineHeight = size * 1.2;

      if (item.type === 'box' && item.box) {
        const { x: px, y: pyTop, width: pw, height: ph, previewW, previewH } = item.box;
        let bx, by, bw, bh;
        const npx = Number(px);
        const npy = Number(pyTop);
        const npw = Number(pw);
        const nph = Number(ph);
        const npreviewW = Number(previewW);
        const npreviewH = Number(previewH);
        if (
          Number.isFinite(npreviewW) &&
          Number.isFinite(npreviewH) &&
          npreviewW > 0 &&
          npreviewH > 0
        ) {
          const scaleX = pageWidth / npreviewW;
          const scaleY = pageHeight / npreviewH;
          bx = (Number.isFinite(npx) ? npx : 0) * scaleX;
          const pdfYFromTop = (Number.isFinite(npy) ? npy : 0) * scaleY;
          bw = (Number.isFinite(npw) ? npw : DEFAULT_BOX_W) * scaleX;
          bh = (Number.isFinite(nph) ? nph : DEFAULT_BOX_H) * scaleY;
          by = pageHeight - pdfYFromTop - bh;
        } else {
          bx = Number.isFinite(npx) ? npx : PDF_TEXT_MARGIN;
          bw = Number.isFinite(npw) ? npw : DEFAULT_BOX_W;
          bh = Number.isFinite(nph) ? nph : DEFAULT_BOX_H;
          by = pageHeight - (Number.isFinite(npy) ? npy : PDF_TEXT_MARGIN) - bh;
        }
        if (!Number.isFinite(bx) || !Number.isFinite(by) || !Number.isFinite(bw) || !Number.isFinite(bh)) continue;
        const textColor = item.color
          ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b)
          : rgb(0, 0, 0);
        if (item.text === '✓') {
          try {
            const cx = bx + bw / 2;
            const cy = by + bh / 2;
            const sym = Math.min(bw, bh) * 0.72;
            const t = Math.max(0.35, Math.min(bw, bh) / 14);
            const x1 = cx - sym * 0.5;
            const y1 = cy + sym * 0.12;
            const x2 = cx - sym * 0.08;
            const y2 = cy - sym * 0.28;
            const x3 = cx + sym * 0.48;
            const y3 = cy + sym * 0.5;
            page.drawLine({
              start: { x: x1, y: y1 },
              end: { x: x2, y: y2 },
              thickness: t,
              color: textColor,
            });
            page.drawLine({
              start: { x: x2, y: y2 },
              end: { x: x3, y: y3 },
              thickness: t,
              color: textColor,
            });
          } catch (_) {}
          continue;
        }
        if (item.text === '✗') {
          try {
            const cx = bx + bw / 2;
            const cy = by + bh / 2;
            const h = Math.min(bw, bh) * 0.36;
            const t = Math.max(0.35, Math.min(bw, bh) / 12);
            page.drawLine({
              start: { x: cx - h, y: cy - h },
              end: { x: cx + h, y: cy + h },
              thickness: t,
              color: textColor,
            });
            page.drawLine({
              start: { x: cx + h, y: cy - h },
              end: { x: cx - h, y: cy + h },
              thickness: t,
              color: textColor,
            });
          } catch (_) {}
          continue;
        }
        if (item.text === '•') {
          try {
            const cx = bx + bw / 2;
            const cy = by + bh / 2;
            const radius = Math.min(bw, bh) * 0.3;
            page.drawCircle({
              x: cx,
              y: cy,
              size: radius,
              color: textColor,
            });
          } catch (_) {}
          continue;
        }
        if (item.text === '○') {
          try {
            const cx = bx + bw / 2;
            const cy = by + bh / 2;
            const radius = Math.min(bw, bh) * 0.36;
            const strokeW = Math.max(0.5, Math.min(bw, bh) / 14);
            page.drawCircle({
              x: cx,
              y: cy,
              size: radius,
              borderWidth: strokeW,
              borderColor: textColor,
            });
          } catch (_) {}
          continue;
        }
        const maxW = Math.max(20, bw - 8);
        const font = getFont(!!item.bold, !!item.italic);
        const underline = !!item.underline;
        const strikethrough = !!item.strikethrough;
        try {
          const lines = wrapTextLines(font, item.text || '', size, maxW);
          let lineY = by + bh - size;
          for (const line of lines) {
            if (lineY < by + 4) break;
            const clampX = Math.max(bx + PDF_BOX_CLAMP_PAD, 0);
            const clampRight = pageWidth - PDF_BOX_CLAMP_RIGHT;
            const drawX = Math.min(clampX, clampRight - font.widthOfTextAtSize(line, size));
            const lineW = font.widthOfTextAtSize(line, size);
            page.drawText(line, { font, size, x: Math.max(0, drawX), y: lineY, color: textColor });
            const t = Math.max(0.3, size / 24);
            if (underline) {
              page.drawLine({
                start: { x: drawX, y: lineY - 2 },
                end: { x: drawX + lineW, y: lineY - 2 },
                thickness: t,
                color: textColor,
              });
            }
            if (strikethrough) {
              const midY = lineY + size * 0.35;
              page.drawLine({
                start: { x: drawX, y: midY },
                end: { x: drawX + lineW, y: midY },
                thickness: t,
                color: textColor,
              });
            }
            lineY -= lineHeight;
          }
        } catch (_) {}
      } else if (item.type === 'signature' && item.box && item.imageDataUrl) {
        const { x: px, y: pyTop, width: pw, height: ph, previewW, previewH } = item.box;
        const npreviewW = Number(previewW);
        const npreviewH = Number(previewH);
        let bx, by, bw, bh;
        if (Number.isFinite(npreviewW) && Number.isFinite(npreviewH) && npreviewW > 0 && npreviewH > 0) {
          const scaleX = pageWidth / npreviewW;
          const scaleY = pageHeight / npreviewH;
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
        if (!Number.isFinite(bx) || !Number.isFinite(by) || !Number.isFinite(bw) || !Number.isFinite(bh)) continue;
        try {
          const img = await pdfDoc.embedPng(item.imageDataUrl);
          page.drawImage(img, { x: bx, y: by, width: bw, height: bh });
        } catch (_) {}
      } else if (item.type === 'markup' && item.subtype === 'crossout' && item.box) {
        const { x: px, y: pyTop, width: pw, height: ph, previewW, previewH } = item.box;
        const npreviewW = Number(previewW);
        const npreviewH = Number(previewH);
        let bx, by, bw, bh;
        if (Number.isFinite(npreviewW) && Number.isFinite(npreviewH) && npreviewW > 0 && npreviewH > 0) {
          const scaleX = pageWidth / npreviewW;
          const scaleY = pageHeight / npreviewH;
          bx = Number(px) * scaleX;
          const pdfYFromTop = Number(pyTop) * scaleY;
          bw = Number(pw) * scaleX;
          bh = Number(ph) * scaleY;
          by = pageHeight - pdfYFromTop - bh;
        } else {
          bx = Number(px);
          by = pageHeight - Number(pyTop) - Number(ph);
          bw = Number(pw);
          bh = Number(ph);
        }
        if (!Number.isFinite(bx) || !Number.isFinite(by) || !Number.isFinite(bw) || !Number.isFinite(bh)) continue;
        const markupColor = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : rgb(0, 0, 0);
        try {
          const t = Math.max(0.5, Math.min(bw, bh) / 6);
          page.drawLine({
            start: { x: bx, y: by + bh },
            end: { x: bx + bw, y: by },
            thickness: t,
            color: markupColor,
          });
        } catch (_) {}
      } else if (item.type === 'markup' && (item.subtype === 'highlight' || item.subtype === 'underline' || item.subtype === 'strikethrough') && item.box) {
        const { x: px, y: pyTop, width: pw, height: ph, previewW, previewH } = item.box;
        const npreviewW = Number(previewW);
        const npreviewH = Number(previewH);
        let bx, by, bw, bh;
        if (Number.isFinite(npreviewW) && Number.isFinite(npreviewH) && npreviewW > 0 && npreviewH > 0) {
          const scaleX = pageWidth / npreviewW;
          const scaleY = pageHeight / npreviewH;
          bx = Number(px) * scaleX;
          const pdfYFromTop = Number(pyTop) * scaleY;
          bw = Number(pw) * scaleX;
          bh = Number(ph) * scaleY;
          by = pageHeight - pdfYFromTop - bh;
        } else {
          bx = Number(px);
          by = pageHeight - Number(pyTop) - Number(ph);
          bw = Number(pw);
          bh = Number(ph);
        }
        if (!Number.isFinite(bx) || !Number.isFinite(by) || !Number.isFinite(bw) || !Number.isFinite(bh)) continue;
        try {
          if (item.subtype === 'highlight') {
            const yellow = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : rgb(1, 1, 0);
            page.drawRectangle({
              x: bx,
              y: by,
              width: bw,
              height: bh,
              color: yellow,
              opacity: 0.4,
            });
          } else {
            const lineColor = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : rgb(0, 0, 0);
            const t = Math.max(0.5, bh / 4);
            if (item.subtype === 'underline') {
              page.drawLine({
                start: { x: bx, y: by },
                end: { x: bx + bw, y: by },
                thickness: t,
                color: lineColor,
              });
            } else {
              page.drawLine({
                start: { x: bx, y: by + bh / 2 },
                end: { x: bx + bw, y: by + bh / 2 },
                thickness: t,
                color: lineColor,
              });
            }
          }
        } catch (_) {}
      } else if (item.type === 'draw' && item.subtype === 'pen' && Array.isArray(item.path) && item.path.length >= 2 && item.previewW > 0 && item.previewH > 0) {
        const scaleX = pageWidth / Number(item.previewW);
        const scaleY = pageHeight / Number(item.previewH);
        const drawColor = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : rgb(0, 0, 0);
        const thickness = Math.max(0.5, Math.min(pageWidth, pageHeight) / 400);
        try {
          for (let j = 1; j < item.path.length; j++) {
            const a = item.path[j - 1];
            const b = item.path[j];
            const ax = Number(a.x) * scaleX;
            const ay = pageHeight - Number(a.y) * scaleY;
            const bx = Number(b.x) * scaleX;
            const by = pageHeight - Number(b.y) * scaleY;
            page.drawLine({
              start: { x: ax, y: ay },
              end: { x: bx, y: by },
              thickness,
              color: drawColor,
            });
          }
        } catch (_) {}
      } else if (item.type === 'draw' && item.subtype && ['line', 'arrow', 'rectangle', 'circle', 'polygon'].includes(item.subtype) && item.previewW > 0 && item.previewH > 0) {
        const scaleX = pageWidth / Number(item.previewW);
        const scaleY = pageHeight / Number(item.previewH);
        const toPdf = (x, y) => ({ x: Number(x) * scaleX, y: pageHeight - Number(y) * scaleY });
        const drawColor = item.color ? rgb(hexToRgb(item.color).r, hexToRgb(item.color).g, hexToRgb(item.color).b) : rgb(0, 0, 0);
        const thickness = Math.max(0.5, Math.min(pageWidth, pageHeight) / 400);
        try {
          if (item.subtype === 'line' || item.subtype === 'arrow') {
            const start = toPdf(item.start.x, item.start.y);
            const end = toPdf(item.end.x, item.end.y);
            page.drawLine({ start, end, thickness, color: drawColor });
            if (item.subtype === 'arrow') {
              const dx = end.x - start.x;
              const dy = end.y - start.y;
              const len = Math.hypot(dx, dy) || 1;
              const ux = dx / len;
              const uy = dy / len;
              const arrowLen = Math.min(len * 0.3, 12);
              const head1 = { x: end.x - ux * arrowLen + uy * arrowLen * 0.4, y: end.y - uy * arrowLen - ux * arrowLen * 0.4 };
              const head2 = { x: end.x - ux * arrowLen - uy * arrowLen * 0.4, y: end.y - uy * arrowLen + ux * arrowLen * 0.4 };
              page.drawLine({ start: end, end: head1, thickness, color: drawColor });
              page.drawLine({ start: end, end: head2, thickness, color: drawColor });
            }
          } else if (item.subtype === 'rectangle' && item.box) {
            const { x: px, y: pyTop, width: pw, height: ph } = item.box;
            const bx = Number(px) * scaleX;
            const by = pageHeight - Number(pyTop) * scaleY - Number(ph) * scaleY;
            const bw = Number(pw) * scaleX;
            const bh = Number(ph) * scaleY;
            page.drawRectangle({
              x: bx,
              y: by,
              width: bw,
              height: bh,
              borderWidth: thickness,
              borderColor: drawColor,
            });
          } else if (item.subtype === 'circle' && item.box) {
            const { x: px, y: pyTop, width: pw, height: ph } = item.box;
            const cx = (Number(px) + Number(pw) / 2) * scaleX;
            const cy = pageHeight - (Number(pyTop) + Number(ph) / 2) * scaleY;
            const radius = (Math.min(Number(pw), Number(ph)) / 2) * Math.min(scaleX, scaleY);
            if (radius > 0) {
              page.drawCircle({
                x: cx,
                y: cy,
                size: radius,
                borderWidth: thickness,
                borderColor: drawColor,
              });
            }
          } else if (item.subtype === 'polygon' && item.box) {
            const { x: px, y: pyTop, width: pw, height: ph } = item.box;
            const cx = (Number(px) + Number(pw) / 2) * scaleX;
            const cy = pageHeight - (Number(pyTop) + Number(ph) / 2) * scaleY;
            const r = (Math.min(Number(pw), Number(ph)) / 2) * Math.min(scaleX, scaleY);
            if (r > 0) {
              const hexPoints = Array.from({ length: 7 }, (_, i) => {
                const a = (i * 60 - 90) * (Math.PI / 180);
                return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
              });
              for (let j = 0; j < 6; j++) {
                page.drawLine({ start: hexPoints[j], end: hexPoints[j + 1], thickness, color: drawColor });
              }
            }
          }
        } catch (_) {}
      }
    }
  }
  return await pdfDoc.save();
}
