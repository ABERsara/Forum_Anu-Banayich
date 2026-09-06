import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ProfessionalService } from './professional.service';
import { environment } from '../../../environments/environment';
import { ProfessionalDomain, QueryStatus } from '../constants';
import type { LikeResponse, ProfessionalProfile, ProfessionalQuery, PublicQA } from '../models';

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
    like_count: 0,
    liked_by_me: false,
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

  it('getPublicQA GETs the feed with page and page_size but no domain by default', () => {
    let result: PublicQA[] | undefined;
    service.getPublicQA().subscribe((res) => (result = res));

    const req = httpMock.expectOne((r) =>
      r.url.startsWith(`${environment.apiUrl}/advice/questions/public`),
    );
    expect(req.request.method).toBe('GET');
    const query = new URLSearchParams(req.request.urlWithParams.split('?')[1]);
    expect(query.get('page')).toBe('1');
    expect(query.get('page_size')).toBe('20');
    expect(query.has('domain')).toBe(false);

    const mockList: PublicQA[] = [
      {
        id: 'q1',
        content: 'שאלה ציבורית',
        answer: 'תשובה ציבורית',
        domain: ProfessionalDomain.LAWYER,
        is_featured: false,
        answered_at: '2026-07-14T10:00:00',
        like_count: 2,
        liked_by_me: false,
        professional: null,
        asker_alias: 'אלמנה – ספרדי',
        asker: null,
      },
    ];
    req.flush(mockList);
    expect(result).toEqual(mockList);
  });

  it('getPublicQA passes domain and page through as query params', () => {
    service.getPublicQA(ProfessionalDomain.RABBI, 3, 10).subscribe();

    const req = httpMock.expectOne((r) =>
      r.url.startsWith(`${environment.apiUrl}/advice/questions/public`),
    );
    const query = new URLSearchParams(req.request.urlWithParams.split('?')[1]);
    expect(query.get('domain')).toBe(ProfessionalDomain.RABBI);
    expect(query.get('page')).toBe('3');
    expect(query.get('page_size')).toBe('10');
    req.flush([]);
  });

  it('toggleLike PATCHes the like endpoint for the given question', () => {
    let result: LikeResponse | undefined;
    service.toggleLike('q1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/advice/questions/q1/like`);
    expect(req.request.method).toBe('PATCH');

    const liked: LikeResponse = { liked: true, like_count: 1 };
    req.flush(liked);
    expect(result).toEqual(liked);
  });
});
