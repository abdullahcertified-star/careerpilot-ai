'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, User } from '@/lib/api';

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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

  const navLinks = [
    { label: 'Overview', href: '/' },
    { label: 'Jobs & Discovery', href: '/jobs' },
    { label: 'Applications', href: '/applications' },
    { label: 'Document Studio', href: '/documents' },
    { label: 'Resumes', href: '/resumes' },
    { label: 'Profile', href: '/profile' },
  ];

  return (
    <header className="border-b border-[#1F1F24] bg-[#0B0B0C] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Brand & Main Navigation */}
        <div className="flex items-center gap-7">
          <Link href="/" className="flex items-center gap-2.5 group">
            <span className="w-6 h-6 rounded-[3px] bg-[#121215] border border-[#26262D] flex items-center justify-center text-white font-mono text-[11px] font-medium tracking-tight group-hover:border-[#0070F3] transition-colors">
              CP
            </span>
            <span className="font-medium text-[14px] tracking-tight text-white">
              CareerPilot <span className="text-[#A1A1AA]">AI</span>
            </span>
          </Link>

          {/* Navigation Links */}
          <nav className="hidden lg:flex items-center gap-5 text-[13px] font-normal">
            {navLinks.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={`transition-colors py-1 ${
                    isActive
                      ? 'text-white font-medium border-b border-[#0070F3]'
                      : 'text-[#9E9EA8] hover:text-[#EDEDED]'
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}

            {/* Sharp Distinct Blue Status Indicator */}
            <div className="flex items-center gap-2 pl-3 border-l border-[#222227] text-[12px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-[#0070F3] inline-block shadow-[0_0_6px_rgba(0,112,243,0.6)]" />
              <span className="text-[#A1A1AA]">Online</span>
            </div>
          </nav>
        </div>

        {/* Auth / Account Actions */}
        <div className="hidden sm:flex items-center gap-3">
          {user ? (
            <div className="flex items-center gap-3">
              <span className="text-[12px] text-[#A1A1AA] font-mono">
                {user.email}
              </span>
              <button
                onClick={handleLogout}
                className="text-[12px] font-medium px-3 py-1.5 rounded-[3px] bg-[#141418] hover:bg-[#1E1E24] text-[#EDEDED] border border-[#26262D] transition-colors"
              >
                Log Out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/auth/login"
                className="text-[13px] font-normal text-[#A1A1AA] hover:text-white transition-colors px-3 py-1.5"
              >
                Sign In
              </Link>
              <Link
                href="/auth/register"
                className="text-[13px] font-medium px-3.5 py-1.5 rounded-[3px] bg-[#16161B] hover:bg-[#202028] text-white border border-[#2D2D36] transition-colors"
              >
                Get Started
              </Link>
            </div>
          )}
        </div>

        {/* Mobile Hamburger Toggle */}
        <div className="flex lg:hidden items-center gap-2">
          <div className="flex items-center gap-1.5 text-[11px] font-mono mr-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#0070F3]" />
            <span className="text-[#A1A1AA]">Online</span>
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-1.5 rounded-[3px] text-[#A1A1AA] hover:text-white bg-[#121215] border border-[#222227]"
            aria-label="Toggle Navigation"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-t border-[#1F1F24] bg-[#0E0E11] px-4 py-3 space-y-2">
          {navLinks.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              onClick={() => setMobileMenuOpen(false)}
              className={`block px-3 py-2 rounded-[3px] text-[13px] ${
                pathname === item.href
                  ? 'bg-[#18181D] text-white font-medium'
                  : 'text-[#A1A1AA] hover:text-white'
              }`}
            >
              {item.label}
            </Link>
          ))}
          <div className="pt-2 border-t border-[#1F1F24] flex items-center justify-between">
            {user ? (
              <button
                onClick={handleLogout}
                className="w-full text-left px-3 py-2 text-[13px] text-rose-400 font-medium"
              >
                Log Out ({user.email})
              </button>
            ) : (
              <div className="flex items-center gap-2 w-full pt-1">
                <Link
                  href="/auth/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex-1 text-center py-2 text-[13px] text-[#A1A1AA] hover:text-white bg-[#141418] border border-[#26262D] rounded-[3px]"
                >
                  Sign In
                </Link>
                <Link
                  href="/auth/register"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex-1 text-center py-2 text-[13px] text-white bg-[#0070F3] rounded-[3px] font-medium"
                >
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}


