/**
 * Guards the app against layout that cannot turn with `<html dir>`.
 *
 * `LocaleService` flips `<html dir>` between `rtl` and `ltr` with the active
 * language and every screen inherits it. That only works while nothing under
 * `src/` names a physical side of its own. ABF-134 established the rule for one
 * component; this spec is what makes it hold for the next one, the way
 * `translations.spec.ts` holds the two translation files together.
 *
 * Read as text off the disk, not as modules: a stylesheet that has been
 * compiled and a template that has been rendered no longer show which side the
 * author asked for. Four things are checked, and each had failed somewhere:
 *
 *   1. a physical side property in a stylesheet    — none; the SCSS was clean
 *   2. a physical side property in a `style="…"`   — ABF-134 fixed the one there was
 *   3. a screen pinning its own direction          — ABF-136 removed the one there was
 *   4. a sideways glyph that does not mirror       — fourteen back links, still open
 *
 * The first three are regression guards over ground already won. The fourth is
 * what was still broken, and what this spec was written for.
 *
 * **Where it does not look.** Component styles in this project live in `.scss`
 * files: there is no `styles: []` in a decorator and no `<style>` in a
 * component template, so neither is parsed here. `src/index.html` is left out
 * too — its `dir="rtl"` is the document's boot value, which `LocaleService`
 * takes ownership of on the first tick, not a screen pinning itself.
 */

/// <reference types="node" />
// The only spec that reaches for the filesystem, and the only one that asks for
// Node's types. Declared here rather than in tsconfig.spec.json's `types` so
// that reaching for `fs` stays a deliberate act in one file instead of a thing
// every spec can quietly do.

import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { TRANSLATIONS } from '../../../testing/transloco-testing';

const SRC = join(process.cwd(), 'src');
const APP = join(SRC, 'app');

function filesUnder(directory: string, matches: (name: string) => boolean): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return filesUnder(path, matches);
    return matches(entry.name) ? [path] : [];
  });
}

/** `…/src/app/features/home/home.component.html` → `app/features/home/…` */
const shortPath = (path: string) => relative(SRC, path).replaceAll('\\', '/');

const read = (path: string): [string, string] => [shortPath(path), readFileSync(path, 'utf8')];

const STYLESHEETS = filesUnder(SRC, (name) => name.endsWith('.scss')).map(read);
const TEMPLATE_FILES = filesUnder(APP, (name) => name.endsWith('.html')).map(read);

/** Components that carry their template as a string in the decorator. */
const INLINE_TEMPLATE_FILES = filesUnder(APP, (name) => name.endsWith('.component.ts')).map(read);

/**
 * Blanks text out while keeping its newlines, so that what is dropped here does
 * not move the line numbers a failure reports.
 */
const blanked = (text: string) => text.replace(/[^\n]/g, '');

/**
 * The part of a file that becomes markup, still at its original line numbers.
 *
 * For a component that carries its template in the decorator that is the
 * backticked string and nothing else — the class's own doc comment is prose,
 * and `register.component.ts` lays its steps out with `→`. HTML comments go the
 * same way: Angular compiles them out, so they render nothing and may point
 * wherever they like.
 */
function markupOf(path: string, source: string): string {
  const inline = /template:\s*`([\s\S]*?)`/.exec(source);
  const markup = path.endsWith('.html')
    ? source
    : inline
      ? blanked(source.slice(0, inline.index)) + inline[1]
      : '';

  return markup.replace(/<!--[\s\S]*?-->/g, blanked);
}

const TEMPLATES: [string, string][] = [...TEMPLATE_FILES, ...INLINE_TEMPLATE_FILES].map(
  ([path, source]) => [path, markupOf(path, source)],
);

// ---------------------------------------------------------------------------
// What counts as physical
// ---------------------------------------------------------------------------

/**
 * Properties that name a side of the screen instead of a side of the text.
 * Each has a logical twin — `margin-inline-start`, `border-inline-end`,
 * `inset-inline-start` — that follows `<html dir>` on its own.
 */
