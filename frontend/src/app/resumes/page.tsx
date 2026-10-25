'use client';

import { useEffect, useState } from 'react';
import {
  api,
  ExtractedProfileData,
  ResumeExtractionResponse,
  ResumeItem,
} from '@/lib/api';

export default function ResumesPage() {
  const [resumes, setResumes] = useState<ResumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Active Review State
  const [activeResume, setActiveResume] = useState<ResumeItem | null>(null);
  const [activeExtraction, setActiveExtraction] = useState<ResumeExtractionResponse | null>(null);
  const [reviewData, setReviewData] = useState<ExtractedProfileData | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let ignore = false;
    api.listResumes()
      .then((items) => {
        if (!ignore) {
          setResumes(items);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          if (err instanceof Error) {
            setError(err.message);
          } else {
            setError('Failed to load resumes.');
          }
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const refreshResumes = async () => {
    try {
      const items = await api.listResumes();
      setResumes(items);
    } catch (err: unknown) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setSuccess(null);
    setUploading(true);

    try {
      await api.uploadResume(file);
      setSuccess(`File "${file.name}" uploaded successfully!`);
      await refreshResumes();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Upload failed. Please ensure file is a valid PDF, DOCX, or TXT file.');
      }
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleParse = async (resume: ResumeItem) => {
    setError(null);
    setParsingId(resume.id);
    try {
      const extraction = await api.parseResume(resume.id);
      setActiveResume(resume);
      setActiveExtraction(extraction);
      setReviewData(extraction.extracted_data);
      await refreshResumes();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Parsing failed.');
      }
    } finally {
      setParsingId(null);
    }
  };

  const handleOpenReview = async (resume: ResumeItem) => {
    setError(null);
    try {
      const extraction = await api.getExtraction(resume.id);
      setActiveResume(resume);
      setActiveExtraction(extraction);
      setReviewData(extraction.extracted_data);
    } catch (err: unknown) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const handleDelete = async (resumeId: number) => {
    if (!confirm('Are you sure you want to delete this resume?')) return;
    try {
      await api.deleteResume(resumeId);
      if (activeResume?.id === resumeId) {
        setActiveResume(null);
        setActiveExtraction(null);
        setReviewData(null);
      }
      await refreshResumes();
    } catch (err: unknown) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const handleConfirmMerge = async () => {
    if (!activeResume || !reviewData) return;
    setConfirming(true);
    setError(null);

    try {
      const res = await api.confirmExtraction(activeResume.id, {
        data: reviewData,
        override_headline: true,
        override_bio: true,
        override_location: true,
      });
      setSuccess(res.message);
      setActiveResume(null);
      setActiveExtraction(null);
      setReviewData(null);
      await refreshResumes();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to merge facts into profile.');
      }
    } finally {
      setConfirming(false);
    }
  };

  const toggleSkillConfirmation = (index: number) => {
    if (!reviewData) return;
    const updated = [...reviewData.skills];
    updated[index].is_confirmed = !updated[index].is_confirmed;
    setReviewData({ ...reviewData, skills: updated });
  };

  const toggleExperienceConfirmation = (index: number) => {
    if (!reviewData) return;
    const updated = [...reviewData.experience];
    updated[index].is_confirmed = !updated[index].is_confirmed;
    setReviewData({ ...reviewData, experience: updated });
  };

  const toggleEducationConfirmation = (index: number) => {
    if (!reviewData) return;
    const updated = [...reviewData.education];
    updated[index].is_confirmed = !updated[index].is_confirmed;
    setReviewData({ ...reviewData, education: updated });
  };

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin mb-4" />
        <p className="text-sm text-slate-400">Loading resume records...</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10 space-y-10">
      <div>
        <h1 className="text-3xl font-extrabold text-white">Resume &amp; CV Ingestion</h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload your resume in PDF, DOCX, or TXT. Extract structured candidate facts with verbatim source evidence.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-start gap-3">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>{success}</span>
        </div>
      )}

      {/* CV Upload Dropzone Area */}
      <div className="p-8 rounded-[6px] bg-[#121215] border border-dashed border-[#26262D] hover:border-[#0070F3]/60 transition-colors text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-[4px] bg-[#0070F3]/10 text-[#0070F3] mb-3 border border-[#0070F3]/30">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
        <h3 className="text-base font-medium text-white">Upload Candidate CV</h3>
        <p className="text-[13px] text-[#A1A1AA] mt-1 max-w-md mx-auto">
          Supported formats: PDF, DOCX, TXT. Files are validated for magic signatures, scanned for scripts, and stored securely.
        </p>
        <div className="mt-5">
          <label className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] text-white font-medium text-xs cursor-pointer transition-all shadow-[0_0_12px_rgba(0,112,243,0.3)]">
            {uploading ? 'Validating & Uploading...' : 'Select CV File'}
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              disabled={uploading}
              onChange={handleFileUpload}
            />
          </label>
        </div>
      </div>

      {/* Uploaded Resumes List */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-white">Uploaded Documents</h2>
        {resumes.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-900/40 border border-slate-800 text-center text-xs text-slate-500 italic">
            No resumes uploaded yet. Upload a PDF or DOCX above to begin parsing.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {resumes.map((r) => (
              <div
                key={r.id}
                className="p-4 sm:p-5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4 backdrop-blur-sm"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 font-bold text-xs uppercase border border-slate-700/60">
                    {r.filename.split('.').pop()}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">{r.filename}</h4>
                    <p className="text-xs text-slate-400">
                      {(r.size_bytes / 1024).toFixed(1)} KB • {new Date(r.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${
                      r.parsing_status === 'confirmed'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        : r.parsing_status === 'pending_review'
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        : 'bg-slate-800 text-slate-400 border-slate-700'
                    }`}
                  >
                    {r.parsing_status}
                  </span>

                  {r.has_parsed ? (
                    <button
                      onClick={() => handleOpenReview(r)}
                      className="px-3 py-1.5 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-xs font-medium transition-colors"
                    >
                      Review Extracted Facts
                    </button>
                  ) : (
                    <button
                      onClick={() => handleParse(r)}
                      disabled={parsingId === r.id}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                    >
                      {parsingId === r.id ? 'Extracting...' : 'Parse & Extract Facts'}
                    </button>
                  )}

                  <a
                    href={`http://localhost:8000/api/v1/resumes/${r.id}/download`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
                  >
                    Download
                  </a>

                  <button
                    onClick={() => handleDelete(r.id)}
                    className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 text-xs font-medium transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Staged Profile Verification & Evidence Review Panel */}
      {activeResume && reviewData && (
        <div className="p-6 sm:p-8 rounded-2xl bg-slate-900 border border-indigo-500/40 shadow-2xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div>
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-1">
                Staged Fact Review
              </div>
              <h2 className="text-xl font-bold text-white">
                Review Extracted Facts: {activeResume.filename}{' '}
                {activeExtraction && (
                  <span className="text-xs text-indigo-400 font-normal">
                    ({activeExtraction.page_count} pages • {activeExtraction.status})
                  </span>
                )}
              </h2>
              <p className="text-xs text-slate-400">
                Every extracted claim below includes verbatim source evidence from your CV. Confirm or exclude items before merging into your verified profile.
              </p>
            </div>
            <button
              onClick={handleConfirmMerge}
              disabled={confirming}
              className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors shadow-lg shadow-emerald-600/20"
            >
              {confirming ? 'Merging...' : '✓ Confirm & Merge into Verified Profile'}
            </button>
          </div>

          {/* Extracted Headline & Bio */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Extracted Headline</label>
              <input
                type="text"
                value={reviewData.headline || ''}
                onChange={(e) => setReviewData({ ...reviewData, headline: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Extracted Location</label>
              <input
                type="text"
                value={reviewData.location || ''}
                onChange={(e) => setReviewData({ ...reviewData, location: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Extracted Skills with Evidence Grounding */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-white">Extracted Skills ({reviewData.skills.length})</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {reviewData.skills.map((skill, idx) => (
                <div
                  key={idx}
                  onClick={() => toggleSkillConfirmation(idx)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    skill.is_confirmed
                      ? 'bg-slate-950/80 border-indigo-500/40 text-white'
                      : 'bg-slate-950/40 border-slate-800 opacity-50 text-slate-400'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={skill.is_confirmed}
                        readOnly
                        className="rounded bg-slate-900 border-slate-700 text-indigo-600"
                      />
                      <span className="font-semibold text-xs">{skill.name}</span>
                    </div>
                    <span className="text-[10px] text-slate-400">Page {skill.evidence.page_number}</span>
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400 bg-slate-900/60 p-2 rounded border border-slate-800/80 italic font-mono">
                    &ldquo;{skill.evidence.text_snippet}&rdquo;
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Extracted Experience with Evidence */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-white">Extracted Experience ({reviewData.experience.length})</h3>
            <div className="space-y-3">
              {reviewData.experience.map((exp, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-xl border ${
                    exp.is_confirmed ? 'bg-slate-950/80 border-indigo-500/40' : 'bg-slate-950/40 border-slate-800 opacity-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={exp.is_confirmed}
                        onChange={() => toggleExperienceConfirmation(idx)}
                        className="rounded bg-slate-900 border-slate-700 text-indigo-600"
                      />
                      <span className="font-bold text-xs text-white">{exp.title}</span>
                      <span className="text-xs text-slate-400">at {exp.company}</span>
                    </div>
                    {exp.start_date && (
                      <span className="text-[11px] text-indigo-400">{exp.start_date}</span>
                    )}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400 bg-slate-900/60 p-2 rounded border border-slate-800/80 italic font-mono">
                    &ldquo;{exp.evidence.text_snippet}&rdquo;
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Extracted Education */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-white">Extracted Education ({reviewData.education.length})</h3>
            <div className="space-y-3">
              {reviewData.education.map((edu, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-xl border ${
                    edu.is_confirmed ? 'bg-slate-950/80 border-indigo-500/40' : 'bg-slate-950/40 border-slate-800 opacity-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={edu.is_confirmed}
                        onChange={() => toggleEducationConfirmation(idx)}
                        className="rounded bg-slate-900 border-slate-700 text-indigo-600"
                      />
                      <span className="font-bold text-xs text-white">{edu.degree} in {edu.field_of_study}</span>
                    </div>
                    <span className="text-xs text-slate-400">{edu.institution}</span>
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400 bg-slate-900/60 p-2 rounded border border-slate-800/80 italic font-mono">
                    &ldquo;{edu.evidence.text_snippet}&rdquo;
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex justify-end gap-3">
            <button
              onClick={() => {
                setActiveResume(null);
                setReviewData(null);
              }}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
            >
              Close Review
            </button>
            <button
              onClick={handleConfirmMerge}
              disabled={confirming}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs"
            >
              {confirming ? 'Merging...' : '✓ Confirm & Merge Facts'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
