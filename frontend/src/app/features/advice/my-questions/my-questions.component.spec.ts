import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { MyQuestionsComponent } from './my-questions.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';
import { translocoTesting } from '../../../../testing/transloco-testing';

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
    like_count: 0,
    liked_by_me: false,
    ...overrides,
  };
}

describe('MyQuestionsComponent', () => {
  let fixture: ComponentFixture<MyQuestionsComponent>;
  let component: MyQuestionsComponent;
  let professionalServiceMock: {
    getMyQuestions: ReturnType<typeof vi.fn>;
    toggleLike: ReturnType<typeof vi.fn>;
  };

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
      toggleLike: vi.fn(),
    };
    await setup();

    expect(component.isLoading()).toBe(false);
    expect(component.errorMessage()).toBe('');
    expect(component.questions().length).toBe(1);
  });

  it('shows an error message when loading fails', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
      toggleLike: vi.fn(),
    };
    await setup();

    expect(component.errorMessage()).toBe('שגיאת שרת');
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
      toggleLike: vi.fn(),
    };
    await setup();

    expect(component.target(component.questions()[0])).toBe('דוד כהן');
  });

  it('falls back to the domain label when there is no specific professional', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(of([makeQuestion({ domain: ProfessionalDomain.RABBI })])),
      toggleLike: vi.fn(),
    };
    await setup();

    expect(component.target(component.questions()[0])).toBe('רב/דיין');
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
      toggleLike: vi.fn(),
    };
    await setup();

    const answerEl = fixture.nativeElement.querySelector('.question-answer');
    expect(answerEl?.textContent).toContain('זו תשובת המקצוען לשאלה שלך.');
  });

  it('does not show an answer block for an open question', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(of([makeQuestion({ status: QueryStatus.OPEN })])),
      toggleLike: vi.fn(),
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
      toggleLike: vi.fn(),
    };
    await setup();

    const answerEl = fixture.nativeElement.querySelector('.question-answer');
    expect(answerEl).toBeNull();
  });

  it('shows the like button for a public, answered question', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            is_public: true,
            status: QueryStatus.ANSWERED,
            answer: 'תשובה לשאלה ציבורית',
            like_count: 3,
          }),
        ]),
      ),
      toggleLike: vi.fn(),
    };
    await setup();

    const likeButton = fixture.nativeElement.querySelector('.like-button');
    expect(likeButton?.textContent).toContain('3');
  });

  it('still shows the like button for a public, answered question with no answer text', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            is_public: true,
            status: QueryStatus.ANSWERED,
            answer: null,
            like_count: 1,
          }),
        ]),
      ),
      toggleLike: vi.fn(),
    };
    await setup();

    expect(fixture.nativeElement.querySelector('.like-button')).not.toBeNull();
  });

  it('hides the like button for a private question, even when answered', async () => {
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(
        of([
          makeQuestion({
            is_public: false,
            status: QueryStatus.ANSWERED,
            answer: 'תשובה לשאלה פרטית',
          }),
        ]),
      ),
      toggleLike: vi.fn(),
    };
    await setup();

    expect(fixture.nativeElement.querySelector('.like-button')).toBeNull();
  });

  it('hides the like button for a public question still awaiting an answer', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(of([makeQuestion({ is_public: true, status: QueryStatus.OPEN })])),
      toggleLike: vi.fn(),
    };
    await setup();

    expect(fixture.nativeElement.querySelector('.like-button')).toBeNull();
  });

  it('updates the question in place when a like is toggled', async () => {
    const question = makeQuestion({
      is_public: true,
      status: QueryStatus.ANSWERED,
      answer: 'תשובה לשאלה ציבורית',
      like_count: 2,
      liked_by_me: false,
    });
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(of([question])),
      toggleLike: vi.fn().mockReturnValue(of({ liked: true, like_count: 3 })),
    };
    await setup();

    component.toggleLike(component.questions()[0]);

    expect(professionalServiceMock.toggleLike).toHaveBeenCalledWith('q1');
    expect(component.questions()[0].liked_by_me).toBe(true);
    expect(component.questions()[0].like_count).toBe(3);
  });

  it('flags the affected question when a like toggle fails, without touching its state', async () => {
    const question = makeQuestion({
      is_public: true,
      status: QueryStatus.ANSWERED,
      answer: 'תשובה לשאלה ציבורית',
      like_count: 2,
      liked_by_me: false,
    });
    professionalServiceMock = {
      getMyQuestions: vi.fn().mockReturnValue(of([question])),
      toggleLike: vi.fn().mockReturnValue(throwError(() => ({}))),
    };
    await setup();

    component.toggleLike(component.questions()[0]);

    expect(component.likeErrorId()).toBe('q1');
    expect(component.questions()[0].liked_by_me).toBe(false);
    expect(component.questions()[0].like_count).toBe(2);
  });
});
