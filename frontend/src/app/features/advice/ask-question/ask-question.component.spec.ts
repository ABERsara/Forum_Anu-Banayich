import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AskQuestionComponent } from './ask-question.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain, QueryStatus } from '../../../core/constants';
import type { ProfessionalQuery } from '../../../core/models';

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
      imports: [AskQuestionComponent],
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
    component.form.setValue({
      content: 'זוהי שאלה תקינה עם תוכן מספיק',
      is_public: false,
      show_real_name: false,
      domain: ProfessionalDomain.RABBI,
    });

    component.onSubmit();

    expect(component.errorMessage()).toBe('שגיאה מהשרת');
    expect(component.isLoading()).toBe(false);
  });
});
