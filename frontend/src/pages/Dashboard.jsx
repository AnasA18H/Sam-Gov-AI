/**
 * Dashboard Page
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
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
  HiOutlineCog
} from 'react-icons/hi';

const Dashboard = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [opportunityToDelete, setOpportunityToDelete] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('newest');

  useEffect(() => {
    fetchOpportunities();
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
                <h1 className="text-lg font-semibold text-[#2D1B3D]">Sam Gov AI</h1>
              </div>
              <div className="flex items-center space-x-3">
                <span className="text-xs text-gray-600 hidden sm:inline">
                  {user?.email}
                </span>
                <button
                  onClick={() => navigate('/analyze')}
                  className="p-2 text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors"
                  title="New Analysis"
                >
                  <HiOutlinePlus className="w-5 h-5" />
                </button>
                <button
                  onClick={handleLogout}
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                  title="Logout"
                >
                  <HiOutlineLogout className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <div className="relative">
          {/* Floating Utilities Block */}
          <div className={`fixed bottom-6 right-6 z-50 transition-all duration-300 ease-in-out ${
            sidebarOpen ? 'w-80' : 'w-14'
          }`}>
            <div className="bg-white border-2 border-[#14B8A6] rounded-lg shadow-2xl overflow-hidden">
              {/* Toggle Button / Header */}
              <div className="bg-[#14B8A6] px-4 py-3 flex items-center justify-between cursor-pointer" onClick={() => setSidebarOpen(!sidebarOpen)}>
                <div className="flex items-center space-x-2">
                  <HiOutlineCog className="w-5 h-5 text-white" />
                  {sidebarOpen && (
                    <h3 className="text-sm font-semibold text-white transition-opacity duration-300">Utilities</h3>
                  )}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSidebarOpen(!sidebarOpen);
                  }}
                  className="p-1 text-white hover:bg-[#0D9488] rounded transition-colors"
                  title={sidebarOpen ? 'Collapse' : 'Expand'}
                >
                  {sidebarOpen ? (
                    <HiOutlineChevronRight className="w-5 h-5 transition-transform duration-300" />
                  ) : (
                    <HiOutlineChevronLeft className="w-5 h-5 transition-transform duration-300" />
                  )}
                </button>
              </div>

              {/* Sidebar Content */}
              <div className={`overflow-hidden transition-all duration-300 ease-in-out ${
                sidebarOpen ? 'max-h-[600px] opacity-100' : 'max-h-0 opacity-0'
              }`}>
                <div className="px-4 py-4 space-y-5 max-h-[600px] overflow-y-auto">
                  {/* Statistics */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineChartBar className="w-4 h-4 mr-1 text-[#14B8A6]" />
                      Statistics
                    </h4>
                    <div className="space-y-2">
                      <div className="flex justify-between items-center p-2 bg-gray-100 rounded-lg border border-gray-200">
                        <span className="text-sm text-gray-700">Total</span>
                        <span className="text-sm font-semibold text-black">{stats.total}</span>
                      </div>
                      <div className="flex justify-between items-center p-2 bg-[#14B8A6] bg-opacity-10 rounded-lg border border-[#14B8A6] border-opacity-20">
                        <span className="text-sm text-gray-700">Completed</span>
                        <span className="text-sm font-semibold text-[#14B8A6]">{stats.completed}</span>
                      </div>
                      <div className="flex justify-between items-center p-2 bg-gray-100 rounded-lg border border-gray-200">
                        <span className="text-sm text-gray-700">Processing</span>
                        <span className="text-sm font-semibold text-black">{stats.processing}</span>
                      </div>
                      <div className="flex justify-between items-center p-2 bg-gray-100 rounded-lg border border-gray-200">
                        <span className="text-sm text-gray-700">Failed</span>
                        <span className="text-sm font-semibold text-black">{stats.failed}</span>
                      </div>
                    </div>
                  </div>

                  {/* Search */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineSearch className="w-4 h-4 mr-1 text-[#14B8A6]" />
                      Search
                    </h4>
                    <div className="relative">
                      <HiOutlineSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="text"
                        placeholder="Search opportunities..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white"
                      />
                      {searchQuery && (
                        <button
                          onClick={() => setSearchQuery('')}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-black"
                        >
                          <HiOutlineX className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Filters */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineFilter className="w-4 h-4 mr-1 text-[#14B8A6]" />
                      Filters
                    </h4>
                    <div className="space-y-2">
                      <label className="block">
                        <select
                          value={statusFilter}
                          onChange={(e) => setStatusFilter(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white text-black"
                        >
                          <option value="all">All Status</option>
                          <option value="completed">Completed</option>
                          <option value="processing">Processing</option>
                          <option value="pending">Pending</option>
                          <option value="failed">Failed</option>
                        </select>
                      </label>
                      <label className="block">
                        <select
                          value={sortBy}
                          onChange={(e) => setSortBy(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] outline-none text-sm bg-white text-black"
                        >
                          <option value="newest">Newest First</option>
                          <option value="oldest">Oldest First</option>
                          <option value="title">Title (A-Z)</option>
                        </select>
                      </label>
                    </div>
                  </div>

                  {/* Quick Actions */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3">Quick Actions</h4>
                    <div className="space-y-2">
                      <button
                        onClick={handleRefresh}
                        disabled={loading}
                        className="w-full flex items-center justify-center px-3 py-2 text-sm text-black bg-gray-100 rounded-lg hover:bg-gray-200 border border-gray-300 transition-colors disabled:opacity-50"
                      >
                        <HiOutlineRefresh className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                      </button>
                      <button
                        onClick={handleExport}
                        disabled={opportunities.length === 0}
                        className="w-full flex items-center justify-center px-3 py-2 text-sm text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <HiOutlineDownload className="w-4 h-4 mr-2" />
                        Export JSON
                      </button>
                    </div>
                  </div>

                  {/* Help */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center">
                      <HiOutlineInformationCircle className="w-4 h-4 mr-1 text-[#14B8A6]" />
                      Help
                    </h4>
                    <div className="space-y-2 text-sm text-gray-700">
                      <p className="text-xs leading-relaxed">
                        Use the search bar to find opportunities by title, notice ID, or description.
                      </p>
                      <p className="text-xs leading-relaxed">
                        Filter by status to see only completed, processing, or failed opportunities.
                      </p>
                      <p className="text-xs leading-relaxed">
                        Click on any opportunity to view detailed information and CLINs.
                      </p>
                    </div>
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
                  <h2 className="text-xl font-semibold text-gray-900">Dashboard</h2>
                  <p className="mt-0.5 text-sm text-gray-500">
                    Welcome back, {user?.full_name || user?.email}
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
                      className="text-xs text-[#14B8A6] hover:text-[#0D9488] font-medium"
                    >
                      Clear filters
                    </button>
                  </div>
                )}
              </div>

            {/* Opportunities List */}
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="px-4 py-3 border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900">Your Opportunities</h3>
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
                          onClick={() => navigate('/analyze')}
                          className="inline-flex items-center justify-center p-2 text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors"
                          title="Start Your First Analysis"
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
                          className="text-sm text-[#14B8A6] hover:text-[#0D9488]"
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
                      className="px-4 py-3 hover:bg-gray-50 transition-colors group"
                    >
                      <div className="flex items-center justify-between">
                        <div
                          className="flex-1 min-w-0 cursor-pointer"
                          onClick={() => navigate(`/opportunities/${opp.id}`)}
                        >
                          <div className="flex items-center space-x-2">
                            <h4 className="text-sm font-medium text-gray-900 truncate">
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
                  onClick={handleDeleteCancel}
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={deletingId !== null}
                  title="Cancel"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={handleDeleteConfirm}
                  className="p-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
