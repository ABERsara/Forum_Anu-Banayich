import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { PendingQuestionsComponent } from './pending-questions.component';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeQuestion(overrides: Partial<ProfessionalQuery> = {}): ProfessionalQuery {
  return {
    id: 'q1',
    content: 'שאלה שממתינה לתשובת איש המקצוע',
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
    ...overrides,
  };
}

/**
 * A pending question whose own text carries no Hebrew.
 *
 * What a person asked, and the alias or name they are shown under, are
 * user-generated content — out of scope for ABF-131 and never translated.
 * Feeding Latin content to the `HEBREW` sweeps below keeps them pointed at the
 * UI copy, which is the thing they are meant to guard.
 */
function makeLatinQuestion(overrides: Partial<ProfessionalQuery> = {}): ProfessionalQuery {
  return makeQuestion({
    content: 'A question waiting for the professional',
    asker_alias: 'Widow - Sephardic',
    ...overrides,
  });
}

describe('PendingQuestionsComponent', () => {
  let fixture: ComponentFixture<PendingQuestionsComponent>;
  let component: PendingQuestionsComponent;
  let professionalServiceMock: {
    getPendingQuestions: ReturnType<typeof vi.fn>;
    answerQuestion: ReturnType<typeof vi.fn>;
  };

  async function setup(): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [PendingQuestionsComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ProfessionalService, useValue: professionalServiceMock },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PendingQuestionsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function mockService(overrides: Partial<typeof professionalServiceMock> = {}): void {
    professionalServiceMock = {
      getPendingQuestions: vi.fn().mockReturnValue(of([makeQuestion()])),
      answerQuestion: vi.fn().mockReturnValue(of(makeQuestion({ status: QueryStatus.ANSWERED }))),
      ...overrides,
    };
  }

  it('loads the pending queue on init', async () => {
    mockService();
    await setup();

    expect(component.isLoading()).toBe(false);
    expect(component.error()).toEqual({ key: '', text: '' });
    expect(component.questions().length).toBe(1);
  });

  it('shows an error message when loading fails', async () => {
    mockService({
      getPendingQuestions: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
    });
    await setup();

    expect(component.error()).toEqual({ key: '', text: 'שגיאת שרת' });
    expect(component.isLoading()).toBe(false);
  });

  /** No `detail` — a network failure, say — so our own key carries the message. */
  it('falls back to our own key when the API sent no detail', async () => {
    mockService({ getPendingQuestions: vi.fn().mockReturnValue(throwError(() => ({}))) });
    await setup();

    expect(component.error()).toEqual({ key: 'advice.errors.load_pending_failed', text: '' });
    expect(component.isLoading()).toBe(false);
  });

  it('identifies the asker by alias, not by name', async () => {
    mockService();
    await setup();

    expect(component.askerLabel(component.questions()[0])).toBe('אלמנה – ספרדי');
  });

  it('shows the real name when the asker chose to reveal it', async () => {
    mockService({
      getPendingQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            asker: { id: 'u1', first_name: 'שרה', last_name: 'לוי' },
          }),
        ]),
      ),
    });
    await setup();

    expect(component.askerLabel(component.questions()[0])).toBe('שרה לוי');
  });

  it('submits the answer and removes the question from the queue', async () => {
    mockService();
    await setup();

    const question = component.questions()[0];
    component.answerControl(question).setValue('זו התשובה המקצועית המלאה');
    component.submit(question);

    expect(professionalServiceMock.answerQuestion).toHaveBeenCalledWith(
      'q1',
      'זו התשובה המקצועית המלאה',
    );
    expect(component.questions().length).toBe(0);
    expect(component.successKey()).toBe('advice.pending.success');
    expect(component.submittingId()).toBeNull();
  });

  it('does not submit an answer that is too short', async () => {
    mockService();
    await setup();

    const question = component.questions()[0];
    component.answerControl(question).setValue('קצר');
    component.submit(question);

    expect(professionalServiceMock.answerQuestion).not.toHaveBeenCalled();
    expect(component.questions().length).toBe(1);
  });

  it('keeps the question in the queue when submitting fails', async () => {
    mockService({
      answerQuestion: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'השאלה כבר נענתה.' } }))),
    });
    await setup();

    const question = component.questions()[0];
    component.answerControl(question).setValue('תשובה שלא תיקלט בשרת');
    component.submit(question);

    expect(component.error()).toEqual({ key: '', text: 'השאלה כבר נענתה.' });
    expect(component.questions().length).toBe(1);
    expect(component.submittingId()).toBeNull();
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

    /** Touches the answer box with something too short, so its error renders. */
    function showValidationError(): void {
      const control = component.answerControl(component.questions()[0]);
      control.setValue('קצר');
      control.markAsTouched();
      fixture.detectChanges();
    }

    /** Answers the one pending question, so the confirmation renders. */
    function answerTheQuestion(): void {
      const question = component.questions()[0];
      component.answerControl(question).setValue('זו התשובה המקצועית המלאה');
      component.submit(question);
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      mockService();
      await setup();

      expect(text()).toContain('חזרה לעמוד הבית');
      expect(heading()).toBe('שאלות ממתינות לתשובה');
      expect(text()).toContain(
        'השאלות מוצגות לפי סדר הגעתן — הוותיקה ביותר ראשונה. פרטי השואל/ת חסויים.',
      );
      expect(text()).toContain('נשאלה ב-14/07/2026');
      expect(text()).toContain('התשובה שלך');
      expect(text()).toContain('שליחת תשובה');
      expect(text()).toContain('עו"ד');
      expect(placeholders()).toContain('כתוב/כתבי כאן את התשובה (10 עד 5000 תווים)');
    });

    it('leaves no Hebrew on the page in English', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])) });
      await setup();

      switchToEnglish();

      expect(text()).toContain('Back to the home page');
      expect(heading()).toBe('Questions awaiting an answer');
      expect(text()).toContain('Questions are listed in the order they arrived');
      expect(text()).toContain('Your answer');
      expect(text()).toContain('Send answer');
      expect(text()).toContain('Lawyer');
      expect(placeholders()).toContain('Write your answer here (10 to 5000 characters)');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The date is a parameter, so the sentence around it changes and it does not. */
    it('keeps the date when the sentence around it changes', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])) });
      await setup();
      expect(text()).toContain('נשאלה ב-14/07/2026');

      switchToEnglish();

      expect(text()).toContain('Asked on 14/07/2026');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the validation message', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])) });
      await setup();
      showValidationError();
      expect(text()).toContain('נא להזין תשובה באורך 10 עד 5000 תווים');

      switchToEnglish();

      expect(text()).toContain('Please enter an answer of 10 to 5000 characters');
    });

    it('translates the loading copy', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(NEVER) });
      await setup();
      expect(text()).toContain('טוען שאלות ממתינות...');

      switchToEnglish();

      expect(text()).toContain('Loading pending questions...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(of([])) });
      await setup();
      expect(text()).toContain('אין כרגע שאלות שממתינות לתשובתך.');

      switchToEnglish();

      expect(text()).toContain('No questions are waiting for your answer right now.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The confirmation is held as a key, so it follows the switch too. */
    it('re-renders the confirmation that is already on screen', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])) });
      await setup();
      answerTheQuestion();
      expect(text()).toContain('התשובה נשלחה, והשואל/ת קיבל/ה על כך התראה במייל.');

      switchToEnglish();

      expect(text()).toContain('Your answer was sent, and the asker has been notified by email.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the in-flight copy on the button that is submitting', async () => {
      mockService({
        getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])),
        answerQuestion: vi.fn().mockReturnValue(NEVER),
      });
      await setup();
      answerTheQuestion();
      expect(text()).toContain('שולח תשובה...');

      switchToEnglish();

      expect(text()).toContain('Sending answer...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders our own failure copy in the new language', async () => {
      mockService({ getPendingQuestions: vi.fn().mockReturnValue(throwError(() => ({}))) });
      await setup();
      expect(text()).toContain('שגיאה בטעינת השאלות הממתינות.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the pending questions.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      mockService({
        getPendingQuestions: vi.fn().mockReturnValue(of([makeLatinQuestion()])),
        answerQuestion: vi
          .fn()
          .mockReturnValue(throwError(() => ({ error: { detail: 'השאלה כבר נענתה.' } }))),
      });
      await setup();
      answerTheQuestion();

      switchToEnglish();

      expect(text()).toContain('השאלה כבר נענתה.');
    });

    /** The asker's alias or name, and their question, are content — not UI. */
    it('leaves the asker alias and the question text alone', async () => {
      mockService();
      await setup();

      switchToEnglish();

      expect(text()).toContain('אלמנה – ספרדי');
      expect(text()).toContain('שאלה שממתינה לתשובת איש המקצוע');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      mockService();
      await setup();

      expect(fixture.nativeElement.querySelector('.pending-questions').hasAttribute('dir')).toBe(
        false,
      );
    });
  });
});
