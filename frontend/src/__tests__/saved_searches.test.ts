import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';

describe('Phase 8: Saved Searches and Notifications API', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('creates, lists, pauses, and resumes saved searches', async () => {
    const mockCreated = {
      id: 10,
      user_id: 1,
      name: 'Python Remote Backend',
      role_title: 'Backend Engineer',
      keywords: ['Python', 'FastAPI'],
      location: 'Remote',
      work_mode: 'remote',
      employment_type: 'full_time',
      min_match_score: 75.0,
      interval_minutes: 60,
      provider_id: 'greenhouse',
      is_active: true,
      is_paused: false,
      consecutive_failures: 0,
      total_runs: 0,
      total_discovered: 0,
      created_at: '2026-10-25T12:00:00Z',
      updated_at: '2026-10-25T12:00:00Z',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockCreated,
    } as Response);

    const created = await api.createSavedSearch({
      name: 'Python Remote Backend',
      role_title: 'Backend Engineer',
      keywords: ['Python', 'FastAPI'],
      location: 'Remote',
      work_mode: 'remote',
      employment_type: 'full_time',
      min_match_score: 75.0,
      interval_minutes: 60,
      provider_id: 'greenhouse',
    });

    expect(fetchSpy).toHaveBeenCalled();
    const [calledUrl, calledOpts] = fetchSpy.mock.calls[0];
    expect(calledUrl).toContain('/saved-searches');
    expect(calledOpts?.method).toBe('POST');
    expect(created.name).toBe('Python Remote Backend');
    expect(created.min_match_score).toBe(75.0);

    // Pause test
    const mockPaused = { ...mockCreated, is_paused: true };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => mockPaused,
    } as Response);

    const paused = await api.pauseSavedSearch(10);
    expect(paused.is_paused).toBe(true);

    // Resume test
    const mockResumed = { ...mockCreated, is_paused: false };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => mockResumed,
    } as Response);

    const resumed = await api.resumeSavedSearch(10);
    expect(resumed.is_paused).toBe(false);
  });

  it('triggers run now and requests cancellation for a saved search scan', async () => {
    const mockRun = {
      id: 5,
      saved_search_id: 10,
      task_id: 'scan-run-10-20261025120000',
      status: 'completed',
      started_at: '2026-10-25T12:00:00Z',
      completed_at: '2026-10-25T12:00:05Z',
      duration_seconds: 5.2,
      retry_count: 0,
      discovered_count: 3,
      ingested_count: 2,
      duplicate_count: 1,
      high_match_count: 2,
      created_at: '2026-10-25T12:00:00Z',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockRun,
    } as Response);

    const runResult = await api.runSavedSearchNow(10);
    expect(fetchSpy).toHaveBeenCalled();
    const [runUrl, runOpts] = fetchSpy.mock.calls[0];
    expect(runUrl).toContain('/saved-searches/10/run-now');
    expect(runOpts?.method).toBe('POST');
    expect(runResult.discovered_count).toBe(3);
    expect(runResult.duplicate_count).toBe(1);

    // Cancellation test
    const mockCancel = {
      saved_search_id: 10,
      status: 'cancellation_requested',
      message: 'Cancellation requested for saved search scan 10',
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => mockCancel,
    } as Response);

    const cancelResult = await api.cancelSavedSearchScan(10);
    expect(cancelResult.status).toBe('cancellation_requested');
  });

  it('retrieves notifications, unread count, and marks notifications as read', async () => {
    const mockList = {
      items: [
        {
          id: 1,
          user_id: 1,
          type: 'high_match_job',
          title: 'High Match Job Discovered',
          message: 'Found Staff Backend Engineer matching 92.5%',
          data: { job_id: 42, match_score: 92.5 },
          is_read: false,
          created_at: '2026-10-25T12:00:00Z',
        },
        {
          id: 2,
          user_id: 1,
          type: 'pending_application_review',
          title: 'Pending Application Review',
          message: 'Application #8 awaits candidate review',
          data: { application_id: 8 },
          is_read: false,
          created_at: '2026-10-25T12:05:00Z',
        },
      ],
      total: 2,
      unread_count: 2,
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockList,
    } as Response);

    const notifs = await api.listNotifications();
    expect(notifs.items).toHaveLength(2);
    expect(notifs.unread_count).toBe(2);

    // Unread count
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ unread_count: 2 }),
    } as Response);
    const countResp = await api.getUnreadNotificationCount();
    expect(countResp.unread_count).toBe(2);

    // Mark single read
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...mockList.items[0], is_read: true, read_at: '2026-10-25T12:10:00Z' }),
    } as Response);
    const readItem = await api.markNotificationRead(1);
    expect(readItem.is_read).toBe(true);

    // Mark all read
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'All notifications marked as read', count: 2 }),
    } as Response);
    const markAllResp = await api.markAllNotificationsRead();
    expect(markAllResp.count).toBe(2);
  });
});
