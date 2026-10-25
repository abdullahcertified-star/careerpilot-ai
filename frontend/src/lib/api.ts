/**
 * Client API utilities for CareerPilot AI
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface AuthResponse {
  user: User;
  token: string;
  token_type: string;
  expires_at: string;
  message: string;
}

export interface Profile {
  id: number;
  user_id: number;
  headline: string | null;
  bio: string | null;
  location: string | null;
  phone: string | null;
  github_url: string | null;
  linkedin_url: string | null;
  website_url: string | null;
  target_job_titles: string[];
  target_salary_min: number | null;
  target_salary_max: number | null;
  remote_preference: string;
  work_authorization_status?: string | null;
  profile_version?: number;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: number;
  user_id: number;
  name: string;
  category: string;
  proficiency_level: string;
  years_experience: number;
  created_at: string;
}

export interface FullProfile {
  user_id: number;
  email: string;
  full_name: string;
  profile: Profile | null;
  skills: Skill[];
  educations: Array<{ id: number; institution: string; degree: string; field_of_study: string }>;
  experiences: Array<{ id: number; company: string; title: string; is_current: boolean }>;
  projects: Array<{ id: number; title: string; technologies: string[] }>;
  certifications: Array<{ id: number; name: string; issuer: string }>;
}

export interface EvidenceSource {
  text_snippet: string;
  page_number: number;
  confidence: number;
}

export interface ExtractedSkill {
  name: string;
  category: string;
  proficiency_level: string;
  years_experience: number;
  evidence: EvidenceSource;
  is_confirmed: boolean;
}

export interface ExtractedEducation {
  institution: string;
  degree: string;
  field_of_study: string;
  start_date?: string | null;
  end_date?: string | null;
  gpa?: string | null;
  evidence: EvidenceSource;
  is_confirmed: boolean;
}

export interface ExtractedExperience {
  company: string;
  title: string;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
  description?: string | null;
  achievements: string[];
  evidence: EvidenceSource;
  is_confirmed: boolean;
}

export interface ExtractedProject {
  title: string;
  description?: string | null;
  url?: string | null;
  repo_url?: string | null;
  technologies: string[];
  evidence: EvidenceSource;
  is_confirmed: boolean;
}

export interface ExtractedCertification {
  name: string;
  issuer: string;
  issue_date?: string | null;
  expiration_date?: string | null;
  credential_id?: string | null;
  evidence: EvidenceSource;
  is_confirmed: boolean;
}

export interface ExtractedProfileData {
  headline?: string | null;
  bio?: string | null;
  location?: string | null;
  phone?: string | null;
  skills: ExtractedSkill[];
  education: ExtractedEducation[];
  experience: ExtractedExperience[];
  projects: ExtractedProject[];
  certifications: ExtractedCertification[];
}

export interface ResumeItem {
  id: number;
  filename: string;
  size_bytes: number;
  mime_type: string;
  is_primary: boolean;
  has_parsed: boolean;
  parsing_status: string;
  created_at: string;
}

export interface ResumeExtractionResponse {
  id: number;
  resume_id: number;
  user_id: number;
  status: string;
  page_count: number;
  extracted_data: ExtractedProfileData;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('careerpilot_token');
}

export function setToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('careerpilot_token', token);
  }
}

export function removeToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('careerpilot_token');
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include', // sends HTTP-only session cookie automatically
  });

  if (!response.ok) {
    let errorDetail = 'Request failed';
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      errorDetail = response.statusText || `HTTP ${response.status}`;
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  // Authentication
  async register(data: { email: string; password: string; full_name: string }): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    setToken(res.token);
    return res;
  },

  async login(data: { email: string; password: string }): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    setToken(res.token);
    return res;
  },

  async logout(): Promise<{ message: string }> {
    try {
      const res = await request<{ message: string }>('/auth/logout', {
        method: 'POST',
      });
      removeToken();
      return res;
    } catch {
      removeToken();
      return { message: 'Logged out' };
    }
  },

  async getMe(): Promise<User> {
    return request<User>('/auth/me');
  },

  // Profile Management
  async getProfile(): Promise<FullProfile> {
    return request<FullProfile>('/profile/me');
  },

  async updateProfile(data: Partial<Profile>): Promise<Profile> {
    return request<Profile>('/profile/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async addSkill(data: { name: string; category?: string; proficiency_level?: string; years_experience?: number }): Promise<Skill> {
    return request<Skill>('/profile/skills', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deleteSkill(skillId: number): Promise<{ message: string }> {
    return request<{ message: string }>(`/profile/skills/${skillId}`, {
      method: 'DELETE',
    });
  },

  // Resume & CV Management (Phase 2)
  async uploadResume(file: File): Promise<ResumeItem> {
    const formData = new FormData();
    formData.append('file', file);
    return request<ResumeItem>('/resumes/upload', {
      method: 'POST',
      body: formData,
    });
  },

  async listResumes(): Promise<ResumeItem[]> {
    return request<ResumeItem[]>('/resumes');
  },

  async deleteResume(resumeId: number): Promise<{ message: string }> {
    return request<{ message: string }>(`/resumes/${resumeId}`, {
      method: 'DELETE',
    });
  },

  async parseResume(resumeId: number): Promise<ResumeExtractionResponse> {
    return request<ResumeExtractionResponse>(`/resumes/${resumeId}/parse`, {
      method: 'POST',
    });
  },

  async getExtraction(resumeId: number): Promise<ResumeExtractionResponse> {
    return request<ResumeExtractionResponse>(`/resumes/${resumeId}/extraction`);
  },

  async updateExtraction(resumeId: number, data: ExtractedProfileData): Promise<ResumeExtractionResponse> {
    return request<ResumeExtractionResponse>(`/resumes/${resumeId}/extraction`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async confirmExtraction(
    resumeId: number,
    payload: { data: ExtractedProfileData; override_headline: boolean; override_bio: boolean; override_location: boolean }
  ): Promise<{ message: string }> {
    return request<{ message: string }>(`/resumes/${resumeId}/extraction/confirm`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Health probe
  async checkHealth(): Promise<{ status: string; app_name: string }> {
    return request<{ status: string; app_name: string }>('/health');
  },

  // Job Discovery & Providers
  async listJobProviders(): Promise<JobProviderCapability[]> {
    return request<JobProviderCapability[]>('/jobs/providers');
  },

  async searchJobs(params: {
    query?: string;
    location?: string;
    work_mode?: string;
    provider_id?: string;
    board_token?: string;
    page?: number;
    page_size?: number;
  }): Promise<JobSearchResponse> {
    const queryParams = new URLSearchParams();
    if (params.query) queryParams.set('query', params.query);
    if (params.location) queryParams.set('location', params.location);
    if (params.work_mode) queryParams.set('work_mode', params.work_mode);
    if (params.provider_id) queryParams.set('provider_id', params.provider_id);
    if (params.board_token) queryParams.set('board_token', params.board_token);
    if (params.page) queryParams.set('page', params.page.toString());
    if (params.page_size) queryParams.set('page_size', params.page_size.toString());

    const qs = queryParams.toString();
    return request<JobSearchResponse>(`/jobs/search${qs ? `?${qs}` : ''}`);
  },

  async getJob(id: number): Promise<JobPosting> {
    return request<JobPosting>(`/jobs/${id}`);
  },

  async importJobUrl(url: string): Promise<JobPosting> {
    return request<JobPosting>('/jobs/import-url', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  },

  async listSavedJobs(): Promise<SavedJob[]> {
    return request<SavedJob[]>('/jobs/saved');
  },

  async saveJob(jobId: number, payload?: { notes?: string; status?: string }): Promise<SavedJob> {
    return request<SavedJob>(`/jobs/${jobId}/save`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  },

  async unsaveJob(jobId: number): Promise<{ message: string }> {
    return request<{ message: string }>(`/jobs/${jobId}/save`, {
      method: 'DELETE',
    });
  },

  async updateSavedJob(savedId: number, payload: { status?: string; notes?: string }): Promise<SavedJob> {
    return request<SavedJob>(`/jobs/saved/${savedId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  // Job Matching & Ranking (Phase 4)
  async listRankedMatches(params: {
    min_score?: number;
    work_mode?: string;
    location?: string;
    role?: string;
    company?: string;
    sort_by?: string;
    page?: number;
    page_size?: number;
  } = {}): Promise<RankedMatchListResponse> {
    const queryParams = new URLSearchParams();
    if (params.min_score !== undefined) queryParams.set('min_score', params.min_score.toString());
    if (params.work_mode) queryParams.set('work_mode', params.work_mode);
    if (params.location) queryParams.set('location', params.location);
    if (params.role) queryParams.set('role', params.role);
    if (params.company) queryParams.set('company', params.company);
    if (params.sort_by) queryParams.set('sort_by', params.sort_by);
    if (params.page) queryParams.set('page', params.page.toString());
    if (params.page_size) queryParams.set('page_size', params.page_size.toString());

    const qs = queryParams.toString();
    return request<RankedMatchListResponse>(`/matches${qs ? `?${qs}` : ''}`);
  },

  async getMatchDetail(jobId: number): Promise<JobMatch> {
    return request<JobMatch>(`/matches/${jobId}`);
  },

  async recalculateMatches(): Promise<{ message: string; evaluated_count: number }> {
    return request<{ message: string; evaluated_count: number }>('/matches/recalculate', {
      method: 'POST',
    });
  },

  async getScoringWeights(): Promise<ScoringWeightsResponse> {
    return request<ScoringWeightsResponse>('/matches/weights');
  },

  async updateMatchingPreferences(prefs: MatchPreferencesUpdate): Promise<{ message: string }> {
    return request<{ message: string }>('/matches/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  },

  // Document Generation & Studio (Phase 5)
  async generateDocument(payload: DocumentGenerateRequest): Promise<GeneratedDocumentResponse> {
    return request<GeneratedDocumentResponse>('/documents/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listDocuments(params: { job_id?: number; doc_type?: string } = {}): Promise<GeneratedDocumentResponse[]> {
    const qp = new URLSearchParams();
    if (params.job_id) qp.set('job_id', params.job_id.toString());
    if (params.doc_type) qp.set('doc_type', params.doc_type);
    const qs = qp.toString();
    return request<GeneratedDocumentResponse[]>(`/documents${qs ? `?${qs}` : ''}`);
  },

  async getDocument(documentId: number): Promise<GeneratedDocumentResponse> {
    return request<GeneratedDocumentResponse>(`/documents/${documentId}`);
  },

  async listDocumentVersions(documentId: number): Promise<DocumentVersionResponse[]> {
    return request<DocumentVersionResponse[]>(`/documents/${documentId}/versions`);
  },

  async updateDocumentVersion(documentId: number, payload: DocumentUpdateRequest): Promise<DocumentVersionResponse> {
    return request<DocumentVersionResponse>(`/documents/${documentId}/versions`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  async downloadDocumentBlob(documentId: number, format: 'pdf' | 'docx', versionId?: number): Promise<{ blob: Blob; filename: string }> {
    const token = getToken();
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const query = new URLSearchParams({ format });
    if (versionId) query.set('version_id', versionId.toString());

    const response = await fetch(`${API_BASE}/documents/${documentId}/download?${query.toString()}`, {
      headers,
      credentials: 'include',
    });
    if (!response.ok) {
      throw new Error(`Download failed: HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch ? filenameMatch[1] : `document.${format}`;
    return { blob, filename };
  },

  // Phase 6: Applications & LangGraph Durable Workflow
  async startApplicationWorkflow(payload: ApplicationStartRequest): Promise<ApplicationResponse> {
    return request<ApplicationResponse>('/applications/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listApplications(statusFilter?: string): Promise<ApplicationResponse[]> {
    const qp = new URLSearchParams();
    if (statusFilter && statusFilter !== 'all') qp.set('status', statusFilter);
    const qs = qp.toString();
    return request<ApplicationResponse[]>(`/applications${qs ? `?${qs}` : ''}`);
  },

  async getApplication(id: number): Promise<ApplicationResponse> {
    return request<ApplicationResponse>(`/applications/${id}`);
  },

  async approveApplication(id: number, payload: ApplicationApprovalRequest): Promise<ApplicationResponse> {
    return request<ApplicationResponse>(`/applications/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async cancelApplication(id: number, reason?: string): Promise<ApplicationResponse> {
    const qp = new URLSearchParams();
    if (reason) qp.set('reason', reason);
    const qs = qp.toString();
    return request<ApplicationResponse>(`/applications/${id}/cancel${qs ? `?${qs}` : ''}`, {
      method: 'POST',
    });
  },

  async getApplicationHistory(id: number): Promise<WorkflowHistoryItem[]> {
    return request<WorkflowHistoryItem[]>(`/applications/${id}/history`);
  },
};

export interface JobProviderCapability {
  provider_id: string;
  name: string;
  description: string;
  integration_status: string;
  supports_search: boolean;
  supports_details: boolean;
  supports_url_import: boolean;
  is_direct_api: boolean;
  link_first_only: boolean;
  rate_limit_rpm: number;
  documentation_url?: string;
  external_search_template?: string;
}

export interface JobPosting {
  id: number;
  source: string;
  source_id: string;
  canonical_url: string;
  title: string;
  company: string;
  description: string;
  location: string | null;
  work_mode: string;
  employment_type: string;
  department?: string | null;
  posted_at: string | null;
  retrieved_at: string;
  is_active: boolean;
  is_saved: boolean;
  saved_id?: number | null;
  saved_status?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedJob {
  id: number;
  user_id: number;
  job_id: number;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  job: JobPosting;
}

export interface JobSearchResponse {
  items: JobPosting[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
  warnings: string[];
  external_search_url: string | null;
}

export interface ComponentScores {
  required_skills: number;
  role_relevance: number;
  experience_seniority: number;
  education_certifications: number;
  location_work_authorization: number;
  preferred_skills: number;
}

export interface MatchedSkill {
  skill: string;
  proficiency?: string;
  years?: number;
  verified: boolean;
}

export interface JobMatch {
  id: number;
  user_id: number;
  job_id: number;
  total_score: number;
  component_scores: ComponentScores;
  matched_skills: MatchedSkill[];
  missing_skills: string[];
  missing_preferred_skills: string[];
  candidate_facts_state?: Record<string, string>;
  explanation: string;
  is_stale: boolean;
  candidate_profile_version: number;
  scoring_version: string;
  evaluated_at: string;
  job?: JobPosting;
}

export interface RankedMatchListResponse {
  items: JobMatch[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
  scoring_version: string;
}

export interface ScoringWeightsResponse {
  scoring_version: string;
  weights: Record<string, number>;
  rules: string[];
}

export interface MatchPreferencesUpdate {
  target_job_titles?: string[];
  location?: string;
  remote_preference?: string;
  work_authorization_status?: string;
}

// Phase 5: Document Studio Types
export interface ResumeExperienceItem {
  company: string;
  title: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  location?: string | null;
  bullets: string[];
}

export interface ResumeEducationItem {
  institution: string;
  degree: string;
  field_of_study: string;
  graduation_year?: string | null;
}

export interface ResumeProjectItem {
  name: string;
  description: string;
  technologies: string[];
  url?: string | null;
}

export interface ResumeCertificationItem {
  name: string;
  issuer: string;
  issue_year?: string | null;
}

export interface StructuredResume {
  full_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  target_title: string;
  target_company: string;
  professional_summary: string;
  highlighted_skills: string[];
  experience: ResumeExperienceItem[];
  projects: ResumeProjectItem[];
  education: ResumeEducationItem[];
  certifications: ResumeCertificationItem[];
}

export interface StructuredCoverLetter {
  sender_name: string;
  sender_email: string;
  sender_phone?: string | null;
  sender_location?: string | null;
  target_company: string;
  target_title: string;
  salutation: string;
  opening_paragraph: string;
  body_paragraphs: string[];
  closing_paragraph: string;
  call_to_action: string;
  sign_off: string;
}

export interface UnsupportedClaim {
  field: string;
  claim: string;
  reason: string;
  severity: string;
  line_or_context?: string | null;
}

export interface FactualValidationReport {
  is_clean: boolean;
  factual_confidence_score: number;
  total_claims_checked: number;
  verified_claims_count: number;
  unsupported_claims: UnsupportedClaim[];
  verified_facts: string[];
  warnings: string[];
}

export interface DocumentVersionResponse {
  id: number;
  document_id: number;
  version_number: number;
  structured_data: Record<string, unknown>;
  formatted_text: string;
  model_name: string;
  prompt_version: string;
  validation_report: FactualValidationReport;
  is_approved: boolean;
  change_summary: string;
  created_at: string;
}

export interface GeneratedDocumentResponse {
  id: number;
  user_id: number;
  job_id: number;
  doc_type: 'resume' | 'cover_letter';
  title: string;
  template_id: string;
  candidate_profile_version: number;
  created_at: string;
  updated_at: string;
  latest_version?: DocumentVersionResponse;
  versions_count: number;
  job_title?: string;
  job_company?: string;
}

export interface DocumentGenerateRequest {
  job_id: number;
  doc_type: 'resume' | 'cover_letter';
  template_id: string;
  custom_instructions?: string;
}

export interface DocumentUpdateRequest {
  structured_data: Record<string, unknown>;
  template_id?: string;
  change_summary: string;
  is_approved?: boolean;
}

// Phase 6: Applications & Durable Workflow Types
export interface ApplicationStartRequest {
  job_id?: number;
  job_url?: string;
  provider_id?: string;
  source_id?: string;
  template_id?: string;
  custom_instructions?: string;
  submission_mode?: 'manual_handoff' | 'automated_api';
  idempotency_key?: string;
}

export interface ApplicationApprovalRequest {
  approved: boolean;
  notes?: string;
}

export interface WorkflowHistoryItem {
  id: number;
  node_name: string;
  status: string;
  details: Record<string, unknown>;
  error_message?: string | null;
  attempt_number: number;
  created_at: string;
}

export interface ApplicationResponse {
  id: number;
  user_id: number;
  job_id?: number | null;
  resume_document_id?: number | null;
  resume_version_id?: number | null;
  cover_letter_document_id?: number | null;
  cover_letter_version_id?: number | null;
  idempotency_key: string;
  workflow_thread_id: string;
  status: string;
  approval_status: string;
  approval_notes?: string | null;
  approved_at?: string | null;
  submission_mode: string;
  application_payload: Record<string, unknown>;
  tracking_metadata: Record<string, unknown>;
  retry_count: number;
  max_retries: number;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
  job_title?: string | null;
  job_company?: string | null;
  recent_logs?: WorkflowHistoryItem[];
}


