/**
 * Professional advisory service.
 *
 * TODO list for junior developer:
 *   [ ] implement getProfessionals()
 *   [ ] implement askQuestion()
 *   [ ] implement getMyQuestions()
 *   [ ] implement getPublicQA()
 *   [ ] implement getPendingQuestions() (for professional users)
 *   [ ] implement answerQuestion() (for professional users)
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
    /**
     * TODO:
     *   return this.api.get<ProfessionalProfile[]>('/advice/professionals');
     */
    throw new Error('getProfessionals() not yet implemented');
  }

  askQuestion(data: ProfessionalQueryCreate): Observable<ProfessionalQuery> {
    void data;
    /**
     * TODO:
     *   return this.api.post<ProfessionalQuery>('/advice/questions', data);
     */
    throw new Error('askQuestion() not yet implemented');
  }

  getMyQuestions(): Observable<ProfessionalQuery[]> {
    /**
     * TODO:
     *   return this.api.get<ProfessionalQuery[]>('/advice/questions');
     */
    throw new Error('getMyQuestions() not yet implemented');
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

  getPendingQuestions(): Observable<ProfessionalQuery[]> {
    /**
     * TODO: (professional role only)
     *   return this.api.get<ProfessionalQuery[]>('/advice/questions/pending');
     */
    throw new Error('getPendingQuestions() not yet implemented');
  }

  answerQuestion(queryId: string, answer: string): Observable<ProfessionalQuery> {
    void queryId;
    void answer;
    /**
     * TODO: (professional role only)
     *   return this.api.put<ProfessionalQuery>(`/advice/questions/${queryId}/answer`, { answer });
     */
    throw new Error('answerQuestion() not yet implemented');
  }
}
