import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorUserCardComponent } from './user-card.component';
import { ReportService } from '../../../core/services/report.service';
import { AccountStatus, Sector, UserType } from '../../../core/constants';
import type { UserModerationCard } from '../../../core/models';

function makeCard(overrides: Partial<UserModerationCard> = {}): UserModerationCard {
  return {
    id: 'user-2',
    first_name: 'רחל',
    last_name: 'כהן',
    user_type: UserType.WIDOW,
    sector: Sector.HASIDIC,
    account_status: AccountStatus.ACTIVE,
    reports_against_total: 4,
    reports_against_valid: 3,
    reports_against_invalid: 1,
    reports_filed_total: 2,
    false_reports_filed: 1,
    is_suspended: false,
    suspended_until: null,
    ...overrides,
  };
}

describe('ModeratorUserCardComponent', () => {
  let fixture: ComponentFixture<ModeratorUserCardComponent>;
  let component: ModeratorUserCardComponent;
  let reportServiceMock: {
    getUserCard: ReturnType<typeof vi.fn>;
    suspendUser: ReturnType<typeof vi.fn>;
  };

  /** Creates the component with the :userId route parameter already bound. */
  function render(userId = 'user-2'): void {
    fixture = TestBed.createComponent(ModeratorUserCardComponent);
    fixture.componentRef.setInput('userId', userId);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  beforeEach(async () => {
    reportServiceMock = {
      getUserCard: vi.fn().mockReturnValue(of(makeCard())),
      suspendUser: vi.fn().mockReturnValue(
        of(
          makeCard({
            account_status: AccountStatus.SUSPENDED,
            is_suspended: true,
            suspended_until: '2026-08-20T12:00:00',
          }),
        ),
      ),
    };

    await TestBed.configureTestingModule({
      imports: [ModeratorUserCardComponent],
      providers: [{ provide: ReportService, useValue: reportServiceMock }, provideRouter([])],
    }).compileComponents();

    render();
  });

  describe('the card', () => {
    it('loads the card of the user named in the route', () => {
      expect(reportServiceMock.getUserCard).toHaveBeenCalledWith('user-2');
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
    });

    it('shows the moderation history the decision rests on', () => {
      const text: string = fixture.nativeElement.textContent;

      expect(text).toContain('רחל כהן');
      expect(text).toContain('אלמנה');
      expect(text).toContain('חסידי');
      expect(text).toContain('פעיל');
      expect(component.cellLabel()).toBe('אלמנה · חסידי');
    });

    it('shows every count the card is made of', () => {
      const counts = Array.from(
        fixture.nativeElement.querySelectorAll('.stats dd') as NodeListOf<HTMLElement>,
      ).map((dd) => dd.textContent?.trim());

      expect(counts).toEqual(['4', '3', '1', '2', '1']);
    });

    it('says the account is not suspended when it is not', () => {
      expect(fixture.nativeElement.textContent).toContain('החשבון אינו מושעה כרגע');
    });

    it('shows until when a suspended account is suspended', () => {
      reportServiceMock.getUserCard.mockReturnValue(
        of(
          makeCard({
            account_status: AccountStatus.SUSPENDED,
            is_suspended: true,
            suspended_until: '2026-08-20T12:00:00',
          }),
        ),
      );

      render();

      expect(fixture.nativeElement.textContent).toContain('20/08/2026');
      expect(fixture.nativeElement.textContent).toContain('מושעה');
    });

    it('falls back to a dash for a user placed in no cell yet', () => {
      reportServiceMock.getUserCard.mockReturnValue(
        of(makeCard({ user_type: null, sector: null })),
      );

      render();

      expect(component.cellLabel()).toBe('—');
    });

    it('sets hasError when the card fails to load', () => {
      reportServiceMock.getUserCard.mockReturnValue(throwError(() => ({})));

      render();

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
    });
  });

  describe('suspending the user', () => {
    it('does not call the service until the dialog is confirmed', () => {
      component.openSuspendDialog();
      fixture.detectChanges();

      expect(reportServiceMock.suspendUser).not.toHaveBeenCalled();
      expect(fixture.nativeElement.querySelector('app-suspend-dialog')).toBeTruthy();
    });

    it('sends the duration and the reason the moderator wrote', () => {
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });

      expect(reportServiceMock.suspendUser).toHaveBeenCalledWith(
        'user-2',
        48,
        'התנהגות פוגענית חוזרת',
      );
    });

    it('shows the suspension the moment it is applied, without refetching', () => {
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.card()?.is_suspended).toBe(true);
      expect(component.isSuspendDialogOpen()).toBe(false);
      expect(reportServiceMock.getUserCard).toHaveBeenCalledTimes(1);
      expect(fixture.nativeElement.textContent).toContain('20/08/2026');
    });

    it('offers the button only while the account is active', () => {
      expect(component.canSuspend()).toBe(true);

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.canSuspend()).toBe(false);
      expect(fixture.nativeElement.querySelector('app-button')).toBeNull();
    });

    it('closes the dialog without suspending on cancel', () => {
      component.openSuspendDialog();

      component.cancelSuspend();

      expect(component.isSuspendDialogOpen()).toBe(false);
      expect(reportServiceMock.suspendUser).not.toHaveBeenCalled();
    });

    it('shows the backend message when the suspension is refused', () => {
      reportServiceMock.suspendUser.mockReturnValue(
        throwError(() => ({ error: { detail: 'ניתן להשעות רק משתמש פעיל' } })),
      );
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });

      expect(component.actionError()).toBe('ניתן להשעות רק משתמש פעיל');
      expect(component.card()?.is_suspended).toBe(false);
      expect(component.isSuspending()).toBe(false);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      reportServiceMock.suspendUser.mockReturnValue(throwError(() => ({ error: null })));
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });

      expect(component.actionError()).toBe('אירעה שגיאה בהשעיית המשתמש. נסי שוב.');
    });
  });
});
