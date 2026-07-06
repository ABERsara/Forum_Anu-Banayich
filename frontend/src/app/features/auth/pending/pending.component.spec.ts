import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PendingApprovalComponent } from './pending.component';

describe('PendingApprovalComponent', () => {
  let fixture: ComponentFixture<PendingApprovalComponent>;
  let component: PendingApprovalComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PendingApprovalComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(PendingApprovalComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
