/**
 * OAuth callback: reads access_token and refresh_token from URL hash, stores them, then redirects to dashboard.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const AuthCallback = () => {
  const navigate = useNavigate();
  const { checkAuth } = useAuth();
  const [error, setError] = useState('');

  useEffect(() => {
    const hash = window.location.hash.slice(1);
    const params = new URLSearchParams(hash);
    const access_token = params.get('access_token');
    const refresh_token = params.get('refresh_token');

    if (!access_token || !refresh_token) {
      setError('Missing tokens from sign-in. Please try again.');
      return;
    }

    const finish = async () => {
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      await checkAuth();
      navigate('/dashboard', { replace: true });
    };

    finish().catch(() => setError('Sign-in failed. Please try again.'));
  }, [checkAuth, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#18242b]">
        <div className="text-center text-white space-y-4">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => navigate('/login', { replace: true })}
            className="px-4 py-2 rounded-xl bg-teal-500 hover:bg-teal-600 text-white"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#18242b]">
      <div className="text-white text-lg">Signing you in...</div>
    </div>
  );
};

export default AuthCallback;
