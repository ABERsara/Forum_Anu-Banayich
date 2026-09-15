/**
 * Sends the UI's active language to our API on every request (ABF-137).
 *
 * The backend now answers 4xx, 422 and success messages in the language the
 * request asks for. Without this interceptor that language would be whatever
 * the *browser* puts in `Accept-Language` — a header it attaches to every XHR
 * on its own, and one that says which locale Chrome was installed in, not
 * which language the member picked in our header.
 *
 * Those two disagree constantly. A member reading the site in Hebrew from an
 * English-language browser (`en-US,en;q=0.9`) would get English sentences
 * inside a Hebrew RTL screen, because `screenErrorFrom` shows the API's
 * `detail` as finished prose rather than running it through Transloco. The
 * language the API answers in has to follow `LocaleService`, which is the one
 * place that knows what the member actually chose.
 *
 * `Accept-Language` is not a forbidden header name, so script may set it, and
 * it is CORS-safelisted, so overriding it adds no preflight.
 *
 * **The URL check comes before `inject()`, deliberately.** Transloco fetches
 * its own `/i18n/*.json` through `HttpClient`, so an interceptor that injected
 * `LocaleService` unconditionally could be asked for it while `LocaleService`
 * is still being constructed — a circular dependency on the very first load.
 * Returning early on anything that is not our API keeps that unreachable, and
 * is the right behaviour anyway: another origin's response language is not
 * ours to choose.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { LocaleService } from '../services/locale.service';
import { environment } from '../../../environments/environment';

export const languageInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(environment.apiUrl)) return next(req);

  const locale = inject(LocaleService);
  return next(req.clone({ setHeaders: { 'Accept-Language': locale.lang() } }));
};
