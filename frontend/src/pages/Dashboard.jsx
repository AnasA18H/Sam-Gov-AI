/**
 * Dashboard Page
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI, authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft } from 'react-icons/fa';
import {
  HiOutlineTrash,
  HiOutlinePlus,
  HiOutlineLogout,
  HiOutlineDocumentText,
  HiOutlineClock,
  HiOutlineChevronRight,
  HiOutlineArrowLeft,
  HiOutlineSearch,
  HiOutlineFilter,
  HiOutlineX,
  HiOutlineRefresh,
  HiOutlineDownload,
  HiOutlineInformationCircle,
  HiOutlineChartBar,
  HiOutlineMenu,
  HiOutlineChevronLeft,
  HiOutlineChevronDown,
  HiOutlineChevronUp,
  HiOutlineCog,
  HiOutlineUser,
  HiOutlineMail,
  HiOutlineCheckCircle
} from 'react-icons/hi';
import ThemeToggle from '../components/ThemeToggle';

const Dashboard = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [opportunityToDelete, setOpportunityToDelete] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('newest');
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [emailConnection, setEmailConnection] = useState(null);
  const [emailConnectionLoading, setEmailConnectionLoading] = useState(true);
  const [showAnalyzeConfirm, setShowAnalyzeConfirm] = useState(false);

  useEffect(() => {
    fetchOpportunities();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setEmailConnectionLoading(true);
      try {
        const res = await authAPI.getEmailConnection();
        if (!cancelled) setEmailConnection(res.data);
      } catch {
        if (!cancelled) setEmailConnection({ connected: false });
      } finally {
        if (!cancelled) setEmailConnectionLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const fetchOpportunities = async () => {
    try {
      const response = await opportunitiesAPI.list();
      setOpportunities(response.data.opportunities || []);
    } catch (error) {
      console.error('Error fetching opportunities:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleDeleteClick = (e, opportunityId) => {
    e.stopPropagation(); // Prevent navigation to detail page
    setOpportunityToDelete(opportunityId);
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    if (!opportunityToDelete) return;
    
    setDeletingId(opportunityToDelete);
    setShowDeleteConfirm(false);
    
    try {
      await opportunitiesAPI.delete(opportunityToDelete);
      // Refresh the list
      await fetchOpportunities();
    } catch (error) {
      console.error('Error deleting opportunity:', error);
      alert(error.response?.data?.detail || 'Failed to delete opportunity. Please try again.');
    } finally {
      setDeletingId(null);
      setOpportunityToDelete(null);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteConfirm(false);
    setOpportunityToDelete(null);
  };

  /** Navigate to Analyze; if email/calendar not connected, ask user to confirm first. */
  const goToAnalyze = () => {
    if (!emailConnectionLoading && !emailConnection?.connected) {
      setShowAnalyzeConfirm(true);
      return;
    }
    navigate('/analyze');
  };

  const handleAnalyzeConfirmContinue = () => {
    setShowAnalyzeConfirm(false);
    navigate('/analyze');
  };

  // Calculate statistics
  const stats = {
    total: opportunities.length,
    completed: opportunities.filter(opp => opp.status === 'completed').length,
    processing: opportunities.filter(opp => opp.status === 'processing' || opp.status === 'pending').length,
    failed: opportunities.filter(opp => opp.status === 'failed').length,
  };

  // Filter and sort opportunities
  const filteredAndSortedOpportunities = opportunities
    .filter(opp => {
      // Search filter
      const matchesSearch = !searchQuery || 
        (opp.title || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (opp.notice_id || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (opp.description || '').toLowerCase().includes(searchQuery.toLowerCase());
      
      // Status filter
      const matchesStatus = statusFilter === 'all' || opp.status === statusFilter;
      
      return matchesSearch && matchesStatus;
    })
    .sort((a, b) => {
      if (sortBy === 'newest') {
        return new Date(b.created_at) - new Date(a.created_at);
      } else if (sortBy === 'oldest') {
        return new Date(a.created_at) - new Date(b.created_at);
      } else if (sortBy === 'title') {
        return (a.title || '').localeCompare(b.title || '');
      }
      return 0;
    });

  const handleExport = () => {
    // Export opportunities as JSON
    const dataStr = JSON.stringify(opportunities, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `opportunities_${new Date().toISOString().split('T')[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleRefresh = () => {
    setLoading(true);
    fetchOpportunities();
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 dark:bg-matte">
        {/* Navigation */}
        <nav className="bg-white dark:bg-dark-surface border-b border-gray-200 dark:border-dark-border shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <button
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-2.5 rounded-xl py-1.5 pr-2 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
              >
                <div className="flex flex-col space-y-0.5">
                  <div className="h-0.5 w-6 bg-green-500 rounded" />
                  <div className="h-0.5 w-6 bg-yellow-400 rounded" />
                  <div className="h-0.5 w-6 bg-blue-500 rounded" />
                </div>
                <span className="text-xl font-semibold text-[#2D1B3D] dark:text-white tracking-tight">Sam Gov AI</span>
              </button>
              <div className="flex items-center gap-2 sm:gap-4">
                <ThemeToggle />
                {!emailConnectionLoading && (
                  <>
                    {emailConnection?.connected ? (
                      <span className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-300 px-4 py-2 rounded-xl bg-gray-100 dark:bg-dark-hover border border-gray-200 dark:border-dark-border">
                        <HiOutlineCheckCircle className="w-4 h-4 text-green-600 dark:text-teal-dm shrink-0" />
                        <span className="capitalize">{emailConnection.provider || 'Email'}</span>
                      </span>
                    ) : (
                      <div className="hidden sm:flex items-center gap-2">
                        <a href={authAPI.connectGoogleUrl()} className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-xl border border-[#14B8A6]/50 dark:border-teal-dm/50 text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/10 transition-colors min-w-[5.5rem] justify-center">
                          <SiGoogle className="w-4 h-4 shrink-0" />
                          Gmail
                        </a>
                        <a href={authAPI.connectMicrosoftUrl()} className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-xl border border-[#14B8A6]/50 dark:border-teal-dm/50 text-[#0D9488] dark:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/10 transition-colors min-w-[5.5rem] justify-center">
                          <FaMicrosoft className="w-4 h-4 shrink-0" aria-hidden />
                          Outlook
                        </a>
                      </div>
                    )}
                  </>
                )}
                <button
                  onClick={goToAnalyze}
                  className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white dark:text-gray-900 bg-[#14B8A6] dark:bg-teal-dm rounded-xl hover:bg-[#0D9488] dark:hover:bg-teal-600 transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black shadow-sm"
                  title="New Analysis — add opportunity by notice ID or URL"
                  aria-label="New Analysis"
                >
                  <HiOutlinePlus className="w-5 h-5" />
                  <span className="hidden sm:inline">New</span>
                </button>

                <div className="relative">
                  <button
                    onClick={() => setUserMenuOpen(!userMenuOpen)}
                    className="flex items-center gap-3 pl-1 pr-2.5 py-1.5 rounded-xl hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6]/30 dark:focus:ring-teal-dm/30 focus:ring-offset-2 dark:focus:ring-offset-black"
                    aria-expanded={userMenuOpen}
                    aria-haspopup="true"
                    title="Account menu"
                    aria-label="Account menu"
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
                className="p-2 text-white dark:text-black hover:bg-[#0D9488] dark:hover:bg-teal-400 rounded-md transition-colors flex-shrink-0 mr-1"
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
                  onClick={() => setSidebarOpen(true)}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center"
                  title="Open Statistics"
                  aria-label="Open Statistics panel"
                >
                  <HiOutlineChartBar className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center"
                  title="Open Search"
                  aria-label="Open Search panel"
                >
                  <HiOutlineSearch className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 w-10 h-10 flex items-center justify-center"
                  title="Open Filters"
                  aria-label="Open Filters panel"
                >
                  <HiOutlineFilter className="w-5 h-5" />
                </button>
                <div className="h-px w-8 bg-gray-200 dark:bg-dark-hover my-1"></div>
                <button
                  onClick={handleRefresh}
                  disabled={loading}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center"
                  title="Refresh opportunities list"
                  aria-label="Refresh opportunities list"
                >
                  <HiOutlineRefresh className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={handleExport}
                  disabled={opportunities.length === 0}
                  className="p-2.5 text-gray-600 dark:text-gray-300 hover:text-[#14B8A6] dark:hover:text-teal-dm hover:bg-[#14B8A6]/10 dark:hover:bg-teal-dm/20 rounded-lg transition-all duration-200 disabled:opacity-50 w-10 h-10 flex items-center justify-center"
                  title="Export opportunities to JSON"
                  aria-label="Export opportunities to JSON"
                >
                  <HiOutlineDownload className="w-5 h-5" />
                </button>
              </div>
            )}

            {/* Expanded View - Full Content */}
            <div className={`flex-1 overflow-hidden transition-all duration-300 ease-in-out ${
              sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none absolute inset-0'
            }`}>
              <div className="px-4 py-5 space-y-6 h-full overflow-y-auto scrollbar-hidden">
                  {/* Statistics */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineChartBar className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Statistics
                    </h4>
                    <div className="bg-gray-50 dark:bg-dark-hover/50 rounded-lg border border-gray-200 dark:border-dark-border p-4 space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Total</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{stats.total}</span>
                      </div>
                      <div className="h-px bg-gray-200 dark:bg-dark-hover"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Completed</span>
                        <span className="text-sm font-bold text-[#14B8A6] dark:text-teal-dm">{stats.completed}</span>
                      </div>
                      <div className="h-px bg-gray-200"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Processing</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{stats.processing}</span>
                      </div>
                      <div className="h-px bg-gray-200"></div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Failed</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-white">{stats.failed}</span>
                      </div>
                    </div>
                  </div>

                  {/* Search */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineSearch className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Search
                    </h4>
                    <div className="relative">
                      <HiOutlineSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                      <input
                        type="text"
                        placeholder="Search opportunities..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-10 py-2.5 border border-gray-300 dark:border-dark-border rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white dark:bg-dark-hover text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 transition-all"
                      />
                      {searchQuery && (
                        <button
                          onClick={() => setSearchQuery('')}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 rounded p-0.5 transition-colors"
                          title="Clear search"
                          aria-label="Clear search"
                        >
                          <HiOutlineX className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Filters */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineFilter className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Filters
                    </h4>
                    <div className="space-y-3">
                      <label className="block">
                        <span className="block text-xs text-gray-600 mb-1.5">Status</span>
                        <select
                          value={statusFilter}
                          onChange={(e) => setStatusFilter(e.target.value)}
                          className="w-full px-3 py-2.5 border border-gray-300 dark:border-dark-border rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white dark:bg-dark-hover text-gray-900 dark:text-white transition-all cursor-pointer"
                        >
                          <option value="all">All Status</option>
                          <option value="completed">Completed</option>
                          <option value="processing">Processing</option>
                          <option value="pending">Pending</option>
                          <option value="failed">Failed</option>
                        </select>
                      </label>
                      <label className="block">
                        <span className="block text-xs text-gray-600 mb-1.5">Sort By</span>
                        <select
                          value={sortBy}
                          onChange={(e) => setSortBy(e.target.value)}
                          className="w-full px-3 py-2.5 border border-gray-300 dark:border-dark-border rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white dark:bg-dark-hover text-gray-900 dark:text-white transition-all cursor-pointer"
                        >
                          <option value="newest">Newest First</option>
                          <option value="oldest">Oldest First</option>
                          <option value="title">Title (A-Z)</option>
                        </select>
                      </label>
                    </div>
                  </div>

                  {/* Email & calendar */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineMail className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Email & calendar
                    </h4>
                    {emailConnectionLoading ? (
                      <p className="text-xs text-gray-500">Loading…</p>
                    ) : emailConnection?.connected ? (
                      <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                        <HiOutlineCheckCircle className="w-4 h-4 flex-shrink-0" />
                        <span>Connected ({emailConnection.provider === 'google' ? 'Gmail' : 'Outlook'})</span>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-xs text-gray-600">Connect to send quote emails and add deadlines to your calendar.</p>
                        <div className="flex flex-col gap-2">
                          <a
                            href={authAPI.connectGoogleUrl()}
                            className="w-full inline-flex items-center justify-center gap-2 text-sm px-3 py-2 rounded-lg border-2 border-[#14B8A6] text-[#0D9488] hover:bg-[#14B8A6]/10 font-medium transition-colors"
                          >
                            <SiGoogle className="w-4 h-4" />
                            Connect Gmail
                          </a>
                          <a
                            href={authAPI.connectMicrosoftUrl()}
                            className="w-full inline-flex items-center justify-center gap-2 text-sm px-3 py-2 rounded-lg border-2 border-[#14B8A6] text-[#0D9488] hover:bg-[#14B8A6]/10 font-medium transition-colors"
                          >
                            <FaMicrosoft className="w-4 h-4" aria-hidden />
                            Connect Outlook
                          </a>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Quick Actions */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3">Quick Actions</h4>
                    <div className="space-y-2.5">
                      <button
                        onClick={handleRefresh}
                        disabled={loading}
                        className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-hover rounded-lg hover:bg-gray-100 dark:hover:bg-dark-border border border-gray-300 dark:border-dark-border hover:border-gray-400 dark:hover:border-gray-500 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:ring-offset-2 dark:focus:ring-offset-black"
                      >
                        <HiOutlineRefresh className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                      </button>
                      <button
                        onClick={handleExport}
                        disabled={opportunities.length === 0}
                        className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow"
                      >
                        <HiOutlineDownload className="w-4 h-4 mr-2" />
                        Export JSON
                      </button>
                    </div>
                  </div>

                  {/* Help */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineInformationCircle className="w-4 h-4 mr-2 text-[#14B8A6] dark:text-teal-dm" />
                      Help
                    </h4>
                    <div className="space-y-2.5 text-sm app-note rounded-lg p-3">
                      <p className="text-xs leading-relaxed">
                        <span className="font-medium">Search:</span> Find opportunities by title, notice ID, or description.
                      </p>
                      <p className="text-xs leading-relaxed">
                        <span className="font-medium">Filter:</span> View opportunities by status or sort order.
                      </p>
                      <p className="text-xs leading-relaxed">
                        <span className="font-medium">Click:</span> Any opportunity to view detailed information and CLINs.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          {/* Main Content Area */}
          <main className="max-w-7xl mx-auto py-4 sm:px-6 lg:px-8">
            <div className="px-4 py-4 sm:px-0">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Dashboard</h2>
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-300">
                    Welcome back, {user?.full_name || user?.email}
                  </p>
                  <p className="mt-1 text-[11px] font-medium app-note inline-block">
                    Your opportunities from SAM.gov appear here. Use the + button to add one; open the left panel to search and filter.
                  </p>
                </div>
                {(searchQuery || statusFilter !== 'all') && (
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-500">
                      Showing {filteredAndSortedOpportunities.length} of {opportunities.length}
                    </span>
                    <button
                      onClick={() => {
                        setSearchQuery('');
                        setStatusFilter('all');
                      }}
                      className="text-xs text-[#14B8A6] dark:text-teal-dm hover:text-[#0D9488] dark:hover:text-teal-400 font-medium"
                    >
                      Clear filters
                    </button>
                  </div>
                )}
              </div>

            {/* Opportunities List */}
            <div className="bg-white dark:bg-dark-elevated rounded-lg border border-gray-200 dark:border-dark-border shadow-sm">
              <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Your Opportunities</h3>
                <p className="text-xs app-note mt-0.5 inline-block">Click a card to open details, CLINs, and documents.</p>
              </div>
              
              <div className="divide-y divide-gray-200">
                {loading ? (
                  <div className="px-4 py-8 text-center text-sm text-gray-500">Loading...</div>
                ) : filteredAndSortedOpportunities.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    {opportunities.length === 0 ? (
                      <>
                        <p className="text-sm text-gray-500 mb-3">No opportunities yet.</p>
                        <button
                          onClick={goToAnalyze}
                          className="inline-flex items-center justify-center p-2 text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors"
                          title="Start your first analysis"
                          aria-label="Start your first analysis"
                        >
                          <HiOutlinePlus className="w-5 h-5" />
                        </button>
                      </>
                    ) : (
                      <>
                        <p className="text-sm text-gray-500 mb-3">No opportunities match your filters.</p>
                        <button
                          onClick={() => {
                            setSearchQuery('');
                            setStatusFilter('all');
                          }}
                          className="text-sm text-[#14B8A6] hover:text-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2 rounded px-1"
                        >
                          Clear filters
                        </button>
                      </>
                    )}
                  </div>
                ) : (
                  filteredAndSortedOpportunities.map((opp) => (
                    <div
                      key={opp.id}
                      className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-dark-hover/50 transition-colors group"
                    >
                      <div className="flex items-center justify-between">
                        <div
                          className="flex-1 min-w-0 cursor-pointer"
                          onClick={() => navigate(`/opportunities/${opp.id}`)}
                        >
                          <div className="flex items-center space-x-2">
                            <h4 className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {opp.title || 'Untitled Opportunity'}
                            </h4>
                            <span className={`px-2 py-0.5 rounded-lg text-xs font-medium flex-shrink-0 ${
                              opp.status === 'completed' ? 'bg-green-50 text-green-700 border border-green-200' :
                              opp.status === 'processing' ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' :
                              opp.status === 'failed' ? 'bg-red-50 text-red-700 border border-red-200' :
                              'bg-gray-50 text-gray-700 border border-gray-200'
                            }`}>
                              {opp.status}
                            </span>
                          </div>
                          <div className="mt-1.5 flex items-center space-x-3 text-xs text-gray-500">
                            <span className="flex items-center">
                              <HiOutlineDocumentText className="w-3.5 h-3.5 mr-1" />
                              {opp.notice_id || 'No Notice ID'}
                            </span>
                            <span className="flex items-center">
                              <HiOutlineClock className="w-3.5 h-3.5 mr-1" />
                              {new Date(opp.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2 ml-4">
                          <button
                            onClick={(e) => handleDeleteClick(e, opp.id)}
                            disabled={deletingId === opp.id}
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Delete opportunity"
                            aria-label="Delete opportunity"
                          >
                            {deletingId === opp.id ? (
                              <span className="text-xs text-gray-400">Deleting...</span>
                            ) : (
                              <HiOutlineTrash className="w-4 h-4" />
                            )}
                          </button>
                          <HiOutlineChevronRight className="w-4 h-4 text-gray-400 group-hover:text-gray-600 transition-colors" />
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
            </div>
          </main>
        </div>

        {/* Confirm before analysis when email/calendar not connected */}
        {showAnalyzeConfirm && (
          <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
            <div className="bg-white dark:bg-dark-elevated rounded-xl shadow-xl dark:shadow-none dark:ring-1 dark:ring-gray-600 max-w-md w-full border-2 border-[#14B8A6]/40 dark:border-teal-dm/40 overflow-hidden">
              <div className="px-6 py-4 border-b border-[#14B8A6]/30 dark:border-teal-dm/30 bg-[#14B8A6]/10 dark:bg-teal-dm/10">
                <h3 className="text-base font-bold text-gray-900 dark:text-white">Email & calendar not connected</h3>
                <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">Connect to send quote emails and sync deadlines</p>
              </div>
              <div className="px-6 py-4">
                <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed mb-3">
                  Connect Gmail or Outlook to send quote emails from the app and add opportunity deadlines to your calendar. You can also connect later from any opportunity page.
                </p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Do you want to connect now or run analysis without connecting?</p>
              </div>
              <div className="px-6 py-4 border-t border-gray-200 dark:border-dark-border space-y-4 bg-gray-50/50 dark:bg-matte/30">
                <div className="flex flex-wrap gap-2">
                  <a
                    href={authAPI.connectGoogleUrl()}
                    className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-xl border-2 border-[#14B8A6] dark:border-teal-dm text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/10 hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/20 transition-colors"
                  >
                    <SiGoogle className="w-5 h-5" />
                    Connect Gmail
                  </a>
                  <a
                    href={authAPI.connectMicrosoftUrl()}
                    className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-xl border-2 border-[#14B8A6] dark:border-teal-dm text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/10 hover:bg-[#14B8A6]/20 dark:hover:bg-teal-dm/20 transition-colors"
                  >
                    <FaMicrosoft className="w-5 h-5" aria-hidden />
                    Connect Outlook
                  </a>
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    onClick={() => setShowAnalyzeConfirm(false)}
                    className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-dark-hover rounded-xl hover:bg-gray-200 dark:hover:bg-dark-border transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleAnalyzeConfirmContinue}
                    className="px-4 py-2.5 text-sm font-medium text-white dark:text-gray-900 bg-[#14B8A6] dark:bg-teal-dm rounded-xl hover:bg-[#0D9488] dark:hover:bg-teal-600 transition-colors"
                  >
                    Continue without connecting
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
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
                  onClick={handleDeleteCancel}
                  className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-dark-hover rounded-lg hover:bg-gray-200 dark:hover:bg-dark-border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deletingId !== null}
                  title="Cancel"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteConfirm}
                  className="px-4 py-2.5 text-sm font-medium text-white bg-red-600 dark:bg-red-600 rounded-lg hover:bg-red-700 dark:hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  disabled={deletingId !== null}
                  title={deletingId !== null ? 'Deleting...' : 'Delete'}
                >
                  {deletingId !== null ? (
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
    </ProtectedRoute>
  );
};

export default Dashboard;
