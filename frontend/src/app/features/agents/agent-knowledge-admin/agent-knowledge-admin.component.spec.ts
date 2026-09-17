/**
 * The knowledge base admin screen (ABF-124).
 *
 * What matters here is that the screen only ever works on a domain the server
 * handed it, that an edit sends exactly what changed — the server re-embeds on
 * `title` or `content`, so a form sent whole would pay for a re-index on every
 * source fix — and that a delete happens only after the confirmation. Who may
 * do any of it is the server's decision and is tested there; this screen only
 * has to show the refusal it gets back.
 */

import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AgentKnowledgeAdminComponent } from './agent-knowledge-admin.component';
import { ProfessionalDomain, UserRole } from '../../../core/constants';
import type { AgentDomain, AgentKnowledgeEntry, PaginatedResponse } from '../../../core/models';
import { AgentService } from '../../../core/services/agent.service';
import { AuthService } from '../../../core/services/auth.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const RIGHTS: AgentDomain = {
  id: 'domain-rights',
  name: 'Single-parent rights',
  description: 'Benefits for single-parent families',
  professional_domain: ProfessionalDomain.LAWYER,
};

const ESTATES: AgentDomain = {
  id: 'domain-estates',
  name: 'Estates',
  description: 'Wills and inheritance',
  professional_domain: ProfessionalDomain.LAWYER,
};

function makeEntry(overrides: Partial<AgentKnowledgeEntry> = {}): AgentKnowledgeEntry {
  return {
    id: 'e1',
    domain_id: RIGHTS.id,
    title: 'Property tax discount',
    content: 'A single-parent family is entitled to a property tax discount.',
    source_name: 'Kol Zchut',
    source_url: 'https://www.kolzchut.org.il/',
    updated_by: 'u1',
    created_at: '2026-09-15T10:00:00',
    updated_at: '2026-09-15T10:00:00',
    ...overrides,
  };
}

function pageOf(
  items: AgentKnowledgeEntry[],
  overrides: Partial<PaginatedResponse<AgentKnowledgeEntry>> = {},
): PaginatedResponse<AgentKnowledgeEntry> {
  return { items, total: items.length, page: 1, page_size: 20, ...overrides };
}

