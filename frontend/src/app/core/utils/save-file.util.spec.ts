import { vi } from 'vitest';

import { REVOKE_AFTER_MS, saveFile } from './save-file.util';

/** The byte-order mark the audit log's CSV opens with, written visibly. */
const BOM = String.fromCharCode(0xfeff);

describe('saveFile', () => {
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  let createObjectURL: ReturnType<typeof vi.fn<(file: Blob) => string>>;
  let revokeObjectURL: ReturnType<typeof vi.fn<(url: string) => void>>;
  let clicked: HTMLAnchorElement[];

  beforeEach(() => {
    vi.useFakeTimers();
    // Neither exists in jsdom (profile.component.spec.ts says the same), so
    // they are put on `URL` for the test and put back after it.
    createObjectURL = vi.fn<(file: Blob) => string>().mockReturnValue('blob:audit-log');
    revokeObjectURL = vi.fn<(url: string) => void>();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;

    clicked = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      // Checked at the click, which is the moment the browser reads the link.
      expect(this.isConnected).toBe(true);
      clicked.push(this);
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  });

  it('downloads the very blob it was given, not a copy of its text', () => {
    const file = new Blob([`${BOM}a,b\r\n`], { type: 'text/csv' });

    saveFile(file, 'audit-log.csv');

    expect(createObjectURL).toHaveBeenCalledWith(file);
  });

  it('clicks one link to that blob, named as asked', () => {
    saveFile(new Blob(['x']), 'audit-log-2026-10-08.csv');

    expect(clicked).toHaveLength(1);
    expect(clicked[0].href).toBe('blob:audit-log');
    expect(clicked[0].download).toBe('audit-log-2026-10-08.csv');
  });

  it('attaches the link for the click and leaves nothing behind', () => {
    saveFile(new Blob(['x']), 'audit-log.csv');

    expect(clicked[0].isConnected).toBe(false);
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('keeps the URL alive until the browser has had time to read it', () => {
    saveFile(new Blob(['x']), 'audit-log.csv');

    vi.advanceTimersByTime(REVOKE_AFTER_MS - 1);
    expect(revokeObjectURL).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:audit-log');
  });
});
