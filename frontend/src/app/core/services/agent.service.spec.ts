/**
 * The three member-facing agent calls, against `HttpTestingController`.
 *
 * What is worth asserting here is the shape of the *request*, because that is
 * the half the backend contract fixes and the half a component cannot check:
 * the path an agent id is spliced into, and whether `conversation_id` is on
 * the body at all — the difference between continuing a thread and silently
 * opening a new one on every question.
 */

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AgentService } from './agent.service';
import { environment } from '../../../environments/environment';
import { AgentMessageRole, ProfessionalDomain } from '../constants';
import type { AgentChatResponse, AgentConversation, AgentDomain } from '../models';

const DOMAIN: AgentDomain = {
  id: 'domain-1',
  name: 'זכויות חד-הוריות',
  description: 'מידע על זכויות והטבות למשפחות חד-הוריות',
  professional_domain: ProfessionalDomain.LAWYER,
};

const QUESTION = {
  id: 'm1',
  role: AgentMessageRole.USER,
  content: 'מה מגיע לי?',
  created_at: '2026-09-15T10:00:00',
};

const ANSWER = {
  id: 'm2',
  role: AgentMessageRole.AGENT,
  content: 'על פי בסיס הידע...',
  created_at: '2026-09-15T10:00:05',
};

describe('AgentService', () => {
  let service: AgentService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AgentService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  describe('getDomains', () => {
    it('GETs the member-facing catalog', () => {
      let result: AgentDomain[] | undefined;
      service.getDomains().subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/agents`);
      expect(req.request.method).toBe('GET');

      req.flush([DOMAIN]);
      expect(result).toEqual([DOMAIN]);
    });

    /**
     * The server filters by group/sector and can legitimately find nothing.
     * An empty catalog is a state the screen renders, not a failure.
     */
    it('passes an empty catalog through as an empty list', () => {
      let result: AgentDomain[] | undefined;
      service.getDomains().subscribe((res) => (result = res));

      httpMock.expectOne(`${environment.apiUrl}/agents`).flush([]);
      expect(result).toEqual([]);
    });
  });

  describe('chat', () => {
    it('POSTs the question to the agent named in the path', () => {
      let result: AgentChatResponse | undefined;
      service.chat('domain-1', 'מה מגיע לי?').subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/agents/domain-1/chat`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ message: 'מה מגיע לי?' });

      const response: AgentChatResponse = {
        conversation_id: 'c1',
        question: QUESTION,
        answer: ANSWER,
        sources: [{ title: 'חוק המזונות', source_name: 'ספר החוקים', source_url: null }],
      };
      req.flush(response);
      expect(result).toEqual(response);
    });

    /**
     * The field has to be *absent*, not null: the schema types it
     * `str | None` with a length bound, and "start a new thread" is the
     * absence of it. A `conversation_id: null` on the wire would be a second,
     * undocumented spelling of the same thing.
     */
    it('leaves conversation_id off the body when no thread is open', () => {
      service.chat('domain-1', 'שאלה ראשונה').subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/agents/domain-1/chat`);
      expect('conversation_id' in (req.request.body as object)).toBe(false);
    });

    it('sends conversation_id on a follow-up, so the agent sees what came before', () => {
      service.chat('domain-1', 'וכמה זה בערך?', 'c1').subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/agents/domain-1/chat`);
      expect(req.request.body).toEqual({ message: 'וכמה זה בערך?', conversation_id: 'c1' });
    });

    /** The daily quota is a 429 with the server's own sentence in `detail`. */
    it('surfaces the server error rather than swallowing it', () => {
      let status: number | undefined;
      let detail: string | undefined;
      service.chat('domain-1', 'שאלה').subscribe({
        error: (err) => {
          status = err.status;
          detail = err.error?.detail;
        },
      });

      httpMock
        .expectOne(`${environment.apiUrl}/agents/domain-1/chat`)
        .flush(
          { detail: 'הגעת למכסת ההודעות היומית לסוכנים (30 ביממה). אפשר להמשיך מחר.' },
          { status: 429, statusText: 'Too Many Requests' },
        );

      expect(status).toBe(429);
      expect(detail).toContain('מכסת ההודעות היומית');
    });
  });

  describe('getConversation', () => {
    it('GETs the thread under the agent it belongs to', () => {
      let result: AgentConversation | undefined;
      service.getConversation('domain-1', 'c1').subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/agents/domain-1/conversations/c1`);
      expect(req.request.method).toBe('GET');

      const conversation: AgentConversation = {
        id: 'c1',
        domain_id: 'domain-1',
        started_at: '2026-09-15T10:00:00',
        last_message_at: '2026-09-15T10:00:05',
        messages: [QUESTION, ANSWER],
      };
      req.flush(conversation);
      expect(result).toEqual(conversation);
    });
  });
});
