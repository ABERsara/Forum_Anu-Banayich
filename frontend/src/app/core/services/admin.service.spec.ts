import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AdminService } from './admin.service';
import { environment } from '../../../environments/environment';
import {
  AuditAction,
  AuditSortField,
  DocumentType,
  GroupVisibility,
  ProfessionalDomain,
  Sector,
  SectorVisibility,
  SortDirection,
  UserType,
} from '../constants';
import type {
  AuditLogEntry,
  AuditLogList,
  ForumPost,
  ModeratorAdminView,
  ProfessionalAdminView,
  RegistrationDetail,
  UserAdminView,
} from '../models';

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

  it('getModerators GETs the moderator roster', () => {
    let result: ModeratorAdminView[] | undefined;
    service.getModerators().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/moderators`);
    expect(req.request.method).toBe('GET');

    const mockRoster = [{ id: 'm1' }] as ModeratorAdminView[];
    req.flush(mockRoster);
    expect(result).toEqual(mockRoster);
  });

  it('addModerator POSTs the new moderator with their cells', () => {
    const body = {
      first_name: 'שרה',
      last_name: 'לוי',
      email: 'sara.levi@example.com',
      moderator_cells: [
        { group: UserType.WIDOW, sector: Sector.SEPHARDIC },
        { group: UserType.WIDOWER, sector: Sector.SEPHARDIC },
      ],
      alert_email: 'alerts.sara@example.com',
    };
    let result: ModeratorAdminView | undefined;
    service.addModerator(body).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/moderators`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);

    const created = { id: 'm1' } as ModeratorAdminView;
    req.flush(created);
    expect(result).toEqual(created);
  });

  it('updateModerator PATCHes only the submitted fields', () => {
    let result: ModeratorAdminView | undefined;
    service.updateModerator('m1', { alert_email: null }).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/moderators/m1`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ alert_email: null });

    const updated = { id: 'm1' } as ModeratorAdminView;
    req.flush(updated);
    expect(result).toEqual(updated);
  });

  it('removeModerator DELETEs the moderator', () => {
    let completed = false;
    service.removeModerator('m1').subscribe(() => (completed = true));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/moderators/m1`);
    expect(req.request.method).toBe('DELETE');

    req.flush(null);
    expect(completed).toBe(true);
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

  it('getRestrictedUsers GETs the restricted users endpoint', () => {
    let result: UserAdminView[] | undefined;
    service.getRestrictedUsers().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/users/restricted`);
    expect(req.request.method).toBe('GET');

    const mockUsers = [{ id: 'u1' }] as UserAdminView[];
    req.flush(mockUsers);
    expect(result).toEqual(mockUsers);
  });

  it('liftRestriction PATCHes the lift-restriction endpoint', () => {
    let result: UserAdminView | undefined;
    service.liftRestriction('u1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/admin/users/u1/lift-restriction`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({});

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

  // ---------------------------------------------------------------------------
  // The audit log (ABF-152)
  // ---------------------------------------------------------------------------

  describe('getAuditLog', () => {
    const PAGE: AuditLogList = {
      items: [
        {
          id: 'entry-1',
          actor_id: 'admin-1',
          action_type: AuditAction.USER_APPROVED,
          entity_type: 'User',
          entity_id: 'user-9',
          timestamp: '2026-09-01T12:00:00',
          details: null,
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 50,
    };

    it('GETs the admin audit log and returns the page', () => {
      let result: AuditLogList | undefined;

      service.getAuditLog().subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/admin/audit-log`);
      expect(req.request.method).toBe('GET');

      req.flush(PAGE);
      expect(result).toEqual(PAGE);
    });

    it('sends no query string at all when nothing is being filtered', () => {
      service.getAuditLog().subscribe();

      // Not `?` with nothing after it: an empty query string is a URL the
      // test would have to match twice over, and the server sees a different
      // request than the one the caller described.
      const req = httpMock.expectOne(`${environment.apiUrl}/admin/audit-log`);
      req.flush(PAGE);
    });

    /** The query string of the one request that was made, parsed back. */
    function requestedParams(): URLSearchParams {
      const req = httpMock.expectOne((r) =>
        r.url.startsWith(`${environment.apiUrl}/admin/audit-log`),
      );
      const query = req.request.url.split('?')[1] ?? '';
      req.flush(PAGE);
      return new URLSearchParams(query);
    }

    it('puts every filter it was given into the query string', () => {
      service
        .getAuditLog({
          actor_id: 'admin-1',
          action_type: AuditAction.POST_DELETED,
          entity_type: 'ForumPost',
          entity_id: 'post-3',
          date_from: '2026-09-01',
          date_to: '2026-09-30',
          sort: AuditSortField.TIMESTAMP,
          direction: SortDirection.ASC,
          page: 2,
          page_size: 25,
        })
        .subscribe();

      const params = requestedParams();
      expect(params.get('actor_id')).toBe('admin-1');
      expect(params.get('action_type')).toBe('post_deleted');
      expect(params.get('entity_type')).toBe('ForumPost');
      expect(params.get('entity_id')).toBe('post-3');
      expect(params.get('date_from')).toBe('2026-09-01');
      expect(params.get('date_to')).toBe('2026-09-30');
      expect(params.get('sort')).toBe('timestamp');
      expect(params.get('direction')).toBe('asc');
      expect(params.get('page')).toBe('2');
      expect(params.get('page_size')).toBe('25');
    });

    /**
     * An admin who clears a box means "stop filtering by this". Sent as
     * `actor_id=`, the server filters on the empty string and answers with
     * nothing — an empty screen that looks exactly like a log with no
     * matching rows, for a filter the reader believes they removed.
     */
    it('leaves an emptied box out of the query string entirely', () => {
      service
        .getAuditLog({ actor_id: '', entity_type: '', action_type: AuditAction.USER_LOGIN })
        .subscribe();

      const params = requestedParams();
      expect(params.has('actor_id')).toBe(false);
      expect(params.has('entity_type')).toBe(false);
      expect(params.get('action_type')).toBe('user_login');
    });

    it('encodes a value that would otherwise break the URL', () => {
      service.getAuditLog({ entity_id: 'a&b=c d' }).subscribe();

      const params = requestedParams();
      // Read back as one value, not split into several parameters by its own
      // `&` — which is what a template literal would have produced.
      expect(params.get('entity_id')).toBe('a&b=c d');
      expect([...params.keys()]).toEqual(['entity_id']);
    });
  });

  describe('getAuditLogEntry', () => {
    const ENTRY: AuditLogEntry = {
      id: 'entry-1',
      actor_id: 'admin-1',
      action_type: AuditAction.USER_SUSPENDED,
      entity_type: 'User',
      entity_id: 'user-9',
      timestamp: '2026-09-01T12:00:00',
      details: { hours: 48, changes: { title: { from: 'a', to: 'b' } } },
    };

    it('GETs the one entry by id and returns it', () => {
      let result: AuditLogEntry | undefined;

      service.getAuditLogEntry('entry-1').subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/admin/audit-log/entry-1`);
      expect(req.request.method).toBe('GET');

      req.flush(ENTRY);
      expect(result).toEqual(ENTRY);
    });

    it('hands details on as the object it arrived as', () => {
      let result: AuditLogEntry | undefined;

      service.getAuditLogEntry('entry-1').subscribe((res) => (result = res));
      httpMock.expectOne(`${environment.apiUrl}/admin/audit-log/entry-1`).flush(ENTRY);

      expect(result!.details).toEqual({ hours: 48, changes: { title: { from: 'a', to: 'b' } } });
    });

    /**
     * A path segment, not a query value: unencoded, an id with a `/` in it
     * would address a different route, and one with a `?` would turn the
     * rest of itself into a query string.
     */
    it('encodes the id so it stays one path segment', () => {
      service.getAuditLogEntry('a/b?c').subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/admin/audit-log/a%2Fb%3Fc`);
      req.flush(ENTRY);
    });
  });
});
