import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api, setToken, removeToken } from '../lib/api';

describe('Frontend API Client Unit Tests', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('manages auth tokens in localStorage', () => {
    expect(localStorage.getItem('careerpilot_token')).toBeNull();
    setToken('test_session_token_xyz');
    expect(localStorage.getItem('careerpilot_token')).toBe('test_session_token_xyz');
    removeToken();
    expect(localStorage.getItem('careerpilot_token')).toBeNull();
  });

  it('handles logout gracefully by clearing local token', async () => {
    setToken('active_token');
    // Mock global fetch to return ok response for logout
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ message: 'Logged out' }),
    } as unknown as Response);

    const res = await api.logout();
    expect(res.message).toBe('Logged out');
    expect(localStorage.getItem('careerpilot_token')).toBeNull();
  });

  it('parses error details from failed server responses', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid email or password.' }),
    } as unknown as Response);

    await expect(api.login({ email: 'bad@example.com', password: 'wrong' })).rejects.toThrow(
      'Invalid email or password.'
    );
  });
});
