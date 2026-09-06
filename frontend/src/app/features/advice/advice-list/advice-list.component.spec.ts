import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AdviceListComponent } from './advice-list.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain } from '../../../core/constants';
import type { ProfessionalProfile } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeProfessional(overrides: Partial<ProfessionalProfile> = {}): ProfessionalProfile {
  return {
    id: 'p1',
    first_name: 'דוד',
    last_name: 'כהן',
    professional_domain: ProfessionalDomain.LAWYER,
    professional_description: 'עו"ד לדיני משפחה',
    ...overrides,
  };
}

/**
 * A professional whose own words carry no Hebrew.
 *
 * A professional's name and the description they wrote about themselves are
 * user-generated content — out of scope for ABF-131 and never translated.
 * Feeding Latin content to the `HEBREW` sweeps below keeps them pointed at the
 * UI copy, which is the thing they are meant to guard.
 */
function makeLatinProfessional(overrides: Partial<ProfessionalProfile> = {}): ProfessionalProfile {
  return makeProfessional({
    first_name: 'David',
    last_name: 'Cohen',
    professional_description: 'Family law',
    ...overrides,
  });
}

describe('AdviceListComponent', () => {
  let fixture: ComponentFixture<AdviceListComponent>;
  let component: AdviceListComponent;
  let professionalServiceMock: { getProfessionals: ReturnType<typeof vi.fn> };

  function setup(): void {
    fixture = TestBed.createComponent(AdviceListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  beforeEach(async () => {
    professionalServiceMock = {
      getProfessionals: vi.fn().mockReturnValue(of([makeProfessional()])),
    };

    await TestBed.configureTestingModule({
      imports: [AdviceListComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ProfessionalService, useValue: professionalServiceMock },
      ],
    }).compileComponents();
  });

  it('loads professionals on init', () => {
    setup();

    expect(professionalServiceMock.getProfessionals).toHaveBeenCalled();
    expect(component.isLoading()).toBe(false);
    expect(component.isError()).toBe(false);
    expect(component.professionals().length).toBe(1);
    expect(component.filteredProfessionals().length).toBe(1);
  });

  it('sets isError when loading fails', () => {
    professionalServiceMock.getProfessionals.mockReturnValue(throwError(() => ({})));

    setup();

    expect(component.isError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when there are no professionals', () => {
    professionalServiceMock.getProfessionals.mockReturnValue(of([]));

    setup();
    fixture.detectChanges();

    expect(component.filteredProfessionals().length).toBe(0);
    expect(fixture.nativeElement.textContent).toContain('לא נמצאו אנשי מקצוע זמינים');
  });

  it('does not render contact details (privacy rule)', () => {
    setup();
    fixture.detectChanges();

    const cardText = fixture.nativeElement.textContent as string;
    expect(cardText).not.toContain('@');
  });

  it('filters professionals by domain on the client side', () => {
    const lawyer = makeProfessional({ id: 'p1', professional_domain: ProfessionalDomain.LAWYER });
    const accountant = makeProfessional({
      id: 'p2',
      professional_domain: ProfessionalDomain.ACCOUNTANT,
    });
    professionalServiceMock.getProfessionals.mockReturnValue(of([lawyer, accountant]));

    setup();
    component.onDomainChange({
      target: { value: ProfessionalDomain.ACCOUNTANT },
    } as unknown as Event);

    expect(component.filteredProfessionals()).toEqual([accountant]);
  });

  it('resets the filter when domain is cleared', () => {
    const lawyer = makeProfessional({ id: 'p1', professional_domain: ProfessionalDomain.LAWYER });
    const accountant = makeProfessional({
      id: 'p2',
      professional_domain: ProfessionalDomain.ACCOUNTANT,
    });
    professionalServiceMock.getProfessionals.mockReturnValue(of([lawyer, accountant]));

    setup();
    component.onDomainChange({
      target: { value: ProfessionalDomain.ACCOUNTANT },
    } as unknown as Event);
    component.onDomainChange({ target: { value: '' } } as unknown as Event);

    expect(component.filteredProfessionals().length).toBe(2);
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

    /** Re-renders the list against a different service response. */
    function renderWith(response: Observable<ProfessionalProfile[]>): void {
      professionalServiceMock.getProfessionals.mockReturnValue(response);
      setup();
    }

    it('reads in Hebrew exactly as it did before the keys went in', () => {
      setup();

      expect(heading()).toBe('ייעוץ מקצועי');
      expect(text()).toContain('לשאלות ותשובות ציבוריות');
      expect(text()).toContain('השאלות שלי');
      expect(text()).toContain('סינון לפי תחום:');
      expect(text()).toContain('הכל');
      expect(text()).toContain('שאל/י שאלה');
      expect(text()).toContain('עו"ד');
    });

    it('leaves no Hebrew on the page in English', () => {
      renderWith(of([makeLatinProfessional()]));

      switchToEnglish();

      expect(heading()).toBe('Professional advice');
      expect(text()).toContain('Public questions and answers');
      expect(text()).toContain('My questions');
      expect(text()).toContain('Filter by field:');
      expect(text()).toContain('All');
      expect(text()).toContain('Ask a question');
      expect(text()).toContain('Lawyer');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the loading copy', () => {
      renderWith(NEVER);
      expect(text()).toContain('טוען...');

      switchToEnglish();

      expect(text()).toContain('Loading...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', () => {
      renderWith(of([]));
      expect(text()).toContain('לא נמצאו אנשי מקצוע זמינים.');

      switchToEnglish();

      expect(text()).toContain('No professionals are available.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The failure is copy of ours, piped in the template, so it follows the switch. */
    it('re-renders a load failure that is already on screen', () => {
      renderWith(throwError(() => ({})));
      expect(text()).toContain('אירעה שגיאה בטעינת רשימת אנשי המקצוע. נסה שוב מאוחר יותר.');

      switchToEnglish();

      expect(text()).toContain(
        'Something went wrong loading the professionals list. Please try again later.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    /** The domain filter's options belong to `constants.*` (ABF-127), not to this module. */
    it('lists the filter options in the active language', () => {
      renderWith(of([makeLatinProfessional()]));
      const options = () =>
        Array.from(
          (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLOptionElement>(
            '.filter-bar option',
          ),
        ).map((option) => option.textContent?.trim());

      expect(options()).toEqual([
        'הכל',
        'עו"ד',
        'רואה חשבון',
        'פסיכולוג',
        'יועץ כלכלי',
        'רב/דיין',
        'רפואה',
        'סוציאל וורקר',
        'אחר',
      ]);

      switchToEnglish();

      expect(options()).toEqual([
        'All',
        'Lawyer',
        'Accountant',
        'Psychologist',
        'Financial advisor',
        'Rabbi / Dayan',
        'Medicine',
        'Social worker',
        'Other',
      ]);
    });

    /** A professional's own words are content, not UI: they survive the switch. */
    it('leaves what a professional wrote about themselves alone', () => {
      renderWith(of([makeProfessional()]));

      switchToEnglish();

      expect(text()).toContain('דוד כהן');
      expect(text()).toContain('עו"ד לדיני משפחה');
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup();

      expect(fixture.nativeElement.querySelector('.page').hasAttribute('dir')).toBe(false);
    });
  });
});
