/**
 * The disclaimer banner: the sentence, the role it is announced under, and the
 * direction it does *not* pin.
 *
 * The text is asserted character for character against SPEC §12 rather than
 * merely "is not empty". It is the one sentence on the agent screens that the
 * association is legally exposed by, so a reworded key should fail here and be
 * re-approved, not slip through because the element still renders something.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { DisclaimerBannerComponent } from './disclaimer-banner.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

/** SPEC §12, verbatim. */
const HEBREW_TEXT = 'המידע הוא כללי בלבד ואינו מהווה ייעוץ מקצועי מחייב.';
const ENGLISH_TEXT = 'This information is general only and is not binding professional advice.';

describe('DisclaimerBannerComponent', () => {
  let fixture: ComponentFixture<DisclaimerBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DisclaimerBannerComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(DisclaimerBannerComponent);
    fixture.detectChanges();
  });

  function banner(): HTMLElement {
    return fixture.nativeElement.querySelector('.disclaimer-banner');
  }

  /** The icon is decorative and aria-hidden; the sentence is what is read. */
  function sentence(): string {
    return banner().querySelector('span:not([aria-hidden])')!.textContent!.trim();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  it('shows the spec wording, in Hebrew, with no caller involved', () => {
    expect(sentence()).toBe(HEBREW_TEXT);
  });

  it('shows the same notice in English, leaving no Hebrew behind', () => {
    switchToEnglish();

    expect(sentence()).toBe(ENGLISH_TEXT);
    expect(fixture.nativeElement.textContent).not.toMatch(HEBREW);
  });

  /**
   * The banner is inserted with the chat screen, and a live region that
   * arrives carrying its text is announced on arrival — which is the point:
   * the member hears the disclaimer on entering the conversation rather than
   * after the first answer.
   */
  it('announces itself as an alert', () => {
    expect(banner().getAttribute('role')).toBe('alert');
  });

  /** WCAG 1.4.1 — the icon is colour and shape, so it is hidden, not read. */
  it('hides the decorative icon from assistive technology', () => {
    expect(banner().querySelector('[aria-hidden="true"]')).toBeTruthy();
  });

  /**
   * The ticket asked for `dir="rtl"`. CONTRIBUTING §6 forbids it and
   * `core/i18n/direction.spec.ts` fails the build over it — direction comes
   * from `<html dir>`, so the banner turns with the language on its own.
   */
  it('does not pin its own text direction — it follows <html dir>', () => {
    expect(banner().hasAttribute('dir')).toBe(false);
  });
});
