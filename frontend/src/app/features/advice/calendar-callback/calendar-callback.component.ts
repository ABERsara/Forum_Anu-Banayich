import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { MeetingService } from '../../../core/services/meeting.service';
import { AdviceError, NO_ERROR, adviceErrorFrom } from '../advice-error';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** What this page is showing. One of four, never two. */
type CallbackStatus = 'connecting' | 'connected' | 'denied' | 'failed';

/**
 * Where Google returns the browser after the calendar consent screen.
 *
 * The path is not ours to choose: it is the `redirect_uri` registered with the
 * OAuth client (`GOOGLE_REDIRECT_URI_MEET`), and Google refuses any other. The
 * page's whole job is to hand the `code` and `state` it arrived with to
 * `POST /meetings/calendar/connect`, which is authenticated — the server
 * requires the state to have been issued to the caller holding the token, and
 * that is what stops a consent link from being completed by anyone else.
 *
 * Then it clears them out of the address bar. The code is single-use, so a
 * reload of the untouched URL would post a spent code and get a 400 on top of
 * an authorisation that had already succeeded.
 */
@Component({
  selector: 'app-calendar-callback',
  standalone: true,
  imports: [RouterLink, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './calendar-callback.component.html',
  styleUrl: './calendar-callback.component.scss',
})
export class CalendarCallbackComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly meetings = inject(MeetingService);

  readonly status = signal<CallbackStatus>('connecting');
  /** What went wrong, as a key of ours or a sentence the API sent. */
  readonly error = signal<AdviceError>(NO_ERROR);

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const code = params.get('code');
    const oauthState = params.get('state');
    const googleError = params.get('error');

    // Read first, then cleared — including on the paths that never post
    // anything, so a consent screen she declined does not leave `error=` in a
    // URL she might bookmark or share.
    this.stripQueryString();

    if (googleError === 'access_denied') {
      this.status.set('denied');
      return;
    }

    if (googleError || !code || !oauthState) {
      // Any other `error=` Google sends, or a URL that reached this page
      // without the two values the exchange needs.
      this.status.set('failed');
      this.error.set({ key: 'meetings.callback.missing_code', text: '' });
      return;
    }

    this.meetings.connectCalendar(code, oauthState).subscribe({
      next: () => this.status.set('connected'),
      error: (err: unknown) => {
        this.status.set('failed');
        this.error.set(adviceErrorFrom(err, 'meetings.errors.connect_failed'));
      },
    });
  }

  private stripQueryString(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {},
      // Replaced rather than pushed: Back should return her to the screen she
      // started from, not to a URL holding a code that has been spent.
      replaceUrl: true,
    });
  }
}
