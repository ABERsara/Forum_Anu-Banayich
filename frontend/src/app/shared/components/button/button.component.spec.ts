import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ButtonComponent } from './button.component';

describe('ButtonComponent', () => {
  let fixture: ComponentFixture<ButtonComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ButtonComponent] }).compileComponents();

    fixture = TestBed.createComponent(ButtonComponent);
    fixture.detectChanges();
  });

  function button(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('button') as HTMLButtonElement;
  }

  describe('accessible naming', () => {
    it('names the button itself, not the app-button wrapper around it', () => {
      fixture.componentRef.setInput('ariaLabel', 'אישור הבקשה של שרה לוי');
      fixture.detectChanges();

      // The wrapper is not the control a screen reader announces, so a label
      // left on it would be a label nobody hears.
      expect(button().getAttribute('aria-label')).toBe('אישור הבקשה של שרה לוי');
      expect(fixture.nativeElement.getAttribute('aria-label')).toBeNull();
    });

    it('leaves an unlabelled button to its own text', () => {
      expect(button().hasAttribute('aria-label')).toBe(false);
    });
  });

  describe('as a disclosure button', () => {
    it('reports the panel it controls as open or closed', () => {
      fixture.componentRef.setInput('ariaExpanded', false);
      fixture.componentRef.setInput('ariaControls', 'registration-detail-u1');
      fixture.detectChanges();

      expect(button().getAttribute('aria-expanded')).toBe('false');
      expect(button().getAttribute('aria-controls')).toBe('registration-detail-u1');

      fixture.componentRef.setInput('ariaExpanded', true);
      fixture.detectChanges();

      expect(button().getAttribute('aria-expanded')).toBe('true');
    });

    it('carries no disclosure state on a button that discloses nothing', () => {
      expect(button().hasAttribute('aria-expanded')).toBe(false);
      expect(button().hasAttribute('aria-controls')).toBe(false);
    });
  });
});
