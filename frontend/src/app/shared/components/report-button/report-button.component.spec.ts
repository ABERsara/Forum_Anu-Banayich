import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ReportButtonComponent } from './report-button.component';
import { ReportReason, ReportTargetType } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';

describe('ReportButtonComponent', () => {
  let fixture: ComponentFixture<ReportButtonComponent>;
  let component: ReportButtonComponent;
  let reportServiceMock: { fileReport: ReturnType<typeof vi.fn> };

  function setup(): void {
    reportServiceMock = {
      fileReport: vi.fn().mockReturnValue(of({ id: 'report-1' })),
    };

    TestBed.configureTestingModule({
      imports: [ReportButtonComponent],
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

  it('hides the dialog and shows a confirmation on success', () => {
    setup();
    openButton().click();
    fixture.detectChanges();

    submitButton().click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.dialog')).toBeFalsy();
    expect(fixture.nativeElement.textContent).toContain('הדיווח נשלח, תודה.');
  });

  it('shows a specific message for a duplicate report (409)', () => {
    setup();
    reportServiceMock.fileReport.mockReturnValue(throwError(() => ({ status: 409 })));
    openButton().click();
    fixture.detectChanges();

    submitButton().click();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('כבר דיווחת על תוכן זה.');
  });

  it('shows a generic message for other errors', () => {
    setup();
    reportServiceMock.fileReport.mockReturnValue(throwError(() => ({ status: 500 })));
    openButton().click();
    fixture.detectChanges();

    submitButton().click();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('אירעה שגיאה בשליחת הדיווח. נסה שוב.');
  });
});
