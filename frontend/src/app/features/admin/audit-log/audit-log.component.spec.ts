/**
 * The audit log is still a stub: the viewer itself is a TODO, and the only
 * real UI on the page is its heading and its back link. This spec pins those
 * two through a language switch, so the screen is already migrated when
 * whoever implements the log arrives — the same treatment qa-feed got in
 * ABF-131.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';

import { AuditLogComponent } from './audit-log.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('AuditLogComponent', () => {
  let fixture: ComponentFixture<AuditLogComponent>;

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function heading(): string {
    return fixture.nativeElement.querySelector('h1').textContent.trim();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AuditLogComponent, translocoTesting()],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
  });

  it('reads in Hebrew exactly as it did before the keys went in', () => {
    expect(heading()).toBe('יומן פעולות (Audit Log)');
    expect(text()).toContain('חזרה ללוח הבקרה');
  });

  it('leaves no Hebrew on the page in English', () => {
    switchToEnglish();

    expect(heading()).toBe('Audit log');
    expect(text()).toContain('Back to the dashboard');
    expect(text()).not.toMatch(HEBREW);
  });

  /**
   * The heading is longer than the dashboard's link to this page, so the two
   * keep separate keys — sharing one would have edited the Hebrew on one of
   * them (CONTRIBUTING §6, ABF-131).
   */
  it('keeps a heading of its own, not the dashboard link to it', () => {
    const translate = TestBed.inject(TranslocoService);

    expect(translate.translate('admin.audit_log.title')).not.toBe(
      translate.translate('admin.dashboard.nav_audit_log'),
    );
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    const page = fixture.nativeElement.querySelector('div') as HTMLElement;

    expect(page.hasAttribute('dir')).toBe(false);
    expect(page.style.direction).toBe('');
  });
});
