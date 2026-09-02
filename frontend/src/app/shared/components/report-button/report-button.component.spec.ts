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

  function setup(): void {
    reportServiceMock = {
      fileReport: vi.fn().mockReturnValue(of({ id: 'report-1' })),
    };

    TestBed.configureTestingModule({
      imports: [ReportButtonComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ReportButtonComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('contentType', ReportTargetType.FORUM_POST);
    fixture.componentRef.setInput('contentId', 'post-1');
    fixture.detectChanges();
  }

  function openButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('.report-button button') as HTMLButtonElement;
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

  it('shows the report button and no dialog initially', () => {
    setup();

    expect(openButton()).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.dialog')).toBeFalsy();
  });

  it('opens the dialog on click', () => {
    setup();

    openButton().click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.dialog')).toBeTruthy();
  });

  it('closes the dialog on cancel without submitting', () => {
    setup();
    openButton().click();
    fixture.detectChanges();

    cancelButton().click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.dialog')).toBeFalsy();
    expect(reportServiceMock.fileReport).not.toHaveBeenCalled();
  });

  it('submits with the selected reason, trimmed description, and given content target', () => {
    setup();
    openButton().click();
    fixture.detectChanges();
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
    openButton().click();
    fixture.detectChanges();

    submitButton().click();

    expect(reportServiceMock.fileReport).toHaveBeenCalledWith(
      expect.objectContaining({ description: undefined }),
    );
  });

  function dialogText(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('hides the dialog and shows a confirmation on success', () => {
    setup();
    openButton().click();
    fixture.detectChanges();

    submitButton().click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.dialog')).toBeFalsy();
    expect(fixture.nativeElement.textContent).toContain('הדיווח נשלח, תודה.');
  });

  function failWith(status: number): void {
    reportServiceMock.fileReport.mockReturnValue(throwError(() => ({ status })));
    openButton().click();
    fixture.detectChanges();
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

      openButton().click();
      fixture.detectChanges();

      expect(dialogText()).toContain('דיווח על תוכן');
      expect(dialogText()).toContain('סיבת הדיווח');
      expect(dialogText()).toContain('פירוט (לא חובה)');
      expect(dialogText()).toContain('שליחת דיווח');
      expect(dialogText()).toContain('ביטול');
    });

    it('renders the button and dialog in English under an English locale', () => {
      setup();
      openButton().click();
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(dialogText()).toContain('Report content');
      expect(dialogText()).toContain('Reason for the report');
      expect(dialogText()).toContain('Send report');
      // The reason options come from REPORT_REASON_LABELS (ABF-127).
      expect(dialogText()).toContain('Harassment');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('shows the sent confirmation in English too', () => {
      setup();
      openButton().click();
      fixture.detectChanges();
      submitButton().click();
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(dialogText()).toContain('Your report was sent, thank you.');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup();
      openButton().click();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.report-button').hasAttribute('dir')).toBe(false);
      expect(fixture.nativeElement.querySelector('.dialog').hasAttribute('dir')).toBe(false);
    });
  });
});
