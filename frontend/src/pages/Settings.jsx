/**
 * Settings Page – sidebar navigation and sectioned content (profile, email, signature, stamps, appearance)
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineCog,
  HiOutlineDocumentText,
  HiOutlineMail,
  HiOutlineCalendar,
  HiOutlineCheckCircle,
  HiOutlineX,
  HiOutlineOfficeBuilding,
  HiOutlineSave,
  HiOutlineUser,
  HiOutlineUpload,
  HiOutlineLocationMarker,
  HiOutlineIdentification,
  HiOutlineTag,
  HiOutlinePhone,
  HiOutlineBadgeCheck,
  HiOutlinePhotograph,
  HiOutlinePencil,
  HiOutlineSun,
  HiOutlineMoon,
  HiOutlineLogout,
  HiOutlineViewGrid,
  HiOutlineRefresh,
} from 'react-icons/hi';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft, FaBold, FaItalic, FaUnderline } from 'react-icons/fa';
import ThemeToggle from '../components/ThemeToggle';
import CustomDropdown from '../components/CustomDropdown';
import { useTheme } from '../contexts/ThemeContext';

const SETTINGS_SECTIONS = [
  { id: 'profile', label: 'Profile', number: 1 },
  { id: 'email', label: 'Email & calendar', number: 2 },
  { id: 'signature', label: 'Digital signature', number: 3 },
  { id: 'stamps', label: 'Custom stamps', number: 4 },
  { id: 'appearance', label: 'Appearance', number: 5 },
];

const Settings = () => {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  /** Which settings section is shown (separate page per section) */
  const [activeSettingsSection, setActiveSettingsSection] = useState('profile');
  const [emailConnection, setEmailConnection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileForm, setProfileForm] = useState({
    company_name: '',
    company_address: '',
    uei: '',
    cage: '',
    tin: '',
    contract_officer_name: '',
    digital_signature: '',
    digital_signature_2: '',
    digital_signature_3: '',
    custom_stamps: [],
    email: '',
    phone: '',
  });
  /** Which signature slot (0–2) is being edited; user can have at most 3 signatures. */
  const [activeSignatureIndex, setActiveSignatureIndex] = useState(0);
  /** Custom stamps workbench: "image" | "text" */
  const [stampWorkbenchMode, setStampWorkbenchMode] = useState('text');
  /** From-text stamp options */
  const [stampText, setStampText] = useState('APPROVED');
  const [stampTextSize, setStampTextSize] = useState(24);
  const [stampTextColor, setStampTextColor] = useState('#b91c1c');
  const [stampStyle, setStampStyle] = useState('circle'); // 'none' | 'circle' | 'rect' | 'rounded'
  const [stampName, setStampName] = useState('');
  const [stampFontFamily, setStampFontFamily] = useState('Helvetica Neue');
  const [stampFontWeight, setStampFontWeight] = useState('bold'); // 'normal' | 'bold'
  const [stampItalic, setStampItalic] = useState(false);
  const [stampUnderline, setStampUnderline] = useState(false);
  const [stampBorderWidth, setStampBorderWidth] = useState(3);
  const [stampOpacity, setStampOpacity] = useState(1);
  /** From-image: new stamp name when uploading */
  const [stampImageName, setStampImageName] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await authAPI.getEmailConnection();
        if (!cancelled) setEmailConnection(res.data);
      } catch {
        if (!cancelled) setEmailConnection({ connected: false });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setProfileLoading(true);
      try {
        const res = await authAPI.getProfile();
        if (!cancelled && res.data) {
          setProfile(res.data);
          setProfileForm({
            company_name: res.data.company_name ?? '',
            company_address: res.data.company_address ?? '',
            uei: res.data.uei ?? '',
            cage: res.data.cage ?? '',
            tin: res.data.tin ?? '',
            contract_officer_name: res.data.contract_officer_name ?? '',
            digital_signature: res.data.digital_signature ?? '',
            digital_signature_2: res.data.digital_signature_2 ?? '',
            digital_signature_3: res.data.digital_signature_3 ?? '',
            custom_stamps: Array.isArray(res.data.custom_stamps) ? res.data.custom_stamps : [],
            email: res.data.email ?? '',
            phone: res.data.phone ?? '',
          });
        }
      } catch {
        if (!cancelled) setProfile(null);
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const signatureCanvasRef = useRef(null);
  const signatureContainerRef = useRef(null);
  const signatureLogicalSizeRef = useRef({ w: 0, h: 0 });
  const signatureDrawingRef = useRef(false);
  const signatureDataUrlRef = useRef('');
  const stampPreviewCanvasRef = useRef(null);

  const resizeSignatureCanvas = useRef(function resizeSignatureCanvasFn() {
    const container = signatureContainerRef.current;
    const canvas = signatureCanvasRef.current;
    if (!container || !canvas || !container.isConnected) return;
    const logicalW = container.clientWidth;
    const logicalH = container.clientHeight;
    if (logicalW <= 0 || logicalH <= 0) return;
    const scale = Math.min(Math.max(window.devicePixelRatio || 1, 2), 4);
    canvas.width = logicalW * scale;
    canvas.height = logicalH * scale;
    canvas.style.width = `${logicalW}px`;
    canvas.style.height = `${logicalH}px`;
    signatureLogicalSizeRef.current = { w: logicalW, h: logicalH };
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(scale, scale);
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, logicalW, logicalH);
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 1;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const dataUrl = signatureDataUrlRef.current;
    if (dataUrl && dataUrl.startsWith('data:image')) {
      const img = new Image();
      img.onload = () => {
        ctx.shadowBlur = 0;
        ctx.fillStyle = '#ffffff';
        ctx.clearRect(0, 0, logicalW, logicalH);
        ctx.fillRect(0, 0, logicalW, logicalH);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        const drawScale = Math.min(logicalW / img.width, logicalH / img.height, 1);
        const w = img.width * drawScale;
        const h = img.height * drawScale;
        ctx.drawImage(img, (logicalW - w) / 2, (logicalH - h) / 2, w, h);
      };
      img.src = dataUrl;
    }
  });

  useEffect(() => {
    const container = signatureContainerRef.current;
    const canvas = signatureCanvasRef.current;
    if (!container || !canvas || !container.isConnected) return;
    resizeSignatureCanvas.current();
    const ro = new ResizeObserver(() => { resizeSignatureCanvas.current(); });
    ro.observe(container);
    return () => ro.disconnect();
  }, [profileLoading, theme, activeSettingsSection]);

  const signatureFieldKey = activeSignatureIndex === 0 ? 'digital_signature' : activeSignatureIndex === 1 ? 'digital_signature_2' : 'digital_signature_3';
  const currentSignatureDataUrl = profileForm[signatureFieldKey] ?? '';
  const [signatureRefreshTrigger, setSignatureRefreshTrigger] = useState(0);
  const refreshSignaturePad = () => setSignatureRefreshTrigger((t) => t + 1);

  useEffect(() => {
    const dataUrl = currentSignatureDataUrl;
    signatureDataUrlRef.current = dataUrl;
    if (signatureDrawingRef.current) return;
    const canvas = signatureCanvasRef.current;
    if (!canvas || !canvas.isConnected) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    if (!ctx) return;
    const { w: lw, h: lh } = signatureLogicalSizeRef.current;
    if (lw <= 0 || lh <= 0) return;
    const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 2), 4);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#ffffff';
    ctx.clearRect(0, 0, lw, lh);
    ctx.fillRect(0, 0, lw, lh);
    if (!dataUrl || !dataUrl.startsWith('data:image')) return;
    const img = new Image();
    img.onload = () => {
      if (signatureDrawingRef.current) return;
      const c = signatureCanvasRef.current;
      if (!c || !c.isConnected) return;
      const cctx = c.getContext('2d', { willReadFrequently: false });
      if (!cctx) return;
      cctx.setTransform(1, 0, 0, 1, 0, 0);
      cctx.scale(dpr, dpr);
      cctx.shadowBlur = 0;
      cctx.fillStyle = '#ffffff';
      cctx.clearRect(0, 0, lw, lh);
      cctx.fillRect(0, 0, lw, lh);
      cctx.imageSmoothingEnabled = true;
      cctx.imageSmoothingQuality = 'high';
      const scale = Math.min(lw / img.width, lh / img.height, 1);
      const w = img.width * scale;
      const h = img.height * scale;
      cctx.drawImage(img, (lw - w) / 2, (lh - h) / 2, w, h);
    };
    img.src = dataUrl;
  }, [currentSignatureDataUrl, signatureRefreshTrigger, activeSettingsSection]);

  const [signatureDrawing, setSignatureDrawing] = useState(false);
  const lastSignaturePointRef = useRef(null);
  /** Smooth stroke: buffer of points for quadraticCurveTo midpoint interpolation (curve through midpoints) */
  const signaturePointsRef = useRef([]);
  const signaturePathEndRef = useRef(null);
  /** Ink pen: default blue-black ink, smooth fine line */
  const [signaturePenColor, setSignaturePenColor] = useState('#0c0c14');
  const [signaturePenWidth, setSignaturePenWidth] = useState(1);
  const SIGNATURE_PALETTE = [
    { name: 'Ink', hex: '#0c0c14' },
    { name: 'Black', hex: '#000000' },
    { name: 'Navy', hex: '#1e3a5f' },
    { name: 'Blue', hex: '#2563eb' },
    { name: 'Gray', hex: '#374151' },
    { name: 'Brown', hex: '#78350f' },
    { name: 'Slate', hex: '#475569' },
  ];

  const handleProfileChange = (field, value) => {
    setProfileForm((prev) => ({ ...prev, [field]: value }));
  };

  const getSignatureCtx = () => {
    const canvas = signatureCanvasRef.current;
    if (!canvas) return null;
    return canvas.getContext('2d', { willReadFrequently: false });
  };

  const clearSignaturePad = () => {
    const canvas = signatureCanvasRef.current;
    const { w: lw, h: lh } = signatureLogicalSizeRef.current;
    if (canvas && lw > 0 && lh > 0) {
      const ctx = canvas.getContext('2d', { willReadFrequently: false });
      if (ctx) {
        const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 2), 4);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(dpr, dpr);
        ctx.shadowBlur = 0;
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, lw, lh);
      }
    }
    handleProfileChange(signatureFieldKey, '');
  };

  const captureSignatureFromCanvas = () => {
    const canvas = signatureCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    if (!ctx) return;
    const blank = document.createElement('canvas');
    blank.width = canvas.width;
    blank.height = canvas.height;
    const blankCtx = blank.getContext('2d', { willReadFrequently: true });
    if (!blankCtx) return;
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let empty = true;
    for (let i = 3; i < imageData.data.length; i += 4) {
      if (imageData.data[i] > 0) { empty = false; break; }
    }
    if (!empty) handleProfileChange(signatureFieldKey, canvas.toDataURL('image/png'));
  };

  const startDraw = (e) => {
    if (e.type === 'touchstart') e.preventDefault();
    const ctx = getSignatureCtx();
    if (!ctx) return;
    signatureDrawingRef.current = true;
    setSignatureDrawing(true);
    ctx.strokeStyle = signaturePenColor;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.shadowBlur = 0;
    ctx.lineWidth = signaturePenWidth;
    const rect = signatureCanvasRef.current.getBoundingClientRect();
    const x = (e.clientX ?? e.touches?.[0]?.clientX) - rect.left;
    const y = (e.clientY ?? e.touches?.[0]?.clientY) - rect.top;
    const p = { x, y };
    lastSignaturePointRef.current = p;
    signaturePointsRef.current = [p];
    signaturePathEndRef.current = p;
  };

  const SIGNATURE_MIN_DISTANCE = 2; /* px – skip points closer than this for smoother curves */

  const draw = (e) => {
    if (!signatureDrawingRef.current) return;
    const ctx = getSignatureCtx();
    if (!ctx) return;
    e.preventDefault();
    const rect = signatureCanvasRef.current.getBoundingClientRect();
    const x = (e.clientX ?? e.touches?.[0]?.clientX) - rect.left;
    const y = (e.clientY ?? e.touches?.[0]?.clientY) - rect.top;
    const p = { x, y };
    const points = signaturePointsRef.current;
    /* Skip point if too close to last (reduces jaggedness, smoother stroke) */
    if (points.length > 0) {
      const last = points[points.length - 1];
      const dist = Math.hypot(p.x - last.x, p.y - last.y);
      if (dist < SIGNATURE_MIN_DISTANCE) return;
    }
    points.push(p);
    lastSignaturePointRef.current = p;

    /* Smooth stroke: quadraticCurveTo with midpoint (curve through midpoints for smooth joins) */
    ctx.lineWidth = signaturePenWidth;
    ctx.shadowBlur = 0;
    if (points.length >= 3) {
      const prev = points[points.length - 2];
      const curr = points[points.length - 1];
      const midX = (prev.x + curr.x) * 0.5;
      const midY = (prev.y + curr.y) * 0.5;
      const pathEnd = signaturePathEndRef.current;
      ctx.beginPath();
      ctx.moveTo(pathEnd.x, pathEnd.y);
      ctx.quadraticCurveTo(prev.x, prev.y, midX, midY);
      ctx.stroke();
      signaturePathEndRef.current = { x: midX, y: midY };
      /* Keep only last 2 points to limit memory */
      signaturePointsRef.current = [prev, curr];
    } else if (points.length === 2) {
      /* First segment: straight line until we have 3 points for smooth curve */
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      ctx.lineTo(points[1].x, points[1].y);
      ctx.stroke();
      signaturePathEndRef.current = p;
    }
  };

  const endDraw = () => {
    if (signatureDrawing) captureSignatureFromCanvas();
    signatureDrawingRef.current = false;
    setSignatureDrawing(false);
    lastSignaturePointRef.current = null;
    signaturePointsRef.current = [];
    signaturePathEndRef.current = null;
  };

  const handleSignatureFile = (e) => {
    const file = e.target?.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result && typeof reader.result === 'string') handleProfileChange(signatureFieldKey, reader.result);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleProfileSave = async () => {
    setProfileSaving(true);
    setProfileSaved(false);
    try {
      const res = await authAPI.updateProfile(profileForm);
      setProfile(res.data);
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 4000);
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to save profile');
    } finally {
      setProfileSaving(false);
    }
  };

  /** Build font string for stamp (canvas font property). Includes italic and weight. */
  const stampFontString = (fontSize) => `${stampItalic ? 'italic' : 'normal'} ${stampFontWeight} ${fontSize}px "${stampFontFamily}", Helvetica, Arial, sans-serif`;

  /** Draw shape on ctx (circle, rect, rounded) around center; lineWidth and color set by caller. */
  const drawStampShape = (ctx, cx, cy, w, h, style, lineWidth) => {
    const pad = 4;
    const r = Math.min(w, h) / 2 - pad;
    if (style === 'circle') {
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    } else if (style === 'rect') {
      ctx.strokeRect(pad, pad, w - pad * 2, h - pad * 2);
    } else if (style === 'rounded') {
      const rad = Math.min(12, (w + h) / 8);
      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath();
        ctx.roundRect(pad, pad, w - pad * 2, h - pad * 2, rad);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.moveTo(pad + rad, pad);
        ctx.lineTo(w - pad - rad, pad);
        ctx.quadraticCurveTo(w - pad, pad, w - pad, pad + rad);
        ctx.lineTo(w - pad, h - pad - rad);
        ctx.quadraticCurveTo(w - pad, h - pad, w - pad - rad, h - pad);
        ctx.lineTo(pad + rad, h - pad);
        ctx.quadraticCurveTo(pad, h - pad, pad, h - pad - rad);
        ctx.lineTo(pad, pad + rad);
        ctx.quadraticCurveTo(pad, pad, pad + rad, pad);
        ctx.closePath();
        ctx.stroke();
      }
    }
  };

  /** Draw multi-line stamp text on ctx (center-aligned block). Optional underline per line. */
  const drawStampTextLines = (ctx, lines, cx, cy, fontSize, lineHeightMultiplier = 1.25) => {
    const lineHeight = fontSize * lineHeightMultiplier;
    const totalH = lines.length * lineHeight - (lineHeight - fontSize);
    let y = cy - totalH / 2 + fontSize / 2;
    ctx.fillStyle = stampTextColor;
    ctx.strokeStyle = stampTextColor;
    const underlineOffset = fontSize * 0.42;
    for (const line of lines) {
      const text = line.trim() || ' ';
      ctx.fillText(text, cx, y);
      if (stampUnderline) {
        const metrics = ctx.measureText(text);
        const halfW = metrics.width / 2;
        const lineY = y + underlineOffset;
        ctx.beginPath();
        ctx.moveTo(cx - halfW, lineY);
        ctx.lineTo(cx + halfW, lineY);
        ctx.lineWidth = Math.max(1, Math.round(fontSize / 16));
        ctx.stroke();
      }
      y += lineHeight;
    }
  };

  /** Create a stamp image from text (Acrobat-style: multi-line text + optional shape + format). Returns data URL. */
  const createStampFromText = () => {
    const canvas = document.createElement('canvas');
    const padding = 16;
    const fontSize = Math.max(8, Math.min(72, stampTextSize));
    const lines = (stampText || 'Stamp').split('\n').map((l) => l.trim() || ' ');
    const effectiveLines = lines.length ? lines : ['Stamp'];
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    if (!ctx) return null;
    ctx.font = stampFontString(fontSize);
    let textW = 0;
    for (const line of effectiveLines) {
      const w = ctx.measureText(line || ' ').width;
      if (w > textW) textW = w;
    }
    const lineHeight = fontSize * 1.25;
    const textH = effectiveLines.length * lineHeight - (lineHeight - fontSize);
    const w = Math.max(200, textW + padding * 2);
    const h = Math.max(80, textH + padding * 2);
    canvas.width = w;
    canvas.height = h;
    ctx.font = stampFontString(fontSize);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cx = w / 2;
    const cy = h / 2;
    ctx.globalAlpha = Math.max(0.2, Math.min(1, stampOpacity));
    if (stampStyle !== 'none' && stampBorderWidth > 0) {
      ctx.strokeStyle = stampTextColor;
      ctx.lineWidth = Math.max(0, Math.min(12, stampBorderWidth));
      drawStampShape(ctx, cx, cy, w, h, stampStyle, ctx.lineWidth);
    }
    drawStampTextLines(ctx, effectiveLines, cx, cy, fontSize);
    ctx.globalAlpha = 1;
    return canvas.toDataURL('image/png');
  };

  const addStampFromText = () => {
    const dataUrl = createStampFromText();
    if (!dataUrl) return;
    const firstLine = (stampText || 'Stamp').split('\n')[0]?.trim() || 'Stamp';
    const name = (stampName || firstLine || 'Stamp').trim() || 'Stamp';
    setProfileForm((prev) => ({
      ...prev,
      custom_stamps: [...(prev.custom_stamps || []), { name, dataUrl }],
    }));
    setStampName('');
  };

  const handleStampImageUpload = (e) => {
    const file = e.target?.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== 'string') return;
      const name = (stampImageName || file.name.replace(/\.[^.]+$/, '') || 'Stamp').trim() || 'Stamp';
      setProfileForm((prev) => ({
        ...prev,
        custom_stamps: [...(prev.custom_stamps || []), { name, dataUrl: reader.result }],
      }));
      setStampImageName('');
      e.target.value = '';
    };
    reader.readAsDataURL(file);
  };

  const removeStamp = (index) => {
    setProfileForm((prev) => {
      const next = [...(prev.custom_stamps || [])];
      next.splice(index, 1);
      return { ...prev, custom_stamps: next };
    });
  };

  const customStamps = profileForm.custom_stamps || [];

  const STAMP_PREVIEW_W = 380;
  const STAMP_PREVIEW_H = 160;

  useEffect(() => {
    const canvas = stampPreviewCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, w, h);
    const scale = Math.min(w / STAMP_PREVIEW_W, h / STAMP_PREVIEW_H, 1);
    const fontSize = Math.max(8, Math.min(72, Math.round(stampTextSize * scale)));
    const lines = (stampText || 'Stamp').split('\n').map((l) => l.trim() || ' ');
    const effectiveLines = lines.length ? lines : ['Stamp'];
    ctx.font = stampFontString(fontSize);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cx = w / 2;
    const cy = h / 2;
    ctx.globalAlpha = Math.max(0.2, Math.min(1, stampOpacity));
    if (stampStyle !== 'none' && stampBorderWidth > 0) {
      ctx.strokeStyle = stampTextColor;
      ctx.lineWidth = Math.max(2, stampBorderWidth * scale);
      drawStampShape(ctx, cx, cy, w, h, stampStyle, ctx.lineWidth);
    }
    drawStampTextLines(ctx, effectiveLines, cx, cy, fontSize);
    ctx.globalAlpha = 1;
  }, [stampText, stampTextSize, stampTextColor, stampStyle, stampFontFamily, stampFontWeight, stampItalic, stampUnderline, stampBorderWidth, stampOpacity]);

  const handleConnect = (provider) => {
    const url = provider === 'google' ? authAPI.connectGoogleUrl() : authAPI.connectMicrosoftUrl();
    window.location.href = url;
  };

  const handleDisconnect = async () => {
    if (!confirm('Disconnect your email and calendar? You can reconnect later.')) return;
    try {
      await authAPI.disconnectEmailConnection();
      setEmailConnection({ connected: false });
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to disconnect');
    }
  };

  const displayName = user?.email?.split('@')[0] || user?.name || 'User';

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 dark:bg-matte transition-colors duration-200">
        <nav className="bg-white dark:bg-dark-surface border-b border-gray-200 dark:border-dark-border shadow-sm transition-colors duration-200">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-14 items-center">
              <div className="flex items-center space-x-2">
                <div className="flex flex-col space-y-0.5">
                  <div className="h-0.5 w-6 bg-green-500 rounded" />
                  <div className="h-0.5 w-6 bg-yellow-400 rounded" />
                  <div className="h-0.5 w-6 bg-blue-500 rounded" />
                </div>
                <span className="text-lg font-semibold text-[#2D1B3D] dark:text-white">Gov OPs AI</span>
              </div>
              <div className="flex items-center gap-2">
                <ThemeToggle />
                <button
                  onClick={() => navigate('/profile')}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 border border-[#14B8A6]/40 dark:border-teal-dm/40 rounded-xl hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/30 transition-colors"
                  title="Open profile"
                  aria-label="Open profile"
                >
                  <HiOutlineUser className="w-4 h-4 shrink-0" />
                  Profile
                </button>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-hover border border-gray-200 dark:border-dark-border rounded-xl hover:bg-gray-50 dark:hover:bg-dark-border transition-colors"
                  title="Back to dashboard"
                  aria-label="Back to dashboard"
                >
                  <HiOutlineArrowLeft className="w-4 h-4 shrink-0" />
                  Dashboard
                </button>
              </div>
            </div>
          </div>
        </nav>

        <div className="relative w-full">
          {/* Sidebar – fixed so it stays while main content scrolls; theme-aware */}
          <aside
            className="fixed left-0 top-14 bottom-0 z-20 w-56 flex flex-col rounded-r-2xl shadow-lg transition-colors duration-200
              bg-[#0D9488] dark:bg-dark-surface text-white dark:text-gray-100"
          >
            <div className="p-5 pb-4">
              <div className="flex items-center gap-3 mb-1">
                <span className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20 dark:bg-white/10">
                  <HiOutlineUser className="w-5 h-5" />
                </span>
                <span className="text-sm font-medium">Welcome, {displayName}</span>
              </div>
            </div>
            <nav className="flex-1 px-3 pb-4 space-y-0.5 overflow-y-auto">
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-3 w-full px-3 py-2.5 text-left text-sm font-medium rounded-lg hover:bg-white/15 dark:hover:bg-white/10 transition-colors"
              >
                <HiOutlineViewGrid className="w-5 h-5 shrink-0 opacity-90" />
                Dashboard
              </button>
              <button
                type="button"
                onClick={() => navigate('/profile')}
                className="flex items-center gap-3 w-full px-3 py-2.5 text-left text-sm font-medium rounded-lg hover:bg-white/15 dark:hover:bg-white/10 transition-colors"
              >
                <HiOutlineUser className="w-5 h-5 shrink-0 opacity-90" />
                Profile
              </button>
              <div className="border-t border-white/20 dark:border-gray-500/30 my-3" aria-hidden />
              {SETTINGS_SECTIONS.map(({ id, label, number }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveSettingsSection(id)}
                  className={`flex items-center gap-3 w-full px-3 py-2.5 text-left text-sm font-medium rounded-lg transition-colors ${activeSettingsSection === id ? 'bg-white/25 dark:bg-teal-dm/30' : 'hover:bg-white/15 dark:hover:bg-white/10'}`}
                >
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-white/20 dark:bg-white/10 text-xs font-bold shrink-0">{number}</span>
                  {label}
                </button>
              ))}
            </nav>
            <div className="border-t border-white/20 dark:border-gray-500/30 p-3">
              <button
                type="button"
                onClick={() => { logout(); navigate('/login'); }}
                className="flex items-center gap-3 w-full px-3 py-2.5 text-left text-sm font-medium rounded-lg hover:bg-white/15 dark:hover:bg-white/10 transition-colors"
              >
                <HiOutlineLogout className="w-5 h-5 shrink-0 opacity-90" />
                Log out
              </button>
            </div>
          </aside>

          {/* Main content – scrolls independently; offset by sidebar width */}
          <main className="ml-56 min-h-[calc(100vh-3.5rem)] overflow-auto bg-white dark:bg-dark-elevated transition-colors duration-200">
            <div className="p-8 pb-12 max-w-6xl">
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">Your personal profile and app settings.</p>

              {activeSettingsSection === 'profile' && (
              <section id="section-profile" className="mb-10">
                <div className="flex items-center gap-3 mb-5">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-dark-border text-gray-600 dark:text-gray-300 text-sm font-bold">1</span>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Profile</h2>
                </div>
          <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/50 dark:bg-dark-hover/20 p-5">
            <div className="p-5">
              <p className="text-sm app-note mb-6 inline-block">Saved here and used when you autofill PDF forms (e.g. SF 1449). Fill once, use every time.</p>
              {profileLoading ? (
                <p className="text-sm text-gray-500 dark:text-gray-300">Loading profile…</p>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                    <div className="xl:col-span-2">
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineOfficeBuilding className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        Company name
                      </label>
                      <input
                        type="text"
                        value={profileForm.company_name}
                        onChange={(e) => handleProfileChange('company_name', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Your company or organization"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineTag className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        CAGE
                      </label>
                      <input
                        type="text"
                        value={profileForm.cage}
                        onChange={(e) => handleProfileChange('cage', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="CAGE code"
                      />
                    </div>
                    <div className="md:col-span-2 xl:col-span-3">
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineLocationMarker className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        Company address
                      </label>
                      <textarea
                        value={profileForm.company_address}
                        onChange={(e) => handleProfileChange('company_address', e.target.value)}
                        rows={2}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Street, city, state, ZIP"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineIdentification className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        UEI
                      </label>
                      <input
                        type="text"
                        value={profileForm.uei}
                        onChange={(e) => handleProfileChange('uei', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Unique Entity ID"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineDocumentText className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        TIN
                      </label>
                      <input
                        type="text"
                        value={profileForm.tin}
                        onChange={(e) => handleProfileChange('tin', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Tax Identification Number"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineUser className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        Contract officer name
                      </label>
                      <input
                        type="text"
                        value={profileForm.contract_officer_name}
                        onChange={(e) => handleProfileChange('contract_officer_name', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Name and title of person signing"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlineMail className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        Email
                      </label>
                      <input
                        type="email"
                        value={profileForm.email}
                        onChange={(e) => handleProfileChange('email', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Contact email for forms"
                      />
                    </div>
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        <HiOutlinePhone className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0" />
                        Phone number
                      </label>
                      <input
                        type="tel"
                        value={profileForm.phone}
                        onChange={(e) => handleProfileChange('phone', e.target.value)}
                        className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-dark-border rounded-xl bg-white dark:bg-dark-hover text-gray-900 dark:text-white focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent"
                        placeholder="Contact phone for forms"
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
              </section>
              )}

              {activeSettingsSection === 'email' && (
              <section id="section-email" className="mb-10">
                <div className="flex items-center gap-3 mb-5">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-dark-border text-gray-600 dark:text-gray-300 text-sm font-bold">2</span>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Email & calendar</h2>
                </div>
                <div className="rounded-2xl bg-gray-50/60 dark:bg-dark-hover/30 p-6">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Connect an account to send quote emails and sync deadlines to your calendar.</p>
                  {loading ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>
                  ) : emailConnection?.connected ? (
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                      <div className="flex items-center gap-4 min-w-0">
                        <div className="flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10 dark:bg-emerald-500/20 shrink-0">
                          <HiOutlineCheckCircle className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div className="min-w-0">
                          <span className="inline-block text-[11px] font-medium uppercase tracking-wider text-emerald-600 dark:text-emerald-400 mb-0.5">Connected</span>
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{emailConnection.sender_email}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{emailConnection.provider === 'google' ? 'Google' : 'Microsoft'}</p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={handleDisconnect}
                        className="self-start sm:self-center text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                        title="Disconnect email account"
                        aria-label="Disconnect email account"
                      >
                        Disconnect
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col sm:flex-row gap-3">
                      <button
                        type="button"
                        onClick={() => handleConnect('google')}
                        className="inline-flex items-center justify-center gap-3 px-5 py-3 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl bg-white dark:bg-dark-elevated border border-gray-200/80 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover transition-colors min-w-[140px]"
                        title="Connect Gmail"
                        aria-label="Connect Gmail"
                      >
                        <SiGoogle className="w-5 h-5 shrink-0" />
                        Gmail
                      </button>
                      <button
                        type="button"
                        onClick={() => handleConnect('microsoft')}
                        className="inline-flex items-center justify-center gap-3 px-5 py-3 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl bg-white dark:bg-dark-elevated border border-gray-200/80 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover transition-colors min-w-[140px]"
                        title="Connect Outlook"
                        aria-label="Connect Outlook"
                      >
                        <FaMicrosoft className="w-5 h-5 shrink-0" />
                        Outlook
                      </button>
                    </div>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-5 pt-5 border-t border-gray-200/60 dark:border-dark-border/60">
                    {emailConnection?.connected
                      ? 'Use “Add to Calendar” on an opportunity to create events for its deadlines.'
                      : 'After connecting, you can add opportunity deadlines to your calendar.'}
                  </p>
                </div>
              </section>
              )}

              {activeSettingsSection === 'signature' && (
              <section id="section-signature" className="mb-10">
                <div className="flex items-center gap-3 mb-5">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-dark-border text-gray-600 dark:text-gray-300 text-sm font-bold">3</span>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Digital signature</h2>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/50 dark:bg-dark-hover/20 p-5">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Draw or upload up to 3 signatures. In the document editor, use <strong>Draw → Signature</strong> to place one on the PDF.</p>
                  <div className="space-y-4">
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400">Saved signatures</p>
                    <div className="flex gap-3">
                      {[0, 1, 2].map((idx) => {
                        const key = idx === 0 ? 'digital_signature' : idx === 1 ? 'digital_signature_2' : 'digital_signature_3';
                        const dataUrl = profileForm[key];
                        const hasImage = dataUrl && String(dataUrl).startsWith('data:image');
                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => setActiveSignatureIndex(idx)}
                            title={hasImage ? 'Signature (has image)' : 'Signature'}
                            aria-label="Signature"
                            className={`flex flex-col items-center rounded-xl border-2 p-3 min-w-[100px] transition-all ${
                              activeSignatureIndex === idx
                                ? 'border-[#14B8A6] dark:border-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20'
                                : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover'
                            }`}
                          >
                            {hasImage ? (
                              <img src={dataUrl} alt="" className="w-20 h-12 object-contain rounded bg-white dark:bg-dark-elevated" />
                            ) : (
                              <span className="w-20 h-12 flex items-center justify-center rounded bg-white dark:bg-dark-elevated border border-gray-200 dark:border-dark-border text-gray-400 dark:text-gray-500 text-xs" aria-hidden>Empty</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    {currentSignatureDataUrl && currentSignatureDataUrl.startsWith('data:image') && (
                      <p className="flex items-center gap-1.5 text-xs font-medium text-[#0D9488] dark:text-teal-dm">
                        <HiOutlineCheckCircle className="w-4 h-4 shrink-0" />
                        Signature ready
                      </p>
                    )}
                    <div className="flex flex-col lg:flex-row gap-4 items-start">
                      <div ref={signatureContainerRef} className="relative flex-1 min-w-0 aspect-[100/40] min-h-[180px] w-full max-w-full rounded-xl border-2 border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated overflow-visible shadow-inner">
                        <canvas
                          ref={signatureCanvasRef}
                          className="block w-full h-full touch-none cursor-crosshair rounded-xl"
                          onMouseDown={startDraw}
                          onMouseMove={draw}
                          onMouseUp={endDraw}
                          onMouseLeave={endDraw}
                          onTouchStart={startDraw}
                          onTouchMove={draw}
                          onTouchEnd={endDraw}
                        />
                        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-lg px-2 py-1.5 ring-1 ring-black/5 dark:ring-white/5">
                          <button type="button" onClick={clearSignaturePad} title="Clear" aria-label="Clear signature pad" className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 transition-colors">
                            <HiOutlineX className="w-4 h-4" />
                            Clear
                          </button>
                          <label className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 cursor-pointer transition-colors">
                            <HiOutlineUpload className="w-4 h-4" />
                            Upload
                            <input type="file" accept="image/*" className="sr-only" onChange={handleSignatureFile} aria-hidden="true" />
                          </label>
                          <button type="button" onClick={refreshSignaturePad} title="Refresh" aria-label="Refresh signature pad" className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 transition-colors">
                            <HiOutlineRefresh className="w-4 h-4" />
                            Refresh
                          </button>
                        </div>
                      </div>
                      <div className="w-full lg:w-52 shrink-0">
                        <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated p-4 space-y-4">
                          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Ink pen</span>
                          <div>
                            <p className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">Color</p>
                            <div className="flex flex-wrap items-center gap-2">
                              <input type="color" value={signaturePenColor} onChange={(e) => setSignaturePenColor(e.target.value)} className="w-9 h-9 rounded-lg border-2 border-gray-200 dark:border-dark-border cursor-pointer bg-white dark:bg-dark-hover" title="Ink color" />
                              {SIGNATURE_PALETTE.map(({ name, hex }) => (
                                <button key={hex} type="button" onClick={() => setSignaturePenColor(hex)} className={`w-8 h-8 rounded-lg border-2 transition-all ${signaturePenColor === hex ? 'ring-2 ring-[#14B8A6] dark:ring-teal-dm ring-offset-2' : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-hover'}`} style={{ backgroundColor: hex }} title={name} />
                              ))}
                            </div>
                          </div>
                          <div>
                            <div className="flex items-center justify-between mb-1.5">
                              <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Width</p>
                              <span className="text-xs font-medium tabular-nums text-gray-700 dark:text-gray-300">{signaturePenWidth.toFixed(1)}</span>
                            </div>
                            <input type="range" min={0.5} max={10} step={0.1} value={signaturePenWidth} onChange={(e) => setSignaturePenWidth(Number(e.target.value))} className="w-full h-1 rounded-full appearance-none cursor-pointer bg-gray-200 dark:bg-dark-hover accent-[#14B8A6] dark:accent-teal-dm" title="Ink pen width" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-5 pt-5 border-t border-gray-200/60 dark:border-dark-border/60">
                    Use <strong>Draw → Signature</strong> in the document editor to place a signature on a PDF. Click <strong>Save profile</strong> at the bottom of this page to keep your signatures.
                  </p>
                </div>
              </section>
              )}

              {activeSettingsSection === 'stamps' && (
              <section id="section-stamps" className="mb-10">
                <div className="flex items-center gap-3 mb-5">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-dark-border text-gray-600 dark:text-gray-300 text-sm font-bold">4</span>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Custom stamps</h2>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/50 dark:bg-dark-hover/20 p-5">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Create text or image stamps (e.g. <strong>APPROVED</strong>, <strong>CONFIDENTIAL</strong>). In the document editor, use <strong>Draw → Stamp</strong> to place them on a PDF.</p>

                  {/* Saved stamps – dedicated section */}
                  <div className="mb-6">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">Saved stamps</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Stamps you create or upload appear here. Use them in the document editor via Draw → Stamp.</p>
                    {customStamps.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-300 dark:border-dark-border bg-white/50 dark:bg-dark-elevated/50 p-6 text-center">
                        <p className="text-sm text-gray-500 dark:text-gray-400">No stamps yet.</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Create one below with <strong>From text</strong> or <strong>From image</strong>, then click <strong>Save profile</strong> to keep it.</p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                        {customStamps.map((stamp, idx) => (
                          <div key={idx} className="rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated overflow-hidden shadow-sm hover:shadow-md transition-shadow flex flex-col">
                            <div className="flex-1 min-h-[80px] p-3 flex items-center justify-center bg-gray-50 dark:bg-dark-hover">
                              <img src={stamp.dataUrl} alt={stamp.name} className="max-w-full max-h-20 w-auto h-auto object-contain" />
                            </div>
                            <div className="px-3 py-2 border-t border-gray-100 dark:border-dark-border flex items-center justify-between gap-2">
                              <span className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate flex-1 min-w-0" title={stamp.name}>{stamp.name}</span>
                              <button type="button" onClick={() => removeStamp(idx)} title="Remove stamp" aria-label={`Remove ${stamp.name}`} className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors flex-shrink-0">
                                <HiOutlineX className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Create new stamp – heading, mode toggle, and form aligned */}
                  <div className="mt-6 pt-6 border-t border-gray-200 dark:border-dark-border">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">Create new stamp</h3>
                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 mb-5">
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 sm:min-w-[4.5rem]">Mode</span>
                      <div className="inline-flex items-center gap-1 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-sm px-2 py-1.5 ring-1 ring-black/5 dark:ring-white/5">
                        <button type="button" onClick={() => setStampWorkbenchMode('text')} className={`px-3 py-2 rounded-xl text-sm font-medium transition-colors ${stampWorkbenchMode === 'text' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black' : 'text-gray-600 dark:text-gray-300 hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 border border-transparent hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40'}`}>
                          From text
                        </button>
                        <button type="button" onClick={() => setStampWorkbenchMode('image')} className={`px-3 py-2 rounded-xl text-sm font-medium transition-colors ${stampWorkbenchMode === 'image' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black' : 'text-gray-600 dark:text-gray-300 hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 border border-transparent hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40'}`}>
                          From image
                        </button>
                      </div>
                    </div>
                  </div>
                  {stampWorkbenchMode === 'text' && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-2">
                      <div className="space-y-5">
                        <div>
                          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Text</label>
                          <textarea value={stampText} onChange={(e) => setStampText(e.target.value)} placeholder={"e.g. APPROVED\nMUHAMMAD ANAS"} rows={3} className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated text-gray-900 dark:text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent resize-y min-h-[4.5rem]" />
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Multiple lines allowed. Use Enter for a new line.</p>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Stamp name</label>
                          <input type="text" value={stampName} onChange={(e) => setStampName(e.target.value)} placeholder="Optional (default: first line of text)" className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated text-gray-900 dark:text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Format</label>
                          <div className="flex items-center gap-1">
                            <button type="button" onClick={() => setStampFontWeight((w) => (w === 'bold' ? 'normal' : 'bold'))} aria-pressed={stampFontWeight === 'bold'} title="Bold" className={`p-2 rounded-lg transition-colors ${stampFontWeight === 'bold' ? 'text-[#14B8A6] dark:text-teal-dm' : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'}`}>
                              <FaBold className="w-5 h-5" />
                            </button>
                            <button type="button" onClick={() => setStampItalic((v) => !v)} aria-pressed={stampItalic} title="Italic" className={`p-2 rounded-lg transition-colors ${stampItalic ? 'text-[#14B8A6] dark:text-teal-dm' : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'}`}>
                              <FaItalic className="w-5 h-5" />
                            </button>
                            <button type="button" onClick={() => setStampUnderline((v) => !v)} aria-pressed={stampUnderline} title="Underline" className={`p-2 rounded-lg transition-colors ${stampUnderline ? 'text-[#14B8A6] dark:text-teal-dm' : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'}`}>
                              <FaUnderline className="w-5 h-5" />
                            </button>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Font size</label>
                            <input type="range" min={8} max={48} value={stampTextSize} onChange={(e) => setStampTextSize(Number(e.target.value))} className="w-full h-1 rounded-full accent-[#14B8A6] dark:accent-teal-dm" />
                            <span className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 block">{stampTextSize}</span>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Color</label>
                            <input type="color" value={stampTextColor} onChange={(e) => setStampTextColor(e.target.value)} className="w-10 h-10 rounded-xl border border-gray-200 dark:border-dark-border cursor-pointer bg-white dark:bg-dark-hover" />
                          </div>
                        </div>
                        <div>
                          <label id="stamp-style-label" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Style</label>
                          <CustomDropdown
                            id="stamp-style"
                            options={[
                              { value: 'none', label: 'Text only' },
                              { value: 'circle', label: 'Circle' },
                              { value: 'rect', label: 'Rectangle' },
                              { value: 'rounded', label: 'Rounded rectangle' },
                            ]}
                            value={stampStyle}
                            onChange={setStampStyle}
                          />
                        </div>
                        <div>
                          <label id="stamp-font-label" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Font</label>
                          <CustomDropdown
                            id="stamp-font"
                            options={[
                              { value: 'Helvetica Neue', label: 'Helvetica Neue' },
                              { value: 'Arial', label: 'Arial' },
                              { value: 'Georgia', label: 'Georgia' },
                              { value: 'Courier New', label: 'Courier New' },
                              { value: 'Times New Roman', label: 'Times New Roman' },
                            ]}
                            value={stampFontFamily}
                            onChange={setStampFontFamily}
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Border width</label>
                            <input type="range" min={0} max={8} value={stampBorderWidth} onChange={(e) => setStampBorderWidth(Number(e.target.value))} className="w-full h-1 rounded-full accent-[#14B8A6] dark:accent-teal-dm" />
                            <span className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 block">{stampBorderWidth}</span>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Opacity</label>
                            <input type="range" min={0.2} max={1} step={0.05} value={stampOpacity} onChange={(e) => setStampOpacity(Number(e.target.value))} className="w-full h-1 rounded-full accent-[#14B8A6] dark:accent-teal-dm" />
                            <span className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 block">{Math.round(stampOpacity * 100)}%</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col">
                        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Preview</p>
                        <div className="relative flex-1 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated p-4 flex items-center justify-center min-h-[200px]">
                          <canvas ref={stampPreviewCanvasRef} width={STAMP_PREVIEW_W} height={STAMP_PREVIEW_H} className="max-w-full h-auto rounded-lg shadow-sm" style={{ maxHeight: '200px' }} />
                          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-lg px-2 py-1.5 ring-1 ring-black/5 dark:ring-white/5">
                            <button type="button" onClick={addStampFromText} title="Create stamp" className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 transition-colors">
                              Create stamp
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  {stampWorkbenchMode === 'image' && (
                    <div className="space-y-4 mt-2">
                      <div>
                        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Stamp name</label>
                        <input type="text" value={stampImageName} onChange={(e) => setStampImageName(e.target.value)} placeholder="e.g. Company logo" className="w-full max-w-sm px-3 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated text-gray-900 dark:text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent" />
                      </div>
                      <div className="inline-flex items-center gap-1 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-sm px-2 py-1.5 ring-1 ring-black/5 dark:ring-white/5">
                        <label className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-hover hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 cursor-pointer transition-colors">
                          <HiOutlineUpload className="w-4 h-4" />
                          Upload
                          <input type="file" accept="image/*" className="sr-only" onChange={handleStampImageUpload} aria-hidden="true" />
                        </label>
                      </div>
                    </div>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-5 pt-5 border-t border-gray-200/60 dark:border-dark-border/60">
                    Use <strong>Draw → Stamp</strong> in the document editor to place a stamp on a PDF. Click <strong>Save profile</strong> at the bottom of this page to keep your stamps.
                  </p>
                </div>
              </section>
              )}

              {activeSettingsSection === 'appearance' && (
              <section id="section-appearance" className="mb-10">
                <div className="flex items-center gap-3 mb-5">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-dark-border text-gray-600 dark:text-gray-300 text-sm font-bold">5</span>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Appearance</h2>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/50 dark:bg-dark-hover/20 p-5">
                  <p className="text-sm app-note mb-4 inline-block">Choose light or dark theme for the app.</p>
                  <div className="flex items-center gap-4 flex-wrap">
                    <ThemeToggle />
                    <span className="text-sm text-gray-600 dark:text-gray-300">
                      {theme === 'dark' ? 'Dark mode' : 'Light mode'}
                    </span>
                    <div className="flex rounded-xl border border-gray-200 dark:border-dark-border p-1 bg-gray-50 dark:bg-dark-hover/50">
                      <button
                        type="button"
                        onClick={() => setTheme('light')}
                        className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${theme === 'light' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border'}`}
                        title="Light theme"
                        aria-label="Light theme"
                      >
                        <HiOutlineSun className="w-4 h-4 shrink-0" />
                        Light
                      </button>
                      <button
                        type="button"
                        onClick={() => setTheme('dark')}
                        className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${theme === 'dark' ? 'bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border'}`}
                        title="Dark theme"
                        aria-label="Dark theme"
                      >
                        <HiOutlineMoon className="w-4 h-4 shrink-0" />
                        Dark
                      </button>
                    </div>
                  </div>
                </div>
              </section>
              )}

              {(activeSettingsSection === 'profile' || activeSettingsSection === 'signature' || activeSettingsSection === 'stamps') && (
              <div className="flex justify-end pt-6 border-t border-gray-200 dark:border-dark-border mt-8">
                <button
                  type="button"
                  onClick={handleProfileSave}
                  disabled={profileSaving}
                  title={profileSaving ? 'Saving…' : 'Save profile'}
                  aria-label={profileSaving ? 'Saving…' : 'Save profile'}
                  className="inline-flex items-center gap-2.5 px-6 py-3 text-sm font-medium text-white dark:text-black bg-[#14B8A6] dark:bg-teal-dm hover:bg-[#0D9488] dark:hover:bg-teal-600 rounded-xl disabled:opacity-50 shadow-sm transition-colors"
                >
                  {profileSaving ? (
                    <svg className="animate-spin w-5 h-5 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  ) : (
                    <HiOutlineSave className="w-5 h-5 shrink-0" />
                  )}
                  {profileSaving ? 'Saving…' : 'Save profile'}
                </button>
                {profileSaved && (
                  <span className="self-center ml-3 text-sm font-medium text-green-600 dark:text-green-400">Saved.</span>
                )}
              </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
};

export default Settings;
