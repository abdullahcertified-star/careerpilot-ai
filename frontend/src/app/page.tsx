'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export default function Home() {
  const [healthStatus, setHealthStatus] = useState<string>('Checking...');

  useEffect(() => {
    api.checkHealth()
      .then((res) => setHealthStatus(`Online (${res.app_name})`))
      .catch(() => setHealthStatus('Offline / Local Development'));
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-16">
      {/* Hero Section */}
      <div className="text-center space-y-6 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          Phase 1: Secure Foundation & Candidate Profiles Ready
        </div>
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-tight">
          Autonomous Job Discovery & <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">Application Management</span>
        </h1>
        <p className="text-base sm:text-lg text-slate-400 leading-relaxed">
          CareerPilot AI empowers candidates with verified profile ownership, persistent PostgreSQL &amp; SQLAlchemy 2.x data storage, secure PBKDF2 authentication, and multi-tier agentic matching.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <Link
            href="/auth/register"
            className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-600/25"
          >
            Create Candidate Account
          </Link>
          <Link
            href="/auth/login"
            className="px-6 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm border border-slate-700 transition-all"
          >
            Sign In with Demo
          </Link>
          <Link
            href="/profile"
            className="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-indigo-400 font-semibold text-sm border border-indigo-500/30 transition-all"
          >
            Candidate Profile Editor
          </Link>
        </div>
      </div>

      {/* Architecture Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm space-y-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center border border-indigo-500/20">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-white">PBKDF2 & Server Sessions</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            OWASP-compliant PBKDF2-HMAC-SHA256 password hashing with constant-time verification, cryptographic salt, and server-managed session tokens.
          </p>
        </div>

        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm space-y-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 text-cyan-400 flex items-center justify-center border border-cyan-500/20">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2 1.5 3 3.5 3h9c2 0 3.5-1 3.5-3V7c0-2-1.5-3-3.5-3h-9C5.5 4 4 5 4 7zM9 9h6M9 13h4" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-white">SQLAlchemy 2.x & Alembic</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Strict declarative models for Users, Profiles, Skills, Education, Experience, and Certifications, migrated seamlessly via async Alembic.
          </p>
        </div>

        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm space-y-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center border border-purple-500/20">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 004 11m0 0c0-1.873.344-3.665.975-5.314" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-white">Resource Ownership Checks</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Every candidate-owned record (skills, experiences, educations) is strictly validated at the API layer, blocking cross-tenant snooping.
          </p>
        </div>
      </div>

      {/* System Status Footer */}
      <div className="p-4 rounded-xl bg-slate-900/30 border border-slate-800 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span>Backend API Status:</span>
          <span className="font-semibold text-indigo-400">{healthStatus}</span>
        </div>
        <div>
          <span>API Docs: </span>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="text-slate-300 hover:text-white underline font-mono"
          >
            /docs (Swagger)
          </a>
        </div>
      </div>
    </div>
  );
}
