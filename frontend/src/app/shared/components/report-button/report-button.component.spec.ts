import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ReportButtonComponent } from './report-button.component';
import { ReportReason, ReportTargetType } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('ReportButtonComponent', () => {
  let fixture: ComponentFixture<ReportButtonComponent>;
  let component: ReportButtonComponent;
  let reportServiceMock: { fileReport: ReturnType<typeof vi.fn> };

  function setup(contentType = ReportTargetType.FORUM_POST, contentId = 'post-1'): void {
    reportServiceMock = {
      fileReport: vi.fn().mockReturnValue(of({ id: 'report-1' })),
    };

    TestBed.configureTestingModule({
      imports: [ReportButtonComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ReportButtonComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('contentType', contentType);
    fixture.componentRef.setInput('contentId', contentId);
    // Attached to the document so focus() actually moves — jsdom does not move
    // focus into a detached tree, and half of this dialog's job is focus.
    document.body.appendChild(fixture.nativeElement);
    fixture.detectChanges();
  }

  afterEach(() => {
    fixture?.nativeElement.remove();
  });

  function openButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('.report-button button') as HTMLButtonElement;
  }

  function open(): void {
    openButton().click();
    fixture.detectChanges();
  }

  function dialog(): HTMLElement {
    return fixture.nativeElement.querySelector('.dialog') as HTMLElement;
  }

  function reasonSelect(): HTMLSelectElement {
    return fixture.nativeElement.querySelector('select') as HTMLSelectElement;
  }

  function setReason(value: string): void {
    const select = reasonSelect();
    select.value = value;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function setDescription(value: string): void {
    const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    textarea.value = value;
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function submitButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('.btn--primary') as HTMLButtonElement;
  }

  function cancelButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('.btn--cancel') as HTMLButtonElement;
  }

  function dialogText(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('shows the report button and no dialog initially', () => {
    setup();

    expect(openButton()).toBeTruthy();
    expect(dialog()).toBeFalsy();
  });

  it('opens the dialog on click', () => {
    setup();

    open();

    expect(dialog()).toBeTruthy();
  });

  it('closes the dialog on cancel without submitting', () => {
    setup();
    open();

    cancelButton().click();
    fixture.detectChanges();

    expect(dialog()).toBeFalsy();
    expect(reportServiceMock.fileReport).not.toHaveBeenCalled();
  });

  /**
   * §7.1 says the user *chooses* a reason. The dialog used to open on
   * "harassment", so anyone who just pressed send filed the gravest reason
   * available without ever having picked it.
   */
  describe('a reason has to be chosen', () => {
    it('opens with nothing selected', () => {
      setup();

      open();

      expect(component.reason()).toBeNull();
      expect(reasonSelect().value).toBe('');
    });

    it('keeps submit disabled until a reason is picked', () => {
      setup();
      open();

      expect(submitButton().disabled).toBe(true);

      setReason(ReportReason.SPAM);

      expect(submitButton().disabled).toBe(false);
    });

    it('files nothing if submit is invoked with no reason', () => {
      setup();
      open();

      component.onSubmit();

      expect(reportServiceMock.fileReport).not.toHaveBeenCalled();
      expect(dialog()).toBeTruthy();
    });

    it('says why submit is unavailable, for a reader who cannot see it', () => {
      setup();
      open();

      expect(dialogText()).toContain('יש לבחור סיבה כדי לשלוח דיווח.');

      setReason(ReportReason.SPAM);

      expect(dialogText()).not.toContain('יש לבחור סיבה כדי לשלוח דיווח.');
    });

    it('forgets the previous choice when reopened', () => {
      setup();
      open();
      setReason(ReportReason.SPAM);
      cancelButton().click();
      fixture.detectChanges();

      open();

      expect(component.reason()).toBeNull();
    });
  });

  /**
   * The acceptance criterion "the notice is shown before confirming" — and
   * the reason it is derived from the content type rather than passed in: a
   * screen cannot add a reporting control and forget the warning.
   */
  describe('disclosure', () => {
    it('warns that a private message will be revealed to the moderator', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');

      open();

      const disclosure = dialog().querySelector('.dialog__disclosure') as HTMLElement;
      expect(disclosure.textContent).toContain('יחשוף את ההודעה הזו בלבד למבקר האחראי');
    });

    it('is part of the dialog description, so it is read out on opening', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');

      open();

      const describedBy = dialog().getAttribute('aria-describedby');
      expect(describedBy).toBe('report-message-1-disclosure');
      expect(dialog().querySelector(`#${describedBy}`)).toBeTruthy();
    });

    it('is shown before the confirm button, not after it', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');

      open();

      const children = Array.from(dialog().children);
      const disclosureIndex = children.findIndex((el) =>
        el.classList.contains('dialog__disclosure'),
      );
      const actionsIndex = children.findIndex((el) => el.classList.contains('dialog__actions'));
      expect(disclosureIndex).toBeGreaterThan(-1);
      expect(disclosureIndex).toBeLessThan(actionsIndex);
    });

    /** A forum post is already visible to a whole cell — nothing to disclose. */
    it('says nothing extra about a forum post', () => {
      setup(ReportTargetType.FORUM_POST);

      open();

      expect(dialog().querySelector('.dialog__disclosure')).toBeFalsy();
      expect(dialog().getAttribute('aria-describedby')).toBeNull();
    });
  });

  describe('accessibility', () => {
    it('is a labelled modal dialog', () => {
      setup();

      open();

      expect(dialog().getAttribute('role')).toBe('dialog');
      expect(dialog().getAttribute('aria-modal')).toBe('true');
      const labelledBy = dialog().getAttribute('aria-labelledby');
      expect(dialog().querySelector(`#${labelledBy}`)?.textContent).toContain('דיווח על תוכן');
    });

    it('moves focus into the dialog when it opens', async () => {
      setup();

      open();
      await Promise.resolve();

      expect(document.activeElement).toBe(reasonSelect());
    });

    it('gives focus back to the button that opened it', () => {
      setup();
      const trigger = openButton();
      open();

      cancelButton().click();
      fixture.detectChanges();

      expect(document.activeElement).toBe(trigger);
    });

    it('closes on Escape', () => {
      setup();
      open();

      dialog().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      fixture.detectChanges();

      expect(dialog()).toBeFalsy();
      expect(reportServiceMock.fileReport).not.toHaveBeenCalled();
    });

    it('wraps Tab from the last control back to the first', () => {
      setup();
      open();
      setReason(ReportReason.SPAM);
      submitButton().focus();

      const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
      dialog().dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(reasonSelect());
    });

    it('labels its fields with ids derived from the content', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-42');

      open();

      expect(reasonSelect().id).toBe('report-message-42-reason');
      const label = dialog().querySelector('label[for="report-message-42-reason"]');
      expect(label).toBeTruthy();
    });

    /**
     * A conversation renders one of these per message. Without a per-message
     * accessible name they are fifty buttons called "report".
     */
    it('takes an accessible name for the trigger when given one', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
      fixture.componentRef.setInput('triggerLabel', 'דיווח על ההודעה מאת שרה בשעה 10:00');
      fixture.detectChanges();

      expect(openButton().getAttribute('aria-label')).toBe('דיווח על ההודעה מאת שרה בשעה 10:00');
    });

    it('leaves the visible label as the name when none is given', () => {
      setup();

      expect(openButton().getAttribute('aria-label')).toBeNull();
      expect(openButton().textContent?.trim()).toBe('דיווח');
    });
  });

  it('submits with the selected reason, trimmed description, and given content target', () => {
    setup();
    open();
    setReason(ReportReason.SPAM);
    setDescription('  יש כאן ספאם  ');

    submitButton().click();

    expect(reportServiceMock.fileReport).toHaveBeenCalledWith({
      target_type: ReportTargetType.FORUM_POST,
      target_id: 'post-1',
      reason: ReportReason.SPAM,
      description: 'יש כאן ספאם',
    });
  });

  it('sends undefined description when left blank', () => {
    setup();
    open();
    setReason(ReportReason.HARASSMENT);

    submitButton().click();

    expect(reportServiceMock.fileReport).toHaveBeenCalledWith(
      expect.objectContaining({ description: undefined }),
    );
  });

  it('reports a private message against the direct-message target type', () => {
    setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
    open();
    setReason(ReportReason.OFFENSIVE);

    submitButton().click();

    expect(reportServiceMock.fileReport).toHaveBeenCalledWith(
      expect.objectContaining({
        target_type: ReportTargetType.DIRECT_MESSAGE,
        target_id: 'message-1',
        reason: ReportReason.OFFENSIVE,
      }),
    );
  });

  it('hides the dialog and shows a confirmation on success', () => {
    setup();
    open();
    setReason(ReportReason.HARASSMENT);

    submitButton().click();
    fixture.detectChanges();

    expect(dialog()).toBeFalsy();
    expect(dialogText()).toContain('הדיווח נשלח, תודה.');
  });

  it('tells the host screen once the report is stored', () => {
    setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
    const seen: number[] = [];
    component.reported.subscribe(() => seen.push(1));
    open();
    setReason(ReportReason.SPAM);

    submitButton().click();
    fixture.detectChanges();

    expect(seen).toHaveLength(1);
  });

  it('does not announce a report the server refused', () => {
    setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
    reportServiceMock.fileReport.mockReturnValue(throwError(() => ({ status: 409 })));
    const seen: number[] = [];
    component.reported.subscribe(() => seen.push(1));
    open();
    setReason(ReportReason.SPAM);

    submitButton().click();
    fixture.detectChanges();

    expect(seen).toHaveLength(0);
  });

  /**
   * The mark has to survive a reload, so the screen states it from what the
   * server said rather than only from what happened in this session.
   */
  it('shows the confirmation instead of the button when already reported', () => {
    setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
    fixture.componentRef.setInput('alreadyReported', true);
    fixture.detectChanges();

    expect(openButton()).toBeFalsy();
    expect(dialogText()).toContain('הדיווח נשלח, תודה.');
  });

  function failWith(status: number): void {
    reportServiceMock.fileReport.mockReturnValue(throwError(() => ({ status })));
    open();
    setReason(ReportReason.HARASSMENT);
    submitButton().click();
    fixture.detectChanges();
  }

  it('shows a specific message for a duplicate report (409)', () => {
    setup();

    failWith(409);

    expect(component.errorKey()).toBe('shared.report.error_duplicate');
    expect(dialogText()).toContain('כבר דיווחת על תוכן זה.');
  });

  it('shows a generic message for other errors', () => {
    setup();

    failWith(500);

    expect(component.errorKey()).toBe('shared.report.error_generic');
    expect(dialogText()).toContain('אירעה שגיאה בשליחת הדיווח. נסה שוב.');
  });

  it('announces that the report is being sent while it is in flight', () => {
    setup();
    let release: ((value: unknown) => void) | undefined;
    reportServiceMock.fileReport.mockReturnValue({
      subscribe: (observer: { next: (value: unknown) => void }) => {
        release = observer.next;
        return { unsubscribe: () => undefined };
      },
    });
    open();
    setReason(ReportReason.SPAM);

    submitButton().click();
    fixture.detectChanges();

    expect(dialogText()).toContain('שולח דיווח...');
    expect(dialog().getAttribute('aria-busy')).toBe('true');
    expect(submitButton().disabled).toBe(true);

    release!({ id: 'report-1' });
    fixture.detectChanges();

    expect(dialog()).toBeFalsy();
  });

  it('keeps the dialog open on failure so the report can be retried', () => {
    setup();

    failWith(500);

    expect(dialog()).toBeTruthy();
    expect(submitButton().disabled).toBe(false);
  });

  /**
   * The reason the signal holds a key and the template runs the pipe: a
   * failure already on screen has to follow the reader into the other
   * language, which a message resolved to text at throw time cannot do.
   */
  it('re-renders a failure already on screen when the language changes', () => {
    setup();
    failWith(409);

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(dialogText()).toContain('You have already reported this content.');
  });

  describe('text', () => {
    it('renders the button and dialog in Hebrew by default', () => {
      setup();
      expect(openButton().textContent?.trim()).toBe('דיווח');

      open();

      expect(dialogText()).toContain('דיווח על תוכן');
      expect(dialogText()).toContain('סיבת הדיווח');
      expect(dialogText()).toContain('בחרו סיבה');
      expect(dialogText()).toContain('פירוט (לא חובה)');
      expect(dialogText()).toContain('שליחת דיווח');
      expect(dialogText()).toContain('ביטול');
    });

    it('renders the button and dialog in English under an English locale', () => {
      setup();
      open();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(dialogText()).toContain('Report content');
      expect(dialogText()).toContain('Reason for the report');
      expect(dialogText()).toContain('Choose a reason');
      expect(dialogText()).toContain('Send report');
      // The reason options come from REPORT_REASON_LABELS (ABF-127).
      expect(dialogText()).toContain('Harassment');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('translates the private-message disclosure too', () => {
      setup(ReportTargetType.DIRECT_MESSAGE, 'message-1');
      open();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(dialogText()).toContain(
        'confirming will reveal this message alone to the responsible moderator',
      );
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('shows the sent confirmation in English too', () => {
      setup();
      open();
      setReason(ReportReason.HARASSMENT);
      submitButton().click();
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(dialogText()).toContain('Your report was sent, thank you.');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup();
      open();

      expect(fixture.nativeElement.querySelector('.report-button').hasAttribute('dir')).toBe(false);
      expect(dialog().hasAttribute('dir')).toBe(false);
    });
  });
});
