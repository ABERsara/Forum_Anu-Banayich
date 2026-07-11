import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { ConfirmDialogComponent } from './confirm-dialog.component';

describe('ConfirmDialogComponent', () => {
  let fixture: ComponentFixture<ConfirmDialogComponent>;
  let component: ConfirmDialogComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmDialogComponent],
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
});
