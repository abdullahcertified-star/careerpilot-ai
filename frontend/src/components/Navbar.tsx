'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, User } from '@/lib/api';

export default function Navbar() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api.getMe()
      .then((u) => setUser(u))
      .catch(() => setUser(null));
  }, []);

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    router.push('/auth/login');
  };

  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-indigo-500/20 shadow-lg">
              CP
            </span>
            <span className="font-bold text-xl tracking-tight text-white">
              CareerPilot <span className="text-indigo-400">AI</span>
            </span>
          </Link>
          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-300">
            <Link href="/" className="hover:text-white transition-colors">
              Overview
            </Link>
            <Link href="/jobs" className="hover:text-white transition-colors">
              Jobs &amp; Discovery
            </Link>
            <Link href="/documents" className="hover:text-white transition-colors">
              Document Studio
            </Link>
            <Link href="/applications" className="hover:text-white transition-colors text-indigo-300 font-semibold">
              Applications &amp; Tracking
            </Link>
            <Link href="/resumes" className="hover:text-white transition-colors">
              Resumes &amp; Ingestion
            </Link>
            <Link href="/profile" className="hover:text-white transition-colors">
              Candidate Profile
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user ? (
            <div className="flex items-center gap-4">
              <span className="text-xs text-slate-400 hidden sm:inline">
                Signed in as <strong className="text-slate-200">{user.full_name}</strong>
              </span>
              <button
                onClick={handleLogout}
                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Log Out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Link
                href="/auth/login"
                className="text-xs font-semibold px-3 py-1.5 rounded-md hover:text-white text-slate-300 transition-colors"
              >
                Sign In
              </Link>
              <Link
                href="/auth/register"
                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm"
              >
                Get Started
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
