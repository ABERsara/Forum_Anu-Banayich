import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { vi } from 'vitest';

import { CopyTextComponent } from './copy-text.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('CopyTextComponent', () => {
  let fixture: ComponentFixture<CopyTextComponent>;
  let component: CopyTextComponent;
  let writeTextMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    await TestBed.configureTestingModule({
      imports: [CopyTextComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(CopyTextComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('text', 'test-value');
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('renders the copy button', () => {
    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.type).toBe('button');
  });

  it('has a descriptive aria-label that includes the text', () => {
    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    expect(button.getAttribute('aria-label')).toContain('test-value');
  });

  it('copies text to clipboard on click', async () => {
    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    button.click();
    await fixture.whenStable();

    expect(writeTextMock).toHaveBeenCalledWith('test-value');
  });

  it('shows success label after copying', async () => {
    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    button.click();
    await fixture.whenStable();
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.copy-btn__label') as HTMLElement;
    expect(label.textContent?.trim()).toBe('הועתק!');
  });

  it('reverts to original label after 2 seconds', async () => {
    vi.useFakeTimers();

    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    button.click();

    // fixture.whenStable() deadlocks under fake timers with zoneless change
    // detection, so flush the clipboard microtask and the reset timer via
    // advanceTimersByTimeAsync instead of whenStable().
    await vi.advanceTimersByTimeAsync(2000);
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.copy-btn__label') as HTMLElement;
    expect(label.textContent?.trim()).toBe('העתק');
  });

  it('emits the copied output on successful copy', async () => {
    const copiedHandler = vi.fn();
    component.copied.subscribe(copiedHandler);

    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    button.click();
    await fixture.whenStable();

    expect(copiedHandler).toHaveBeenCalled();
  });

  it('applies --copied modifier class while in success state', async () => {
    const button = fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement;
    expect(button.classList.contains('copy-btn--copied')).toBe(false);

    button.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(button.classList.contains('copy-btn--copied')).toBe(true);
  });

  it('accepts a custom label via input', () => {
    fixture.componentRef.setInput('label', 'Copy ID');
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.copy-btn__label') as HTMLElement;
    expect(label.textContent?.trim()).toBe('Copy ID');
  });

  it('falls back to a generic label in English under an English locale', async () => {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.copy-btn__label') as HTMLElement;
    expect(label.textContent?.trim()).toBe('Copy');

    (fixture.nativeElement.querySelector('.copy-btn') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(label.textContent?.trim()).toBe('Copied!');
    expect((fixture.nativeElement as HTMLElement).textContent ?? '').not.toMatch(HEBREW);
  });
});
