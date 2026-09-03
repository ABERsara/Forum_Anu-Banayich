/**
 * `screenErrorFrom` decides which of two authors a screen quotes, so the one
 * thing worth pinning down is the boundary between them: anything the API
 * actually wrote wins, and everything else falls through to our key.
 */

import { NO_ERROR, screenErrorFrom } from './screen-error';

describe('screenErrorFrom', () => {
  it('quotes the sentence the API sent', () => {
    const err = { error: { detail: 'ניתן להשעות רק משתמש פעיל' } };

    expect(screenErrorFrom(err, 'admin.errors.suspend_failed')).toEqual({
      key: '',
      text: 'ניתן להשעות רק משתמש פעיל',
    });
  });

  it.each([
    ['no error body at all', {}],
    ['a null error body', { error: null }],
    ['an error body with no detail', { error: {} }],
    ['a detail that is not a string', { error: { detail: { message: 'nope' } } }],
    ['a blank detail', { error: { detail: '   ' } }],
    ['nothing thrown at all', undefined],
  ])('falls back to our own key on %s', (_case, err) => {
    expect(screenErrorFrom(err, 'admin.errors.suspend_failed')).toEqual({
      key: 'admin.errors.suspend_failed',
      text: '',
    });
  });

  it('never fills both fields, so a template cannot show two messages', () => {
    const cases = [{ error: { detail: 'שגיאת שרת' } }, {}];

    for (const err of cases) {
      const result = screenErrorFrom(err, 'admin.errors.broadcast_failed');
      expect(result.key === '' || result.text === '').toBe(true);
    }
  });

  it('starts empty', () => {
    expect(NO_ERROR).toEqual({ key: '', text: '' });
  });
});
