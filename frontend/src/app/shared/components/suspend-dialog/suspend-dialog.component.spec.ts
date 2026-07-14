import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { SuspendDialogComponent } from './suspend-dialog.component';

describe('SuspendDialogComponent', () => {
  let fixture: ComponentFixture<SuspendDialogComponent>;
  let component: SuspendDialogComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SuspendDialogComponent],
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
});
