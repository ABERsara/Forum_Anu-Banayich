import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { LoadingSpinnerComponent } from './loading-spinner.component';
import { translocoTesting } from '../../../../testing/transloco-testing';

describe('LoadingSpinnerComponent', () => {
  let fixture: ComponentFixture<LoadingSpinnerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoadingSpinnerComponent, translocoTesting()],
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

  /**
   * The spinner has no visible text of its own, so this label is the only
   * thing a screen reader gets from it. It used to be a hardcoded English
   * "Loading..." sitting in an otherwise Hebrew page.
   */
  it('announces itself in the active language', () => {
    fixture.detectChanges();
    const spinner = fixture.nativeElement.querySelector('.spinner') as HTMLElement;
    expect(spinner.getAttribute('aria-label')).toBe('טוען...');

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(spinner.getAttribute('aria-label')).toBe('Loading...');
  });
});
