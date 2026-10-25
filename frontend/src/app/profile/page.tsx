'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, FullProfile } from '@/lib/api';

export default function ProfilePage() {
  const [data, setData] = useState<FullProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form states
  const [headline, setHeadline] = useState('');
  const [bio, setBio] = useState('');
  const [location, setLocation] = useState('');
  const [remotePreference, setRemotePreference] = useState('flexible');
  const [targetTitles, setTargetTitles] = useState('');

  // New skill form
  const [skillName, setSkillName] = useState('');
  const [skillCategory, setSkillCategory] = useState('technical');
  const [skillProficiency, setSkillProficiency] = useState('intermediate');
  const [skillYears, setSkillYears] = useState(2.0);
  const [addingSkill, setAddingSkill] = useState(false);

  useEffect(() => {
    let ignore = false;
    api.getProfile()
      .then((profileData) => {
        if (!ignore) {
          setData(profileData);
          if (profileData.profile) {
            setHeadline(profileData.profile.headline || '');
            setBio(profileData.profile.bio || '');
            setLocation(profileData.profile.location || '');
            setRemotePreference(profileData.profile.remote_preference || 'flexible');
            setTargetTitles((profileData.profile.target_job_titles || []).join(', '));
          }
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          if (err instanceof Error) {
            setError(err.message);
          } else {
            setError('Failed to load profile. Please make sure you are signed in.');
          }
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    const titlesList = targetTitles
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      await api.updateProfile({
        headline,
        bio,
        location,
        remote_preference: remotePreference,
        target_job_titles: titlesList,
      });
      setSuccess('Profile updated successfully!');
      setTimeout(() => setSuccess(null), 4000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to update profile.');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleAddSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!skillName.trim()) return;

    setAddingSkill(true);
    try {
      const newSkill = await api.addSkill({
        name: skillName.trim(),
        category: skillCategory,
        proficiency_level: skillProficiency,
        years_experience: skillYears,
      });
      if (data) {
        setData({
          ...data,
          skills: [...data.skills, newSkill],
        });
      }
      setSkillName('');
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setAddingSkill(false);
    }
  };

  const handleDeleteSkill = async (id: number) => {
    try {
      await api.deleteSkill(id);
      if (data) {
        setData({
          ...data,
          skills: data.skills.filter((s) => s.id !== id),
        });
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      }
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin mb-4" />
        <p className="text-sm text-slate-400">Loading candidate profile...</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center">
        <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 mx-auto mb-4 flex items-center justify-center border border-amber-500/20">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Authentication Required</h2>
        <p className="text-sm text-slate-400 mb-6">{error}</p>
        <Link
          href="/auth/login"
          className="inline-flex px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm transition-colors shadow-lg shadow-indigo-600/20"
        >
          Sign In to View Profile
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-8">
      {/* Header Profile Summary */}
      <div className="bg-slate-900/60 p-6 sm:p-8 rounded-2xl border border-slate-800 backdrop-blur-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <h1 className="text-2xl font-bold text-white">{data?.full_name}</h1>
            <p className="text-sm text-indigo-400 mt-0.5">{data?.email}</p>
          </div>
          <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            Active Candidate
          </span>
        </div>

        {success && (
          <div className="mt-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm">
            {success}
          </div>
        )}

        {/* Profile Details Form */}
        <form onSubmit={handleSaveProfile} className="mt-6 space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="headline">
                Professional Headline
              </label>
              <input
                id="headline"
                type="text"
                value={headline}
                onChange={(e) => setHeadline(e.target.value)}
                placeholder="Senior Full Stack AI Systems Architect"
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="location">
                Location
              </label>
              <input
                id="location"
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="San Francisco, CA (or Remote)"
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="bio">
              Executive Summary / Bio
            </label>
            <textarea
              id="bio"
              rows={3}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="Summary of experience, technical specializations, and career goals..."
              className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="remotePreference">
                Work Preference
              </label>
              <select
                id="remotePreference"
                value={remotePreference}
                onChange={(e) => setRemotePreference(e.target.value)}
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="remote">Fully Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-site</option>
                <option value="flexible">Flexible</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="targetTitles">
                Target Roles (comma-separated)
              </label>
              <input
                id="targetTitles"
                type="text"
                value={targetTitles}
                onChange={(e) => setTargetTitles(e.target.value)}
                placeholder="AI Architect, Staff Engineer, Full Stack Lead"
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2.5 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] disabled:opacity-50 text-white font-medium text-xs transition-colors shadow-[0_0_12px_rgba(0,112,243,0.3)]"
          >
            {saving ? 'Saving Profile...' : 'Save Profile Changes'}
          </button>
        </form>
      </div>

      {/* Skills Management Section */}
      <div className="bg-slate-900/60 p-6 sm:p-8 rounded-2xl border border-slate-800 backdrop-blur-xl space-y-6">
        <div>
          <h2 className="text-lg font-bold text-white">Skills & Competencies</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Add your verified technical skills for autonomous job matching.
          </p>
        </div>

        {/* Existing skills list */}
        <div className="flex flex-wrap gap-2">
          {data?.skills && data.skills.length > 0 ? (
            data.skills.map((skill) => (
              <span
                key={skill.id}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 border border-slate-700/60 text-slate-200"
              >
                <span>{skill.name}</span>
                <span className="text-[10px] text-indigo-400 uppercase tracking-wider">
                  {skill.proficiency_level}
                </span>
                <button
                  type="button"
                  onClick={() => handleDeleteSkill(skill.id)}
                  className="text-slate-400 hover:text-rose-400 transition-colors ml-1"
                  title="Remove skill"
                >
                  ×
                </button>
              </span>
            ))
          ) : (
            <p className="text-xs text-slate-500 italic">No skills added yet.</p>
          )}
        </div>

        {/* Add skill form */}
        <form onSubmit={handleAddSkill} className="pt-4 border-t border-slate-800 flex flex-wrap sm:flex-nowrap gap-3 items-end">
          <div className="flex-1 min-w-[140px]">
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="skillName">
              Skill Name
            </label>
            <input
              id="skillName"
              type="text"
              required
              value={skillName}
              onChange={(e) => setSkillName(e.target.value)}
              placeholder="e.g. LangGraph"
              className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="w-32">
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="skillCategory">
              Category
            </label>
            <select
              id="skillCategory"
              value={skillCategory}
              onChange={(e) => setSkillCategory(e.target.value)}
              className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="technical">Technical</option>
              <option value="soft">Soft</option>
              <option value="domain">Domain</option>
            </select>
          </div>

          <div className="w-32">
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="skillProficiency">
              Proficiency
            </label>
            <select
              id="skillProficiency"
              value={skillProficiency}
              onChange={(e) => setSkillProficiency(e.target.value)}
              className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
              <option value="expert">Expert</option>
            </select>
          </div>

          <div className="w-24">
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="skillYears">
              Years
            </label>
            <input
              id="skillYears"
              type="number"
              min="0"
              step="0.5"
              value={skillYears}
              onChange={(e) => setSkillYears(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <button
            type="submit"
            disabled={addingSkill}
            className="px-4 py-2 rounded-[4px] bg-[#0070F3] hover:bg-[#0060DF] disabled:opacity-50 text-white font-medium text-xs transition-colors shrink-0 shadow-[0_0_10px_rgba(0,112,243,0.3)]"
          >
            {addingSkill ? 'Adding...' : '+ Add Skill'}
          </button>
        </form>
      </div>

      {/* Experience & Education Preview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div className="bg-slate-900/60 p-6 rounded-2xl border border-slate-800 backdrop-blur-xl">
          <h3 className="text-sm font-bold text-white mb-3">Experience History</h3>
          {data?.experiences && data.experiences.length > 0 ? (
            <div className="space-y-3">
              {data.experiences.map((exp) => (
                <div key={exp.id} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <p className="text-xs font-semibold text-white">{exp.title}</p>
                  <p className="text-[11px] text-slate-400">{exp.company}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 italic">No experience records found.</p>
          )}
        </div>

        <div className="bg-slate-900/60 p-6 rounded-2xl border border-slate-800 backdrop-blur-xl">
          <h3 className="text-sm font-bold text-white mb-3">Education History</h3>
          {data?.educations && data.educations.length > 0 ? (
            <div className="space-y-3">
              {data.educations.map((edu) => (
                <div key={edu.id} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <p className="text-xs font-semibold text-white">{edu.degree} in {edu.field_of_study}</p>
                  <p className="text-[11px] text-slate-400">{edu.institution}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 italic">No education records found.</p>
          )}
        </div>
      </div>
    </div>
  );
}
