/**
 * Opportunity Details/Results Page
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { opportunitiesAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
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
  HiOutlineTag,
  HiOutlineRefresh,
  HiOutlineDownload,
  HiOutlineSparkles,
  HiOutlineCheckCircle,
} from 'react-icons/hi';

const OpportunityDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const [opportunity, setOpportunity] = useState(null);
  
  const handleViewDocument = async (documentId, fileType) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/opportunities/${id}/documents/${documentId}/view`,
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
      if (fileType === 'pdf') {
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractionMessage, setExtractionMessage] = useState('');
  const pollIntervalRef = useRef(null);

  useEffect(() => {
    fetchOpportunity();
    
    // Cleanup polling on unmount
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [id]);

  const fetchOpportunity = async () => {
    try {
      const response = await opportunitiesAPI.get(id);
      setOpportunity(response.data);
      setError('');
      
      // Poll for updates if status is processing or pending
      if (response.data.status === 'processing' || response.data.status === 'pending') {
        startPolling();
      } else {
        stopPolling();
      }
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to load opportunity');
      stopPolling();
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
            // Fetch one more time after a short delay to ensure all data is loaded
            setTimeout(() => {
              opportunitiesAPI.get(id)
                .then(finalResponse => {
                  setOpportunity(finalResponse.data);
                })
                .catch(err => {
                  console.error('Final fetch error:', err);
                });
            }, 1000);
            stopPolling();
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

  const handleExtractDocuments = async () => {
    if (!opportunity || !opportunity.documents || opportunity.documents.length === 0) {
      setExtractionMessage('No documents available to extract');
      return;
    }

    setExtracting(true);
    setExtractionMessage('');
    setError('');

    try {
      const response = await opportunitiesAPI.extract(id);
      const { message, document_count } = response.data;
      setExtractionMessage(`${message}. Extraction is running in the background. Check debug extracts for results.`);
      
      // Refresh opportunity data after a delay to see updates
      setTimeout(() => {
        fetchOpportunity();
      }, 2000);
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to start text extraction. Please try again.');
      setExtractionMessage('');
    } finally {
      setExtracting(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-sm text-gray-600">Loading...</div>
        </div>
      </ProtectedRoute>
    );
  }

  if (error) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50">
          <div className="max-w-7xl mx-auto py-8 px-4">
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
              {error}
            </div>
            <button
              onClick={() => navigate('/dashboard')}
              className="mt-4 inline-flex items-center px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
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

  const getFileIcon = (fileType) => {
    switch (fileType) {
      case 'pdf':
        return <HiOutlineDocumentText className="w-5 h-5 text-red-600" />;
      case 'word':
        return <HiOutlineDocumentText className="w-5 h-5 text-blue-600" />;
      case 'excel':
        return <HiOutlineDocumentText className="w-5 h-5 text-green-600" />;
      default:
        return <HiOutlinePaperClip className="w-5 h-5 text-gray-600" />;
    }
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50">
        {/* Navigation */}
        <nav className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-14">
              <div className="flex items-center space-x-2">
                <div className="flex flex-col space-y-0.5">
                  <div className="h-0.5 w-6 bg-green-500 rounded"></div>
                  <div className="h-0.5 w-6 bg-yellow-400 rounded"></div>
                  <div className="h-0.5 w-6 bg-blue-500 rounded"></div>
                </div>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="text-lg font-semibold text-[#2D1B3D] hover:text-[#14B8A6] transition-colors"
                >
                  Sam Gov AI
                </button>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="p-2 text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deleteLoading}
                  title={deleteLoading ? 'Deleting...' : 'Delete'}
                >
                  {deleteLoading ? (
                    <svg className="animate-spin h-5 w-5 text-red-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  ) : (
                    <HiOutlineTrash className="w-5 h-5" />
                  )}
                </button>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                  title="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto py-4 sm:px-6 lg:px-8">
          <div className="px-4 py-4 sm:px-0">
            {/* Title Section */}
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-4">
              <div className="px-4 py-4 border-b border-gray-200">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h1 className="text-xl font-semibold text-gray-900 mb-1.5 truncate">
                      {opportunity.title || (opportunity.status === 'processing' ? 'Processing Opportunity...' : 'Untitled Opportunity')}
                    </h1>
                    {opportunity.notice_id && (
                      <div className="flex items-center space-x-2 text-xs text-gray-600">
                        <HiOutlineInformationCircle className="w-4 h-4 flex-shrink-0" />
                        <span>Notice ID: <span className="font-mono font-medium">{opportunity.notice_id}</span></span>
                      </div>
                    )}
                  </div>
                  <span className={`ml-4 px-3 py-1 rounded-lg text-xs font-medium flex-shrink-0 ${
                    opportunity.status === 'completed' ? 'bg-green-50 text-green-700 border border-green-200' :
                    opportunity.status === 'processing' ? 'bg-yellow-50 text-yellow-700 border border-yellow-200 animate-pulse' :
                    opportunity.status === 'failed' ? 'bg-red-50 text-red-700 border border-red-200' :
                    'bg-gray-50 text-gray-700 border border-gray-200'
                  }`}>
                    {opportunity.status}
                  </span>
                </div>
              </div>

              {/* Status Messages */}
              <div className="px-4 py-3 space-y-3">
                {opportunity.status === 'pending' && (
                  <div className="bg-white rounded-lg border-2 border-yellow-400 shadow-sm p-4">
                    <div className="flex items-start space-x-3">
                      <HiOutlineExclamationCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <h3 className="text-sm font-semibold text-gray-900 mb-1">Waiting to Start</h3>
                        <p className="text-sm text-gray-600">
                          Your request is queued and will begin processing shortly.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {opportunity.status === 'processing' && (
                  <div className="bg-white rounded-lg border-2 border-blue-400 shadow-sm p-4">
                    <div className="flex items-start space-x-3">
                      <div className="relative flex-shrink-0">
                        <HiOutlineSparkles className="w-5 h-5 text-blue-600 animate-pulse" />
                      </div>
                      <div className="flex-1 space-y-3">
                        <div>
                          <h3 className="text-sm font-semibold text-gray-900 mb-2">Processing in Progress</h3>
                          <div className="space-y-2.5">
                            <div className="flex items-center space-x-2 text-sm text-gray-700">
                              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                              <span>Accessing SAM.gov page and extracting metadata...</span>
                            </div>
                            <div className="flex items-center space-x-2 text-sm text-gray-700">
                              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                              <span>Downloading attachments and documents...</span>
                            </div>
                            <div className="flex items-center space-x-2 text-sm text-gray-700">
                              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                              <span>Extracting deadlines and contact information...</span>
                            </div>
                          </div>
                        </div>
                        <div className="pt-2 border-t border-gray-200">
                          <div className="flex items-center space-x-2 text-xs text-gray-500">
                            <HiOutlineClock className="w-3.5 h-3.5" />
                            <span>This may take a few moments. Please wait...</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {opportunity.error_message && (
                  <div className="flex items-start space-x-2 bg-red-50 border border-red-200 rounded-md p-3">
                    <HiOutlineExclamationCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-800">Error:</p>
                      <p className="text-sm text-red-700 mt-1">{opportunity.error_message}</p>
                    </div>
                  </div>
                )}

                {extractionMessage && (
                  <div className="flex items-start space-x-2 bg-blue-50 border border-blue-200 rounded-md p-3">
                    <HiOutlineCheckCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-blue-800">Extraction Started:</p>
                      <p className="text-sm text-blue-700 mt-1">{extractionMessage}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Main Content Column */}
              <div className="lg:col-span-2 space-y-4">
                {/* Deadlines - CRITICAL */}
                {opportunity.deadlines && opportunity.deadlines.length > 0 && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineClock className="w-5 h-5 mr-2 text-red-600" />
                        Deadlines {opportunity.deadlines.some(d => d.is_primary) && <span className="ml-2 text-xs font-normal text-red-600">(CRITICAL)</span>}
                      </h2>
                    </div>
                    <div className="p-4 space-y-3">
                      {opportunity.deadlines.map((deadline) => (
                        <div
                          key={deadline.id}
                          className={`p-3 rounded-lg border-2 ${
                            deadline.is_primary
                              ? 'border-red-300 bg-red-50'
                              : 'border-gray-200 bg-gray-50'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center space-x-2 mb-1.5">
                                <HiOutlineCalendar className={`w-4 h-4 flex-shrink-0 ${deadline.is_primary ? 'text-red-600' : 'text-gray-600'}`} />
                                <h3 className="text-sm font-semibold text-gray-900">
                                  {deadline.deadline_type?.replace('_', ' ').toUpperCase() || 'Deadline'}
                                  {deadline.is_primary && <span className="ml-2 text-xs font-medium text-red-600">(PRIMARY)</span>}
                                </h3>
                              </div>
                              <p className="text-base font-semibold text-gray-900 ml-6 mb-1">
                                {formatDate(deadline.due_date)}
                              </p>
                              <div className="ml-6 space-y-1 text-xs text-gray-600">
                                {deadline.timezone && (
                                  <div className="flex items-center space-x-1">
                                    <HiOutlineGlobe className="w-3.5 h-3.5" />
                                    <span>Timezone: {deadline.timezone}</span>
                                  </div>
                                )}
                                {deadline.due_time && (
                                  <div className="flex items-center space-x-1">
                                    <HiOutlineClock className="w-3.5 h-3.5" />
                                    <span>Time: {deadline.due_time}</span>
                                  </div>
                                )}
                                {deadline.description && (
                                  <p className="text-gray-700 mt-1.5">{deadline.description}</p>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Description - Read More */}
                {opportunity.description && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <div className="flex items-center">
                        <HiOutlineDocumentText className="w-5 h-5 mr-2 text-gray-600" />
                        <h2 className="text-base font-semibold text-gray-900">Description</h2>
                      </div>
                    </div>
                    <div className="px-4 py-3">
                      <p className={`text-sm text-gray-700 whitespace-pre-wrap leading-relaxed ${!isDescriptionExpanded ? 'line-clamp-3' : ''}`}>
                        {opportunity.description}
                      </p>
                      {opportunity.description.length > 200 && (
                        <button
                          onClick={() => setIsDescriptionExpanded(!isDescriptionExpanded)}
                          className="mt-2 text-sm text-blue-600 hover:text-blue-700 font-medium flex items-center space-x-1 transition-colors"
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

              </div>

              {/* Sidebar */}
              <div className="space-y-4">
                {/* Metadata */}
                <div className="bg-white rounded-lg border-2 border-green-500 shadow-sm">
                  <div className="px-4 py-3 border-b border-gray-200">
                    <h2 className="text-base font-semibold text-gray-900">Details</h2>
                  </div>
                  <dl className="px-4 py-3 space-y-3">
                    <div className="flex items-start space-x-2">
                      <dt className="flex-shrink-0 mt-0.5">
                        <HiOutlineGlobe className="w-5 h-5 text-gray-600" title="SAM.gov URL" />
                      </dt>
                      <dd className="text-sm text-gray-600 flex-1 min-w-0">
                        <a
                          href={opportunity.sam_gov_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green-600 hover:text-green-700 inline-flex items-center space-x-1 max-w-full group font-bold italic"
                        >
                          <span className="truncate text-xs font-bold italic">{opportunity.sam_gov_url}</span>
                          <HiOutlineGlobe className="w-3.5 h-3.5 flex-shrink-0 group-hover:text-green-800" />
                        </a>
                      </dd>
                    </div>

                    {opportunity.agency && (
                      <div className="flex items-start space-x-2">
                        <dt className="flex-shrink-0 mt-0.5">
                          <HiOutlineOfficeBuilding className="w-5 h-5 text-gray-600" title="Agency" />
                        </dt>
                        <dd className="text-sm text-gray-600 flex-1">{opportunity.agency}</dd>
                      </div>
                    )}

                    {opportunity.solicitation_type && (
                      <div className="flex items-start space-x-2">
                        <dt className="flex-shrink-0 mt-0.5">
                          <HiOutlineTag className="w-5 h-5 text-gray-600" title="Solicitation Type" />
                        </dt>
                        <dd className="text-sm text-gray-600 flex-1 capitalize">
                          {opportunity.solicitation_type}
                          {opportunity.classification_confidence && (
                            <span className="block text-xs text-gray-600 mt-0.5">
                              Confidence: {opportunity.classification_confidence}
                            </span>
                          )}
                        </dd>
                      </div>
                    )}

                    <div className="flex items-start space-x-2">
                      <dt className="flex-shrink-0 mt-0.5">
                        <HiOutlineCalendar className="w-5 h-5 text-gray-600" title="Created" />
                      </dt>
                      <dd className="text-sm text-gray-600 flex-1">{formatDate(opportunity.created_at)}</dd>
                    </div>

                    <div className="flex items-start space-x-2">
                      <dt className="flex-shrink-0 mt-0.5">
                        <HiOutlineRefresh className="w-5 h-5 text-gray-600" title="Updated" />
                      </dt>
                      <dd className="text-sm text-gray-600 flex-1">{formatDate(opportunity.updated_at)}</dd>
                    </div>
                  </dl>
                </div>

                {/* Documents - Attachments */}
                {opportunity.documents && opportunity.documents.length > 0 && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlinePaperClip className="w-5 h-5 mr-2 text-gray-600" />
                        Attachments ({opportunity.documents.length})
                      </h2>
                      <button
                        onClick={handleExtractDocuments}
                        disabled={extracting || opportunity.status === 'processing' || opportunity.status === 'pending'}
                        className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title={extracting ? 'Extraction in progress...' : 'Extract text from all documents'}
                      >
                        {extracting ? (
                          <>
                            <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Extracting...
                          </>
                        ) : (
                          <>
                            <HiOutlineSparkles className="w-4 h-4 mr-1.5" />
                            Extract Text
                          </>
                        )}
                      </button>
                    </div>
                    <div className="p-4 space-y-2">
                      {opportunity.documents.map((doc) => (
                        <div
                          key={doc.id}
                          className="flex items-center justify-between p-2.5 bg-gray-50 rounded-lg border-2 border-gray-200 hover:bg-gray-100 transition-colors group"
                        >
                          <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                            {getFileIcon(doc.file_type)}
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-gray-900 truncate">{doc.file_name}</p>
                              <div className="flex items-center space-x-2 text-xs text-gray-500 mt-0.5">
                                <span>{formatFileSize(doc.file_size)}</span>
                                <span>•</span>
                                <span className="capitalize">{doc.source.replace('_', ' ')}</span>
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => handleViewDocument(doc.id, doc.file_type)}
                            className="ml-3 p-2 text-[#14B8A6] bg-white border-2 border-[#14B8A6] rounded-lg hover:bg-teal-50 transition-colors flex-shrink-0"
                            title="View Document"
                          >
                            <HiOutlineDocumentText className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Contact Information */}
                {(opportunity.primary_contact || opportunity.alternative_contact || opportunity.contracting_office_address) && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineUser className="w-5 h-5 mr-2 text-gray-600" />
                        Contact Information
                      </h2>
                    </div>
                    <div className="px-4 py-3 space-y-4">
                      {opportunity.primary_contact && (
                        <div className="pb-3 border-b border-gray-200 last:border-0 last:pb-0">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Primary Point of Contact</h3>
                          <div className="space-y-1.5 text-sm text-gray-900">
                            {opportunity.primary_contact.name && (
                              <div className="flex items-center space-x-2">
                                <HiOutlineUser className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <span>{opportunity.primary_contact.name}</span>
                              </div>
                            )}
                            {opportunity.primary_contact.email && (
                              <div className="flex items-center space-x-2">
                                <HiOutlineMail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <a href={`mailto:${opportunity.primary_contact.email}`} className="text-blue-600 hover:text-blue-700 truncate">
                                  {opportunity.primary_contact.email}
                                </a>
                              </div>
                            )}
                            {opportunity.primary_contact.phone && (
                              <div className="flex items-center space-x-2">
                                <HiOutlinePhone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <a href={`tel:${opportunity.primary_contact.phone}`} className="text-gray-900">
                                  {opportunity.primary_contact.phone}
                                </a>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {opportunity.alternative_contact && (
                        <div className="pb-3 border-b border-gray-200 last:border-0 last:pb-0">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Alternative Point of Contact</h3>
                          <div className="space-y-1.5 text-sm text-gray-900">
                            {opportunity.alternative_contact.name && (
                              <div className="flex items-center space-x-2">
                                <HiOutlineUser className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <span>{opportunity.alternative_contact.name}</span>
                              </div>
                            )}
                            {opportunity.alternative_contact.email && (
                              <div className="flex items-center space-x-2">
                                <HiOutlineMail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <a href={`mailto:${opportunity.alternative_contact.email}`} className="text-blue-600 hover:text-blue-700 truncate">
                                  {opportunity.alternative_contact.email}
                                </a>
                              </div>
                            )}
                            {opportunity.alternative_contact.phone && (
                              <div className="flex items-center space-x-2">
                                <HiOutlinePhone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                <a href={`tel:${opportunity.alternative_contact.phone}`} className="text-gray-900">
                                  {opportunity.alternative_contact.phone}
                                </a>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {opportunity.contracting_office_address && (
                        <div>
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Contracting Office Address</h3>
                          <div className="flex items-start space-x-2 text-sm text-gray-900">
                            <HiOutlineOfficeBuilding className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" />
                            <p className="whitespace-pre-wrap">{opportunity.contracting_office_address}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

              </div>
            </div>
          </div>
        </main>

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-base font-semibold text-gray-900">Delete Opportunity</h3>
              </div>
              <div className="px-6 py-4">
                <p className="text-sm text-gray-600">
                  Are you sure you want to delete this opportunity? This action cannot be undone and will permanently delete all related documents and deadlines.
                </p>
              </div>
              <div className="px-6 py-4 border-t border-gray-200 flex justify-end space-x-2">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deleteLoading}
                  title="Cancel"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={handleDelete}
                  className="p-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deleteLoading}
                  title={deleteLoading ? 'Deleting...' : 'Delete'}
                >
                  {deleteLoading ? (
                    <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  ) : (
                    <HiOutlineTrash className="w-5 h-5" />
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
};

export default OpportunityDetail;
