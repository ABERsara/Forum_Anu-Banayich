import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { BroadcastComponent } from './broadcast.component';
import { AdminService } from '../../../core/services/admin.service';
import { ForumPost } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('BroadcastComponent', () => {
  let fixture: ComponentFixture<BroadcastComponent>;
  let component: BroadcastComponent;
  let sendBroadcastMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    sendBroadcastMock = vi.fn();

    await TestBed.configureTestingModule({
      imports: [BroadcastComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: AdminService, useValue: { sendBroadcast: sendBroadcastMock } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(BroadcastComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should show field errors when submitting an empty form', () => {
    component.onSubmit();
    fixture.detectChanges();

    const errors = fixture.nativeElement.querySelectorAll('.field-error');
    expect(errors.length).toBeGreaterThan(0);
    expect(sendBroadcastMock).not.toHaveBeenCalled();
  });

  it('should call AdminService.sendBroadcast with the form values on submit', () => {
    sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();

    expect(sendBroadcastMock).toHaveBeenCalledWith({
      title: 'הודעה חשובה',
      content: 'תוכן ההודעה',
    });
  });

  it('should show a success message and reset the form after a successful send', () => {
    sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.successKey()).toBe('admin.broadcast.success');
    expect(component.isLoading()).toBe(false);
    expect(component.form.value.title).toBeFalsy();
  });

  it('should show the sentence the server sent and hide the spinner on error', () => {
    sendBroadcastMock.mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } })));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: '', text: 'שגיאת שרת' });
    expect(fixture.nativeElement.textContent).toContain('שגיאת שרת');
    expect(component.isLoading()).toBe(false);
    expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeNull();
  });

  /** No `detail` — a network failure, say — so our own key carries the message. */
  it('should fall back to our own key when the server sent no detail', () => {
    sendBroadcastMock.mockReturnValue(throwError(() => ({})));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: 'admin.errors.broadcast_failed', text: '' });
    expect(fixture.nativeElement.textContent).toContain('שגיאה בשליחת השידור.');
  });

  it('should clear the previous outcome when a new send starts', () => {
    sendBroadcastMock.mockReturnValue(throwError(() => ({})));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });
    component.onSubmit();

    sendBroadcastMock.mockReturnValue(new Subject());
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });
    component.onSubmit();

    expect(component.error()).toEqual({ key: '', text: '' });
    expect(component.successKey()).toBe('');
  });

  it('should disable submit button while loading', () => {
    sendBroadcastMock.mockReturnValue(new Subject());
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    const btn = fixture.nativeElement.querySelector('.btn-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('.broadcast-title').textContent.trim();
    }

    function placeholderOf(selector: string): string {
      return (fixture.nativeElement.querySelector(selector) as HTMLElement).getAttribute(
        'placeholder',
      )!;
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /** Submits an empty form, so the two validation messages are on screen. */
    function showValidationErrors(): void {
      component.onSubmit();
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', () => {
      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('שידור לכלל המשתמשים');
      expect(text()).toContain(
        'הפוסט יופיע ברשימת הפורום של כל המשתמשים הפעילים, ללא קשר לקבוצה או מגזר.',
      );
      expect(text()).toContain('כותרת');
      expect(text()).toContain('תוכן');
      expect(text()).toContain('שלח שידור');
      expect(placeholderOf('#title')).toBe('כותרת השידור');
      expect(placeholderOf('#content')).toBe('תוכן ההודעה');
    });

    it('leaves no Hebrew on the page in English', () => {
      switchToEnglish();

      expect(text()).toContain('Back to the dashboard');
      expect(heading()).toBe('Broadcast to all users');
      expect(text()).toContain(
        'The post will appear in the forum list of every active user, regardless of group or sector.',
      );
      expect(text()).toContain('Send broadcast');
      expect(placeholderOf('#title')).toBe('Broadcast title');
      expect(placeholderOf('#content')).toBe('Message content');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Read off the rendered messages, not the static labels beside them. */
    it('translates the validation messages the form actually shows', () => {
      showValidationErrors();
      expect(text()).toContain('נא להזין כותרת (2 עד 256 תווים)');
      expect(text()).toContain('נא להזין תוכן (עד 5000 תווים)');

      switchToEnglish();

      expect(text()).toContain('Please enter a title (2 to 256 characters)');
      expect(text()).toContain('Please enter content (up to 5000 characters)');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while the send is in flight', () => {
      sendBroadcastMock.mockReturnValue(new Subject());
      component.form.setValue({ title: 'Important notice', content: 'Body of the notice' });
      component.onSubmit();
      fixture.detectChanges();
      expect(text()).toContain('שולח שידור...');

      switchToEnglish();

      expect(text()).toContain('Sending broadcast...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a message already on screen follows the switch. */
    it('re-renders the confirmation in the new language', () => {
      sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
      component.form.setValue({ title: 'Important notice', content: 'Body of the notice' });
      component.onSubmit();
      fixture.detectChanges();
      expect(text()).toContain('השידור נשלח בהצלחה לכלל המשתמשים.');

      switchToEnglish();

      expect(text()).toContain('The broadcast was sent to all users.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('re-renders our own failure copy in the new language', () => {
      sendBroadcastMock.mockReturnValue(throwError(() => ({})));
      component.form.setValue({ title: 'Important notice', content: 'Body of the notice' });
      component.onSubmit();
      fixture.detectChanges();
      expect(text()).toContain('שגיאה בשליחת השידור.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong sending the broadcast.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', () => {
      sendBroadcastMock.mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } })));
      component.form.setValue({ title: 'Important notice', content: 'Body of the notice' });
      component.onSubmit();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('שגיאת שרת');
    });

    /**
     * The ticket asks which half of this screen is content and which is UI. The
     * answer is in the payload: what the admin types is posted verbatim to
     * `/forum/broadcast` and read as a forum post, so it is content — it is not
     * translated, and it does not move when the interface language does.
     */
    it('leaves what the admin typed alone when the language changes', () => {
      component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });
      fixture.detectChanges();

      switchToEnglish();

      const title = fixture.nativeElement.querySelector('#title') as HTMLInputElement;
      const content = fixture.nativeElement.querySelector('#content') as HTMLTextAreaElement;
      expect(title.value).toBe('הודעה חשובה');
      expect(content.value).toBe('תוכן ההודעה');

      sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
      component.onSubmit();

      expect(sendBroadcastMock).toHaveBeenCalledWith({
        title: 'הודעה חשובה',
        content: 'תוכן ההודעה',
      });
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      const page = fixture.nativeElement.querySelector('.broadcast-page') as HTMLElement;

      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
