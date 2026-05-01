/**
 * API service for backend communication
 */
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

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

// Response interceptor: on 401 try refresh token and retry, else redirect to login
let isRefreshing = false;
let failedQueue = [];

const processQueue = (err, token = null) => {
  failedQueue.forEach((prom) => (err ? prom.reject(err) : prom.resolve(token)));
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    // Don't retry refresh endpoint (avoid loop)
    if (originalRequest.url?.includes('/auth/refresh')) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(error);
    }

    if (originalRequest._retry === true) {
      // Already retried once; give up
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Wait for the in-flight refresh to finish, then retry with new token
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        })
        .catch((err) => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const { data } = await api.post('/api/v1/auth/refresh', { refresh_token: refreshToken });
      const newAccessToken = data?.access_token;
      if (newAccessToken) {
        localStorage.setItem('access_token', newAccessToken);
        processQueue(null, newAccessToken);
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      }
    } catch (refreshErr) {
      processQueue(refreshErr, null);
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }

    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
    return Promise.reject(error);
  }
);

const API_BASE = import.meta.env.VITE_API_URL || '';

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
  /** Contractor profile for form fill (SF 1449 etc.) */
  getProfile: () => api.get('/api/v1/auth/profile'),
  updateProfile: (data) => api.put('/api/v1/auth/profile', data),
};

export { API_BASE };

// Opportunities API
export const opportunitiesAPI = {
  create: (data) => api.post('/api/v1/opportunities', data),
  list: (params = {}) => api.get('/api/v1/opportunities', { params }),
  get: (id) => api.get(`/api/v1/opportunities/${id}`),
  delete: (id) => api.delete(`/api/v1/opportunities/${id}`),
  /** Re-run only document processing (text + classification). Does not affect CLINs or manufacturer/dealer. */
  rerunAttachments: (id) => api.post(`/api/v1/opportunities/${id}/rerun/attachments`),
  /** Re-run only CLIN (and deadline) extraction. Does not affect documents or manufacturer/dealer. */
  rerunClins: (id) => api.post(`/api/v1/opportunities/${id}/rerun/clins`),
  /** Re-run only manufacturer & dealer research (Tavily). Does not affect documents or CLINs. */
  rerunManufacturerDealer: (id) => api.post(`/api/v1/opportunities/${id}/rerun/manufacturer-dealer`),
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
  /** Add a new document to the opportunity (Save as new). file: File or Blob. Returns new document. */
  uploadNewDocument: (opportunityId, file, filename) => {
    if (!file) return Promise.reject(new Error('File is required'));
    const formData = new FormData();
    formData.append('file', file, filename || (file?.name || 'document'));
    return api.post(`/api/v1/opportunities/${opportunityId}/documents`, formData);
  },
  /** Delete a document from the opportunity (and remove file from disk). */
  deleteDocument: (opportunityId, documentId) => {
    return api.delete(`/api/v1/opportunities/${opportunityId}/documents/${documentId}`);
  },
  /** For a Word document, get the PDF document created from it for editing. 404 if none. */
  getEditablePdfDocument: (opportunityId, documentId) =>
    api.get(`/api/v1/opportunities/${opportunityId}/documents/${documentId}/editable-pdf-document`),
  /** Convert Word document to PDF: add as new attachment (keeps .docx) or overwrite existing converted PDF. Returns the PDF document. */
  createPdfFromWord: (opportunityId, documentId) =>
    api.post(`/api/v1/opportunities/${opportunityId}/documents/${documentId}/create-pdf-from-word`),
  /** Get suggested form field values from opportunity data (autofill preview). Returns { fields: { fieldName: value } }; unmapped = "-". Pass fieldValues so government fields are only filled when empty. */
  autofillPreview: (opportunityId, documentId, fieldNames, fieldTypes = null, fieldValues = null) => {
    return api.post(
      `/api/v1/opportunities/${opportunityId}/documents/${documentId}/autofill-preview`,
      {
        field_names: fieldNames,
        field_types: fieldTypes || undefined,
        field_values: fieldValues || undefined,
      },
      { timeout: 90000 }
    );
  },
};

export default api;
