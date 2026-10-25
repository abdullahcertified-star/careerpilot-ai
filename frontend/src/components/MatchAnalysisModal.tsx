'use client';

import React from 'react';
import { JobMatch } from '@/lib/api';

interface MatchAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobMatch: JobMatch | null;
  onRecalculate?: () => Promise<void>;
  isRecalculating?: boolean;
}

export default function MatchAnalysisModal({
  isOpen,
  onClose,
  jobMatch,
  onRecalculate,
  isRecalculating = false,
}: MatchAnalysisModalProps) {
  if (!isOpen || !jobMatch) return null;

  const score = Math.round(jobMatch.total_score);

  const getScoreBadgeColor = (val: number) => {
    if (val >= 80) return 'text-emerald-400 bg-emerald-950/80 border-emerald-500/50';
    if (val >= 60) return 'text-amber-300 bg-amber-950/80 border-amber-500/50';
    return 'text-rose-400 bg-rose-950/80 border-rose-500/50';
  };

  const getBarColor = (val: number) => {
    if (val >= 80) return 'bg-emerald-500';
    if (val >= 60) return 'bg-amber-500';
    return 'bg-rose-500';
  };

  const componentLabels: Array<{
    key: keyof typeof jobMatch.component_scores;
    name: string;
    weight: string;
    description: string;
  }> = [
    {
      key: 'required_skills',
      name: 'Required Skills',
      weight: '35%',
      description: 'Coverage of must-have technical & domain skills from requisitions',
    },
    {
      key: 'role_relevance',
      name: 'Responsibilities & Role Relevance',
      weight: '25%',
      description: 'Alignment between candidate target titles, responsibilities, and job requirements',
    },
    {
      key: 'experience_seniority',
      name: 'Experience & Seniority',
      weight: '15%',
      description: 'Comparison of candidate years of experience vs required seniority level',
    },
    {
      key: 'education_certifications',
      name: 'Education & Certifications',
      weight: '10%',
      description: 'Academic degree and industry credential compatibility',
    },
    {
      key: 'location_work_authorization',
      name: 'Location & Work Authorization',
      weight: '10%',
      description: 'Work mode & legal authorization compatibility (zero assumptions on unknown facts)',
    },
    {
      key: 'preferred_skills',
      name: 'Preferred Skills',
      weight: '5%',
      description: 'Bonus skills and "nice-to-have" qualifications',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-6 border-b border-slate-800/80 flex items-start justify-between bg-slate-950/40">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-400 bg-indigo-950/80 border border-indigo-800/60 px-2 py-0.5 rounded">
                Deterministic Match Analysis
              </span>
              <span className="text-[11px] text-slate-400">
                Engine v{jobMatch.scoring_version} • Profile v{jobMatch.candidate_profile_version}
              </span>
            </div>
            <h2 className="text-xl font-extrabold text-white">
              {jobMatch.job?.title || 'Job Match Breakdown'}
            </h2>
            <p className="text-xs font-semibold text-indigo-300">
              {jobMatch.job?.company} {jobMatch.job?.location ? `• ${jobMatch.job.location}` : ''}
            </p>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-slate-200">
          {/* Stale Match Alert */}
          {jobMatch.is_stale && (
            <div className="p-3.5 rounded-xl bg-amber-950/50 border border-amber-800/80 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-xs text-amber-200">
                <span className="text-base">⚠️</span>
                <span>
                  Candidate profile has been updated since this score was computed. Recalculate to view fresh alignment.
                </span>
              </div>
              {onRecalculate && (
                <button
                  onClick={onRecalculate}
                  disabled={isRecalculating}
                  className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-bold text-xs whitespace-nowrap transition-colors"
                >
                  {isRecalculating ? 'Recalculating...' : 'Recalculate Now'}
                </button>
              )}
            </div>
          )}

          {/* Overall Match Hero Card */}
          <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="space-y-1.5 text-center sm:text-left">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                Overall Alignment Score
              </span>
              <div className="flex items-baseline justify-center sm:justify-start gap-2">
                <span className="text-4xl font-extrabold text-white tracking-tight">{score}</span>
                <span className="text-slate-400 text-sm font-semibold">/ 100</span>
              </div>
              <p className="text-xs text-slate-400 max-w-sm">
                Evaluated deterministically with fixed, immutable weights. No non-deterministic LLM hallucination in final ranking.
              </p>
            </div>

            <div className={`px-5 py-3 rounded-xl border text-center font-bold text-sm ${getScoreBadgeColor(score)}`}>
              {score >= 80 ? '🌟 Highly Compatible' : score >= 60 ? '⚡ Moderate Fit' : '⏳ Low Alignment'}
              <div className="text-[11px] font-normal opacity-80 mt-0.5">
                Evaluated on {new Date(jobMatch.evaluated_at).toLocaleDateString()}
              </div>
            </div>
          </div>

          {/* Component Breakdown Progress Bars */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Deterministic Component Breakdown (Sums to 100%)
            </h3>
            <div className="grid grid-cols-1 gap-3">
              {componentLabels.map((c) => {
                const compScore = jobMatch.component_scores[c.key] ?? 0;
                return (
                  <div
                    key={c.key}
                    className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div>
                        <span className="font-bold text-white mr-2">{c.name}</span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                          Weight: {c.weight}
                        </span>
                      </div>
                      <span className="font-extrabold text-white">
                        {compScore.toFixed(1)} / 100
                      </span>
                    </div>

                    {/* Progress Track */}
                    <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${getBarColor(compScore)}`}
                        style={{ width: `${Math.min(100, Math.max(0, compScore))}%` }}
                      />
                    </div>

                    <p className="text-[11px] text-slate-400">{c.description}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Skills Breakdown Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Matched Skills */}
            <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                  <span>✓</span> Matched Skills ({jobMatch.matched_skills.length})
                </span>
                <span className="text-[10px] text-slate-400">Verified from Profile</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {jobMatch.matched_skills.length > 0 ? (
                  jobMatch.matched_skills.map((s, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30"
                    >
                      {s.skill}
                      {s.proficiency && (
                        <span className="text-[10px] text-emerald-400/80">({s.proficiency})</span>
                      )}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500 italic">No direct skill overlaps identified</span>
                )}
              </div>
            </div>

            {/* Missing Required Skills */}
            <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                  <span>✗</span> Missing Required Skills ({jobMatch.missing_skills.length})
                </span>
                <span className="text-[10px] text-slate-400">Penalizes Score (35%)</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {jobMatch.missing_skills.length > 0 ? (
                  jobMatch.missing_skills.map((s, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/30"
                    >
                      {s}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-emerald-400 font-semibold">All required skills met!</span>
                )}
              </div>
            </div>
          </div>

          {/* Missing Preferred Skills (if any) */}
          {jobMatch.missing_preferred_skills && jobMatch.missing_preferred_skills.length > 0 && (
            <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-2">
              <span className="text-xs font-bold text-slate-300">
                Optional / Preferred Skills to Consider ({jobMatch.missing_preferred_skills.length})
              </span>
              <div className="flex flex-wrap gap-1.5">
                {jobMatch.missing_preferred_skills.map((s, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Candidate Facts State */}
          {jobMatch.candidate_facts_state && (
            <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Candidate Facts Audit Trail
              </span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(jobMatch.candidate_facts_state).map(([fact, status]) => (
                  <div key={fact} className="flex items-center justify-between p-2 rounded bg-slate-900 border border-slate-800">
                    <span className="text-slate-300 capitalize">{fact.replace(/_/g, ' ')}:</span>
                    <span
                      className={`font-semibold capitalize px-2 py-0.5 rounded text-[10px] ${
                        status === 'verified'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : status === 'unknown'
                          ? 'bg-amber-500/20 text-amber-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}
                    >
                      {status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Explainable Decision Narrative */}
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-indigo-400">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Explainable Decision Narrative</span>
            </div>
            <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 font-mono whitespace-pre-line leading-relaxed">
              {jobMatch.explanation}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950 flex items-center justify-between">
          <span className="text-xs text-slate-500 hidden sm:inline">
            Rule-based deterministic scoring engine. Zero LLM score hallucination.
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-white"
            >
              Close
            </button>
            <a
              href={`/documents?job_id=${jobMatch.job_id}`}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-md transition-colors flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span>Tailor Resume / Letter</span>
            </a>
            {jobMatch.job?.canonical_url && (
              <a
                href={jobMatch.job.canonical_url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-md transition-colors"
              >
                Apply on Platform ↗
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
