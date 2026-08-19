import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AdminService } from './admin.service';
import { environment } from '../../../environments/environment';
import { DocumentType } from '../constants';
import type { ForumPost, RegistrationDetail, UserAdminView } from '../models';

describe('AdminService', () => {
  let service: AdminService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('getRegistration GETs one registration with its documents', () => {
    let result: RegistrationDetail | undefined;
    service.getRegistration('u1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/registrations/u1`);
    expect(req.request.method).toBe('GET');

    const mockDetail = {
      id: 'u1',
      documents: [
        {
          id: 'd1',
          doc_type: DocumentType.DEATH_CERTIFICATE,
          expires_on: null,
          uploaded_at: '2026-06-30T04:20:00',
        },
      ],
    } as RegistrationDetail;
    req.flush(mockDetail);
    expect(result).toEqual(mockDetail);
  });

  it('approveRegistration POSTs to the approve endpoint with no body', () => {
    let result: UserAdminView | undefined;
    service.approveRegistration('u1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/registrations/u1/approve`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});

    const mockUser = { id: 'u1' } as UserAdminView;
    req.flush(mockUser);
    expect(result).toEqual(mockUser);
  });

  it('rejectRegistration POSTs to the reject endpoint with the reason', () => {
    let result: UserAdminView | undefined;
    service.rejectRegistration('u1', 'מסמכים חסרים').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/registrations/u1/reject`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ reason: 'מסמכים חסרים' });

    const mockUser = { id: 'u1' } as UserAdminView;
    req.flush(mockUser);
    expect(result).toEqual(mockUser);
  });

  it('sendBroadcast POSTs to the broadcast endpoint with title and content', () => {
    let result: ForumPost | undefined;
    service
      .sendBroadcast({ title: 'הודעה חשובה', content: 'תוכן ההודעה' })
      .subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/broadcast`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    const mockPost = { id: 'p1', title: 'הודעה חשובה' } as ForumPost;
    req.flush(mockPost);
    expect(result).toEqual(mockPost);
  });

  it('getActiveUsers GETs the active users endpoint', () => {
    let result: UserAdminView[] | undefined;
    service.getActiveUsers().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/users/active`);
    expect(req.request.method).toBe('GET');

    const mockUsers = [{ id: 'u1' }] as UserAdminView[];
    req.flush(mockUsers);
    expect(result).toEqual(mockUsers);
  });

  it('suspendUser POSTs to the suspend endpoint with hours and reason', () => {
    let result: UserAdminView | undefined;
    service.suspendUser('u1', 48, 'הפרת כללי הפורום').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/users/u1/suspend`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ hours: 48, reason: 'הפרת כללי הפורום' });

    const mockUser = { id: 'u1' } as UserAdminView;
    req.flush(mockUser);
    expect(result).toEqual(mockUser);
  });
});
