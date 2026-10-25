import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, DocumentGenerateRequest, DocumentUpdateRequest } from '../lib/api';

describe('Document Studio Client API (Phase 5)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('generates a tailored document via POST /documents/generate', async () => {
    const mockDoc = {
      id: 1,
      user_id: 42,
      job_id: 101,
      doc_type: 'resume',
      title: 'Senior Software Engineer Resume - Stripe',
      template_id: 'modern',
      candidate_profile_version: 1,
      created_at: '2026-10-24T12:00:00Z',
      updated_at: '2026-10-24T12:00:00Z',
      versions_count: 1,
      job_title: 'Senior Software Engineer',
      job_company: 'Stripe',
      latest_version: {
        id: 10,
        document_id: 1,
        version_number: 1,
        structured_data: {
          full_name: 'Alex Mercer',
          email: 'alex@example.com',
          target_title: 'Senior Software Engineer',
          target_company: 'Stripe',
          professional_summary: 'Senior Engineer with verified backend expertise.',
          highlighted_skills: ['Python', 'PostgreSQL'],
          experience: [],
          projects: [],
          education: [],
          certifications: [],
        },
        formatted_text: 'Alex Mercer\nSenior Software Engineer...',
        model_name: 'gpt-4o-mini',
        prompt_version: 'v1.0.0-resume-grounded',
        validation_report: {
          is_clean: true,
          factual_confidence_score: 100.0,
          total_claims_checked: 5,
          verified_claims_count: 5,
          unsupported_claims: [],
          verified_facts: ['Python', 'PostgreSQL'],
          warnings: [],
        },
        is_approved: false,
        change_summary: 'Initial factual generation',
        created_at: '2026-10-24T12:00:00Z',
      },
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockDoc,
    } as Response);

    const payload: DocumentGenerateRequest = {
      job_id: 101,
      doc_type: 'resume',
      template_id: 'modern',
      custom_instructions: 'Focus on distributed systems',
    };

    const res = await api.generateDocument(payload);

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/documents/generate');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual(payload);
    expect(res.id).toBe(1);
    expect(res.latest_version?.validation_report.is_clean).toBe(true);
    expect(res.latest_version?.validation_report.factual_confidence_score).toBe(100.0);
  });

  it('lists documents with optional job and doc_type filters', async () => {
    const mockList = [
      {
        id: 1,
        user_id: 42,
        job_id: 101,
        doc_type: 'resume',
        title: 'Resume - Stripe',
        template_id: 'modern',
        candidate_profile_version: 1,
        created_at: '2026-10-24T12:00:00Z',
        updated_at: '2026-10-24T12:00:00Z',
        versions_count: 2,
      },
    ];

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockList,
    } as Response);

    const res = await api.listDocuments({ job_id: 101, doc_type: 'resume' });

    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/documents?job_id=101&doc_type=resume');
    expect(res).toHaveLength(1);
  });

  it('fetches document details and version history', async () => {
    const mockDoc = { id: 1, title: 'Resume - Stripe' };
    const mockVersions = [
      { id: 10, version_number: 1, change_summary: 'Initial generation' },
      { id: 11, version_number: 2, change_summary: 'User manual edits' },
    ];

    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDoc,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockVersions,
      } as Response);

    const doc = await api.getDocument(1);
    const versions = await api.listDocumentVersions(1);

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(doc.id).toBe(1);
    expect(versions).toHaveLength(2);
    expect(versions[1].version_number).toBe(2);
  });

  it('saves an edited document as a new immutable version without mutating earlier versions', async () => {
    const mockUpdatedVersion = {
      id: 12,
      document_id: 1,
      version_number: 2,
      structured_data: {
        full_name: 'Alex Mercer',
        professional_summary: 'Updated summary highlighting verified Python projects.',
      },
      formatted_text: 'Updated formatted text',
      model_name: 'user_edit',
      prompt_version: 'manual_v2',
      validation_report: {
        is_clean: true,
        factual_confidence_score: 100.0,
        total_claims_checked: 4,
        verified_claims_count: 4,
        unsupported_claims: [],
        verified_facts: ['Python'],
        warnings: [],
      },
      is_approved: true,
      change_summary: 'Revised summary and approved version',
      created_at: '2026-10-24T12:30:00Z',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockUpdatedVersion,
    } as Response);

    const updatePayload: DocumentUpdateRequest = {
      structured_data: {
        full_name: 'Alex Mercer',
        professional_summary: 'Updated summary highlighting verified Python projects.',
      },
      template_id: 'classic',
      change_summary: 'Revised summary and approved version',
      is_approved: true,
    };

    const res = await api.updateDocumentVersion(1, updatePayload);

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/documents/1/versions');
    expect(init?.method).toBe('PUT');
    expect(res.version_number).toBe(2);
    expect(res.is_approved).toBe(true);
    expect(res.change_summary).toBe('Revised summary and approved version');
  });

  it('downloads document blob for PDF and DOCX with correct headers and filename', async () => {
    localStorage.setItem('careerpilot_token', 'mock_jwt_token');

    const fakeBlob = new Blob(['%PDF-1.4 test binary'], { type: 'application/pdf' });
    const headers = new Headers();
    headers.set('Content-Disposition', 'attachment; filename="Tailored_Resume_Stripe.pdf"');

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers,
      blob: async () => fakeBlob,
    } as unknown as Response);

    const result = await api.downloadDocumentBlob(1, 'pdf', 10);

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/documents/1/download?format=pdf&version_id=10');
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer mock_jwt_token');
    expect(result.filename).toBe('Tailored_Resume_Stripe.pdf');
    expect(result.blob.size).toBe(fakeBlob.size);
  });
});
