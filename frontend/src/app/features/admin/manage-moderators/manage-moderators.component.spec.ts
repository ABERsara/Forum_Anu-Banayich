import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ManageModeratorsComponent } from './manage-moderators.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { ModeratorAdminView } from '../../../core/models';

const WIDOWS_SEPHARDIC = { group: UserType.WIDOW, sector: Sector.SEPHARDIC };
const WIDOWERS_SEPHARDIC = { group: UserType.WIDOWER, sector: Sector.SEPHARDIC };

function makeModerator(overrides: Partial<ModeratorAdminView> = {}): ModeratorAdminView {
  return {
    id: 'm1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sara.levi@example.com',
    role: UserRole.MODERATOR,
    account_status: AccountStatus.ACTIVE,
    moderator_cells: [WIDOWS_SEPHARDIC],
    alert_email: 'alerts.sara@example.com',
    created_at: '2026-06-30T04:18:27',
    ...overrides,
  };
}

describe('ManageModeratorsComponent', () => {
  let fixture: ComponentFixture<ManageModeratorsComponent>;
  let component: ManageModeratorsComponent;
  let adminServiceMock: {
    getModerators: ReturnType<typeof vi.fn>;
    addModerator: ReturnType<typeof vi.fn>;
    updateModerator: ReturnType<typeof vi.fn>;
    removeModerator: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getModerators: vi.fn().mockReturnValue(of([makeModerator()])),
      addModerator: vi.fn(),
      updateModerator: vi.fn(),
      removeModerator: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ManageModeratorsComponent],
      providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ManageModeratorsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  describe('loading the roster', () => {
    it('lists the moderators returned by the backend', () => {
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
      expect(component.moderators().length).toBe(1);
    });

    it('shows an error state when the roster cannot be loaded', () => {
      adminServiceMock.getModerators.mockReturnValue(throwError(() => ({})));

      component.ngOnInit();

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
    });

    it('renders each assigned cell with its Hebrew label', () => {
      adminServiceMock.getModerators.mockReturnValue(
        of([makeModerator({ moderator_cells: [WIDOWERS_SEPHARDIC, WIDOWS_SEPHARDIC] })]),
      );

      component.ngOnInit();
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent;
      expect(text).toContain('שרה לוי');
      expect(text).toContain('אלמנים – ספרדי');
      expect(text).toContain('אלמנות – ספרדי');
    });

    it('shows where alerts are sent, falling back to the login address', () => {
      adminServiceMock.getModerators.mockReturnValue(of([makeModerator({ alert_email: null })]));

      component.ngOnInit();
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('sara.levi@example.com');
    });

    it('says so when a moderator holds no cells', () => {
      adminServiceMock.getModerators.mockReturnValue(of([makeModerator({ moderator_cells: [] })]));

      component.ngOnInit();
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('לא הוצאו תאים');
    });
  });

  describe('the cell matrix', () => {
    it('offers a checkbox for every group×sector cell', () => {
      component.openAddForm();
      fixture.detectChanges();

      const checkboxes = (fixture.nativeElement as HTMLElement).querySelectorAll(
        '.matrix__checkbox',
      );
      expect(checkboxes.length).toBe(component.groups.length * component.sectors.length);
    });

    it('ticks a cell and unticks it again', () => {
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      expect(component.isCellSelected(UserType.WIDOW, Sector.SEPHARDIC)).toBe(true);

      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);

      expect(component.isCellSelected(UserType.WIDOW, Sector.SEPHARDIC)).toBe(false);
      expect(component.form.controls.moderator_cells.value).toEqual([]);
    });

    it('keeps the cells in matrix order however they were ticked', () => {
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.toggleCell(UserType.WIDOWER, Sector.HASIDIC);

      expect(component.form.controls.moderator_cells.value).toEqual([
        { group: UserType.WIDOWER, sector: Sector.HASIDIC },
        WIDOWS_SEPHARDIC,
      ]);
    });

    it('is invalid while no cell is ticked', () => {
      component.openAddForm();

      expect(component.form.controls.moderator_cells.invalid).toBe(true);

      component.toggleCell(UserType.ORPHAN_FEMALE, Sector.LITVISH);

      expect(component.form.controls.moderator_cells.valid).toBe(true);
    });

    it('counts the ticked cells for the admin', () => {
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.toggleCell(UserType.WIDOWER, Sector.SEPHARDIC);

      expect(component.selectedCellCount()).toBe(2);
    });
  });

  describe('appointing a moderator', () => {
    function fillAddForm(): void {
      component.openAddForm();
      component.form.patchValue({
        first_name: 'שרה',
        last_name: 'לוי',
        email: 'sara.levi@example.com',
        alert_email: '  alerts.sara@example.com  ',
      });
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.toggleCell(UserType.WIDOWER, Sector.SEPHARDIC);
    }

    it('posts the identity and the cells, and adds the new row to the roster', () => {
      const created = makeModerator({ id: 'm2', first_name: 'רבקה', last_name: 'אברמסון' });
      adminServiceMock.addModerator.mockReturnValue(of(created));
      fillAddForm();

      component.save();

      expect(adminServiceMock.addModerator).toHaveBeenCalledWith({
        first_name: 'שרה',
        last_name: 'לוי',
        email: 'sara.levi@example.com',
        moderator_cells: [WIDOWERS_SEPHARDIC, WIDOWS_SEPHARDIC],
        alert_email: 'alerts.sara@example.com',
      });
      expect(component.moderators().map((m) => m.id)).toEqual(['m2', 'm1']);
      expect(component.isFormOpen()).toBe(false);
      expect(component.successMessage()).toContain('רבקה אברמסון');
    });

    it('sends null instead of a blank alert email', () => {
      adminServiceMock.addModerator.mockReturnValue(of(makeModerator({ id: 'm2' })));
      fillAddForm();
      component.form.patchValue({ alert_email: '   ' });

      component.save();

      expect(adminServiceMock.addModerator).toHaveBeenCalledWith(
        expect.objectContaining({ alert_email: null }),
      );
    });

    it('does not call the backend while no cell is ticked', () => {
      component.openAddForm();
      component.form.patchValue({
        first_name: 'שרה',
        last_name: 'לוי',
        email: 'sara.levi@example.com',
      });

      component.save();

      expect(adminServiceMock.addModerator).not.toHaveBeenCalled();
      expect(component.form.controls.moderator_cells.touched).toBe(true);
    });

    it('does not call the backend while the identity is incomplete', () => {
      component.openAddForm();
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);

      component.save();

      expect(adminServiceMock.addModerator).not.toHaveBeenCalled();
      expect(component.form.controls.email.touched).toBe(true);
    });

    it('surfaces the backend message when the email is already registered', () => {
      adminServiceMock.addModerator.mockReturnValue(
        throwError(() => ({ error: { detail: 'כתובת המייל כבר רשומה במערכת' } })),
      );
      fillAddForm();

      component.save();

      expect(component.actionError()).toBe('כתובת המייל כבר רשומה במערכת');
      expect(component.isSaving()).toBe(false);
      expect(component.isFormOpen()).toBe(true);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      adminServiceMock.addModerator.mockReturnValue(throwError(() => ({ error: null })));
      fillAddForm();

      component.save();

      expect(component.actionError()).toBe('אירעה שגיאה בשמירת הממונה. נסה שוב.');
    });
  });

  describe('editing a moderator', () => {
    it('loads the current assignment into the form and locks the identity fields', () => {
      component.openEditForm(makeModerator());

      expect(component.form.controls.moderator_cells.value).toEqual([WIDOWS_SEPHARDIC]);
      expect(component.form.controls.alert_email.value).toBe('alerts.sara@example.com');
      expect(component.form.controls.email.disabled).toBe(true);
      expect(component.form.controls.first_name.disabled).toBe(true);
    });

    it('sends only the assignment fields and replaces the row', () => {
      const updated = makeModerator({ moderator_cells: [WIDOWERS_SEPHARDIC] });
      adminServiceMock.updateModerator.mockReturnValue(of(updated));
      component.openEditForm(makeModerator());
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.toggleCell(UserType.WIDOWER, Sector.SEPHARDIC);

      component.save();

      expect(adminServiceMock.updateModerator).toHaveBeenCalledWith('m1', {
        moderator_cells: [WIDOWERS_SEPHARDIC],
        alert_email: 'alerts.sara@example.com',
      });
      expect(component.moderators()).toEqual([updated]);
      expect(component.isFormOpen()).toBe(false);
    });

    it('clears the alert email by sending null', () => {
      adminServiceMock.updateModerator.mockReturnValue(of(makeModerator({ alert_email: null })));
      component.openEditForm(makeModerator());
      component.form.patchValue({ alert_email: '' });

      component.save();

      expect(adminServiceMock.updateModerator).toHaveBeenCalledWith(
        'm1',
        expect.objectContaining({ alert_email: null }),
      );
    });

    it('re-enables the identity fields when switching back to appointing', () => {
      component.openEditForm(makeModerator());

      component.openAddForm();

      expect(component.form.controls.email.disabled).toBe(false);
      expect(component.editing()).toBeNull();
    });
  });

  describe('removing a moderator', () => {
    it('asks for confirmation before calling the backend', () => {
      component.askRemove(makeModerator());

      expect(component.pendingRemoval()?.id).toBe('m1');
      expect(adminServiceMock.removeModerator).not.toHaveBeenCalled();
    });

    it('drops the row once the removal is confirmed', () => {
      adminServiceMock.removeModerator.mockReturnValue(of(undefined));
      component.askRemove(makeModerator());

      component.confirmRemove();

      expect(adminServiceMock.removeModerator).toHaveBeenCalledWith('m1');
      expect(component.moderators()).toEqual([]);
      expect(component.pendingRemoval()).toBeNull();
      expect(component.isRemoving()).toBe(false);
      expect(component.successMessage()).toContain('הוסר/ה מרשימת הממונים');
    });

    it('closes the form when the row it was editing is removed', () => {
      adminServiceMock.removeModerator.mockReturnValue(of(undefined));
      component.openEditForm(makeModerator());
      component.askRemove(makeModerator());

      component.confirmRemove();

      expect(component.isFormOpen()).toBe(false);
      expect(component.editing()).toBeNull();
    });

    it('keeps the row when the removal is cancelled', () => {
      component.askRemove(makeModerator());

      component.cancelRemove();

      expect(component.pendingRemoval()).toBeNull();
      expect(component.moderators().length).toBe(1);
      expect(adminServiceMock.removeModerator).not.toHaveBeenCalled();
    });

    it('reports a failed removal and leaves the roster as it was', () => {
      adminServiceMock.removeModerator.mockReturnValue(
        throwError(() => ({ error: { detail: 'הממונה כבר הוסר מהמערכת' } })),
      );
      component.askRemove(makeModerator());

      component.confirmRemove();

      expect(component.actionError()).toBe('הממונה כבר הוסר מהמערכת');
      expect(component.moderators().length).toBe(1);
      expect(component.isRemoving()).toBe(false);
    });
  });
});
