'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export default function Home() {
  const [healthStatus, setHealthStatus] = useState<string>('Online');
  const [latency, setLatency] = useState<number | null>(null);

  useEffect(() => {
    const start = performance.now();
    api.checkHealth()
      .then(() => {
        setLatency(Math.round(performance.now() - start));
        setHealthStatus('Online');
      })
      .catch(() => {
        setHealthStatus('Offline / Standby');
      });
  }, []);

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col justify-between bg-[#0B0B0C] text-[#EDEDED]">
      {/* Main Content Area */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 w-full space-y-24">
        
        {/* Hero Section */}
        <div className="space-y-6 max-w-3xl">
          <div className="inline-flex items-center gap-2 text-[12px] font-mono tracking-tight text-[#8E8E93]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#0070F3]" />
            <span>Platform Release v0.1.0-production</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-[56px] font-medium tracking-[-0.035em] text-white leading-[1.08]">
            Autonomous Job Discovery &amp; Application Management
          </h1>

          <p className="text-[15px] sm:text-[16px] text-[#A1A1AA] leading-[1.65] font-normal max-w-2xl">
            Autonomous matching, deterministic fact extraction, and verifiable application tracking. Built with strict resource-level tenant isolation and zero-hallucination resume tailoring.
          </p>

          <div className="flex flex-wrap items-center gap-5 pt-3">
            <Link
              href="/auth/register"
              className="px-5 py-2.5 rounded-[3px] bg-[#161618] hover:bg-[#202024] text-white text-[13px] font-medium border border-[#2B2B30] transition-colors"
            >
              Create Candidate Account
            </Link>

            <Link
              href="/auth/login"
              className="text-[13px] font-normal text-[#8E8E93] hover:text-white transition-colors flex items-center gap-1.5"
            >
              <span>Sign In with Demo</span>
              <span aria-hidden="true">→</span>
            </Link>

            <span className="text-[#2A2A2E] hidden sm:inline">|</span>

            <Link
              href="/profile"
              className="text-[13px] font-normal text-[#8E8E93] hover:text-white transition-colors"
            >
              Candidate Profile Editor
            </Link>
          </div>
        </div>

        {/* Feature Grid: Separated with clean vertical divider lines instead of boxed cards */}
        <div className="border-y border-[#1F1F23]">
          <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#1F1F23]">
            
            {/* Feature 1 */}
            <div className="py-10 md:py-12 md:pr-10 space-y-3">
              <div className="text-[11px] font-mono tracking-wider text-[#8E8E93] uppercase">
                01 / Security &amp; Auth
              </div>
              <h2 className="text-[17px] font-medium tracking-tight text-white">
                PBKDF2 &amp; Server Sessions
              </h2>
              <p className="text-[13px] text-[#A1A1AA] leading-[1.65]">
                OWASP-compliant PBKDF2-HMAC-SHA256 password hashing with constant-time verification, cryptographic salt, and server-managed session tokens.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="py-10 md:py-12 md:px-10 space-y-3">
              <div className="text-[11px] font-mono tracking-wider text-[#8E8E93] uppercase">
                02 / Data Persistence
              </div>
              <h2 className="text-[17px] font-medium tracking-tight text-white">
                SQLAlchemy 2.x &amp; Alembic
              </h2>
              <p className="text-[13px] text-[#A1A1AA] leading-[1.65]">
                Strict declarative models for Users, Profiles, Skills, Education, Experience, and Certifications, migrated seamlessly via async Alembic.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="py-10 md:py-12 md:pl-10 space-y-3">
              <div className="text-[11px] font-mono tracking-wider text-[#8E8E93] uppercase">
                03 / Tenant Governance
              </div>
              <h2 className="text-[17px] font-medium tracking-tight text-white">
                Resource Ownership Checks
              </h2>
              <p className="text-[13px] text-[#A1A1AA] leading-[1.65]">
                Every candidate-owned record (skills, experiences, educations) is strictly validated at the API layer, blocking cross-tenant snooping.
              </p>
            </div>

          </div>
        </div>

        {/* Technical Specification Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-2 text-[12px] font-mono text-[#8E8E93]">
          <div>
            <div className="text-[#52525B] text-[11px] uppercase tracking-wider mb-1">Database Engine</div>
            <div className="text-[#EDEDED]">Neon PostgreSQL 16+</div>
          </div>
          <div>
            <div className="text-[#52525B] text-[11px] uppercase tracking-wider mb-1">Async Driver</div>
            <div className="text-[#EDEDED]">asyncpg / SQLAlchemy 2.x</div>
          </div>
          <div>
            <div className="text-[#52525B] text-[11px] uppercase tracking-wider mb-1">State Machine</div>
            <div className="text-[#EDEDED]">LangGraph Checkpointer</div>
          </div>
          <div>
            <div className="text-[#52525B] text-[11px] uppercase tracking-wider mb-1">Security Standard</div>
            <div className="text-[#EDEDED]">OWASP ASVS Compliant</div>
          </div>
        </div>

      </div>

      {/* Footer: Flat, solid black status bar */}
      <footer className="w-full border-t border-[#1F1F23] bg-[#0B0B0C] text-[12px] font-mono text-[#8E8E93]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-12 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#0070F3]" />
              <span>Backend API Status:</span>
              <span className="text-[#EDEDED] font-medium">{healthStatus}</span>
              {latency !== null && (
                <span className="text-[#52525B]">({latency}ms)</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-6">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-[#8E8E93] hover:text-white transition-colors"
            >
              API Docs: <span className="text-[#EDEDED]">/docs</span>
            </a>
            <span className="text-[#2A2A2E] hidden sm:inline">|</span>
            <span className="hidden sm:inline text-[#52525B]">
              CareerPilot AI &copy; 2026
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

