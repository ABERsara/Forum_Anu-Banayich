/**
 * The association's standing notice that an AI agent is not a professional
 * advisor (SPEC §12: "Disclaimer קבוע בממשק").
 *
 * **The one shared component that holds its own text, and on purpose.**
 * CONTRIBUTING §6 has the rule the other way round — a shared component takes
 * translated text and the key belongs to the caller — because `app-card` and
 * `app-error-display` render whatever they are handed and have no opinion
 * about it. This one is the opposite: the sentence *is* the component. Giving
 * a caller an input to override it would turn "every agent screen shows the
 * same disclaimer" from a guarantee into a convention, which is the same
 * argument `agent_service._compose_answer()` makes for concatenating the
 * server-side disclaimer onto every answer instead of asking the model for
 * one. The dialogs' defaults (`shared.confirm_dialog.*`) are the precedent for
 * a shared component owning a `shared.*` key; this one simply has no override.
 *
 * **`role="alert"`.** The banner is not a reaction to anything — it is there
 * before the member types and stays there — so most of the time it announces
 * nothing, exactly as the live regions in `features/messages/chat` document. It
 * earns the role at the one moment that matters: the component is inserted into
 * the DOM when the chat route renders, and a region that arrives carrying text
 * is announced on arrival. That is the moment a member is owed the sentence —
 * on entering the conversation, before the first answer, not after it.
 *
 * **No `dir`.** The ticket asked for `dir="rtl"`; CONTRIBUTING §6 forbids it
 * and `core/i18n/direction.spec.ts` fails the build over it. The requirement
 * behind it predates ABF-126: direction now comes from `<html dir>`, which
 * `LocaleService` sets from the active language, so the banner is right-to-left
 * in Hebrew and left-to-right in English without naming a side — which is more
 * than the hard-coded attribute would have given it.
 */

import { Component } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-disclaimer-banner',
  imports: [TranslocoPipe],
  template: `
    <p class="disclaimer-banner" role="alert">
      <span class="disclaimer-banner__icon" aria-hidden="true">ℹ</span>
      <span>{{ 'shared.disclaimer.agent' | transloco }}</span>
    </p>
  `,
  styleUrl: './disclaimer-banner.component.scss',
})
export class DisclaimerBannerComponent {}
