import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ErrorDisplayComponent } from './error-display.component';

describe('ErrorDisplayComponent', () => {
  let fixture: ComponentFixture<ErrorDisplayComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ErrorDisplayComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(ErrorDisplayComponent);
  });

  it('should show error div when message is not empty', () => {
    fixture.componentRef.setInput('message', 'שגיאה כלשהי');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.error-display')).toBeTruthy();
  });

  it('should not show error div when message is empty', () => {
    fixture.componentRef.setInput('message', '');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.error-display')).toBeNull();
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    fixture.componentRef.setInput('message', 'שגיאה כלשהי');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.error-display').hasAttribute('dir')).toBe(false);
  });
});
