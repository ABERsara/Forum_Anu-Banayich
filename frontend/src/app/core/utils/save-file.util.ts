/**
 * Hand a file the app already holds to the browser as a download.
 *
 * For a body that had to be fetched with the session's token. A plain
 * `<a href>` to an API URL cannot carry the `Authorization` header the auth
 * interceptor adds, so the file is fetched through HttpClient first and then
 * given to the browser from memory, under a name of the caller's choosing.
 *
 * The link is attached to the document for the click and removed straight
 * after: a detached anchor's click is not honoured by every browser. The
 * object URL is revoked later rather than at once, because revoking it in the
 * same task as the click can cancel a download Safari has not started reading
 * yet; FileSaver.js waits the same 40 seconds for the same reason. Until then
 * the URL is reachable only from this tab.
 *
 * The audit log's CSV export (ABF-161) is the first caller.
 */

/** How long the object URL outlives the click — see above. */
export const REVOKE_AFTER_MS = 40_000;

/** Download `file` as `filename`, from memory. */
export function saveFile(file: Blob, filename: string): void {
  const url = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;

  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}
