import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AccountService } from './account.service';
import { environment } from '../../../environments/environment';
import type { DirectMessageExportResult } from '../models';

const MOCK_EXPORT: DirectMessageExportResult = {
  items: [
    {
      id: 'm1',
      sender_id: 'u1',
      recipient_id: 'u2',
      content: 'שלום',
      sent_at: '2026-01-01T00:00:00Z',
      read_at: null,
    },
  ],
  total: 1,
};

describe('AccountService', () => {
  let service: AccountService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AccountService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('exportMyMessages GETs the export endpoint and returns the result', () => {
    let result: DirectMessageExportResult | undefined;
    service.exportMyMessages().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/users/me/messages/export`);
    expect(req.request.method).toBe('GET');

    req.flush(MOCK_EXPORT);
    expect(result).toEqual(MOCK_EXPORT);
  });

  it('deleteMyAccount DELETEs the current user', () => {
    let completed = false;
    service.deleteMyAccount().subscribe(() => (completed = true));

    const req = httpMock.expectOne(`${environment.apiUrl}/users/me`);
    expect(req.request.method).toBe('DELETE');

    req.flush(null, { status: 204, statusText: 'No Content' });
    expect(completed).toBe(true);
  });
});
