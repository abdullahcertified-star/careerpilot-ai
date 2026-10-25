import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';

describe('Deterministic Job Matching Client API', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lists ranked matches with filter parameters and score thresholds', async () => {
    const mockRanked = {
      items: [
        {
          id: 1,
          user_id: 10,
          job_id: 101,
          total_score: 88.5,
          component_scores: {
            required_skills: 100.0,
            role_relevance: 80.0,
            experience_seniority: 80.0,
            education_certifications: 90.0,
            location_work_authorization: 100.0,
            preferred_skills: 100.0,
          },
          matched_skills: [{ skill: 'python', proficiency: 'expert', years: 5.0, verified: true }],
          missing_skills: [],
          missing_preferred_skills: [],
          explanation: 'Deterministic evaluation completed.',
          is_stale: false,
          candidate_profile_version: 1,
          scoring_version: '1.0.0',
          evaluated_at: '2026-10-24T12:00:00Z',
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      scoring_version: '1.0.0',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockRanked,
    } as Response);

    const res = await api.listRankedMatches({
      min_score: 85,
      sort_by: 'score_desc',
      role: 'Backend',
      work_mode: 'remote',
    });

    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/matches');
    expect(calledUrl).toContain('min_score=85');
    expect(calledUrl).toContain('sort_by=score_desc');
    expect(calledUrl).toContain('role=Backend');
    expect(calledUrl).toContain('work_mode=remote');

    expect(res.items).toHaveLength(1);
    expect(res.items[0].total_score).toBe(88.5);
    expect(res.items[0].scoring_version).toBe('1.0.0');
    expect(res.items[0].component_scores.required_skills).toBe(100.0);
  });

  it('fetches match details and explainability narrative for a specific job', async () => {
    const mockDetail = {
      id: 5,
      user_id: 10,
      job_id: 42,
      total_score: 72.0,
      component_scores: {
        required_skills: 66.7,
        role_relevance: 75.0,
        experience_seniority: 80.0,
        education_certifications: 90.0,
        location_work_authorization: 65.0,
        preferred_skills: 50.0,
      },
      matched_skills: [{ skill: 'python', proficiency: 'advanced', years: 3.5, verified: true }],
      missing_skills: ['docker'],
      missing_preferred_skills: ['kubernetes'],
      candidate_facts_state: {
        work_authorization: 'unknown',
        work_mode: 'verified',
      },
      explanation: 'Work authorization unknown; not assumed eligible.',
      is_stale: false,
      candidate_profile_version: 2,
      scoring_version: '1.0.0',
      evaluated_at: '2026-10-24T12:00:00Z',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockDetail,
    } as Response);

    const res = await api.getMatchDetail(42);
    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/matches/42');
    expect(res.total_score).toBe(72.0);
    expect(res.missing_skills).toContain('docker');
    expect(res.candidate_facts_state?.work_authorization).toBe('unknown');
  });

  it('triggers match recalculation across active jobs', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Recalculated 25 job matches.', evaluated_count: 25 }),
    } as Response);

    const res = await api.recalculateMatches();
    expect(fetchSpy).toHaveBeenCalled();
    const [calledUrl, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toContain('/matches/recalculate');
    expect(options.method).toBe('POST');
    expect(res.evaluated_count).toBe(25);
  });

  it('retrieves deterministic scoring weights summing to 100%', async () => {
    const mockWeights = {
      scoring_version: '1.0.0',
      weights: {
        required_skills: 0.35,
        role_relevance: 0.25,
        experience_seniority: 0.15,
        education_certifications: 0.10,
        location_work_authorization: 0.10,
        preferred_skills: 0.05,
      },
      rules: ['Strictly deterministic', 'Zero assumption on unknown facts'],
    };

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockWeights,
    } as Response);

    const res = await api.getScoringWeights();
    const sum = Object.values(res.weights).reduce((a, b) => a + b, 0);
    expect(Math.round(sum * 100) / 100).toBe(1.0);
    expect(res.weights.required_skills).toBe(0.35);
  });

  it('updates candidate matching preferences', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Matching preferences updated.' }),
    } as Response);

    const res = await api.updateMatchingPreferences({
      target_job_titles: ['Staff Backend Engineer'],
      remote_preference: 'remote',
      work_authorization_status: 'authorized_without_sponsorship',
    });

    expect(fetchSpy).toHaveBeenCalled();
    const [calledUrl, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toContain('/matches/preferences');
    expect(options.method).toBe('PUT');
    expect(res.message).toBe('Matching preferences updated.');
  });
});