describe('AgentKnowledgeAdminComponent', () => {
  let fixture: ComponentFixture<AgentKnowledgeAdminComponent>;
  let component: AgentKnowledgeAdminComponent;
  let agentServiceMock: {
    getManageableDomains: ReturnType<typeof vi.fn>;
    listKnowledgeEntries: ReturnType<typeof vi.fn>;
    createKnowledgeEntry: ReturnType<typeof vi.fn>;
    updateKnowledgeEntry: ReturnType<typeof vi.fn>;
    deleteKnowledgeEntry: ReturnType<typeof vi.fn>;
  };

  async function render(
    overrides: Partial<typeof agentServiceMock> = {},
    { role = UserRole.PROFESSIONAL }: { role?: UserRole } = {},
  ): Promise<void> {
    TestBed.resetTestingModule();
    agentServiceMock = {
      getManageableDomains: vi.fn().mockReturnValue(of([RIGHTS])),
      listKnowledgeEntries: vi.fn().mockReturnValue(of(pageOf([makeEntry()]))),
      createKnowledgeEntry: vi.fn().mockReturnValue(of(makeEntry())),
      updateKnowledgeEntry: vi.fn().mockReturnValue(of(makeEntry())),
      deleteKnowledgeEntry: vi.fn().mockReturnValue(of(undefined)),
      ...overrides,
    };

    await TestBed.configureTestingModule({
      imports: [AgentKnowledgeAdminComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: AgentService, useValue: agentServiceMock },
        { provide: AuthService, useValue: { isAdmin: signal(role === UserRole.ADMIN) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AgentKnowledgeAdminComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function fillForm(values: {
    title?: string;
    content?: string;
    source_name?: string;
    source_url?: string;
  }): void {
    component.form.patchValue(values);
  }

  describe('choosing the domain', () => {
    it('opens the only domain it was given, with no picker', async () => {
      await render();

      expect(component.selectedDomainId()).toBe(RIGHTS.id);
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenCalledWith(RIGHTS.id, 1, 20);
      expect(root().querySelector('select')).toBeNull();
      expect(text()).toContain('Single-parent rights');
    });

    it('offers a picker when there are several, and loads the one chosen', async () => {
      await render({ getManageableDomains: vi.fn().mockReturnValue(of([RIGHTS, ESTATES])) });

      expect(root().querySelectorAll('select option').length).toBe(2);

      component.selectDomain(ESTATES.id);

      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenLastCalledWith(ESTATES.id, 1, 20);
    });

    it('closes an open form when the domain changes, so an edit cannot land elsewhere', async () => {
      await render({ getManageableDomains: vi.fn().mockReturnValue(of([RIGHTS, ESTATES])) });
      component.openEditForm(makeEntry());

      component.selectDomain(ESTATES.id);

      expect(component.isFormOpen()).toBe(false);
      expect(component.editing()).toBeNull();
    });

    /**
     * A save still in flight belongs to the domain it started on; switching
     * under it would put its confirmation over another domain's list.
     */
    it('holds the domain while a save is in flight', async () => {
      await render({
        getManageableDomains: vi.fn().mockReturnValue(of([RIGHTS, ESTATES])),
        createKnowledgeEntry: vi.fn().mockReturnValue(new Subject()),
      });
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });

      component.save();
      fixture.detectChanges();

      expect(root().querySelector<HTMLSelectElement>('#knowledge-domain')!.disabled).toBe(true);
      component.selectDomain(ESTATES.id);
      expect(component.selectedDomainId()).toBe(RIGHTS.id);
    });

    it('holds the domain while a delete is in flight', async () => {
      await render({
        getManageableDomains: vi.fn().mockReturnValue(of([RIGHTS, ESTATES])),
        deleteKnowledgeEntry: vi.fn().mockReturnValue(new Subject()),
      });
      component.requestDelete(makeEntry());

      component.confirmDelete();
      component.selectDomain(ESTATES.id);

      expect(component.selectedDomainId()).toBe(RIGHTS.id);
    });

    it('says so when no domain is assigned, and asks for no entries', async () => {
      await render({ getManageableDomains: vi.fn().mockReturnValue(of([])) });
      fixture.detectChanges();

      expect(text()).toContain('אין סוכן שבסיס הידע שלו בניהולך');
      expect(agentServiceMock.listKnowledgeEntries).not.toHaveBeenCalled();
      expect(text()).not.toContain('הוספת תוכן');
    });

    it('shows an error when the domains cannot be loaded', async () => {
      await render({ getManageableDomains: vi.fn().mockReturnValue(throwError(() => ({}))) });
      fixture.detectChanges();

      expect(component.domainsError()).toBe(true);
      expect(text()).toContain('שגיאה בטעינת הסוכנים שבניהולך');
    });
  });

  describe('the entries', () => {
    it('lists what the server returned for the domain', async () => {
      await render();
      fixture.detectChanges();

      expect(text()).toContain('Property tax discount');
      expect(text()).toContain('A single-parent family is entitled');
      const link = root().querySelector<HTMLAnchorElement>('.entries__meta a');
      expect(link?.getAttribute('href')).toBe('https://www.kolzchut.org.il/');
      expect(link?.getAttribute('rel')).toContain('noopener');
    });

    it('shows the spinner while the list is in flight', async () => {
      await render({ listKnowledgeEntries: vi.fn().mockReturnValue(NEVER) });
      fixture.detectChanges();

      expect(root().querySelector('app-loading-spinner')).not.toBeNull();
      expect(text()).not.toContain('אין עדיין תוכן');
    });

    it('tells the professional the knowledge base is empty', async () => {
      await render({ listKnowledgeEntries: vi.fn().mockReturnValue(of(pageOf([]))) });
      fixture.detectChanges();

      expect(text()).toContain('אין עדיין תוכן בבסיס הידע של הסוכן הזה.');
    });

    it('shows an error when the list cannot be loaded', async () => {
      await render({ listKnowledgeEntries: vi.fn().mockReturnValue(throwError(() => ({}))) });
      fixture.detectChanges();

      expect(text()).toContain('שגיאה בטעינת בסיס הידע');
    });

    it('hides the pager when everything fits on one page', async () => {
      await render();
      fixture.detectChanges();

      expect(root().querySelector('.pager')).toBeNull();
    });

    it('pages forward and back through a long knowledge base', async () => {
      await render({
        listKnowledgeEntries: vi.fn().mockReturnValue(of(pageOf([makeEntry()], { total: 45 }))),
      });
      fixture.detectChanges();

      expect(component.pageCount()).toBe(3);
      expect(root().querySelector('.pager')).not.toBeNull();

      agentServiceMock.listKnowledgeEntries.mockReturnValue(
        of(pageOf([makeEntry()], { total: 45, page: 2 })),
      );
      component.goToNextPage();
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenLastCalledWith(RIGHTS.id, 2, 20);
      expect(component.page()).toBe(2);

      component.goToPreviousPage();
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenLastCalledWith(RIGHTS.id, 1, 20);
    });

    /** Someone else deleted entries while this page was open. */
    it('moves to the last page that exists when the one asked for has emptied', async () => {
      await render({
        listKnowledgeEntries: vi.fn().mockReturnValue(of(pageOf([makeEntry()], { total: 45 }))),
      });
      agentServiceMock.listKnowledgeEntries.mockImplementation((_id: string, page: number) =>
        of(pageOf(page === 1 ? [makeEntry()] : [], { total: 15, page })),
      );

      component.goToNextPage();
      fixture.detectChanges();

      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenLastCalledWith(RIGHTS.id, 1, 20);
      expect(component.page()).toBe(1);
      expect(text()).not.toContain('אין עדיין תוכן');
    });

    it('does not page before the first page', async () => {
      await render();
      agentServiceMock.listKnowledgeEntries.mockClear();

      component.goToPreviousPage();

      expect(agentServiceMock.listKnowledgeEntries).not.toHaveBeenCalled();
    });
  });

  describe('adding an entry', () => {
    it('POSTs the trimmed form, with a blank source sent as none', async () => {
      await render();
      component.openAddForm();
      fillForm({ title: '  New entry  ', content: 'Some content\n', source_name: '  ' });

      component.save();

      expect(agentServiceMock.createKnowledgeEntry).toHaveBeenCalledWith(RIGHTS.id, {
        title: 'New entry',
        content: 'Some content',
        source_name: null,
        source_url: null,
      });
    });

    it('confirms, closes the form and reloads the first page', async () => {
      await render();
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });
      agentServiceMock.listKnowledgeEntries.mockClear();

      component.save();
      fixture.detectChanges();

      expect(component.isFormOpen()).toBe(false);
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenCalledWith(RIGHTS.id, 1, 20);
      expect(root().querySelector('[role="status"]')?.textContent).toContain(
        '"Property tax discount" נוסף לבסיס הידע.',
      );
    });

    it('refuses a title or content made only of spaces', async () => {
      await render();
      component.openAddForm();
      fillForm({ title: '   ', content: '   ' });

      component.save();

      expect(agentServiceMock.createKnowledgeEntry).not.toHaveBeenCalled();
      expect(component.form.controls.title.touched).toBe(true);
    });

    it('refuses a source link that is not a full web address', async () => {
      await render();
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content', source_url: 'kolzchut.org.il' });

      component.save();

      expect(agentServiceMock.createKnowledgeEntry).not.toHaveBeenCalled();
      expect(component.form.controls.source_url.invalid).toBe(true);
    });

    it('sends one POST however many times the form is submitted', async () => {
      await render({ createKnowledgeEntry: vi.fn().mockReturnValue(new Subject()) });
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });

      component.save();
      component.save();

      expect(agentServiceMock.createKnowledgeEntry).toHaveBeenCalledTimes(1);
    });

    it('refuses a title longer than the server accepts', async () => {
      await render();
      component.openAddForm();
      fillForm({ title: 'x'.repeat(257), content: 'Some content' });

      component.save();

      expect(agentServiceMock.createKnowledgeEntry).not.toHaveBeenCalled();
    });

    /** A 403 for a domain that is not theirs is a sentence the server wrote. */
    it("keeps the form open and shows the server's refusal as it came", async () => {
      await render({
        createKnowledgeEntry: vi
          .fn()
          .mockReturnValue(throwError(() => ({ status: 403, error: { detail: 'אין הרשאה' } }))),
      });
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });

      component.save();
      fixture.detectChanges();

      expect(component.isFormOpen()).toBe(true);
      expect(component.isSaving()).toBe(false);
      expect(text()).toContain('אין הרשאה');
    });

    it('falls back to our own message when the server sent none', async () => {
      await render({ createKnowledgeEntry: vi.fn().mockReturnValue(throwError(() => ({}))) });
      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });

      component.save();

      expect(component.actionError()).toEqual({ key: 'agents.errors.save_entry_failed', text: '' });
    });
  });

  describe('editing an entry', () => {
    it('fills the form with the entry', async () => {
      await render();

      component.openEditForm(makeEntry());

      expect(component.form.getRawValue()).toEqual({
        title: 'Property tax discount',
        content: 'A single-parent family is entitled to a property tax discount.',
        source_name: 'Kol Zchut',
        source_url: 'https://www.kolzchut.org.il/',
      });
    });

    /** A source fix alone must not carry title and content, which re-index. */
    it('PATCHes only the fields that changed', async () => {
      await render();
      component.openEditForm(makeEntry());
      fillForm({ source_name: 'National Insurance' });

      component.save();

      expect(agentServiceMock.updateKnowledgeEntry).toHaveBeenCalledWith(RIGHTS.id, 'e1', {
        source_name: 'National Insurance',
      });
    });

    it('sends a cleared source as null, which removes it', async () => {
      await render();
      component.openEditForm(makeEntry());
      fillForm({ source_url: '' });

      component.save();

      expect(agentServiceMock.updateKnowledgeEntry).toHaveBeenCalledWith(RIGHTS.id, 'e1', {
        source_url: null,
      });
    });

    it('sends the content when it changed', async () => {
      await render();
      component.openEditForm(makeEntry());
      fillForm({ content: 'Updated content' });

      component.save();

      expect(agentServiceMock.updateKnowledgeEntry).toHaveBeenCalledWith(RIGHTS.id, 'e1', {
        content: 'Updated content',
      });
    });

    it('sends nothing when nothing changed, and just closes the form', async () => {
      await render();
      component.openEditForm(makeEntry());

      component.save();

      expect(agentServiceMock.updateKnowledgeEntry).not.toHaveBeenCalled();
      expect(component.isFormOpen()).toBe(false);
    });

    it('confirms the update and reloads the first page, where the entry now is', async () => {
      await render();
      component.openEditForm(makeEntry());
      fillForm({ title: 'Renamed' });
      agentServiceMock.updateKnowledgeEntry.mockReturnValue(of(makeEntry({ title: 'Renamed' })));
      agentServiceMock.listKnowledgeEntries.mockClear();

      component.save();

      expect(component.successMessage()).toEqual({
        key: 'agents.knowledge.updated',
        title: 'Renamed',
      });
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenCalledWith(RIGHTS.id, 1, 20);
    });
  });

  describe('deleting an entry', () => {
    it('asks for confirmation before anything is sent', async () => {
      await render();

      component.requestDelete(makeEntry());
      fixture.detectChanges();

      expect(agentServiceMock.deleteKnowledgeEntry).not.toHaveBeenCalled();
      expect(root().querySelector('app-confirm-dialog')?.textContent).toContain(
        '"Property tax discount" יימחק',
      );
    });

    it('sends nothing when the confirmation is cancelled', async () => {
      await render();
      component.requestDelete(makeEntry());

      component.cancelDelete();
      fixture.detectChanges();

      expect(agentServiceMock.deleteKnowledgeEntry).not.toHaveBeenCalled();
      expect(root().querySelector('app-confirm-dialog')).toBeNull();
    });

    it('deletes on confirmation, confirms, and reloads the page', async () => {
      await render();
      component.requestDelete(makeEntry());
      agentServiceMock.listKnowledgeEntries.mockClear();

      component.confirmDelete();

      expect(agentServiceMock.deleteKnowledgeEntry).toHaveBeenCalledWith(RIGHTS.id, 'e1');
      expect(component.pendingDeletion()).toBeNull();
      expect(component.successMessage()).toEqual({
        key: 'agents.knowledge.deleted',
        title: 'Property tax discount',
      });
      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenCalledWith(RIGHTS.id, 1, 20);
    });

    it('steps back a page when it deleted the last entry on a later one', async () => {
      await render({
        listKnowledgeEntries: vi.fn().mockReturnValue(of(pageOf([makeEntry()], { total: 21 }))),
      });
      agentServiceMock.listKnowledgeEntries.mockReturnValue(
        of(pageOf([makeEntry()], { total: 21, page: 2 })),
      );
      component.goToNextPage();
      // After the delete, page 2 comes back empty and 20 entries remain.
      agentServiceMock.listKnowledgeEntries.mockImplementation((_id: string, page: number) =>
        of(pageOf(page === 2 ? [] : [makeEntry()], { total: 20, page })),
      );
      component.requestDelete(makeEntry());

      component.confirmDelete();

      expect(agentServiceMock.listKnowledgeEntries).toHaveBeenLastCalledWith(RIGHTS.id, 1, 20);
      expect(component.page()).toBe(1);
      expect(component.entries().length).toBe(1);
    });

    /**
     * The dialog stays open until the server answers and its confirm button is
     * not ours to disable, so a second click reaches confirmDelete() again.
     */
    it('sends one DELETE however many times the confirmation is clicked', async () => {
      const response = new Subject<void>();
      await render({ deleteKnowledgeEntry: vi.fn().mockReturnValue(response) });
      component.requestDelete(makeEntry());

      component.confirmDelete();
      component.confirmDelete();
      response.next();
      response.complete();

      expect(agentServiceMock.deleteKnowledgeEntry).toHaveBeenCalledTimes(1);
      expect(component.actionError()).toEqual({ key: '', text: '' });
    });

    it('closes the edit form of the entry it deleted', async () => {
      await render();
      component.openEditForm(makeEntry());
      component.requestDelete(makeEntry());

      component.confirmDelete();

      expect(component.isFormOpen()).toBe(false);
    });

    it('shows the failure and keeps the list as it was', async () => {
      await render({ deleteKnowledgeEntry: vi.fn().mockReturnValue(throwError(() => ({}))) });
      component.requestDelete(makeEntry());
      agentServiceMock.listKnowledgeEntries.mockClear();

      component.confirmDelete();

      expect(component.actionError()).toEqual({
        key: 'agents.errors.delete_entry_failed',
        text: '',
      });
      expect(component.pendingDeletion()).toBeNull();
      expect(agentServiceMock.listKnowledgeEntries).not.toHaveBeenCalled();
    });
  });

  describe('i18n', () => {
    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    it('reads in Hebrew as the screen was written', async () => {
      await render();
      fixture.detectChanges();

      expect(root().querySelector('h1')!.textContent!.trim()).toBe('ניהול בסיס הידע');
      expect(text()).toContain('הוספת תוכן');
      expect(text()).toContain('עריכה');
    });

    it('leaves no Hebrew in the chrome once the language is English', async () => {
      await render();
      component.openAddForm();
      fixture.detectChanges();

      switchToEnglish();

      expect(root().querySelector('h1')!.textContent!.trim()).toBe('Manage the knowledge base');
      expect(text()).toContain('Source (optional)');
      expect(text()).toContain('Lawyer');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves what the professional wrote alone in English', async () => {
      await render({
        listKnowledgeEntries: vi
          .fn()
          .mockReturnValue(of(pageOf([makeEntry({ title: 'הנחה בארנונה' })]))),
      });

      switchToEnglish();

      expect(text()).toContain('הנחה בארנונה');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await render();

      expect(root().querySelector('.knowledge-admin')!.hasAttribute('dir')).toBe(false);
    });
  });

  describe('accessibility and access', () => {
    /**
     * CONTRIBUTING §5: a status region born with its text inside is not a
     * change and is never announced, so the region has to be there first.
     */
    it('keeps the status region on screen before there is anything to announce', async () => {
      await render();
      fixture.detectChanges();

      const region = root().querySelector('[role="status"]');
      expect(region).not.toBeNull();
      expect(region!.textContent!.trim()).toBe('');

      component.openAddForm();
      fillForm({ title: 'New entry', content: 'Some content' });
      component.save();
      fixture.detectChanges();

      expect(root().querySelector('[role="status"]')).toBe(region);
      expect(region!.textContent).toContain('נוסף לבסיס הידע');
    });

    it('leads a professional back to the pending questions', async () => {
      await render();
      fixture.detectChanges();

      expect(root().querySelector('a')!.getAttribute('href')).toBe('/professional/questions');
    });

    /** An admin reaches this screen by URL, and cannot open the questions next to it. */
    it('leads an admin back to the dashboard instead', async () => {
      await render({}, { role: UserRole.ADMIN });
      fixture.detectChanges();

      const back = root().querySelector('a')!;
      expect(back.getAttribute('href')).toBe('/admin');
      expect(back.textContent).toContain('חזרה ללוח הבקרה');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await render();

      expect(root().querySelector('.knowledge-admin')!.hasAttribute('dir')).toBe(false);
    });
  });
});
