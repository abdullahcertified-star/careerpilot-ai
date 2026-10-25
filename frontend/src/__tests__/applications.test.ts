import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApplicationApprovalRequest, ApplicationStartRequest } from '../lib/api';

describe('Applications & LangGraph Workflow Client API (Phase 6)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('initiates a durable application workflow via POST /applications/start', async () => {
    const mockApp = {
      id: 10,
      user_id: 1,
      job_id: 101,
      workflow_thread_id: 'thread_1_abcd1234efgh',
      idempotency_key: 'idemp_key_1',
      status: 'awaiting_approval',
      approval_status: 'pending',
      submission_mode: 'manual_handoff',
      application_payload: { target_company: 'CloudScale Corp' },
      tracking_metadata: {},
      retry_count: 0,
      max_retries: 3,
      created_at: '2026-10-24T12:00:00Z',
      updated_at: '2026-10-24T12:00:00Z',
      job_title: 'Senior Software Engineer',
      job_company: 'CloudScale Corp',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockApp,
    } as Response);

    const payload: ApplicationStartRequest = {
      job_id: 101,
      template_id: 'modern',
      submission_mode: 'manual_handoff',
      idempotency_key: 'idemp_key_1',
    };

    const res = await api.startApplicationWorkflow(payload);

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/applications/start');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual(payload);
    expect(res.id).toBe(10);
    expect(res.status).toBe('awaiting_approval');
    expect(res.approval_status).toBe('pending');
  });

  it('lists user applications with optional status filter', async () => {
    const mockList = [
      {
        id: 10,
        user_id: 1,
        status: 'awaiting_approval',
        approval_status: 'pending',
      },
    ];

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockList,
    } as Response);

    const res = await api.listApplications('awaiting_approval');

    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/applications?status=awaiting_approval');
    expect(res).toHaveLength(1);
    expect(res[0].status).toBe('awaiting_approval');
  });

  it('submits human approval decision via POST /applications/:id/approve', async () => {
    const mockApproved = {
      id: 10,
      user_id: 1,
      status: 'manual_handoff',
      approval_status: 'approved',
      tracking_metadata: { workflow_completed: true, confirmation_reference: 'CP-APP-10-12345' },
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockApproved,
    } as Response);

    const approvalPayload: ApplicationApprovalRequest = {
      approved: true,
      notes: 'Verified and approved by candidate.',
    };

    const res = await api.approveApplication(10, approvalPayload);

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/applications/10/approve');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual(approvalPayload);
    expect(res.approval_status).toBe('approved');
    expect(res.tracking_metadata.workflow_completed).toBe(true);
  });

  it('cancels application workflow via POST /applications/:id/cancel', async () => {
    const mockCancelled = {
      id: 10,
      user_id: 1,
      status: 'cancelled',
      approval_status: 'rejected',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockCancelled,
    } as Response);

    const res = await api.cancelApplication(10, 'Candidate withdrew');

    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/applications/10/cancel?reason=Candidate+withdrew');
    expect(init?.method).toBe('POST');
    expect(res.status).toBe('cancelled');
  });

  it('fetches workflow timeline history via GET /applications/:id/history', async () => {
    const mockLogs = [
      { id: 1, node_name: 'discover_job', status: 'completed', details: {}, attempt_number: 1, created_at: '2026-10-24T12:00:00Z' },
      { id: 2, node_name: 'human_approval', status: 'interrupted', details: {}, attempt_number: 1, created_at: '2026-10-24T12:01:00Z' },
    ];

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockLogs,
    } as Response);

    const logs = await api.getApplicationHistory(10);

    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/applications/10/history');
    expect(logs).toHaveLength(2);
    expect(logs[1].node_name).toBe('human_approval');
  });

  // Phase 7: Secure Review & Submission Tests
  it('fetches complete application package via GET /applications/:id/package', async () => {
    const mockPackage = {
      application_id: 10,
      user_id: 1,
      workflow_thread_id: 'thread_123',
      job: { id: 101, title: 'Engineer', company: 'Acme', canonical_url: 'https://example.com/job/1' },
      original_application_url: 'https://example.com/job/1',
      form_answers: { full_name: 'John Doe', email: 'john@example.com', work_authorization: 'US Citizen' },
      provider_capability: { provider_id: 'manual_handoff', submission_method: 'manual_handoff' },
      submission_method: 'manual_handoff',
      package_hash: 'hash_abc123',
      approval_status: 'pending',
      is_content_altered_since_approval: false,
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockPackage,
    } as Response);

    const pkg = await api.getApplicationPackage(10);
    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/applications/10/package');
    expect(pkg.package_hash).toBe('hash_abc123');
    expect(pkg.form_answers.full_name).toBe('John Doe');
  });

  it('updates proposed form answers via PUT /applications/:id/answers', async () => {
    const mockUpdatedPackage = {
      application_id: 10,
      approval_status: 'invalidated',
      package_hash: 'hash_new456',
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockUpdatedPackage,
    } as Response);

    const updatedAnswers = {
      full_name: 'John Updated',
      email: 'john@example.com',
      phone: '555-1234',
      location: 'Remote',
      work_authorization: 'Citizen',
      requires_sponsorship: false,
      notice_period: 'Immediate',
    };

    const res = await api.updateProposedAnswers(10, updatedAnswers);
    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/applications/10/answers');
    expect(init?.method).toBe('PUT');
    expect(res.approval_status).toBe('invalidated');
  });

  it('submits application package with unique submission key via POST /applications/:id/submit', async () => {
    const mockResult = {
      status: 'manual_handoff',
      receipt_reference: 'HANDOFF-10-key123',
      blind_resubmission_prevented: false,
      handoff_packet: {
        application_id: 10,
        original_application_url: 'https://example.com/job/1',
      },
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockResult,
    } as Response);

    const submitReq = {
      submission_key: 'sub_key_123',
      target_job_id: 101,
      confirmed_package_hash: 'hash_abc123',
    };

    const res = await api.submitApplicationPackage(10, submitReq);
    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain('/applications/10/submit');
    expect(init?.method).toBe('POST');
    expect(res.status).toBe('manual_handoff');
    expect(res.receipt_reference).toContain('HANDOFF-10');
  });
});
