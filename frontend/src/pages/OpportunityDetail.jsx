/**
 * Opportunity Details/Results Page
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
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
} from 'react-icons/hi';

const OpportunityDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [expandedClins, setExpandedClins] = useState(new Set());
  const pollIntervalRef = useRef(null);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

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
            // Fetch one more time after a short delay to ensure analysis results are loaded
            stopPolling();
            setTimeout(() => {
              opportunitiesAPI.get(id)
                .then(finalResponse => {
                  setOpportunity(finalResponse.data);
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
    // Handle both enum values (from backend) and string values
    const typeStr = typeof fileType === 'string' ? fileType.toLowerCase() : String(fileType).toLowerCase();
    
    // Check if it's a PDF (handle various formats: 'pdf', 'DocumentType.PDF', etc.)
    if (typeStr === 'pdf' || typeStr.includes('pdf')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-red-600" />;
    }
    if (typeStr === 'word' || typeStr.includes('word')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-blue-600" />;
    }
    if (typeStr === 'excel' || typeStr.includes('excel')) {
      return <HiOutlineDocumentText className="w-5 h-5 text-green-600" />;
    }
    // Also check file name extension as fallback
    return <HiOutlinePaperClip className="w-5 h-5 text-gray-600" />;
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
                  className="p-2 text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
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
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2"
                  title="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
                
                {/* User Menu Banner */}
                <div className="relative">
                  <button
                    onClick={() => setUserMenuOpen(!userMenuOpen)}
                    className="flex items-center space-x-2 px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
                  >
                    <div className="flex items-center justify-center w-8 h-8 bg-[#14B8A6] text-white rounded-full text-xs font-semibold">
                      {user?.full_name ? user.full_name.charAt(0).toUpperCase() : user?.email?.charAt(0).toUpperCase() || 'U'}
                    </div>
                    <div className="hidden sm:block text-left">
                      <div className="text-xs font-medium text-gray-900">
                        {user?.full_name || 'User'}
                      </div>
                      <div className="text-xs text-gray-500 truncate max-w-[120px]">
                        {user?.email}
                      </div>
                    </div>
                    {userMenuOpen ? (
                      <HiOutlineChevronUp className="w-4 h-4 text-gray-600 hidden sm:block" />
                    ) : (
                      <HiOutlineChevronDown className="w-4 h-4 text-gray-600 hidden sm:block" />
                    )}
                  </button>

                  {/* Dropdown Menu */}
                  {userMenuOpen && (
                    <>
                      <div 
                        className="fixed inset-0 z-10" 
                        onClick={() => setUserMenuOpen(false)}
                      ></div>
                      <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-20">
                        <div className="px-4 py-3 border-b border-gray-200 sm:hidden">
                          <div className="text-sm font-medium text-gray-900">
                            {user?.full_name || 'User'}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {user?.email}
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            setUserMenuOpen(false);
                            navigate('/dashboard');
                          }}
                          className="w-full flex items-center space-x-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors focus:outline-none focus:bg-gray-100"
                        >
                          <HiOutlineArrowLeft className="w-4 h-4" />
                          <span>Dashboard</span>
                        </button>
                        <button
                          onClick={() => {
                            setUserMenuOpen(false);
                            // Add profile/settings navigation here if needed
                          }}
                          className="w-full flex items-center space-x-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors focus:outline-none focus:bg-gray-100"
                        >
                          <HiOutlineUser className="w-4 h-4" />
                          <span>Profile</span>
                        </button>
                        <button
                          onClick={() => {
                            setUserMenuOpen(false);
                            // Add settings navigation here if needed
                          }}
                          className="w-full flex items-center space-x-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors focus:outline-none focus:bg-gray-100"
                        >
                          <HiOutlineCog className="w-4 h-4" />
                          <span>Settings</span>
                        </button>
                        <div className="border-t border-gray-200 my-1"></div>
                        <button
                          onClick={() => {
                            setUserMenuOpen(false);
                            handleLogout();
                          }}
                          className="w-full flex items-center space-x-3 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors focus:outline-none focus:bg-red-50"
                        >
                          <HiOutlineLogout className="w-4 h-4" />
                          <span>Logout</span>
                        </button>
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
          <div className={`fixed left-6 top-6 bottom-6 z-40 bg-white border-2 border-[#14B8A6] rounded-xl shadow-lg transition-all duration-300 ease-in-out overflow-hidden flex flex-col ${
            sidebarOpen ? 'w-80' : 'w-20'
          }`}>
            {/* Toggle Button / Header */}
            <div 
              className="bg-[#14B8A6] h-14 flex items-center justify-between cursor-pointer hover:bg-[#0D9488] transition-colors rounded-t-lg flex-shrink-0 shadow-sm"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              <div className="flex items-center space-x-2 px-3 min-w-0">
                <HiOutlineCog className="w-5 h-5 text-white flex-shrink-0" />
                {sidebarOpen && (
                  <h3 className="text-sm font-semibold text-white transition-opacity duration-300 whitespace-nowrap">Utilities</h3>
                )}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSidebarOpen(!sidebarOpen);
                }}
                className="p-2 text-white hover:bg-[#0D9488] rounded-md transition-colors flex-shrink-0 mr-1 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-[#14B8A6]"
                title={sidebarOpen ? 'Collapse' : 'Expand'}
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
                  className="p-2.5 text-gray-600 hover:text-[#14B8A6] hover:bg-[#14B8A6] hover:bg-opacity-10 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
                  title="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={fetchOpportunity}
                  disabled={loading}
                  className="p-2.5 text-gray-600 hover:text-[#14B8A6] hover:bg-[#14B8A6] hover:bg-opacity-10 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
                  title="Refresh"
                >
                  <HiOutlineRefresh className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <div className="h-px w-8 bg-gray-200 my-1"></div>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={deleteLoading}
                  className="p-2.5 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                  title="Delete"
                >
                  <HiOutlineTrash className="w-5 h-5" />
                </button>
              </div>
            )}

            {/* Expanded View - Full Content */}
            <div className={`flex-1 overflow-hidden transition-all duration-300 ease-in-out ${
              sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none absolute inset-0'
            }`}>
              <div className="px-4 py-5 space-y-6 h-full overflow-y-auto custom-scrollbar">
                {/* Quick Actions */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3">Quick Actions</h4>
                  <div className="space-y-2.5">
                    <button
                      onClick={() => navigate('/dashboard')}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-50 rounded-lg hover:bg-gray-100 border border-gray-300 hover:border-gray-400 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
                    >
                      <HiOutlineArrowLeft className="w-4 h-4 mr-2" />
                      Back to Dashboard
                    </button>
                    <button
                      onClick={fetchOpportunity}
                      disabled={loading}
                      className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-50 rounded-lg hover:bg-gray-100 border border-gray-300 hover:border-gray-400 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
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

                {/* Summary */}
                {opportunity && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineChartBar className="w-4 h-4 mr-2 text-[#14B8A6]" />
                      Summary
                    </h4>
                    <div className="bg-gray-50 rounded-lg border border-gray-200 p-4 space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">Status</span>
                        <span className={`text-xs font-bold px-2 py-1 rounded ${
                          opportunity.status === 'completed' ? 'bg-green-100 text-green-700' :
                          opportunity.status === 'processing' ? 'bg-yellow-100 text-yellow-700' :
                          opportunity.status === 'failed' ? 'bg-red-100 text-red-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {opportunity.status}
                        </span>
                      </div>
                      <div className="h-px bg-gray-200"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">CLINs</span>
                        <span className="text-sm font-bold text-gray-900">{opportunity.clins?.length || 0}</span>
                      </div>
                      <div className="h-px bg-gray-200"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">Documents</span>
                        <span className="text-sm font-bold text-gray-900">{opportunity.documents?.length || 0}</span>
                      </div>
                      <div className="h-px bg-gray-200"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">Deadlines</span>
                        <span className="text-sm font-bold text-gray-900">{opportunity.deadlines?.length || 0}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Navigation */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3">Navigation</h4>
                  <div className="space-y-2 text-sm text-gray-600 bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700">Scroll:</span> View all sections of this opportunity.
                    </p>
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700">CLINs:</span> View extracted contract line items.
                    </p>
                    <p className="text-xs leading-relaxed">
                      <span className="font-medium text-gray-700">Documents:</span> Access all downloaded files.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

        <main className="max-w-7xl mx-auto py-4 sm:px-6 lg:px-8">
          <div className="px-4 py-4 sm:px-0">
            {/* Title Section */}
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-4">
              <div className="px-4 py-4 border-b border-gray-200">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h1 className="text-xl font-semibold text-gray-900 mb-1.5 truncate">
                      {opportunity.title || (opportunity.status === 'processing' ? 'Analyzing Opportunity...' : 'Untitled Opportunity')}
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
                        <h3 className="text-sm font-semibold text-gray-900 mb-1">Waiting to Start Analysis</h3>
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
                        <HiOutlineSparkles className="w-5 h-5 text-blue-600" />
                      </div>
                      <div className="flex-1 space-y-4">
                        <div>
                          <h3 className="text-sm font-semibold text-gray-900 mb-3">Analysis in Progress</h3>
                          
                          {/* Progress Steps */}
                          <div className="space-y-3">
                            {/* Step 1: Scraping SAM.gov Data */}
                            <div className="flex items-start space-x-3">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.title || opportunity.description || opportunity.deadlines?.length > 0
                                  ? 'bg-green-100 text-green-600' 
                                  : 'bg-blue-100 text-blue-600'
                              }`}>
                                {opportunity.title || opportunity.description || opportunity.deadlines?.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (
                                  <HiOutlineGlobe className="w-4 h-4" />
                                )}
                            </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-900">
                                  Scraping SAM.gov Data
                                </p>
                                <p className="text-xs text-gray-500 mt-0.5">
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
                            <div className="flex items-start space-x-3">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.documents && opportunity.documents.length > 0 
                                  ? 'bg-green-100 text-green-600' 
                                  : (opportunity.title || opportunity.description) && opportunity.status === 'processing'
                                    ? 'bg-blue-100 text-blue-600'
                                    : 'bg-gray-100 text-gray-400'
                              }`}>
                                {opportunity.documents && opportunity.documents.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (opportunity.title || opportunity.description) && opportunity.status === 'processing' ? (
                                  <HiOutlineDownload className="w-4 h-4" />
                                ) : (
                                  <HiOutlineDownload className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 || ((opportunity.title || opportunity.description) && opportunity.status === 'processing')
                                    ? 'text-gray-900'
                                    : 'text-gray-500'
                                }`}>
                                  Downloading Documents
                                </p>
                                <p className="text-xs text-gray-500 mt-0.5">
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
                                        <span key={doc.id || idx} className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                                          {doc.file_name && doc.file_name.length > 20 ? doc.file_name.substring(0, 20) + '...' : (doc.file_name || 'Document')}
                                        </span>
                                      ))}
                                      {opportunity.documents.length > 3 && (
                                        <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                                          +{opportunity.documents.length - 3} more
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Step 3: Extracting Text */}
                            <div className="flex items-start space-x-3">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && !opportunity.clins
                                  ? 'bg-blue-100 text-blue-600'
                                  : opportunity.clins && opportunity.clins.length > 0
                                    ? 'bg-green-100 text-green-600'
                                    : 'bg-gray-100 text-gray-400'
                              }`}>
                                {opportunity.clins && opportunity.clins.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' && !opportunity.clins ? (
                                  <HiOutlineDocumentText className="w-4 h-4" />
                                ) : (
                                  <HiOutlineDocumentText className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'text-gray-900'
                                    : 'text-gray-500'
                                }`}>
                                  Extracting Text from Documents
                                </p>
                                <p className="text-xs text-gray-500 mt-0.5">
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
                            <div className="flex items-start space-x-3">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.clins && opportunity.clins.length > 0
                                  ? 'bg-green-100 text-green-600'
                                  : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'bg-blue-100 text-blue-600'
                                    : 'bg-gray-100 text-gray-400'
                              }`}>
                                {opportunity.clins && opportunity.clins.length > 0 ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing' ? (
                                  <HiOutlineSparkles className="w-4 h-4" />
                                ) : (
                                  <HiOutlineSparkles className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.documents && opportunity.documents.length > 0 && opportunity.status === 'processing'
                                    ? 'text-gray-900'
                                    : 'text-gray-500'
                                }`}>
                                  Analyzing CLINs with AI
                                </p>
                                <p className="text-xs text-gray-500 mt-0.5">
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
                                    <div className="w-full bg-gray-200 rounded-full h-1.5">
                                      <div 
                                        className="bg-blue-600 h-1.5 rounded-full transition-all duration-500"
                                        style={{ width: '75%' }}
                                      ></div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Step 5: Complete */}
                            <div className="flex items-start space-x-3">
                              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                                opportunity.status === 'completed'
                                  ? 'bg-green-100 text-green-600'
                                  : 'bg-gray-100 text-gray-400'
                              }`}>
                                {opportunity.status === 'completed' ? (
                                  <HiOutlineCheckCircle className="w-4 h-4" />
                                ) : (
                                  <HiOutlineCheckCircle className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${
                                  opportunity.status === 'completed'
                                    ? 'text-gray-900'
                                    : 'text-gray-500'
                                }`}>
                                  Analysis Complete
                                </p>
                                <p className="text-xs text-gray-500 mt-0.5">
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
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Main Content Column */}
              <div className="lg:col-span-2 space-y-4">
                {/* Deadlines - CRITICAL */}
                {opportunity.deadlines && opportunity.deadlines.length > 0 && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-2 border-b border-gray-200">
                      <h2 className="text-sm font-semibold text-gray-900 flex items-center">
                        <HiOutlineClock className="w-4 h-4 mr-2 text-red-600" />
                        Deadlines {opportunity.deadlines.some(d => d.is_primary) && <span className="ml-2 text-xs font-normal text-red-600">(CRITICAL)</span>}
                      </h2>
                    </div>
                    <div className="p-3 space-y-2">
                      {opportunity.deadlines.map((deadline) => (
                        <div
                          key={deadline.id}
                          className={`p-2.5 rounded border ${
                            deadline.is_primary
                              ? 'border-red-300 bg-red-50'
                              : 'border-gray-200 bg-gray-50'
                          }`}
                        >
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center space-x-2 flex-1 min-w-0">
                              <HiOutlineCalendar className={`w-3.5 h-3.5 flex-shrink-0 ${deadline.is_primary ? 'text-red-600' : 'text-gray-600'}`} />
                              <div className="flex items-center space-x-2 flex-wrap">
                                <span className="text-xs font-semibold text-gray-900">
                                  {deadline.deadline_type?.replace('_', ' ').toUpperCase() || 'Deadline'}
                                </span>
                                {deadline.is_primary && (
                                  <span className="text-xs font-medium text-red-600">(PRIMARY)</span>
                                )}
                                <span className="text-sm font-semibold text-gray-900">
                                  {formatDate(deadline.due_date)}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center space-x-3 text-xs text-gray-600">
                              {deadline.timezone && (
                                <span className="flex items-center space-x-1">
                                  <HiOutlineGlobe className="w-3 h-3" />
                                  <span>{deadline.timezone}</span>
                                </span>
                              )}
                              {deadline.due_time && (
                                <span className="flex items-center space-x-1">
                                  <HiOutlineClock className="w-3 h-3" />
                                  <span>{deadline.due_time}</span>
                                </span>
                              )}
                            </div>
                          </div>
                          {deadline.description && (
                            <p className="text-xs text-gray-700 mt-1.5 ml-6">{deadline.description}</p>
                          )}
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
                      <p className={`text-sm text-gray-700 italic whitespace-pre-wrap leading-relaxed ${!isDescriptionExpanded ? 'line-clamp-3' : ''}`}>
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

                {/* CLINs - Contract Line Items */}
                {/* Empty state with fading effect when processing */}
                {(!opportunity.clins || opportunity.clins.length === 0) && (opportunity.status === 'processing' || opportunity.status === 'pending') && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm opacity-50 transition-opacity duration-500">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600" />
                        Contract Line Items (CLINs)
                      </h2>
                    </div>
                    <div className="p-4">
                      <div className="h-32 flex items-center justify-center">
                        <p className="text-sm text-gray-400">CLINs will appear here once analysis is complete...</p>
                        </div>
                    </div>
                  </div>
                )}

                {/* No CLINs found - Show when completed with 0 CLINs */}
                {(!opportunity.clins || opportunity.clins.length === 0) && opportunity.status === 'completed' && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600" />
                        Contract Line Items (CLINs)
                      </h2>
                    </div>
                    <div className="p-4">
                      <div className="flex flex-col items-center justify-center py-8 space-y-3">
                        <HiOutlineCheckCircle className="w-12 h-12 text-gray-400" />
                        <div className="text-center">
                          <p className="text-sm font-medium text-gray-700 mb-1">No CLINs found</p>
                          <p className="text-xs text-gray-500">Analysis completed. No Contract Line Items were detected in the documents.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* CLINs - Contract Line Items (when data is available) */}
                {opportunity.clins && opportunity.clins.length > 0 && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineTag className="w-5 h-5 mr-2 text-blue-600" />
                        Contract Line Items (CLINs) ({opportunity.clins.length})
                      </h2>
                    </div>
                    <div className="p-4 space-y-4">
                      {opportunity.clins.map((clin) => (
                        <div
                          key={clin.id}
                          className="bg-white rounded-lg border-2 border-gray-200 hover:border-[#14B8A6] hover:shadow-md transition-all duration-200 overflow-hidden"
                        >
                          {/* CLIN Header */}
                          <div className="bg-gradient-to-r from-[#14B8A6] to-[#0D9488] px-5 py-3">
                            <div className="flex items-center justify-between flex-wrap gap-2">
                              <div className="flex items-center space-x-3">
                                <div className="bg-white/20 backdrop-blur-sm rounded-lg px-3 py-1.5">
                                  <span className="text-white font-bold text-lg tracking-wide">
                                    CLIN {clin.clin_number}
                                  </span>
                                </div>
                                {clin.base_item_number && (
                                  <span className="text-xs text-white/90 bg-white/10 px-2.5 py-1 rounded-md font-medium">
                                    Base: {clin.base_item_number}
                                  </span>
                                )}
                              </div>
                              {clin.extended_price && (
                                <div className="text-right">
                                  <div className="text-xs text-white/80 font-medium">Total Price</div>
                                  <div className="text-white font-bold text-lg">
                                    ${clin.extended_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  </div>
                                </div>
                              )}
                            </div>
                            {clin.clin_name && (
                              <div className="mt-2 text-sm text-white/95 font-medium">
                                {clin.clin_name}
                              </div>
                            )}
                          </div>

                          {/* CLIN Content */}
                          <div className="p-5 space-y-4">
                            {/* Product Details Section */}
                            {(clin.product_name || clin.product_description || clin.manufacturer_name || clin.part_number || clin.model_number || clin.quantity || clin.contract_type || (clin.additional_data && (clin.additional_data.drawing_number || clin.additional_data.delivery_timeline || clin.additional_data.delivery_address || clin.additional_data.special_delivery_instructions))) && (
                              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                                <div className="flex items-center space-x-2 mb-3">
                                  <HiOutlineSparkles className="w-4 h-4 text-[#14B8A6]" />
                                  <h4 className="text-sm font-semibold text-gray-900">Product Details</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3 text-sm">
                                  {clin.product_name && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Name:</span>
                                      <span className="text-gray-900 font-semibold">{clin.product_name}</span>
                                    </div>
                                  )}
                                  {clin.manufacturer_name && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Manufacturer:</span>
                                      <span className="text-gray-900">{clin.manufacturer_name}</span>
                                    </div>
                                  )}
                                  {clin.part_number && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Part #:</span>
                                      <span className="text-gray-900 font-mono text-xs">{clin.part_number}</span>
                                    </div>
                                  )}
                                  {clin.model_number && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Model #:</span>
                                      <span className="text-gray-900 font-mono text-xs">{clin.model_number}</span>
                                    </div>
                                  )}
                                  {(clin.additional_data?.drawing_number || clin.drawing_number) && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Drawing #:</span>
                                      <span className="text-gray-900 font-mono text-xs">{clin.additional_data?.drawing_number || clin.drawing_number}</span>
                                    </div>
                                  )}
                                  {clin.quantity && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Quantity:</span>
                                      <span className="text-gray-900 font-semibold">
                                        {clin.quantity}
                                        {clin.unit_of_measure && (
                                          <span className="text-gray-600 font-normal ml-1">{clin.unit_of_measure}</span>
                                        )}
                                      </span>
                                    </div>
                                  )}
                                  {clin.contract_type && (
                                    <div className="flex items-start">
                                      <span className="text-gray-500 font-medium min-w-[110px] flex-shrink-0">Contract Type:</span>
                                      <span className="text-gray-900">{clin.contract_type}</span>
                                    </div>
                                  )}
                                  {expandedClins.has(clin.id) && (
                                    <>
                                      {(clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline) && (
                                        <div className="md:col-span-2">
                                          <div className="flex items-center space-x-2 mb-2">
                                            <HiOutlineClock className="w-4 h-4 text-gray-600" />
                                            <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Delivery Timeline:</div>
                                          </div>
                                          <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-white p-4 rounded-lg border border-gray-300 shadow-sm italic">
                                            {clin.additional_data?.delivery_timeline || clin.delivery_timeline || clin.timeline}
                                          </div>
                                        </div>
                                      )}
                                      {(clin.additional_data?.delivery_address) && (
                                        <div className="md:col-span-2">
                                          <div className="flex items-center space-x-2 mb-2">
                                            <HiOutlineLocationMarker className="w-4 h-4 text-gray-600" />
                                            <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Delivery Address:</div>
                                          </div>
                                          <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-white p-4 rounded-lg border border-gray-300 shadow-sm font-mono">
                                            {clin.additional_data.delivery_address}
                                          </div>
                                        </div>
                                      )}
                                      {(clin.additional_data?.special_delivery_instructions) && (
                                        <div className="md:col-span-2">
                                          <div className="flex items-center space-x-2 mb-2">
                                            <HiOutlineExclamationCircle className="w-4 h-4 text-gray-600" />
                                            <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Special Delivery Instructions:</div>
                                          </div>
                                          <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-white p-4 rounded-lg border border-gray-300 shadow-sm italic">
                                            {clin.additional_data.special_delivery_instructions}
                                          </div>
                                        </div>
                                      )}
                                    </>
                                  )}
                                </div>
                                {expandedClins.has(clin.id) && clin.product_description && (
                                  <div className="mt-3 pt-3 border-t border-gray-200">
                                    <div className="flex items-center space-x-2 mb-2">
                                      <HiOutlineTag className="w-4 h-4 text-gray-600" />
                                      <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Supplies/Services:</div>
                                    </div>
                                    <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-white p-4 rounded-lg border border-gray-300 shadow-sm italic">
                                      {clin.product_description}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Service Details Section */}
                            {expandedClins.has(clin.id) && (clin.service_description || clin.scope_of_work || clin.service_requirements) && (
                              <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                                <div className="flex items-center space-x-2 mb-3">
                                  <HiOutlineDocumentText className="w-4 h-4 text-blue-600" />
                                  <h4 className="text-sm font-semibold text-gray-900">Service Details</h4>
                                </div>
                                <div className="space-y-3 text-sm">
                                  {clin.service_description && (
                                    <div>
                                      <div className="text-xs text-gray-500 font-medium mb-1.5">Description:</div>
                                      <div className="text-gray-700 leading-relaxed whitespace-pre-wrap bg-white p-3 rounded border border-blue-200">
                                        {clin.service_description}
                                      </div>
                                    </div>
                                  )}
                                  {clin.scope_of_work && (
                                    <div>
                                      <div className="flex items-center space-x-2 mb-2">
                                        <HiOutlineDocumentText className="w-4 h-4 text-gray-600" />
                                        <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Scope of Work:</div>
                                      </div>
                                      <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-white p-4 rounded-lg border border-gray-300 shadow-sm font-bold italic">
                                        {clin.scope_of_work}
                                      </div>
                                    </div>
                                  )}
                                  {clin.service_requirements && (
                                    <div>
                                      <div className="text-xs text-gray-500 font-medium mb-1.5">Requirements:</div>
                                      <div className="text-gray-700 leading-relaxed whitespace-pre-wrap bg-white p-3 rounded border border-blue-200">
                                        {clin.service_requirements}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
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
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlinePaperClip className="w-5 h-5 mr-2 text-gray-600" />
                        Attachments ({opportunity.documents.length})
                      </h2>
                    </div>
                    <div className="p-4 space-y-2">
                      {opportunity.documents.map((doc) => (
                        <div
                          key={doc.id}
                          className="flex items-center justify-between p-2.5 bg-gray-50 rounded-lg border-2 border-gray-200 hover:bg-gray-100 hover:border-gray-300 transition-all duration-200 group focus-within:ring-2 focus-within:ring-[#14B8A6] focus-within:ring-offset-2"
                        >
                          <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                            {getFileIcon(doc.file_type)}
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-gray-900 truncate">{doc.file_name}</p>
                              <div className="flex items-center space-x-2 text-xs text-gray-500 mt-0.5">
                                <span>{formatFileSize(doc.file_size)}</span>
                                <span>•</span>
                                {/* Show file type - handle enum values */}
                                <span className="capitalize">
                                  {String(doc.file_type).toLowerCase().replace('documenttype.', '').replace('_', ' ')}
                                </span>
                                <span>•</span>
                                <span className="capitalize">{doc.source.replace('_', ' ')}</span>
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => handleViewDocument(doc.id, doc.file_type)}
                            className="ml-3 p-2 text-[#14B8A6] bg-white border-2 border-[#14B8A6] rounded-lg hover:bg-teal-50 transition-colors flex-shrink-0 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2"
                            title="View Document"
                          >
                            <HiOutlineDocumentText className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Delivery Requirements */}
                {opportunity.classification_codes?.delivery_requirements && (
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-gray-200">
                      <h2 className="text-base font-semibold text-gray-900 flex items-center">
                        <HiOutlineOfficeBuilding className="w-5 h-5 mr-2 text-green-600" />
                        Delivery Requirements
                      </h2>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                      {opportunity.classification_codes.delivery_requirements.delivery_address && (
                        <div className="pb-3 border-b border-gray-200">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Delivery Address</h3>
                          <div className="text-sm text-gray-900 space-y-1">
                            {opportunity.classification_codes.delivery_requirements.delivery_address.facility_name && (
                              <div className="font-semibold">{opportunity.classification_codes.delivery_requirements.delivery_address.facility_name}</div>
                            )}
                            {opportunity.classification_codes.delivery_requirements.delivery_address.street_address && (
                              <div>{opportunity.classification_codes.delivery_requirements.delivery_address.street_address}</div>
                            )}
                            {(opportunity.classification_codes.delivery_requirements.delivery_address.city || 
                              opportunity.classification_codes.delivery_requirements.delivery_address.state || 
                              opportunity.classification_codes.delivery_requirements.delivery_address.zip_code) && (
                              <div>
                                {[
                                  opportunity.classification_codes.delivery_requirements.delivery_address.city,
                                  opportunity.classification_codes.delivery_requirements.delivery_address.state,
                                  opportunity.classification_codes.delivery_requirements.delivery_address.zip_code
                                ].filter(Boolean).join(', ')}
                              </div>
                            )}
                            {opportunity.classification_codes.delivery_requirements.delivery_address.country && (
                              <div className="text-xs text-gray-500">{opportunity.classification_codes.delivery_requirements.delivery_address.country}</div>
                            )}
                          </div>
                        </div>
                      )}
                      {opportunity.classification_codes.delivery_requirements.fob_terms && (
                        <div className="pb-3 border-b border-gray-200">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-1">FOB Terms</h3>
                          <div className="text-sm text-gray-900 capitalize">{opportunity.classification_codes.delivery_requirements.fob_terms}</div>
                        </div>
                      )}
                      {opportunity.classification_codes.delivery_requirements.delivery_timeline && (
                        <div className="pb-3 border-b border-gray-200">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-1">Delivery Timeline</h3>
                          <div className="text-sm text-gray-900">{opportunity.classification_codes.delivery_requirements.delivery_timeline}</div>
                        </div>
                      )}
                      {opportunity.classification_codes.delivery_requirements.packing_requirements && (
                        <div className="pb-3 border-b border-gray-200">
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-1">Packing Requirements</h3>
                          <div className="text-sm text-gray-900">{opportunity.classification_codes.delivery_requirements.packing_requirements}</div>
                        </div>
                      )}
                      {opportunity.classification_codes.delivery_requirements.special_instructions && 
                       opportunity.classification_codes.delivery_requirements.special_instructions.length > 0 && (
                        <div>
                          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Special Instructions</h3>
                          <ul className="text-sm text-gray-900 space-y-1 list-disc list-inside">
                            {opportunity.classification_codes.delivery_requirements.special_instructions.map((instruction, idx) => (
                              <li key={idx}>{instruction}</li>
                            ))}
                          </ul>
                        </div>
                      )}
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
        </div>

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-base font-semibold text-gray-900">Delete Opportunity</h3>
              </div>
              <div className="px-6 py-4">
                <p className="text-sm text-gray-600">
                  Are you sure you want to delete this opportunity? This action cannot be undone and will permanently delete all related documents, deadlines, and CLINs.
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
