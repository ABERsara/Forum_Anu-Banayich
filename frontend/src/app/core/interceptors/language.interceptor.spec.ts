import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { languageInterceptor } from './language.interceptor';
import { LocaleService } from '../services/locale.service';
import { environment } from '../../../environments/environment';

describe('languageInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let localeMock: { lang: ReturnType<typeof vi.fn> };

  const API = `${environment.apiUrl}/auth/register`;

  beforeEach(() => {
    localeMock = { lang: vi.fn().mockReturnValue('he') };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([languageInterceptor])),
        provideHttpClientTesting(),
        { provide: LocaleService, useValue: localeMock },
      ],
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('sends the active UI language as Accept-Language', () => {
    http.get(API).subscribe();

    expect(httpMock.expectOne(API).request.headers.get('Accept-Language')).toBe('he');
  });

  it('follows a language switch rather than the language at startup', () => {
    localeMock.lang.mockReturnValue('en');

    http.get(API).subscribe();

    expect(httpMock.expectOne(API).request.headers.get('Accept-Language')).toBe('en');
  });

  /**
   * The regression this interceptor exists for: the browser attaches its own
   * `Accept-Language` to every XHR, so without an explicit value the server
   * would answer in the locale the *browser* was installed in. Overwriting is
   * the point — a header already on the request must not win.
   */
  it("overwrites a header already on the request instead of leaving the browser's", () => {
    http.get(API, { headers: { 'Accept-Language': 'en-US,en;q=0.9' } }).subscribe();

    expect(httpMock.expectOne(API).request.headers.get('Accept-Language')).toBe('he');
  });

  /**
   * Transloco fetches `/i18n/*.json` through HttpClient. Touching it would
   * mean injecting LocaleService while LocaleService is still constructing —
   * and another origin's response language is not ours to pick either.
   */
  it('leaves requests that are not to our API alone', () => {
    http.get('/i18n/he.json').subscribe();

    const req = httpMock.expectOne('/i18n/he.json');
    expect(req.request.headers.has('Accept-Language')).toBe(false);
    expect(localeMock.lang).not.toHaveBeenCalled();
  });
});
