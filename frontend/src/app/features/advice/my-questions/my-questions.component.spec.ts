import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { MyQuestionsComponent } from './my-questions.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeQuestion(overrides: Partial<ProfessionalQuery> = {}): ProfessionalQuery {
  return {
    id: 'q1',
    content: 'שאלה לדוגמה בנושא ירושה',
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
 * A question whose own text carries no Hebrew.
 *
 * What a person asked and what the professional answered are user-generated
 * content — out of scope for ABF-131 and never translated. Feeding Latin
 * content to the `HEBREW` sweeps below keeps them pointed at the UI copy,
 * which is the thing they are meant to guard.
 */
function makeLatinQuestion(overrides: Partial<ProfessionalQuery> = {}): ProfessionalQuery {
  return makeQuestion({
    content: 'A question about the paperwork',
    asker_alias: 'Widow - Sephardic',
    ...overrides,
  });
}

describe('MyQuestionsComponent', () => {
  let fixture: ComponentFixture<MyQuestionsComponent>;
  let component: MyQuestionsComponent;
  let professionalServiceMock: { getMyQuestions: ReturnType<typeof vi.fn> };

  async function setup(): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [MyQuestionsComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ProfessionalService, useValue: professionalServiceMock },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MyQuestionsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  it('loads questions on init', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(of([makeQuestion()])),
    };
    await setup();

    expect(component.isLoading()).toBe(false);
    expect(component.error()).toEqual({ key: '', text: '' });
    expect(component.questions.length).toBe(1);
  });

  it('shows an error message when loading fails', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
    };
    await setup();

    expect(component.error()).toEqual({ key: '', text: 'שגיאת שרת' });
    expect(component.isLoading()).toBe(false);
  });

  /** No `detail` — a network failure, say — so our own key carries the message. */
  it('falls back to our own key when the API sent no detail', async () => {
    professionalServiceMock = { getMyQuestions: vi.fn().mockReturnValue(throwError(() => ({}))) };
    await setup();

    expect(component.error()).toEqual({
      key: 'advice.errors.load_my_questions_failed',
      text: '',
    });
    expect(component.isLoading()).toBe(false);
  });

  it('shows the professional name when the question targets a specific professional', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            professional: {
              id: 'p1',
              first_name: 'דוד',
              last_name: 'כהן',
              professional_domain: ProfessionalDomain.LAWYER,
              professional_description: null,
            },
          }),
        ]),
      ),
    };
    await setup();

    expect(component.target(component.questions[0])).toBe('דוד כהן');
  });

  it('falls back to the domain label when there is no specific professional', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(of([makeQuestion({ domain: ProfessionalDomain.RABBI })])),
    };
    await setup();

    expect(component.target(component.questions[0])).toBe('רב/דיין');
  });

  it('shows the answer text when the question was answered', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            status: QueryStatus.ANSWERED,
            answer: 'זו תשובת המקצוען לשאלה שלך.',
          }),
        ]),
      ),
    };
    await setup();

    const answerEl = fixture.nativeElement.querySelector('.question-answer');
    expect(answerEl?.textContent).toContain('זו תשובת המקצוען לשאלה שלך.');
  });

  it('does not show an answer block for an open question', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(of([makeQuestion({ status: QueryStatus.OPEN })])),
    };
    await setup();

    const answerEl = fixture.nativeElement.querySelector('.question-answer');
    expect(answerEl).toBeNull();
  });

  it('does not show an answer block when answered but the answer text is missing', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(of([makeQuestion({ status: QueryStatus.ANSWERED, answer: null })])),
    };
    await setup();

    const answerEl = fixture.nativeElement.querySelector('.question-answer');
    expect(answerEl).toBeNull();
  });
  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /** Renders the screen against one service response. */
    async function renderWith(getMyQuestions: ReturnType<typeof vi.fn>): Promise<void> {
      professionalServiceMock = { getMyQuestions };
      await setup();
    }

    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeQuestion()])));

      expect(text()).toContain('חזרה לרשימת אנשי מקצוע');
      expect(heading()).toBe('השאלות שלי');
      expect(text()).toContain('עו"ד');
      expect(text()).toContain('פתוח');
    });

    it('leaves no Hebrew on the page in English', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinQuestion()])));

      switchToEnglish();

      expect(text()).toContain('Back to the professionals list');
      expect(heading()).toBe('My questions');
      expect(text()).toContain('Lawyer');
      expect(text()).toContain('Open');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the loading copy', async () => {
      await renderWith(vi.fn().mockReturnValue(NEVER));
      expect(text()).toContain('טוען שאלות...');

      switchToEnglish();

      expect(text()).toContain('Loading questions...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith(vi.fn().mockReturnValue(of([])));
      expect(text()).toContain('עדיין לא שאלת שאלות.');

      switchToEnglish();

      expect(text()).toContain('You have not asked any questions yet.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders our own failure copy in the new language', async () => {
      await renderWith(vi.fn().mockReturnValue(throwError(() => ({}))));
      expect(text()).toContain('שגיאה בטעינת השאלות שלך.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading your questions.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith(
        vi.fn().mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
      );

      switchToEnglish();

      expect(text()).toContain('שגיאת שרת');
    });

    /**
     * `target()` resolves the domain label in TypeScript, so it needs the
     * LabelService to follow the language rather than answer once and go stale.
     */
    it('re-resolves the domain a question was posted under', async () => {
      await renderWith(
        vi.fn().mockReturnValue(of([makeLatinQuestion({ domain: ProfessionalDomain.RABBI })])),
      );
      expect(text()).toContain('רב/דיין');

      switchToEnglish();

      expect(text()).toContain('Rabbi / Dayan');
      expect(text()).not.toMatch(HEBREW);
    });

    /** A question and its answer are content, not UI: they survive the switch. */
    it('leaves what the asker and the professional wrote alone', async () => {
      await renderWith(
        vi.fn().mockReturnValue(
          of([
            makeQuestion({
              status: QueryStatus.ANSWERED,
              answer: 'זו תשובת המקצוען לשאלה שלך.',
            }),
          ]),
        ),
      );

      switchToEnglish();

      expect(text()).toContain('שאלה לדוגמה בנושא ירושה');
      expect(text()).toContain('זו תשובת המקצוען לשאלה שלך.');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeQuestion()])));

      expect(fixture.nativeElement.querySelector('.my-questions-page').hasAttribute('dir')).toBe(
        false,
      );
    });
  });
});
