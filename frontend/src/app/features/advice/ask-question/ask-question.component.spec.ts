import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AskQuestionComponent } from './ask-question.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeActivatedRoute(professionalId: string | null): ActivatedRoute {
  return {
    snapshot: { queryParamMap: convertToParamMap(professionalId ? { professionalId } : {}) },
  } as unknown as ActivatedRoute;
}

const RESPONSE: ProfessionalQuery = {
  id: 'q1',
  content: 'שאלה לדוגמה',
  answer: null,
  is_public: false,
  status: QueryStatus.OPEN,
  is_featured: false,
  domain: ProfessionalDomain.LAWYER,
  professional: null,
  asker_alias: 'אלמנה – ספרדי',
  asker: null,
  created_at: '2026-07-14T10:00:00',
  answered_at: null,
};

describe('AskQuestionComponent', () => {
  let fixture: ComponentFixture<AskQuestionComponent>;
  let component: AskQuestionComponent;
  let professionalServiceMock: { askQuestion: ReturnType<typeof vi.fn> };
  let router: Router;

  async function setup(professionalId: string | null = null): Promise<void> {
    professionalServiceMock = { askQuestion: vi.fn().mockReturnValue(of(RESPONSE)) };

    await TestBed.configureTestingModule({
      imports: [AskQuestionComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ProfessionalService, useValue: professionalServiceMock },
        { provide: ActivatedRoute, useValue: makeActivatedRoute(professionalId) },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    fixture = TestBed.createComponent(AskQuestionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  /** Fills the form with something the validators accept and submits it. */
  function submitValidQuestion(): void {
    component.form.setValue({
      content: 'זוהי שאלה תקינה עם תוכן מספיק',
      is_public: false,
      show_real_name: false,
      domain: ProfessionalDomain.RABBI,
    });
    component.onSubmit();
    fixture.detectChanges();
  }

  it('lists the domain options in the active language', async () => {
    await setup();
    const domainOptions = () =>
      Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLOptionElement>(
          'select[formControlName="domain"] option',
        ),
      ).map((option) => option.textContent?.trim());

    expect(domainOptions()).toContain('רב/דיין');

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(domainOptions()).toContain('Rabbi / Dayan');
  });

  it('reads professionalId from the query params', async () => {
    await setup('pro-1');
    expect(component.professionalId).toBe('pro-1');
  });

  it('does not submit an invalid form', async () => {
    await setup();
    component.onSubmit();
    expect(professionalServiceMock.askQuestion).not.toHaveBeenCalled();
  });

  it('sends professional_id when targeting a specific professional', async () => {
    await setup('pro-1');
    component.form.setValue({
      content: 'זוהי שאלה תקינה עם תוכן מספיק',
      is_public: false,
      show_real_name: false,
      domain: null,
    });

    component.onSubmit();

    expect(professionalServiceMock.askQuestion).toHaveBeenCalledWith(
      expect.objectContaining({ professional_id: 'pro-1' }),
    );
    expect(router.navigate).toHaveBeenCalledWith(['/advice']);
  });

  it('sends domain when no professional is targeted', async () => {
    await setup(null);
    component.form.setValue({
      content: 'זוהי שאלה תקינה עם תוכן מספיק',
      is_public: false,
      show_real_name: false,
      domain: ProfessionalDomain.RABBI,
    });

    component.onSubmit();

    expect(professionalServiceMock.askQuestion).toHaveBeenCalledWith(
      expect.objectContaining({ domain: ProfessionalDomain.RABBI }),
    );
  });

  it('shows the backend error detail when submission fails', async () => {
    await setup(null);
    professionalServiceMock.askQuestion.mockReturnValue(
      throwError(() => ({ error: { detail: 'שגיאה מהשרת' } })),
    );
    submitValidQuestion();

    expect(component.error()).toEqual({ key: '', text: 'שגיאה מהשרת' });
    expect(component.isLoading()).toBe(false);
  });

  /** No `detail` — a network failure, say — so our own key carries the message. */
  it('falls back to our own key when the API sent no detail', async () => {
    await setup(null);
    professionalServiceMock.askQuestion.mockReturnValue(throwError(() => ({})));
    submitValidQuestion();

    expect(component.error()).toEqual({ key: 'advice.errors.ask_failed', text: '' });
    expect(component.isLoading()).toBe(false);
  });
  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    function placeholders(): (string | null)[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('[placeholder]'),
      ).map((element) => element.getAttribute('placeholder'));
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /** Touches every control so the validation messages render. */
    function showValidationErrors(): void {
      component.form.markAllAsTouched();
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await setup(null);

      expect(text()).toContain('חזרה לרשימת אנשי מקצוע');
      expect(heading()).toBe('שאלה מקצועית');
      expect(text()).toContain('בחר/י תחום — השאלה תישלח לכל אנשי המקצוע בתחום זה.');
      expect(text()).toContain('תחום');
      expect(text()).toContain('השאלה שלך');
      expect(text()).toContain('האם לפרסם את השאלה והתשובה לחברי הקהילה?');
      expect(text()).toContain('הצג/י את שמי האמיתי לאיש המקצוע');
      expect(text()).toContain('שלח שאלה');
      expect(placeholders()).toContain('פרט/י את שאלתך (10 עד 2000 תווים)');
    });

    it('leaves no Hebrew on the page in English', async () => {
      await setup(null);

      switchToEnglish();

      expect(text()).toContain('Back to the professionals list');
      expect(heading()).toBe('Professional question');
      expect(text()).toContain(
        'Choose a field — your question will be sent to every professional in it.',
      );
      expect(text()).toContain('Field');
      expect(text()).toContain('Your question');
      expect(placeholders()).toContain('Describe your question (10 to 2000 characters)');
      expect(text()).toContain('Send question');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The ticket calls out both checkbox labels by name. */
    it('translates both checkbox labels', async () => {
      await setup(null);
      expect(text()).toContain('האם לפרסם את השאלה והתשובה לחברי הקהילה?');
      expect(text()).toContain('הצג/י את שמי האמיתי לאיש המקצוע');

      switchToEnglish();

      expect(text()).toContain('Publish this question and its answer to the community?');
      expect(text()).toContain('Show my real name to the professional');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the validation messages', async () => {
      await setup(null);
      showValidationErrors();
      expect(text()).toContain('נא לבחור תחום');
      expect(text()).toContain('נא להזין שאלה (10 עד 2000 תווים)');

      switchToEnglish();

      expect(text()).toContain('Please choose a field');
      expect(text()).toContain('Please enter a question (10 to 2000 characters)');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the hint shown when a professional was chosen', async () => {
      await setup('pro-1');
      expect(text()).toContain('השאלה תישלח לאיש המקצוע הנבחר.');

      switchToEnglish();

      expect(text()).toContain('Your question will be sent to the professional you chose.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the sending copy while the request is in flight', async () => {
      await setup(null);
      professionalServiceMock.askQuestion.mockReturnValue(NEVER);
      submitValidQuestion();
      expect(text()).toContain('שולח שאלה...');

      switchToEnglish();

      expect(text()).toContain('Sending question...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders our own failure copy in the new language', async () => {
      await setup(null);
      professionalServiceMock.askQuestion.mockReturnValue(throwError(() => ({})));
      submitValidQuestion();
      expect(text()).toContain('שגיאה בשליחת השאלה.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong sending the question.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await setup(null);
      professionalServiceMock.askQuestion.mockReturnValue(
        throwError(() => ({ error: { detail: 'לא ניתן לשאול את איש המקצוע הזה.' } })),
      );
      submitValidQuestion();

      switchToEnglish();

      expect(text()).toContain('לא ניתן לשאול את איש המקצוע הזה.');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await setup(null);

      expect(fixture.nativeElement.querySelector('.ask-question-page').hasAttribute('dir')).toBe(
        false,
      );
    });
  });
});
