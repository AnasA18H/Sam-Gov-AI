/**
 * Analysis Input Page - Primary SAM.gov URL input
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineDocumentText,
  HiOutlineGlobe,
  HiOutlineUpload,
  HiOutlineSearch,
  HiOutlineX,
} from 'react-icons/hi';

const Analyze = () => {
  const [samGovUrl, setSamGovUrl] = useState('');
  const [files, setFiles] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [enableDocumentAnalysis, setEnableDocumentAnalysis] = useState(false);
  const [enableClinExtraction, setEnableClinExtraction] = useState(false);
  const navigate = useNavigate();

  // Auto-disable CLIN extraction if document analysis is disabled
  const handleDocumentAnalysisToggle = (enabled) => {
    setEnableDocumentAnalysis(enabled);
    if (!enabled) {
      setEnableClinExtraction(false);
    }
  };

  const handleFileChange = (e) => {
    const selectedFiles = Array.from(e.target.files);
    setFiles(selectedFiles);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Basic URL validation
    if (!samGovUrl.trim()) {
      setError('Please enter a SAM.gov URL');
      setLoading(false);
      return;
    }

    if (!samGovUrl.includes('sam.gov')) {
      setError('Please enter a valid SAM.gov URL');
      setLoading(false);
      return;
    }

    try {
      // Create FormData for multipart/form-data request (to support file uploads)
      const formData = new FormData();
      formData.append('sam_gov_url', samGovUrl);
      formData.append('enable_document_analysis', enableDocumentAnalysis ? 'true' : 'false');
      formData.append('enable_clin_extraction', enableClinExtraction ? 'true' : 'false');
      
      // Add files if any selected
      if (files && files.length > 0) {
        files.forEach((file) => {
          formData.append('files', file);
        });
      }

      // Send request with FormData
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_BASE_URL}/api/v1/opportunities`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          // Don't set Content-Type - let browser set it with boundary for FormData
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create opportunity');
      }

      const data = await response.json();

      // Navigate to opportunity details page
      navigate(`/opportunities/${data.id}`);
    } catch (error) {
      setError(
        error.message || 'Failed to create opportunity. Please try again.'
      );
    } finally {
      setLoading(false);
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
                <button
                  onClick={() => navigate('/dashboard')}
                  className="text-lg font-semibold text-[#2D1B3D] hover:text-[#14B8A6] transition-colors focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2 rounded"
                >
                  Sam Gov AI
                </button>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition-colors"
                  title="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-4 h-4 mr-1.5" />
                  <span className="hidden sm:inline">Dashboard</span>
                </button>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-3xl mx-auto py-4 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg border border-gray-200 shadow-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 bg-[#14B8A6] rounded-t-lg">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-white/20 rounded-lg">
                  <HiOutlineSearch className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-semibold text-white">
                    Analyze SAM.gov Opportunity
                  </h1>
                  <p className="text-sm text-white/90 mt-0.5">
                    Enter a SAM.gov solicitation URL to begin automated analysis
                  </p>
                </div>
              </div>
            </div>
            <div className="px-6 py-4 rounded-b-lg">

              <form onSubmit={handleSubmit} className="space-y-6">
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center space-x-2">
                    <HiOutlineX className="w-5 h-5 flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Primary Input: SAM.gov URL */}
                <div>
                  <label htmlFor="samGovUrl" className="block text-sm font-medium text-gray-700 mb-2">
                    SAM.gov Opportunity URL <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <HiOutlineGlobe className="h-5 w-5 text-gray-400" />
                    </div>
                    <input
                      id="samGovUrl"
                      name="samGovUrl"
                      type="url"
                      required
                      className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:border-[#14B8A6] transition-all bg-white hover:border-gray-400"
                      placeholder="https://sam.gov/opp/[id]/view"
                      value={samGovUrl}
                      onChange={(e) => setSamGovUrl(e.target.value)}
                    />
                  </div>
                  <p className="mt-2 text-xs text-gray-500">
                    Enter the full URL of the SAM.gov opportunity you want to analyze
                  </p>
                </div>

                {/* Optional: File Upload */}
                <div>
                  <label htmlFor="files" className="block text-sm font-medium text-gray-700 mb-2">
                    Additional Documents <span className="text-gray-400 font-normal">(Optional)</span>
                  </label>
                  <div className="relative">
                    <label
                      htmlFor="files"
                      className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 hover:border-gray-400 transition-colors group"
                    >
                      <div className="flex flex-col items-center justify-center pt-5 pb-6">
                        <HiOutlineUpload className="w-8 h-8 mb-2 text-gray-400 group-hover:text-gray-600" />
                        <p className="mb-2 text-sm text-gray-500">
                          <span className="font-semibold">Click to upload</span> or drag and drop
                        </p>
                        <p className="text-xs text-gray-400">PDF, DOC, DOCX, XLS, XLSX (MAX. 10MB per file)</p>
                      </div>
                      <input
                        id="files"
                        name="files"
                        type="file"
                        multiple
                        accept=".pdf,.doc,.docx,.xlsx,.xls"
                        className="hidden"
                        onChange={handleFileChange}
                      />
                    </label>
                  </div>
                  {files.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <p className="text-xs font-medium text-gray-700">Selected files ({files.length}):</p>
                      <div className="space-y-2">
                        {files.map((file, index) => (
                          <div key={index} className="flex items-center justify-between p-2 bg-gray-50 border border-gray-200 rounded-lg">
                            <div className="flex items-center space-x-2 flex-1 min-w-0">
                              <HiOutlineDocumentText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                              <span className="text-sm text-gray-700 truncate">{file.name}</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => setFiles(files.filter((_, i) => i !== index))}
                              className="ml-2 p-1 text-gray-400 hover:text-gray-600 rounded transition-colors"
                            >
                              <HiOutlineX className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="mt-2 text-xs text-gray-500">
                    Upload additional PDF or Word documents related to this solicitation
                  </p>
                </div>

                {/* Analysis Options */}
                <div className="space-y-4 pt-4 border-t border-gray-200">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-3">
                      Analysis Options
                    </label>
                    <div className="space-y-3">
                      {/* Document Analysis Toggle */}
                      <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2">
                            <span className="text-sm font-medium text-gray-900">Document Analysis</span>
                            <span className="text-xs text-gray-500">(Text extraction, classification)</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            Extract text from documents and classify solicitation type
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDocumentAnalysisToggle(!enableDocumentAnalysis)}
                          className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2 ${
                            enableDocumentAnalysis ? 'bg-[#14B8A6]' : 'bg-gray-300'
                          }`}
                          role="switch"
                          aria-checked={enableDocumentAnalysis}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                              enableDocumentAnalysis ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                      </div>

                      {/* CLIN Extraction Toggle */}
                      <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2">
                            <span className="text-sm font-medium text-gray-900">CLIN Extraction</span>
                            <span className="text-xs text-gray-500">(Requires Document Analysis)</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            Extract Contract Line Item Numbers using AI (Claude/Groq)
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setEnableClinExtraction(!enableClinExtraction)}
                          disabled={!enableDocumentAnalysis}
                          className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#14B8A6] focus:ring-offset-2 ${
                            enableClinExtraction && enableDocumentAnalysis ? 'bg-[#14B8A6]' : 'bg-gray-300'
                          } ${!enableDocumentAnalysis ? 'opacity-50 cursor-not-allowed' : ''}`}
                          role="switch"
                          aria-checked={enableClinExtraction}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                              enableClinExtraction && enableDocumentAnalysis ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-gray-500">
                      <strong>Note:</strong> Document Analysis must be enabled for CLIN Extraction to work. 
                      Disable both to test scraping only.
                    </p>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="pt-4 flex items-center justify-end space-x-3 border-t border-gray-200">
                  <button
                    type="button"
                    onClick={() => navigate('/dashboard')}
                    className="inline-flex items-center justify-center px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition-colors"
                    title="Cancel"
                  >
                    <HiOutlineArrowLeft className="w-4 h-4 mr-2" />
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading || !samGovUrl.trim()}
                    className="inline-flex items-center justify-center px-6 py-2.5 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-gray-800 hover:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title={loading ? 'Processing...' : 'Begin Analysis'}
                  >
                    {loading ? (
                      <>
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Processing...
                      </>
                    ) : (
                      <>
                        <HiOutlineSearch className="w-4 h-4 mr-2" />
                        Begin Analysis
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
};

export default Analyze;
