import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AccountService } from './account.service';
import { environment } from '../../../environments/environment';
import { AccountStatus, UserRole } from '../constants';
import type { DirectMessageExportResult, UserProfile } from '../models';

const MOCK_PROFILE: UserProfile = {
  id: 'u1',
  first_name: 'שרה',
  last_name: 'לוי',
  email: 'sara@example.com',
  role: UserRole.USER,
  user_type: null,
  sector: null,
  birth_date: null,
  account_status: AccountStatus.ACTIVE,
  alert_email: 'alerts@example.com',
  created_at: '2026-01-01T00:00:00Z',
};

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

  it('updateMyProfile PUTs the body to /users/me and returns the updated profile', () => {
    let result: UserProfile | undefined;
    service
      .updateMyProfile({ alert_email: 'alerts@example.com' })
      .subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/users/me`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ alert_email: 'alerts@example.com' });

    req.flush(MOCK_PROFILE);
    expect(result).toEqual(MOCK_PROFILE);
  });

  it('updateMyProfile sends an explicit null to clear the alert email', () => {
    service.updateMyProfile({ alert_email: null }).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/users/me`);
    expect(req.request.body).toEqual({ alert_email: null });

    req.flush({ ...MOCK_PROFILE, alert_email: null });
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
