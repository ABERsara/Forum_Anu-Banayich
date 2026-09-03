import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';

import { PendingApprovalComponent } from './pending.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('PendingApprovalComponent', () => {
  let fixture: ComponentFixture<PendingApprovalComponent>;
  let component: PendingApprovalComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PendingApprovalComponent, translocoTesting()],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(PendingApprovalComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('reads exactly as it did before the keys went in', () => {
    expect(fixture.nativeElement.querySelector('h1').textContent.trim()).toBe('הרשמתך התקבלה');
    expect(text()).toContain('הרשמתך התקבלה ואישורך נמצא בבדיקה, תקבל/י על כך הודעה באימייל.');
    expect(text()).toContain('חזרה למסך הכניסה');
  });

  it('is fully translated in English', () => {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('h1').textContent.trim()).toBe(
      'Your registration was received',
    );
    expect(text()).toContain('Back to the login screen');
    expect(text()).not.toMatch(HEBREW);
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    expect(fixture.nativeElement.querySelector('.pending-container').hasAttribute('dir')).toBe(
      false,
    );
  });
});
