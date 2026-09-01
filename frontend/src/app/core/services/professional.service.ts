/**
 * Professional advisory service.
 *
 * TODO list for junior developer:
 *   [x] implement getProfessionals()
 *   [x] implement askQuestion()
 *   [x] implement getMyQuestions()
 *   [x] implement getPublicQA()
 *   [x] implement getPendingQuestions() (for professional users)
 *   [x] implement answerQuestion() (for professional users)
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  LikeResponse,
  ProfessionalProfile,
  ProfessionalQuery,
  ProfessionalQueryCreate,
  PublicQA,
} from '../models';
import { ProfessionalDomain } from '../constants';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ProfessionalService {
  private readonly api = inject(ApiService);

  getProfessionals(): Observable<ProfessionalProfile[]> {
    return this.api.get<ProfessionalProfile[]>('/advice/professionals');
  }

  askQuestion(data: ProfessionalQueryCreate): Observable<ProfessionalQuery> {
    return this.api.post<ProfessionalQuery>('/advice/questions', data);
  }

  getMyQuestions(): Observable<ProfessionalQuery[]> {
    return this.api.get<ProfessionalQuery[]>('/advice/questions');
  }

  getPublicQA(domain?: ProfessionalDomain, page = 1, pageSize = 20): Observable<PublicQA[]> {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (domain) {
      params.set('domain', domain);
    }
    return this.api.get<PublicQA[]>(`/advice/questions/public?${params}`);
  }

  /** Questions still waiting for the logged-in professional. Professional role only. */
  getPendingQuestions(): Observable<ProfessionalQuery[]> {
    return this.api.get<ProfessionalQuery[]>('/advice/questions/pending');
  }

  /** Submit an answer to a pending question. Professional role only. */
  answerQuestion(queryId: string, answer: string): Observable<ProfessionalQuery> {
    return this.api.put<ProfessionalQuery>(`/advice/questions/${queryId}/answer`, { answer });
  }

  /** Toggle a like on a public professional query. */
  toggleLike(queryId: string): Observable<LikeResponse> {
    return this.api.patch<LikeResponse>(`/advice/questions/${queryId}/like`, {});
  }
}
