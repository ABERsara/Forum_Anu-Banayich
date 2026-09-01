/**
 * The public Q&A feed is still a stub: `getPublicQA()` is unimplemented and the
 * body of the page is a TODO placeholder. Only its heading and its back link
 * are real UI, and this spec pins those two through a language switch, so the
 * screen is already migrated when whoever implements the feed arrives.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';

import { QaFeedComponent } from './qa-feed.component';
import { ProfessionalService } from '../../../core/services/professional.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('QaFeedComponent', () => {
  let fixture: ComponentFixture<QaFeedComponent>;

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function heading(): string {
    return fixture.nativeElement.querySelector('h1').textContent.trim();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QaFeedComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        // The feed never calls the service yet, but the component injects it,
        // and the real one would reach for HttpClient.
        { provide: ProfessionalService, useValue: {} },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(QaFeedComponent);
    fixture.detectChanges();
  });

  it('reads in Hebrew exactly as it did before the keys went in', () => {
    expect(heading()).toBe('שאלות ותשובות קהילתיות');
    expect(text()).toContain('חזרה לייעוץ מקצועי');
  });

  it('leaves no Hebrew on the page in English', () => {
    switchToEnglish();

    expect(heading()).toBe('Community questions and answers');
    expect(text()).toContain('Back to professional advice');
    expect(text()).not.toMatch(HEBREW);
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    const page = fixture.nativeElement.querySelector('div') as HTMLElement;

    expect(page.hasAttribute('dir')).toBe(false);
    expect(page.style.direction).toBe('');
  });
});
