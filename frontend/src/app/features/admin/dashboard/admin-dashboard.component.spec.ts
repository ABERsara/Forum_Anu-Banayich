/**
 * The dashboard had no spec before ABF-132.
 *
 * It is a screen made almost entirely of copy — a heading, a stat card and a
 * seven-link menu — so the migration is exactly what needs a guard: without
 * one, nothing catches a nav label falling back to hardcoded Hebrew, or a raw
 * `admin.dashboard.title` reaching the page.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AdminDashboardComponent } from './admin-dashboard.component';
import { AdminService } from '../../../core/services/admin.service';
import type { UserAdminView } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

/** The card only counts what comes back, so an opaque row is enough. */
const REGISTRATION = {} as UserAdminView;

describe('AdminDashboardComponent', () => {
  let fixture: ComponentFixture<AdminDashboardComponent>;
  let component: AdminDashboardComponent;

  /** Builds the screen against one service response. */
  async function renderWith(getPendingRegistrations: ReturnType<typeof vi.fn>): Promise<void> {
    TestBed.resetTestingModule();

    await TestBed.configureTestingModule({
      imports: [AdminDashboardComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: AdminService, useValue: { getPendingRegistrations } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminDashboardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function heading(): string {
    return fixture.nativeElement.querySelector('h1').textContent.trim();
  }

  function navLabels(): string[] {
    return [...fixture.nativeElement.querySelectorAll('nav a')].map((link) =>
      (link as HTMLElement).textContent!.trim(),
    );
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  it('shows the number of registrations waiting for a decision', async () => {
    await renderWith(vi.fn().mockReturnValue(of([REGISTRATION, REGISTRATION])));

    expect(component.pendingCount()).toBe(2);
    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(fixture.nativeElement.querySelector('.stats-card__value').textContent.trim()).toBe('2');
  });

  it('shows a spinner instead of the count while the request is in flight', async () => {
    await renderWith(vi.fn().mockReturnValue(NEVER));

    expect(component.isLoading()).toBe(true);
    expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.stats-card__value')).toBeNull();
  });

  it('drops the count and shows a failure when the request fails', async () => {
    await renderWith(vi.fn().mockReturnValue(throwError(() => ({}))));

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
    expect(fixture.nativeElement.querySelector('.stats-card__value')).toBeNull();
    expect(fixture.nativeElement.querySelector('app-error-display')).toBeTruthy();
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith(vi.fn().mockReturnValue(of([REGISTRATION])));

      expect(heading()).toBe('לוח בקרה – מנהל');
      expect(text()).toContain('הרשמות ממתינות לאישור');
      expect(navLabels()).toEqual([
        'הרשמות ממתינות',
        'משתמשים פעילים',
        'ניהול אנשי מקצוע',
        'ניהול ממונים',
        'יומן פעולות',
        'שידור לכלל המשתמשים',
        'דיווחים',
      ]);
    });

    it('leaves no Hebrew on the page in English', async () => {
      await renderWith(vi.fn().mockReturnValue(of([REGISTRATION])));

      switchToEnglish();

      expect(heading()).toBe('Admin dashboard');
      expect(text()).toContain('Registrations awaiting approval');
      expect(navLabels()).toEqual([
        'Pending registrations',
        'Active users',
        'Manage professionals',
        'Manage moderators',
        'Audit log',
        'Broadcast to all users',
        'Reports',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the failure copy in the new language', async () => {
      await renderWith(vi.fn().mockReturnValue(throwError(() => ({}))));
      expect(text()).toContain('שגיאה בטעינת מספר ההרשמות הממתינות');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the number of pending registrations');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the count is still loading', async () => {
      await renderWith(vi.fn().mockReturnValue(NEVER));

      switchToEnglish();

      expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The card and four of the nav links name the pages they open rather than
     * describing them, so each renders that page's own title key. If one of
     * those keys is renamed, this is what says so.
     */
    it("calls each page it links to by the page's own title", async () => {
      await renderWith(vi.fn().mockReturnValue(of([REGISTRATION])));
      const transloco = TestBed.inject(TranslocoService);

      expect(text()).toContain(transloco.translate('admin.pending_registrations.title'));
      expect(navLabels()).toContain(transloco.translate('admin.active_users.title'));
      expect(navLabels()).toContain(transloco.translate('admin.manage_professionals.title'));
      expect(navLabels()).toContain(transloco.translate('admin.manage_moderators.title'));
      expect(navLabels()).toContain(transloco.translate('admin.broadcast.title'));
    });

    /**
     * The chevron is a glyph, not copy: U+2039 is Bidi_Mirrored, so it turns
     * with the paragraph on its own. It stays out of the translation files, and
     * out of the accessibility tree.
     */
    it('keeps the chevron as a decorative glyph in either language', async () => {
      await renderWith(vi.fn().mockReturnValue(of([REGISTRATION])));
      const arrow = fixture.nativeElement.querySelector('.stats-card__arrow') as HTMLElement;

      expect(arrow.textContent!.trim()).toBe('‹');
      expect(arrow.getAttribute('aria-hidden')).toBe('true');

      switchToEnglish();

      expect(arrow.textContent!.trim()).toBe('‹');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith(vi.fn().mockReturnValue(of([REGISTRATION])));
      const host = fixture.nativeElement as HTMLElement;
      const page = host.querySelector('div') as HTMLElement;

      expect(host.hasAttribute('dir')).toBe(false);
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
