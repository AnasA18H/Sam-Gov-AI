/**
 * Profile Page – view account info and contractor profile summary
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineUser,
  HiOutlineMail,
  HiOutlineShieldCheck,
  HiOutlineCog,
  HiOutlineOfficeBuilding,
  HiOutlineChevronRight,
  HiOutlinePhone,
  HiOutlineLocationMarker,
  HiOutlineIdentification,
  HiOutlineTag,
  HiOutlineDocumentText,
} from 'react-icons/hi';
import { SiGoogle } from 'react-icons/si';
import { FaMicrosoft } from 'react-icons/fa';
import ThemeToggle from '../components/ThemeToggle';

const Profile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [contractorProfile, setContractorProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authAPI.getProfile();
        if (!cancelled && res.data) setContractorProfile(res.data);
      } catch {
        if (!cancelled) setContractorProfile(null);
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

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
    return <HiOutlineMail className="w-5 h-5 text-gray-500 dark:text-gray-300" />;
  };

  const initials = (name) => {
    if (!name || typeof name !== 'string') return '?';
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return (name[0] || '?').toUpperCase();
  };

  const hasProfile = contractorProfile && (
    contractorProfile.company_name ||
    contractorProfile.company_address ||
    contractorProfile.uei ||
    contractorProfile.cage ||
    contractorProfile.contract_officer_name ||
    contractorProfile.email ||
    contractorProfile.phone
  );

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
                  onClick={() => navigate('/settings')}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-hover border border-gray-300 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-border"
                  title="Open settings"
                  aria-label="Open settings"
                >
                  <HiOutlineCog className="w-4 h-4 mr-1.5" />
                  Settings
                </button>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-hover border border-gray-300 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-border"
                  title="Back to dashboard"
                  aria-label="Back to dashboard"
                >
                  <HiOutlineArrowLeft className="w-4 h-4 mr-1.5" />
                  Dashboard
                </button>
              </div>
            </div>
          </div>
        </nav>

        <main className="max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
            <span className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#14B8A6] dark:text-teal-dm">
              <HiOutlineUser className="w-6 h-6" />
            </span>
            Profile
          </h1>

          {/* Profile header: photo + name + email + provider */}
          <div className="rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated overflow-hidden mb-6 shadow-sm transition-colors duration-200">
            <div className="p-6 sm:p-8 flex flex-col sm:flex-row items-center sm:items-start gap-6">
              <div className="flex-shrink-0 w-24 h-24 rounded-full bg-[#14B8A6]/20 dark:bg-teal-dm/30 flex items-center justify-center text-2xl font-semibold text-[#0D9488] dark:text-teal-dm border-2 border-[#14B8A6]/40 dark:border-teal-dm/50">
                {user?.full_name ? initials(user.full_name) : <HiOutlineUser className="w-12 h-12 text-[#14B8A6] dark:text-teal-dm" />}
              </div>
              <div className="flex-1 text-center sm:text-left min-w-0">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white truncate">
                  {user?.full_name || 'No name set'}
                </h2>
                <p className="text-gray-600 dark:text-gray-300 mt-0.5 flex items-center justify-center sm:justify-start gap-1.5">
                  <HiOutlineMail className="w-4 h-4 shrink-0" />
                  {user?.email || '—'}
                </p>
                <div className="mt-3 flex flex-wrap items-center justify-center sm:justify-start gap-3">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm bg-gray-100 dark:bg-dark-hover text-gray-700 dark:text-gray-300">
                    <ProviderIcon />
                    {providerLabel(user?.auth_provider)}
                  </span>
                  {user?.is_verified != null && (
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm ${user.is_verified ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' : 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300'}`}>
                      <HiOutlineShieldCheck className="w-4 h-4 shrink-0" />
                      {user.is_verified ? 'Verified' : 'Not verified'}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Two-column: Account details + Contractor profile */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated overflow-hidden shadow-sm transition-colors duration-200">
              <div className="px-5 py-4 border-b border-gray-200 dark:border-dark-border flex items-center gap-2 text-[#0D9488] dark:text-teal-dm font-medium bg-[#14B8A6]/5 dark:bg-teal-dm/10">
                <HiOutlineUser className="w-5 h-5 shrink-0" />
                <h2 className="text-base text-gray-900 dark:text-white">Account</h2>
              </div>
              <div className="p-5 text-gray-700 dark:text-gray-300 text-sm space-y-4">
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-300 block text-xs uppercase tracking-wide mb-0.5">Full name</span>
                  <span className="text-gray-900 dark:text-white">{user?.full_name || '—'}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-300 block text-xs uppercase tracking-wide mb-0.5">Email</span>
                  <span className="text-gray-900 dark:text-white">{user?.email || '—'}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-300 block text-xs uppercase tracking-wide mb-0.5">Sign-in method</span>
                  <div className="flex items-center gap-2 mt-1">
                    <ProviderIcon />
                    <span className="text-gray-900 dark:text-white">{providerLabel(user?.auth_provider)}</span>
                  </div>
                </div>
                {user?.is_verified != null && (
                  <div className="flex items-center gap-2 pt-1">
                    <HiOutlineShieldCheck className={`w-5 h-5 shrink-0 ${user.is_verified ? 'text-green-600 dark:text-green-400' : 'text-amber-500 dark:text-amber-400'}`} />
                    <span className="text-gray-600 dark:text-gray-300">
                      {user.is_verified ? 'Account verified' : 'Account not verified'}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated overflow-hidden shadow-sm transition-colors duration-200">
              <div className="px-5 py-4 border-b border-gray-200 dark:border-dark-border flex items-center justify-between bg-[#14B8A6]/5 dark:bg-teal-dm/10">
                <div className="flex items-center gap-2 text-[#0D9488] dark:text-teal-dm font-medium">
                  <HiOutlineOfficeBuilding className="w-5 h-5 shrink-0" />
                  <h2 className="text-base text-gray-900 dark:text-white">Contractor profile</h2>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/settings')}
                  className="inline-flex items-center gap-1 text-sm font-medium text-[#14B8A6] dark:text-teal-dm hover:text-[#0D9488] dark:hover:text-teal-400 transition-colors duration-200"
                  title={hasProfile ? 'Edit contractor profile in Settings' : 'Set up contractor profile in Settings'}
                  aria-label={hasProfile ? 'Edit contractor profile' : 'Set up contractor profile'}
                >
                  {hasProfile ? 'Edit' : 'Set up'}
                  <HiOutlineChevronRight className="w-4 h-4" />
                </button>
              </div>
              <div className="p-5 text-gray-700 dark:text-gray-300 text-sm space-y-4">
                {profileLoading ? (
                  <p className="text-gray-500 dark:text-gray-300">Loading…</p>
                ) : hasProfile ? (
                  <div className="space-y-4">
                    {contractorProfile.company_name && (
                      <div className="flex gap-2">
                        <HiOutlineOfficeBuilding className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">Company</span>
                          <span className="text-gray-900 dark:text-white">{contractorProfile.company_name}</span>
                        </div>
                      </div>
                    )}
                    {contractorProfile.company_address && (
                      <div className="flex gap-2">
                        <HiOutlineLocationMarker className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">Address</span>
                          <span className="text-gray-900 dark:text-white whitespace-pre-line">{contractorProfile.company_address}</span>
                        </div>
                      </div>
                    )}
                    {(contractorProfile.uei || contractorProfile.cage) && (
                      <div className="flex flex-wrap gap-4">
                        {contractorProfile.uei && (
                          <div className="flex gap-2">
                            <HiOutlineIdentification className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                            <div>
                              <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">UEI</span>
                              <span className="text-gray-900 dark:text-white">{contractorProfile.uei}</span>
                            </div>
                          </div>
                        )}
                        {contractorProfile.cage && (
                          <div className="flex gap-2">
                            <HiOutlineTag className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                            <div>
                              <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">CAGE</span>
                              <span className="text-gray-900 dark:text-white">{contractorProfile.cage}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {contractorProfile.contract_officer_name && (
                      <div className="flex gap-2">
                        <HiOutlineUser className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">Contract officer</span>
                          <span className="text-gray-900 dark:text-white">{contractorProfile.contract_officer_name}</span>
                        </div>
                      </div>
                    )}
                    {(contractorProfile.email || contractorProfile.phone) && (
                      <div className="flex flex-wrap gap-4">
                        {contractorProfile.email && (
                          <div className="flex gap-2">
                            <HiOutlineMail className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                            <div>
                              <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">Contact email</span>
                              <span className="text-gray-900 dark:text-white">{contractorProfile.email}</span>
                            </div>
                          </div>
                        )}
                        {contractorProfile.phone && (
                          <div className="flex gap-2">
                            <HiOutlinePhone className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                            <div>
                              <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-300 block">Phone</span>
                              <span className="text-gray-900 dark:text-white">{contractorProfile.phone}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {contractorProfile.digital_signature && contractorProfile.digital_signature.startsWith('data:image') && (
                      <div className="flex gap-2 pt-1">
                        <HiOutlineDocumentText className="w-4 h-4 text-[#14B8A6] dark:text-teal-dm shrink-0 mt-0.5" />
                        <span className="text-gray-500 dark:text-gray-300">Digital signature on file</span>
                      </div>
                    )}
                    <p className="text-xs app-note pt-1 border-t border-gray-200 dark:border-gray-600">Used when you autofill PDF forms (e.g. SF 1449).</p>
                  </div>
                ) : (
                  <p className="text-gray-500 dark:text-gray-300">Add your company and signer info in Settings so form autofill can use it every time.</p>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
};

export default Profile;
