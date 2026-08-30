import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { vi } from 'vitest';

import { ConfirmDialogComponent } from './confirm-dialog.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('ConfirmDialogComponent', () => {
  let fixture: ComponentFixture<ConfirmDialogComponent>;
  let component: ConfirmDialogComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmDialogComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(ConfirmDialogComponent);
    component = fixture.componentInstance;
  });

  function confirmButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelectorAll('button')[1] as HTMLButtonElement;
  }

  function cancelButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelectorAll('button')[0] as HTMLButtonElement;
  }

  function setTextareaValue(value: string): void {
    const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    textarea.value = value;
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('does not render a textarea when requireInput is false', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('textarea')).toBeNull();
  });

  it('emits an empty string on confirm when requireInput is false', () => {
    fixture.detectChanges();
    const confirmed = vi.fn();
    component.confirmed.subscribe(confirmed);

    confirmButton().click();

    expect(confirmed).toHaveBeenCalledWith('');
  });

  it('disables confirm while the typed text is shorter than inputMinLength', () => {
    fixture.componentRef.setInput('requireInput', true);
    fixture.componentRef.setInput('inputMinLength', 5);
    fixture.detectChanges();

    expect(confirmButton().disabled).toBe(true);

    setTextareaValue('קצר');
    expect(confirmButton().disabled).toBe(true);

    setTextareaValue('מספיק ארוך');
    expect(confirmButton().disabled).toBe(false);
  });

  it('emits the trimmed typed text on confirm', () => {
    fixture.componentRef.setInput('requireInput', true);
    fixture.componentRef.setInput('inputMinLength', 5);
    fixture.detectChanges();
    const confirmed = vi.fn();
    component.confirmed.subscribe(confirmed);

    setTextareaValue('  סיבה תקינה  ');
    confirmButton().click();

    expect(confirmed).toHaveBeenCalledWith('סיבה תקינה');
  });

  it('does not emit confirmed when clicked while disabled', () => {
    fixture.componentRef.setInput('requireInput', true);
    fixture.componentRef.setInput('inputMinLength', 5);
    fixture.detectChanges();
    const confirmed = vi.fn();
    component.confirmed.subscribe(confirmed);

    setTextareaValue('קצר');
    confirmButton().click();

    expect(confirmed).not.toHaveBeenCalled();
  });

  it('emits cancelled when the cancel button is clicked', () => {
    fixture.detectChanges();
    const cancelled = vi.fn();
    component.cancelled.subscribe(cancelled);

    cancelButton().click();

    expect(cancelled).toHaveBeenCalled();
  });

  describe('text', () => {
    function dialogText(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    it('falls back to the generic Hebrew prompt when the caller passes no text', () => {
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'האם לאשר?',
      );
      expect(confirmButton().textContent?.trim()).toBe('אישור');
      expect(cancelButton().textContent?.trim()).toBe('ביטול');
    });

    /**
     * The dialog renders the text it is handed, untouched. Every feature call
     * site still passes a Hebrew literal — those move to the `transloco` pipe
     * in their own migration ticket, and must keep working until they do.
     */
    it('renders caller-supplied text verbatim, translated or not', () => {
      fixture.componentRef.setInput('title', 'מחיקת הודעה');
      fixture.componentRef.setInput('confirmText', 'מחיקה');
      fixture.componentRef.setInput('cancelText', 'לא עכשיו');
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'מחיקת הודעה',
      );
      expect(confirmButton().textContent?.trim()).toBe('מחיקה');
      expect(cancelButton().textContent?.trim()).toBe('לא עכשיו');
    });

    it('shows the generic prompt in English under an English locale', () => {
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'Are you sure?',
      );
      expect(confirmButton().textContent?.trim()).toBe('Confirm');
      expect(cancelButton().textContent?.trim()).toBe('Cancel');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog').hasAttribute('dir')).toBe(false);
    });
  });
});
