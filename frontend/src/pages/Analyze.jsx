/**
 * Scraping Input Page - Primary SAM.gov URL input
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { opportunitiesAPI } from '../utils/api';
import ProtectedRoute from '../components/ProtectedRoute';
import {
  HiOutlineArrowLeft,
  HiOutlineArrowRight,
  HiOutlineDocumentText,
  HiOutlinePaperClip,
  HiOutlineGlobe,
} from 'react-icons/hi';

const Analyze = () => {
  const [samGovUrl, setSamGovUrl] = useState('');
  const [files, setFiles] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

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
                  className="text-lg font-semibold text-[#2D1B3D] hover:text-[#14B8A6] transition-colors"
                >
                  Sam Gov AI
                </button>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="p-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                  title="Back to Dashboard"
                >
                  <HiOutlineArrowLeft className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-3xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="px-4 py-4 border-b border-gray-200">
              <h1 className="text-xl font-semibold text-gray-900 mb-1">
                Scrape SAM.gov Opportunity
              </h1>
              <p className="text-sm text-gray-600">
                Enter a SAM.gov solicitation URL to scrape and download documents
              </p>
            </div>
            <div className="px-4 py-4">

              <form onSubmit={handleSubmit} className="space-y-5">
                {error && (
                  <div className="bg-red-50 border-2 border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
                    {error}
                  </div>
                )}

                {/* Primary Input: SAM.gov URL */}
                <div>
                  <label htmlFor="samGovUrl" className="block text-xs font-medium text-gray-600 uppercase tracking-wide mb-1.5 flex items-center space-x-2">
                    <HiOutlineGlobe className="w-4 h-4 text-gray-600" />
                    <span>SAM.gov Opportunity URL <span className="text-red-500">*</span></span>
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
                      className="block w-full pl-10 pr-3 py-2.5 border-2 border-green-400 rounded-xl text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-colors"
                      placeholder="https://sam.gov/opp/[id]/view"
                      value={samGovUrl}
                      onChange={(e) => setSamGovUrl(e.target.value)}
                    />
                  </div>
                  <p className="mt-1.5 text-xs text-gray-600">
                    Enter the full URL of the SAM.gov opportunity you want to scrape
                  </p>
                </div>

                {/* Optional: File Upload */}
                <div>
                  <label htmlFor="files" className="block text-xs font-medium text-gray-600 uppercase tracking-wide mb-1.5 flex items-center space-x-2">
                    <HiOutlinePaperClip className="w-4 h-4 text-gray-600" />
                    <span>Additional Documents (Optional)</span>
                  </label>
                  <div className="relative">
                    <input
                      id="files"
                      name="files"
                      type="file"
                      multiple
                      accept=".pdf,.doc,.docx,.xlsx,.xls"
                      className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-2 file:border-green-400 file:text-sm file:font-medium file:bg-green-50 file:text-green-700 hover:file:bg-green-100 file:cursor-pointer"
                      onChange={handleFileChange}
                    />
                  </div>
                  <p className="mt-1.5 text-xs text-gray-600">
                    Upload additional PDF or Word documents related to this solicitation
                  </p>
                  {files.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs text-gray-600 font-medium">Selected files:</p>
                      <ul className="list-disc list-inside text-xs text-gray-600 mt-1 space-y-0.5">
                        {files.map((file, index) => (
                          <li key={index}>{file.name}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Begin Scraping Button */}
                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={loading || !samGovUrl.trim()}
                    className="w-full inline-flex items-center justify-center px-4 py-2.5 border-2 border-[#14B8A6] rounded-xl shadow-sm text-sm font-medium text-white bg-[#14B8A6] hover:bg-[#0D9488] hover:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title={loading ? 'Processing...' : 'Begin Scraping'}
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
