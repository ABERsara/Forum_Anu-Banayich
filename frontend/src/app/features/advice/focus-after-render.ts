/**
 * Moving focus onto an element that is not drawn yet (ABF-163).
 *
 * When a form replaces the button that opened it, the element that had focus
 * leaves the page. Without moving focus into the form, a keyboard or
 * screen-reader user is left on nothing. The form's first field only exists
 * after the next render, so the focus has to wait for it.
 */

import { ElementRef, Injector, afterNextRender, inject } from '@angular/core';

/** Focuses whatever `target` returns once the next render has drawn it. */
export type FocusAfterRender = (target: () => ElementRef<HTMLElement> | undefined) => void;

/**
 * Returns a function that focuses `target()` after the next render.
 *
 * `afterNextRender` needs an injector when it is called outside an injection
 * context, which a click handler always is. Calling this helper from a field
 * initialiser captures that injector once. The component then gets focus
 * handling without injecting `Injector` itself. Pass `injector` to call the
 * helper from somewhere that has no injection context.
 */
export function focusAfterRender(injector: Injector = inject(Injector)): FocusAfterRender {
  return (target) => afterNextRender(() => target()?.nativeElement.focus(), { injector });
}
