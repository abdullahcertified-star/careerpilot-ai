'use client';

import { Suspense, useEffect, useState } from 'react';
import Navbar from '@/components/Navbar';
import {
  api,
  ApplicationApprovalReviewRequest,
  ApplicationPackage,
  ApplicationResponse,
  ApplicationStartRequest,
  ApplicationSubmitRequest,
  JobPosting,
  ManualHandoffPacket,
  ProposedFormAnswers,
  SubmissionAttemptResponse,
  WorkflowHistoryItem,
} from '@/lib/api';

function ApplicationsInner() {
  const [applications, setApplications] = useState<ApplicationResponse[]>([]);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Review & Package Modal
  const [selectedApp, setSelectedApp] = useState<ApplicationResponse | null>(null);
  const [currentPackage, setCurrentPackage] = useState<ApplicationPackage | null>(null);
  const [loadingPackage, setLoadingPackage] = useState<boolean>(false);
  const [showReviewModal, setShowReviewModal] = useState<boolean>(false);

  // Answer Editing State
  const defaultAnswers: ProposedFormAnswers = {
    full_name: '',
    email: '',
    phone: '',
    location: '',
    work_authorization: '',
    requires_sponsorship: false,
    notice_period: '',
  };
  const [isEditingAnswers, setIsEditingAnswers] = useState<boolean>(false);
  const [editableAnswers, setEditableAnswers] = useState<ProposedFormAnswers>(defaultAnswers);
  const [savingAnswers, setSavingAnswers] = useState<boolean>(false);

  // Approval Action State
  const [approvalNotes, setApprovalNotes] = useState<string>('');
  const [processingDecision, setProcessingDecision] = useState<boolean>(false);

  // Submission State
  const [submittingPackage, setSubmittingPackage] = useState<boolean>(false);
  const [manualHandoffResult, setManualHandoffResult] = useState<ManualHandoffPacket | null>(null);
  const [showHandoffModal, setShowHandoffModal] = useState<boolean>(false);

  // Submission Attempts Audit Modal
  const [showAttemptsModal, setShowAttemptsModal] = useState<boolean>(false);
  const [submissionAttempts, setSubmissionAttempts] = useState<SubmissionAttemptResponse[]>([]);
  const [loadingAttempts, setLoadingAttempts] = useState<boolean>(false);

  // Timeline / Workflow History Modal
  const [showHistoryModal, setShowHistoryModal] = useState<boolean>(false);
  const [historyLogs, setHistoryLogs] = useState<WorkflowHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Start Application Form
  const [showStartModal, setShowStartModal] = useState<boolean>(false);
  const [availableJobs, setAvailableJobs] = useState<JobPosting[]>([]);
  const [startJobId, setStartJobId] = useState<number | null>(null);
  const [startJobUrl, setStartJobUrl] = useState<string>('');
  const [startTemplateId, setStartTemplateId] = useState<string>('modern');
  const [startSubmissionMode, setStartSubmissionMode] = useState<'manual_handoff' | 'automated_api'>('manual_handoff');
  const [startInstructions, setStartInstructions] = useState<string>('');
  const [startingWorkflow, setStartingWorkflow] = useState<boolean>(false);

  // Copy state helper
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Initial load
  useEffect(() => {
    let isMounted = true;
    const fetchInitialData = async () => {
      try {
        const [appsRes, jobsRes] = await Promise.allSettled([
          api.listApplications(),
          api.searchJobs({ page_size: 50 }),
        ]);
        if (!isMounted) return;
        if (appsRes.status === 'fulfilled') {
          setApplications(appsRes.value);
        }
        if (jobsRes.status === 'fulfilled') {
          setAvailableJobs(jobsRes.value.items);
          if (jobsRes.value.items.length > 0) {
            setStartJobId(jobsRes.value.items[0].id);
          }
        }
      } catch {
        // Ignored if unauthenticated
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchInitialData();
    return () => {
      isMounted = false;
    };
  }, []);

  const refreshApplications = async () => {
    try {
      const apps = await api.listApplications(activeTab === 'all' ? undefined : activeTab);
      setApplications(apps);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh applications');
    }
  };

  const openReviewPackage = async (app: ApplicationResponse) => {
    setSelectedApp(app);
    setShowReviewModal(true);
    setLoadingPackage(true);
    setError(null);
    setIsEditingAnswers(false);
    try {
      const pkg = await api.getApplicationPackage(app.id);
      setCurrentPackage(pkg);
      setEditableAnswers(pkg.form_answers || defaultAnswers);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load application package');
      setShowReviewModal(false);
    } finally {
      setLoadingPackage(false);
    }
  };

  const handleSaveAnswers = async () => {
    if (!selectedApp) return;
    setSavingAnswers(true);
    setError(null);
    try {
      const updatedPkg = await api.updateProposedAnswers(selectedApp.id, editableAnswers);
      setCurrentPackage(updatedPkg);
      setIsEditingAnswers(false);
      setSuccessMessage('Proposed form answers updated. Approval invalidated if previously approved.');
      await refreshApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save updated answers');
    } finally {
      setSavingAnswers(false);
    }
  };

  const handleApprovalDecision = async (decision: 'approved' | 'rejected' | 'cancelled') => {
    if (!selectedApp || !currentPackage) return;
    setProcessingDecision(true);
    setError(null);

    const payload: ApplicationApprovalReviewRequest = {
      approved: decision === 'approved',
      notes: approvalNotes.trim() || undefined,
      expected_package_hash: currentPackage.package_hash,
      job_id: currentPackage.job.id,
    };

    try {
      const updatedPkg = await api.reviewAndApprovePackage(selectedApp.id, payload);
      setCurrentPackage(updatedPkg);
      setApprovalNotes('');
      setSuccessMessage(
        decision === 'approved'
          ? `Application package ${selectedApp.id} securely approved! Ready for permitted submission or manual handoff.`
          : `Application package ${selectedApp.id} marked as ${decision}.`
      );
      await refreshApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record decision');
    } finally {
      setProcessingDecision(false);
    }
  };

  const handleExecuteSubmission = async () => {
    if (!selectedApp || !currentPackage) return;
    setSubmittingPackage(true);
    setError(null);

    const submissionKey = `sub_${selectedApp.id}_${Date.now()}`;
    const payload: ApplicationSubmitRequest = {
      submission_key: submissionKey,
      target_job_id: currentPackage.job.id,
      confirmed_package_hash: currentPackage.package_hash,
    };

    try {
      const result = await api.submitApplicationPackage(selectedApp.id, payload);
      if (result.handoff_packet) {
        setManualHandoffResult(result.handoff_packet);
        setShowHandoffModal(true);
      }
      setSuccessMessage(
        `Submission action complete. Result: ${result.status.toUpperCase()}${result.receipt_reference ? ` (Ref: ${result.receipt_reference})` : ''}`
      );
      await refreshApplications();
      // Reload package
      const updatedPkg = await api.getApplicationPackage(selectedApp.id);
      setCurrentPackage(updatedPkg);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Application submission failed');
    } finally {
      setSubmittingPackage(false);
    }
  };

  const handleViewAttempts = async (app: ApplicationResponse) => {
    setSelectedApp(app);
    setShowAttemptsModal(true);
    setLoadingAttempts(true);
    try {
      const attempts = await api.getSubmissionAttempts(app.id);
      setSubmissionAttempts(attempts);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load submission audit attempts');
    } finally {
      setLoadingAttempts(false);
    }
  };

  const handleStartWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();
    setStartingWorkflow(true);
    setError(null);
    setSuccessMessage(null);

    const payload: ApplicationStartRequest = {
      job_id: startJobId || undefined,
      job_url: startJobUrl.trim() || undefined,
      template_id: startTemplateId,
      submission_mode: startSubmissionMode,
      custom_instructions: startInstructions.trim() || undefined,
    };

    try {
      const app = await api.startApplicationWorkflow(payload);
      setShowStartModal(false);
      setSuccessMessage(`Application workflow initiated for ${app.job_title || 'job position'}. Status: ${app.status}`);
      await refreshApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start workflow');
    } finally {
      setStartingWorkflow(false);
    }
  };

  const handleViewHistory = async (app: ApplicationResponse) => {
    setSelectedApp(app);
    setShowHistoryModal(true);
    setLoadingHistory(true);
    try {
      const logs = await api.getApplicationHistory(app.id);
      setHistoryLogs(logs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load execution timeline');
    } finally {
      setLoadingHistory(false);
    }
  };

  // Filtered applications
  const filteredApps = applications.filter((app) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'awaiting_approval') return app.status === 'awaiting_approval' || app.approval_status === 'pending';
    if (activeTab === 'in_progress') return ['pending', 'discovered', 'normalized', 'deduplicated', 'matched', 'documents_generated', 'validated'].includes(app.status);
    if (activeTab === 'completed') return ['manual_handoff', 'submitted', 'completed'].includes(app.status);
    if (activeTab === 'failed') return app.status === 'failed' || app.status === 'cancelled' || app.status === 'rejected';
    return true;
  });

  const countAwaiting = applications.filter((a) => a.status === 'awaiting_approval' || a.approval_status === 'pending').length;
  const countCompleted = applications.filter((a) => ['manual_handoff', 'submitted', 'completed'].includes(a.status)).length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6">
        {/* Header Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-extrabold tracking-tight text-white">Application Workflows</h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Phase 7 Review-First Submission
              </span>
            </div>
            <p className="text-slate-400 text-sm mt-1">
              Secure application packages, explicit human approvals, duplicate prevention, and permitted integrations with manual handoff.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowStartModal(true)}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition flex items-center gap-2 shadow-lg shadow-indigo-600/20"
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Initiate Workflow</span>
            </button>
          </div>
        </div>

        {/* Notifications */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/60 border border-red-800/80 text-red-200 text-sm flex items-start gap-3 shadow-lg">
            <svg className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="font-semibold">Operation Alert</p>
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
              <p className="font-semibold">Workflow Status</p>
              <p className="text-emerald-300/90 text-xs mt-0.5">{successMessage}</p>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-white text-xs">Dismiss</button>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex flex-col gap-1 shadow-md">
            <span className="text-[11px] font-semibold uppercase text-slate-400">Total Workflows</span>
            <div className="text-2xl font-black text-white">{applications.length}</div>
          </div>
          <div className="bg-slate-900/80 border border-amber-800/40 rounded-xl p-4 flex flex-col gap-1 shadow-md">
            <span className="text-[11px] font-semibold uppercase text-amber-400">Awaiting Human Approval</span>
            <div className="text-2xl font-black text-amber-300">{countAwaiting}</div>
          </div>
          <div className="bg-slate-900/80 border border-emerald-800/40 rounded-xl p-4 flex flex-col gap-1 shadow-md">
            <span className="text-[11px] font-semibold uppercase text-emerald-400">Completed &amp; Handoff</span>
            <div className="text-2xl font-black text-emerald-300">{countCompleted}</div>
          </div>
          <div className="bg-slate-900/80 border border-indigo-800/40 rounded-xl p-4 flex flex-col gap-1 shadow-md">
            <span className="text-[11px] font-semibold uppercase text-indigo-400">Security Gate</span>
            <div className="text-xs font-semibold text-slate-300 mt-1">Zero Blind Resubmissions &amp; SHA256 Locked</div>
          </div>
        </div>

        {/* Status Filter Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          {[
            { id: 'all', label: 'All Applications', count: applications.length },
            { id: 'awaiting_approval', label: 'Awaiting Approval', count: countAwaiting, highlight: countAwaiting > 0 },
            { id: 'in_progress', label: 'In Progress', count: applications.filter((a) => !['awaiting_approval', 'manual_handoff', 'submitted', 'completed', 'failed', 'cancelled', 'rejected'].includes(a.status)).length },
            { id: 'completed', label: 'Completed', count: countCompleted },
            { id: 'failed', label: 'Issues / Cancelled', count: applications.filter((a) => ['failed', 'cancelled', 'rejected'].includes(a.status)).length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
              }`}
            >
              <span>{tab.label}</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                tab.highlight ? 'bg-amber-400 text-black font-bold' : 'bg-slate-800 text-slate-300'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        {/* Applications List */}
        {loading ? (
          <div className="p-12 text-center text-slate-500 text-xs italic">Loading application workflows...</div>
        ) : filteredApps.length === 0 ? (
          <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-12 text-center flex flex-col items-center justify-center">
            <svg className="w-12 h-12 text-slate-700 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2-0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h3 className="text-sm font-bold text-slate-300">No applications in this category</h3>
            <p className="text-xs text-slate-500 max-w-sm mt-1">
              Initiate a new workflow above to run job discovery, document tailoring, package preparation, and candidate review.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {filteredApps.map((app) => {
              const isAwaiting = app.status === 'awaiting_approval' || app.approval_status === 'pending';
              const isApproved = app.approval_status === 'approved';
              const isInvalidated = app.approval_status === 'invalidated';
              const isCompleted = ['manual_handoff', 'submitted', 'completed'].includes(app.status);
              const isPendingConfirm = app.status === 'confirmation_pending';

              return (
                <div
                  key={app.id}
                  className={`bg-slate-900/90 border rounded-2xl p-5 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-5 transition ${
                    isAwaiting
                      ? 'border-amber-500/60 bg-amber-950/10'
                      : isPendingConfirm
                      ? 'border-purple-500/60 bg-purple-950/10'
                      : isInvalidated
                      ? 'border-rose-500/60 bg-rose-950/10'
                      : isApproved
                      ? 'border-emerald-500/60 bg-emerald-950/10'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Left Column: Job & State Info */}
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-3">
                      <span className="text-base font-bold text-white tracking-tight">
                        {app.job_title || 'Application Requisition'}
                      </span>
                      <span className="text-xs text-slate-400 font-medium">@ {app.job_company || 'Employer'}</span>

                      {/* Status Badges */}
                      {isAwaiting && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
                          Awaiting Human Approval
                        </span>
                      )}
                      {isApproved && app.status !== 'submitted' && app.status !== 'manual_handoff' && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                          Approved &amp; Ready
                        </span>
                      )}
                      {isInvalidated && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                          Approval Invalidated (Doc Changed)
                        </span>
                      )}
                      {isPendingConfirm && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                          Confirmation Pending (Timeout Guarded)
                        </span>
                      )}
                      {isCompleted && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                          {app.status === 'submitted' ? 'Submitted' : 'Manual Handoff Ready'}
                        </span>
                      )}
                      {app.status === 'rejected' && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                          Candidate Rejected
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                      <span>App #{app.id}</span>
                      <span>•</span>
                      <span>Adapter: {app.submission_mode}</span>
                      <span>•</span>
                      <span>Created: {new Date(app.created_at).toLocaleDateString()}</span>
                      {Boolean(app.tracking_metadata?.confirmation_reference) && (
                        <>
                          <span>•</span>
                          <span className="text-emerald-400 font-bold">
                            Receipt: {String(app.tracking_metadata.confirmation_reference)}
                          </span>
                        </>
                      )}
                    </div>

                    {app.last_error && (
                      <p className="text-xs text-red-400/90 font-mono mt-1">Error: {app.last_error}</p>
                    )}
                  </div>

                  {/* Right Column: Actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleViewAttempts(app)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span>Attempts Audit</span>
                    </button>

                    <button
                      onClick={() => handleViewHistory(app)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>Timeline</span>
                    </button>

                    <button
                      onClick={() => openReviewPackage(app)}
                      className={`px-4 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-md ${
                        isAwaiting || isInvalidated
                          ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/20'
                          : isApproved
                          ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20'
                          : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20'
                      }`}
                    >
                      <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2-0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span>Review Package</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* COMPLETE APPLICATION PACKAGE REVIEW MODAL (Phase 7 Core) */}
        {showReviewModal && selectedApp && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full p-6 shadow-2xl flex flex-col gap-5 max-h-[92vh] overflow-hidden">
              {/* Modal Header */}
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-shrink-0">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-bold text-white">Application Package Review</h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    currentPackage?.approval_status === 'approved'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : currentPackage?.approval_status === 'invalidated'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  }`}>
                    {currentPackage?.approval_status || 'Pending Review'}
                  </span>
                </div>
                <button
                  onClick={() => setShowReviewModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 transition"
                >
                  Close
                </button>
              </div>

              {loadingPackage ? (
                <div className="py-20 text-center text-slate-500 text-xs italic">Loading complete application package...</div>
              ) : currentPackage ? (
                <div className="overflow-y-auto pr-2 flex flex-col gap-5 text-xs">
                  {/* Warning: Invalidation Alert */}
                  {currentPackage.is_content_altered_since_approval && (
                    <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/80 text-rose-200 text-xs flex items-center gap-3">
                      <svg className="w-5 h-5 text-rose-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div>
                        <p className="font-bold">Content Changed Since Prior Approval</p>
                        <p className="text-[11px] text-rose-300/90 mt-0.5">
                          Form answers or documents were modified. In accordance with safety policies, prior approval has been invalidated. You must explicitly re-approve the updated package before submission.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Section 1: Job & Submission Capability */}
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-850 pb-2.5">
                      <div>
                        <h4 className="text-sm font-bold text-white">{currentPackage.job.title}</h4>
                        <p className="text-slate-400">{currentPackage.job.company} • {currentPackage.job.location || 'Remote'}</p>
                      </div>
                      {currentPackage.original_application_url && (
                        <a
                          href={currentPackage.original_application_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 text-indigo-300 text-xs font-semibold border border-indigo-800/60 transition inline-flex items-center gap-1.5"
                        >
                          <span>Original Job URL</span>
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11px]">
                      <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                        <span className="text-slate-400 block font-semibold">Adapter Method</span>
                        <span className="font-mono text-indigo-300 font-bold">{currentPackage.submission_method}</span>
                      </div>
                      <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                        <span className="text-slate-400 block font-semibold">Automated Submission Status</span>
                        <span className={`font-semibold ${currentPackage.provider_capability.supports_submission ? 'text-emerald-400' : 'text-amber-400'}`}>
                          {currentPackage.provider_capability.supports_submission ? 'Supported' : 'Manual Handoff Required'}
                        </span>
                      </div>
                      <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                        <span className="text-slate-400 block font-semibold">Package SHA-256 Hash</span>
                        <span className="font-mono text-slate-300 truncate block" title={currentPackage.package_hash}>
                          {currentPackage.package_hash.slice(0, 16)}...
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Section 2: Selected Documents */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Resume Card */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          Resume Document
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">{currentPackage.resume?.version_id ? `v${currentPackage.resume.version_number}` : 'No version'}</span>
                      </div>
                      <p className="text-[11px] text-slate-400">Type: {currentPackage.resume?.doc_type || 'resume'}</p>
                      <div className="bg-slate-900 p-2.5 rounded-lg font-mono text-[10px] text-slate-300 max-h-32 overflow-y-auto whitespace-pre-wrap border border-slate-800">
                        {currentPackage.resume?.formatted_text || 'No resume preview available.'}
                      </div>
                    </div>

                    {/* Cover Letter Card */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                          </svg>
                          Cover Letter Document
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">{currentPackage.cover_letter?.version_id ? `v${currentPackage.cover_letter.version_number}` : 'No version'}</span>
                      </div>
                      <p className="text-[11px] text-slate-400">Type: {currentPackage.cover_letter?.doc_type || 'cover_letter'}</p>
                      <div className="bg-slate-900 p-2.5 rounded-lg font-mono text-[10px] text-slate-300 max-h-32 overflow-y-auto whitespace-pre-wrap border border-slate-800">
                        {currentPackage.cover_letter?.formatted_text || 'No cover letter preview available.'}
                      </div>
                    </div>
                  </div>

                  {/* Section 3: Proposed Form Answers (View & Edit Mode) */}
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <div className="flex items-center gap-2">
                        <h4 className="font-bold text-white">Proposed Form Answers</h4>
                        <span className="text-[10px] text-slate-500">
                          (Verified candidate data • Sensitive answers never guessed)
                        </span>
                      </div>
                      {!isEditingAnswers ? (
                        <button
                          type="button"
                          onClick={() => setIsEditingAnswers(true)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 text-[11px] font-semibold transition"
                        >
                          Edit Answers
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setIsEditingAnswers(false)}
                            className="px-2.5 py-1 rounded bg-slate-800 text-slate-400 text-[11px]"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={handleSaveAnswers}
                            disabled={savingAnswers}
                            className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-[11px] transition"
                          >
                            {savingAnswers ? 'Saving...' : 'Save & Invalidate Prior Approval'}
                          </button>
                        </div>
                      )}
                    </div>

                    {isEditingAnswers ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Full Name</label>
                          <input
                            type="text"
                            value={editableAnswers.full_name || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, full_name: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Email</label>
                          <input
                            type="email"
                            value={editableAnswers.email || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, email: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Phone</label>
                          <input
                            type="text"
                            value={editableAnswers.phone || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, phone: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">LinkedIn URL</label>
                          <input
                            type="url"
                            value={editableAnswers.linkedin_url || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, linkedin_url: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">GitHub URL</label>
                          <input
                            type="url"
                            value={editableAnswers.github_url || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, github_url: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Portfolio URL</label>
                          <input
                            type="url"
                            value={editableAnswers.portfolio_url || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, portfolio_url: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Work Authorization</label>
                          <input
                            type="text"
                            value={editableAnswers.work_authorization || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, work_authorization: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-slate-400 font-semibold block mb-1">Notice Period</label>
                          <input
                            type="text"
                            value={editableAnswers.notice_period || ''}
                            onChange={(e) => setEditableAnswers({ ...editableAnswers, notice_period: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-[11px]">
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Name</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.full_name || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Email</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.email || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Phone</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.phone || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Work Auth</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.work_authorization || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">LinkedIn</span>
                          <span className="text-slate-200 font-medium truncate block">{currentPackage.form_answers?.linkedin_url || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">GitHub</span>
                          <span className="text-slate-200 font-medium truncate block">{currentPackage.form_answers?.github_url || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Notice Period</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.notice_period || '—'}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Location</span>
                          <span className="text-slate-200 font-medium">{currentPackage.form_answers?.location || '—'}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Section 4: Human Review Notes & Actions */}
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
                    <label className="text-slate-300 font-semibold block">Candidate Review Notes (Recorded in Audit Trail)</label>
                    <textarea
                      value={approvalNotes}
                      onChange={(e) => setApprovalNotes(e.target.value)}
                      rows={2}
                      placeholder="e.g. Verified resume bullet points, confirmed contact information and work authorization."
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
                    />

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleApprovalDecision('rejected')}
                          disabled={processingDecision}
                          className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-rose-950/60 text-slate-300 hover:text-rose-200 font-bold text-xs border border-slate-700 transition disabled:opacity-50"
                        >
                          Reject Package
                        </button>
                        <button
                          type="button"
                          onClick={() => handleApprovalDecision('cancelled')}
                          disabled={processingDecision}
                          className="px-3 py-2 rounded-lg bg-slate-900 text-slate-400 hover:text-white text-xs border border-slate-800"
                        >
                          Cancel Application
                        </button>
                      </div>

                      <div className="flex items-center gap-2.5">
                        <button
                          type="button"
                          onClick={() => handleApprovalDecision('approved')}
                          disabled={processingDecision}
                          className="px-4 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-bold text-xs transition flex items-center gap-1.5 shadow-md shadow-emerald-700/20 disabled:opacity-50"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          <span>{processingDecision ? 'Recording...' : 'Explicitly Approve Package'}</span>
                        </button>

                        {currentPackage.approval_status === 'approved' && !currentPackage.is_content_altered_since_approval && (
                          <button
                            type="button"
                            onClick={handleExecuteSubmission}
                            disabled={submittingPackage}
                            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition flex items-center gap-1.5 shadow-lg shadow-indigo-600/30 disabled:opacity-50 animate-pulse"
                          >
                            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                            <span>{submittingPackage ? 'Executing...' : 'Submit / Generate Handoff'}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* MANUAL HANDOFF PACKET MODAL (Phase 7 Deliverable) */}
        {showHandoffModal && manualHandoffResult && (
          <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 shadow-2xl flex flex-col gap-4 max-h-[90vh] overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-shrink-0">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-emerald-400"></span>
                  <h3 className="text-base font-bold text-white">Manual Handoff Package Ready</h3>
                </div>
                <button
                  onClick={() => setShowHandoffModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2.5 py-1 rounded-lg bg-slate-800"
                >
                  Close
                </button>
              </div>

              <div className="overflow-y-auto pr-1 flex flex-col gap-4 text-xs">
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                  <div>
                    <h4 className="font-bold text-white">{manualHandoffResult.job_title} @ {manualHandoffResult.company}</h4>
                    <p className="text-slate-400 text-[11px] mt-0.5">Original requisition portal link ready:</p>
                  </div>
                  <a
                    href={manualHandoffResult.original_application_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition inline-flex items-center gap-1.5 shadow-md shadow-indigo-600/30"
                  >
                    <span>Open Application Page</span>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>

                {/* Instructions */}
                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
                  <h5 className="font-bold text-indigo-300">Instructions:</h5>
                  <ol className="list-decimal list-inside space-y-1 text-slate-300 text-[11px]">
                    {manualHandoffResult.instructions.map((ins, idx) => (
                      <li key={idx}>{ins}</li>
                    ))}
                  </ol>
                </div>

                {/* Labeled Answers Copy Grid */}
                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2.5">
                  <h5 className="font-bold text-white">Prepared Form Answers (Click to Copy)</h5>
                  <div className="flex flex-col gap-2">
                    {manualHandoffResult.labeled_answers.map((item) => (
                      <div
                        key={item.field_key}
                        className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between gap-4"
                      >
                        <div className="flex-1 min-w-0">
                          <span className="text-[10px] uppercase font-bold text-slate-400 block">{item.label}</span>
                          <span className="text-xs font-mono text-slate-200 truncate block">{item.value}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(item.value, item.field_key)}
                          className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex-shrink-0 transition"
                        >
                          {copiedKey === item.field_key ? 'Copied!' : 'Copy'}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SUBMISSION ATTEMPTS AUDIT MODAL */}
        {showAttemptsModal && selectedApp && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 shadow-2xl flex flex-col gap-4 max-h-[85vh]">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <h3 className="text-base font-bold text-white">Submission Audit Attempts (Application #{selectedApp.id})</h3>
                </div>
                <button
                  onClick={() => setShowAttemptsModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
                >
                  Close
                </button>
              </div>

              {loadingAttempts ? (
                <div className="text-xs text-slate-500 italic py-8 text-center">Loading audit records...</div>
              ) : submissionAttempts.length === 0 ? (
                <div className="text-xs text-slate-500 py-8 text-center">No submission attempts recorded yet.</div>
              ) : (
                <div className="flex flex-col gap-2.5 overflow-y-auto max-h-[60vh] pr-1">
                  {submissionAttempts.map((attempt) => (
                    <div
                      key={attempt.id}
                      className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-1.5 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-indigo-300 font-bold">{attempt.submission_key}</span>
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                          attempt.status === 'submitted'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : attempt.status === 'manual_handoff'
                            ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                            : attempt.status === 'confirmation_pending'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : attempt.status === 'failed'
                            ? 'bg-red-950 text-red-300 border border-red-800'
                            : 'bg-slate-800 text-slate-300'
                        }`}>
                          {attempt.status}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-slate-400 font-mono mt-1">
                        <div>Provider: {attempt.provider_id}</div>
                        <div>Actor ID: {attempt.actor_id}</div>
                        <div>Receipt: {attempt.receipt_reference || '—'}</div>
                        <div>Time: {new Date(attempt.started_at).toLocaleTimeString()}</div>
                      </div>
                      {attempt.error_message && (
                        <p className="text-[11px] text-red-400 font-mono mt-1">Error: {attempt.error_message}</p>
                      )}
                      {attempt.response_payload && (
                        <pre className="bg-slate-900/60 p-2 rounded text-[10px] text-slate-400 font-mono overflow-x-auto border border-slate-800">
                          {JSON.stringify(attempt.response_payload, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TIMELINE / HISTORY MODAL */}
        {showHistoryModal && selectedApp && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-4 max-h-[85vh]">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Execution Timeline &amp; Audit Logs
                </h3>
                <button
                  onClick={() => setShowHistoryModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
                >
                  Close
                </button>
              </div>

              {loadingHistory ? (
                <div className="text-xs text-slate-500 italic py-8 text-center">Loading execution logs...</div>
              ) : historyLogs.length === 0 ? (
                <div className="text-xs text-slate-500 py-8 text-center">No execution log entries recorded yet.</div>
              ) : (
                <div className="flex flex-col gap-2.5 overflow-y-auto max-h-[55vh] pr-1">
                  {historyLogs.map((log) => (
                    <div
                      key={log.id}
                      className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 flex flex-col gap-1 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-indigo-300 font-mono">{log.node_name}</span>
                        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                          log.status === 'completed'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : log.status === 'interrupted'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : log.status === 'failed'
                            ? 'bg-red-950 text-red-300 border border-red-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}>
                          {log.status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono mt-0.5">
                        <span>Attempt {log.attempt_number}</span>
                        <span>{new Date(log.created_at).toLocaleTimeString()}</span>
                      </div>
                      {log.error_message && (
                        <p className="text-[11px] text-red-400 font-mono mt-1">{log.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* START NEW WORKFLOW MODAL */}
        {showStartModal && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-base font-bold text-white">Initiate Application Workflow</h3>
                <button
                  onClick={() => setShowStartModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
                >
                  Close
                </button>
              </div>

              <form onSubmit={handleStartWorkflow} className="flex flex-col gap-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Target Requisition</label>
                  <select
                    value={startJobId || ''}
                    onChange={(e) => setStartJobId(e.target.value ? parseInt(e.target.value, 10) : null)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200"
                  >
                    <option value="">Or use manual URL below...</option>
                    {availableJobs.map((j) => (
                      <option key={j.id} value={j.id}>
                        {j.title} @ {j.company} ({j.work_mode})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Direct Job URL (Optional)</label>
                  <input
                    type="url"
                    value={startJobUrl}
                    onChange={(e) => setStartJobUrl(e.target.value)}
                    placeholder="https://boards.greenhouse.io/example/jobs/12345"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Document Style Template</label>
                  <select
                    value={startTemplateId}
                    onChange={(e) => setStartTemplateId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200"
                  >
                    <option value="modern">Modern (Clean indigo headers)</option>
                    <option value="classic">Classic (Traditional serif)</option>
                    <option value="technical">Technical (Monospace accents)</option>
                    <option value="executive">Executive (Leadership burgundy)</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Submission Mode</label>
                  <select
                    value={startSubmissionMode}
                    onChange={(e) => setStartSubmissionMode(e.target.value as 'manual_handoff' | 'automated_api')}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200"
                  >
                    <option value="manual_handoff">Manual Handoff Package (Download &amp; Verify)</option>
                    <option value="automated_api">Direct Automated Submission</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Tailoring Focus (Optional)</label>
                  <textarea
                    value={startInstructions}
                    onChange={(e) => setStartInstructions(e.target.value)}
                    rows={2}
                    placeholder="e.g. Focus on cloud automation and PostgreSQL scaling"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowStartModal(false)}
                    className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={startingWorkflow || (!startJobId && !startJobUrl.trim())}
                    className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition disabled:opacity-50"
                  >
                    {startingWorkflow ? 'Initiating LangGraph...' : 'Start Workflow'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950 text-slate-400 p-8 text-center text-sm">Loading applications...</div>}>
      <ApplicationsInner />
    </Suspense>
  );
}
