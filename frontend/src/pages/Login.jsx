/**
 * Login Page - Split Screen Design
 */
import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { authAPI } from '../utils/api';
import {
  HiOutlineLockClosed,
  HiOutlineMail,
  HiOutlineArrowRight,
} from 'react-icons/hi';
import ThemeToggle from '../components/ThemeToggle';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showVerify, setShowVerify] = useState(false);
  const [unverifiedEmail, setUnverifiedEmail] = useState('');
  const [code, setCode] = useState('');
  const { login, verifyEmail, resendVerification, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    const q = searchParams.get('error');
    if (q) {
      setError(q.replace(/[_+]/g, ' '));
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (showVerify) {
      const result = await verifyEmail(unverifiedEmail, code);
      setLoading(false);
      if (result.success) {
        navigate('/dashboard');
      } else {
        setError(result.error || 'Invalid or expired code');
      }
      return;
    }

    const result = await login(email, password);
    setLoading(false);

    if (result.success) {
      navigate('/dashboard');
    } else if (result.code === 'email_not_verified') {
      setUnverifiedEmail(email);
      setShowVerify(true);
      setError('Please verify your email first. Request a new code below and enter it.');
      setCode('');
    } else {
      setError(result.error || 'Login failed');
    }
  };

  const handleResendCode = async () => {
    setError('');
    setLoading(true);
    const result = await resendVerification(unverifiedEmail);
    setLoading(false);
    if (result.success) {
      setError('');
      setCode('');
    } else {
      setError(result.error || 'Failed to resend');
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-[#18242b] dark:bg-gray-900">
      {/* Container with green border - full screen */}
      <div className="w-full h-screen min-h-screen flex border-[7px] border-[#18242b] dark:border-gray-800 rounded-[25px] overflow-hidden bg-white dark:bg-gray-800 shadow-2xl">
        {/* Left Section - Login Form */}
        <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-white dark:bg-gray-800 relative">
        <div className="absolute top-4 right-4">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-md space-y-8">
          {/* Logo */}
          <div className="flex items-center space-x-2">
            <div className="flex flex-col space-y-0.5">
              <div className="h-1 w-8 bg-green-500 rounded"></div>
              <div className="h-1 w-8 bg-yellow-400 rounded"></div>
              <div className="h-1 w-8 bg-blue-500 rounded"></div>
            </div>
            <h1 className="text-2xl font-semibold text-[#2D1B3D] dark:text-gray-100">Sam Gov AI</h1>
          </div>

          {/* Welcome Section */}
          <div>
            <h2 className="text-3xl font-bold text-[#2D1B3D] dark:text-gray-100 mb-2">
              Welcome Back!
            </h2>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              Please Log in to your account.
            </p>
          </div>

          {/* Form */}
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 px-4 py-3 rounded-xl text-sm">
                {error}
              </div>
            )}

            {showVerify ? (
              <>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Enter the 6-digit code we sent to <strong className="text-gray-900 dark:text-gray-100">{unverifiedEmail}</strong>.
                </p>
                <div>
                  <label htmlFor="code" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Verification code
                  </label>
                  <input
                    id="code"
                    name="code"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="000000"
                    className="block w-full px-4 py-2.5 border-2 border-gray-300 dark:border-gray-500 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 dark:focus:ring-teal-dm dark:!bg-gray-600 bg-white text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={loading || code.length !== 6}
                    className="flex-1 inline-flex items-center justify-center px-4 py-2.5 border border-transparent rounded-xl text-sm font-medium text-white dark:text-gray-900 bg-[#14B8A6] dark:bg-teal-dm hover:bg-[#0D9488] dark:hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-800 focus:ring-teal-500 dark:focus:ring-teal-dm disabled:opacity-50 transition-colors"
                  >
                    {loading ? (
                      <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    ) : (
                      'Verify and sign in'
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={handleResendCode}
                    disabled={loading}
                    className="px-4 py-2.5 border-2 border-[#14B8A6] dark:border-teal-dm rounded-xl text-sm font-medium text-[#14B8A6] dark:text-teal-dm hover:bg-teal-50 dark:hover:bg-teal-dm/20 disabled:opacity-50 transition-colors"
                  >
                    Resend code
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => { setShowVerify(false); setError(''); setCode(''); }}
                  className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  ← Back to password login
                </button>
              </>
            ) : (
              <>
            {/* Email Field */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Email Address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <HiOutlineMail className="h-5 w-5 text-gray-400 dark:text-gray-500" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  className="block w-full pl-10 pr-3 py-2.5 border-2 border-gray-300 dark:border-gray-500 rounded-xl text-sm placeholder-gray-400 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-[#14B8A6] dark:focus:border-teal-dm transition-colors bg-white dark:!bg-gray-600 text-gray-900 dark:text-gray-100"
                  placeholder="tuhelrana@gmail.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <HiOutlineLockClosed className="h-5 w-5 text-gray-400 dark:text-gray-500" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  className="block w-full pl-10 pr-3 py-2.5 border-2 border-gray-300 dark:border-gray-500 rounded-xl text-sm placeholder-gray-400 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 dark:focus:ring-teal-dm focus:border-teal-500 dark:focus:border-teal-dm transition-colors bg-white dark:!bg-gray-600 text-gray-900 dark:text-gray-100"
                  placeholder="•••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {/* Continue with Google / Microsoft */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300 dark:border-gray-600" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">Or continue with</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => { window.location.href = authAPI.signinGoogleUrl(); }}
                className="inline-flex items-center justify-center px-4 py-2.5 border-2 border-gray-300 dark:border-gray-600 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-600 hover:bg-gray-50 dark:hover:bg-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-800 focus:ring-teal-500 dark:focus:ring-teal-dm transition-colors"
              >
                <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Google
              </button>
              <button
                type="button"
                onClick={() => { window.location.href = authAPI.signinMicrosoftUrl(); }}
                className="inline-flex items-center justify-center px-4 py-2.5 border-2 border-gray-300 dark:border-gray-600 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-600 hover:bg-gray-50 dark:hover:bg-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-800 focus:ring-teal-500 dark:focus:ring-teal-dm transition-colors"
              >
                <svg className="w-5 h-5 mr-2" viewBox="0 0 23 23">
                  <path fill="#f35325" d="M1 1h10v10H1z"/>
                  <path fill="#81bc06" d="M12 1h10v10H12z"/>
                  <path fill="#05a6f0" d="M1 12h10v10H1z"/>
                  <path fill="#ffba08" d="M12 12h10v10H12z"/>
                </svg>
                Microsoft
              </button>
            </div>

            {/* Remember Me & Forgot Password */}
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <input
                  id="remember-me"
                  name="remember-me"
                  type="checkbox"
                  className="h-4 w-4 text-teal-600 dark:text-teal-dm focus:ring-teal-500 dark:focus:ring-teal-dm border-gray-300 dark:border-gray-500 rounded-md bg-white dark:bg-gray-600"
                />
                <label htmlFor="remember-me" className="ml-2 block text-sm text-gray-600 dark:text-gray-400">
                  Remember me
                </label>
              </div>
              <Link to="#" className="text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300">
                Forgot password?
              </Link>
            </div>

            {/* Submit Button */}
            <div className="flex space-x-3">
              <button
                type="submit"
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center px-4 py-2.5 border border-transparent rounded-xl text-sm font-medium text-white dark:text-gray-900 bg-[#14B8A6] dark:bg-teal-dm hover:bg-[#0D9488] dark:hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-800 focus:ring-teal-500 dark:focus:ring-teal-dm disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={loading ? 'Signing in...' : 'Sign in'}
              >
                {loading ? (
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <HiOutlineArrowRight className="w-5 h-5" />
                )}
              </button>
              <Link
                to="/signup"
                className="flex-1 inline-flex items-center justify-center px-4 py-2.5 border-2 border-[#14B8A6] dark:border-teal-dm rounded-xl text-sm font-medium text-[#14B8A6] dark:text-teal-dm bg-white dark:bg-gray-600 hover:bg-teal-50 dark:hover:bg-teal-dm/20 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-800 focus:ring-teal-500 dark:focus:ring-teal-dm transition-colors"
              >
                Create account
              </Link>
            </div>
              </>
            )}
          </form>

          {/* Footer */}
          <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
            By sign up you agree to our term and that you have read our data policy
          </p>
        </div>
      </div>

      {/* Right Section - Image */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden rounded-l-3xl">
        <img
          src="/assets/Login.jpg"
          alt="Login illustration"
          className="w-full h-full object-cover"
        />
        {/* Shadow beneath image - left side */}
        <div className="absolute inset-0 shadow-[inset_-30px_0_60px_rgba(0,0,0,0.6)] pointer-events-none z-10"></div>
        {/* Optional overlay for better text readability if needed */}
        <div className="absolute inset-0 bg-gradient-to-br from-teal-900/20 to-purple-900/20"></div>
      </div>
      </div>
    </div>
  );
};

export default Login;
