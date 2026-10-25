'use client';

import { Suspense, useEffect, useState } from 'react';
import Navbar from '@/components/Navbar';
import {
  api,
  ApplicationApprovalRequest,
  ApplicationResponse,
  ApplicationStartRequest,
  JobPosting,
  WorkflowHistoryItem,
} from '@/lib/api';

function ApplicationsInner() {
  const [applications, setApplications] = useState<ApplicationResponse[]>([]);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Modals & Active Selections
  const [selectedApp, setSelectedApp] = useState<ApplicationResponse | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);
  const [approvalNotes, setApprovalNotes] = useState<string>('');
  const [processingApproval, setProcessingApproval] = useState<boolean>(false);

  // History Drawer
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

  const handleApprovalDecision = async (approved: boolean) => {
    if (!selectedApp) return;
    setProcessingApproval(true);
    setError(null);

    const payload: ApplicationApprovalRequest = {
      approved,
      notes: approvalNotes.trim() || undefined,
    };

    try {
      const updated = await api.approveApplication(selectedApp.id, payload);
      setShowApprovalModal(false);
      setApprovalNotes('');
      setSuccessMessage(
        approved
          ? `Application ${updated.id} approved! Handoff package ready.`
          : `Application ${updated.id} rejected / revision requested.`
      );
      await refreshApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approval operation failed');
    } finally {
      setProcessingApproval(false);
    }
  };

  const handleCancelWorkflow = async (appId: number) => {
    if (!confirm('Are you sure you want to cancel this application workflow?')) return;
    setError(null);
    try {
      await api.cancelApplication(appId, 'Candidate cancelled from dashboard');
      setSuccessMessage('Application workflow cancelled successfully.');
      await refreshApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel workflow');
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
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Phase 6 Durable LangGraph
              </span>
            </div>
            <p className="text-slate-400 text-sm mt-1">
              Durable multi-agent coordination with PostgreSQL checkpointing, observable timelines, and mandatory human approval gates.
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
              <p className="font-semibold">Workflow Exception</p>
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
              <p className="font-semibold">Workflow Updated</p>
              <p className="text-emerald-300/90 text-xs mt-0.5">{successMessage}</p>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-white text-xs">Dismiss</button>
          </div>
        )}

        {/* Quick Summary KPI Cards */}
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
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex flex-col gap-1 shadow-md">
            <span className="text-[11px] font-semibold uppercase text-slate-400">Security Gate</span>
            <div className="text-xs font-semibold text-slate-300 mt-1">Zero Unauthorized Submissions Enforced</div>
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
          <div className="p-12 text-center text-slate-500 text-xs italic">Loading durable application workflows...</div>
        ) : filteredApps.length === 0 ? (
          <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-12 text-center flex flex-col items-center justify-center">
            <svg className="w-12 h-12 text-slate-700 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h3 className="text-sm font-bold text-slate-300">No applications in this category</h3>
            <p className="text-xs text-slate-500 max-w-sm mt-1">
              Initiate a new workflow above to run job discovery, deterministic scoring, anti-fabrication tailoring, and human approval.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {filteredApps.map((app) => {
              const isAwaiting = app.status === 'awaiting_approval' || app.approval_status === 'pending';
              const isInvalidated = app.approval_status === 'invalidated';
              const isCompleted = ['manual_handoff', 'submitted', 'completed'].includes(app.status);

              return (
                <div
                  key={app.id}
                  className={`bg-slate-900/90 border rounded-2xl p-5 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-5 transition ${
                    isAwaiting
                      ? 'border-amber-500/60 bg-amber-950/10'
                      : isInvalidated
                      ? 'border-rose-500/60 bg-rose-950/10'
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
                      {isInvalidated && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                          Approval Invalidated (Doc Changed)
                        </span>
                      )}
                      {isCompleted && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                          {app.status === 'submitted' ? 'Submitted' : 'Manual Handoff Ready'}
                        </span>
                      )}
                      {app.status === 'failed' && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-300 border border-red-500/40">
                          Failed ({app.last_error ? 'Outage/Error' : 'Threshold'})
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                      <span>Thread: {app.workflow_thread_id.slice(0, 18)}...</span>
                      <span>•</span>
                      <span>Mode: {app.submission_mode}</span>
                      <span>•</span>
                      <span>Created: {new Date(app.created_at).toLocaleDateString()}</span>
                      {Boolean(app.tracking_metadata?.confirmation_reference) && (
                        <>
                          <span>•</span>
                          <span className="text-emerald-400 font-bold">
                            Ref: {String(app.tracking_metadata.confirmation_reference)}
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
                      onClick={() => handleViewHistory(app)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>Timeline</span>
                    </button>

                    {(isAwaiting || isInvalidated) && (
                      <button
                        onClick={() => {
                          setSelectedApp(app);
                          setShowApprovalModal(true);
                        }}
                        className="px-4 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-amber-600/20"
                      >
                        <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Review &amp; Approve</span>
                      </button>
                    )}

                    {!isCompleted && app.status !== 'cancelled' && (
                      <button
                        onClick={() => handleCancelWorkflow(app.id)}
                        className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-red-950/40 text-slate-400 hover:text-red-300 text-xs font-semibold border border-slate-800 hover:border-red-800 transition"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* HUMAN APPROVAL MODAL */}
        {showApprovalModal && selectedApp && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-5 max-h-[85vh]">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-white">Human Approval Gate</h3>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    Mandatory Candidate Review
                  </span>
                </div>
                <button
                  onClick={() => setShowApprovalModal(false)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
                >
                  Close
                </button>
              </div>

              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 flex flex-col gap-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 font-semibold">Position:</span>
                  <span className="font-bold text-white">{selectedApp.job_title} @ {selectedApp.job_company}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 font-semibold">Submission Mode:</span>
                  <span className="font-mono text-indigo-300">{selectedApp.submission_mode}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 font-semibold">Resume Version ID:</span>
                  <span className="font-mono text-slate-300">{selectedApp.resume_version_id || 'v1'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 font-semibold">Cover Letter Version ID:</span>
                  <span className="font-mono text-slate-300">{selectedApp.cover_letter_version_id || 'v1'}</span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-800/40 text-xs text-amber-300 leading-relaxed">
                <strong>Anti-Hallucination Policy:</strong> As candidate, verify that the prepared documents and factual claims accurately reflect your verified background. An LLM or automated graph transition alone cannot authorize external submission.
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-300">
                  Approval or Revision Notes (Optional)
                </label>
                <textarea
                  value={approvalNotes}
                  onChange={(e) => setApprovalNotes(e.target.value)}
                  rows={2}
                  placeholder="e.g., Looks great. Verified all bullet points and employment dates."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => handleApprovalDecision(false)}
                  disabled={processingApproval}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-rose-950 text-slate-300 hover:text-rose-200 text-xs font-bold border border-slate-700 transition disabled:opacity-50"
                >
                  {processingApproval ? 'Processing...' : 'Reject / Request Revision'}
                </button>
                <button
                  type="button"
                  onClick={() => handleApprovalDecision(true)}
                  disabled={processingApproval}
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-emerald-600/20 disabled:opacity-50"
                >
                  <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>{processingApproval ? 'Submitting Decision...' : 'Approve Application'}</span>
                </button>
              </div>
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
