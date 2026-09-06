# PR Checklist

Copy this checklist into every pull request description.

---

## General
- [ ] Branch name follows pattern: `feat/`, `fix/`, `chore/`, `docs/` —
      or the bare `ABF-NNN-slug` form, approved for the i18n migration
      series (ABF-127…ABF-134). See CONTRIBUTING §8.
- [ ] Commit messages are clear and descriptive
- [ ] No console.log / print debug statements left in code
- [ ] No hardcoded secrets, tokens, or API keys
- [ ] `.env.example` updated if new env vars were added

## Backend (FastAPI)
- [ ] New endpoint has a corresponding Pydantic schema (request + response)
- [ ] New endpoint is registered in `router.py`
- [ ] Sensitive routes are protected (auth dependency injected)
- [ ] Unit / integration test added or updated
- [ ] `pytest` passes locally
- [ ] `ruff check` and `ruff format` pass
- [ ] `mypy` passes with no new errors

## Frontend (Angular)
- [ ] Component is standalone (no NgModule)
- [ ] New page is lazy-loaded via `loadComponent` in `app.routes.ts`
- [ ] Reusable UI goes in `shared/components/`, not in the feature
- [ ] SCSS uses variables from `_variables.scss` (no magic numbers)
- [ ] `npm run lint` passes
- [ ] `npm run format:check` passes
- [ ] `npm test` passes

## Security
- [ ] User input is validated / sanitized before use
- [ ] No `innerHTML` / `bypassSecurityTrust*` without explicit review
- [ ] SQL queries use parameterized statements (no raw string concat)
- [ ] Auth guard applied to protected routes

## Accessibility
- [ ] Interactive elements are keyboard-accessible
- [ ] Images have meaningful `alt` attributes
- [ ] Color contrast meets WCAG AA minimum

## Performance
- [ ] No unnecessary HTTP calls on every render / ngOnInit
- [ ] Large lists use virtual scrolling or pagination
- [ ] Images are compressed / served in modern format (webp)

---

> After merging, delete the feature branch.
