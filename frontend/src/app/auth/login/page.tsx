'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await api.login({ email, password });
      router.push('/profile');
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Authentication failed. Please check your credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  const fillDemoCandidate = () => {
    setEmail('alex.morgan@example.com');
    setPassword('CareerPilot2026!');
    setError(null);
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4 py-16 bg-[#0B0B0C]">
      <div className="max-w-md w-full space-y-7 bg-[#121215] p-8 rounded-[4px] border border-[#222227]">
        <div className="space-y-1.5 text-center">
          <div className="inline-flex items-center justify-center w-9 h-9 rounded-[3px] bg-[#16161B] text-[#0070F3] mb-2 border border-[#26262D]">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h1 className="text-xl font-medium tracking-tight text-white">Sign In to CareerPilot</h1>
          <p className="text-[13px] text-[#A1A1AA]">Access your job matches, profile, and autonomous applications</p>
        </div>

        {error && (
          <div className="p-3 rounded-[3px] bg-rose-950/20 border border-rose-900/40 text-rose-300 text-[13px] flex items-start gap-2">
            <svg className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-medium text-[#D4D4D8] mb-1.5" htmlFor="email">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-[3px] bg-[#0E0E11] border border-[#26262D] text-white placeholder-[#71717A] text-[13px] focus:outline-none focus:border-[#0070F3]"
              placeholder="candidate@example.com"
            />
          </div>

          <div>
            <label className="block text-[12px] font-medium text-[#D4D4D8] mb-1.5" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-[3px] bg-[#0E0E11] border border-[#26262D] text-white placeholder-[#71717A] text-[13px] focus:outline-none focus:border-[#0070F3]"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-[3px] bg-[#0070F3] hover:bg-[#0060DF] disabled:opacity-50 text-white font-medium text-[13px] transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <div className="pt-3 border-t border-[#1F1F24] flex flex-col gap-3 text-center">
          <button
            type="button"
            onClick={fillDemoCandidate}
            className="text-[12px] font-mono text-[#D4D4D8] hover:text-white transition-colors py-2 px-3 rounded-[3px] border border-[#2A2A33] bg-[#16161B] hover:bg-[#1C1C22]"
          >
            Fill Demo Candidate (Alex Morgan)
          </button>

          <p className="text-[12px] text-[#A1A1AA]">
            Don&apos;t have an account?{' '}
            <Link href="/auth/register" className="text-[#3291FF] hover:underline font-medium">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
