import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
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
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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

/**
 * A professional whose own details carry no Hebrew.
 *
 * A person's name and the description they were given are theirs, not UI —
 * out of scope for this ticket and never translated. Feeding Latin details to
 * the `HEBREW` sweeps below keeps them pointed at the copy they are meant to
 * guard.
 */
function makeLatinProfessional(
  overrides: Partial<ProfessionalAdminView> = {},
): ProfessionalAdminView {
  return makeProfessional({
    first_name: 'Israel',
    last_name: 'Cohen',
    professional_description: 'An inheritance lawyer',
    ...overrides,
  });
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
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_professionals.added',
        name: 'רבקה אברמסון',
      });
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'כתובת המייל כבר רשומה במערכת' });
      expect(fixture.nativeElement.textContent).toContain('כתובת המייל כבר רשומה במערכת');
      expect(component.isSaving()).toBe(false);
      expect(component.isFormOpen()).toBe(true);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      adminServiceMock.addProfessional.mockReturnValue(throwError(() => ({ error: null })));
      fillAddForm();

      component.save();
      fixture.detectChanges();

      expect(component.actionError()).toEqual({
        key: 'admin.errors.save_professional_failed',
        text: '',
      });
      expect(fixture.nativeElement.textContent).toContain(
        'אירעה שגיאה בשמירת איש המקצוע. נסה שוב.',
      );
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
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_professionals.unlisted',
        name: 'ישראל כהן',
      });
    });

    it('reactivates a deactivated professional', () => {
      const reactivated = makeProfessional({ is_active_professional: true });
      adminServiceMock.updateProfessional.mockReturnValue(of(reactivated));

      component.toggleActive(makeProfessional({ is_active_professional: false }));

      expect(adminServiceMock.updateProfessional).toHaveBeenCalledWith('p1', {
        is_active_professional: true,
      });
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_professionals.relisted',
        name: 'ישראל כהן',
      });
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'ניתן לערוך אנשי מקצוע בלבד' });
      expect(fixture.nativeElement.textContent).toContain('ניתן לערוך אנשי מקצוע בלבד');
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

  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    /** Placeholders never reach `textContent`, so the sweeps cannot see them. */
    function placeholders(): (string | null)[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('input, textarea'),
      ).map((field) => field.getAttribute('placeholder'));
    }

    function rowActionLabels(): (string | null)[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.catalog__actions button'),
      ).map((button) => button.getAttribute('aria-label'));
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /**
     * Rebuilds the screen against one set of service responses. The default
     * catalog carries Latin details, so the `HEBREW` sweeps below fail on our
     * own copy rather than on a professional's name.
     */
    async function renderWith(overrides: Partial<typeof adminServiceMock> = {}): Promise<void> {
      TestBed.resetTestingModule();
      adminServiceMock = {
        getProfessionals: vi.fn().mockReturnValue(of([makeLatinProfessional()])),
        addProfessional: vi.fn(),
        updateProfessional: vi.fn(),
        ...overrides,
      };

      await TestBed.configureTestingModule({
        imports: [ManageProfessionalsComponent, translocoTesting()],
        providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
      }).compileComponents();

      fixture = TestBed.createComponent(ManageProfessionalsComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    }

    it('reads the catalog in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith({ getProfessionals: vi.fn().mockReturnValue(of([makeProfessional()])) });

      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('ניהול אנשי מקצוע');
      expect(text()).toContain('הוספת איש מקצוע');
      expect(text()).toContain('איש מקצוע פעיל מופיע בקטלוג הייעוץ');
      expect(text()).toContain('עו"ד');
      expect(text()).toContain('פעיל');
      expect(text()).toContain('קבוצות');
      expect(text()).toContain('מגזרים');
      expect(text()).toContain('עריכה');
      expect(text()).toContain('השבתה');
    });

    it('leaves no Hebrew in the catalog in English', async () => {
      await renderWith();

      switchToEnglish();

      expect(heading()).toBe('Manage professionals');
      expect(text()).toContain('Back to the dashboard');
      expect(text()).toContain('Add a professional');
      expect(text()).toContain('An active professional appears in the advice catalog');
      expect(text()).toContain('Lawyer');
      expect(text()).toContain('Active');
      expect(text()).toContain('Groups');
      expect(text()).toContain('Sectors');
      expect(text()).toContain('Edit');
      expect(text()).toContain('Deactivate');
      expect(text()).not.toMatch(HEBREW);
    });

    it('names each row action after the professional, in the language on screen', async () => {
      await renderWith();

      expect(rowActionLabels()).toEqual(['עריכת Israel Cohen', 'השבתת Israel Cohen']);

      switchToEnglish();

      expect(rowActionLabels()).toEqual(['Edit Israel Cohen', 'Deactivate Israel Cohen']);
    });

    it('translates the badge and the action of a deactivated professional', async () => {
      await renderWith({
        getProfessionals: vi
          .fn()
          .mockReturnValue(of([makeLatinProfessional({ is_active_professional: false })])),
      });
      expect(text()).toContain('מושבת');
      expect(text()).toContain('הפעלה');
      expect(rowActionLabels()).toEqual(['עריכת Israel Cohen', 'הפעלת Israel Cohen']);

      switchToEnglish();

      expect(text()).toContain('Deactivated');
      expect(text()).toContain('Activate');
      expect(rowActionLabels()).toEqual(['Edit Israel Cohen', 'Activate Israel Cohen']);
      expect(text()).not.toMatch(HEBREW);
    });

    it('falls back to translated copy when a professional has no field', async () => {
      await renderWith({
        getProfessionals: vi
          .fn()
          .mockReturnValue(of([makeLatinProfessional({ professional_domain: null })])),
      });
      expect(text()).toContain('ללא תחום');

      switchToEnglish();

      expect(text()).toContain('No field set');
      expect(text()).not.toMatch(HEBREW);
    });

    it('reads the add form in Hebrew exactly as it did before', async () => {
      await renderWith();
      component.openAddForm();
      fixture.detectChanges();

      expect(text()).toContain('שם פרטי');
      expect(text()).toContain('שם משפחה');
      expect(text()).toContain('דוא"ל');
      expect(text()).toContain('טלפון (רשות)');
      expect(text()).toContain('תחום');
      expect(text()).toContain('קבוצות שהוא משרת');
      expect(text()).toContain('מגזרים שהוא משרת');
      expect(text()).toContain('תיאור קצר');
      expect(text()).toContain('מופיע בקטלוג הייעוץ');
      expect(text()).toContain('הוספה לקטלוג');
      expect(text()).toContain('ביטול');
      expect(placeholders()).toContain('למשל: עורך דין המתמחה בענייני ירושה וצוואות');
    });

    it('leaves no Hebrew in the add form in English', async () => {
      await renderWith();
      component.openAddForm();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('First name');
      expect(text()).toContain('Last name');
      expect(text()).toContain('Email');
      expect(text()).toContain('Phone (optional)');
      expect(text()).toContain('Field');
      expect(text()).toContain('The groups they serve');
      expect(text()).toContain('The sectors they serve');
      expect(text()).toContain('Short description');
      expect(text()).toContain('Listed in the advice catalog');
      expect(text()).toContain('Add to the catalog');
      expect(text()).toContain('Cancel');
      expect(placeholders()).toContain(
        'For example: a lawyer specializing in inheritance and wills',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    /** Read off the messages the form actually renders, not the static labels. */
    it('translates the validation messages an incomplete form raises', async () => {
      await renderWith();
      component.openAddForm();
      component.form.patchValue({ phone: '123' });
      component.toggleAudience(
        component.form.controls.professional_groups,
        GroupVisibility.ALL,
        GroupVisibility.ALL,
      );
      component.toggleAudience(
        component.form.controls.professional_sectors,
        SectorVisibility.ALL,
        SectorVisibility.ALL,
      );
      component.save();
      fixture.detectChanges();

      expect(text()).toContain('נא להזין שם פרטי (2 עד 100 תווים)');
      expect(text()).toContain('נא להזין שם משפחה (2 עד 100 תווים)');
      expect(text()).toContain('נא להזין כתובת דוא"ל תקינה');
      expect(text()).toContain('מספר טלפון צריך להכיל 9 עד 15 תווים');
      expect(text()).toContain('נא לבחור לפחות קבוצה אחת');
      expect(text()).toContain('נא לבחור לפחות מגזר אחד');

      switchToEnglish();

      expect(text()).toContain('Please enter a first name (2 to 100 characters)');
      expect(text()).toContain('Please enter a last name (2 to 100 characters)');
      expect(text()).toContain('Please enter a valid email address');
      expect(text()).toContain('A phone number must be 9 to 15 characters long');
      expect(text()).toContain('Please choose at least one group');
      expect(text()).toContain('Please choose at least one sector');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The edit panel names the person; the add panel names the screen. */
    it('translates the panel heading in both modes', async () => {
      await renderWith();
      component.openEditForm(makeLatinProfessional());
      fixture.detectChanges();
      const panelTitle = (): string =>
        fixture.nativeElement.querySelector('.panel__title').textContent.trim();
      const panelLabel = (): string | null =>
        fixture.nativeElement.querySelector('.panel').getAttribute('aria-label');
      expect(panelTitle()).toBe('עריכת Israel Cohen');
      expect(panelLabel()).toBe('עריכת איש מקצוע');
      expect(text()).toContain('שמירת שינויים');

      switchToEnglish();

      expect(panelTitle()).toBe('Edit Israel Cohen');
      expect(panelLabel()).toBe('Edit a professional');
      expect(text()).toContain('Save changes');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while a save is in flight', async () => {
      await renderWith({ addProfessional: vi.fn().mockReturnValue(NEVER) });
      component.openAddForm();
      component.form.patchValue({
        first_name: 'Rivka',
        last_name: 'Abramson',
        email: 'rivka@example.com',
      });
      component.save();
      fixture.detectChanges();
      expect(text()).toContain('שומר...');

      switchToEnglish();

      expect(text()).toContain('Saving...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith({ getProfessionals: vi.fn().mockReturnValue(of([])) });
      expect(text()).toContain('עדיין אין אנשי מקצוע בקטלוג.');

      switchToEnglish();

      expect(text()).toContain('There are no professionals in the catalog yet.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while the catalog loads', async () => {
      await renderWith({ getProfessionals: vi.fn().mockReturnValue(NEVER) });
      expect(text()).toContain('טוען אנשי מקצוע...');

      switchToEnglish();

      expect(text()).toContain('Loading professionals...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the load failure in the new language', async () => {
      await renderWith({ getProfessionals: vi.fn().mockReturnValue(throwError(() => ({}))) });
      expect(text()).toContain('אירעה שגיאה בטעינת אנשי המקצוע. נסה לרענן את הדף.');

      switchToEnglish();

      expect(text()).toContain(
        'Something went wrong loading the professionals. Please refresh the page.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    it('re-renders our own toggle failure in the new language', async () => {
      await renderWith({ updateProfessional: vi.fn().mockReturnValue(throwError(() => ({}))) });

      component.toggleActive(makeLatinProfessional());
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בעדכון הסטטוס. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong updating the status.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith({
        updateProfessional: vi
          .fn()
          .mockReturnValue(throwError(() => ({ error: { detail: 'ניתן לערוך אנשי מקצוע בלבד' } }))),
      });

      component.toggleActive(makeLatinProfessional());
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('ניתן לערוך אנשי מקצוע בלבד');
    });

    /** The confirmation names the person, so it is a key *and* a parameter. */
    it('re-renders a confirmation that is already on screen, name and all', async () => {
      const deactivated = makeLatinProfessional({ is_active_professional: false });
      await renderWith({ updateProfessional: vi.fn().mockReturnValue(of(deactivated)) });

      component.toggleActive(makeLatinProfessional());
      fixture.detectChanges();
      expect(text()).toContain('Israel Cohen הושבת ואינו מופיע בקטלוג.');

      switchToEnglish();

      expect(text()).toContain(
        'Israel Cohen was deactivated and no longer appears in the catalog.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    /** A professional's name and description are content, not UI. */
    it('leaves what the professional is called alone', async () => {
      await renderWith({ getProfessionals: vi.fn().mockReturnValue(of([makeProfessional()])) });

      switchToEnglish();

      expect(text()).toContain('ישראל כהן');
      expect(text()).toContain('עורך דין לענייני ירושה');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith();

      const page = fixture.nativeElement.querySelector('.page') as HTMLElement;
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
