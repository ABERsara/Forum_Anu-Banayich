import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideTransloco } from '@jsverse/transloco';
import { vi } from 'vitest';

import { HeaderComponent } from './header.component';
import { TranslocoHttpLoader } from '../../core/i18n/transloco-loader';
import { AuthService } from '../../core/services/auth.service';
import { LocaleService, type AppLang } from '../../core/services/locale.service';

describe('HeaderComponent', () => {
  let fixture: ComponentFixture<HeaderComponent>;
  let langSignal: ReturnType<typeof signal<AppLang>>;
  let toggleLangSpy: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    langSignal = signal<AppLang>('he');
    toggleLangSpy = vi.fn();

    await TestBed.configureTestingModule({
      imports: [HeaderComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTransloco({
          config: { availableLangs: ['he', 'en'], defaultLang: 'he', reRenderOnLangChange: true },
          loader: TranslocoHttpLoader,
        }),
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        { provide: LocaleService, useValue: { lang: langSignal, toggleLang: toggleLangSpy } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(HeaderComponent);
    fixture.detectChanges();
  });

  it('isHebrew() reflects LocaleService.lang()', () => {
    expect(fixture.componentInstance.isHebrew()).toBe(true);

    langSignal.set('en');
    fixture.detectChanges();

    expect(fixture.componentInstance.isHebrew()).toBe(false);
  });

  it('clicking the language toggle calls LocaleService.toggleLang', () => {
    const button = fixture.nativeElement.querySelector('.language-toggle') as HTMLButtonElement;
    button.click();

    expect(toggleLangSpy).toHaveBeenCalled();
  });
});
