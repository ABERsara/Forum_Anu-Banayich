# CONTRIBUTING — אנו בניך

> מדריך זה מגדיר **איך** כותבים קוד בפרויקט. לפני כל PR — עיינו ב-[CHECKLIST.md](./CHECKLIST.md).

## תוכן עניינים

1. [עקרונות ארכיטקטורה](#1-עקרונות-ארכיטקטורה)
2. [Backend — FastAPI](#2-backend--fastapi)
3. [Frontend — Angular](#3-frontend--angular)
4. [RBAC ואבטחה](#4-rbac-ואבטחה)
5. [נגישות](#5-נגישות)
6. [i18n — רב-לשוניות](#6-i18n--רב-לשוניות)
7. [איכות קוד](#7-איכות-קוד)
8. [Git Workflow](#8-git-workflow)
9. [בדיקות](#9-בדיקות)
10. [פריסה ו-CI/CD](#10-פריסה-ו-cicd)

---

## 1. עקרונות ארכיטקטורה

### SRP — Single Responsibility Principle

כל קובץ עושה **דבר אחד בלבד**. שם הקובץ צריך לתאר אותו באופן מלא.

| קובץ | אחריות יחידה |
|---|---|
| `endpoints/*.py` | HTTP contract — קבלת בקשה, אימות צורה, האצלה לשירות, החזרת תשובה |
| `services/*.py` | לוגיקת עסקים — שאילתות, כללים, הצפנה, שליחת מייל, audit |
| `models/*.py` | הגדרת הסכמה ב-DB — עמודות וקשרים בלבד |
| `schemas/*.py` | קלט/פלט של ה-API — חוזה Pydantic |
| `core/services/*.ts` | קריאות HTTP ומצב משותף |
| Feature component | תצוגה ואינטראקציה עם המשתמש |
| `shared/components/` | UI גנרי, ניתן לשימוש חוזר, ללא תלות ב-feature |

### כיוון תלות — One-Way

```
Backend:   Endpoint → Service → Model
Frontend:  Component → Core Service → ApiService → HTTP
```

**לא הפוך, לא מעגלי.** Service לא מייבא `HTTPException`. Model לא מכיל לוגיקה עסקית. Component לא קורא ל-`HttpClient` ישירות.

### חוזים מפורשים

כל חיבור בין שכבות עובר דרך חוזה מוגדר:

- **Backend:** Pydantic schema (`ForumPostCreate`, `ForumPostOut`) בין endpoint לשירות ולקורא
- **Frontend:** TypeScript interface מתוך `core/models/` בין service לקומפוננטה

---

## 2. Backend — FastAPI

### שכבות ואחריויות

```
backend/app/
├── api/v1/endpoints/   ← HTTP layer — thin
├── services/           ← business logic — fat
├── models/             ← SQLAlchemy — data only
├── schemas/            ← Pydantic — contracts
└── core/               ← utilities (security, config, dependencies)
```

### Endpoint — thin

Endpoint מקבל, מאמת צורה, מאציל, מחזיר. **שום דבר אחר.**

```python
# ✅ נכון — endpoint דק
@router.post("/forum/posts", response_model=ForumPostOut, status_code=201)
async def create_post(
    payload: ForumPostCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ForumPostOut:
    return await forum_service.create_post(db, payload, author=current_user)


# ❌ שגוי — לוגיקה עסקית בתוך endpoint
@router.post("/forum/posts")
async def create_post(payload: ForumPostCreate, current_user: User = ...):
    if current_user.sector != payload.target_sector:  # שייך לשירות
        raise HTTPException(...)
    post = ForumPost(**payload.dict())                 # שייך לשירות
    db.add(post)
    await db.commit()
    return post
```

### Service — business logic

Service מכיל כל לוגיקה: סינון visibility, הצפנה, שליחת מייל, audit. **לא מייבא FastAPI** — לא `Request`, לא `Depends`, לא `HTTPException`.

```python
# ✅ נכון — service מעלה ValueError/PermissionError; endpoint תופס ומתרגם ל-HTTPException
async def create_post(
    db: AsyncSession,
    payload: ForumPostCreate,
    author: User,
) -> ForumPost:
    if not _author_may_post_to(author, payload):
        raise PermissionError("sector_mismatch")

    post = ForumPost(author_id=author.id, **payload.model_dump())
    db.add(post)
    await db.flush()

    await audit_service.log_action(
        db, actor=author, action="forum.post.create", entity_id=post.id
    )
    await db.commit()
    return post
```

### Model — data only

Model מגדיר עמודות וקשרים. Property מחושבת על שדות עצמם — OK. לוגיקה עסקית — לא כאן.

```python
# ✅ OK — computed property
@property
def full_name(self) -> str:
    return f"{self.first_name} {self.last_name}"

# ❌ שגוי — לוגיקה עסקית שייכת לשירות
def can_send_broadcast(self) -> bool:
    return self.role in (Role.ADMIN, Role.PROFESSIONAL)
```

### Schema — Pydantic

**שם לפי פעולה, לא לפי ישות:**

```python
# ✅
class ForumPostCreate(BaseModel): ...   # קלט ליצירה
class ForumPostUpdate(BaseModel): ...   # קלט לעדכון
class ForumPostOut(BaseModel): ...      # פלט בקריאה

# ❌
class ForumPost(BaseModel): ...         # לא ברור מה כולל
```

### Migrations — Alembic

- כל שינוי סכמה = **migration חדש בנפרד**. אין לשנות migration קיים.
- שם תיאורי: `alembic revision --autogenerate -m "add_google_uid_to_users"`
- PR לא ממוזג לפני שה-migration נבדק locally עם `alembic upgrade head`.

### Audit Trail — חובה

כל פעולה admin/רגישה **חייבת** קריאה ל-`audit_service.log_action()`. זו דרישה חוקית (SPEC §9.3), לא אופציונלי.

```python
await audit_service.log_action(
    db,
    actor=current_user,
    action="admin.user.suspend",
    entity_type="user",
    entity_id=target_user_id,
    # אין תוכן רגיש בלוג — entity_id בלבד
)
```

### Content Visibility — חוק ברזל

**כל שאילתה שמחזירה תוכן פורום / DM / Q&A** חייבת לכלול WHERE מפורש:

```python
.where(
    or_(
        ForumPost.group_visibility == author.group,
        ForumPost.group_visibility == "all",
    ),
    or_(
        ForumPost.sector_visibility == author.sector,
        ForumPost.sector_visibility == "all",
    ),
)
```

זה נאכף ב-**service**, לא ב-endpoint ולא ב-model. תמיד לבדוק בפיצ'רים חדשים.

---

## 3. Frontend — Angular

### מבנה תיקיות

```
frontend/src/app/
├── features/           ← קומפוננטות feature-specific; תיקייה לכל feature
│   ├── forum/
│   ├── admin/
│   ├── advice/
│   └── ...
├── core/
│   ├── services/       ← כל קריאות ה-API + shared state
│   ├── models/         ← TypeScript interfaces (ממופות על schema הבאקאנד)
│   ├── guards/         ← auth.guard + role.guard
│   └── interceptors/   ← auth token injection
├── shared/
│   └── components/     ← UI גנרי, שימושי ב-2+ features
└── layout/             ← shell (header, nav) — אין לוגיקה עסקית
```

### שאלת מיקום

> "האם הקומפוננטה תשמש feature אחד בלבד?" → `features/[name]/`
> "האם תשמש שניים ויותר?" → `shared/components/`
> "האם היא קריאה ל-API?" → `core/services/`
> "האם היא TypeScript type?" → `core/models/`

### Shared Component — דמה (Dumb)

קומפוננטה shared **לא מזריקה שירות**. מקבלת נתונים דרך `input()`, מדווחת דרך `output()`.

```typescript
// ✅ נכון — shared component
export class CopyTextComponent {
  text = input.required<string>();
  copied = output<void>();
}

// ❌ שגוי — shared component שמכירה feature
export class PostCardComponent {
  constructor(private forumService: ForumService) {} // feature knowledge!
}
```

קומפוננטת reference: [shared/components/copy-text/](./frontend/src/app/shared/components/copy-text/)

### Core Service — fat

Service מטפל בקריאות HTTP, ממפה שגיאות, מנהל cache/state. **Component לא קורא ל-`HttpClient` ישירות.**

```typescript
// ✅ נכון
@Injectable({ providedIn: 'root' })
export class ForumService {
  constructor(private api: ApiService) {}

  getPosts(params: ForumParams): Observable<ForumPost[]> {
    return this.api.get<ForumPost[]>('/forum/posts', { params });
  }
}
```

### Routing — Lazy Loading

**כל עמוד חדש נטען lazy** דרך `loadComponent` ב-`app.routes.ts`:

```typescript
{
  path: 'moderator/reports',
  loadComponent: () =>
    import('./features/moderator/reports/reports.component')
      .then(m => m.ReportsComponent),
  canActivate: [AuthGuard, RoleGuard],
  data: { roles: ['moderator', 'admin'] },
},
```

### SCSS

- תמיד `@use '../../../../styles/variables' as *;` + `@use '../../../../styles/mixins' as *;`
- **BEM:** `.block__element--modifier`
- אין magic numbers — כל ערך מתוך `_variables.scss`
- כיוון: `margin-inline-start/end` במקום `margin-left/right` (RTL-safe)
- אין `!important`

### Signals + Change Detection

```typescript
// ✅ דפוס החדש — signal-based API
export class MyComponent {
  title = input.required<string>();
  size  = input<'sm' | 'md'>('md');
  clicked = output<void>();

  isOpen = signal(false);        // local state
}
```

- `ChangeDetectionStrategy.OnPush` על כל קומפוננטה חדשה ב-`shared/`
- `signal()` למצב מקומי; לא `BehaviorSubject` לדברים פשוטים

---

## 4. RBAC ואבטחה

### Backend — כלל הזהב

**כל endpoint מוגן** = `Depends(get_current_active_user)` + בדיקת תפקיד מפורשת. לא לסמוך על המידע שהלקוח שולח.

```python
async def suspend_user(..., current_user: User = Depends(get_current_active_user)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403)
```

### Frontend — Guards

```typescript
// כל מסלול מוגן — שני גארדים
canActivate: [AuthGuard, RoleGuard],
data: { roles: ['admin'] },
```

`AuthGuard` בודק JWT. `RoleGuard` בודק `data.roles`. **אף פעם לא פותחים מסלול מוגן בלי שניהם.**

### אין PII בלוגים

- לא לוגים תוכן הודעות, ת"ז, מייל, טלפון, שמות — ב-backend וב-frontend כאחד.
- `audit_service.log_action()` רושם **פעולה + entity_id** בלבד.

### Secrets

- הכל דרך `.env` + `core/config.py`. `.env` לא נכנס ל-git.
- כל secret חדש → מעדכן `.env.example` + מוסיף ל-GitHub Secrets.

---

## 5. נגישות

**תקן חובה: ת"י 5568 / WCAG 2.1 AA.** רמת הנגישות המדויקת הנדרשת עדיין שאלה פתוחה מול הלקוח (SPEC §14, סעיף 6) — הטבלה הבאה היא ה-baseline המחייב בינתיים; SPEC §9.5 עוסק בפרטיות/GDPR ולא בנגישות, אין לצטט אותו כמקור לדרישות נגישות.

| דרישה | כיצד |
|---|---|
| כפתורים | `type="button"` תמיד; לא `<div>` כפתור |
| תיוג | `aria-label` / `aria-labelledby` על כל element שהטקסט לא מסביר אותו |
| Focus | `:focus-visible` עם `@include focus-ring` מ-`_mixins.scss` |
| ניגודיות | 4.5:1 לטקסט רגיל — `$color-text` על `$color-bg` עומד בתקן |
| כיוון | `<html lang>`/`<html dir>` נקבעים דינמית ע"י `LocaleService` (ABF-126) לפי השפה הפעילה — לא hardcoded |
| תמונות | `alt` תיאורי — לא "תמונה", לא ריק אלא אם דקורטיבי (`alt=""`) |
| היררכיית כותרות | h1→h2→h3 בסדר, לא מדלגים |

---

## 6. i18n — רב-לשוניות

> ספרינט 5 יוסיף תמיכה מלאה. אנחנו מכינים את התשתית **עכשיו** כדי למנוע שכתוב מאוחר.

**לא לכתוב טקסט hardcoded בתוך templates.** הכל דרך מפתח תרגום, עם ה-pipe של Transloco (`@jsverse/transloco`):

```html
<!-- ✅ -->
<span>{{ 'common.copy' | transloco }}</span>
<button>{{ 'forum.report.button' | transloco }}</button>

<!-- ❌ -->
<span>העתק</span>
```

קבצי תרגום: `frontend/public/i18n/he.json`, `en.json` (לא `src/assets/` — בפרויקט הזה `public/` הוא תיקיית ה-static assets, נטענים ב-runtime מ-`/i18n/{lang}.json`).

**מוסכמת שמות מפתחות**: dot notation, `<module>.<element>` (למשל `common.copy`, `forum.report.button`). דוגמאות אמיתיות מ-ABF-126:
`common.lang_he`, `common.lang_en`, `header.switch_to_hebrew`, `header.switch_to_english`.

**שתי השפות חייבות להיות מלאות.** `core/i18n/translations.spec.ts` מפיל את הבילד אם מפתח קיים
בקובץ אחד ולא בשני, אם ערך כלשהו ריק, או אם אותו מפתח מַפנה לפרמטרים שונים בשתי השפות
(`{{name}}` שנעלם בצד אחד = משפט שבולע את השם). זה החליף את ההקלה של ABF-126 ("מפתח חסר
ב-EN — OK בינתיים"): כל שבעת טיקטי המיגרציה מחויבים ממילא לשתי השפות בקריטריוני הקבלה,
והשומר רק אוכף את מה שהם כבר דורשים. `core/constants/index.spec.ts` ממשיך לשמור בנוסף
על מרחב `constants.*` — שם גם *עודף* תרגום (מפתח שאף מיפוי לא מצביע עליו) הוא כשל.

### תוויות משותפות — אל תתרגמו אותן שוב (ABF-127)

עשרת מיפויי התוויות ב-`core/constants/index.ts` (`SECTOR_LABELS`, `USER_TYPE_LABELS`,
`GROUP_VISIBILITY_LABELS`, `ACCOUNT_STATUS_LABELS`, `PROFESSIONAL_DOMAIN_LABELS`,
`QUERY_STATUS_LABELS`, `POST_STATUS_LABELS`, `REPORT_REASON_LABELS`, `DOCUMENT_TYPE_LABELS`,
`SECTOR_VISIBILITY_LABELS`) כבר מחזיקים **מפתחות תרגום**, במרחב `constants.<enum>.<value>` —
למשל `constants.sector.hasidic`. הם משותפים לכל המודולים, ולכן טיקט מיגרציה של מודול **לא**
מוסיף להם מפתחות ולא נוגע ב-`core/constants/index.ts`: מייבאים את המפה כמו קודם ומרנדרים דרך
ה-pipe.

```html
<!-- ✅ בתבנית — מתעדכן לבד בהחלפת שפה. להוסיף TranslocoPipe ל-imports של הקומפוננטה -->
{{ sectorLabels[user.sector] | transloco }}
```

```ts
// ✅ רק כשה-TypeScript מרכיב את המחרוזת בעצמו — צירוף כמה תוויות, או מתודה שמחזירה
//    שם של אדם בענף אחד ותווית בענף אחר. ראו core/i18n/label.service.ts
this.labels.label(SECTOR_LABELS[user.sector]);
```

```ts
// ❌ אל תוסיפו למודול שלכם מפתח משלכם לאותה תווית — זו בדיוק הכפילות ש-ABF-127 מנע
'forum.sector.hasidic': 'חסידי'
```

**בבדיקות**: `translocoTesting()` מ-`src/testing/transloco-testing.ts` טוען את קבצי ה-he/en
האמיתיים, כך שאפשר להמשיך לבדוק מול הטקסט העברי עצמו:

```ts
TestBed.configureTestingModule({ imports: [MyComponent, translocoTesting()] });
```

### קומפוננטות משותפות — מי מתרגם את הטקסט (ABF-128)

`shared/components/` ו-`layout/header/` כבר migrated. **הכלל: קלט טקסט של קומפוננטה משותפת
מקבל טקסט מתורגם, לא מפתח.** הקומפוננטה המשותפת היא dumb — היא מרנדרת את המחרוזת שקיבלה
כמו שהיא, וה-pipe רץ אצל *הקורא*:

```html
<!-- ✅ הקורא מתרגם -->
<app-confirm-dialog
  [title]="'forum.delete_post.title' | transloco"
  [confirmText]="'forum.delete_post.confirm' | transloco"
/>
<app-card [title]="'home.forum.title' | transloco" />
<app-loading-spinner [message]="'common.loading' | transloco" />
<app-error-display [message]="'forum.load_failed' | transloco" />
```

```html
<!-- ❌ מפתח גולמי כערך — הקומפוננטה לא מתרגמת, והמפתח יגיע למסך -->
<app-confirm-dialog title="forum.delete_post.title" />
```

למה כך: המפתח `forum.*` שייך למודול שקורא, לא לקומפוננטה המשותפת — כך אף מודול לא נוגע
ב-`shared/` בטיקט שלו, ובדיוק כפי שקומפוננטה משותפת לא יודעת מאיזה מודול הגיעה המחרוזת,
היא גם לא צריכה לדעת באיזה מרחב מפתחות הוא משתמש.

**ברירות המחדל** של הדיאלוגים (`shared.confirm_dialog.*`, `shared.suspend_dialog.*`,
`shared.file_upload.choose_file`, `shared.copy_text.*`) הן הטקסט היחיד שהקומפוננטות האלה
מחזיקות בעצמן, והן נכנסות רק כשהקורא לא העביר כלום. קורא שעדיין מעביר מחרוזת עברית קשיחה
(מודול שטרם עבר מיגרציה) ממשיך לעבוד בדיוק כמו קודם.

`common.cancel` ו-`common.loading` הם מפתחות חוצי-מודולים — אל תוסיפו `forum.cancel` משלכם.

**דיווח שגיאה שנשמר ב-signal** — שמרו את ה*מפתח* והריצו pipe בתבנית, לא טקסט מתורגם:

```ts
// ✅ מתחלף עם השפה גם כשההודעה כבר על המסך — ראו report-button.component.ts
errorKey.set(err.status === 409 ? 'shared.report.error_duplicate' : 'shared.report.error_generic');
```

```html
@if (errorKey(); as key) {
  <app-error-display [message]="key | transloco" />
}
```

**כיוון טקסט:** אל תכתבו `dir="rtl"` בתבנית ואל תכתבו `text-align: right`. `LocaleService`
מגדיר `<html dir>` לפי השפה, והכול יורש ממנו; ל-CSS השתמשו במאפיינים לוגיים
(`text-align: start`, `margin-inline-start`). `dir="ltr"` על שדה שהתוכן שלו תמיד LTR (אימייל,
למשל) הוא כיוון של *הערך* ולא של העמוד — הוא נשאר.

**בבדיקות** — `HEBREW` מ-`src/testing/transloco-testing.ts`. אחרי מעבר ל-EN,
`expect(text).not.toMatch(HEBREW)` נופל על *כל* מחרוזת שנשכחה, לא רק על זו שנזכרתם לבדוק:

```ts
TestBed.inject(TranslocoService).setActiveLang('en');
fixture.detectChanges();
expect(fixture.nativeElement.textContent).not.toMatch(HEBREW);
```

### שגיאה מהשרת מול קופי שלנו (ABF-129)

מסכי ה-auth מציגים שגיאה משני מקורות, ואי אפשר לטפל בשניהם אותו דבר:

- **הקופי שלנו** — "קוד שגוי", "שגיאה בכניסה" — נשמר כ**מפתח** ורץ ב-pipe בתבנית, כדי שהודעה
  שכבר על המסך תתחלף עם השפה במקום לקפוא בשפה שבה נוצרה.
- **`error.detail` שהשרת החזיר** — "אימייל כבר קיים" — הוא כבר משפט גמור, ומוצג כמו שהוא.
  לבלוע אותו יעלה לקורא/ת בדיוק את מה שההודעה הגנרית שלנו לא יודעת לתת: *למה* הבקשה נכשלה.

`features/auth/auth-error.ts` מחזיק את שני השדות ב-`AuthError` אחד, כך שלא ייתכן ששניהם
מלאים, ו-`authErrorFrom` שומר בדיוק על סדר העדיפויות של ה-`err.error?.detail ?? '...'`
שהיה שם קודם:

```ts
// ✅ detail מהשרת אם הגיע, אחרת המפתח שלנו
this.error.set(authErrorFrom(err, 'auth.login.error_generic'));
```

```html
@if (error().text; as text) {
  <app-error-display [message]="text" />
} @else if (error().key) {
  <app-error-display [message]="error().key | transloco" />
}
```

אותו כלל חל על טקסט שקומפוננטה משותפת כבר תרגמה בעצמה — למשל ה-`validationError` של
`app-file-upload`: הוא מגיע כטקסט, ולכן נכנס ל-`text` ולא ל-`key`.

השרת עדיין כותב את המשפטים האלה בעברית בכל שפת ממשק; מפתחות תרגום הוא מדבר רק בהודעות
הישירות (ABF-118). להעביר גם את `/auth/*` למפתחות זה שינוי backend, לא טיקט מיגרציה.

### תוכן שמשתמשים כתבו — לא מתרגמים (ABF-130)

כותרת של פוסט, גוף ההודעה, שם הכותב/ת — אלה **תוכן של משתמש/ת, לא UI**. הם מוצגים בשפה שבה
נכתבו, בשתי שפות הממשק, ואין להם מפתח. הגבול הזה חוזר בכל אחד מטיקטי המיגרציה שנשארו.

**בבדיקות זה משנה בפועל:** `expect(text()).not.toMatch(HEBREW)` נופל גם על עברית של fixture,
כלומר על בדיוק מה שהוא לא אמור לשמור עליו. לכן ה-fixture של הסריקה מחזיק תוכן לטיני
(`makeLatinPost` ב-`features/forum/*.spec.ts`), והסריקה נשארת מכוונת לקופי שלנו:

```ts
// ✅ הסריקה בודקת את ה-UI, לא את ה-fixture
renderWith(of(makeList({ items: [makeLatinPost()] })));
switchToEnglish();
expect(text()).not.toMatch(HEBREW);
```

ולצידה בדיקה הפוכה, שמוודאת שתוכן עברי של משתמש/ת **כן** נשאר על המסך אחרי מעבר לאנגלית.

**מפתח שמשמש שני מסכים באותו מודול** יושב במרחב משלו ולא מוכפל: `forum.post_form.*` (תווית
שדה + הודעת ולידציה) משותף ל-new-post ול-edit-post, ו-`forum.back_to_list` לשלושה מסכים. זו
אותה מוסכמה של ABF-127, מדרגה אחת פנימה — תווית משותפת ל*כל* המודולים יושבת ב-`constants.*`.

### מיגרציה לא מאחדת קופי (ABF-131)

קריטריון הקבלה של כל טיקטי המיגרציה הוא ש**העברית תיראה בדיוק כמו קודם**. לכן שני מסכים
שמנסחים אחרת את אותו הדבר מקבלים **שני מפתחות**, גם כשמתחשק לאחד:

```jsonc
// ✅ שני קישורים לאותו עמוד, בשני ניסוחים שהיו שם לפני הטיקט
"advice.back_to_professionals": "חזרה לרשימת אנשי מקצוע",  // ask-question, my-questions
"advice.qa_feed.back_to_advice": "חזרה לייעוץ מקצועי"       // qa-feed
```

```jsonc
// ❌ מפתח אחד לשניהם — משנה את הטקסט העברי על אחד המסכים
"advice.back": "חזרה לרשימת אנשי מקצוע"
```

איחוד הניסוחים הוא **שינוי קופי**, לא מיגרציה — טיקט נפרד, אחרי שהמפתחות במקום. זה לא סותר את
הכלל של ABF-130 על מפתח ששני מסכים חולקים: שם הטקסט **זהה** בשני המסכים ולכן מפתח אחד; כאן הוא שונה.

**ערך בתוך משפט — פרמטר, לא שרשור.** סדר המילים משתנה בין השפות, ומשפט שנבנה משני צמתים נפרדים
לא יכול להתהפך:

```html
<!-- ✅ he: "נשאלה ב-14/07/2026"  ·  en: "Asked on 14/07/2026" -->
{{ 'advice.pending.asked_on' | transloco: { date: question.created_at | date: 'dd/MM/yyyy' } }}
```

```html
<!-- ❌ הטקסט לפני התאריך והתאריך הם שני צמתים — באנגלית זה נשאר בסדר העברי -->
{{ 'advice.pending.asked_on' | transloco }}{{ question.created_at | date: 'dd/MM/yyyy' }}
```

`translations.spec.ts` כבר אוכף שהפרמטר קיים בשתי השפות.

**גם קומפוננטה שהיא stub עוברת מיגרציה.** ל-`qa-feed` יש היום רק כותרת וקישור חזרה, והשאר
`TODO` — שניהם עברו למפתחות עכשיו, כדי שמי שיממש את הפיצ'ר יוסיף **מפתחות** ולא עברית קשיחה
שתחייב טיקט מיגרציה שני.

### שגיאה של מסך — מפתח אחד ב-`core/i18n/` (ABF-132)

הצמד "משפט שהשרת כתב מול קופי שלנו" נכתב שלוש פעמים לפני שהיה ברור שהוא תשתית:
`features/auth/auth-error.ts` (ABF-129), עותק מקומי בתוך `features/forum/new-post` (ABF-130),
ו-`features/advice/advice-error.ts` (ABF-131). מ-ABF-132 הוא יושב ב-**`core/i18n/screen-error.ts`**,
ו**קוד חדש מייבא משם**:

```ts
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';

// ✅ detail מהשרת אם הגיע, אחרת המפתח שלנו
this.error.set(screenErrorFrom(err, 'admin.errors.suspend_failed'));
```

```ts
// ❌ עותק רביעי בתוך features/<module>/
export function adminErrorFrom(err: unknown, fallbackKey: string) { ... }
```

שלושת העותקים הישנים עדיין במקומם בכוונה — הם שייכים לטיקטים שה-PR שלהם פתוח לביקורת, וטיקט
מיגרציה של מודול אחד לא מזיז קבצים של שניים אחרים. איחודם הוא קומיט מכני נפרד: מחיקת קובץ
והפניית import, לכל מודול.

### קישור שקורא לעמוד בשמו (ABF-132)

תפריט שמצביע על עמודים אחרים באותו מודול לא מחזיק עותק שני של הכותרות שלהם — **קישור שהטקסט
שלו הוא בדיוק הכותרת של העמוד שהוא פותח מרנדר את מפתח ה-`title` של אותו עמוד**. זו אותה מוסכמה
של ABF-131 ("השאלות שלי" ב-advice-list), מוחלת על שבעת הקישורים של לוח הבקרה:

```html
<!-- ✅ הקישור והכותרת של active-users הם אותן מילים — מפתח אחד -->
<a routerLink="/admin/active-users">{{ 'admin.active_users.title' | transloco }}</a>
```

```html
<!-- ✅ "הרשמות ממתינות" קצר מהכותרת "הרשמות ממתינות לאישור" — מפתח משלו -->
<a routerLink="/admin/registrations">{{ 'admin.dashboard.nav_registrations' | transloco }}</a>
```

הגבול הוא הטקסט, לא היעד: איחוד של שני ניסוחים שונים היה משנה את העברית על אחד המסכים, וזה
בדיוק מה ש-ABF-131 אסר. **בין מודולים** ממשיכים להפריד גם כשהטקסט זהה — `header.login` ליד
`auth.login.title` — כדי שמודול אחד לא ישנה קופי של מודול אחר בלי לדעת.

תוצאת לוואי מכוונת: טיקט שמתרגם תפריט מגדיר את מפתחות ה-`title` של עמודים שמסך אחר יעבור
מיגרציה אחריו (`admin.pending_registrations.title` וכו'). הטיקט הבא **צורך** אותם, לא מוסיף
מקבילים.

### מסך בלי spec מקבל spec (ABF-132)

`admin-dashboard` הוא כמעט כולו קופי — כותרת, כרטיס וסרגל של שבעה קישורים — ולא הייתה לו בדיקה
בכלל. מסך כזה הוא בדיוק מה שצריך שומר: בלעדיו שום דבר לא תופס תווית שחזרה לעברית קשיחה או מפתח
גולמי שדלף. טיקט מיגרציה שנוגע במסך בלי spec כותב לו אחד, כמו qa-feed ב-ABF-131.

---

## 7. איכות קוד

### Backend

```bash
ruff check backend/
ruff format --check backend/
mypy backend/
```

שלושתם חייבים לעבור לפני PR. `mypy` עובד עם `strict = true` כמוגדר ב-`pyproject.toml`.

### Frontend

```bash
npm run lint
npm run format:check
```

- אין `console.log` בקוד שמוזג
- אין `// TODO` ללא ticket מספר

---

## 8. Git Workflow

### שמות ענפים

```
feat/ABF-101-google-oauth
fix/ABF-99-missing-sector-filter
chore/upgrade-angular-19
docs/update-contributing
```

### סנכרון מ-main — Merge, לא Rebase

```bash
git checkout feat/my-branch
git merge main        # ✅ שומר על היסטוריה קריאה
# לא: git rebase main ❌
```

### Pull Request

- **כותרת:** אנגלית, עד 70 תווים, תיאורית
- **גוף:** אנגלית (ראה CHECKLIST.md לפורמט)
- **PR = שינוי לוגי אחד.** לא לאגד פיצ'רים שונים ב-PR אחד
- לאחר מיזוג — מחיקת הענף

---

## 9. בדיקות

### Backend (pytest)

```bash
pytest --tb=short          # לפני כל PR
pytest tests/test_forum_service.py -v   # לבדיקה ספציפית
```

- **Unit tests** על כל service method חדש ב-`tests/test_*_service.py`
- **Integration tests** עם DB אמיתי (test DB) — **לא mock**; mock ה-DB הוביל בעבר לבאגים בפרודקשן
- מה לא לבדוק: endpoint routing, framework internals

### Frontend (Vitest)

```bash
npm test -- --run          # לפני כל PR
```

- **Unit tests** על shared components (`*.spec.ts` לצד הקובץ)
- בודקים **behavior** — לא markup. מה המשתמש רואה/שומע, לא איך ה-HTML בנוי

---

## 10. פריסה ו-CI/CD

### NetFree Compliance — חובה

> **⚠️ רוב המשתמשים מסונן דרך נטפרי — אתר שאינו מאושר אינו נגיש להם.**

- **אין CDN חיצוניים:** גופנים, CSS, JS — הכל self-hosted או inline
- תמונות UI: webp מכווץ, ב-`assets/`
- API calls: רק לדומיין שלנו (Render backend) + שירותים מאושרים בלבד
- ראה SPEC §9.6 לסדר הפעולות לאישור דומיין

### Environment Variables

| שם | תיאור |
|---|---|
| `ENVIRONMENT` | סביבת הרצה — `production` בכל פריסה מתארחת |
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing key |
| `SENDGRID_API_KEY` | שליחת מיילים |
| `API_URL` | כתובת backend (frontend) |

כל secret חדש → `.env.example` מתעדכן + נוסף ל-GitHub Secrets.

#### פריסה ל-Render — שני משתנים, לא אחד

> **⚠️ ב-Render חובה להגדיר `ENVIRONMENT=production` בנוסף ל-`SECRET_KEY` — לא רק אותו.**

ולידציית ה-`SECRET_KEY` שב-`backend/app/core/config.py` (מפתח חסר / קצר מ-32 תווים /
זהה לברירת המחדל שבריפו) פועלת רק כאשר `ENVIRONMENT` אינו אחד מ-`development`,
`dev`, `local`, `test`. ברירת המחדל היא `development` — כלומר פריסה שמגדירה
`SECRET_KEY` בלבד **עוקפת את הבדיקה בשקט**, והאפליקציה תעלה עם מפתח חלש בלי
להתריע.

בעת יצירת השירות ב-Render — Dashboard → Service → Environment → Add:

| Key | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | פלט של `openssl rand -hex 32` |

אימות לאחר הפריסה: הגדרת `ENVIRONMENT=production` בלי `SECRET_KEY` תקין חייבת
להפיל את השירות ב-startup עם הודעת `CONFIGURATION ERROR` ב-Render logs. אם השירות
עלה — `ENVIRONMENT` לא נקלט.

### CI/CD

`.github/workflows/ci.yml` מריץ: `pytest`, `ruff`, `mypy`, `npm test`, `npm run lint`.

**PR שה-CI שלו נכשל — לא ממוזג, לא ביד.**
