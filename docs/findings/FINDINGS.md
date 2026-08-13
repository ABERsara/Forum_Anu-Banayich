# יומן ממצאים — "אנו בניך"
<!-- last-updated: 2026-07-21 (review fixes: A-05 removed, A-15 added, line refs, §-citations) -->

## איך מוסיפים ממצא

1. בחרי את **מודול** הממצא (סעיף בטבלה) — לא לפי ספרינט, לפי מודול פונקציונלי.
2. בדקי שאין שורה קיימת על אותו **קובץ + תיאור** לפני הוספה — למנוע כפילויות.
3. הוסיפי שורה עם המספר הבא בסדרה של אותו מודול (`A-01`, `A-02` וכן הלאה).
4. מלאי **"סעיף"** לפי `SPEC.md` — לדוגמה `§4.2`, `§7.1`. אם עדיין לא קיים — כיתבי `TBD`.
5. commit: `docs: add finding [XX]-[NN] — [תיאור קצר]`

---

## סוגי ממצא (`סוג`)

| קוד | משמעות |
|-----|--------|
| **באג** | קוד שגוי — מייצר תוצאה שגויה בפועל |
| **חסר** | פיצ'ר מוגדר באפיון אך לא ממומש כלל |
| **אי-דיוק** | ממומש אך לא תואם בדיוק לאפיון |
| **אבטחה** | פרצת אבטחה / בעיית הרשאות |
| **UX** | בעיית ממשק, נגישות, RTL, עברית |
| **ארכיטקטורה** | חלוקת אחריות שגויה, SRP, קומפוננטה / שכבה לא מתאימה |

## רמות חומרה

| ערך | משמעות |
|-----|--------|
| 🔴 קריטי | שבירת זרימה ראשית / פרצת אבטחה |
| 🟠 גבוה | תוצאה שגויה / אי-עמידה בדרישת אפיון מפורשת |
| 🟡 בינוני | חסר פיצ'ר משני / חוסר עקביות |
| 🟢 נמוך | שיפור UX / עיצוב / הערת קוד |

## סטטוסים

| ערך | משמעות |
|-----|--------|
| פתוח | לא טופל |
| בבדיקה | PR פתוח |
| תוקן | PR מוזג |
| לא רלוונטי | הוחלט שאינו ממצא |

---

## A | Auth & הרשמה

