/**
 * Dashboard Page
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import { HiOutlineTrash, HiOutlinePlus, HiOutlineLogout, HiOutlineDocumentText, HiOutlineClock, HiOutlineChevronRight } from 'react-icons/hi';

const Dashboard = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

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

  const handleDelete = async (e, opportunityId) => {
    e.stopPropagation(); // Prevent navigation to detail page
    
    if (!window.confirm('Are you sure you want to delete this opportunity? This action cannot be undone.')) {
      return;
    }

    setDeletingId(opportunityId);
    try {
      await opportunitiesAPI.delete(opportunityId);
      // Refresh the list
      await fetchOpportunities();
    } catch (error) {
      console.error('Error deleting opportunity:', error);
      alert(error.response?.data?.detail || 'Failed to delete opportunity. Please try again.');
    } finally {
      setDeletingId(null);
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
        <main className="max-w-7xl mx-auto py-4 sm:px-6 lg:px-8">
          <div className="px-4 py-4 sm:px-0">
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Dashboard</h2>
              <p className="mt-0.5 text-sm text-gray-500">
                Welcome back, {user?.full_name || user?.email}
              </p>
            </div>

            {/* Opportunities List */}
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="px-4 py-3 border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900">Your Opportunities</h3>
              </div>
              
              <div className="divide-y divide-gray-200">
                {loading ? (
                  <div className="px-4 py-8 text-center text-sm text-gray-500">Loading...</div>
                ) : opportunities.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <p className="text-sm text-gray-500 mb-3">No opportunities yet.</p>
                    <button
                      onClick={() => navigate('/analyze')}
                      className="inline-flex items-center justify-center p-2 text-white bg-[#14B8A6] rounded-lg hover:bg-[#0D9488] transition-colors"
                      title="Start Your First Analysis"
                    >
                      <HiOutlinePlus className="w-5 h-5" />
                    </button>
                  </div>
                ) : (
                  opportunities.map((opp) => (
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
                            onClick={(e) => handleDelete(e, opp.id)}
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
    </ProtectedRoute>
  );
};

export default Dashboard;
