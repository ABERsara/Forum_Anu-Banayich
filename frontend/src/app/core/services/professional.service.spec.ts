import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ProfessionalService } from './professional.service';
import { environment } from '../../../environments/environment';
import { ProfessionalDomain, QueryStatus } from '../constants';
import type { ProfessionalProfile, ProfessionalQuery } from '../models';

function makeQuery(overrides: Partial<ProfessionalQuery> = {}): ProfessionalQuery {
  return {
    id: 'q1',
    content: 'שאלה שממתינה לתשובה',
    answer: null,
    is_public: false,
    status: QueryStatus.OPEN,
    is_featured: false,
    domain: ProfessionalDomain.LAWYER,
    professional: null,
    asker_alias: 'אלמנה – ספרדי',
    asker: null,
    created_at: '2026-07-14T10:00:00',
    answered_at: null,
    ...overrides,
  };
}

describe('ProfessionalService', () => {
  let service: ProfessionalService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProfessionalService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('getProfessionals GETs the professionals catalog', () => {
    let result: ProfessionalProfile[] | undefined;
    service.getProfessionals().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/advice/professionals`);
    expect(req.request.method).toBe('GET');

    const mockList: ProfessionalProfile[] = [
      {
        id: 'p1',
        first_name: 'דוד',
        last_name: 'כהן',
        professional_domain: ProfessionalDomain.LAWYER,
        professional_description: 'עו"ד לדיני משפחה',
      },
    ];
    req.flush(mockList);
    expect(result).toEqual(mockList);
  });

  it('getPendingQuestions GETs the professional pending queue', () => {
    let result: ProfessionalQuery[] | undefined;
    service.getPendingQuestions().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/advice/questions/pending`);
    expect(req.request.method).toBe('GET');

    const pending = [makeQuery()];
    req.flush(pending);
    expect(result).toEqual(pending);
  });

  it('answerQuestion PUTs the answer to the question it belongs to', () => {
    let result: ProfessionalQuery | undefined;
    service.answerQuestion('q1', 'זו התשובה המקצועית').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/advice/questions/q1/answer`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ answer: 'זו התשובה המקצועית' });

    const answered = makeQuery({
      answer: 'זו התשובה המקצועית',
      status: QueryStatus.ANSWERED,
      answered_at: '2026-07-15T09:00:00',
    });
    req.flush(answered);
    expect(result).toEqual(answered);
  });
});
