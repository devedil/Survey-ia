import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const API_BASE = 'http://127.0.0.1:8000/api/v1';

export interface Profile {
  id: string;
  name: string;
}

export interface BrowserSession {
  session_id: string;
  profile_id: string;
  status: 'active' | 'stopped' | 'blocked';
  current_url: string | null;
}

export interface BrowserControl {
  control_id: string;
  question_text: string;
  control_type: string;
  options: string[];
  required: boolean;
  max_length: number | null;
}

export interface BrowserInspection {
  url: string;
  title: string;
  controls: BrowserControl[];
}

export interface AnswerProposal {
  proposal_id: string | null;
  status: 'pending' | 'approved' | 'rejected' | 'corrected';
  suggested_answer: string;
  support_status: 'supported' | 'insufficient' | 'contradictory' | 'sensitive';
  confidence: number;
  sources: Array<{ source_type: string; source_id: string; excerpt: string }>;
  needs_user_input: boolean;
  needs_review: boolean;
}

@Injectable({ providedIn: 'root' })
export class BrowserApi {
  private readonly http = inject(HttpClient);

  listProfiles(): Observable<Profile[]> {
    return this.http.get<Profile[]>(`${API_BASE}/profiles`);
  }

  createProfile(name: string): Observable<Profile> {
    return this.http.post<Profile>(`${API_BASE}/profiles`, { name });
  }

  createSession(profile_id: string): Observable<BrowserSession> {
    return this.http.post<BrowserSession>(`${API_BASE}/browser/sessions`, { profile_id });
  }

  getSession(session_id: string): Observable<BrowserSession> {
    return this.http.get<BrowserSession>(`${API_BASE}/browser/sessions/${session_id}`);
  }

  navigate(session_id: string): Observable<BrowserSession> {
    return this.http.post<BrowserSession>(
      `${API_BASE}/browser/sessions/${session_id}/navigate`,
      { url: `${API_BASE}/browser/test-site` },
    );
  }

  inspect(session_id: string): Observable<BrowserInspection> {
    return this.http.post<BrowserInspection>(
      `${API_BASE}/browser/sessions/${session_id}/inspect`,
      {},
    );
  }

  propose(session_id: string, control_id: string): Observable<AnswerProposal> {
    return this.http.post<AnswerProposal>(
      `${API_BASE}/browser/sessions/${session_id}/propose`,
      { control_id },
    );
  }

  correct(proposal_id: string, profile_id: string, correction: string): Observable<AnswerProposal> {
    return this.http.post<AnswerProposal>(
      `${API_BASE}/answers/${proposal_id}/correct`,
      { correction },
      { params: { profile_id } },
    );
  }

  approve(proposal_id: string, profile_id: string): Observable<AnswerProposal> {
    return this.http.post<AnswerProposal>(
      `${API_BASE}/answers/${proposal_id}/approve`,
      {},
      { params: { profile_id } },
    );
  }

  fillApproved(
    session_id: string,
    control_id: string,
    proposal_id: string,
  ): Observable<{ verified: boolean; status: string }> {
    return this.http.post<{ verified: boolean; status: string }>(
      `${API_BASE}/browser/sessions/${session_id}/fill-approved`,
      { control_id, proposal_id },
    );
  }

  stop(session_id: string): Observable<BrowserSession> {
    return this.http.post<BrowserSession>(
      `${API_BASE}/browser/sessions/${session_id}/stop`,
      {},
    );
  }
}
