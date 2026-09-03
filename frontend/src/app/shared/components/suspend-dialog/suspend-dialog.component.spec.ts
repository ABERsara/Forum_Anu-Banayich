import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { vi } from 'vitest';

import { SuspendDialogComponent } from './suspend-dialog.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('SuspendDialogComponent', () => {
  let fixture: ComponentFixture<SuspendDialogComponent>;
  let component: SuspendDialogComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SuspendDialogComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(SuspendDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  function confirmButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelectorAll('button')[1] as HTMLButtonElement;
  }

  function cancelButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelectorAll('button')[0] as HTMLButtonElement;
  }

  function hoursInput(): HTMLInputElement {
    return fixture.nativeElement.querySelector('input[type="number"]') as HTMLInputElement;
  }

  function setHours(value: string): void {
    const input = hoursInput();
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function setReason(value: string): void {
    const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    textarea.value = value;
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('shows a default of 48 hours', () => {
    expect(hoursInput().value).toBe('48');
  });

  it('disables confirm while the reason is shorter than 5 characters', () => {
    setReason('קצר');
    expect(confirmButton().disabled).toBe(true);

    setReason('סיבה תקינה');
    expect(confirmButton().disabled).toBe(false);
  });

  it('disables confirm when hours is zero or negative', () => {
    setReason('סיבה תקינה');
    setHours('0');
    expect(confirmButton().disabled).toBe(true);

    setHours('-5');
    expect(confirmButton().disabled).toBe(true);

    setHours('24');
    expect(confirmButton().disabled).toBe(false);
  });

  it('emits the hours and trimmed reason on confirm', () => {
    const confirmed = vi.fn();
    component.confirmed.subscribe(confirmed);

    setHours('72');
    setReason('  הפרת כללי הפורום  ');
    confirmButton().click();

    expect(confirmed).toHaveBeenCalledWith({ hours: 72, reason: 'הפרת כללי הפורום' });
  });

  it('does not emit confirmed when clicked while disabled', () => {
    const confirmed = vi.fn();
    component.confirmed.subscribe(confirmed);

    setReason('קצר');
    confirmButton().click();

    expect(confirmed).not.toHaveBeenCalled();
  });

  it('emits cancelled when the cancel button is clicked', () => {
    const cancelled = vi.fn();
    component.cancelled.subscribe(cancelled);

    cancelButton().click();

    expect(cancelled).toHaveBeenCalled();
  });

  describe('text', () => {
    function dialogText(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function reasonTextarea(): HTMLTextAreaElement {
      return fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    }

    it('falls back to the generic Hebrew prompt when the caller passes no text', () => {
      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'השעיית משתמש',
      );
      expect(confirmButton().textContent?.trim()).toBe('השעה');
      expect(cancelButton().textContent?.trim()).toBe('ביטול');
    });

    it('labels its own hours and reason fields', () => {
      const labels = [...fixture.nativeElement.querySelectorAll('.dialog__label')].map(
        (el: Element) => el.textContent?.trim(),
      );

      expect(labels).toEqual(['מספר שעות', 'סיבת ההשעייה']);
      expect(reasonTextarea().placeholder).toBe('לדוגמה: הפרת כללי הפורום');
    });

    /** As in confirm-dialog: un-migrated call sites still pass Hebrew literals. */
    it('renders caller-supplied text verbatim, translated or not', () => {
      fixture.componentRef.setInput('title', 'השעיית שרה לוי');
      fixture.componentRef.setInput('confirmText', 'להשעות');
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'השעיית שרה לוי',
      );
      expect(confirmButton().textContent?.trim()).toBe('להשעות');
    });

    it('shows the whole dialog in English under an English locale', () => {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.dialog__title').textContent.trim()).toBe(
        'Suspend user',
      );
      expect(confirmButton().textContent?.trim()).toBe('Suspend');
      expect(cancelButton().textContent?.trim()).toBe('Cancel');
      expect(reasonTextarea().placeholder).toBe('For example: breach of the forum rules');
      expect(dialogText()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      expect(fixture.nativeElement.querySelector('.dialog').hasAttribute('dir')).toBe(false);
    });
  });
});
