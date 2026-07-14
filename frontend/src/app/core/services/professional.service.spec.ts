import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ProfessionalService } from './professional.service';
import { environment } from '../../../environments/environment';
import { ProfessionalDomain } from '../constants';
import type { ProfessionalProfile } from '../models';

describe('ProfessionalService', () => {
  let service: ProfessionalService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProfessionalService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('getProfessionals GETs the professionals catalog', () => {
    let result: ProfessionalProfile[] | undefined;
    service.getProfessionals().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/advice/professionals`);
    expect(req.request.method).toBe('GET');

    const mockList: ProfessionalProfile[] = [
      {
        id: 'p1',
        first_name: 'דוד',
        last_name: 'כהן',
        professional_domain: ProfessionalDomain.LAWYER,
        professional_description: 'עו"ד לדיני משפחה',
      },
    ];
    req.flush(mockList);
    expect(result).toEqual(mockList);
  });
});
