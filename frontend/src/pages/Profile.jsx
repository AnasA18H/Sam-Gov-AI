/**
 * Profile Page – view account info
 */
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineUser,
  HiOutlineMail,
  HiOutlineShieldCheck,
} from 'react-icons/hi';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft } from 'react-icons/fa';
import ThemeToggle from '../components/ThemeToggle';

const Profile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const providerLabel = (p) => {
    if (!p) return 'Email';
    if (p === 'google') return 'Google';
    if (p === 'microsoft') return 'Microsoft';
    return p;
  };

  const ProviderIcon = () => {
    const p = user?.auth_provider;
    if (p === 'google') return <SiGoogle className="w-5 h-5 text-[#4285F4]" />;
    if (p === 'microsoft') return <FaMicrosoft className="w-5 h-5 text-[#00A4EF]" />;
    return <HiOutlineMail className="w-5 h-5 text-gray-500" />;
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-14 items-center">
              <div className="flex items-center space-x-2">
                <div className="flex flex-col space-y-0.5">
                  <div className="h-0.5 w-6 bg-green-500 rounded" />
                  <div className="h-0.5 w-6 bg-yellow-400 rounded" />
                  <div className="h-0.5 w-6 bg-blue-500 rounded" />
                </div>
                <span className="text-lg font-semibold text-[#2D1B3D] dark:text-gray-100">Sam Gov AI</span>
              </div>
              <div className="flex items-center gap-2">
                <ThemeToggle />
                <button
                  onClick={() => navigate('/dashboard')}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600"
                >
                <HiOutlineArrowLeft className="w-4 h-4 mr-1.5" />
                Dashboard
              </button>
              </div>
            </div>
          </div>
        </nav>

        <main className="max-w-2xl mx-auto py-8 px-4 sm:px-6">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-6 flex items-center gap-2">
            <HiOutlineUser className="w-6 h-6 text-[#14B8A6]" />
            Profile
          </h1>

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/50">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Account</h2>
              <p className="text-xs text-gray-500 mt-0.5">Your account information</p>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Full name</label>
                <p className="text-sm font-medium text-gray-900">{user?.full_name || '—'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Email</label>
                <p className="text-sm text-gray-900">{user?.email || '—'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Sign-in method</label>
                <div className="flex items-center gap-2 mt-1">
                  <ProviderIcon />
                  <span className="text-sm text-gray-900">{providerLabel(user?.auth_provider)}</span>
                </div>
              </div>
              {user?.is_verified != null && (
                <div className="flex items-center gap-2 pt-2">
                  <HiOutlineShieldCheck className="w-5 h-5 text-green-600" />
                  <span className="text-sm text-gray-600">
                    {user.is_verified ? 'Account verified' : 'Account not verified'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
};

export default Profile;
