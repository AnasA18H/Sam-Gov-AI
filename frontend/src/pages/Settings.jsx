/**
 * Settings Page – email/calendar connection and app preferences
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineCog,
  HiOutlineMail,
  HiOutlineCalendar,
  HiOutlineCheckCircle,
  HiOutlineX,
} from 'react-icons/hi';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft } from 'react-icons/fa';
import ThemeToggle from '../components/ThemeToggle';
import { useTheme } from '../contexts/ThemeContext';
import { HiOutlineSun, HiOutlineMoon } from 'react-icons/hi';

const Settings = () => {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const [emailConnection, setEmailConnection] = useState(null);
  const [loading, setLoading] = useState(true);

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
            <HiOutlineCog className="w-6 h-6 text-[#14B8A6]" />
            Settings
          </h1>

          {/* Email & calendar */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden mb-6">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/50">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <HiOutlineMail className="w-4 h-4 text-[#14B8A6]" />
                Email & calendar
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Connect Gmail or Outlook to send quote emails and add deadlines to your calendar.
              </p>
            </div>
            <div className="p-6">
              {loading ? (
                <p className="text-sm text-gray-500">Loading…</p>
              ) : emailConnection?.connected ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-green-700">
                    <HiOutlineCheckCircle className="w-5 h-5" />
                    <span className="text-sm font-medium">Connected</span>
                  </div>
                  <p className="text-sm text-gray-600">
                    Account: <span className="font-medium text-gray-900">{emailConnection.sender_email}</span>
                  </p>
                  <p className="text-xs text-gray-500">
                    Provider: {emailConnection.provider === 'google' ? 'Google' : 'Microsoft'}
                  </p>
                  <button
                    type="button"
                    onClick={handleDisconnect}
                    className="mt-2 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50"
                  >
                    <HiOutlineX className="w-4 h-4" />
                    Disconnect
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-gray-600">Not connected. Connect to send quote emails and sync deadlines.</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => handleConnect('google')}
                      className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      <SiGoogle className="w-5 h-5" />
                      Connect Gmail
                    </button>
                    <button
                      type="button"
                      onClick={() => handleConnect('microsoft')}
                      className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      <FaMicrosoft className="w-5 h-5" />
                      Connect Outlook
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden mb-6">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/50">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <HiOutlineSun className="w-4 h-4 text-[#14B8A6]" />
                Appearance
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Choose light or dark theme for the app.
              </p>
            </div>
            <div className="p-6 flex items-center gap-3">
              <ThemeToggle />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {theme === 'dark' ? 'Dark mode' : 'Light mode'}
              </span>
              <div className="flex rounded-lg border border-gray-200 dark:border-gray-600 p-0.5">
                <button
                  type="button"
                  onClick={() => setTheme('light')}
                  className={`px-3 py-1.5 text-sm rounded-md transition-colors ${theme === 'light' ? 'bg-[#14B8A6] text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
                >
                  <HiOutlineSun className="w-4 h-4 inline-block mr-1.5" />
                  Light
                </button>
                <button
                  type="button"
                  onClick={() => setTheme('dark')}
                  className={`px-3 py-1.5 text-sm rounded-md transition-colors ${theme === 'dark' ? 'bg-[#14B8A6] text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
                >
                  <HiOutlineMoon className="w-4 h-4 inline-block mr-1.5" />
                  Dark
                </button>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/50">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <HiOutlineCalendar className="w-4 h-4 text-[#14B8A6]" />
                Calendar
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                When connected, you can add opportunity deadlines to your Google or Outlook calendar from each opportunity.
              </p>
            </div>
            <div className="p-6">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {emailConnection?.connected
                  ? 'Use "Add to Calendar" on an opportunity to create events for its deadlines.'
                  : 'Connect email above to enable calendar sync.'}
              </p>
            </div>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
};

export default Settings;
