import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ForumService, buildConversationKey } from './forum.service';
import { environment } from '../../../environments/environment';
import { GroupVisibility, PostStatus, SectorVisibility } from '../constants';
import type { DirectMessage, ForumPost, ForumPostList, UserPublic } from '../models';

const MOCK_POST: ForumPost = {
  id: 'post-1',
  title: 'כותרת',
  content: 'תוכן',
  group_visibility: GroupVisibility.WIDOWS,
  sector_visibility: SectorVisibility.HASIDIC,
  status: PostStatus.VISIBLE,
  report_count: 0,
  author: { id: 'user-1', first_name: 'שרה', last_name: 'לוי' },
  attachment_url: null,
  created_at: '2026-07-14T00:00:00',
  updated_at: '2026-07-14T00:00:00',
};

describe('ForumService', () => {
  let service: ForumService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ForumService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('getPosts GETs the forum posts endpoint with default page and page_size', () => {
    let result: ForumPostList | undefined;
    service.getPosts().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts?page=1&page_size=20`);
    expect(req.request.method).toBe('GET');

    const mockList: ForumPostList = { items: [], total: 0, page: 1, page_size: 20 };
    req.flush(mockList);
    expect(result).toEqual(mockList);
  });

  it('getPosts GETs with the given page and pageSize', () => {
    service.getPosts(3, 10).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts?page=3&page_size=10`);
    expect(req.request.method).toBe('GET');
    req.flush({ items: [], total: 0, page: 3, page_size: 10 });
  });

  it('getPost GETs the single post endpoint by id', () => {
    let result: ForumPost | undefined;
    service.getPost('post-1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts/post-1`);
    expect(req.request.method).toBe('GET');
    req.flush(MOCK_POST);
    expect(result).toEqual(MOCK_POST);
  });

  it('deletePost DELETEs the post endpoint and returns the updated post', () => {
    let result: ForumPost | undefined;
    service.deletePost('post-1').subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts/post-1`);
    expect(req.request.method).toBe('DELETE');

    const deletedPost: ForumPost = { ...MOCK_POST, status: PostStatus.DELETED };
    req.flush(deletedPost);
    expect(result).toEqual(deletedPost);
  });

  it('createPost POSTs to the forum posts endpoint with the given data', () => {
    let result: ForumPost | undefined;
    const data = {
      title: 'כותרת',
      content: 'תוכן',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    };
    service.createPost(data).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(data);
    req.flush(MOCK_POST);
    expect(result).toEqual(MOCK_POST);
  });

  it('updatePost PATCHes the single post endpoint with the given data', () => {
    let result: ForumPost | undefined;
    const data = { title: 'כותרת מעודכנת' };
    service.updatePost('post-1', data).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts/post-1`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual(data);

    const updatedPost: ForumPost = { ...MOCK_POST, title: 'כותרת מעודכנת' };
    req.flush(updatedPost);
    expect(result).toEqual(updatedPost);
  });

  describe('buildConversationKey', () => {
    it('is order-independent', () => {
      expect(buildConversationKey('id-a', 'id-b')).toBe(buildConversationKey('id-b', 'id-a'));
    });

    it('joins the sorted ids with a colon', () => {
      expect(buildConversationKey('id-b', 'id-a')).toBe('id-a:id-b');
    });
  });

  describe('direct messages', () => {
    const MOCK_MESSAGE: DirectMessage = {
      id: 'msg-1',
      sender: { id: 'me-1', first_name: 'שרה', last_name: 'לוי' },
      recipient: { id: 'other-1', first_name: 'רבקה', last_name: 'כהן' },
      content: 'שלום',
      is_read: false,
      created_at: '2026-08-01T10:00:00',
    };

    it('sendMessage POSTs to /messages with the given data', () => {
      let result: DirectMessage | undefined;
      const data = { recipient_id: 'other-1', content: 'שלום' };
      service.sendMessage(data).subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/messages`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(data);
      req.flush(MOCK_MESSAGE);
      expect(result).toEqual(MOCK_MESSAGE);
    });

    it('getConversation GETs /conversations/{key}/messages using the sorted key', () => {
      let result: DirectMessage[] | undefined;
      service.getConversation('me-1', 'other-1').subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/conversations/me-1:other-1/messages`);
      expect(req.request.method).toBe('GET');
      req.flush([MOCK_MESSAGE]);
      expect(result).toEqual([MOCK_MESSAGE]);
    });

    it('getCellMembers GETs /cells/me/members', () => {
      let result: UserPublic[] | undefined;
      service.getCellMembers().subscribe((res) => (result = res));

      const req = httpMock.expectOne(`${environment.apiUrl}/cells/me/members`);
      expect(req.request.method).toBe('GET');
      const members: UserPublic[] = [{ id: 'other-1', first_name: 'רבקה', last_name: 'כהן' }];
      req.flush(members);
      expect(result).toEqual(members);
    });
  });
});