> קבצים עיקריים: `backend/app/api/v1/endpoints/auth.py` · `services/auth_service.py`
> · `frontend/src/app/features/auth/` · `core/guards/` · `core/interceptors/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| A-01 | `services/auth_service.py` | אי-דיוק | TBD | רשימת TODO בראש הקובץ (שורות 6-10) לא מעודכנת — `register()` ו-`verify_otp()` מסומנים `[ ]` אך ממומשים במלואם | 🟢 נמוך | פתוח |
| A-02 | `services/auth_service.py` | אבטחה | §9.2 | `verify_otp()`: הודעת שגיאה ל"קוד פג תוקף" (שורה 91) ספציפית במקום גנרית, בניגוד לדרישת האפיון להודעה אחידה לכל שגיאות OTP — מחליש הגנת User Enumeration | 🟠 גבוה | פתוח |
| A-03 | `services/auth_service.py` | אי-דיוק | TBD | `register()`: מחזיר 409 Conflict (שורה 58) בעוד האפיון מגדיר 400 — נדרשת החלטת צוות: ליישר את הקוד לאפיון או לעדכן את האפיון | 🟡 בינוני | פתוח |
| A-04 | `services/auth_service.py` | חסר | §9.3 | `login()`: חזרה אוטומטית של משתמש מושעה לסטטוס ACTIVE (שורות 116-119) לא נרשמת ב-Audit Log, בניגוד לדרישת האפיון לתיעוד כל פעולה מנהלתית/רגישה | 🟠 גבוה | פתוח |
| A-06 | `features/auth/login/login.component.ts` | ארכיטקטורה | TBD | inline template בתוך ה-.ts במקום templateUrl נפרד — כמו AD-01 | 🟢 נמוך | פתוח |
| A-07 | `services/auth_service.py` | אבטחה | TBD | `verify_otp()` (שורה 92) ללא הגבלת ניסיונות/קצב — קוד בן 6 ספרות ניתן לניחוש בברוטפורס בתוך חלון התוקף של 10 דקות | 🔴 קריטי | פתוח |
| A-08 | `core/guards/role.guard.ts` | באג | TBD | `roleGuard` (שורות 21-25) בודק `auth.currentUser()` באופן סינכרוני בעוד `loadCurrentUser()` עדיין רץ אסינכרונית מה-constructor של `AuthService` — ברענון דף / רשת איטית, אדמין/מבקר מחובר לגמרי מנותק חזרה ל-`/login` | 🟠 גבוה | פתוח |
| A-09 | `core/services/auth.service.ts` | באג | TBD | signal `currentUser` (שורות 127-129) מתעדכן רק ב-login/bootstrap ולא מתרענן אחרי שינוי סטטוס/תפקיד בשרת — משתמש שאושר/שונה תפקידו ע"י אדמין בזמן שהיה מחובר נשאר נעול על ההרשאות הישנות עד רענון דף מלא | 🟡 בינוני | פתוח |
| A-10 | `features/auth/register/register.component.html` | UX | TBD | טופס הרשמה שלב 2 (שורות 79-84) — שדה סיסמה יחיד ללא שדה אימות/השוואה; טעות הקלדה מתגלה רק בניסיון ההתחברות הראשון | 🟡 בינוני | פתוח |
| A-11 | `services/auth_service.py` | אבטחה | TBD | `_generate_otp()` (שורות 13, 30) משתמש ב-`random.choices` (Mersenne Twister) במקום `secrets` (CSPRNG) ליצירת קוד ה-OTP בן 6 הספרות | 🟠 גבוה | פתוח |
| A-12 | `models/user.py` · `services/auth_service.py` | אבטחה | TBD | אין אילוץ ייחודיות (לא באפליקציה, לא ב-DB) על `id_number` או `phone` — רק `email` נבדק; אותה ת"ז יכולה להירשם תחת כמה חשבונות שונים | 🟠 גבוה | פתוח |
| A-13 | `core/guards/auth.guard.ts` | אבטחה | TBD | `authGuard` (שורות 12-29) מטפל רק ב-`PENDING_APPROVAL`/`PARTIALLY_APPROVED`, לא ב-`SUSPENDED`/`REJECTED`/`CANCELLED` — משתמש בסטטוס כזה עלול להיכנס לאזורים מוגנים ללא הפניה למסך הסבר | 🟠 גבוה | פתוח |
| A-14 | `core/interceptors/auth.interceptor.ts` | ארכיטקטורה | TBD | `authInterceptor` (שורות 13-33) ללא נעילת single-flight סביב רענון טוקן — בקשות 401 מקבילות מפעילות כל אחת `refreshToken()` נפרד; אם refresh token מתחלף (rotation), עלול לגרום logout שגוי של session תקף | 🟠 גבוה | פתוח |
| A-15 | `models/user.py` · `services/auth_service.py` | אבטחה | §9.1 | `email`/`id_number`/`phone` מתועדים `# encrypted` (models/user.py שורות 50-72) ומפנים ל"encryption helpers" ב-auth_service.py, אך `register()` (שורות 54-80) לא מבצע כל הצפנה — נשמרים בטקסט גלוי ב-DB | 🔴 קריטי | פתוח |

---

## AD | Admin Dashboard

