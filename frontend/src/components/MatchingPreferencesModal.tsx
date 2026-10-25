'use client';

import React, { useState } from 'react';
import { api, MatchPreferencesUpdate } from '@/lib/api';

interface MatchingPreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPrefs?: {
    target_job_titles?: string[];
    location?: string;
    remote_preference?: string;
    work_authorization_status?: string;
  };
  onSaved: () => void;
}

export default function MatchingPreferencesModal({
  isOpen,
  onClose,
  initialPrefs,
  onSaved,
}: MatchingPreferencesModalProps) {
  const [titles, setTitles] = useState<string>(
    initialPrefs?.target_job_titles?.join(', ') || ''
  );
  const [location, setLocation] = useState<string>(initialPrefs?.location || '');
  const [remotePref, setRemotePref] = useState<string>(
    initialPrefs?.remote_preference || 'flexible'
  );
  const [workAuth, setWorkAuth] = useState<string>(
    initialPrefs?.work_authorization_status || 'unknown'
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const titlesArray = titles
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      const payload: MatchPreferencesUpdate = {
        target_job_titles: titlesArray,
        location: location.trim() || undefined,
        remote_preference: remotePref,
        work_authorization_status: workAuth,
      };

      await api.updateMatchingPreferences(payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update preferences');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">Target Matching Preferences</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Tune your target role criteria, work authorization status, and remote preferences.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-lg font-bold p-1"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-300 mb-1">
              Target Job Titles (Comma-Separated)
            </label>
            <input
              type="text"
              value={titles}
              onChange={(e) => setTitles(e.target.value)}
              placeholder="e.g. Backend Engineer, Python Developer, Tech Lead"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1">
              Preferred Candidate Location
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. San Francisco, CA or London, UK"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">
                Remote Preference
              </label>
              <select
                value={remotePref}
                onChange={(e) => setRemotePref(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="flexible">Flexible / Any</option>
                <option value="remote">Remote Only</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">Onsite Only</option>
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">
                Work Authorization
              </label>
              <select
                value={workAuth}
                onChange={(e) => setWorkAuth(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="authorized_without_sponsorship">Authorized (No Sponsorship)</option>
                <option value="us_citizen">US Citizen</option>
                <option value="permanent_resident">Permanent Resident (GC)</option>
                <option value="requires_sponsorship">Requires Sponsorship</option>
                <option value="unknown">Unknown / Unspecified</option>
              </select>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-indigo-950/40 border border-indigo-800/60 text-[11px] text-indigo-300">
            <strong>Zero-Assumption Principle:</strong> If work authorization is unknown or unspecified, the matching engine will never assume eligibility for roles mandating legal authorization.
          </div>

          {error && (
            <div className="p-2.5 rounded bg-red-950/50 border border-red-800 text-red-200 text-xs">
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg font-semibold text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold shadow-md transition-colors"
            >
              {saving ? 'Saving & Invalidating Matches...' : 'Save Preferences'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
