import { useState, useEffect } from 'react';
import { authAPI } from '../utils/api';

/**
 * Modal to send email from the app (user's connected Gmail/Outlook).
 * If not connected, shows Connect Gmail / Connect Outlook.
 */
export default function SendEmailModal({ isOpen, onClose, to = '', subject = '', body = '' }) {
  const [connection, setConnection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ to: '', subject: '', body: '' });

  useEffect(() => {
    if (isOpen) {
      setForm({ to, subject, body });
      setError('');
      setLoading(true);
      authAPI.getEmailConnection()
        .then((r) => setConnection(r.data))
        .catch(() => setConnection({ connected: false }))
        .finally(() => setLoading(false));
    }
  }, [isOpen, to, subject, body]);

  const handleSend = () => {
    if (!form.to?.trim()) return;
    setSending(true);
    setError('');
    authAPI.sendEmail({
      to: form.to.trim(),
      subject: form.subject?.trim() || '(No subject)',
      body: form.body?.trim() || '',
    })
      .then(() => {
        onClose();
      })
      .catch((err) => {
        setError(err.response?.data?.detail || 'Failed to send email');
      })
      .finally(() => setSending(false));
  };

  const handleConnect = (provider) => {
    const url = provider === 'google' ? authAPI.connectGoogleUrl() : authAPI.connectMicrosoftUrl();
    window.location.href = url;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Send email</h3>
        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : !connection?.connected ? (
          <div className="space-y-4">
            <p className="text-gray-600 text-sm">Connect your email to send from the app (no mail client).</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => handleConnect('google')}
                className="flex-1 px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
              >
                Connect Gmail
              </button>
              <button
                type="button"
                onClick={() => handleConnect('microsoft')}
                className="flex-1 px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
              >
                Connect Outlook
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">Sending as {connection.sender_email || connection.provider}</p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">To</label>
              <input
                type="email"
                value={form.to}
                onChange={(e) => setForm((f) => ({ ...f, to: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                placeholder="dealer@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
              <input
                type="text"
                value={form.subject}
                onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                placeholder="Quote request"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
              <textarea
                value={form.body}
                onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                placeholder="Your message…"
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg">
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={sending || !form.to?.trim()}
                className="px-4 py-2 bg-[#0D9488] text-white rounded-lg hover:bg-[#0f766e] disabled:opacity-50"
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
