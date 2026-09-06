import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTransloco } from '@jsverse/transloco';
import { vi } from 'vitest';

import { LanguageToggleComponent } from './language-toggle.component';
import { TranslocoHttpLoader } from '../../../core/i18n/transloco-loader';

describe('LanguageToggleComponent', () => {
  let fixture: ComponentFixture<LanguageToggleComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LanguageToggleComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTransloco({
          config: { availableLangs: ['he', 'en'], defaultLang: 'he', reRenderOnLangChange: true },
          loader: TranslocoHttpLoader,
        }),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LanguageToggleComponent);
    fixture.componentRef.setInput('isHebrew', true);
    fixture.detectChanges();
  });

  it('renders a button', () => {
    const button = fixture.nativeElement.querySelector('.language-toggle') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.type).toBe('button');
  });

  it('emits toggled on click', () => {
    const toggleHandler = vi.fn();
    fixture.componentInstance.toggled.subscribe(toggleHandler);

    const button = fixture.nativeElement.querySelector('.language-toggle') as HTMLButtonElement;
    button.click();

    expect(toggleHandler).toHaveBeenCalled();
  });

  it('does not inject LocaleService or TranslocoService directly', () => {
    // Architectural guard: this is a dumb component per CONTRIBUTING.md §3 —
    // it must only depend on its inputs/outputs, never reach for a service itself.
    expect(fixture.componentInstance).not.toHaveProperty('locale');
    expect(fixture.componentInstance).not.toHaveProperty('transloco');
  });
});
