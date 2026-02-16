/**
 * Quote Emails Preview & Review Page
 * Auto-generates professional quote inquiry emails for dealers/manufacturers
 * Requires user review and approval before sending
 */
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI, authAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineMail,
  HiOutlineCheckCircle,
  HiOutlineX,
  HiOutlinePencil,
  HiOutlinePaperAirplane,
  HiOutlineUser,
  HiOutlineOfficeBuilding,
  HiOutlineTag,
  HiOutlineCalendar,
  HiOutlineLocationMarker,
  HiOutlineChartBar,
  HiOutlineChevronDown,
  HiOutlineChevronUp,
  HiOutlineRefresh,
} from 'react-icons/hi';
import ThemeToggle from '../components/ThemeToggle';

/** Map API draft to local shape (id, to, toName, subject, body, contactType, clinNumber, selected, editing). */
function draftToEmail(d) {
  return {
    id: d.id,
    to: d.to,
    toName: d.to_name ?? d.toName ?? '',
    subject: d.subject,
    body: d.body,
    clinId: d.clin_id,
    clinNumber: d.clin_number ?? '',
    contactType: d.contact_type ?? d.contactType ?? 'dealer',
    selected: true,
    editing: false,
  };
}

const QuoteEmailsPreview = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [opportunity, setOpportunity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [draftsLoading, setDraftsLoading] = useState(true);
  const [error, setError] = useState('');
  const [emailConnection, setEmailConnection] = useState(null);
  const [emails, setEmails] = useState([]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [expandedEmailIds, setExpandedEmailIds] = useState(new Set());
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetchOpportunity();
    fetchEmailConnection();
  }, [id]);

  useEffect(() => {
    if (id && !error) fetchDrafts();
  }, [id, error]);

  const fetchOpportunity = async () => {
    try {
      const response = await opportunitiesAPI.get(id);
      setOpportunity(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load opportunity');
    } finally {
      setLoading(false);
    }
  };

  const fetchDrafts = async () => {
    if (!id) return;
    setDraftsLoading(true);
    try {
      const res = await opportunitiesAPI.listQuoteEmailDrafts(id);
      const list = res.data?.drafts ?? [];
      setEmails(list.map(draftToEmail));
    } catch {
      setEmails([]);
    } finally {
      setDraftsLoading(false);
    }
  };

  const fetchEmailConnection = async () => {
    try {
      const res = await authAPI.getEmailConnection();
      setEmailConnection(res.data);
    } catch {
      setEmailConnection({ connected: false });
    }
  };

  const toggleEmailSelection = (emailId) => {
    setEmails((prev) =>
      prev.map((e) => (e.id === emailId ? { ...e, selected: !e.selected } : e))
    );
  };

  const toggleEdit = (emailId) => {
    setEmails((prev) => {
      const wasEditing = prev.find((e) => e.id === emailId)?.editing;
      const next = prev.map((e) => (e.id === emailId ? { ...e, editing: !e.editing } : e));
      if (wasEditing) saveDraftEdits(emailId);
      return next;
    });
  };

  const toggleExpanded = (emailId) => {
    setExpandedEmailIds((prev) => {
      const next = new Set(prev);
      if (next.has(emailId)) next.delete(emailId);
      else next.add(emailId);
      return next;
    });
  };

  const updateEmail = (emailId, field, value) => {
    setEmails((prev) =>
      prev.map((e) => (e.id === emailId ? { ...e, [field]: value } : e))
    );
  };

  const saveDraftEdits = async (emailId) => {
    const email = emails.find((e) => e.id === emailId);
    if (!email || !id) return;
    try {
      await opportunitiesAPI.updateQuoteEmailDraft(id, emailId, {
        to: email.to,
        to_name: email.toName,
        subject: email.subject,
        body: email.body,
      });
    } catch (_) {}
  };

  const handleSendBatch = async () => {
    const selectedEmails = emails.filter((e) => e.selected);
    if (selectedEmails.length === 0) {
      setSendError('Please select at least one email to send.');
      return;
    }
    if (!emailConnection?.connected) {
      setSendError('Please connect your email account first.');
      return;
    }
    setSending(true);
    setSendError('');
    try {
      for (const email of selectedEmails) {
        await authAPI.sendEmail({ to: email.to, subject: email.subject, body: email.body });
        await opportunitiesAPI.deleteQuoteEmailDraft(id, email.id);
      }
      await fetchDrafts();
      alert(`Successfully sent ${selectedEmails.length} email(s).`);
    } catch (err) {
      setSendError(err.response?.data?.detail || 'Failed to send emails. Please try again.');
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-lg text-gray-600">Loading...</div>
        </div>
      </ProtectedRoute>
    );
  }

  if (error) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-center">
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={() => navigate(`/opportunities/${id}`)}
              className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
            >
              Back to Opportunity
            </button>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  const discardEmail = async (emailId) => {
    try {
      await opportunitiesAPI.deleteQuoteEmailDraft(id, emailId);
      await fetchDrafts();
    } catch (_) {
      setEmails((prev) => prev.filter((e) => e.id !== emailId));
    }
  };

  const handleGenerateEmails = async () => {
    if (!id) return;
    setGenerating(true);
    try {
      await opportunitiesAPI.generateQuoteEmailDrafts(id);
      setExpandedEmailIds(new Set());
      await fetchDrafts();
    } catch (err) {
      setSendError(err.response?.data?.detail || 'Failed to generate emails.');
    } finally {
      setGenerating(false);
    }
  };

  const selectedCount = emails.filter((e) => e.selected).length;

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        {/* Header */}
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <ThemeToggle />
                <button
                  onClick={() => navigate(`/opportunities/${id}`)}
                  className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                  title="Back to Opportunity"
                >
                  <HiOutlineArrowLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                </button>
                <div>
                  <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Quote Emails Preview</h1>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                    {opportunity?.title || 'Review and send quote inquiry emails'}
                  </p>
                </div>
              </div>
              {emailConnection?.connected ? (
                <div className="flex items-center gap-2 text-sm text-green-700 dark:text-teal-dm">
                  <HiOutlineCheckCircle className="w-5 h-5" />
                  <span>Sending as {emailConnection.sender_email}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                  <HiOutlineX className="w-5 h-5" />
                  <span>Email not connected</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {draftsLoading ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm p-8 text-center">
              <div className="text-gray-600 dark:text-gray-400">Loading drafts…</div>
            </div>
          ) : emails.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm p-8 text-center">
              <HiOutlineMail className="w-12 h-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                {!opportunity?.clins?.length ? 'No emails to generate' : 'Generate quote emails'}
              </h2>
              <p className="text-gray-600 dark:text-gray-400 mb-4">
                {!opportunity?.clins?.length
                  ? 'No dealers or manufacturers with contact emails were found for this opportunity.'
                  : 'Build the email list from this opportunity\'s CLINs (dealers and manufacturers with contact emails). Emails are saved in the database; view shows saved drafts.'}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                {opportunity?.clins?.length > 0 && (
                  <button
                    type="button"
                    onClick={handleGenerateEmails}
                    disabled={generating}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg text-white dark:text-gray-900 bg-[#0D9488] dark:bg-teal-dm hover:bg-[#0f766e] dark:hover:bg-teal-600 border border-[#0D9488] dark:border-teal-dm disabled:opacity-50"
                  >
                    <HiOutlineRefresh className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
                    {generating ? 'Generating…' : 'Generate emails'}
                  </button>
                )}
                <button
                  onClick={() => navigate(`/opportunities/${id}`)}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500"
                >
                  Back to Opportunity
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Summary Bar */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm p-4 mb-6">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  Review each email below. Approve with the checkbox; use Discard to remove from the list. No emails are sent without your approval.
                </p>
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-6 flex-wrap">
                    <div>
                      <span className="text-sm text-gray-500 dark:text-gray-400">Total:</span>
                      <span className="ml-2 text-lg font-semibold text-gray-900 dark:text-gray-100">{emails.length}</span>
                    </div>
                    <div>
                      <span className="text-sm text-gray-500 dark:text-gray-400">Manufacturers:</span>
                      <span className="ml-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {emails.filter((e) => e.contactType === 'manufacturer').length}
                      </span>
                    </div>
                    <div>
                      <span className="text-sm text-gray-500 dark:text-gray-400">Dealers:</span>
                      <span className="ml-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {emails.filter((e) => e.contactType === 'dealer').length}
                      </span>
                    </div>
                    <div>
                      <span className="text-sm text-gray-500 dark:text-gray-400">Approved to send:</span>
                      <span className="ml-2 text-lg font-semibold text-[#0D9488] dark:text-teal-dm">{selectedCount}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleGenerateEmails}
                      disabled={generating}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-600 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-500 border border-gray-300 dark:border-gray-500 transition-colors flex items-center gap-2 disabled:opacity-50"
                      title="Rebuild the email list from opportunity CLINs (saves to database)"
                    >
                      <HiOutlineRefresh className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
                      {generating ? 'Generating…' : 'Generate emails'}
                    </button>
                    <button
                      onClick={handleSendBatch}
                      disabled={sending || selectedCount === 0 || !emailConnection?.connected}
                      className="px-6 py-2 bg-[#0D9488] dark:bg-teal-dm text-white dark:text-gray-900 rounded-lg hover:bg-[#0f766e] dark:hover:bg-teal-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      <HiOutlinePaperAirplane className="w-5 h-5" />
                      {sending ? 'Sending...' : `Send ${selectedCount} approved`}
                    </button>
                  </div>
                </div>
                {sendError && (
                  <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
                    {sendError}
                  </div>
                )}
                {!emailConnection?.connected && (
                  <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-lg text-sm text-amber-700 dark:text-amber-300">
                    Please connect your email account to send emails. Go to the opportunity detail page to connect Gmail or Outlook.
                  </div>
                )}
              </div>

              {/* Email List - Manufacturers then Dealers, compact expandable with CLIN reference */}
              <div className="space-y-4">
                {(['manufacturer', 'dealer']).map((contactType) => {
                  const sectionEmails = emails.filter((e) => e.contactType === contactType);
                  if (sectionEmails.length === 0) return null;
                  const sectionTitle = contactType === 'manufacturer' ? 'Manufacturers' : 'Dealers';
                  const SectionIcon = contactType === 'manufacturer' ? HiOutlineOfficeBuilding : HiOutlineChartBar;
                  return (
                    <div key={contactType}>
                      <div className="flex items-center gap-2 mb-2 px-1">
                        <SectionIcon className="w-5 h-5 text-[#0D9488] dark:text-teal-dm" />
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{sectionTitle}</h3>
                        <span className="text-xs text-gray-500 dark:text-gray-400">({sectionEmails.length} email{sectionEmails.length !== 1 ? 's' : ''})</span>
                      </div>
                      <div className="space-y-1">
                {sectionEmails.map((email) => {
                  const isExpanded = expandedEmailIds.has(email.id);
                  const subjectPreview = email.subject.length > 50 ? email.subject.slice(0, 50) + '…' : email.subject;
                  return (
                  <div
                    key={email.id}
                    className={`bg-white dark:bg-gray-800 rounded-lg border-2 shadow-sm overflow-hidden ${
                      email.selected ? 'border-[#0D9488] dark:border-teal-dm' : 'border-gray-200 dark:border-gray-600'
                    }`}
                  >
                    {/* Compact row */}
                    <div className="flex items-center gap-2 p-2 sm:p-3 border-b border-gray-100 dark:border-gray-600">
                      <input
                        type="checkbox"
                        checked={email.selected}
                        onChange={() => toggleEmailSelection(email.id)}
                        onClick={(e) => e.stopPropagation()}
                        title="Approve this email for sending"
                        className="w-4 h-4 text-[#0D9488] dark:text-teal-dm border-gray-300 dark:border-gray-500 rounded focus:ring-[#0D9488] dark:focus:ring-teal-dm flex-shrink-0"
                      />
                      <button
                        type="button"
                        onClick={() => toggleExpanded(email.id)}
                        className="flex-1 flex items-center gap-2 min-w-0 text-left"
                      >
                        <span className="flex items-center gap-1 text-xs font-semibold text-[#0D9488] dark:text-teal-dm bg-[#14B8A6]/10 dark:bg-teal-dm/20 px-1.5 py-0.5 rounded flex-shrink-0">
                          <HiOutlineTag className="w-3.5 h-3.5 dark:text-teal-dm" />
                          CLIN {email.clinNumber}
                        </span>
                        {email.contactType === 'manufacturer' ? (
                          <HiOutlineOfficeBuilding className="w-4 h-4 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                        ) : (
                          <HiOutlineChartBar className="w-4 h-4 text-[#0D9488] dark:text-teal-dm flex-shrink-0" />
                        )}
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{email.toName}</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400 truncate hidden sm:inline">{email.to}</span>
                        <span className="text-xs text-gray-600 dark:text-gray-400 truncate max-w-[140px] ml-auto mr-1">{subjectPreview}</span>
                        {isExpanded ? (
                          <HiOutlineChevronUp className="w-4 h-4 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                        ) : (
                          <HiOutlineChevronDown className="w-4 h-4 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                        )}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleEdit(email.id); }}
                        className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-600 rounded text-gray-600 dark:text-gray-400 hover:text-[#0D9488] dark:hover:text-teal-dm flex-shrink-0"
                        title="Edit recipient, subject and message"
                      >
                        <HiOutlinePencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); discardEmail(email.id); }}
                        className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 rounded text-gray-600 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 flex-shrink-0"
                        title="Discard this email"
                      >
                        <HiOutlineX className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Expanded content */}
                    {isExpanded && (
                    <>
                    {email.editing ? (
                      <div className="p-4 space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">To (email)</label>
                          <input
                            type="email"
                            value={email.to}
                            onChange={(e) => updateEmail(email.id, 'to', e.target.value)}
                            placeholder="recipient@example.com"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#0D9488] dark:focus:ring-teal-dm focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">To (name)</label>
                          <input
                            type="text"
                            value={email.toName || ''}
                            onChange={(e) => updateEmail(email.id, 'toName', e.target.value)}
                            placeholder="Recipient name or company"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#0D9488] dark:focus:ring-teal-dm focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Subject</label>
                          <input
                            type="text"
                            value={email.subject}
                            onChange={(e) => updateEmail(email.id, 'subject', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#0D9488] dark:focus:ring-teal-dm focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Message</label>
                          <textarea
                            value={email.body}
                            onChange={(e) => updateEmail(email.id, 'body', e.target.value)}
                            rows={12}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-500 rounded-lg focus:ring-2 focus:ring-[#0D9488] dark:focus:ring-teal-dm focus:border-transparent font-mono text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="p-4">
                        <div className="mb-3">
                          <label className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1 block">
                            Subject
                          </label>
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{email.subject}</p>
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1 block">
                            Message
                          </label>
                          {email.body && email.body.includes('<') ? (
                            <div
                              className="text-sm text-gray-700 dark:text-gray-300 font-sans bg-gray-50 dark:bg-gray-700 p-3 rounded-lg border border-gray-200 dark:border-gray-600 prose prose-sm max-w-none prose-p:my-1 prose-strong:font-semibold dark:prose-invert"
                              dangerouslySetInnerHTML={{ __html: email.body }}
                            />
                          ) : (
                            <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-sans bg-gray-50 dark:bg-gray-700 p-3 rounded-lg border border-gray-200 dark:border-gray-600">
                              {email.body}
                            </pre>
                          )}
                        </div>
                      </div>
                    )}
                    </>
                    )}
                  </div>
                  );
                })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
};

export default QuoteEmailsPreview;
