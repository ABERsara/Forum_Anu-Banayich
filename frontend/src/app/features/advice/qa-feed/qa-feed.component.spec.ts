import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { QaFeedComponent } from './qa-feed.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain } from '../../../core/constants';
import type { PublicQA } from '../../../core/models';
import { translocoTesting } from '../../../../testing/transloco-testing';

function makeItem(overrides: Partial<PublicQA> = {}): PublicQA {
  return {
    id: 'q1',
    content: 'שאלה ציבורית לדוגמה',
    answer: 'תשובה ציבורית לדוגמה',
    domain: ProfessionalDomain.LAWYER,
    is_featured: false,
    answered_at: '2026-07-14T10:00:00',
    like_count: 0,
    liked_by_me: false,
    professional: {
      id: 'pro1',
      first_name: 'משה',
      last_name: 'כהן',
      professional_domain: ProfessionalDomain.LAWYER,
      professional_description: null,
    },
    asker_alias: 'אלמנה – ספרדי',
    asker: null,
    ...overrides,
  };
}

describe('QaFeedComponent', () => {
  let fixture: ComponentFixture<QaFeedComponent>;
  let component: QaFeedComponent;
  let professionalServiceMock: {
    getPublicQA: ReturnType<typeof vi.fn>;
    toggleLike: ReturnType<typeof vi.fn>;
  };

  async function setup(): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [QaFeedComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ProfessionalService, useValue: professionalServiceMock },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(QaFeedComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  beforeEach(() => {
    professionalServiceMock = {
      getPublicQA: vi.fn().mockReturnValue(of([makeItem()])),
      toggleLike: vi.fn(),
    };
  });

  it('loads the feed on init', async () => {
    await setup();

    expect(professionalServiceMock.getPublicQA).toHaveBeenCalledWith(undefined, 1, 20);
    expect(component.isLoading()).toBe(false);
    expect(component.items().length).toBe(1);
  });

  it('shows the answering professional by name', async () => {
    await setup();

    expect(component.professionalName(component.items()[0])).toBe('משה כהן');
  });

  it('hides the answered-by attribution for a domain question with no professional attached', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(of([makeItem({ professional: null })]));
    await setup();

    expect(component.professionalName(component.items()[0])).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('תשובה מאת');
  });

  it('falls back to the anonymized alias when the asker did not opt in', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(
      of([makeItem({ asker: null, asker_alias: 'אלמנה – ספרדי' })]),
    );
    await setup();

    expect(component.askerName(component.items()[0])).toBe('אלמנה – ספרדי');
  });

  it('shows the asker by real name once they opted in', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(
      of([makeItem({ asker: { id: 'u1', first_name: 'שרה', last_name: 'לוי' } })]),
    );
    await setup();

    expect(component.askerName(component.items()[0])).toBe('שרה לוי');
  });

  it('shows a generic error state when loading fails', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(
      throwError(() => ({ error: { detail: 'unexpected backend error' } })),
    );

    await setup();

    expect(component.hasError()).toBe(true);
    expect(component.errorKey()).toBe('errors.generic');
    expect(component.isLoading()).toBe(false);
  });

  it('re-fetches from the server with the chosen domain, not a client-side filter', async () => {
    await setup();
    professionalServiceMock.getPublicQA.mockReturnValue(of([]));

    component.onDomainChange({
      target: { value: ProfessionalDomain.ACCOUNTANT },
    } as unknown as Event);

    expect(professionalServiceMock.getPublicQA).toHaveBeenCalledWith(
      ProfessionalDomain.ACCOUNTANT,
      1,
      20,
    );
  });

  it('ignores a stale response from a superseded domain change', async () => {
    const firstRequest = new Subject<PublicQA[]>();
    const secondRequest = new Subject<PublicQA[]>();
    professionalServiceMock.getPublicQA
      .mockReturnValueOnce(of([makeItem({ id: 'initial' })])) // ngOnInit's load
      .mockReturnValueOnce(firstRequest.asObservable())
      .mockReturnValueOnce(secondRequest.asObservable());
    await setup();

    component.onDomainChange({
      target: { value: ProfessionalDomain.LAWYER },
    } as unknown as Event);
    component.onDomainChange({
      target: { value: ProfessionalDomain.ACCOUNTANT },
    } as unknown as Event);

    // The newer (second) request resolves first...
    secondRequest.next([makeItem({ id: 'accountant-result' })]);
    // ...then the older, now-superseded request resolves late. It must be
    // ignored rather than overwriting the newer result.
    firstRequest.next([makeItem({ id: 'lawyer-result' })]);

    expect(component.items().map((item) => item.id)).toEqual(['accountant-result']);
  });

  it('hides "load more" when the last page came back shorter than the page size', async () => {
    await setup();

    expect(component.hasMore()).toBe(false);
  });

  it('shows "load more" and appends the next page when a full page came back', async () => {
    const fullPage = Array.from({ length: 20 }, (_, i) => makeItem({ id: `q${i}` }));
    professionalServiceMock.getPublicQA.mockReturnValue(of(fullPage));
    await setup();

    expect(component.hasMore()).toBe(true);

    professionalServiceMock.getPublicQA.mockReturnValue(of([makeItem({ id: 'q-next' })]));
    component.loadMore();

    expect(professionalServiceMock.getPublicQA).toHaveBeenLastCalledWith(undefined, 2, 20);
    expect(component.items().length).toBe(21);
    expect(component.hasMore()).toBe(false);
  });

  it('updates the item in place when a like is toggled', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(
      of([makeItem({ like_count: 2, liked_by_me: false })]),
    );
    professionalServiceMock.toggleLike.mockReturnValue(of({ liked: true, like_count: 3 }));
    await setup();

    component.toggleLike(component.items()[0]);

    expect(professionalServiceMock.toggleLike).toHaveBeenCalledWith('q1');
    expect(component.items()[0].liked_by_me).toBe(true);
    expect(component.items()[0].like_count).toBe(3);
  });

  it('flags only the affected item when a like toggle fails, without touching its state', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(
      of([makeItem({ id: 'q1', like_count: 2, liked_by_me: false })]),
    );
    professionalServiceMock.toggleLike.mockReturnValue(throwError(() => ({})));
    await setup();

    component.toggleLike(component.items()[0]);

    expect(component.likeErrorId()).toBe('q1');
    expect(component.items()[0].liked_by_me).toBe(false);
    expect(component.items()[0].like_count).toBe(2);
  });

  it('clears the previous like error once a new toggle is attempted', async () => {
    professionalServiceMock.getPublicQA.mockReturnValue(of([makeItem({ id: 'q1' })]));
    professionalServiceMock.toggleLike.mockReturnValue(throwError(() => ({})));
    await setup();
    component.toggleLike(component.items()[0]);
    expect(component.likeErrorId()).toBe('q1');

    professionalServiceMock.toggleLike.mockReturnValue(of({ liked: true, like_count: 1 }));
    component.toggleLike(component.items()[0]);

    expect(component.likeErrorId()).toBeNull();
  });
});
