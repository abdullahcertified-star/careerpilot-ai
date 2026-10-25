import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';

describe('Job Discovery Client API', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('searches jobs with parameters and normalizes query string', async () => {
    const mockResponse = {
      items: [
        {
          id: 1,
          source: 'greenhouse',
          source_id: 'gh-101',
          canonical_url: 'https://job-boards.greenhouse.io/gitlab/jobs/101',
          title: 'Senior Python Engineer',
          company: 'GitLab',
          description: 'High performance backend architecture.',
          location: 'Remote',
          work_mode: 'remote',
          employment_type: 'full_time',
          retrieved_at: '2026-10-11T12:00:00Z',
          is_active: true,
          is_saved: false,
          created_at: '2026-10-11T12:00:00Z',
          updated_at: '2026-10-11T12:00:00Z',
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 15,
      has_more: false,
      warnings: [],
      external_search_url: null,
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const result = await api.searchJobs({
      query: 'Python',
      location: 'Remote',
      work_mode: 'remote',
      provider_id: 'greenhouse',
    });

    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/jobs/search');
    expect(calledUrl).toContain('query=Python');
    expect(calledUrl).toContain('location=Remote');
    expect(calledUrl).toContain('work_mode=remote');
    expect(calledUrl).toContain('provider_id=greenhouse');

    expect(result.items).toHaveLength(1);
    expect(result.items[0].title).toBe('Senior Python Engineer');
    expect(result.items[0].source).toBe('greenhouse');
  });

  it('imports job from public URL', async () => {
    const mockJob = {
      id: 2,
      source: 'manual_import',
      source_id: 'sha256-hash',
      canonical_url: 'https://careers.example.com/jobs/devops',
      title: 'DevOps Architect',
      company: 'Example Corp',
      description: 'Terraform and Kubernetes infrastructure.',
      location: 'New York, NY',
      work_mode: 'hybrid',
      employment_type: 'full_time',
      retrieved_at: '2026-10-11T12:00:00Z',
      is_active: true,
      is_saved: false,
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockJob,
    } as Response);

    const result = await api.importJobUrl('https://careers.example.com/jobs/devops');

    expect(fetchSpy).toHaveBeenCalled();
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toContain('/jobs/import-url');
    expect(options?.method).toBe('POST');
    expect(JSON.parse(options?.body as string)).toEqual({
      url: 'https://careers.example.com/jobs/devops',
    });

    expect(result.title).toBe('DevOps Architect');
    expect(result.source).toBe('manual_import');
  });

  it('saves and unsaves a job with candidate tracking', async () => {
    const mockSaved = {
      id: 10,
      user_id: 1,
      job_id: 2,
      status: 'saved',
      notes: 'Follow up next week',
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
      job: {
        id: 2,
        title: 'DevOps Architect',
      },
    };

    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockSaved,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Job bookmark successfully removed.' }),
      } as Response);

    const saved = await api.saveJob(2, { status: 'saved', notes: 'Follow up next week' });
    expect(saved.id).toBe(10);
    expect(saved.status).toBe('saved');

    const unsaved = await api.unsaveJob(2);
    expect(unsaved.message).toContain('removed');
  });
});
