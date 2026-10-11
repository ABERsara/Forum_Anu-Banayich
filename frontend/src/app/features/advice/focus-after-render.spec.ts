/**
 * focusAfterRender: focus lands on an element that the next render draws,
 * whether the injector comes from the caller's injection context or is passed
 * in by hand.
 */

import { Component, ElementRef, Injector, signal, viewChild } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { focusAfterRender } from './focus-after-render';

@Component({
  standalone: true,
  template: `
    @if (open()) {
      <input #field />
    }
  `,
})
class HostComponent {
  readonly open = signal(false);
  readonly field = viewChild<ElementRef<HTMLInputElement>>('field');
  readonly focus = focusAfterRender();
}

describe('focusAfterRender', () => {
  function setup() {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('focuses an element that only exists after the next render', async () => {
    const fixture = setup();
    const host = fixture.componentInstance;

    host.open.set(true);
    host.focus(host.field);
    await fixture.whenStable();

    expect(document.activeElement).toBe(host.field()?.nativeElement);
  });

  it('takes the injector as an argument outside an injection context', async () => {
    const fixture = setup();
    const host = fixture.componentInstance;
    const focus = focusAfterRender(TestBed.inject(Injector));

    host.open.set(true);
    focus(host.field);
    await fixture.whenStable();

    expect(document.activeElement).toBe(host.field()?.nativeElement);
  });

  it('does nothing when the element is not drawn after all', async () => {
    const fixture = setup();
    const host = fixture.componentInstance;
    const before = document.activeElement;

    host.focus(host.field);
    await fixture.whenStable();

    expect(document.activeElement).toBe(before);
  });
});
