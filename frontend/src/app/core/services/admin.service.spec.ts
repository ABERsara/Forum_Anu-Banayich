import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AdminService } from './admin.service';
import { environment } from '../../../environments/environment';
import { GroupVisibility, ProfessionalDomain, SectorVisibility } from '../constants';
import type { ForumPost, ProfessionalAdminView, UserAdminView } from '../models';

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

  it('getProfessionals GETs the professional catalog', () => {
    let result: ProfessionalAdminView[] | undefined;
    service.getProfessionals().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/professionals`);
    expect(req.request.method).toBe('GET');

    const mockCatalog = [{ id: 'p1' }] as ProfessionalAdminView[];
    req.flush(mockCatalog);
    expect(result).toEqual(mockCatalog);
  });

  it('addProfessional POSTs the new professional', () => {
    const body = {
      first_name: 'ישראל',
      last_name: 'כהן',
      email: 'cohen.law@example.com',
      phone: null,
      professional_domain: ProfessionalDomain.LAWYER,
      professional_groups: [GroupVisibility.WIDOWS],
      professional_sectors: [SectorVisibility.HASIDIC],
      professional_description: null,
      is_active_professional: true,
    };
    let result: ProfessionalAdminView | undefined;
    service.addProfessional(body).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/professionals`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);

    const created = { id: 'p1' } as ProfessionalAdminView;
    req.flush(created);
    expect(result).toEqual(created);
  });

  it('updateProfessional PUTs only the submitted fields', () => {
    let result: ProfessionalAdminView | undefined;
    service
      .updateProfessional('p1', { is_active_professional: false })
      .subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/professionals/p1`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ is_active_professional: false });

    const updated = { id: 'p1' } as ProfessionalAdminView;
    req.flush(updated);
    expect(result).toEqual(updated);
  });
});
