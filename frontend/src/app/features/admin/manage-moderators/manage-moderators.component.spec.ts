import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ManageModeratorsComponent } from './manage-moderators.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { ModeratorAdminView } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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

/**
 * A moderator whose own details carry no Hebrew.
 *
 * A person's name and email address are theirs, not UI — out of scope for this
 * ticket and never translated. Feeding Latin details to the `HEBREW` sweeps
 * below keeps them pointed at the copy they are meant to guard.
 */
function makeLatinModerator(overrides: Partial<ModeratorAdminView> = {}): ModeratorAdminView {
  return makeModerator({ first_name: 'Sarah', last_name: 'Levy', ...overrides });
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
      imports: [ManageModeratorsComponent, translocoTesting()],
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

    it('re-reads those labels in English when the language changes', () => {
      adminServiceMock.getModerators.mockReturnValue(
        of([makeModerator({ moderator_cells: [WIDOWERS_SEPHARDIC, WIDOWS_SEPHARDIC] })]),
      );
      component.ngOnInit();
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      // Read the badges themselves: the caption above them quotes a cell as an
      // example, and that sentence is this module's own copy, not a label.
      const badges = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.badge'),
      ).map((badge) => badge.textContent?.trim());
      expect(badges).toEqual(['Widowers – Sephardic', 'Widows – Sephardic']);
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
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_moderators.appointed',
        name: 'רבקה אברמסון',
      });
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'כתובת המייל כבר רשומה במערכת' });
      expect(fixture.nativeElement.textContent).toContain('כתובת המייל כבר רשומה במערכת');
      expect(component.isSaving()).toBe(false);
      expect(component.isFormOpen()).toBe(true);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      adminServiceMock.addModerator.mockReturnValue(throwError(() => ({ error: null })));
      fillAddForm();

      component.save();
      fixture.detectChanges();

      expect(component.actionError()).toEqual({
        key: 'admin.errors.save_moderator_failed',
        text: '',
      });
      expect(fixture.nativeElement.textContent).toContain('אירעה שגיאה בשמירת הממונה. נסה שוב.');
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
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_moderators.assignments_updated',
        name: 'שרה לוי',
      });
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
      expect(component.successMessage()).toEqual({
        key: 'admin.manage_moderators.removed',
        name: 'שרה לוי',
      });
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'הממונה כבר הוסר מהמערכת' });
      expect(fixture.nativeElement.textContent).toContain('הממונה כבר הוסר מהמערכת');
      expect(component.moderators().length).toBe(1);
      expect(component.isRemoving()).toBe(false);
    });
  });

  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    function rowActionLabels(): (string | null)[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.roster__actions button'),
      ).map((button) => button.getAttribute('aria-label'));
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /**
     * Rebuilds the screen against one set of service responses. The default
     * roster carries Latin details, so the `HEBREW` sweeps below fail on our
     * own copy rather than on a moderator's name.
     */
    async function renderWith(overrides: Partial<typeof adminServiceMock> = {}): Promise<void> {
      TestBed.resetTestingModule();
      adminServiceMock = {
        getModerators: vi.fn().mockReturnValue(of([makeLatinModerator()])),
        addModerator: vi.fn(),
        updateModerator: vi.fn(),
        removeModerator: vi.fn(),
        ...overrides,
      };

      await TestBed.configureTestingModule({
        imports: [ManageModeratorsComponent, translocoTesting()],
        providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
      }).compileComponents();

      fixture = TestBed.createComponent(ManageModeratorsComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    }

    it('reads the roster in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith({ getModerators: vi.fn().mockReturnValue(of([makeModerator()])) });

      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('ניהול ממונים');
      expect(text()).toContain('הוספת ממונה');
      expect(text()).toContain('ממונה מקבל התראה על דיווחים בתאים שהוצאו לו.');
      expect(text()).toContain('התראות נשלחות אל: alerts.sara@example.com');
      expect(text()).toContain('תאים באחריותו');
      expect(text()).toContain('אלמנות – ספרדי');
      expect(text()).toContain('עריכה');
      expect(text()).toContain('הסרה');
    });

    it('leaves no Hebrew in the roster in English', async () => {
      await renderWith();

      switchToEnglish();

      expect(heading()).toBe('Manage moderators');
      expect(text()).toContain('Back to the dashboard');
      expect(text()).toContain('Add a moderator');
      expect(text()).toContain('A moderator is alerted to reports in the cells assigned to them.');
      expect(text()).toContain('Alerts are sent to: alerts.sara@example.com');
      expect(text()).toContain('The cells in their charge');
      expect(text()).toContain('Widows – Sephardic');
      expect(text()).toContain('Edit');
      expect(text()).toContain('Remove');
      expect(text()).not.toMatch(HEBREW);
    });

    it('names each row action after the moderator, in the language on screen', async () => {
      await renderWith();

      expect(rowActionLabels()).toEqual(['עריכת Sarah Levy', 'הסרת Sarah Levy']);

      switchToEnglish();

      expect(rowActionLabels()).toEqual(['Edit Sarah Levy', 'Remove Sarah Levy']);
    });

    it('translates the line a moderator with no cells gets', async () => {
      await renderWith({
        getModerators: vi.fn().mockReturnValue(of([makeLatinModerator({ moderator_cells: [] })])),
      });
      expect(text()).toContain('לא הוצאו תאים.');

      switchToEnglish();

      expect(text()).toContain('No cells are assigned.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('reads the appointment form in Hebrew exactly as it did before', async () => {
      await renderWith();
      component.openAddForm();
      fixture.detectChanges();

      expect(text()).toContain('שם פרטי');
      expect(text()).toContain('שם משפחה');
      expect(text()).toContain('דוא"ל');
      expect(text()).toContain('דוא"ל להתראות (רשות)');
      expect(text()).toContain('אם לא יוזן, ההתראות יישלחו לכתובת הדוא"ל של הממונה.');
      expect(text()).toContain('תאים שבאחריות הממונה');
      expect(text()).toContain('ביטול');
    });

    it('leaves no Hebrew in the appointment form in English', async () => {
      await renderWith();
      component.openAddForm();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('First name');
      expect(text()).toContain('Last name');
      expect(text()).toContain('Email');
      expect(text()).toContain('Alert email (optional)');
      expect(text()).toContain(
        "If it is left empty, alerts are sent to the moderator's own email address.",
      );
      expect(text()).toContain("The cells in the moderator's charge");
      expect(text()).toContain('Cancel');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The tally is a parameter, so the sentence can put it where each language does. */
    it('counts the ticked cells inside one sentence, in both languages', async () => {
      await renderWith();
      component.openAddForm();
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.toggleCell(UserType.WIDOWER, Sector.SEPHARDIC);
      fixture.detectChanges();
      const caption = (): string =>
        fixture.nativeElement.querySelector('.matrix__caption').textContent.trim();
      expect(caption()).toBe('יש לסמן כל תא שבאחריות הממונה. נבחרו 2 תאים.');

      switchToEnglish();

      expect(caption()).toBe("Tick every cell in the moderator's charge. 2 cells are selected.");
    });

    /** Every checkbox in the matrix names its own cell, for a screen reader. */
    it('names each cell checkbox in the language on screen', async () => {
      await renderWith();
      component.openAddForm();
      fixture.detectChanges();
      const firstCell = (): string | null =>
        fixture.nativeElement.querySelector('.matrix__checkbox').getAttribute('aria-label');
      expect(firstCell()).toBe('אלמנים – חסידי');

      switchToEnglish();

      expect(firstCell()).toBe('Widowers – Hasidic');
    });

    it('translates the validation messages an incomplete form raises', async () => {
      await renderWith();
      component.openAddForm();
      component.form.patchValue({ alert_email: 'not-an-address' });
      component.save();
      fixture.detectChanges();

      expect(text()).toContain('נא להזין שם פרטי (2 עד 100 תווים)');
      expect(text()).toContain('נא להזין שם משפחה (2 עד 100 תווים)');
      expect(text()).toContain('נא להזין כתובת דוא"ל תקינה');
      expect(text()).toContain('נא לבחור לפחות תא אחד');

      switchToEnglish();

      expect(text()).toContain('Please enter a first name (2 to 100 characters)');
      expect(text()).toContain('Please enter a last name (2 to 100 characters)');
      expect(text()).toContain('Please enter a valid email address');
      expect(text()).toContain('Please choose at least one cell');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The edit panel names the person; the appointment panel names the screen. */
    it('translates the panel heading in both modes', async () => {
      await renderWith();
      component.openEditForm(makeLatinModerator());
      fixture.detectChanges();
      const panelTitle = (): string =>
        fixture.nativeElement.querySelector('.panel__title').textContent.trim();
      const panelLabel = (): string | null =>
        fixture.nativeElement.querySelector('.panel').getAttribute('aria-label');
      expect(panelTitle()).toBe('עריכת Sarah Levy');
      expect(panelLabel()).toBe('עריכת ממונה');
      expect(text()).toContain('שמירת שינויים');

      switchToEnglish();

      expect(panelTitle()).toBe('Edit Sarah Levy');
      expect(panelLabel()).toBe('Edit a moderator');
      expect(text()).toContain('Save changes');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while a save is in flight', async () => {
      await renderWith({ addModerator: vi.fn().mockReturnValue(NEVER) });
      component.openAddForm();
      component.form.patchValue({
        first_name: 'Rivka',
        last_name: 'Abramson',
        email: 'rivka@example.com',
      });
      component.toggleCell(UserType.WIDOW, Sector.SEPHARDIC);
      component.save();
      fixture.detectChanges();
      expect(text()).toContain('שומר...');

      switchToEnglish();

      expect(text()).toContain('Saving...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith({ getModerators: vi.fn().mockReturnValue(of([])) });
      expect(text()).toContain('עדיין לא מונו ממונים.');

      switchToEnglish();

      expect(text()).toContain('No moderators have been appointed yet.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while the roster loads', async () => {
      await renderWith({ getModerators: vi.fn().mockReturnValue(NEVER) });
      expect(text()).toContain('טוען ממונים...');

      switchToEnglish();

      expect(text()).toContain('Loading moderators...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the load failure in the new language', async () => {
      await renderWith({ getModerators: vi.fn().mockReturnValue(throwError(() => ({}))) });
      expect(text()).toContain('אירעה שגיאה בטעינת הממונים. נסה לרענן את הדף.');

      switchToEnglish();

      expect(text()).toContain(
        'Something went wrong loading the moderators. Please refresh the page.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    it('re-renders our own removal failure in the new language', async () => {
      await renderWith({ removeModerator: vi.fn().mockReturnValue(throwError(() => ({}))) });

      component.askRemove(makeLatinModerator());
      component.confirmRemove();
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בהסרת הממונה. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong removing the moderator.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith({
        removeModerator: vi
          .fn()
          .mockReturnValue(throwError(() => ({ error: { detail: 'הממונה כבר הוסר מהמערכת' } }))),
      });

      component.askRemove(makeLatinModerator());
      component.confirmRemove();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('הממונה כבר הוסר מהמערכת');
    });

    /** The confirmation names the person, so it is a key *and* a parameter. */
    it('re-renders a confirmation that is already on screen, name and all', async () => {
      await renderWith({ removeModerator: vi.fn().mockReturnValue(of(undefined)) });

      component.askRemove(makeLatinModerator());
      component.confirmRemove();
      fixture.detectChanges();
      expect(text()).toContain('Sarah Levy הוסר מרשימת הממונים.');

      switchToEnglish();

      expect(text()).toContain('Sarah Levy was removed from the moderator roster.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the copy it hands the removal dialog, name and all', async () => {
      await renderWith();

      component.askRemove(makeLatinModerator());
      fixture.detectChanges();
      expect(text()).toContain('הסרת ממונה');
      expect(text()).toContain('Sarah Levy יוסר מרשימת הממונים ולא יקבל עוד התראות על דיווחים.');

      switchToEnglish();

      expect(text()).toContain('Remove moderator');
      expect(text()).toContain(
        'Sarah Levy will be removed from the moderator roster and will no longer receive report alerts.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    /** A moderator's name and address are content, not UI: they survive the switch. */
    it('leaves what the moderator is called alone', async () => {
      await renderWith({ getModerators: vi.fn().mockReturnValue(of([makeModerator()])) });

      switchToEnglish();

      expect(text()).toContain('שרה לוי');
      expect(text()).toContain('alerts.sara@example.com');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith();

      const page = fixture.nativeElement.querySelector('.page') as HTMLElement;
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
