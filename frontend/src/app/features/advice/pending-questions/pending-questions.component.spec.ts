import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { PendingQuestionsComponent } from './pending-questions.component';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

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
    expect(component.errorMessage()).toBe('');
    expect(component.questions().length).toBe(1);
  });

  it('shows an error message when loading fails', async () => {
    mockService({
      getPendingQuestions: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
    });
    await setup();

    expect(component.errorMessage()).toBe('שגיאת שרת');
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
    expect(component.successMessage()).not.toBe('');
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

    expect(component.errorMessage()).toBe('השאלה כבר נענתה.');
    expect(component.questions().length).toBe(1);
    expect(component.submittingId()).toBeNull();
  });
});
