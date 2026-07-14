import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ForumService } from './forum.service';
import { environment } from '../../../environments/environment';
import type { ForumPostList } from '../models';

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
});
