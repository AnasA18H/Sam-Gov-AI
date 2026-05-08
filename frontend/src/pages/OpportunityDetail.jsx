/**
 * Opportunity Details/Results Page
 */
import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI, authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import SendEmailModal from '../components/SendEmailModal';
import DocumentEditorModal from '../components/DocumentEditorModal';
import {
  HiOutlineTrash,
  HiOutlineArrowLeft,
  HiOutlineClock,
  HiOutlineDocumentText,
  HiOutlinePaperClip,
  HiOutlineInformationCircle,
  HiOutlineExclamationCircle,
  HiOutlineMail,
  HiOutlinePhone,
  HiOutlineUser,
  HiOutlineOfficeBuilding,
  HiOutlineCalendar,
  HiOutlineGlobe,
  HiOutlineChevronDown,
  HiOutlineChevronUp,
  HiOutlineChevronRight,
  HiOutlineChevronLeft,
  HiOutlineTag,
  HiOutlineRefresh,
  HiOutlineDownload,
  HiOutlineSparkles,
  HiOutlineCheckCircle,
  HiOutlineCog,
  HiOutlineChartBar,
  HiOutlineX,
  HiOutlineLogout,
  HiOutlineLocationMarker,
  HiOutlineExternalLink,
  HiOutlineSave,
  HiOutlinePencil,
  HiOutlineDotsVertical,
} from 'react-icons/hi';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft } from 'react-icons/fa';
import ThemeToggle from '../components/ThemeToggle';

const OpportunityDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  
  const API_BASE_URL = import.meta.env.VITE_API_URL || '';
  const [opportunity, setOpportunity] = useState(null);
  
  /** For Word docs: get or create the PDF used for editing, then open editor with that PDF. For others, open with the doc. */
  const handleEditDocument = async (doc) => {
    if (!id || !doc) return;
    const oid = parseInt(id, 10);
    if (!isWordDoc(doc)) {
      setDocumentToEdit(doc);
      return;
    }
    setEditWordPreparingForId(doc.id);
    try {
      let pdfDoc = null;
      try {
        const res = await opportunitiesAPI.getEditablePdfDocument(oid, doc.id);
        pdfDoc = res.data;
      } catch (e) {
        if (e?.response?.status === 404) {
          const createRes = await opportunitiesAPI.createPdfFromWord(oid, doc.id);
          pdfDoc = createRes.data;
          const oppRes = await opportunitiesAPI.get(id);
          setOpportunity(oppRes.data);
        } else throw e;
      }
      if (pdfDoc) setDocumentToEdit(pdfDoc);
    } catch (err) {
      console.error('Edit Word document:', err);
      setOpportunity((prev) => prev ? { ...prev, _editWordError: err?.response?.data?.detail || 'Failed to get or create PDF for editing.' } : null);
      setTimeout(() => setOpportunity((p) => (p && p._editWordError ? { ...p, _editWordError: undefined } : p)), 5000);
    } finally {
      setEditWordPreparingForId(null);
    }
  };

  const handleConvertToPdf = async (doc) => {
    if (!id || !doc || !isWordDoc(doc) || convertToPdfDocumentId) return;
    setConvertToPdfDocumentId(doc.id);
    try {
      await opportunitiesAPI.createPdfFromWord(parseInt(id, 10), doc.id);
      const res = await opportunitiesAPI.get(id);
      setOpportunity(res.data);
    } catch (err) {
      console.error('Convert to PDF:', err);
    } finally {
      setConvertToPdfDocumentId(null);
    }
  };

  const handleViewDocument = async (documentId, fileType) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/opportunities/${id}/documents/${documentId}/view?t=${Date.now()}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to fetch document');
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      
      // For PDFs, open in new tab; for others, download
      // Handle both enum values (from backend) and string values
      const typeStr = typeof fileType === 'string' ? fileType.toLowerCase() : String(fileType).toLowerCase();
      if (typeStr === 'pdf' || typeStr.includes('pdf')) {
        window.open(url, '_blank');
        // Clean up URL after a delay (blob URL will be freed when tab closes)
        setTimeout(() => window.URL.revokeObjectURL(url), 100);
      } else {
        const a = document.createElement('a');
        a.href = url;
        
        // Get filename from Content-Disposition header or use document name
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'document';
        if (contentDisposition) {
          const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
          if (filenameMatch) {
            filename = filenameMatch[1];
          }
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (error) {
      console.error('Error viewing document:', error);
      alert('Failed to view document. Please try again.');
    }
  };

  const handleSaveAsDocument = async (doc) => {
    if (!id || !doc) return;
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/opportunities/${id}/documents/${doc.id}/view?t=${Date.now()}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) throw new Error('Failed to fetch document');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.original_file_name || doc.file_name || 'document';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error saving document:', error);
      alert('Failed to save document. Please try again.');
    }
  };

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [emailMenuOpen, setEmailMenuOpen] = useState(false);
  const [expandedClins, setExpandedClins] = useState(new Set());
  const [lookupLinksByClinId, setLookupLinksByClinId] = useState({});
  const [loadingLookupClinId, setLoadingLookupClinId] = useState(null);
  const [sendEmailModal, setSendEmailModal] = useState({ open: false, to: '', subject: '', body: '' });
  const [emailConnection, setEmailConnection] = useState(null);
  const [emailConnectionLoading, setEmailConnectionLoading] = useState(true);
  const [emailConnectionDisconnecting, setEmailConnectionDisconnecting] = useState(false);
  const [searchParams] = useSearchParams();
  const [editingDealerEmail, setEditingDealerEmail] = useState(null); // { clinId, dealerIndex }
  const [draftDealerEmail, setDraftDealerEmail] = useState('');
  const [savingDealerEmail, setSavingDealerEmail] = useState(false);
  const [documentToEdit, setDocumentToEdit] = useState(null);
  const [documentToDelete, setDocumentToDelete] = useState(null);
  const [deleteDocumentLoading, setDeleteDocumentLoading] = useState(false);
  const [convertToPdfDocumentId, setConvertToPdfDocumentId] = useState(null);
  const [editWordPreparingForId, setEditWordPreparingForId] = useState(null);
  const [attachmentMenuDocId, setAttachmentMenuDocId] = useState(null);
  const attachmentMenuRef = useRef(null);

  useEffect(() => {
    if (attachmentMenuDocId == null) return;
    const onMouseDown = (e) => {
      if (attachmentMenuRef.current && !attachmentMenuRef.current.contains(e.target)) {
        setAttachmentMenuDocId(null);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [attachmentMenuDocId]);
  const pollIntervalRef = useRef(null);
  const [dealersManufacturersLoading, setDealersManufacturersLoading] = useState(false);
  const dealersPollIntervalRef = useRef(null);
  const dealersPollStartedAtRef = useRef(null);
  const DEALERS_POLL_MS = 5000;
  const DEALERS_POLL_TIMEOUT_MS = 120000;
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [calendarSyncMessage, setCalendarSyncMessage] = useState('');
  const [rerunLoading, setRerunLoading] = useState({ attachments: false, clins: false, manufacturerDealer: false });

  const handleRerun = async (kind) => {
    if (!id || rerunLoading[kind]) return;
    setRerunLoading((prev) => ({ ...prev, [kind]: true }));
    try {
      if (kind === 'attachments') await opportunitiesAPI.rerunAttachments(id);
      else if (kind === 'clins') await opportunitiesAPI.rerunClins(id);
      else if (kind === 'manufacturerDealer') await opportunitiesAPI.rerunManufacturerDealer(id);
      await fetchOpportunity();
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : detail?.message || 'Re-run failed. Please try again.');
    } finally {
      setRerunLoading((prev) => ({ ...prev, [kind]: false }));
    }
  };

  const handleSyncCalendar = async () => {
    if (!id || syncingCalendar || !emailConnection?.connected) return;
    setSyncingCalendar(true);
    setCalendarSyncMessage('');
    try {
      const res = await opportunitiesAPI.syncCalendar(id);
      const created = res.data?.created ?? 0;
      setCalendarSyncMessage(created > 0 ? `Added ${created} deadline(s) to your calendar.` : 'All deadlines are already in your calendar.');
      await fetchOpportunity();
    } catch (err) {
      setCalendarSyncMessage(err.response?.data?.detail || 'Failed to add to calendar.');
    } finally {
      setSyncingCalendar(false);
    }
  };

  const handleSaveDealerEmail = async (clinId, dealerIndex, email) => {
    const trimmed = (email || '').trim();
    if (!trimmed || !/^[^@]+@[^@]+\.[^@]+$/.test(trimmed)) {
      alert('Please enter a valid email address.');
      return;
    }
    setSavingDealerEmail(true);
    try {
      await opportunitiesAPI.updateDealerEmail(id, clinId, { dealer_index: dealerIndex, sales_contact_email: trimmed });
      setEditingDealerEmail(null);
      setDraftDealerEmail('');
      await fetchOpportunity();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save email.');
    } finally {
      setSavingDealerEmail(false);
    }
  };

  const fetchEmailConnection = async () => {
    try {
      const res = await authAPI.getEmailConnection();
      setEmailConnection(res.data);
    } catch {
      setEmailConnection({ connected: false });
    } finally {
      setEmailConnectionLoading(false);
    }
  };

  const handleDisconnectEmail = async () => {
    if (emailConnectionDisconnecting) return;
    setEmailConnectionDisconnecting(true);
    try {
      await authAPI.disconnectEmailConnection();
      setEmailConnection({ connected: false });
    } catch {
      setEmailConnection(null);
    } finally {
      setEmailConnectionDisconnecting(false);
    }
  };

  const loadClinLookupLinks = async (clinId) => {
    if (!id || loadingLookupClinId === clinId) return;
    setLoadingLookupClinId(clinId);
    try {
      const { data } = await opportunitiesAPI.getClinLookupLinks(id, clinId);
      setLookupLinksByClinId((prev) => ({ ...prev, [clinId]: data.links || [] }));
    } catch (e) {
      setLookupLinksByClinId((prev) => ({ ...prev, [clinId]: [] }));
    } finally {
      setLoadingLookupClinId(null);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  /** Normalize CLIN manufacturer_research to an array. API may return array or single object (legacy). */
  const getClinManufacturerResearchList = (clin) => {
    const m = clin?.manufacturer_research;
    if (m == null) return [];
    let parsed = m;
    if (typeof m === 'string') {
      try { parsed = JSON.parse(m); } catch { return []; }
    }
    if (Array.isArray(parsed)) return parsed;
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed))
      return [{ name: null, official_website: parsed.official_website, sales_contact_email: parsed.sales_contact_email }];
    return [];
  };

  /** Normalize CLIN dealer_research (API may return array, single object, or JSON string). */
  const getClinDealerResearch = (clin) => {
    const d = clin?.dealer_research;
    if (d == null) return [];
    if (Array.isArray(d)) return d;
    if (typeof d === 'string') {
      try { const a = JSON.parse(d); return Array.isArray(a) ? a : (a && typeof a === 'object' ? [a] : []); } catch { return []; }
    }
    if (typeof d === 'object' && d !== null) return [d];
    return [];
  };

  /** True if at least one CLIN has manufacturer or dealer research (for polling until Tavily results arrive). */
  const hasAnyDealerOrManufacturerResearch = (opp) => {
    if (!opp?.clins?.length) return false;
    return opp.clins.some((clin) => {
      const mfr = getClinManufacturerResearchList(clin);
      const dlr = getClinDealerResearch(clin);
      return (mfr.length > 0 && mfr.some((m) => m.official_website || m.sales_contact_email)) || dlr.length > 0;
    });
  };

  useEffect(() => {
    fetchOpportunity();
    fetchEmailConnection();
    // Cleanup polling on unmount
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      if (dealersPollIntervalRef.current) {
        clearInterval(dealersPollIntervalRef.current);
        dealersPollIntervalRef.current = null;
      }
    };
  }, [id]);

  // Refetch email connection when returning from OAuth (e.g. ?email_connected=google)
  useEffect(() => {
    if (searchParams.get('email_connected')) {
      fetchEmailConnection();
    }
  }, [searchParams]);

  const fetchOpportunity = async () => {
    try {
      const response = await opportunitiesAPI.get(id);
      setOpportunity(response.data);
      setError('');
      
      // Poll for updates if status is processing or pending
      if (response.data.status === 'processing' || response.data.status === 'pending') {
        startPolling();
        stopDealersPoll();
      } else {
        stopPolling();
        if (response.data.status === 'completed' && response.data.clins?.length > 0) {
          if (hasAnyDealerOrManufacturerResearch(response.data)) {
            stopDealersPoll();
          } else {
            startDealersPoll();
          }
        } else {
          stopDealersPoll();
        }
      }
    } catch (error) {
      const status = error.response?.status;
      let message = 'Failed to load opportunity';
      if (status === 404) {
        message = 'Opportunity not found. It may have been deleted or you don’t have access.';
      } else if (error.response?.data?.detail != null) {
        const d = error.response.data.detail;
        message = typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e?.msg ?? JSON.stringify(e)).join(', ') : String(d);
      } else if (error.message) {
        message = error.message;
      }
      setError(message);
      stopPolling();
      stopDealersPoll();
    } finally {
      setLoading(false);
    }
  };

  const startPolling = () => {
    // Stop existing polling
    stopPolling();
    
    // Poll every 3 seconds when processing
    pollIntervalRef.current = setInterval(() => {
      opportunitiesAPI.get(id)
        .then(response => {
          setOpportunity(response.data);
          // Stop polling when done (completed or failed)
          // But do one more fetch to ensure we have the latest data
          if (response.data.status !== 'processing' && response.data.status !== 'pending') {
            // Fetch one more time after a short delay to ensure analysis results are loaded
            stopPolling();
            setTimeout(() => {
              opportunitiesAPI.get(id)
                .then(finalResponse => {
                  setOpportunity(finalResponse.data);
                  const data = finalResponse.data;
                  if (data.status === 'completed' && data.clins?.length > 0 && !hasAnyDealerOrManufacturerResearch(data)) {
                    startDealersPoll();
                  } else if (data.status === 'completed' && data.clins?.length > 0 && hasAnyDealerOrManufacturerResearch(data)) {
                    stopDealersPoll();
                  }
                })
                .catch(err => {
                  console.error('Final fetch error:', err);
                });
            }, 2000); // Increased delay to 2 seconds to ensure backend has finished processing
          }
        })
        .catch(err => {
          console.error('Polling error:', err);
          stopPolling();
        });
    }, 3000);
  };

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  const stopDealersPoll = () => {
    if (dealersPollIntervalRef.current) {
      clearInterval(dealersPollIntervalRef.current);
      dealersPollIntervalRef.current = null;
    }
    setDealersManufacturersLoading(false);
  };

  const startDealersPoll = () => {
    if (dealersPollIntervalRef.current) return;
    setDealersManufacturersLoading(true);
    dealersPollStartedAtRef.current = Date.now();
    const doFetch = () => {
      if (Date.now() - dealersPollStartedAtRef.current > DEALERS_POLL_TIMEOUT_MS) {
        stopDealersPoll();
        return;
      }
      opportunitiesAPI.get(id)
        .then((response) => {
          setOpportunity(response.data);
          if (hasAnyDealerOrManufacturerResearch(response.data)) {
            stopDealersPoll();
          }
        })
        .catch(() => stopDealersPoll());
    };
    doFetch(); // immediate first fetch so data auto-loads as soon as it's ready
    dealersPollIntervalRef.current = setInterval(doFetch, DEALERS_POLL_MS);
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    setError('');
    
    try {
      await opportunitiesAPI.delete(id);
      // Navigate to dashboard after successful deletion
      navigate('/dashboard', { state: { message: 'Opportunity deleted successfully' } });
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to delete opportunity. Please try again.');
      setDeleteLoading(false);
      setShowDeleteConfirm(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50 dark:bg-matte flex items-center justify-center">
          <div className="text-sm text-gray-600 dark:text-gray-300">Loading...</div>
        </div>
      </ProtectedRoute>
    );
  }

  if (error) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50 dark:bg-matte">
          <div className="max-w-7xl mx-auto py-8 px-4">
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 px-4 py-3 rounded-md text-sm">
              {error}
            </div>
            <button
              onClick={() => navigate('/dashboard')}
              className="mt-4 inline-flex items-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-dark-hover rounded-md hover:bg-gray-200 dark:hover:bg-dark-border transition-colors"
            >
              <HiOutlineArrowLeft className="w-4 h-4 mr-1.5" />
              Back to Dashboard
            </button>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'N/A';
    const kb = bytes / 1024;
    const mb = kb / 1024;
    if (mb >= 1) return `${mb.toFixed(2)} MB`;
    return `${kb.toFixed(2)} KB`;
  };

  /** Normalize backend file_type (e.g. "pdf", "PDF", "DocumentType.PDF") to lowercase key */
  const normalizeFileType = (fileType) => {
    const s = typeof fileType === 'string' ? fileType : String(fileType ?? '');
    return s.toLowerCase().replace(/^documenttype\./, '').replace(/_/g, '').trim();
  };

  /** Display label for file type; when type is "other", infer from file_name extension so existing data shows correctly */
  const getFileTypeDisplayLabel = (doc) => {
    const typeStr = normalizeFileType(doc?.file_type);
    if (typeStr === 'pdf') return 'PDF';
    if (typeStr === 'word') return 'Word';
    if (typeStr === 'excel') return 'Excel';
    if (typeStr === 'text') return 'Text';
    if (typeStr === 'other' || !typeStr) {
      const name = (doc?.file_name ?? '').toLowerCase();
      if (name.endsWith('.pdf')) return 'PDF';
      if (name.endsWith('.txt') || name.endsWith('.text')) return 'Text';
      if (name.endsWith('.doc') || name.endsWith('.docx')) return 'Word';
      if (name.endsWith('.xls') || name.endsWith('.xlsx')) return 'Excel';
    }
    return 'Other';
  };

  const isWordDoc = (doc) => {
    if (!doc) return false;
    const typeStr = normalizeFileType(doc.file_type);
    if (typeStr === 'word') return true;
    const name = (doc.file_name ?? '').toLowerCase();
    return name.endsWith('.doc') || name.endsWith('.docx');
  };

  const getFileIcon = (fileType, fileName) => {
    const typeStr = normalizeFileType(fileType);
    if (typeStr === 'pdf' || typeStr.includes('pdf')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-red-600" />;
    }
    if (typeStr === 'word' || typeStr.includes('word')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-blue-600" />;
    }
    if (typeStr === 'excel' || typeStr.includes('excel')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-green-600" />;
    }
    if (typeStr === 'text' || typeStr.includes('text')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-gray-600" />;
    }
    // Fallback from file name
    const name = (fileName ?? '').toLowerCase();
    if (name.endsWith('.pdf')) return <HiOutlineDocumentText className="w-5 h-5 text-red-600" />;
    if (name.endsWith('.txt') || name.endsWith('.text')) return <HiOutlineDocumentText className="w-5 h-5 text-gray-600" />;
    return <HiOutlinePaperClip className="w-5 h-5 text-gray-600" />;
  };

  const isNetworkError = (msg) => {
    if (!msg || typeof msg !== 'string') return false;
    const s = msg.toLowerCase();
    return (
      s.includes('err_name_not_resolved') ||
      s.includes('net::err_') ||
      s.includes('econnrefused') ||
      s.includes('enotfound') ||
      s.includes('etimedout') ||
      s.includes('network') && (s.includes('failed') || s.includes('error')) ||
      s.includes('fetch failed') ||
      s.includes('timeout') && s.includes('load')
    );
  };

  /** True if the CLIN "manufacturer" name looks like a government agency (buyer). We do not show agency contact as "manufacturer research". */
  const isLikelyAgencyNotManufacturer = (name) => {
    if (!name || typeof name !== 'string') return false;
    const s = name.toLowerCase();
    return /bureau of|department of|^gsa\b|^dod\b|agency|federal |government|u\.s\. |united states /.test(s) || /\b(bep|doj|dod|gsa|va|dhs|doe|usda)\b/.test(s);
  };

  /** Subject and body for quote emails (sent from app). */
  const getQuoteSubject = () =>
    opportunity?.title ? `Quote request: ${opportunity.title}` : 'Quote request - government opportunity';
  const getQuoteBody = () =>
    opportunity?.notice_id
      ? `I am inquiring about a quote for the following opportunity (Notice ID: ${opportunity.notice_id}).\n\nPlease provide pricing and availability.\n\nThank you.`
      : '';

  const openSendEmail = (toEmail) => {
    if (!toEmail) return;
    setSendEmailModal({
      open: true,
      to: toEmail,
      subject: getQuoteSubject(),
      body: getQuoteBody(),
    });
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 dark:bg-matte">
        {/* Navigation */}
        <nav className="bg-white dark:bg-dark-surface border-b border-gray-200 dark:border-dark-border shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              {/* Left: logo + back */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="flex items-center gap-2.5 rounded-xl py-1.5 pr-2 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
                >
                  <div className="flex flex-col space-y-0.5">
                    <div className="h-0.5 w-6 bg-green-500 rounded" />
                    <div className="h-0.5 w-6 bg-yellow-400 rounded" />
                    <div className="h-0.5 w-6 bg-blue-500 rounded" />
                  </div>
                  <span className="text-xl font-semibold text-[#2D1B3D] dark:text-white tracking-tight">Gov OPs AI</span>
                </button>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-gray-100 dark:hover:bg-dark-hover rounded-xl transition-colors"
                  title="Back to Dashboard"
                  aria-label="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
              </div>

              {/* Right: theme, email, delete, user */}
              <div className="flex items-center gap-2 sm:gap-3">
                <ThemeToggle />
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="p-2.5 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deleteLoading}
                  title={deleteLoading ? 'Deleting...' : 'Delete opportunity'}
                  aria-label={deleteLoading ? 'Deleting...' : 'Delete opportunity'}
                >
                  {deleteLoading ? (
                    <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  ) : (
                    <HiOutlineTrash className="w-5 h-5" />
                  )}
                </button>

                <div className="relative flex items-center">
                  <button
                    type="button"
                    onClick={() => { setEmailMenuOpen((v) => !v); setUserMenuOpen(false); }}
                    className={`min-h-[2.5rem] min-w-[7.5rem] sm:min-w-[8.5rem] flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl border bg-transparent text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-black ${
                      emailConnection?.connected
                        ? 'border-[#14B8A6]/50 dark:border-teal-dm/50 text-[#0D9488] dark:text-teal-dm'
                        : 'border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 hover:border-[#14B8A6]/40 dark:hover:border-teal-dm/40 hover:text-[#0D9488] dark:hover:text-teal-dm'
                    }`}
                    title={emailConnection?.connected ? `${emailConnection.sender_email || ''} — Disconnect or switch` : 'Connect Gmail or Outlook'}
                    aria-label={emailConnection?.connected ? 'Email connected — open menu to disconnect or switch' : 'Connect email (Gmail or Outlook)'}
                  >
                    <HiOutlineMail className="w-4 h-4 shrink-0" />
                    {emailConnectionLoading ? (
                      <span className="animate-pulse">…</span>
                    ) : emailConnection?.connected ? (
                      <>
                        <span className="hidden sm:inline whitespace-nowrap">{emailConnection.provider === 'google' ? 'Gmail' : 'Outlook'}</span>
                        {emailMenuOpen ? <HiOutlineChevronUp className="w-4 h-4 shrink-0" /> : <HiOutlineChevronDown className="w-4 h-4 shrink-0" />}
                      </>
                    ) : (
                      <>
                        <span className="hidden sm:inline">Connect</span>
                        {emailMenuOpen ? <HiOutlineChevronUp className="w-4 h-4 shrink-0" /> : <HiOutlineChevronDown className="w-4 h-4 shrink-0" />}
                      </>
                    )}
                  </button>
                  {emailMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setEmailMenuOpen(false)} aria-hidden />
                      <div className="absolute right-0 top-full mt-1.5 w-56 bg-white dark:bg-dark-elevated rounded-lg shadow-lg border border-gray-200 dark:border-dark-border py-1 z-20">
                        {emailConnectionLoading ? (
                          <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-300">Loading…</div>
                        ) : emailConnection?.connected ? (
                          <>
                            <div className="px-3 py-2 border-b border-gray-100 dark:border-dark-border">
                              <p className="text-xs text-gray-500 dark:text-gray-300">Account</p>
                              <p className="text-xs font-medium text-gray-900 dark:text-white truncate" title={emailConnection.sender_email}>{emailConnection.sender_email || '—'}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => { setEmailMenuOpen(false); handleDisconnectEmail(); }}
                              disabled={emailConnectionDisconnecting}
                              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                            >
                              <HiOutlineLogout className="w-3.5 h-3.5" />
                              {emailConnectionDisconnecting ? 'Disconnecting…' : 'Disconnect'}
                            </button>
                            <button
                              type="button"
                              onClick={() => { setEmailMenuOpen(false); window.location.href = authAPI.connectGoogleUrl(); }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
                            >
                              <SiGoogle className="w-3.5 h-3.5" />
                              {emailConnection?.provider === 'google' ? 'Reconnect Gmail' : 'Switch to Gmail'}
                            </button>
                            <button
                              type="button"
                              onClick={() => { setEmailMenuOpen(false); window.location.href = authAPI.connectMicrosoftUrl(); }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
                            >
                              <FaMicrosoft className="w-3.5 h-3.5" aria-hidden />
                              {emailConnection?.provider === 'microsoft' ? 'Reconnect Outlook' : 'Switch to Outlook'}
                            </button>
                          </>
                        ) : (
                          <>
                            <p className="px-3 py-2 text-xs text-gray-500 dark:text-gray-300">Send emails & add to calendar</p>
                            <a
                              href={authAPI.connectGoogleUrl()}
                              className="flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
                            >
                              <SiGoogle className="w-3.5 h-3.5" />
                              Connect Gmail
                            </a>
                            <a
                              href={authAPI.connectMicrosoftUrl()}
                              className="flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover"
                            >
                              <FaMicrosoft className="w-3.5 h-3.5" aria-hidden />
                              Connect Outlook
                            </a>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>

                {/* User account — same as Dashboard */}
                <div className="relative">
                  <button
                    onClick={() => { setUserMenuOpen(!userMenuOpen); setEmailMenuOpen(false); }}
                    className="flex items-center gap-3 pl-1 pr-2.5 py-1.5 rounded-xl hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6]/30 dark:focus:ring-teal-dm/30 focus:ring-offset-2 dark:focus:ring-offset-black"
                    aria-expanded={userMenuOpen}
                    aria-haspopup="true"
                  >
                    <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black text-sm font-semibold shrink-0">
                      {user?.full_name ? user.full_name.trim().charAt(0).toUpperCase() : user?.email?.trim().charAt(0).toUpperCase() || 'U'}
                    </div>
                    <div className="hidden md:block text-left min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-white truncate max-w-[160px]">
                        {user?.full_name || 'User'}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[160px]">
                        {user?.email}
                      </div>
                    </div>
                    {userMenuOpen ? (
                      <HiOutlineChevronUp className="w-4 h-4 text-gray-500 dark:text-gray-400 shrink-0" />
                    ) : (
                      <HiOutlineChevronDown className="w-4 h-4 text-gray-500 dark:text-gray-400 shrink-0" />
                    )}
                  </button>

                  {userMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} aria-hidden="true" />
                      <div className="absolute right-0 top-full mt-2 w-64 bg-white dark:bg-dark-elevated rounded-xl shadow-xl border border-gray-200 dark:border-dark-border py-2 z-20">
                        <div className="px-4 py-3 border-b border-gray-100 dark:border-dark-border">
                          <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                            {user?.full_name || 'User'}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                            {user?.email}
                          </div>
                        </div>
                        <div className="py-1">
                          <button onClick={() => { setUserMenuOpen(false); navigate('/dashboard'); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors text-left">
                            <HiOutlineArrowLeft className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                            <span>Dashboard</span>
                          </button>
                          <button onClick={() => { setUserMenuOpen(false); navigate('/profile'); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors text-left">
                            <HiOutlineUser className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                            <span>Profile</span>
                          </button>
                          <button onClick={() => { setUserMenuOpen(false); navigate('/settings'); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors text-left">
                            <HiOutlineCog className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                            <span>Settings</span>
                          </button>
                        </div>
                        <div className="border-t border-gray-100 dark:border-dark-border my-1" />
                        <div className="py-1">
                          <button onClick={() => { setUserMenuOpen(false); handleLogout(); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors text-left">
                            <HiOutlineLogout className="w-5 h-5" />
                            <span>Logout</span>
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <div className="relative">
          {/* Floating Left Side Utilities Panel */}
          <div className={`fixed left-6 top-6 bottom-6 z-40 bg-white dark:bg-dark-elevated border-2 border-[#14B8A6] dark:border-teal-dm rounded-xl shadow-lg transition-all duration-300 ease-in-out overflow-hidden flex flex-col ${
            sidebarOpen ? 'w-80' : 'w-20'
          }`}>
            {/* Toggle Button / Header */}
            <div 
              className="bg-[#14B8A6] dark:bg-teal-dm h-14 flex items-center justify-between cursor-pointer hover:bg-[#0D9488] dark:hover:bg-teal-400 transition-colors rounded-t-lg flex-shrink-0 shadow-sm"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              <div className="flex items-center space-x-2 px-3 min-w-0">
                <HiOutlineCog className="w-5 h-5 text-white dark:text-black flex-shrink-0" />
                {sidebarOpen && (
                  <h3 className="text-sm font-semibold text-white dark:text-black transition-opacity duration-300 whitespace-nowrap">Utilities</h3>
                )}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSidebarOpen(!sidebarOpen);
                }}
                className="p-2 text-white dark:text-black hover:bg-[#0D9488] dark:hover:bg-teal-400 rounded-md transition-colors flex-shrink-0 mr-1 focus:outline-none focus:ring-2 focus:ring-white dark:focus:ring-gray-900 focus:ring-offset-2 focus:ring-offset-[#14B8A6] dark:focus:ring-offset-teal-dm"
                    title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
                    aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
              >
                {sidebarOpen ? (
                  <HiOutlineChevronLeft className="w-5 h-5 transition-transform duration-300" />
                ) : (
                  <HiOutlineChevronRight className="w-5 h-5 transition-transform duration-300" />
                )}
              </button>
            </div>

            {/* Collapsed View - Icon Buttons */}
            {!sidebarOpen && (
              <div className="flex-1 flex flex-col items-center justify-start py-4 space-y-2 overflow-y-auto">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                  title="Back to Dashboard"
                  aria-label="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={fetchOpportunity}
                  disabled={loading}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                  title="Refresh opportunity"
                  aria-label="Refresh opportunity"
                >
                  <HiOutlineRefresh className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <div className="h-px w-8 bg-gray-200 dark:bg-gray-600 my-1"></div>
                {opportunity?.clins?.some((clin) => {
                  const mfr = getClinManufacturerResearchList(clin);
                  const dlr = getClinDealerResearch(clin);
                  return (mfr.some((m) => m.sales_contact_email) || dlr.some((d) => d.sales_contact_email));
                }) && (
                  <button
                    onClick={() => navigate(`/opportunities/${id}/quote-emails`)}
                    className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    title="View quote emails"
                    aria-label="View quote emails"
                  >
                    <HiOutlineMail className="w-5 h-5" />
                  </button>
                )}
                {emailConnection?.connected && opportunity?.deadlines?.length > 0 && (
                  <button
                    onClick={handleSyncCalendar}
                    disabled={syncingCalendar}
                    className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    title="Add to Calendar"
                    aria-label="Add opportunity to calendar"
                  >
                    <HiOutlineCalendar className={`w-5 h-5 ${syncingCalendar ? 'animate-spin' : ''}`} />
                  </button>
                )}
                <div className="h-px w-8 bg-gray-200 dark:bg-gray-600 my-1"></div>
                <button
                  onClick={() => navigate('/profile')}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                  title="Profile"
                  aria-label="Open profile"
                >
                  <HiOutlineUser className="w-5 h-5" />
                </button>
                <button
                  onClick={() => navigate('/settings')}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                  title="Settings"
                  aria-label="Open settings"
                >
                  <HiOutlineCog className="w-5 h-5" />
                </button>
                <div className="h-px w-8 bg-gray-200 dark:bg-gray-600 my-1"></div>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={deleteLoading}
                  className="p-2.5 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                  title="Delete opportunity"
                  aria-label="Delete opportunity"
                >
                  <HiOutlineTrash className="w-5 h-5" />
                </button>
              </div>
            )}

            {/* Expanded View - Full Content */}
            <div className={`flex-1 overflow-hidden transition-all duration-300 ease-in-out ${
              sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none absolute inset-0'
            }`}>
              <div className="px-4 py-5 space-y-6 h-full overflow-y-auto scrollbar-hidden">
                {/* Quick Actions */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3">Quick Actions</h4>
                  <div className="space-y-2.5">
                    <button
                      onClick={() => navigate('/dashboard')}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border hover:border-gray-400 dark:hover:border-gray-500 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    >
                      <HiOutlineArrowLeft className="w-4 h-4 mr-2" />
                      Back to Dashboard
                    </button>
                    <button
                      onClick={fetchOpportunity}
                      disabled={loading}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border hover:border-gray-400 dark:hover:border-gray-500 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    >
                      <HiOutlineRefresh className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                      Refresh
                    </button>
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      disabled={deleteLoading}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                    >
                      <HiOutlineTrash className="w-4 h-4 mr-2" />
                      Delete Opportunity
                    </button>
                  </div>
                </div>

                {/* Email & calendar in utility bar */}
                {opportunity && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineMail className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Email & calendar
                    </h4>
                    <div className="space-y-2.5">
                    {opportunity.clins?.some((clin) => {
                        const mfr = getClinManufacturerResearchList(clin);
                        const dlr = getClinDealerResearch(clin);
                        return (mfr.some((m) => m.sales_contact_email) || dlr.some((d) => d.sales_contact_email));
                      }) && (
                        <button
                          onClick={() => navigate(`/opportunities/${id}/quote-emails`)}
                          className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 rounded-lg hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/30 border border-[#14B8A6]/40 dark:border-teal-dm/40 transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                        >
                          <HiOutlineMail className="w-4 h-4 mr-2" />
                          View quote emails
                        </button>
                      )}
                      {emailConnection?.connected && opportunity.deadlines?.length > 0 && (
                        <button
                          onClick={handleSyncCalendar}
                          disabled={syncingCalendar}
                          className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 rounded-lg hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/30 border border-[#14B8A6]/40 dark:border-teal-dm/40 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                        >
                          <HiOutlineCalendar className={`w-4 h-4 mr-2 ${syncingCalendar ? 'animate-spin' : ''}`} />
                          {syncingCalendar ? 'Adding…' : 'Add to Calendar'}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Re-run options: run only one part without affecting the rest */}
                {opportunity && opportunity.status === 'completed' && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineRefresh className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Re-run options
                    </h4>
                    <p className="text-xs app-note mb-2 inline-block">Re-run only one part; the rest stays unchanged.</p>
                    <div className="space-y-2">
                      <button
                        onClick={() => handleRerun('attachments')}
                        disabled={rerunLoading.attachments}
                        className="w-full flex items-center justify-center px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border disabled:opacity-50 transition-colors"
                        title="Re-extract text and re-classify documents. Does not change CLINs or manufacturer/dealer."
                        aria-label="Re-run attachments: re-extract text and re-classify documents"
                      >
                        {rerunLoading.attachments ? <span className="animate-spin mr-1.5">⟳</span> : <HiOutlinePaperClip className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />}
                        Re-run attachments
                      </button>
                      <button
                        onClick={() => handleRerun('clins')}
                        disabled={rerunLoading.clins}
                        className="w-full flex items-center justify-center px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border disabled:opacity-50 transition-colors"
                        title="Re-extract CLINs and deadlines from documents. Does not change documents or manufacturer/dealer."
                        aria-label="Re-run CLINs: re-extract CLINs and deadlines from documents"
                      >
                        {rerunLoading.clins ? <span className="animate-spin mr-1.5">⟳</span> : <HiOutlineDocumentText className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />}
                        Re-run CLINs
                      </button>
                      <button
                        onClick={() => handleRerun('manufacturerDealer')}
                        disabled={rerunLoading.manufacturerDealer}
                        className="w-full flex items-center justify-center px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border disabled:opacity-50 transition-colors"
                        title="Re-run manufacturer and dealer research (Tavily). Does not change documents or CLINs."
                        aria-label="Re-run manufacturer and dealer research"
                      >
                        {rerunLoading.manufacturerDealer ? <span className="animate-spin mr-1.5">⟳</span> : <HiOutlineGlobe className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />}
                        Re-run manufacturer & dealer
                      </button>
                    </div>
                  </div>
                )}

                {/* Summary */}
                {opportunity && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineChartBar className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Summary
                    </h4>
                    <div className="bg-gray-50 dark:bg-dark-hover rounded-lg border border-gray-200 dark:border-dark-border p-4 space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Type</span>
                        <span className={`text-xs font-bold px-2.5 py-1 rounded capitalize ${
                          opportunity.solicitation_type === 'product' ? 'bg-[#14B8A6]/20 dark:bg-teal-dm/20 text-[#0D9488] dark:text-teal-dm' :
                          opportunity.solicitation_type === 'service' ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200' :
                          opportunity.solicitation_type === 'both' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200' :
                          'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
                        }`}>
                          {opportunity.solicitation_type === 'unknown' ? '—' : opportunity.solicitation_type}
                        </span>
                      </div>
                      <div className="h-px bg-gray-200 dark:bg-gray-600"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Status</span>
                        <span className={`text-xs font-bold px-2 py-1 rounded ${
                          opportunity.status === 'completed' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-200' :
                          opportunity.status === 'processing' ? 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-200' :
                          opportunity.status === 'failed' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-200' :
                          'bg-gray-100 dark:bg-gray-600 text-gray-700 dark:text-gray-300'
                        }`}>
                          {opportunity.status}
                        </span>
                      </div>
                      <div className="h-px bg-gray-200 dark:bg-gray-600"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">CLINs</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{opportunity.clins?.length || 0}</span>
                      </div>
                      <div className="h-px bg-gray-200 dark:bg-gray-600"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Documents</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{opportunity.documents?.length || 0}</span>
                      </div>
                      <div className="h-px bg-gray-200 dark:bg-gray-600"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Deadlines</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{opportunity.deadlines?.length || 0}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Account */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                    <HiOutlineUser className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                    Account
                  </h4>
                  <div className="space-y-2.5">
                    <button
                      onClick={() => navigate('/profile')}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 rounded-lg hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/30 border border-[#14B8A6]/40 dark:border-teal-dm/40 transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    >
                      <HiOutlineUser className="w-4 h-4 mr-2" />
                      Profile
                    </button>
                    <button
                      onClick={() => navigate('/settings')}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                    >
                      <HiOutlineCog className="w-4 h-4 mr-2" />
                      Settings
                    </button>
                  </div>
                </div>

                {/* Navigation */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3">Navigation</h4>
                  <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-dark-hover rounded-lg p-3 border border-gray-200 dark:border-dark-border">
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700 dark:text-gray-300">Scroll:</span> View all sections of this opportunity.
                    </p>
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700 dark:text-gray-300">CLINs:</span> View extracted contract line items.
                    </p>
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700 dark:text-gray-300">Documents:</span> Access all downloaded files.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

        {/* Wrapper with left padding so content is not under the fixed utility bar (left-6 + w-20 collapsed, left-6 + w-80 expanded) */}
        <div className={`min-w-0 transition-[padding] duration-300 ease-in-out ${sidebarOpen ? 'pl-[352px]' : 'pl-[112px]'}`}>
        <main className="w-full max-w-[1600px] mx-auto py-4 sm:px-6 lg:px-8">
          <div className="px-4 py-4 sm:px-0 w-full">
            {/* Title Section - green background; light mode: white text, dark mode: green bg + dark text */}
            <div className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border shadow-sm mb-6 overflow-hidden w-full">
              <div 
                className="relative z-10 rounded-t-xl shadow-md px-4 py-4 text-white dark:text-black"
                style={{
                  backgroundImage: 'repeating-linear-gradient(-55deg, transparent, transparent 8px, rgba(255,255,255,0.06) 8px, rgba(255,255,255,0.06) 9px), repeating-linear-gradient(35deg, transparent, transparent 8px, rgba(255,255,255,0.04) 8px, rgba(255,255,255,0.04) 9px), linear-gradient(to right, #14B8A6, #0D9488)',
                }}
              >
                <div className="relative flex justify-between items-start flex-wrap gap-3">
                  <div className="flex-1 min-w-0">
                    <div className={opportunity.title && opportunity.title.length > 60 ? 'max-h-[3.6rem] overflow-hidden' : ''}>
                      <h1 className="text-xl font-semibold text-white dark:text-black mb-1.5">
                        {opportunity.title || (opportunity.status === 'processing' ? 'Analyzing Opportunity...' : 'Untitled Opportunity')}
                      </h1>
                    </div>
                    {opportunity.sam_gov_url && (
                      <a
                        href={opportunity.sam_gov_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-white/90 dark:text-gray-800 hover:text-white dark:hover:text-gray-900 inline-flex items-center gap-1 mt-1"
                      >
                        <HiOutlineExternalLink className="w-3.5 h-3.5" />
                        <span className="truncate max-w-[280px] sm:max-w-none">{opportunity.sam_gov_url}</span>
                      </a>
                    )}
                    {opportunity.notice_id && (
                      <div className="flex items-center space-x-2 text-xs text-white/90 dark:text-gray-800 mt-1">
                        <HiOutlineInformationCircle className="w-4 h-4 flex-shrink-0" />
                        <span>Notice ID: <span className="font-mono font-medium">{opportunity.notice_id}</span></span>
                      </div>
                    )}
                  </div>
                  <span className={`px-3 py-1.5 rounded-lg text-xs font-medium flex-shrink-0 ${
                    opportunity.status === 'completed' ? 'bg-white/25 dark:bg-black/20 text-white dark:text-black' :
                    opportunity.status === 'processing' ? 'bg-yellow-400/90 dark:bg-amber-400/80 text-yellow-900 dark:text-amber-900 animate-pulse' :
                    opportunity.status === 'failed' ? 'bg-red-400/90 dark:bg-red-800/80 text-white dark:text-red-100' :
                    'bg-white/20 dark:bg-black/20 text-white dark:text-black'
                  }`}>
                    {opportunity.status}
                  </span>
                </div>
                </div>

              {/* Contact info - directly under title (one block: title over contact) */}
              {(opportunity.agency || opportunity.primary_contact || opportunity.alternative_contact) && (
                <div className="bg-white dark:bg-dark-elevated px-4 pt-4 pb-3 rounded-b-xl border-t border-gray-200 dark:border-dark-border overflow-visible">
                  <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1 mb-1">
                    <HiOutlineUser className="w-3.5 h-3.5" /> Contact
                  </div>
                  <p className="text-xs app-note mb-2 inline-block">Agency and point of contact from SAM.gov.</p>
                  {(opportunity.primary_contact || opportunity.alternative_contact) && (
                  <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-2">
                    {opportunity.primary_contact && (
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        {opportunity.primary_contact.name && <span className="text-gray-900 dark:text-white font-medium">{opportunity.primary_contact.name}</span>}
                        {opportunity.primary_contact.email && (
                          <a href={`mailto:${opportunity.primary_contact.email}`} className="text-[#0D9488] dark:text-teal-dm hover:text-[#14B8A6] dark:hover:text-teal-400 inline-flex items-center gap-1">
                            <HiOutlineMail className="w-3.5 h-3.5" />
                            <span className="truncate max-w-[200px]">{opportunity.primary_contact.email}</span>
                          </a>
                        )}
                        {opportunity.primary_contact.phone && (
                          <a href={`tel:${opportunity.primary_contact.phone}`} className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 inline-flex items-center gap-1">
                            <HiOutlinePhone className="w-3.5 h-3.5" />
                            {opportunity.primary_contact.phone}
                          </a>
                        )}
                      </div>
                    )}
                    {opportunity.alternative_contact && (
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        {opportunity.alternative_contact.name && <span className="text-gray-600 dark:text-gray-300 text-xs">Alt: {opportunity.alternative_contact.name}</span>}
                        {opportunity.alternative_contact.email && (
                          <a href={`mailto:${opportunity.alternative_contact.email}`} className="text-[#0D9488] dark:text-teal-dm hover:text-[#14B8A6] dark:hover:text-teal-400 text-xs inline-flex items-center gap-1">
                            <HiOutlineMail className="w-3 h-3" />
                            <span className="truncate max-w-[180px]">{opportunity.alternative_contact.email}</span>
                          </a>
                        )}
                        {opportunity.alternative_contact.phone && (
                          <a href={`tel:${opportunity.alternative_contact.phone}`} className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 text-xs inline-flex items-center gap-1">
                            <HiOutlinePhone className="w-3 h-3" />
                            {opportunity.alternative_contact.phone}
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                  )}
                  {opportunity.agency && (
                    <div className="w-full min-w-0">
                      <div className="flex items-start gap-2 text-xs text-gray-500 w-full" style={{ fontFamily: 'Arial, sans-serif' }}>
                        <HiOutlineOfficeBuilding className="w-3.5 h-3.5 text-gray-500 flex-shrink-0 mt-0.5" />
                        <span className="flex-1 min-w-0 break-words overflow-visible" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                          {opportunity.agency}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

            </div>

              {/* Status Messages */}
              <div className="px-4 py-3 space-y-3">
                {opportunity.status === 'pending' && (
                  <div className="bg-white dark:bg-dark-elevated rounded-lg border-2 border-gray-300 dark:border-dark-border shadow-sm p-4 animate-fade-in">
                    <div className="flex items-start space-x-3">
                      <HiOutlineExclamationCircle className="w-5 h-5 text-gray-500 dark:text-gray-400 flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Waiting to Start Analysis</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                          Your request is queued and will begin processing shortly.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {opportunity.status === 'processing' && (
                  <div className="bg-white dark:bg-dark-elevated rounded-lg border-2 border-blue-400 dark:border-blue-500 shadow-sm p-4 animate-fade-in">
                    <div className="flex items-start space-x-3">
                      <div className="relative flex-shrink-0">
                        <HiOutlineSparkles className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                      </div>
                      <div className="flex-1 space-y-4">
                        <div>
                          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Analysis in Progress</h3>
                          
                          {/* Progress Steps */}
                          <div className="space-y-3">
                            {/* Step 1: Scraping SAM.gov Data */}
                            <div className="flex items-start space-x-3 animate-fade-in animate-delay-0">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.title || opportunity.description || opportunity.deadlines?.length > 0
                                  ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400' 
                                  : 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                              }`}>
                                {opportunity.title || opportunity.description || opportunity.deadlines?.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (
                                  <HiOutlineGlobe className="w-4 h-4" />
                                )}
                            </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  Scraping SAM.gov Data
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                  {opportunity.title || opportunity.description || opportunity.deadlines?.length > 0
                                    ? (() => {
                                        const parts = [];
                                        if (opportunity.title) parts.push('Title');
                                        if (opportunity.description) parts.push('Description');
                                        if (opportunity.deadlines?.length > 0) parts.push(`${opportunity.deadlines.length} Deadline(s)`);
                                        if (opportunity.primary_contact || opportunity.alternative_contact) parts.push('Contact Info');
                                        return `Extracted: ${parts.join(', ')}`;
                                      })()
                                    : 'Extracting title, description, deadlines, and contacts...'}
                                </p>
                            </div>
                            </div>

                            {/* Step 2: Downloading Documents */}
                            <div className="flex items-start space-x-3 animate-fade-in animate-delay-75">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.documents && opportunity.documents.length > 0 
                                  ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400' 
                                  : (opportunity.title || opportunity.description) && opportunity.status === 'processing'
                                    ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                                    : 'bg-gray-100 dark:bg-gray-600 text-gray-400 dark:text-gray-500'
                              }`}>
                                {opportunity.documents && opportunity.documents.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (opportunity.title || opportunity.description) && opportunity.status === 'processing' ? (
                                  <HiOutlineDownload className="w-4 h-4" />
                                ) : (
                                  <HiOutlineDownload className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 || ((opportunity.title || opportunity.description) && opportunity.status === 'processing')
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-300'
                                }`}>
                                  Downloading Documents
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                  {opportunity.documents && opportunity.documents.length > 0
                                    ? `${opportunity.documents.length} document(s) downloaded`
                                    : (opportunity.title || opportunity.description) && opportunity.status === 'processing'
                                      ? 'Downloading attachments from SAM.gov...'
                                      : 'Waiting for data scraping...'}
                                </p>
                                {opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && (
                                  <div className="mt-1.5">
                                    <div className="flex flex-wrap gap-1">
                                      {opportunity.documents.slice(0, 3).map((doc, idx) => (
                                        <span key={doc.id || idx} className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded">
                                          {doc.file_name && doc.file_name.length > 20 ? doc.file_name.substring(0, 20) + '...' : (doc.file_name || 'Document')}
                                        </span>
                                      ))}
                                      {opportunity.documents.length > 3 && (
                                        <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded">
                                          +{opportunity.documents.length - 3} more
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Step 3: Extracting Text */}
                            <div className="flex items-start space-x-3 animate-fade-in animate-delay-150">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && !opportunity.clins
                                  ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                                  : opportunity.clins && opportunity.clins.length > 0
                                    ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400'
                                    : 'bg-gray-100 dark:bg-gray-600 text-gray-400 dark:text-gray-500'
                              }`}>
                                {opportunity.clins && opportunity.clins.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && !opportunity.clins ? (
                                  <HiOutlineDocumentText className="w-4 h-4" />
                                ) : (
                                  <HiOutlineDocumentText className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-300'
                                }`}>
                                  Extracting Text from Documents
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                  {opportunity.clins && opportunity.clins.length > 0
                                    ? 'Text extraction complete'
                                    : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                      ? (() => {
                                          // Check if analysis is enabled
                                          const analysisEnabled = opportunity.enable_document_analysis === 'true' || opportunity.enable_document_analysis === true;
                                          if (!analysisEnabled) {
                                            return 'Document analysis disabled - skipping text extraction';
                                          }
                                          return `Extracting text from ${opportunity.documents.length} document(s)...`;
                                        })()
                                      : 'Waiting for documents...'}
                                </p>
                              </div>
                            </div>

                            {/* Step 4: Analyzing CLINs */}
                            <div className="flex items-start space-x-3 animate-fade-in animate-delay-225">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.clins && opportunity.clins.length > 0
                                  ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400'
                                  : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                                    : 'bg-gray-100 dark:bg-gray-600 text-gray-400 dark:text-gray-500'
                              }`}>
                                {opportunity.clins && opportunity.clins.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' ? (
                                  <HiOutlineSparkles className="w-4 h-4" />
                                ) : (
                                  <HiOutlineSparkles className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-300'
                                }`}>
                                  Analyzing CLINs with AI
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                  {opportunity.clins && opportunity.clins.length > 0
                                    ? `Found ${opportunity.clins.length} CLIN(s)`
                                    : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                      ? (() => {
                                          // Check if CLIN extraction is enabled
                                          const clinEnabled = opportunity.enable_clin_extraction === 'true' || opportunity.enable_clin_extraction === true;
                                          const analysisEnabled = opportunity.enable_document_analysis === 'true' || opportunity.enable_document_analysis === true;
                                          
                                          if (!analysisEnabled) {
                                            return 'Document analysis disabled - CLIN extraction skipped';
                                          }
                                          if (!clinEnabled) {
                                            return 'CLIN extraction disabled';
                                          }
                                          return `Processing ${opportunity.documents.length} document(s) sequentially using AI...`;
                                        })()
                                      : 'Waiting for text extraction...'}
                                </p>
                                {opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && !opportunity.clins && (
                                  <div className="mt-2">
                                    <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-1.5">
                                      <div 
                                        className="bg-blue-600 dark:bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                                        style={{ width: '75%' }}
                                      ></div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Step 5: Complete */}
                            <div className="flex items-start space-x-3 animate-fade-in animate-delay-300">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.status === 'completed'
                                  ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400'
                                  : 'bg-gray-100 dark:bg-gray-600 text-gray-400 dark:text-gray-500'
                              }`}>
                                {opportunity.status === 'completed' ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (
                                  <HiOutlineCheckCircle className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.status === 'completed'
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-300'
                                }`}>
                                  Analysis Complete
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                  {opportunity.status === 'completed'
                                    ? (() => {
                                        const parts = [];
                                        if (opportunity.documents?.length > 0) parts.push(`${opportunity.documents.length} document(s)`);
                                        if (opportunity.clins?.length > 0) parts.push(`${opportunity.clins.length} CLIN(s)`);
                                        if (opportunity.deadlines?.length > 0) parts.push(`${opportunity.deadlines.length} deadline(s)`);
                                        return parts.length > 0 ? `Complete: ${parts.join(', ')} extracted` : 'All data extracted and ready!';
                                      })()
                                    : opportunity.status === 'processing'
                                      ? 'Finalizing results...'
                                      : 'Waiting for analysis to complete...'}
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div className="pt-2 border-t border-gray-200 dark:border-dark-border">
                          <div className="flex items-center space-x-2 text-xs text-gray-500 dark:text-gray-300">
                            <HiOutlineClock className="w-3.5 h-3.5" />
                            <span>This may take a few moments. Please wait...</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {opportunity.error_message && (
                  <div className="flex items-start space-x-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3 animate-fade-in">
                    <HiOutlineExclamationCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-red-800 dark:text-red-200">
                        {isNetworkError(opportunity.error_message) ? 'Connection problem' : 'Error:'}
                      </p>
                      {isNetworkError(opportunity.error_message) ? (
                        <>
                          <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                            Please check your internet connection and try again. If the problem continues, SAM.gov may be temporarily unavailable.
                          </p>
                          <button
                            type="button"
                            onClick={fetchOpportunity}
                            disabled={loading}
                            className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-800 dark:text-red-200 bg-white dark:bg-dark-hover border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-black disabled:opacity-50"
                          >
                            <HiOutlineRefresh className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                            Retry
                          </button>
                          <p className="text-xs text-red-600/80 dark:text-red-400/80 mt-2 font-mono truncate max-w-full" title={opportunity.error_message}>
                            {opportunity.error_message}
                          </p>
                        </>
                      ) : (
                        <p className="text-sm text-red-700 dark:text-red-300 mt-1">{opportunity.error_message}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-10 gap-4 w-full">
              {/* Main Content Column */}
              <div className="lg:col-span-7 space-y-4">
                {/* Deadlines - mostly white, green accent */}
                {opportunity.deadlines && opportunity.deadlines.length > 0 && (
                  <div className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border shadow-sm animate-slide-up overflow-hidden">
                    <div className="px-4 py-3 bg-white dark:bg-dark-elevated border-b border-gray-200 dark:border-dark-border flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center">
                          <HiOutlineClock className="w-4 h-4 mr-2 text-green-600 dark:text-teal-dm" />
                          Deadlines
                          {opportunity.deadlines.some(d => d.is_primary) && (
                            <span className="ml-2 text-xs font-medium text-green-700 dark:text-teal-dm bg-white dark:bg-dark-hover border border-green-200 dark:border-teal-dm/50 px-2 py-0.5 rounded">CRITICAL</span>
                          )}
                        </h2>
                        <p className="text-xs app-note mt-0.5 inline-block">Add to Calendar sends these to your connected Google or Outlook calendar.</p>
                      </div>
                      {emailConnection?.connected && (
                        <button
                          type="button"
                          onClick={handleSyncCalendar}
                          disabled={syncingCalendar}
                          className="text-xs font-medium px-3 py-2 rounded-lg bg-[#14B8A6] dark:bg-teal-dm text-white dark:text-black hover:bg-[#0D9488] dark:hover:bg-teal-600 disabled:opacity-50 flex items-center gap-1.5 transition-colors shadow-sm"
                        >
                          <HiOutlineCalendar className="w-3.5 h-3.5" />
                          {syncingCalendar ? 'Adding…' : 'Add to Calendar'}
                        </button>
                      )}
                    </div>
                    {calendarSyncMessage && (
                      <div className="px-4 py-2 text-xs text-gray-600 dark:text-gray-300 bg-white dark:bg-dark-elevated border-b border-gray-100 dark:border-dark-border">
                        {calendarSyncMessage}
                      </div>
                    )}
                    <div className="p-3 space-y-3 bg-white dark:bg-dark-elevated">
                      {[...(opportunity.deadlines || [])]
                        .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
                        .map((deadline) => (
                        <div
                          key={deadline.id}
                          className="rounded-lg p-3 bg-white dark:bg-dark-hover border border-gray-200 dark:border-dark-border transition-colors"
                        >
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-2 flex-1 min-w-0 flex-wrap">
                              <span className={`text-xs font-semibold uppercase tracking-wide ${deadline.is_primary ? 'text-green-700 dark:text-teal-dm' : 'text-gray-600 dark:text-gray-300'}`}>
                                {deadline.deadline_type?.replace('_', ' ') || 'Deadline'}
                              </span>
                              {deadline.is_primary && (
                                <span className="text-xs font-medium text-green-700 dark:text-teal-dm bg-white dark:bg-dark-hover border border-green-200 dark:border-teal-dm/50 px-1.5 py-0.5 rounded">PRIMARY</span>
                              )}
                              {deadline.calendar_event_id && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-white dark:bg-dark-hover border border-green-200 dark:border-teal-dm/50 text-green-700 dark:text-teal-dm font-medium">In calendar</span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 text-sm">
                              <span className="font-semibold text-gray-900 dark:text-white">
                                {formatDate(deadline.due_date)}
                              </span>
                              {(deadline.due_time || deadline.timezone) && (
                                <span className="text-xs text-gray-600 dark:text-gray-300 flex items-center gap-1.5">
                                  {deadline.due_time && <span>{deadline.due_time}</span>}
                                  {deadline.timezone && (
                                    <span className="flex items-center gap-1">
                                      <HiOutlineGlobe className="w-3 h-3" />
                                      {deadline.timezone}
                                    </span>
                                  )}
                                </span>
                              )}
                            </div>
                          </div>
                          {deadline.description && (
                            <p className="text-xs text-gray-600 dark:text-gray-300 mt-2 pl-0">{deadline.description}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Description - Read More (classification next to label, fade when long) */}
                {opportunity.description && (
                  <div className="bg-white dark:bg-dark-elevated rounded-lg border border-gray-200 dark:border-dark-border shadow-sm animate-slide-up">
                    <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border">
                      <div className="flex items-center flex-wrap gap-2">
                        <HiOutlineDocumentText className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">Description</h2>
                        {opportunity.solicitation_type && (
                          <span className="inline-flex items-center gap-1 font-mono text-xs font-medium text-[#0D9488] dark:text-teal-dm">
                            <HiOutlineTag className="w-3.5 h-3.5" />
                            {opportunity.solicitation_type}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="px-4 py-3">
                      <div className="relative">
                        <p className={`text-sm text-gray-700 dark:text-gray-300 italic whitespace-pre-wrap leading-relaxed ${!isDescriptionExpanded ? 'line-clamp-3' : ''}`}>
                          {opportunity.description}
                        </p>
                        {!isDescriptionExpanded && opportunity.description.length > 200 && (
                          <div className="absolute bottom-0 left-0 right-0 h-14 bg-gradient-to-t from-white dark:from-dark-elevated to-transparent pointer-events-none" aria-hidden />
                        )}
                      </div>
                      {opportunity.description.length > 200 && (
                        <button
                          onClick={() => setIsDescriptionExpanded(!isDescriptionExpanded)}
                          className="mt-2 text-sm text-[#0D9488] dark:text-teal-dm hover:text-[#0D9488]/80 dark:hover:text-teal-400 font-medium flex items-center space-x-1 transition-colors"
                        >
                          <span>{isDescriptionExpanded ? 'Read less' : 'Read more'}</span>
                          {isDescriptionExpanded ? (
                            <HiOutlineChevronUp className="w-4 h-4" />
                          ) : (
                            <HiOutlineChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* CLINs - Contract Line Items */}
                {/* Empty state with fading effect when processing */}
                {(!opportunity.clins || opportunity.clins.length === 0) && (opportunity.status === 'processing' || opportunity.status === 'pending') && (
                  <div className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border shadow-sm opacity-50 transition-opacity duration-500 animate-fade-in">
                    <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border">
                      <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                        <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600 dark:text-teal-dm" />
                        Contract Line Items (CLINs)
                      </h2>
                    </div>
                    <div className="p-4">
                      <div className="h-32 flex items-center justify-center">
                        <p className="text-sm app-note inline-block">CLINs will appear here once analysis is complete...</p>
                        </div>
                    </div>
                  </div>
                )}

                {/* No CLINs found - Show when completed with 0 CLINs */}
                {(!opportunity.clins || opportunity.clins.length === 0) && opportunity.status === 'completed' && (
                  <div className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border shadow-sm animate-slide-up">
                    <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border">
                      <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                        <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600 dark:text-teal-dm" />
                        Contract Line Items (CLINs)
                      </h2>
                    </div>
                    <div className="p-4">
                      <div className="flex flex-col items-center justify-center py-8 space-y-3">
                        <HiOutlineCheckCircle className="w-12 h-12 text-gray-400 dark:text-gray-500" />
                        <div className="text-center">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">No CLINs found</p>
                          <p className="text-xs app-note inline-block">Analysis completed. No Contract Line Items were detected in the documents.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* CLINs - Contract Line Items (when data is available) */}
                {opportunity.clins && opportunity.clins.length > 0 && (
                  <div className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border shadow-sm animate-slide-up overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                          <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600 dark:text-teal-dm" />
                          Contract Line Items (CLINs) ({opportunity.clins.length})
                        </h2>
                        <p className="text-xs app-note mt-0.5 inline-block">Extracted from solicitation documents. Use dealer/manufacturer info for quote requests.</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => {
                            const dataStr = JSON.stringify(opportunity.clins, null, 2);
                            const blob = new Blob([dataStr], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `opportunity_${id}_clins_${new Date().toISOString().split('T')[0]}.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 rounded-lg hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/30 border border-[#14B8A6]/40 dark:border-teal-dm/40 transition-colors"
                          title="Export CLINs to JSON"
                          aria-label="Export CLINs to JSON file"
                        >
                          <HiOutlineDownload className="w-4 h-4" />
                          Export to JSON
                        </button>
                        {opportunity.clins.length > 1 && (
                          <p className="text-xs app-note inline-block">Click a row to expand</p>
                        )}
                      </div>
                    </div>

                    {dealersManufacturersLoading && (
                      <div className="mx-4 mt-3 mb-1 px-3 py-2 rounded-lg bg-gray-50 dark:bg-dark-hover border border-gray-200 dark:border-dark-border flex items-center gap-2 text-[11px] font-medium app-note">
                        <HiOutlineRefresh className="w-4 h-4 animate-spin flex-shrink-0" />
                        <span>Finding dealers and manufacturers… Results will appear when ready.</span>
                      </div>
                    )}
                    {!dealersManufacturersLoading && opportunity.status === 'completed' && opportunity.clins?.length > 0 && !hasAnyDealerOrManufacturerResearch(opportunity) && (
                      <div className="mx-4 mt-2 mb-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-dark-hover border border-gray-200 dark:border-dark-border flex items-center justify-between gap-2 text-sm text-gray-600 dark:text-gray-300">
                        <span>Manufacturer and dealer research may still be loading or is not yet available.</span>
                        <button type="button" onClick={() => fetchOpportunity()} className="text-[#14B8A6] dark:text-teal-dm hover:underline font-medium flex items-center gap-1">
                          <HiOutlineRefresh className="w-4 h-4" /> Refresh
                        </button>
                      </div>
                    )}

                    {/* Multi-CLIN: compact table + expandable rows */}
                    {opportunity.clins.length > 1 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm border-collapse">
                          <thead>
                            <tr className="bg-gray-100 dark:bg-dark-hover border-b border-gray-200 dark:border-dark-border">
                              <th className="text-left py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 w-20">CLIN</th>
                              <th className="text-left py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 min-w-[140px]">Name / Title</th>
                              <th className="text-left py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 hidden sm:table-cell min-w-[100px]">Manufacturer</th>
                              <th className="text-left py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 hidden md:table-cell w-24">Part #</th>
                              <th className="text-right py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 w-20">Qty</th>
                              <th className="text-right py-2.5 px-3 font-semibold text-gray-700 dark:text-gray-200 w-28">Price</th>
                              <th className="w-8 py-2.5 px-2" aria-label="Expand" />
                            </tr>
                          </thead>
                          <tbody>
                            {opportunity.clins.map((clin) => {
                              const isExpanded = expandedClins.has(clin.id);
                              const hasMore = !!(clin.product_description || clin.additional_data?.delivery_timeline || clin.additional_data?.delivery_address || clin.additional_data?.special_delivery_instructions || clin.service_description || clin.scope_of_work || clin.service_requirements);
                              const text = (clin.product_name || clin.product_description || '').toLowerCase();
                              const clinTypeLabel = text.startsWith('warranty') || text.includes('warranty and support') ? 'Warranty' : text.startsWith('training') || text.includes('training:') ? 'Training' : text.startsWith('support') ? 'Support' : null;
                              return (
                                <React.Fragment key={clin.id}>
                                  <tr
                                    key={clin.id}
                                    onClick={() => {
                                      const next = new Set(expandedClins);
                                      if (next.has(clin.id)) next.delete(clin.id);
                                      else next.add(clin.id);
                                      setExpandedClins(next);
                                    }}
                                    className={`border-b cursor-pointer transition-colors ${isExpanded ? 'text-white dark:text-gray-700' : 'border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-hover'}`}
                                    style={isExpanded ? {
                                      backgroundImage: 'repeating-linear-gradient(-55deg, transparent, transparent 8px, rgba(255,255,255,0.06) 8px, rgba(255,255,255,0.06) 9px), repeating-linear-gradient(35deg, transparent, transparent 8px, rgba(255,255,255,0.04) 8px, rgba(255,255,255,0.04) 9px), linear-gradient(to right, #14B8A6, #0D9488)',
                                    } : undefined}
                                  >
                                    <td className="py-2.5 px-3">
                                      <span className={`font-bold ${isExpanded ? 'text-white dark:text-gray-700' : 'text-[#0D9488] dark:text-teal-dm'}`}>CLIN {clin.clin_number}</span>
                                      {(clin.base_item_number || clin.additional_data?.nsn) && (
                                        <span className={`block text-xs ${isExpanded ? 'text-white/90 dark:text-gray-600' : 'text-gray-500 dark:text-gray-300'}`}>NSN: {clin.base_item_number || clin.additional_data?.nsn}</span>
                                      )}
                                    </td>
                                    <td className="py-2.5 px-3">
                                      <div className="flex flex-col gap-1">
                                        {clinTypeLabel && (
                                          <span className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded w-fit ${isExpanded ? 'bg-black/20 text-white dark:bg-white/25 dark:text-gray-800' : 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200'}`} title="Service/support line item, not a product">
                                            {clinTypeLabel}
                                          </span>
                                        )}
                                        <span className={`font-medium line-clamp-2 ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-900 dark:text-white'}`} title={clin.product_name || clin.clin_name || clin.product_description}>
                                          {clin.product_name || clin.clin_name || (clin.product_description ? (clin.product_description.length > 80 ? `${clin.product_description.slice(0, 80)}…` : clin.product_description) : '—')}
                                        </span>
                                      </div>
                                    </td>
                                    <td className={`py-2.5 px-3 hidden sm:table-cell ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-700 dark:text-gray-300'}`} title={!clin.manufacturer_name ? 'Not specified in document for this line' : undefined}>
                                      {clin.manufacturer_name || '—'}
                                    </td>
                                    <td className={`py-2.5 px-3 hidden md:table-cell font-mono text-xs ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-700 dark:text-gray-300'}`} title={!(clin.part_number || clin.model_number) ? 'Not specified in document for this line' : undefined}>
                                      {clin.part_number || clin.model_number || '—'}
                                    </td>
                                    <td className={`py-2.5 px-3 text-right font-medium ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-900 dark:text-white'}`}>
                                      {clin.quantity != null ? `${clin.quantity}${clin.unit_of_measure ? ` ${clin.unit_of_measure}` : ''}` : '—'}
                                    </td>
                                    <td className={`py-2.5 px-3 text-right font-semibold ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-900 dark:text-white'}`}>
                                      {clin.extended_price != null ? `$${Number(clin.extended_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                                    </td>
                                    <td className="py-2.5 px-2">
                                      {hasMore && (
                                        <span className={`inline-flex items-center justify-center w-7 h-7 rounded ${isExpanded ? 'text-white dark:text-gray-700' : 'text-gray-500 dark:text-gray-300'}`}>
                                          {isExpanded ? <HiOutlineChevronUp className="w-4 h-4" /> : <HiOutlineChevronDown className="w-4 h-4" />}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                  {isExpanded && (
                                    <tr key={`${clin.id}-detail`} className="border-b border-gray-200 dark:border-dark-border">
                                      <td colSpan={7} className="p-0 align-top bg-white dark:bg-dark-elevated">
                                        {/* Card aligns full-width with table; rounded bottom to match theme; keep white in light theme when expanded */}
                                        <div className="mx-2 mb-2 rounded-b-xl border-x-2 border-b-2 border-[#14B8A6] dark:border-teal-dm bg-white dark:bg-dark-elevated text-sm overflow-hidden">
                                          <div className="px-4 py-4 space-y-4 bg-white dark:bg-dark-elevated">
                                            {/* Key details */}
                                            <div className="rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-4">
                                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
                                                {clin.product_name && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Name:</span> <span className="text-gray-600 dark:text-gray-200">{clin.product_name}</span></div>}
                                                {(clin.base_item_number || clin.additional_data?.nsn) && <div><span className="text-gray-700 dark:text-gray-300 font-bold">NSN:</span> <span className="font-mono text-gray-600 dark:text-gray-200">{clin.base_item_number || clin.additional_data?.nsn}</span></div>}
                                                {clin.manufacturer_name && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Manufacturer:</span> <span className="text-gray-600 dark:text-gray-200">{clin.manufacturer_name}</span></div>}
                                                {clin.part_number && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Part #:</span> <span className="font-mono text-gray-600 dark:text-gray-200">{clin.part_number}</span></div>}
                                                {clin.model_number && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Model #:</span> <span className="font-mono text-gray-600 dark:text-gray-200">{clin.model_number}</span></div>}
                                                {(clin.additional_data?.drawing_number || clin.drawing_number) && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Drawing #:</span> <span className="font-mono text-gray-600 dark:text-gray-200">{clin.additional_data?.drawing_number || clin.drawing_number}</span></div>}
                                                {clin.contract_type && <div><span className="text-gray-700 dark:text-gray-300 font-bold">Contract type:</span> <span className="text-gray-600 dark:text-gray-200">{clin.contract_type}</span></div>}
                                              </div>
                                            </div>
                                            {(clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline) && (
                                              <div className="space-y-1.5">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineClock className="w-3.5 h-3.5" /> Delivery timeline</div>
                                                <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3">{clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline}</p>
                                              </div>
                                            )}
                                            {clin.additional_data?.delivery_address && (
                                              <div className="space-y-1.5">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineLocationMarker className="w-3.5 h-3.5" /> Delivery address</div>
                                                <p className="text-gray-800 dark:text-white whitespace-pre-wrap font-mono rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3 text-xs">{clin.additional_data.delivery_address}</p>
                                              </div>
                                            )}
                                            {clin.additional_data?.special_delivery_instructions && (
                                              <div className="space-y-1.5">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineExclamationCircle className="w-3.5 h-3.5" /> Special instructions</div>
                                                <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3">{clin.additional_data.special_delivery_instructions}</p>
                                              </div>
                                            )}
                                            {clin.product_description && (
                                              <div className="space-y-1.5">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide">Supplies / services</div>
                                                <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3 italic">{clin.product_description}</p>
                                              </div>
                                            )}
                                            {(clin.service_description || clin.scope_of_work || clin.service_requirements) && (
                                              <div className="pt-3 border-t border-[#14B8A6]/40 dark:border-teal-dm/40 space-y-2">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineDocumentText className="w-3.5 h-3.5" /> Service details</div>
                                                <div className="space-y-2">
                                                  {clin.service_description && <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3">{clin.service_description}</p>}
                                                  {clin.scope_of_work && <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3 font-medium">{clin.scope_of_work}</p>}
                                                  {clin.service_requirements && <p className="text-gray-800 dark:text-white whitespace-pre-wrap rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3">{clin.service_requirements}</p>}
                                                </div>
                                              </div>
                                            )}
                                            {/* Manufacturer research (Tavily) – do not show when "manufacturer" is the buying agency */}
                                            {(() => {
                                              const manufacturerName = clin?.manufacturer_name || '';
                                              if (isLikelyAgencyNotManufacturer(manufacturerName)) return null;
                                              const mfrList = getClinManufacturerResearchList(clin);
                                              if (mfrList.length === 0 || !mfrList.some(m => m.official_website || m.sales_contact_email)) return null;
                                              return (
                                              <div className="pt-3 border-t border-[#14B8A6]/40 dark:border-teal-dm/40 space-y-3">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineOfficeBuilding className="w-3.5 h-3.5" /> Manufacturer research</div>
                                                <p className="text-xs text-gray-500 dark:text-gray-300 -mt-0.5">Use these to request quotes or contact for this CLIN. Contact email is required for quote requests.</p>
                                                {mfrList.map((mfr, idx) => {
                                                  const websiteHref = mfr.official_website?.startsWith('http') ? mfr.official_website : (mfr.official_website ? `https://${mfr.official_website.replace(/^\/*/, '')}` : null);
                                                  const label = mfr.name || (mfrList.length === 1 ? manufacturerName || 'Manufacturer' : `Manufacturer ${idx + 1}`);
                                                  if (!websiteHref && !mfr.sales_contact_email) return null;
                                                  return (
                                                    <div key={idx} className="rounded-xl border border-[#14B8A6]/40 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-2.5 space-y-1.5">
                                                      {mfrList.length > 1 && <p className="text-xs font-medium text-gray-800 dark:text-gray-200">{label}</p>}
                                                      <div className="flex flex-wrap gap-3 text-sm">
                                                        {websiteHref && (
                                                          <span className="inline-flex items-center gap-1.5">
                                                            <HiOutlineGlobe className="w-3.5 h-3.5 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                                                            <span className="text-gray-600 dark:text-gray-300">Official website:</span>
                                                            <a href={websiteHref} target="_blank" rel="noopener noreferrer" className="text-[#0D9488] dark:text-teal-dm hover:underline break-all">{websiteHref.replace(/^https?:\/\//, '')}</a>
                                                          </span>
                                                        )}
                                                        {mfr.sales_contact_email ? (
                                                          <span className="inline-flex items-center gap-1.5">
                                                            <HiOutlineMail className="w-3.5 h-3.5 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                                                            <span className="text-gray-600 dark:text-gray-300">Email (quote/contact):</span>
                                                            <button type="button" onClick={() => openSendEmail(mfr.sales_contact_email)} className="text-[#0D9488] dark:text-teal-dm hover:underline break-all text-left" title="Send email from the app">{mfr.sales_contact_email}</button>
                                                          </span>
                                                        ) : dealersManufacturersLoading && websiteHref ? (
                                                          <span className="inline-flex items-center gap-1.5 text-gray-400 dark:text-gray-500 animate-pulse" aria-busy="true">
                                                            <HiOutlineMail className="w-3.5 h-3.5 flex-shrink-0" />
                                                            <span>Finding…</span>
                                                          </span>
                                                        ) : null}
                                                      </div>
                                                    </div>
                                                  );
                                                })}
                                              </div>
                                              );
                                            })()}
                                            {/* Dealers / distributors (Tavily) */}
                                            {getClinDealerResearch(clin).length > 0 && (
                                              <div className="pt-3 border-t border-[#14B8A6]/40 dark:border-teal-dm/40 space-y-2">
                                                <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineChartBar className="w-3.5 h-3.5" /> Authorized dealers / distributors</div>
                                                <p className="text-xs text-gray-500 dark:text-gray-300 -mt-0.5">Contact email is required for quote requests and outreach.</p>
                                                <div className="overflow-x-auto">
                                                  <table className="min-w-full text-xs border border-gray-200 dark:border-dark-border rounded-lg">
                                                    <thead><tr className="bg-white dark:bg-dark-hover text-left"><th className="py-1.5 px-2 font-semibold text-gray-700 dark:text-gray-200">Company</th><th className="py-1.5 px-2 font-semibold text-gray-700 dark:text-gray-200">Website</th><th className="py-1.5 px-2 font-semibold text-gray-700 dark:text-gray-200">Contact email (quote)</th><th className="py-1.5 px-2 font-semibold text-gray-700 dark:text-gray-200">Price</th></tr></thead>
                                                    <tbody>
                                                      {getClinDealerResearch(clin).slice(0, 8).map((d, idx) => (
                                                        <tr key={idx} className="border-t border-gray-100 dark:border-dark-border bg-white dark:bg-dark-elevated">
                                                          <td className="py-1.5 px-2 text-gray-800 dark:text-gray-200">{d.company_name || '—'}</td>
                                                          <td className="py-1.5 px-2">{d.website_url ? <a href={d.website_url} target="_blank" rel="noopener noreferrer" className="text-[#0D9488] dark:text-teal-dm hover:underline inline-flex items-center gap-0.5"><HiOutlineExternalLink className="w-3 h-3" /> Link</a> : '—'}</td>
                                                          <td className="py-1.5 px-2">
                                                            {d.sales_contact_email ? (
                                                              <button type="button" onClick={() => openSendEmail(d.sales_contact_email)} className="text-[#0D9488] dark:text-teal-dm hover:underline break-all text-left" title="Send email from the app">{d.sales_contact_email}</button>
                                                            ) : dealersManufacturersLoading ? (
                                                              <span className="inline-flex items-center gap-1 text-gray-400 dark:text-gray-500 animate-pulse" aria-busy="true">Finding…</span>
                                                            ) : (
                                                              <div className="flex items-center gap-1.5">
                                                                <input
                                                                  type="email"
                                                                  placeholder="Add contact email"
                                                                  className="text-xs border-0 border-b border-gray-400 dark:border-dark-border bg-transparent px-0 py-0.5 w-28 max-w-full focus:outline-none focus:border-[#14B8A6] dark:focus:border-teal-dm focus:ring-0 text-gray-900 dark:text-white"
                                                                  value={editingDealerEmail?.clinId === clin.id && editingDealerEmail?.dealerIndex === idx ? draftDealerEmail : ''}
                                                                  onChange={(e) => { setEditingDealerEmail({ clinId: clin.id, dealerIndex: idx }); setDraftDealerEmail(e.target.value); }}
                                                                  onFocus={() => { setEditingDealerEmail({ clinId: clin.id, dealerIndex: idx }); }}
                                                                />
                                                                <button
                                                                  type="button"
                                                                  title="Save"
                                                                  disabled={savingDealerEmail || !(editingDealerEmail?.clinId === clin.id && editingDealerEmail?.dealerIndex === idx && draftDealerEmail.trim())}
                                                                  onClick={() => handleSaveDealerEmail(clin.id, idx, draftDealerEmail)}
                                                                  className="p-1 text-[#14B8A6] dark:text-teal-dm hover:text-[#0D9488] dark:hover:text-teal-400 hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                  <HiOutlineSave className="w-4 h-4" />
                                                                </button>
                                                              </div>
                                                            )}
                                                          </td>
                                                          <td className="py-1.5 px-2 text-gray-600 dark:text-gray-300">{d.retail_pricing || '—'}</td>
                                                        </tr>
                                                      ))}
                                                    </tbody>
                                                  </table>
                                                </div>
                                                {getClinDealerResearch(clin).length > 0 && !getClinDealerResearch(clin).some(d => d.sales_contact_email) && (
                                                  <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-300">
                                                    {getClinDealerResearch(clin).some(d => d.website_url)
                                                      ? 'Dealer contact emails not found; use website links above to request quotes.'
                                                      : 'Dealer contact details not found. Use the lookup links below to find dealers online or search for the company to request a quote.'}
                                                  </p>
                                                )}
                                              </div>
                                            )}
                                            {/* Find manufacturers & dealers - external lookup links */}
                                            <div className="pt-3 border-t border-[#14B8A6]/40 dark:border-teal-dm/40 space-y-2">
                                              <div className="text-xs font-semibold text-[#0D9488] dark:text-teal-dm uppercase tracking-wide flex items-center gap-1"><HiOutlineGlobe className="w-3.5 h-3.5" /> Find manufacturers & dealers</div>
                                              {!lookupLinksByClinId[clin.id] ? (
                                                <button
                                                  type="button"
                                                  onClick={() => loadClinLookupLinks(clin.id)}
                                                  disabled={loadingLookupClinId === clin.id}
                                                  className="text-sm px-3 py-1.5 rounded border border-[#14B8A6] dark:border-teal-dm text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 disabled:opacity-50"
                                                >
                                                  {loadingLookupClinId === clin.id ? 'Loading…' : 'Load lookup links'}
                                                </button>
                                              ) : (
                                                <div className="flex flex-wrap gap-2">
                                                  {(lookupLinksByClinId[clin.id] || []).map((link, idx) => (
                                                    <a
                                                      key={idx}
                                                      href={link.url}
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                      className="inline-flex items-center gap-1 text-sm px-2.5 py-1.5 rounded border border-[#14B8A6]/60 dark:border-teal-dm/60 bg-white dark:bg-dark-hover text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20"
                                                    >
                                                      <HiOutlineExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                                                      {link.label}
                                                    </a>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                          </div>
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      /* Single CLIN: card layout with rounded corners to match theme */
                      <div className="p-4">
                        {opportunity.clins.map((clin) => (
                          <div
                            key={clin.id}
                            className="bg-white dark:bg-dark-elevated rounded-xl border border-gray-200 dark:border-dark-border hover:border-[#14B8A6] dark:hover:border-teal-dm hover:shadow-md transition-all duration-200 overflow-hidden"
                          >
                            <div className="relative rounded-t-xl bg-gradient-to-r from-[#14B8A6] to-[#0D9488] dark:from-teal-dm dark:to-teal-600 px-5 py-3">
                              <div
                                className="absolute inset-0 pointer-events-none opacity-100"
                                aria-hidden
                                style={{
                                  backgroundImage: 'repeating-linear-gradient(-55deg, transparent, transparent 8px, rgba(255,255,255,0.06) 8px, rgba(255,255,255,0.06) 9px), repeating-linear-gradient(35deg, transparent, transparent 8px, rgba(255,255,255,0.04) 8px, rgba(255,255,255,0.04) 9px)',
                                }}
                              />
                              <div className="relative flex items-center justify-between flex-wrap gap-2">
                                <div className="flex items-center space-x-3">
                                  <div className="bg-white/20 backdrop-blur-sm rounded-lg px-3 py-1.5">
                                    <span className="text-black font-bold text-lg tracking-wide">CLIN {clin.clin_number}</span>
                                  </div>
                                  {(clin.base_item_number || clin.additional_data?.nsn) && (
                                    <span className="text-xs text-black bg-white/10 px-2.5 py-1 rounded-md font-medium">NSN: {clin.base_item_number || clin.additional_data?.nsn}</span>
                                  )}
                                </div>
                                {clin.extended_price != null && (
                                  <div className="text-right">
                                    <div className="text-xs text-white/80 font-medium">Total Price</div>
                                    <div className="text-white font-bold text-lg">
                                      ${Number(clin.extended_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </div>
                                  </div>
                                )}
                              </div>
                              {clin.clin_name && <div className="relative mt-2 text-sm text-white/95 font-medium">{clin.clin_name}</div>}
                            </div>
                            <div className="p-5 space-y-4">
                              {(clin.product_name || clin.product_description || clin.manufacturer_name || clin.part_number || clin.model_number || clin.quantity != null || clin.contract_type || (clin.additional_data && (clin.additional_data.drawing_number || clin.additional_data.delivery_timeline || clin.additional_data.delivery_address || clin.additional_data.special_delivery_instructions))) && (
                                <div className="bg-white dark:bg-dark-elevated rounded-xl p-4 border border-gray-200 dark:border-teal-dm/40">
                                  <div className="flex items-center space-x-2 mb-3">
                                    <HiOutlineSparkles className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm" />
                                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Product Details</h4>
                                  </div>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3 text-sm">
                                    {clin.product_name && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Name:</span><span className="text-gray-600 dark:text-gray-300">{clin.product_name}</span></div>}
                                    {(clin.base_item_number || clin.additional_data?.nsn) && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">NSN:</span><span className="text-gray-600 dark:text-gray-300 font-mono text-xs">{clin.base_item_number || clin.additional_data?.nsn}</span></div>}
                                    {clin.manufacturer_name && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Manufacturer:</span><span className="text-gray-600 dark:text-gray-300">{clin.manufacturer_name}</span></div>}
                                    {clin.part_number && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Part #:</span><span className="text-gray-600 dark:text-gray-300 font-mono text-xs">{clin.part_number}</span></div>}
                                    {clin.model_number && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Model #:</span><span className="text-gray-600 dark:text-gray-300 font-mono text-xs">{clin.model_number}</span></div>}
                                    {(clin.additional_data?.drawing_number || clin.drawing_number) && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Drawing #:</span><span className="text-gray-600 dark:text-gray-300 font-mono text-xs">{clin.additional_data?.drawing_number || clin.drawing_number}</span></div>}
                                    {clin.quantity != null && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Quantity:</span><span className="text-gray-600 dark:text-gray-300">{clin.quantity}{clin.unit_of_measure ? ` ${clin.unit_of_measure}` : ''}</span></div>}
                                    {clin.contract_type && <div className="flex items-start"><span className="text-gray-700 dark:text-gray-300 font-bold min-w-[110px] flex-shrink-0">Contract Type:</span><span className="text-gray-600 dark:text-gray-300">{clin.contract_type}</span></div>}
                                  </div>
                              {expandedClins.has(clin.id) && (
                                <div className="mt-4 pt-4 border-t border-gray-300 dark:border-teal-dm/40 space-y-5">
                                      {(clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline) && (
                                        <div>
                                          <div className="flex items-center space-x-2 mb-3"><HiOutlineClock className="w-4 h-4 text-[#0D9488] dark:text-teal-dm" /><div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Delivery Timeline:</div></div>
                                          <div className="text-sm text-gray-800 dark:text-white leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm italic ml-6">{clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline}</div>
                                        </div>
                                      )}
                                      {clin.additional_data?.delivery_address && (
                                        <div>
                                          <div className="flex items-center space-x-2 mb-3"><HiOutlineLocationMarker className="w-4 h-4 text-[#0D9488] dark:text-teal-dm" /><div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Delivery Address:</div></div>
                                          <div className="text-sm text-gray-800 dark:text-white leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm font-mono ml-6">{clin.additional_data.delivery_address}</div>
                                        </div>
                                      )}
                                      {clin.additional_data?.special_delivery_instructions && (
                                        <div>
                                          <div className="flex items-center space-x-2 mb-3"><HiOutlineExclamationCircle className="w-4 h-4 text-[#0D9488] dark:text-teal-dm" /><div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Special Delivery Instructions:</div></div>
                                          <div className="text-sm text-gray-800 dark:text-white leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm italic ml-6">{clin.additional_data.special_delivery_instructions}</div>
                                        </div>
                                      )}
                                      {clin.product_description && (
                                        <div>
                                          <div className="flex items-center space-x-2 mb-3"><HiOutlineTag className="w-4 h-4 text-[#0D9488] dark:text-teal-dm" /><div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Supplies/Services:</div></div>
                                          <div className="text-sm text-gray-800 dark:text-white leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm italic ml-6">{clin.product_description}</div>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
                              {expandedClins.has(clin.id) && (clin.service_description || clin.scope_of_work || clin.service_requirements) && (
                                <div className="mt-5 pt-5 border-t border-gray-300 dark:border-teal-dm/40">
                                  <div className="flex items-center space-x-2 mb-4"><HiOutlineDocumentText className="w-5 h-5 text-[#0D9488] dark:text-teal-dm" /><h4 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide">Service Details</h4></div>
                                  <div className="space-y-5">
                                    {clin.service_description && <div><div className="text-xs text-gray-500 dark:text-gray-300 font-medium mb-2">Description:</div><div className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm ml-4">{clin.service_description}</div></div>}
                                    {clin.scope_of_work && <div><div className="flex items-center space-x-2 mb-3"><HiOutlineDocumentText className="w-4 h-4 text-[#0D9488] dark:text-teal-dm" /><div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Scope of Work:</div></div><div className="text-sm text-gray-800 dark:text-white leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm font-bold italic ml-6">{clin.scope_of_work}</div></div>}
                                    {clin.service_requirements && <div><div className="text-xs text-gray-500 dark:text-gray-300 font-medium mb-2">Requirements:</div><div className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap bg-white dark:bg-dark-elevated p-4 rounded-xl border border-gray-300 dark:border-teal-dm/40 shadow-sm ml-4">{clin.service_requirements}</div></div>}
                                  </div>
                                </div>
                              )}
                              {expandedClins.has(clin.id) && (() => {
                                const manufacturerName = clin?.manufacturer_name || '';
                                if (isLikelyAgencyNotManufacturer(manufacturerName)) return null;
                                const mfrList = getClinManufacturerResearchList(clin);
                                if (mfrList.length === 0 || !mfrList.some(m => m.official_website || m.sales_contact_email)) return null;
                                return (
                                <div className="mt-5 pt-5 border-t border-gray-300 dark:border-teal-dm/40">
                                  <div className="flex items-center space-x-2 mb-2"><HiOutlineOfficeBuilding className="w-5 h-5 text-[#0D9488] dark:text-teal-dm" /><h4 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide">Manufacturer research</h4></div>
                                  <p className="text-xs text-gray-500 dark:text-gray-300 mb-3">Use these to request quotes or contact for this CLIN. Contact email is required for quote requests.</p>
                                  <div className="space-y-4">
                                    {mfrList.map((mfr, idx) => {
                                      const websiteHref = mfr.official_website?.startsWith('http') ? mfr.official_website : (mfr.official_website ? `https://${mfr.official_website.replace(/^\/*/, '')}` : null);
                                      const label = mfr.name || (mfrList.length === 1 ? manufacturerName || 'Manufacturer' : `Manufacturer ${idx + 1}`);
                                      if (!websiteHref && !mfr.sales_contact_email) return null;
                                      return (
                                        <div key={idx} className="rounded-xl border border-gray-200 dark:border-teal-dm/40 bg-white dark:bg-dark-elevated p-3 space-y-2">
                                          {mfrList.length > 1 && <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{label}</p>}
                                          <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3 text-sm">
                                            {websiteHref && (
                                              <div className="flex items-center gap-2 flex-wrap">
                                                <HiOutlineGlobe className="w-4 h-4 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                                                <span className="text-gray-600 dark:text-gray-300">Official website:</span>
                                                <a href={websiteHref} target="_blank" rel="noopener noreferrer" className="text-[#0D9488] dark:text-teal-dm hover:underline break-all">{websiteHref.replace(/^https?:\/\//, '')}</a>
                                              </div>
                                            )}
                                            {mfr.sales_contact_email ? (
                                              <div className="flex items-center gap-2 flex-wrap">
                                                <HiOutlineMail className="w-4 h-4 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                                                <span className="text-gray-600 dark:text-gray-300">Email (quote/contact):</span>
                                                <button type="button" onClick={() => openSendEmail(mfr.sales_contact_email)} className="text-[#0D9488] dark:text-teal-dm hover:underline break-all text-left" title="Send email from the app">{mfr.sales_contact_email}</button>
                                              </div>
                                            ) : dealersManufacturersLoading && websiteHref ? (
                                              <div className="flex items-center gap-2 flex-wrap text-gray-400 dark:text-gray-500 animate-pulse" aria-busy="true">
                                                <HiOutlineMail className="w-4 h-4 flex-shrink-0" />
                                                <span>Finding…</span>
                                              </div>
                                            ) : null}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                                );
                              })()}
                              {expandedClins.has(clin.id) && getClinDealerResearch(clin).length > 0 && (
                                <div className="mt-5 pt-5 border-t border-gray-300 dark:border-teal-dm/40">
                                  <div className="flex items-center space-x-2 mb-3"><HiOutlineChartBar className="w-5 h-5 text-gray-600 dark:text-gray-300" /><h4 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide">Authorized dealers / distributors</h4></div>
                                  <p className="text-xs text-gray-500 dark:text-gray-300 mb-2">Contact email is required for quote requests and outreach.</p>
                                  <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-dark-border">
                                    <table className="min-w-full text-sm">
                                      <thead><tr className="bg-white dark:bg-dark-hover text-left"><th className="py-2 px-3 font-semibold text-gray-700 dark:text-gray-200">Company</th><th className="py-2 px-3 font-semibold text-gray-700 dark:text-gray-200">Website</th><th className="py-2 px-3 font-semibold text-gray-700 dark:text-gray-200">Contact email (quote)</th><th className="py-2 px-3 font-semibold text-gray-700 dark:text-gray-200">Price</th></tr></thead>
                                      <tbody>
                                        {getClinDealerResearch(clin).slice(0, 8).map((d, idx) => (
                                          <tr key={idx} className="border-t border-gray-100 dark:border-dark-border bg-white dark:bg-dark-elevated">
                                            <td className="py-2 px-3 text-gray-800 dark:text-gray-200">{d.company_name || '—'}</td>
                                            <td className="py-2 px-3">{d.website_url ? <a href={d.website_url} target="_blank" rel="noopener noreferrer" className="text-[#0D9488] dark:text-teal-dm hover:underline inline-flex items-center gap-1"><HiOutlineExternalLink className="w-3.5 h-3.5" /> Link</a> : '—'}</td>
                                            <td className="py-2 px-3">
                                              {d.sales_contact_email ? (
                                                <button type="button" onClick={() => openSendEmail(d.sales_contact_email)} className="text-[#0D9488] hover:underline break-all text-left" title="Send email from the app">{d.sales_contact_email}</button>
                                              ) : dealersManufacturersLoading ? (
                                                <span className="inline-flex items-center gap-1 text-gray-400 animate-pulse" aria-busy="true">Finding…</span>
                                              ) : (
                                                <div className="flex items-center gap-2">
                                                  <input
                                                    type="email"
                                                    placeholder="Add contact email"
                                                    className="text-sm border-0 border-b border-gray-400 dark:border-dark-border bg-transparent px-0 py-0.5 w-36 max-w-full focus:outline-none focus:border-[#14B8A6] dark:focus:border-teal-dm focus:ring-0 text-gray-900 dark:text-white"
                                                    value={editingDealerEmail?.clinId === clin.id && editingDealerEmail?.dealerIndex === idx ? draftDealerEmail : ''}
                                                    onChange={(e) => { setEditingDealerEmail({ clinId: clin.id, dealerIndex: idx }); setDraftDealerEmail(e.target.value); }}
                                                    onFocus={() => { setEditingDealerEmail({ clinId: clin.id, dealerIndex: idx }); }}
                                                  />
                                                  <button
                                                    type="button"
                                                    title="Save"
                                                    disabled={savingDealerEmail || !(editingDealerEmail?.clinId === clin.id && editingDealerEmail?.dealerIndex === idx && draftDealerEmail.trim())}
                                                    onClick={() => handleSaveDealerEmail(clin.id, idx, draftDealerEmail)}
                                                    className="p-1 text-[#14B8A6] hover:text-[#0D9488] hover:bg-[#14B8A6]/10 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                                                  >
                                                    <HiOutlineSave className="w-4 h-4" />
                                                  </button>
                                                </div>
                                              )}
                                            </td>
                                            <td className="py-2 px-3 text-gray-600 dark:text-gray-300">{d.retail_pricing || '—'}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                  {getClinDealerResearch(clin).length > 0 && !getClinDealerResearch(clin).some(d => d.sales_contact_email) && (
                                    <p className="mt-2 text-sm text-gray-500">
                                      {getClinDealerResearch(clin).some(d => d.website_url)
                                        ? 'Dealer contact emails not found; use website links above to request quotes.'
                                        : 'Dealer contact details not found. Use the lookup links below to find dealers online or search for the company to request a quote.'}
                                    </p>
                                  )}
                                </div>
                              )}
                              {expandedClins.has(clin.id) && (
                              <div className="mt-5 pt-5 border-t border-gray-300 dark:border-dark-border">
                                <div className="flex items-center space-x-2 mb-3"><HiOutlineGlobe className="w-5 h-5 text-gray-600 dark:text-gray-300" /><h4 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide">Find manufacturers & dealers</h4></div>
                                {!lookupLinksByClinId[clin.id] ? (
                                  <button type="button" onClick={() => loadClinLookupLinks(clin.id)} disabled={loadingLookupClinId === clin.id} className="text-sm px-3 py-1.5 rounded-lg border border-[#14B8A6] dark:border-teal-dm text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 disabled:opacity-50 transition-colors">
                                    {loadingLookupClinId === clin.id ? 'Loading…' : 'Load lookup links'}
                                  </button>
                                ) : (
                                  <div className="flex flex-wrap gap-2">
                                    {(lookupLinksByClinId[clin.id] || []).map((link, idx) => (
                                      <a key={idx} href={link.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm px-2.5 py-1.5 rounded-lg border border-[#14B8A6]/60 dark:border-teal-dm/60 bg-white dark:bg-dark-hover text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 transition-colors">
                                        <HiOutlineExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                                        {link.label}
                                      </a>
                                    ))}
                                  </div>
                                )}
                              </div>
                              )}
                              {((clin.additional_data?.delivery_timeline || clin.additional_data?.delivery_address || clin.additional_data?.special_delivery_instructions || clin.product_description || clin.scope_of_work || clin.service_description || clin.service_requirements) ||
                                getClinDealerResearch(clin).length > 0 ||
                                (!isLikelyAgencyNotManufacturer(clin?.manufacturer_name || '') ? false : getClinManufacturerResearchList(clin).some(m => m.official_website || m.sales_contact_email))) && (
                                <div className="flex justify-center mt-4 pt-3 border-t border-gray-200 dark:border-dark-border">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); const next = new Set(expandedClins); if (next.has(clin.id)) next.delete(clin.id); else next.add(clin.id); setExpandedClins(next); }}
                                    className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 font-medium transition-colors"
                                    title={expandedClins.has(clin.id) ? 'Collapse' : 'Expand'}
                                    aria-label={expandedClins.has(clin.id) ? 'Collapse CLIN details' : 'Expand CLIN details'}
                                  >
                                    <span>{expandedClins.has(clin.id) ? 'Show Less' : 'Show More'}</span>
                                    {expandedClins.has(clin.id) ? <HiOutlineChevronUp className="w-4 h-4" /> : <HiOutlineChevronDown className="w-4 h-4" />}
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Sidebar - attachments, quote emails, email and calendar (~20% wider than before) */}
              <div className="lg:col-span-3 space-y-4">
                {/* Documents - Attachments */}
                {opportunity.documents && opportunity.documents.length > 0 && (
                  <div className="bg-white dark:bg-dark-elevated rounded-lg border border-gray-200 dark:border-dark-border shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border">
                      <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                        <HiOutlinePaperClip className="w-5 h-5 mr-2 text-gray-600 dark:text-gray-300" />
                        Attachments ({opportunity.documents.length})
                      </h2>
                      <p className="text-[11px] font-medium text-[#0D9488] dark:text-teal-dm mt-0.5">View, download, or Edit to fill forms and add text to PDFs. Word docs open as a saved PDF copy (original kept).</p>
                    </div>
                    {opportunity._editWordError && (
                      <div className="mx-4 mt-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-xs border border-red-200 dark:border-red-800">
                        {opportunity._editWordError}
                      </div>
                    )}
                    <div className="p-4 space-y-2">
                      {opportunity.documents.map((doc) => (
                        <div
                          key={doc.id}
                          className="flex items-stretch bg-gray-100 dark:bg-dark-elevated rounded-lg border-2 border-gray-200 dark:border-dark-border hover:bg-gray-200 dark:hover:bg-dark-hover hover:border-gray-300 dark:hover:border-gray-500 transition-all duration-200 group focus-within:ring-2 focus-within:ring-[#14B8A6] dark:focus-within:ring-teal-dm focus-within:ring-offset-2 dark:focus-within:ring-offset-black overflow-visible"
                        >
                          <div className="flex items-center space-x-2.5 min-w-0 flex-1 p-2.5">
                            {getFileIcon(doc.file_type, doc.file_name)}
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{doc.file_name}</p>
                              <div className="flex items-center space-x-2 text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                                <span>{formatFileSize(doc.file_size)}</span>
                                <span>•</span>
                                <span>{getFileTypeDisplayLabel(doc)}</span>
                                <span>•</span>
                                <span className="capitalize">{doc.source.replace('_', ' ')}</span>
                              </div>
                            </div>
                          </div>
                          <div
                            className="relative flex items-center flex-shrink-0 rounded-r-lg border-l border-gray-200 dark:border-dark-border bg-gray-200 dark:bg-dark-hover"
                            ref={attachmentMenuDocId === Number(doc.id) ? attachmentMenuRef : undefined}
                          >
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); const id = Number(doc.id); setAttachmentMenuDocId((prev) => (prev === id ? null : id)); }}
                              className="h-full px-3 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors focus:outline-none"
                              title="Actions"
                              aria-label="Document actions"
                              aria-expanded={attachmentMenuDocId === Number(doc.id)}
                            >
                              <HiOutlineDotsVertical className="w-5 h-5" />
                            </button>
                            {attachmentMenuDocId === Number(doc.id) && (
                              <div className="absolute right-0 top-full z-[100] mt-0.5 min-w-[180px] rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-lg py-1">
                                <button
                                  type="button"
                                  onClick={() => { setAttachmentMenuDocId(null); handleEditDocument(doc); }}
                                  disabled={!!editWordPreparingForId}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-60"
                                >
                                  <HiOutlinePencil className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => { setAttachmentMenuDocId(null); handleViewDocument(doc.id, doc.file_type); }}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                                >
                                  <HiOutlineDocumentText className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm flex-shrink-0" />
                                  View
                                </button>
                                <button
                                  type="button"
                                  onClick={() => { setAttachmentMenuDocId(null); handleSaveAsDocument(doc); }}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                                >
                                  <HiOutlineDownload className="w-4 h-4 flex-shrink-0" />
                                  Save as
                                </button>
                                {isWordDoc(doc) && (
                                  <button
                                    type="button"
                                    onClick={() => { setAttachmentMenuDocId(null); handleConvertToPdf(doc); }}
                                    disabled={!!convertToPdfDocumentId || !!editWordPreparingForId}
                                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-60"
                                  >
                                    {convertToPdfDocumentId === doc.id ? (
                                      <span className="animate-spin inline-block w-4 h-4 border-2 border-[#14B8A6] border-t-transparent rounded-full flex-shrink-0" />
                                    ) : (
                                      <HiOutlineDocumentText className="w-4 h-4 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                                    )}
                                    Convert to PDF
                                  </button>
                                )}
                                <div className="my-1 border-t border-gray-200 dark:border-dark-border" />
                                <button
                                  type="button"
                                  onClick={() => { setAttachmentMenuDocId(null); setDocumentToDelete(doc); }}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                                >
                                  <HiOutlineTrash className="w-4 h-4 flex-shrink-0" />
                                  Delete
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <DocumentEditorModal
                  open={!!documentToEdit}
                  onClose={() => setDocumentToEdit(null)}
                  opportunityId={id ? parseInt(id, 10) : null}
                  document={documentToEdit}
                  onSaved={async () => {
                    try {
                      const res = await opportunitiesAPI.get(id);
                      setOpportunity(res.data);
                    } catch (_) {}
                    // Keep modal open; only PDF preview reloads inside the editor
                  }}
                />

                {/* Quote emails - separate block. While finding dealers/manufacturers, show faded pulsing placeholder. */}
                {opportunity.status === 'completed' && opportunity.clins?.length > 0 && (() => {
                  let emailCount = 0;
                  let manufacturerCount = 0;
                  let dealerCount = 0;
                  opportunity.clins?.forEach((clin) => {
                    const mfr = getClinManufacturerResearchList(clin);
                    const dlr = getClinDealerResearch(clin);
                    mfr.filter((m) => m.sales_contact_email).forEach(() => { emailCount++; manufacturerCount++; });
                    dlr.filter((d) => d.sales_contact_email).forEach(() => { emailCount++; dealerCount++; });
                  });
                  const hasContactEmails = emailCount > 0;
                  const isLoading = dealersManufacturersLoading;

                  if (!isLoading && !hasContactEmails) return null;

                  const handleGenerateThenView = async () => {
                    if (isLoading) return;
                    try {
                      await opportunitiesAPI.generateQuoteEmailDrafts(id);
                      navigate(`/opportunities/${id}/quote-emails`);
                    } catch (_) {
                      navigate(`/opportunities/${id}/quote-emails`);
                    }
                  };

                  const breakdown = [];
                  if (manufacturerCount > 0) breakdown.push(`${manufacturerCount} manufacturer${manufacturerCount !== 1 ? 's' : ''}`);
                  if (dealerCount > 0) breakdown.push(`${dealerCount} dealer${dealerCount !== 1 ? 's' : ''}`);
                  const breakdownText = breakdown.length ? breakdown.join(' · ') : null;

                  return (
                    <div className={`bg-white dark:bg-dark-elevated rounded-lg border border-gray-200 dark:border-dark-border shadow-sm overflow-hidden ${isLoading ? 'animate-fade-pulse pointer-events-none' : ''}`}>
                      <div className="px-4 py-3 border-b border-gray-100 dark:border-dark-border bg-gray-50/60 dark:bg-dark-hover/60">
                        <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                          <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#0D9488] dark:text-teal-dm">
                            <HiOutlineMail className="w-4 h-4 dark:text-teal-dm" />
                          </span>
                          Quote emails
                        </h2>
                        <p className="text-xs text-gray-500 dark:text-gray-300 mt-1 ml-10">
                          {isLoading
                            ? 'Finding dealers and manufacturers… Results will appear when ready.'
                            : 'Create and send quote requests to manufacturers and dealers.'}
                        </p>
                      </div>
                      <div className="p-4 space-y-4">
                        {isLoading ? (
                          <p className="text-xs text-gray-500 dark:text-gray-300">
                            Recipients and actions will appear when research is ready.
                          </p>
                        ) : (
                          <>
                            <p className="text-xs text-gray-600 dark:text-gray-300">
                              <span className="font-semibold text-gray-900 dark:text-white">{emailCount}</span> recipient{emailCount !== 1 ? 's' : ''} with contact email
                              {breakdownText && <span className="text-gray-500 dark:text-gray-300"> ({breakdownText})</span>}
                            </p>
                            <div className="flex flex-wrap items-center gap-2">
                              <button
                                type="button"
                                onClick={() => navigate(`/opportunities/${id}/quote-emails`)}
                                className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-lg bg-[#0D9488] dark:bg-teal-dm text-white dark:text-black hover:bg-[#0f766e] dark:hover:bg-teal-600 transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                              >
                                <HiOutlineMail className="w-4 h-4 dark:text-black" />
                                View quote emails
                              </button>
                              <button
                                type="button"
                                onClick={handleGenerateThenView}
                                className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-lg border border-gray-300 dark:border-dark-border text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-hover hover:bg-gray-50 dark:hover:bg-dark-border transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                              >
                                Generate drafts
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })()}

              </div>
            </div>
        </main>
        </div>
        </div>

        {/* Delete document confirmation */}
        {documentToDelete && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-dark-elevated rounded-lg shadow-xl max-w-md w-full border border-gray-200 dark:border-dark-border">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-dark-border">
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">Delete document</h3>
              </div>
              <div className="px-6 py-4">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Remove &quot;{documentToDelete.file_name}&quot; from this opportunity? The file will be deleted from the server. This cannot be undone.
                </p>
              </div>
              <div className="px-6 py-4 border-t border-gray-200 dark:border-dark-border flex justify-end gap-2">
                <button
                  onClick={() => setDocumentToDelete(null)}
                  disabled={deleteDocumentLoading}
                  className="px-3 py-2 text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-600 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-500 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    if (!documentToDelete || !id) return;
                    setDeleteDocumentLoading(true);
                    try {
                      await opportunitiesAPI.deleteDocument(id, documentToDelete.id);
                      const res = await opportunitiesAPI.get(id);
                      setOpportunity(res.data);
                      setDocumentToDelete(null);
                      if (documentToEdit?.id === documentToDelete.id) setDocumentToEdit(null);
                    } catch (e) {
                      console.error('Delete document failed', e);
                    } finally {
                      setDeleteDocumentLoading(false);
                    }
                  }}
                  disabled={deleteDocumentLoading}
                  className="px-3 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {deleteDocumentLoading ? (
                    <>
                      <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Deleting…
                    </>
                  ) : (
                    <>
                      <HiOutlineTrash className="w-4 h-4" />
                      Delete
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Opportunity Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
            <div className="bg-white dark:bg-dark-elevated rounded-xl shadow-xl dark:shadow-none dark:ring-1 dark:ring-gray-600 max-w-md w-full border border-gray-200 dark:border-dark-border">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-dark-border">
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">Delete Opportunity</h3>
              </div>
              <div className="px-6 py-4">
                <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                  Are you sure you want to delete this opportunity? This action cannot be undone and will permanently delete all related documents, deadlines, and CLINs.
                </p>
              </div>
              <div className="px-6 py-4 border-t border-gray-200 dark:border-dark-border flex justify-end gap-2 bg-gray-50/50 dark:bg-matte/30 rounded-b-xl">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-600 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deleteLoading}
                  title="Cancel"
                  aria-label="Cancel and keep opportunity"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-4 py-2.5 text-sm font-medium text-white bg-red-600 dark:bg-red-600 rounded-lg hover:bg-red-700 dark:hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  disabled={deleteLoading}
                  title={deleteLoading ? 'Deleting...' : 'Delete'}
                  aria-label={deleteLoading ? 'Deleting...' : 'Delete opportunity permanently'}
                >
                  {deleteLoading ? (
                    <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  ) : (
                    <HiOutlineTrash className="w-5 h-5" />
                  )}
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      <SendEmailModal
        isOpen={sendEmailModal.open}
        onClose={() => setSendEmailModal((s) => ({ ...s, open: false }))}
        to={sendEmailModal.to}
        subject={sendEmailModal.subject}
        body={sendEmailModal.body}
      />
    </ProtectedRoute>
  );
};

export default OpportunityDetail;