> קבצים עיקריים: `endpoints/admin.py` · `services/user_service.py` · `services/audit_service.py`
> · `frontend/src/app/features/admin/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| AD-01 | `features/admin/pending-registrations/pending-registrations.component.ts` | ארכיטקטורה | TBD | הקומפוננטה משתמשת ב-inline `template` (כ-48 שורות HTML, כולל inline styles כגון `style="padding: 1rem; direction: rtl"`) בתוך קובץ ה-`.ts` במקום `templateUrl` לקובץ `.html` נפרד — בניגוד לדפוס העקבי בשאר הקומפוננטות באפליקציה (`button`, `card`, `report-button` וכו') שמפרידות logic/template/style לשלושה קבצים; פוגע בקריאות ובתחזוקה | 🟢 נמוך | פתוח |

---

## F | Forum

> קבצים עיקריים: `endpoints/forum.py` · `services/forum_service.py`
> · `frontend/src/app/features/forum/` · `shared/components/report-button/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| F-01 | `shared/components/report-button/` | חסר | TBD | כפתור הדיווח קיים ב-UI אך `reportPost()` ב-`forum.service.ts` זורק `Error` — לחיצה לא עושה כלום. **עדכון 2026-07-20:** נבדק מחדש ונמצא לא מדויק — `ReportButtonComponent` בפועל קורא ל-`report.service.ts`'s `fileReport()` (לא ל-`reportPost()`), וזו כן ממומשת עבור `FORUM_POST`; הכפתור עובד בפועל. ראו F-04. | 🟠 גבוה | לא רלוונטי |
| F-02 | `services/forum_service.py` | אי-דיוק | TBD | רשימת TODO בראש הקובץ (שורות 8-12) לא מעודכנת: `get_posts()` ו-`get_post_by_id()` מסומנים `[ ]` אך ממומשים; `send_direct_message()` ו-`get_conversation()` לא ממומשים אך לא מופיעים ברשימה כלל | 🟢 נמוך | פתוח |
| F-03 | `services/forum_service.py` | אי-דיוק | TBD | `get_posts()`: TODO פנימי בן 6 שלבים (שורות 83-89) לא הוסר לאחר המימוש; המימוש בפועל אף חורג מהשלבים המקוריים (branch הרשאות ל-ADMIN שלא נכלל ב-TODO) | 🟢 נמוך | פתוח |
| F-04 | `core/services/forum.service.ts` | ארכיטקטורה | TBD | `reportPost()` (שורות 54-62) הוא stub מת (`throw new Error('reportPost() not yet implemented')`) שאף קומפוננטה לא קוראת לו — זרימת הדיווח בפועל עוברת דרך `report.service.ts`'s `fileReport()` (דרך `ReportButtonComponent`). קוד כפול/מת שכדאי להסיר כדי למנוע בלבול עתידי | 🟢 נמוך | פתוח |
| F-05 | `services/forum_service.py` · `endpoints/forum.py` | אבטחה | TBD | `create_post()` (שורות 241-267) לא בודק `role` — משתמש ADMIN/MODERATOR/PROFESSIONAL עם `group_visibility=ALL, sector_visibility=ALL` עוקף את `create_broadcast_post()` (ADMIN-only + audit log מבוקר) ומפרסם "שידור" לא מתועד | 🟠 גבוה | פתוח |

---

## M | Moderator

> קבצים עיקריים: `endpoints/moderator.py` · `services/report_service.py`
> · `frontend/src/app/features/moderator/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| M-01 | `services/report_service.py` | אי-דיוק | TBD | `file_report()` (שורה 74) בודק ליטרלית `report_count == 2` במקום לקרוא את `settings.AUTO_HIDE_REPORT_COUNT` — שינוי הסף בקונפיגורציה לא משפיע בפועל על ההסתרה האוטומטית | 🟡 בינוני | פתוח |

---

## P | ייעוץ מקצועי

> קבצים עיקריים: `endpoints/professional.py` · `services/professional_service.py`
> · `frontend/src/app/features/advice/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| P-01 | `features/advice/advice-list/advice-list.component.ts` | ארכיטקטורה | TBD | inline `template` בתוך ה-`.ts` במקום `templateUrl` נפרד — כמו AD-01 | 🟢 נמוך | פתוח |

---

## DM | הודעות פרטיות

