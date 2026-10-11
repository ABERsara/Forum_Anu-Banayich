import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(`${this.base}${path}`);
  }

  /**
   * A GET whose body is a file, handed over as the bytes the server sent.
   *
   * A `Blob`, not `responseType: 'text'`: decoding to a string runs the body
   * through a UTF-8 `TextDecoder`, which strips a leading byte-order mark — and
   * the audit log's CSV export (ABF-161) carries one precisely so that Excel
   * reads its Hebrew as UTF-8. Saved from a string, the file would open as
   * mojibake.
   */
  getBlob(path: string): Observable<Blob> {
    return this.http.get(`${this.base}${path}`, { responseType: 'blob' });
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(`${this.base}${path}`, body);
  }

  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(`${this.base}${path}`, body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(`${this.base}${path}`);
  }
}
