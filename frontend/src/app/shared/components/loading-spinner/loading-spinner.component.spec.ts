import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LoadingSpinnerComponent } from './loading-spinner.component';

describe('LoadingSpinnerComponent', () => {
  let fixture: ComponentFixture<LoadingSpinnerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoadingSpinnerComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(LoadingSpinnerComponent);
  });

  it('should show message when message is not empty', () => {
    fixture.componentRef.setInput('message', 'טוען...');
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.spinner-message');
    expect(el).toBeTruthy();
    expect(el.textContent).toContain('טוען...');
  });

  it('should not show message when message is empty', () => {
    fixture.componentRef.setInput('message', '');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.spinner-message')).toBeNull();
  });
});
