import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AdviceListComponent } from './advice-list.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ProfessionalDomain } from '../../../core/constants';
import type { ProfessionalProfile } from '../../../core/models';

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
      imports: [AdviceListComponent],
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
});
