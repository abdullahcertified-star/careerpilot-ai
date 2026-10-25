'use client';

import { useCallback, useEffect, useState } from 'react';
import MatchAnalysisModal from '@/components/MatchAnalysisModal';
import MatchingPreferencesModal from '@/components/MatchingPreferencesModal';
import {
  api,
  FullProfile,
  JobMatch,
  JobPosting,
  JobProviderCapability,
  SavedJob,
  ScoringWeightsResponse,
} from '@/lib/api';

export default function JobsPage() {
  // Navigation Tabs
  const [activeTab, setActiveTab] = useState<'matches' | 'discover' | 'saved'>('matches');

  // Provider & Job State (Discovery)
  const [providers, setProviders] = useState<JobProviderCapability[]>([]);
  const [jobs, setJobs] = useState<JobPosting[]>([]);
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [savedLoading, setSavedLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [externalSearchUrl, setExternalSearchUrl] = useState<string | null>(null);

  // Search filter inputs
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('');
  const [workMode, setWorkMode] = useState('all');
  const [providerId, setProviderId] = useState('greenhouse');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Modals & Analysis State
  const [selectedJob, setSelectedJob] = useState<JobPosting | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);

  // Phase 4: Matching & Ranking State
  const [rankedMatches, setRankedMatches] = useState<JobMatch[]>([]);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [matchSortBy, setMatchSortBy] = useState('score_desc');
  const [minMatchScore, setMinMatchScore] = useState<number | undefined>(undefined);
  const [matchRoleFilter, setMatchRoleFilter] = useState('');
  const [matchLocationFilter, setMatchLocationFilter] = useState('');
  const [matchWorkModeFilter, setMatchWorkModeFilter] = useState('all');
  const [recalculating, setRecalculating] = useState(false);
  const [recalculateMessage, setRecalculateMessage] = useState<string | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<JobMatch | null>(null);
  const [showPreferencesModal, setShowPreferencesModal] = useState(false);
  const [profileData, setProfileData] = useState<FullProfile | null>(null);
  const [scoringWeights, setScoringWeights] = useState<ScoringWeightsResponse | null>(null);

  // Load candidate profile for match preferences
  const loadProfile = useCallback(async () => {
    try {
      const p = await api.getProfile();
      setProfileData(p);
    } catch {
      // Unauthenticated or not created yet
    }
  }, []);

  // Load ranked matches
  const loadRankedMatches = useCallback(async () => {
    setMatchesLoading(true);
    setMatchesError(null);
    try {
      const res = await api.listRankedMatches({
        min_score: minMatchScore,
        sort_by: matchSortBy,
        role: matchRoleFilter.trim() || undefined,
        location: matchLocationFilter.trim() || undefined,
        work_mode: matchWorkModeFilter === 'all' ? undefined : matchWorkModeFilter,
        page: 1,
        page_size: 50,
      });
      setRankedMatches(res.items);
    } catch (err) {
      setMatchesError(err instanceof Error ? err.message : 'Please sign in to view deterministic job matches.');
    } finally {
      setMatchesLoading(false);
    }
  }, [minMatchScore, matchSortBy, matchRoleFilter, matchLocationFilter, matchWorkModeFilter]);

  // Recalculate matches action
  const handleRecalculateAll = async () => {
    setRecalculating(true);
    setRecalculateMessage(null);
    try {
      const res = await api.recalculateMatches();
      setRecalculateMessage(`Recalculated ${res.evaluated_count} jobs against current profile.`);
      await loadRankedMatches();
      // If modal is open, refresh selected match
      if (selectedMatch) {
        const fresh = await api.getMatchDetail(selectedMatch.job_id);
        setSelectedMatch(fresh);
      }
    } catch (err) {
      setRecalculateMessage(err instanceof Error ? err.message : 'Recalculation failed');
    } finally {
      setRecalculating(false);
    }
  };

  // Inspect match detail
  const handleAnalyzeMatch = async (jobId: number) => {
    try {
      const match = await api.getMatchDetail(jobId);
      setSelectedMatch(match);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to retrieve match details');
    }
  };

  // Perform search in discovery
  const performSearch = useCallback(async (pageNum = 1) => {
    setLoading(true);
    setError(null);
    setWarnings([]);
    setExternalSearchUrl(null);
    try {
      const res = await api.searchJobs({
        query: query.trim() || undefined,
        location: location.trim() || undefined,
        work_mode: workMode === 'all' ? undefined : workMode,
        provider_id: providerId,
        page: pageNum,
        page_size: 15,
      });
      setJobs(res.items);
      setTotalCount(res.total_count);
      setPage(res.page);
      setWarnings(res.warnings || []);
      setExternalSearchUrl(res.external_search_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to search jobs');
    } finally {
      setLoading(false);
    }
  }, [query, location, workMode, providerId]);

  // Load saved jobs
  const loadSavedJobs = useCallback(async () => {
    setSavedLoading(true);
    try {
      const list = await api.listSavedJobs();
      setSavedJobs(list);
    } catch {
      // Ignored
    } finally {
      setSavedLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    let ignore = false;
    api.listJobProviders().then((res) => { if (!ignore) setProviders(res); }).catch(() => {});
    api.listRankedMatches({ page: 1, page_size: 50 }).then((res) => { if (!ignore) setRankedMatches(res.items); }).catch(() => {});
    api.getProfile().then((res) => { if (!ignore) setProfileData(res); }).catch(() => {});
    api.getScoringWeights().then((res) => { if (!ignore) setScoringWeights(res); }).catch(() => {});
    api.searchJobs({ page: 1, page_size: 15, provider_id: 'greenhouse' }).then((res) => {
      if (!ignore) {
        setJobs(res.items);
        setTotalCount(res.total_count);
        setPage(res.page);
        setWarnings(res.warnings || []);
        setExternalSearchUrl(res.external_search_url);
      }
    }).catch(() => {});
    api.listSavedJobs().then((res) => { if (!ignore) setSavedJobs(res); }).catch(() => {});

    return () => {
      ignore = true;
    };
  }, []);

  const handleToggleSave = async (job: JobPosting) => {
    try {
      if (job.is_saved && job.saved_id) {
        await api.unsaveJob(job.id);
        setJobs((prev) =>
          prev.map((j) => (j.id === job.id ? { ...j, is_saved: false, saved_id: null, saved_status: null } : j))
        );
        setSavedJobs((prev) => prev.filter((s) => s.job_id !== job.id));
      } else {
        const saved = await api.saveJob(job.id, { status: 'saved' });
        setJobs((prev) =>
          prev.map((j) => (j.id === job.id ? { ...j, is_saved: true, saved_id: saved.id, saved_status: saved.status } : j))
        );
        setSavedJobs((prev) => [saved, ...prev]);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Please sign in to save jobs.');
    }
  };

  const handleUpdateSavedStatus = async (savedId: number, newStatus: string) => {
    try {
      const updated = await api.updateSavedJob(savedId, { status: newStatus });
      setSavedJobs((prev) => prev.map((s) => (s.id === savedId ? updated : s)));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update status');
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importUrl.trim()) return;

    setImportLoading(true);
    setImportError(null);
    setImportSuccess(null);
    try {
      const newJob = await api.importJobUrl(importUrl.trim());
      setImportSuccess(`Successfully imported "${newJob.title}" at ${newJob.company}!`);
      setImportUrl('');
      performSearch(1);
      loadRankedMatches();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Failed to import URL');
    } finally {
      setImportLoading(false);
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source.toLowerCase()) {
      case 'greenhouse':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            Greenhouse Live API
          </span>
        );
      case 'manual_import':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            Imported Web Posting
          </span>
        );
      case 'linkedin':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            LinkedIn (Link-First)
          </span>
        );
      case 'indeed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            Indeed (Link-First)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">
            {source}
          </span>
        );
    }
  };

  const getScoreBadge = (score: number) => {
    const s = Math.round(score);
    if (s >= 80) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-extrabold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
          ★ {s}% Match
        </span>
      );
    }
    if (s >= 60) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
          ⚡ {s}% Match
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
        {s}% Match
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-[#0B0B0C] text-slate-100 flex flex-col">
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[11px] font-mono tracking-wider uppercase text-[#3291FF] bg-[#0070F3]/10 border border-[#0070F3]/30 px-2.5 py-0.5 rounded-[3px]">
                Deterministic Matching Engine
              </span>
              <span className="text-[12px] text-[#A1A1AA]">• Transparent Explainable Ranking</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-white">
              Job Intelligence &amp; Matching Engine
            </h1>
            <p className="text-[13px] text-[#A1A1AA] mt-1 max-w-3xl leading-relaxed">
              Strictly deterministic evaluation: required skills (35%), role relevance (25%), experience (15%), education (10%), location &amp; work authorization (10%), and preferred skills (5%). Zero LLM score hallucination.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setShowPreferencesModal(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[4px] bg-[#16161B] hover:bg-[#202028] text-[#EDEDED] hover:text-white font-medium text-xs transition-colors border border-[#2D2D36] hover:border-[#0070F3]/60"
            >
              ⚙ Preferences
            </button>

            <button
              onClick={handleRecalculateAll}
              disabled={recalculating}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] disabled:opacity-50 text-white font-medium text-xs transition-all shadow-[0_0_12px_rgba(0,112,243,0.3)]"
            >
              {recalculating ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Recalculating...
                </>
              ) : (
                '🔄 Recalculate Matches'
              )}
            </button>

            <button
              onClick={() => {
                setImportError(null);
                setImportSuccess(null);
                setShowImportModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[4px] bg-[#141418] hover:bg-[#1E1E24] text-[#EDEDED] hover:text-white font-medium text-xs transition-colors border border-[#2B2B34] hover:border-[#0070F3]/60"
            >
              + Import URL
            </button>
          </div>
        </div>

        {/* Recalculate Notification Feedback */}
        {recalculateMessage && (
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-200 text-xs flex items-center justify-between">
            <span>✓ {recalculateMessage}</span>
            <button onClick={() => setRecalculateMessage(null)} className="text-emerald-400 hover:text-white">✕</button>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-6">
            <button
              onClick={() => {
                setActiveTab('matches');
                loadRankedMatches();
              }}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === 'matches'
                  ? 'border-emerald-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Deterministic Matches &amp; Ranking
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800/60">
                {rankedMatches.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('discover')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === 'discover'
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Discovered Opportunities
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                {totalCount}
              </span>
            </button>

            <button
              onClick={() => {
                setActiveTab('saved');
                loadSavedJobs();
              }}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === 'saved'
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Saved Jobs &amp; Pipeline
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
                {savedJobs.length}
              </span>
            </button>
          </div>
        </div>

        {/* TAB 1: Deterministic Matches & Ranking */}
        {activeTab === 'matches' && (
          <div className="space-y-5">
            {/* Scoring System Information Bar */}
            <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-bold text-slate-300">Scoring Formula:</span>
                <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/50">
                  Required Skills: 35%
                </span>
                <span className="px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/50">
                  Role Relevance: 25%
                </span>
                <span className="px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/50">
                  Experience: 15%
                </span>
                <span className="px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/50">
                  Education &amp; Certs: 10%
                </span>
                <span className="px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                  Location &amp; Work Auth: 10%
                </span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  Preferred Skills: 5%
                </span>
              </div>

              <div className="text-[11px] text-slate-400">
                Deterministic Engine v{scoringWeights?.scoring_version || '1.0.0'} • Profile v{profileData?.profile?.profile_version || 1}
              </div>
            </div>

            {/* Filter & Sorting Controls */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
                {/* Role Filter */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">Role / Title Filter</label>
                  <input
                    type="text"
                    value={matchRoleFilter}
                    onChange={(e) => setMatchRoleFilter(e.target.value)}
                    placeholder="e.g. Backend, Lead..."
                    className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>

                {/* Location Filter */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">Location Filter</label>
                  <input
                    type="text"
                    value={matchLocationFilter}
                    onChange={(e) => setMatchLocationFilter(e.target.value)}
                    placeholder="e.g. Remote, SF..."
                    className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>

                {/* Work Mode */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">Work Mode</label>
                  <select
                    value={matchWorkModeFilter}
                    onChange={(e) => setMatchWorkModeFilter(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="all">All Modes</option>
                    <option value="remote">Remote Only</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">Onsite Only</option>
                  </select>
                </div>

                {/* Minimum Match Score */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">Minimum Match Score</label>
                  <select
                    value={minMatchScore !== undefined ? minMatchScore.toString() : 'all'}
                    onChange={(e) => {
                      const v = e.target.value;
                      setMinMatchScore(v === 'all' ? undefined : parseFloat(v));
                    }}
                    className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="all">All Scores (0%+)</option>
                    <option value="50">50%+ (Moderate Fit)</option>
                    <option value="70">70%+ (Strong Match)</option>
                    <option value="85">85%+ (Exceptional Fit)</option>
                  </select>
                </div>

                {/* Sort By */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">Sort Results By</label>
                  <select
                    value={matchSortBy}
                    onChange={(e) => setMatchSortBy(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="score_desc">Match Score (High to Low)</option>
                    <option value="score_asc">Match Score (Low to High)</option>
                    <option value="date_desc">Posting Date (Newest)</option>
                    <option value="title_asc">Role Title (A to Z)</option>
                    <option value="company_asc">Company (A to Z)</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="button"
                  onClick={() => loadRankedMatches()}
                  className="px-4 py-1.5 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] text-white font-medium text-xs transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <span>Apply Filters &amp; Sort</span>
                </button>
              </div>
            </div>

            {/* Error state */}
            {matchesError && (
              <div className="p-3.5 rounded-[4px] bg-red-950/30 border border-red-900/40 text-red-200 text-xs">
                {matchesError}
              </div>
            )}

            {/* Empty state with Visual Telemetry Preview */}
            {rankedMatches.length === 0 && !matchesLoading && (
              <div className="rounded-[6px] border border-[#222227] bg-[#121215] overflow-hidden">
                <div className="p-8 sm:p-10 text-center space-y-4 max-w-xl mx-auto">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[3px] bg-[#0070F3]/10 border border-[#0070F3]/30 text-[#3291FF] text-[11px] font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#0070F3] animate-pulse" />
                    <span>Awaiting Job Telemetry Stream</span>
                  </div>
                  <h3 className="text-lg font-medium text-white">No active matches in current view</h3>
                  <p className="text-[13px] text-[#A1A1AA] leading-relaxed">
                    Import open job URLs from Greenhouse, Lever, or LinkedIn, or click below to run deterministic multi-factor scoring against all database openings.
                  </p>
                  <div className="pt-2 flex items-center justify-center gap-3">
                    <button
                      onClick={handleRecalculateAll}
                      className="px-4 py-2 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] text-white font-medium text-xs transition-all shadow-[0_0_12px_rgba(0,112,243,0.3)]"
                    >
                      Recalculate All Openings
                    </button>
                    <button
                      onClick={() => setShowImportModal(true)}
                      className="px-4 py-2 rounded-[4px] bg-[#16161B] hover:bg-[#202028] text-[#EDEDED] hover:text-white border border-[#2D2D36] hover:border-[#0070F3]/60 font-medium text-xs transition-all"
                    >
                      + Import Job Posting
                    </button>
                  </div>
                </div>

                {/* Dashboard Visualization Image */}
                <div className="border-t border-[#1F1F24] bg-[#0E0E11] p-3">
                  <div className="rounded-[4px] overflow-hidden border border-[#1F1F24] opacity-80 hover:opacity-100 transition-opacity">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src="/images/jobs-telemetry.jpg"
                      alt="Job Telemetry & Ingestion Stream Preview"
                      className="w-full h-auto object-cover max-h-72"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Ranked Job Matches List */}
            <div className="grid grid-cols-1 gap-3.5">
              {rankedMatches.map((match) => (
                <div
                  key={match.id}
                  className="p-5 rounded-xl bg-slate-900/70 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {getScoreBadge(match.total_score)}
                      {match.is_stale && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          Profile Modified (Stale)
                        </span>
                      )}
                      {match.job && getSourceBadge(match.job.source)}
                      {match.job?.work_mode && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider bg-slate-800 text-slate-300">
                          {match.job.work_mode}
                        </span>
                      )}
                      {match.job?.location && (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          📍 {match.job.location}
                        </span>
                      )}
                    </div>

                    <div>
                      <h3 className="text-lg font-bold text-white hover:text-emerald-400 transition-colors">
                        {match.job?.title || 'Job Posting'}
                      </h3>
                      <p className="text-xs font-semibold text-emerald-400">{match.job?.company}</p>
                    </div>

                    {/* Matched & Missing Skills Previews */}
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      {match.matched_skills.slice(0, 4).map((s, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                        >
                          ✓ {s.skill}
                        </span>
                      ))}
                      {match.missing_skills.slice(0, 2).map((s, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded text-[11px] font-medium bg-rose-500/10 text-rose-300 border border-rose-500/20"
                        >
                          ✗ {s}
                        </span>
                      ))}
                      {match.matched_skills.length + match.missing_skills.length > 6 && (
                        <span className="text-[10px] text-slate-400">
                          +{match.matched_skills.length + match.missing_skills.length - 6} more skills
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex sm:flex-row md:flex-col items-end gap-2 shrink-0">
                    <button
                      onClick={() => handleAnalyzeMatch(match.job_id)}
                      className="w-full sm:w-auto px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors shadow-md shadow-emerald-600/20 flex items-center justify-center gap-1.5"
                    >
                      <span>🔍 Match Analysis</span>
                    </button>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      {match.job && (
                        <button
                          onClick={() => handleToggleSave(match.job!)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex-1 text-center ${
                            match.job.is_saved
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                              : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
                          }`}
                        >
                          {match.job.is_saved ? '★ Saved' : '☆ Save'}
                        </button>
                      )}

                      {match.job?.canonical_url && (
                        <a
                          href={match.job.canonical_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition-colors flex items-center justify-center gap-1"
                        >
                          Apply ↗
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 2: Discovered Jobs (Phase 3 Search) */}
        {activeTab === 'discover' && (
          <div className="space-y-4">
            {error && (
              <div className="p-3.5 rounded-lg bg-red-950/50 border border-red-800 text-red-200 text-xs">
                {error}
              </div>
            )}
            {/* Provider Capability Overview Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {providers.map((p) => (
                <div
                  key={p.provider_id}
                  className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-slate-200">{p.name}</span>
                    <span
                      className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                        p.integration_status === 'verified_live_api'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : p.integration_status === 'verified_secure_import'
                          ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                      }`}
                    >
                      {p.integration_status === 'verified_live_api'
                        ? 'LIVE API'
                        : p.integration_status === 'verified_secure_import'
                        ? 'SECURE IMPORT'
                        : 'LINK-FIRST'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                    {p.description}
                  </p>
                </div>
              ))}
            </div>

            {/* Search Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                performSearch(1);
              }}
              className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-xl space-y-3"
            >
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="md:col-span-2 relative">
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Job title, keywords, tech stack (e.g. Python, Full Stack)..."
                    className="w-full pl-3 pr-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="City, country, or remote..."
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <select
                    value={providerId}
                    onChange={(e) => setProviderId(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="greenhouse">Greenhouse (Live REST API)</option>
                    <option value="all">All Providers</option>
                    <option value="linkedin">LinkedIn (Link-First)</option>
                    <option value="indeed">Indeed (Link-First)</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                <div className="flex items-center gap-1.5 text-xs text-slate-300">
                  <span className="text-slate-400 font-medium mr-1">Work Mode:</span>
                  {(['all', 'remote', 'hybrid', 'onsite'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setWorkMode(mode)}
                      className={`px-2.5 py-1 rounded-md text-xs font-semibold capitalize transition-colors ${
                        workMode === mode
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center gap-1.5"
                >
                  {loading ? 'Searching...' : 'Search Discovered Jobs'}
                </button>
              </div>
            </form>

            {/* Warnings or External Search */}
            {warnings.length > 0 && (
              <div className="p-3.5 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200 text-xs space-y-1">
                {warnings.map((w, i) => (
                  <p key={i}>• {w}</p>
                ))}
              </div>
            )}

            {externalSearchUrl && (
              <div className="p-4 rounded-xl bg-indigo-950/40 border border-indigo-800/60 flex items-center justify-between gap-3">
                <p className="text-xs text-indigo-200">
                  External Link-First search URL generated for provider.
                </p>
                <a
                  href={externalSearchUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs whitespace-nowrap"
                >
                  Open External Portal ↗
                </a>
              </div>
            )}

            {/* Jobs Grid */}
            <div className="grid grid-cols-1 gap-3">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="p-5 rounded-xl bg-slate-900/70 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {getSourceBadge(job.source)}
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider bg-slate-800 text-slate-300">
                        {job.work_mode}
                      </span>
                      {job.location && (
                        <span className="text-xs text-slate-400">📍 {job.location}</span>
                      )}
                    </div>

                    <div>
                      <h3 className="text-lg font-bold text-white">{job.title}</h3>
                      <p className="text-xs font-semibold text-indigo-300">{job.company}</p>
                    </div>

                    <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                      {job.description.replace(/<[^>]+>/g, ' ')}
                    </p>
                  </div>

                  <div className="flex sm:flex-row md:flex-col items-end gap-2 shrink-0">
                    <button
                      onClick={() => handleAnalyzeMatch(job.id)}
                      className="w-full sm:w-auto px-3.5 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 font-semibold text-xs transition-colors"
                    >
                      ⚡ Check Match Score
                    </button>

                    <button
                      onClick={() => handleToggleSave(job)}
                      className={`w-full sm:w-auto px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        job.is_saved
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
                      }`}
                    >
                      {job.is_saved ? '★ Saved' : '☆ Save Job'}
                    </button>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <button
                        onClick={() => setSelectedJob(job)}
                        className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs"
                      >
                        Details
                      </button>
                      <a
                        href={job.canonical_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs"
                      >
                        Apply ↗
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {totalCount > 15 && (
              <div className="flex items-center justify-between pt-4 border-t border-slate-800">
                <span className="text-xs text-slate-400">
                  Showing page {page} of {Math.ceil(totalCount / 15)} ({totalCount} opportunities)
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => performSearch(page - 1)}
                    disabled={page <= 1 || loading}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-semibold text-slate-200"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => performSearch(page + 1)}
                    disabled={page * 15 >= totalCount || loading}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-semibold text-slate-200"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Saved Jobs */}
        {activeTab === 'saved' && (
          <div className="space-y-4">
            {savedJobs.length === 0 && !savedLoading && (
              <div className="p-12 text-center rounded-xl bg-slate-900/40 border border-slate-800 space-y-2">
                <h3 className="text-base font-bold text-slate-200">No saved jobs yet</h3>
                <p className="text-xs text-slate-400">
                  Bookmark high-scoring opportunities to track them in your pipeline.
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3">
              {savedJobs.map((item) => (
                <div
                  key={item.id}
                  className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-indigo-950 text-indigo-300 border border-indigo-800">
                        {item.status.toUpperCase()}
                      </span>
                      {getSourceBadge(item.job.source)}
                    </div>
                    <h3 className="text-lg font-bold text-white">{item.job.title}</h3>
                    <p className="text-xs font-semibold text-indigo-300">{item.job.company}</p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleAnalyzeMatch(item.job_id)}
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 font-semibold text-xs transition-colors"
                    >
                      ⚡ Check Match Score
                    </button>
                    <select
                      value={item.status}
                      onChange={(e) => handleUpdateSavedStatus(item.id, e.target.value)}
                      className="px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100"
                    >
                      <option value="saved">Saved</option>
                      <option value="applied">Applied</option>
                      <option value="interviewing">Interviewing</option>
                      <option value="offered">Offered</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Match Analysis Modal */}
      <MatchAnalysisModal
        isOpen={Boolean(selectedMatch)}
        onClose={() => setSelectedMatch(null)}
        jobMatch={selectedMatch}
        onRecalculate={handleRecalculateAll}
        isRecalculating={recalculating}
      />

      {/* Matching Preferences Modal */}
      <MatchingPreferencesModal
        isOpen={showPreferencesModal}
        onClose={() => setShowPreferencesModal(false)}
        initialPrefs={{
          target_job_titles: profileData?.profile?.target_job_titles,
          location: profileData?.profile?.location || undefined,
          remote_preference: profileData?.profile?.remote_preference,
          work_authorization_status: profileData?.profile?.work_authorization_status || undefined,
        }}
        onSaved={async () => {
          await loadProfile();
          await loadRankedMatches();
        }}
      />

      {/* Job Details Modal */}
      {selectedJob && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-6 border-b border-slate-800 flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">{selectedJob.title}</h2>
                <p className="text-sm font-semibold text-indigo-400">{selectedJob.company}</p>
              </div>
              <button onClick={() => setSelectedJob(null)} className="text-slate-400 hover:text-white font-bold p-1">
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto space-y-4 flex-1 text-xs text-slate-300 leading-relaxed whitespace-pre-line">
              {selectedJob.description}
            </div>
            <div className="p-4 border-t border-slate-800 bg-slate-950 flex items-center justify-between">
              <button
                onClick={() => {
                  const jId = selectedJob.id;
                  setSelectedJob(null);
                  handleAnalyzeMatch(jId);
                }}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs"
              >
                View Match Analysis
              </button>
              <button onClick={() => setSelectedJob(null)} className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual URL Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Import Job from Web URL</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Secure ingestion engine for company career pages and ATS postings.
                </p>
              </div>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-white font-bold">
                ✕
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="space-y-4">
              <div>
                <input
                  type="url"
                  required
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  placeholder="https://example.com/careers/senior-engineer"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {importError && (
                <div className="p-2.5 rounded bg-red-950/50 border border-red-800 text-red-200 text-xs">
                  {importError}
                </div>
              )}
              {importSuccess && (
                <div className="p-2.5 rounded bg-emerald-950/50 border border-emerald-800 text-emerald-200 text-xs">
                  {importSuccess}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowImportModal(false)} className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={importLoading}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs"
                >
                  {importLoading ? 'Validating...' : 'Import Posting'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
