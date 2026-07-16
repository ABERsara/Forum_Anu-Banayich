import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ForumService } from './forum.service';
import { environment } from '../../../environments/environment';
import { GroupVisibility, PostStatus, SectorVisibility } from '../constants';
import type { ForumPost, ForumPostList } from '../models';

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
});
