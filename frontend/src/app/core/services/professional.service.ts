/**
 * Professional advisory service.
 *
 * TODO list for junior developer:
 *   [x] implement getProfessionals()
 *   [x] implement askQuestion()
 *   [x] implement getMyQuestions()
 *   [ ] implement getPublicQA()
 *   [x] implement getPendingQuestions() (for professional users)
 *   [x] implement answerQuestion() (for professional users)
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
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

  getPublicQA(domain?: ProfessionalDomain, page = 1): Observable<PublicQA[]> {
    void domain;
    void page;
    /**
     * TODO:
     *   const params = domain ? `?domain=${domain}&page=${page}` : `?page=${page}`;
     *   return this.api.get<PublicQA[]>(`/advice/questions/public${params}`);
     */
    throw new Error('getPublicQA() not yet implemented');
  }

  /** Questions still waiting for the logged-in professional. Professional role only. */
  getPendingQuestions(): Observable<ProfessionalQuery[]> {
    return this.api.get<ProfessionalQuery[]>('/advice/questions/pending');
  }

  /** Submit an answer to a pending question. Professional role only. */
  answerQuestion(queryId: string, answer: string): Observable<ProfessionalQuery> {
    return this.api.put<ProfessionalQuery>(`/advice/questions/${queryId}/answer`, { answer });
  }
}
