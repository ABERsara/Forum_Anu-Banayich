import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { MyQuestionsComponent } from './my-questions.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';

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

describe('MyQuestionsComponent', () => {
  let fixture: ComponentFixture<MyQuestionsComponent>;
  let component: MyQuestionsComponent;
  let professionalServiceMock: { getMyQuestions: ReturnType<typeof vi.fn> };

  async function setup(): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [MyQuestionsComponent],
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
    expect(component.errorMessage()).toBe('');
    expect(component.questions.length).toBe(1);
  });

  it('shows an error message when loading fails', async () => {
    professionalServiceMock = {
      getMyQuestions: vi
        .fn()
        .mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } }))),
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
});
