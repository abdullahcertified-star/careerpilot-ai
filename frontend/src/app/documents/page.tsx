'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Navbar from '@/components/Navbar';
import {
  api,
  DocumentVersionResponse,
  FactualValidationReport,
  GeneratedDocumentResponse,
  JobPosting,
  ResumeExperienceItem,
  ResumeProjectItem,
} from '@/lib/api';

const TEMPLATE_OPTIONS = [
  { id: 'modern', name: 'Modern', desc: 'Clean, sleek indigo headers with high ATS readability', badge: 'Popular' },
  { id: 'classic', name: 'Classic', desc: 'Formal serif styling with balanced navy margins', badge: 'Traditional' },
  { id: 'technical', name: 'Technical', desc: 'Monospace accented for software & engineering roles', badge: 'Developer' },
  { id: 'executive', name: 'Executive', desc: 'Burgundy luxury palette for senior leadership positions', badge: 'Leadership' },
];

interface EditableResume {
  professional_summary?: string;
  highlighted_skills?: string[];
  experience?: ResumeExperienceItem[];
  projects?: ResumeProjectItem[];
}

interface EditableCoverLetter {
  opening_paragraph?: string;
  body_paragraphs?: string[];
  closing_paragraph?: string;
}

function DocumentStudioInner() {
  const searchParams = useSearchParams();
  const initialJobId = searchParams.get('job_id') ? parseInt(searchParams.get('job_id')!, 10) : null;
  const initialDocType = searchParams.get('doc_type') === 'cover_letter' ? 'cover_letter' : 'resume';

  // Selection & generation form state
  const [targetJobId, setTargetJobId] = useState<number | null>(initialJobId);
  const [docType, setDocType] = useState<'resume' | 'cover_letter'>(initialDocType);
  const [templateId, setTemplateId] = useState<string>('modern');
  const [customInstructions, setCustomInstructions] = useState<string>('');

  // Available jobs for selector
  const [availableJobs, setAvailableJobs] = useState<JobPosting[]>([]);
  const [loadingJobs, setLoadingJobs] = useState<boolean>(true);

  // Document list & active document
  const [documents, setDocuments] = useState<GeneratedDocumentResponse[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<GeneratedDocumentResponse | null>(null);
  const [versions, setVersions] = useState<DocumentVersionResponse[]>([]);
  const [activeVersion, setActiveVersion] = useState<DocumentVersionResponse | null>(null);

  // Editable structured draft
  const [editableData, setEditableData] = useState<Record<string, unknown>>({});
  const [editViewMode, setEditViewMode] = useState<'editor' | 'preview'>('editor');
  const [changeSummary, setChangeSummary] = useState<string>('');
  const [isApproved, setIsApproved] = useState<boolean>(false);

  // Status & notifications
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showVersionHistory, setShowVersionHistory] = useState<boolean>(false);

  // Initial fetch of jobs and documents
  useEffect(() => {
    let isMounted = true;

    const initData = async () => {
      try {
        const [jobsRes, docsRes] = await Promise.allSettled([
          api.searchJobs({ page_size: 50 }),
          api.listDocuments(),
        ]);
        if (!isMounted) return;

        if (jobsRes.status === 'fulfilled') {
          setAvailableJobs(jobsRes.value.items);
          if (!targetJobId && jobsRes.value.items.length > 0) {
            setTargetJobId(jobsRes.value.items[0].id);
          }
        }
        if (docsRes.status === 'fulfilled') {
          const docs = docsRes.value;
          setDocuments(docs);
          if (docs.length > 0) {
            const match = initialJobId ? docs.find((d) => d.job_id === initialJobId) || docs[0] : docs[0];
            setSelectedDoc(match);
          }
        }
      } catch {
        // Ignored
      } finally {
        if (isMounted) {
          setLoadingJobs(false);
          setLoading(false);
        }
      }
    };

    initData();
    return () => {
      isMounted = false;
    };
  }, [initialJobId, targetJobId]);

  // When selected document changes, fetch its versions and populate draft
  const selectedDocId = selectedDoc?.id;
  useEffect(() => {
    if (!selectedDocId) return;
    let isMounted = true;

    const fetchDocDetails = async () => {
      try {
        const fullDoc = await api.getDocument(selectedDocId);
        const vList = await api.listDocumentVersions(selectedDocId);
        if (!isMounted) return;

        setSelectedDoc(fullDoc);
        setVersions(vList);
        if (vList.length > 0) {
          const latest = vList[0];
          setActiveVersion(latest);
          setEditableData(JSON.parse(JSON.stringify(latest.structured_data)));
          setIsApproved(latest.is_approved);
          setTemplateId(fullDoc.template_id);
          setDocType(fullDoc.doc_type);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load document details');
        }
      }
    };

    fetchDocDetails();
    return () => {
      isMounted = false;
    };
  }, [selectedDocId]);

  // Handle generation of new document
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetJobId) {
      setError('Please select a target job posting.');
      return;
    }
    setGenerating(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const newDoc = await api.generateDocument({
        job_id: targetJobId,
        doc_type: docType,
        template_id: templateId,
        custom_instructions: customInstructions.trim() || undefined,
      });

      setSuccessMessage(
        `Successfully generated tailored ${docType === 'resume' ? 'Resume' : 'Cover Letter'} for ${newDoc.job_company || 'target role'}`
      );
      setSelectedDoc(newDoc);
      // Refresh documents list
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed. Please verify candidate profile facts and AI configuration.');
    } finally {
      setGenerating(false);
    }
  };

  // Handle saving new version
  const handleSaveNewVersion = async () => {
    if (!selectedDoc) return;
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const summary = changeSummary.trim() || `User manual revision (Version ${versions.length + 1})`;
      const updatedVersion = await api.updateDocumentVersion(selectedDoc.id, {
        structured_data: editableData,
        template_id: templateId,
        change_summary: summary,
        is_approved: isApproved,
      });

      setChangeSummary('');
      setSuccessMessage(`Saved as Version ${updatedVersion.version_number}. Previous versions remain preserved.`);
      // Refresh version list
      const vList = await api.listDocumentVersions(selectedDoc.id);
      setVersions(vList);
      setActiveVersion(updatedVersion);
      setEditableData(JSON.parse(JSON.stringify(updatedVersion.structured_data)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save updated version.');
    } finally {
      setSaving(false);
    }
  };

  // Handle document file download
  const handleDownload = async (format: 'pdf' | 'docx') => {
    if (!selectedDoc) return;
    setDownloading(format);
    setError(null);

    try {
      const { blob, filename } = await api.downloadDocumentBlob(
        selectedDoc.id,
        format,
        activeVersion?.id
      );
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setSuccessMessage(`Downloaded ${filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to download ${format.toUpperCase()}`);
    } finally {
      setDownloading(null);
    }
  };

  // Helper to switch active version view
  const handleSelectVersion = (v: DocumentVersionResponse) => {
    setActiveVersion(v);
    setEditableData(JSON.parse(JSON.stringify(v.structured_data)));
    setIsApproved(v.is_approved);
  };

  // Factual report shortcut
  const factualReport: FactualValidationReport | undefined = activeVersion?.validation_report;
  const resumeDraft = editableData as unknown as EditableResume;
  const coverDraft = editableData as unknown as EditableCoverLetter;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6">
        {/* Header Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-extrabold tracking-tight text-white">Document Studio</h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Phase 5 Active
              </span>
            </div>
            <p className="text-slate-400 text-sm mt-1">
              Job-specific resume and cover letter generation strictly grounded in verified candidate facts with zero fabrication.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowVersionHistory(!showVersionHistory)}
              className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-2 border border-slate-700 transition"
              title="View immutable revision history"
            >
              <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>History ({versions.length} {versions.length === 1 ? 'version' : 'versions'})</span>
            </button>

            {selectedDoc && (
              <>
                <button
                  onClick={() => handleDownload('docx')}
                  disabled={!!downloading}
                  className="px-3.5 py-2 rounded-lg bg-blue-900/60 hover:bg-blue-800 text-blue-200 text-xs font-semibold flex items-center gap-2 border border-blue-700/50 transition disabled:opacity-50"
                  title="Download editable Microsoft Word document"
                >
                  <svg className="w-4 h-4 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>{downloading === 'docx' ? 'Generating DOCX...' : 'Download DOCX'}</span>
                </button>

                <button
                  onClick={() => handleDownload('pdf')}
                  disabled={!!downloading}
                  className="px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition disabled:opacity-50"
                  title="Download text-selectable, ATS-friendly PDF"
                >
                  <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>{downloading === 'pdf' ? 'Generating PDF...' : 'Download PDF'}</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Notifications & Error alerts */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/60 border border-red-800/80 text-red-200 text-sm flex items-start gap-3 shadow-lg">
            <svg className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="font-semibold">Document Operation Issue</p>
              <p className="text-red-300/90 text-xs mt-0.5">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-white text-xs">Dismiss</button>
          </div>
        )}

        {successMessage && (
          <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-800/80 text-emerald-200 text-sm flex items-start gap-3 shadow-lg">
            <svg className="w-5 h-5 text-emerald-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <div className="flex-1">
              <p className="font-semibold">Success</p>
              <p className="text-emerald-300/90 text-xs mt-0.5">{successMessage}</p>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-white text-xs">Dismiss</button>
          </div>
        )}

        {/* Workspace Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* LEFT COLUMN: Generation Controls & Document Switcher */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                  </svg>
                  Generate New
                </h2>
                <span className="text-[10px] text-slate-500 font-mono">Agent v1.0</span>
              </div>

              <form onSubmit={handleGenerate} className="flex flex-col gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Target Requisition
                  </label>
                  {loadingJobs ? (
                    <div className="text-xs text-slate-500 italic py-2">Loading job listings...</div>
                  ) : (
                    <select
                      value={targetJobId || ''}
                      onChange={(e) => setTargetJobId(parseInt(e.target.value, 10))}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                      required
                    >
                      <option value="" disabled>Select a target position...</option>
                      {availableJobs.map((j) => (
                        <option key={j.id} value={j.id}>
                          {j.title} @ {j.company} ({j.work_mode})
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Document Type
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setDocType('resume')}
                      className={`px-3 py-2 rounded-lg text-xs font-semibold border transition text-center ${
                        docType === 'resume'
                          ? 'bg-indigo-600/30 border-indigo-500 text-indigo-300 shadow-sm'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      Tailored Resume
                    </button>
                    <button
                      type="button"
                      onClick={() => setDocType('cover_letter')}
                      className={`px-3 py-2 rounded-lg text-xs font-semibold border transition text-center ${
                        docType === 'cover_letter'
                          ? 'bg-indigo-600/30 border-indigo-500 text-indigo-300 shadow-sm'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      Cover Letter
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Visual Style Template
                  </label>
                  <div className="flex flex-col gap-1.5">
                    {TEMPLATE_OPTIONS.map((tmpl) => (
                      <div
                        key={tmpl.id}
                        onClick={() => setTemplateId(tmpl.id)}
                        className={`p-2.5 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                          templateId === tmpl.id
                            ? 'bg-slate-800 border-indigo-500 text-white shadow-sm'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex flex-col">
                          <span className="text-xs font-semibold text-slate-200">{tmpl.name}</span>
                          <span className="text-[10px] text-slate-400">{tmpl.desc}</span>
                        </div>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400">
                          {tmpl.badge}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Focus / Custom Emphasis (Optional)
                  </label>
                  <textarea
                    value={customInstructions}
                    onChange={(e) => setCustomInstructions(e.target.value)}
                    rows={2}
                    placeholder="e.g., Emphasize distributed systems & cloud automation achievements"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 resize-none transition"
                  />
                </div>

                <button
                  type="submit"
                  disabled={generating || !targetJobId}
                  className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 disabled:opacity-50"
                >
                  {generating ? (
                    <>
                      <svg className="w-4 h-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      <span>Tailoring &amp; Verifying...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>Generate Document</span>
                    </>
                  )}
                </button>
              </form>
            </div>

            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-3">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
                <span>Your Documents</span>
                <span className="text-xs text-slate-500 font-mono">({documents.length})</span>
              </h2>

              {loading ? (
                <div className="text-xs text-slate-500 italic py-2">Loading documents...</div>
              ) : documents.length === 0 ? (
                <div className="text-xs text-slate-500 py-3 text-center border border-dashed border-slate-800 rounded-xl">
                  No tailored documents generated yet. Select a job above to create your first verified application.
                </div>
              ) : (
                <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1">
                  {documents.map((doc) => {
                    const isSelected = selectedDoc?.id === doc.id;
                    return (
                      <div
                        key={doc.id}
                        onClick={() => setSelectedDoc(doc)}
                        className={`p-3 rounded-xl border cursor-pointer transition flex flex-col gap-1 ${
                          isSelected
                            ? 'bg-indigo-950/40 border-indigo-500/70 text-white shadow-md'
                            : 'bg-slate-950 border-slate-800/80 text-slate-300 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold truncate max-w-[170px] text-slate-100">
                            {doc.title}
                          </span>
                          <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-800 text-indigo-300">
                            {doc.doc_type === 'resume' ? 'Resume' : 'Cover'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-400">
                          <span className="truncate max-w-[150px]">{doc.job_company || 'Employer'}</span>
                          <span className="text-[10px] text-slate-500 font-mono">v{doc.versions_count}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* CENTER COLUMN: Document Editor / Preview Workspace */}
          <div className="lg:col-span-6 flex flex-col gap-4">
            {selectedDoc && activeVersion ? (
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-bold text-white tracking-tight">{selectedDoc.title}</h2>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                        Version {activeVersion.version_number}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Target: <span className="text-slate-200 font-medium">{selectedDoc.job_title}</span> at{' '}
                      <span className="text-slate-200 font-medium">{selectedDoc.job_company}</span>
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800">
                      <button
                        onClick={() => setEditViewMode('editor')}
                        className={`px-3 py-1 rounded text-xs font-semibold transition ${
                          editViewMode === 'editor'
                            ? 'bg-indigo-600 text-white'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        Structured Editor
                      </button>
                      <button
                        onClick={() => setEditViewMode('preview')}
                        className={`px-3 py-1 rounded text-xs font-semibold transition ${
                          editViewMode === 'preview'
                            ? 'bg-indigo-600 text-white'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        Formatted Preview
                      </button>
                    </div>
                  </div>
                </div>

                {/* Sub-bar: Approval & Quick Metadata */}
                <div className="flex items-center justify-between bg-slate-950/70 p-3 rounded-xl border border-slate-800/80 text-xs">
                  <div className="flex items-center gap-2">
                    <input
                      id="candidate-approval"
                      type="checkbox"
                      checked={isApproved}
                      onChange={(e) => setIsApproved(e.target.checked)}
                      className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                    />
                    <label htmlFor="candidate-approval" className="text-slate-300 font-medium cursor-pointer">
                      Candidate Reviewed &amp; Approved for Submission
                    </label>
                  </div>

                  <span className="text-[11px] text-slate-500 font-mono">
                    Model: {activeVersion.model_name}
                  </span>
                </div>

                {/* EDIT VIEW: STRUCTURED FORM */}
                {editViewMode === 'editor' && (
                  <div className="flex flex-col gap-5 max-h-[600px] overflow-y-auto pr-2">
                    {selectedDoc.doc_type === 'resume' ? (
                      <>
                        <div className="flex flex-col gap-1.5">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                            Tailored Professional Summary
                          </label>
                          <textarea
                            value={resumeDraft.professional_summary || ''}
                            onChange={(e) =>
                              setEditableData({ ...editableData, professional_summary: e.target.value })
                            }
                            rows={3}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition leading-relaxed"
                          />
                        </div>

                        <div className="flex flex-col gap-1.5">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                            Highlighted Skills (Comma-separated)
                          </label>
                          <input
                            type="text"
                            value={(resumeDraft.highlighted_skills || []).join(', ')}
                            onChange={(e) =>
                              setEditableData({
                                ...editableData,
                                highlighted_skills: e.target.value
                                  .split(',')
                                  .map((s) => s.trim())
                                  .filter(Boolean),
                              })
                            }
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                          />
                        </div>

                        <div className="flex flex-col gap-3">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                            Work Experience &amp; Achievement Bullets
                          </label>
                          {(resumeDraft.experience || []).map((exp: ResumeExperienceItem, idx: number) => (
                            <div key={idx} className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-2">
                              <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
                                <span>{exp.title} - <span className="text-indigo-400">{exp.company}</span></span>
                                <span className="text-slate-500 text-[11px] font-mono">{exp.start_date} – {exp.end_date}</span>
                              </div>
                              <div className="flex flex-col gap-1.5 mt-1">
                                {exp.bullets.map((b: string, bIdx: number) => (
                                  <textarea
                                    key={bIdx}
                                    value={b}
                                    onChange={(e) => {
                                      const updatedExp = [...(resumeDraft.experience || [])];
                                      updatedExp[idx].bullets[bIdx] = e.target.value;
                                      setEditableData({ ...editableData, experience: updatedExp });
                                    }}
                                    rows={2}
                                    className="w-full bg-slate-900 border border-slate-800 rounded-md p-2 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
                                  />
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>

                        {resumeDraft.projects && resumeDraft.projects.length > 0 && (
                          <div className="flex flex-col gap-3">
                            <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                              Tailored Technical Projects
                            </label>
                            {resumeDraft.projects.map((proj: ResumeProjectItem, pIdx: number) => (
                              <div key={pIdx} className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-2">
                                <span className="text-xs font-semibold text-slate-200">{proj.name}</span>
                                <textarea
                                  value={proj.description}
                                  onChange={(e) => {
                                    const updatedProj = [...(resumeDraft.projects || [])];
                                    updatedProj[pIdx].description = e.target.value;
                                    setEditableData({ ...editableData, projects: updatedProj });
                                  }}
                                  rows={2}
                                  className="w-full bg-slate-900 border border-slate-800 rounded-md p-2 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="flex flex-col gap-1.5">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">Opening Paragraph</label>
                          <textarea
                            value={coverDraft.opening_paragraph || ''}
                            onChange={(e) =>
                              setEditableData({ ...editableData, opening_paragraph: e.target.value })
                            }
                            rows={3}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 leading-relaxed"
                          />
                        </div>

                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">Body Paragraphs</label>
                          {(coverDraft.body_paragraphs || []).map((bp: string, bpIdx: number) => (
                            <textarea
                              key={bpIdx}
                              value={bp}
                              onChange={(e) => {
                                const updatedBp = [...(coverDraft.body_paragraphs || [])];
                                updatedBp[bpIdx] = e.target.value;
                                setEditableData({ ...editableData, body_paragraphs: updatedBp });
                              }}
                              rows={3}
                              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 leading-relaxed"
                            />
                          ))}
                        </div>

                        <div className="flex flex-col gap-1.5">
                          <label className="text-xs font-bold text-slate-300 uppercase tracking-wide">Closing &amp; Call to Action</label>
                          <textarea
                            value={coverDraft.closing_paragraph || ''}
                            onChange={(e) =>
                              setEditableData({ ...editableData, closing_paragraph: e.target.value })
                            }
                            rows={2}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 leading-relaxed"
                          />
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* PREVIEW VIEW: FORMATTED TEXT */}
                {editViewMode === 'preview' && (
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 max-h-[600px] overflow-y-auto">
                    <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed selection:bg-indigo-500/30">
                      {activeVersion.formatted_text}
                    </pre>
                  </div>
                )}

                {/* Footer Save & Revision Controls */}
                <div className="flex flex-col sm:flex-row items-center gap-3 pt-3 border-t border-slate-800">
                  <input
                    type="text"
                    value={changeSummary}
                    onChange={(e) => setChangeSummary(e.target.value)}
                    placeholder="Describe revision notes (e.g., Emphasized AWS and PostgreSQL)"
                    className="flex-1 w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                  <button
                    onClick={handleSaveNewVersion}
                    disabled={saving}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-2 shadow-lg shadow-emerald-600/20 disabled:opacity-50"
                  >
                    {saving ? 'Creating Revision...' : 'Save As New Version'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full min-h-[400px] bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-8 flex flex-col items-center justify-center text-center">
                <svg className="w-12 h-12 text-slate-700 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h3 className="text-base font-bold text-slate-300">No Document Selected</h3>
                <p className="text-xs text-slate-500 max-w-sm mt-1">
                  Choose an existing document from your documents list on the left, or generate a tailored resume for any requisition.
                </p>
              </div>
            )}
          </div>

          {/* RIGHT COLUMN: Automated Factual Consistency Checker */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            {factualReport ? (
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                    Factual Audit Engine
                  </h3>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      factualReport.is_clean
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {factualReport.is_clean ? 'Verified Clean' : 'Flags Found'}
                  </span>
                </div>

                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] text-slate-400 font-semibold uppercase">Factual Confidence</span>
                    <div className="text-2xl font-extrabold text-white mt-0.5">
                      {factualReport.factual_confidence_score}%
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-slate-400 font-semibold uppercase">Verified Facts</span>
                    <div className="text-xs font-mono font-bold text-slate-300 mt-1">
                      {factualReport.verified_claims_count} / {factualReport.total_claims_checked} claims
                    </div>
                  </div>
                </div>

                {factualReport.unsupported_claims && factualReport.unsupported_claims.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <span className="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1.5">
                      <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      Flagged Unsupported Claims ({factualReport.unsupported_claims.length})
                    </span>
                    <div className="flex flex-col gap-2 max-h-56 overflow-y-auto pr-1">
                      {factualReport.unsupported_claims.map((claim, cIdx) => (
                        <div
                          key={cIdx}
                          className="bg-amber-950/30 border border-amber-800/60 rounded-xl p-3 flex flex-col gap-1 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-amber-200">{claim.claim}</span>
                            <span className="text-[9px] uppercase px-1 py-0.5 rounded bg-amber-900/50 text-amber-300 border border-amber-700/50">
                              {claim.field}
                            </span>
                          </div>
                          <p className="text-[11px] text-amber-300/80 mt-0.5">{claim.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 text-xs flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Zero unverified facts or fabrications detected across candidate history.</span>
                  </div>
                )}

                {factualReport.verified_facts && factualReport.verified_facts.length > 0 && (
                  <div className="flex flex-col gap-1.5 mt-2">
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wide">
                      Verified Profile Anchor Points
                    </span>
                    <div className="flex flex-wrap gap-1 max-h-36 overflow-y-auto">
                      {factualReport.verified_facts.map((vf, vfIdx) => (
                        <span
                          key={vfIdx}
                          className="text-[10px] px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300"
                        >
                          ✓ {vf}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 text-[10px] text-slate-500 leading-normal">
                  <strong className="text-slate-400">Anti-Hallucination Policy:</strong> CareerPilot strictly enforces factual verification against candidate-confirmed data. Generating text with an LLM does not make it verified.
                </div>
              </div>
            ) : (
              <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 text-center text-xs text-slate-500">
                Generate or select a document version to review automated factual consistency audits.
              </div>
            )}
          </div>
        </div>

        {/* REVISION HISTORY MODAL */}
        {showVersionHistory && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-4 max-h-[80vh]">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Document Version History ({versions.length})
                </h3>
                <button
                  onClick={() => setShowVersionHistory(false)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
                >
                  Close
                </button>
              </div>

              <p className="text-xs text-slate-400">
                All document revisions are stored immutably. Restoring or previewing previous versions will not alter existing history.
              </p>

              <div className="flex flex-col gap-2.5 overflow-y-auto max-h-[50vh] pr-1">
                {versions.map((ver) => {
                  const isCurrent = activeVersion?.id === ver.id;
                  return (
                    <div
                      key={ver.id}
                      className={`p-3.5 rounded-xl border flex items-center justify-between transition ${
                        isCurrent
                          ? 'bg-indigo-950/40 border-indigo-500 text-white'
                          : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold font-mono">v{ver.version_number}</span>
                          <span className="text-xs text-slate-200">{ver.change_summary}</span>
                          {ver.is_approved && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                              Approved
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                          <span>{new Date(ver.created_at).toLocaleString()}</span>
                          <span>•</span>
                          <span>Score: {ver.validation_report?.factual_confidence_score}%</span>
                          <span>•</span>
                          <span>{ver.model_name}</span>
                        </div>
                      </div>

                      <button
                        onClick={() => {
                          handleSelectVersion(ver);
                          setShowVersionHistory(false);
                        }}
                        className={`px-3 py-1.5 rounded text-xs font-semibold transition ${
                          isCurrent
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
                        }`}
                      >
                        {isCurrent ? 'Viewing' : 'Load Version'}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function DocumentStudioPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950 text-slate-400 p-8 text-center text-sm">Loading Document Studio...</div>}>
      <DocumentStudioInner />
    </Suspense>
  );
}