const PHYSICAL_PROPERTY = [
  /^(margin|padding|scroll-margin|scroll-padding)-(left|right)$/,
  /^border-(left|right)(-(width|style|color))?$/,
  /^border-(top|bottom)-(left|right)-radius$/,
  /^(left|right)$/,
];

/** Properties that stay logical only until they are given a physical value. */
const PHYSICAL_VALUE: Record<string, RegExp> = {
  'text-align': /^(left|right)$/,
  float: /^(left|right)$/,
  clear: /^(left|right)$/,
};

/**
 * `direction` is not on the list above because it has no logical twin: a screen
 * that sets it stops following the language rather than picking the wrong side.
 * `flex-direction` is a different property and deliberately does not match.
 */
const PINS_DIRECTION = /^direction$/;

// ---------------------------------------------------------------------------
// Reading declarations out of text
// ---------------------------------------------------------------------------

interface Declaration {
  property: string;
  value: string;
  line: number;
}

/**
 * Comments out of the way, so that a property named in prose is not read as
 * code — four stylesheets here say "no margin-left/right" in so many words.
 * The `[^:]` guard is what keeps `https://` from opening a line comment.
 */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blanked)
    .replace(
      /(^|[^:])(\/\/[^\n]*)/g,
      (_, before: string, comment: string) => before + blanked(comment),
    );
}

const lineOf = (source: string, index = 0) => source.slice(0, index).split('\n').length;

/**
 * Every `property: value` in a stylesheet or in a `style="…"` attribute.
 *
 * A declaration starts after `{`, `}`, `;` or the start of the text, which is
 * what keeps selectors (`&:hover`), at-rules (`@media (min-width: …)`) and SCSS
 * variables (`$shadow-sm: …`) out: none of them opens with a bare property name
 * in that position.
 */
function declarationsIn(source: string): Declaration[] {
  const text = withoutComments(source);
  const declaration = /(?:^|[;{}])\s*([a-z-]+)\s*:\s*([^;{}]*)/g;

  return [...text.matchAll(declaration)].map((match) => ({
    property: match[1],
    value: match[2].trim(),
    line: lineOf(text, match.index),
  }));
}

/** The contents of every `style="…"` in a template. */
function inlineStylesIn(source: string): { css: string; line: number }[] {
  return [...source.matchAll(/style="([^"]*)"/g)].map((match) => ({
    css: match[1],
    line: lineOf(source, match.index),
  }));
}

const isPhysical = ({ property, value }: Declaration): boolean =>
  PHYSICAL_PROPERTY.some((pattern) => pattern.test(property)) ||
  PHYSICAL_VALUE[property]?.test(value) === true;

// ---------------------------------------------------------------------------
// What counts as a frozen glyph
// ---------------------------------------------------------------------------

/**
 * Glyphs that point sideways.
 *
 * Appearing on this list is not the offence — the list is only where to look.
 * The verdict is Unicode's: a glyph belongs here when it carries
 * `Bidi_Mirrored`, because the browser then turns it with the paragraph and it
 * reads as "back" in both languages without anyone having chosen a side.
 * `‹ › « »` carry it and pass. Nothing in the Arrows block carries it, which is
 * why the fourteen back links that read `←` pointed into the page in Hebrew.
 */
const SIDEWAYS = /[←→↔↩↪⇐⇒⇔◀▶◄►◂▸⬅➡‹›«»❮❯]/gu;

/** The same arrows spelled as an entity: `&larr;` renders `←` just as well. */
const ARROW_ENTITY = /&[lrh]arr;|&[lrh]Arr;/g;

function frozenGlyphsIn(source: string): string[] {
  const glyphs = [...new Set(source.match(SIDEWAYS) ?? [])].filter(
    (glyph) => !/\p{Bidi_Mirrored}/u.test(glyph),
  );

  return [...glyphs, ...new Set(source.match(ARROW_ENTITY) ?? [])];
}

/** `{a: {b: '→ x'}}` → `['a.b: → x']`, so a failure names the key it came from. */
function flatten(source: unknown, prefix = ''): string[] {
  return Object.entries(source as Record<string, unknown>).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'string' ? [`${path}: ${value}`] : flatten(value, path);
  });
}

