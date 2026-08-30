import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ManageProfessionalsComponent } from './manage-professionals.component';
import { AdminService } from '../../../core/services/admin.service';
import {
  AccountStatus,
  GroupVisibility,
  ProfessionalDomain,
  SectorVisibility,
  UserRole,
} from '../../../core/constants';
import type { ProfessionalAdminView } from '../../../core/models';
import { translocoTesting } from '../../../../testing/transloco-testing';

function makeProfessional(overrides: Partial<ProfessionalAdminView> = {}): ProfessionalAdminView {
  return {
    id: 'p1',
    first_name: 'ישראל',
    last_name: 'כהן',
    email: 'cohen.law@example.com',
    phone: '0501234567',
    role: UserRole.PROFESSIONAL,
    account_status: AccountStatus.ACTIVE,
    professional_domain: ProfessionalDomain.LAWYER,
    professional_groups: [GroupVisibility.WIDOWS],
    professional_sectors: [SectorVisibility.HASIDIC],
    professional_description: 'עורך דין לענייני ירושה',
    is_active_professional: true,
    created_at: '2026-06-30T04:18:27',
    ...overrides,
  };
}

describe('ManageProfessionalsComponent', () => {
  let fixture: ComponentFixture<ManageProfessionalsComponent>;
  let component: ManageProfessionalsComponent;
  let adminServiceMock: {
    getProfessionals: ReturnType<typeof vi.fn>;
    addProfessional: ReturnType<typeof vi.fn>;
    updateProfessional: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getProfessionals: vi.fn().mockReturnValue(of([makeProfessional()])),
      addProfessional: vi.fn(),
      updateProfessional: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ManageProfessionalsComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ManageProfessionalsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  describe('loading the catalog', () => {
    it('lists the professionals returned by the backend', () => {
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
      expect(component.professionals().length).toBe(1);
    });

    it('shows an error state when the catalog cannot be loaded', () => {
      adminServiceMock.getProfessionals.mockReturnValue(throwError(() => ({})));

      component.ngOnInit();

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
    });

    it('renders the domain, the description and an active badge per row', () => {
      const text = fixture.nativeElement.textContent;

      expect(text).toContain('ישראל כהן');
      expect(text).toContain('עו"ד');
      expect(text).toContain('עורך דין לענייני ירושה');
      expect(text).toContain('פעיל');
    });

    it('marks a deactivated professional as such', () => {
      adminServiceMock.getProfessionals.mockReturnValue(
        of([makeProfessional({ is_active_professional: false })]),
      );

      component.ngOnInit();
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('מושבת');
    });
  });

  describe('audience selection', () => {
    it('replaces a narrower choice when "everyone" is picked', () => {
      const groups = component.form.controls.professional_groups;
      groups.setValue([GroupVisibility.WIDOWS, GroupVisibility.ORPHANS_MALE]);

      component.toggleAudience(groups, GroupVisibility.ALL, GroupVisibility.ALL);

      expect(groups.value).toEqual([GroupVisibility.ALL]);
    });

    it('drops "everyone" when a specific group is picked', () => {
      const groups = component.form.controls.professional_groups;
      groups.setValue([GroupVisibility.ALL]);

      component.toggleAudience(groups, GroupVisibility.WIDOWS, GroupVisibility.ALL);

      expect(groups.value).toEqual([GroupVisibility.WIDOWS]);
    });

    it('unticks an already selected option', () => {
      const sectors = component.form.controls.professional_sectors;
      sectors.setValue([SectorVisibility.HASIDIC, SectorVisibility.LITVISH]);

      component.toggleAudience(sectors, SectorVisibility.HASIDIC, SectorVisibility.ALL);

      expect(sectors.value).toEqual([SectorVisibility.LITVISH]);
    });

    it('is invalid once nothing is selected', () => {
      const sectors = component.form.controls.professional_sectors;
      sectors.setValue([SectorVisibility.HASIDIC]);

      component.toggleAudience(sectors, SectorVisibility.HASIDIC, SectorVisibility.ALL);

      expect(sectors.value).toEqual([]);
      expect(sectors.invalid).toBe(true);
    });
  });

  describe('adding a professional', () => {
    function fillAddForm(): void {
      component.openAddForm();
      component.form.patchValue({
        first_name: 'רבקה',
        last_name: 'אברמסון',
        email: 'rivka@example.com',
        phone: '0521234567',
        professional_domain: ProfessionalDomain.PSYCHOLOGIST,
        professional_groups: [GroupVisibility.WIDOWS],
        professional_sectors: [SectorVisibility.LITVISH],
        professional_description: '  מטפלת בטראומה  ',
      });
    }

    it('posts the whole profile and adds the new row to the catalog', () => {
      const created = makeProfessional({ id: 'p2', first_name: 'רבקה', last_name: 'אברמסון' });
      adminServiceMock.addProfessional.mockReturnValue(of(created));
      fillAddForm();

      component.save();

      expect(adminServiceMock.addProfessional).toHaveBeenCalledWith({
        first_name: 'רבקה',
        last_name: 'אברמסון',
        email: 'rivka@example.com',
        phone: '0521234567',
        professional_domain: ProfessionalDomain.PSYCHOLOGIST,
        professional_groups: [GroupVisibility.WIDOWS],
        professional_sectors: [SectorVisibility.LITVISH],
        professional_description: 'מטפלת בטראומה',
        is_active_professional: true,
      });
      expect(component.professionals().map((p) => p.id)).toEqual(['p2', 'p1']);
      expect(component.isFormOpen()).toBe(false);
      expect(component.successMessage()).toContain('רבקה אברמסון');
    });

    it('sends null instead of a blank description or phone', () => {
      adminServiceMock.addProfessional.mockReturnValue(of(makeProfessional({ id: 'p2' })));
      fillAddForm();
      component.form.patchValue({ phone: '', professional_description: '   ' });

      component.save();

      expect(adminServiceMock.addProfessional).toHaveBeenCalledWith(
        expect.objectContaining({ phone: null, professional_description: null }),
      );
    });

    it('does not call the backend while the form is incomplete', () => {
      component.openAddForm();

      component.save();

      expect(adminServiceMock.addProfessional).not.toHaveBeenCalled();
      expect(component.form.controls.email.touched).toBe(true);
    });

    it('surfaces the backend message when the email is already registered', () => {
      adminServiceMock.addProfessional.mockReturnValue(
        throwError(() => ({ error: { detail: 'כתובת המייל כבר רשומה במערכת' } })),
      );
      fillAddForm();

      component.save();

      expect(component.actionError()).toBe('כתובת המייל כבר רשומה במערכת');
      expect(component.isSaving()).toBe(false);
      expect(component.isFormOpen()).toBe(true);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      adminServiceMock.addProfessional.mockReturnValue(throwError(() => ({ error: null })));
      fillAddForm();

      component.save();

      expect(component.actionError()).toBe('אירעה שגיאה בשמירת איש המקצוע. נסה שוב.');
    });
  });

  describe('editing a professional', () => {
    it('loads the current values into the form and locks the identity fields', () => {
      component.openEditForm(makeProfessional());

      expect(component.form.controls.professional_domain.value).toBe(ProfessionalDomain.LAWYER);
      expect(component.form.controls.professional_groups.value).toEqual([GroupVisibility.WIDOWS]);
      expect(component.form.controls.professional_description.value).toBe('עורך דין לענייני ירושה');
      expect(component.form.controls.email.disabled).toBe(true);
      expect(component.form.controls.first_name.disabled).toBe(true);
    });

    it('sends only the editable profile fields and replaces the row', () => {
      const updated = makeProfessional({ professional_domain: ProfessionalDomain.RABBI });
      adminServiceMock.updateProfessional.mockReturnValue(of(updated));
      component.openEditForm(makeProfessional());
      component.form.patchValue({ professional_domain: ProfessionalDomain.RABBI });

      component.save();

      expect(adminServiceMock.updateProfessional).toHaveBeenCalledWith('p1', {
        professional_domain: ProfessionalDomain.RABBI,
        professional_groups: [GroupVisibility.WIDOWS],
        professional_sectors: [SectorVisibility.HASIDIC],
        professional_description: 'עורך דין לענייני ירושה',
        is_active_professional: true,
      });
      expect(component.professionals()).toEqual([updated]);
      expect(component.isFormOpen()).toBe(false);
    });

    it('re-enables the identity fields when switching back to adding', () => {
      component.openEditForm(makeProfessional());

      component.openAddForm();

      expect(component.form.controls.email.disabled).toBe(false);
      expect(component.editing()).toBeNull();
    });
  });

  describe('toggling a professional in and out of the catalog', () => {
    it('deactivates with a request that touches nothing else', () => {
      const deactivated = makeProfessional({ is_active_professional: false });
      adminServiceMock.updateProfessional.mockReturnValue(of(deactivated));

      component.toggleActive(makeProfessional());

      expect(adminServiceMock.updateProfessional).toHaveBeenCalledWith('p1', {
        is_active_professional: false,
      });
      expect(component.professionals()).toEqual([deactivated]);
      expect(component.togglingId()).toBeNull();
      expect(component.successMessage()).toContain('הושבת');
    });

    it('reactivates a deactivated professional', () => {
      const reactivated = makeProfessional({ is_active_professional: true });
      adminServiceMock.updateProfessional.mockReturnValue(of(reactivated));

      component.toggleActive(makeProfessional({ is_active_professional: false }));

      expect(adminServiceMock.updateProfessional).toHaveBeenCalledWith('p1', {
        is_active_professional: true,
      });
      expect(component.successMessage()).toContain('שוב בקטלוג');
    });

    it('locks the toggle of the row currently open in the form', () => {
      component.openEditForm(component.professionals()[0]);
      fixture.detectChanges();

      const toggle: HTMLButtonElement | null = (fixture.nativeElement as HTMLElement).querySelector(
        'button[aria-label^="השבתת"]',
      );
      expect(toggle?.disabled).toBe(true);
    });

    it('reports a failed toggle and leaves the row as it was', () => {
      adminServiceMock.updateProfessional.mockReturnValue(
        throwError(() => ({ error: { detail: 'ניתן לערוך אנשי מקצוע בלבד' } })),
      );

      component.toggleActive(makeProfessional());

      expect(component.actionError()).toBe('ניתן לערוך אנשי מקצוע בלבד');
      expect(component.professionals()[0].is_active_professional).toBe(true);
      expect(component.togglingId()).toBeNull();
    });
  });

  describe('the actions on the page', () => {
    function buttons(): HTMLButtonElement[] {
      return Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button'));
    }

    it('renders every action through the shared app-button', () => {
      // A bare <button> here would need its own copy of the .btn rules the
      // shared component already owns, and would drift the day those change.
      expect(buttons().length).toBeGreaterThan(0);
      expect(buttons().every((btn) => btn.closest('app-button') !== null)).toBe(true);
    });

    it('names each row action after the professional it acts on', () => {
      const labels = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.catalog__actions button'),
      ).map((btn) => btn.getAttribute('aria-label'));

      expect(labels).toEqual(['עריכת ישראל כהן', 'השבתת ישראל כהן']);
    });
  });
});