> קבצים עיקריים: `endpoints/messages.py` (עדיין לא קיים — Sprint 5)
> · `frontend/src/app/features/messages/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| DM-01 | | | | | | |

---

## I | תשתית, DevOps ואבטחה

> קבצים עיקריים: `core/security.py` · `core/dependencies.py`
> · `.github/workflows/` · `docker-compose.yml` · `Dockerfile`s

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| I-01 | `core/security.py` · `core/dependencies.py` | אבטחה | §9.2 | `decode_access_token()` (security.py שורה 19) לא בודק את שדה `type` בתוך ה-JWT — refresh token (תוקף 7 ימים) מתקבל כ-access token תקין בכל endpoint מוגן ב-`get_current_user()` | 🔴 קריטי | פתוח |
| I-02 | `core/config.py` | אבטחה | §9.2 | `SECRET_KEY` (שורה 24) בעל ערך דיפולטי ידוע וקבוע בקוד (`dev-secret-change-in-production`), ללא בדיקת startup החוסמת עלייה בפרודקשן עם הערך הזה | 🔴 קריטי | פתוח |
| I-03 | `migrations/versions/91c4a53eec32_initial.py` | באג | §9.3 | ה-`sa.Enum` של `audit_logs.action` (שורה 27) חסר את `USER_PARTIALLY_APPROVED` ו-`BROADCAST_SENT` שבשימוש פעיל ב-`user_service.py`/`forum_service.py` — מול DB עם enum אמיתי (Postgres), אישור הרשמה ראשון או broadcast יכשלו ב-constraint violation (500) | 🔴 קריטי | פתוח |
| I-04 | `services/email_service.py` | ארכיטקטורה | TBD | שגיאות SMTP נתפסות ב-`except Exception` גורף ומתועדות ללוג בלבד ללא alerting — תקלת SMTP מלאה בפרודקשן (OTP / אישור / השעיה) תיכשל בשקט מוחלט וללא התראה לצוות | 🟡 בינוני | פתוח |
| I-05 | `core/security.py` | אבטחה | TBD | `bcrypt` חותך שקט ל-72 בייט (אין `bcrypt__truncate_error=True`) בעוד הסכמה (`schemas/auth.py` שורה 28) מתירה סיסמה עד 128 תווים — שתי סיסמאות שחולקות 72 בייט ראשונים נחשבות זהות | 🟡 בינוני | פתוח |

---

## S | Shared Components & Cross-Cutting

> קומפוננטות משותפות, routing, guards, interceptors, מודלים, Enums

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| S-01 | `src/index.html` | UX | TBD | `<title>` נותר `Frontend` — ערך ברירת המחדל שיצר Angular CLI, לא הוחלף לשם האתר בפועל | 🟢 נמוך | פתוח |
| S-02 | `public/favicon.ico` | UX | TBD | ה-favicon הוא אייקון ברירת המחדל של Angular CLI ולא הוחלף בלוגו/אייקון של האתר | 🟢 נמוך | פתוח |
| S-03 | `src/app/app.html` | ארכיטקטורה | TBD | קובץ template יתום משאריות ה-scaffold של Angular CLI — `App` (`app.ts`) משתמש ב-inline `template` משלו (לא `templateUrl`), כך ש-`app.html` (ובו `<router-outlet />` נוסף, כפול לזה שב-inline template) אינו נטען כלל ואינו מוצג באפליקציה; מומלץ למחיקה | 🟢 נמוך | פתוח |
| S-04 | `src/app/shared/components/button/` | ארכיטקטורה | TBD | `ButtonComponent` (`app-button`) קיימת ומוכנה (4 variants, 3 sizes, loading state) אך אינה בשימוש באף feature באפליקציה — 0 הפניות ל-`<app-button>` בכל ה-templates; קומפוננטות אחרות (למשל `report-button`) בונות `<button>` עצמאי במקום לעשות שימוש חוזר בה, מה שעלול ליצור חוסר עקביות עיצובית/נגישות | 🟢 נמוך | פתוח |
| S-05 | `shared/components/file-upload/file-upload.component.ts` | אבטחה | TBD | `onFileChange()` (שורות 30-53) מאמת גודל קובץ בלבד; ה-`[accept]` הוא רמז UI בדפדפן בלבד וניתן לעקיפה בקלות — אין בדיקת `file.type`/סיומת בפועל לפני `fileSelected.emit()` | 🟡 בינוני | פתוח |
| S-06 | `src/index.html` | UX | TBD | `<html lang="en">` (שורה 2) ללא `dir="rtl"` על ה-root, למרות שכל האפליקציה עברית/RTL — משפיע על native UI (confirm/autofill), title, וקוראי מסך | 🟠 גבוה | פתוח |
| S-07 | `features/profile/` · `layout/header/` | ארכיטקטורה | TBD | `ProfileComponent` בנוי במלואו ומנותב ל-`/profile`, אך אין אף `routerLink`/קישור אליו בשום מקום באפליקציה — משתמש לא יכול להגיע לפרופיל שלו בלי להקליד URL ידנית | 🟡 בינוני | פתוח |
