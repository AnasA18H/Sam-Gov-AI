/**
 * API service for backend communication
 */
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Let the browser set Content-Type with boundary for FormData (required for file uploads)
    if (config.data instanceof FormData && config.headers) {
      delete config.headers['Content-Type'];
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Auth API
export const authAPI = {
  register: (data) => api.post('/api/v1/auth/register', data),
  verifyEmail: (data) => api.post('/api/v1/auth/verify-email', data),
  resendVerification: (data) => api.post('/api/v1/auth/resend-verification', data),
  login: (data) => api.post('/api/v1/auth/login', data),
  logout: () => api.post('/api/v1/auth/logout'),
  getMe: () => api.get('/api/v1/auth/me'),
  getEmailConnection: () => api.get('/api/v1/auth/email-connection'),
  disconnectEmailConnection: () => api.delete('/api/v1/auth/email-connection'),
  sendEmail: (data) => api.post('/api/v1/auth/send-email', data),
  connectGoogleUrl: () => `${API_BASE}/api/v1/auth/connect-google?access_token=${encodeURIComponent(localStorage.getItem('access_token') || '')}`,
  connectMicrosoftUrl: () => `${API_BASE}/api/v1/auth/connect-microsoft?access_token=${encodeURIComponent(localStorage.getItem('access_token') || '')}`,
  /** Sign-in with Google/Microsoft (no auth required); redirects to provider then back to /auth/callback */
  signinGoogleUrl: () => `${API_BASE}/api/v1/auth/signin/google`,
  signinMicrosoftUrl: () => `${API_BASE}/api/v1/auth/signin/microsoft`,
};

export { API_BASE };

// Opportunities API
export const opportunitiesAPI = {
  create: (data) => api.post('/api/v1/opportunities', data),
  list: (params = {}) => api.get('/api/v1/opportunities', { params }),
  get: (id) => api.get(`/api/v1/opportunities/${id}`),
  delete: (id) => api.delete(`/api/v1/opportunities/${id}`),
  getClinLookupLinks: (opportunityId, clinId) =>
    api.get(`/api/v1/opportunities/${opportunityId}/clins/${clinId}/lookup-links`),
  updateDealerEmail: (opportunityId, clinId, body) =>
    api.patch(`/api/v1/opportunities/${opportunityId}/clins/${clinId}/dealer-email`, body),
  syncCalendar: (opportunityId) =>
    api.post(`/api/v1/opportunities/${opportunityId}/sync-calendar`),
  // Quote email drafts (persisted in DB)
  listQuoteEmailDrafts: (opportunityId) =>
    api.get(`/api/v1/opportunities/${opportunityId}/quote-email-drafts`),
  generateQuoteEmailDrafts: (opportunityId) =>
    api.post(`/api/v1/opportunities/${opportunityId}/quote-email-drafts/generate`),
  deleteQuoteEmailDraft: (opportunityId, draftId) =>
    api.delete(`/api/v1/opportunities/${opportunityId}/quote-email-drafts/${draftId}`),
  updateQuoteEmailDraft: (opportunityId, draftId, body) =>
    api.patch(`/api/v1/opportunities/${opportunityId}/quote-email-drafts/${draftId}`, body),
  /** Overwrite document with new file (e.g. after in-app edit). file: File or Blob. */
  overwriteDocument: (opportunityId, documentId, file, filename) => {
    if (!file) return Promise.reject(new Error('Replacement file is required'));
    const formData = new FormData();
    formData.append('file', file, filename || (file?.name || 'document'));
    return api.put(`/api/v1/opportunities/${opportunityId}/documents/${documentId}`, formData);
  },
  /** Get PDF form fields (for editor / autofill). */
  getFormFields: (opportunityId, documentId) =>
    api.get(`/api/v1/opportunities/${opportunityId}/documents/${documentId}/form-fields`),
  /** Get opportunity form data for prefill (flat key-value). */
  getFormData: (opportunityId) =>
    api.get(`/api/v1/opportunities/${opportunityId}/form-data`),
  /** Fill PDF form. body: { fields?: {}, use_opportunity_data?: boolean, save_as_new?: boolean }. */
  fillForm: (opportunityId, documentId, body) =>
    api.post(`/api/v1/opportunities/${opportunityId}/documents/${documentId}/fill-form`, body),
};

export default api;