// ---------------------------------------------------------------------------

describe('direction', () => {
  /**
   * A guard that reads nothing passes for the wrong reason, and it fails that
   * way silently: an earlier draft of this spec pulled the files in through the
   * bundler, which hands back an empty string for `.scss`, and check 1 sailed
   * over a stylesheet with `margin-left: 1px` in it. Counting the files did not
   * catch that — they were all found, and all empty — so what is counted here
   * is the files that came back with something in them.
   */
  it('has the stylesheets and the templates in front of it', () => {
    const withContent = (files: [string, string][]) =>
      files.filter(([, source]) => source.trim() !== '').length;

    expect(withContent(STYLESHEETS), 'stylesheets read').toBeGreaterThan(30);
    expect(withContent(TEMPLATE_FILES), 'templates read').toBeGreaterThan(20);
    expect(withContent(INLINE_TEMPLATE_FILES), 'components read').toBeGreaterThan(20);
  });

  it('names no physical side in a stylesheet', () => {
    const offenders = STYLESHEETS.flatMap(([path, source]) =>
      declarationsIn(source)
        .filter(isPhysical)
        .map(({ property, value, line }) => `${path} — line ${line}: ${property}: ${value}`),
    ).sort();

    expect(offenders, 'use the -inline-start / -inline-end twin instead').toEqual([]);
  });

  it('names no physical side in an inline style attribute', () => {
    const offenders = TEMPLATES.flatMap(([path, markup]) =>
      inlineStylesIn(markup).flatMap(({ css, line }) =>
        declarationsIn(css)
          .filter(isPhysical)
          .map(({ property, value }) => `${path} — line ${line}: ${property}: ${value}`),
      ),
    ).sort();

    expect(offenders, 'use the -inline-start / -inline-end twin instead').toEqual([]);
  });

  /**
   * A screen that sets its own direction stops following the language: the
   * `direction: rtl` ABF-136 took out of the profile page is what an English
   * screen looks like when it still runs right-to-left. `dir="rtl"` is the same
   * mistake spelled as an attribute — the direction a screen inherits is
   * already the right one, and content that genuinely owns a direction takes
   * `dir="auto"` or, where the datum is always Latin, the `dir="ltr"` that the
   * two email fields carry.
   */
  it('pins no direction of its own', () => {
    const inStylesheets = STYLESHEETS.flatMap(([path, source]) =>
      declarationsIn(source)
        .filter(({ property }) => PINS_DIRECTION.test(property))
        .map(({ value, line }) => `${path} — line ${line}: direction: ${value}`),
    );

    const inTemplates = TEMPLATES.flatMap(([path, markup]) => [
      ...inlineStylesIn(markup)
        .filter(({ css }) =>
          declarationsIn(css).some(({ property }) => PINS_DIRECTION.test(property)),
        )
        .map(({ line }) => `${path} — line ${line}: style="direction: …"`),
      ...[...markup.matchAll(/\bdir="rtl"/g)].map(
        (match) => `${path} — line ${lineOf(markup, match.index)}: dir="rtl"`,
      ),
    ]);

    expect([...inStylesheets, ...inTemplates].sort(), 'let <html dir> decide').toEqual([]);
  });

  /**
   * The one this spec was written for. A back arrow is not decoration: it says
   * which way "back" is, and `←` says "left" in a language that runs right.
   */
  it('points sideways only with glyphs that Unicode mirrors', () => {
    const inTemplates = TEMPLATES.flatMap(([path, markup]) =>
      frozenGlyphsIn(markup).map((glyph) => `${path}: ${glyph}`),
    );

    const inTranslations = Object.entries(TRANSLATIONS).flatMap(([lang, translations]) =>
      flatten(translations)
        .filter((entry) => frozenGlyphsIn(entry).length > 0)
        .map((entry) => `${lang}.json ${entry}`),
    );

    expect(
      [...inTemplates, ...inTranslations].sort(),
      'use ‹ (U+2039), which carries Bidi_Mirrored and turns with the page',
    ).toEqual([]);
  });
});
