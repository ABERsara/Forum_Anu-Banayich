# יומן ממצאים — "אנו בניך"
<!-- last-updated: 2026-08-13 (re-verified all findings vs code on main; updated SPEC refs to v3.0; F-05 severity raised to קריטי; A-17–A-18 added; NG section added per §9.5 MVP; path confirmed on I-03) -->

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
| A-07 | `services/auth_service.py` | אבטחה | §9.2 | `verify_otp()` (שורה 92) ללא הגבלת ניסיונות/קצב — קוד בן 6 ספרות ניתן לניחוש בברוטפורס בתוך חלון התוקף של 10 דקות. **[דיוק]:** בנוסף, `resend_otp()` גם היא ללא צינון (cooldown) בין קריאות — מאפשר לחדש את חלון התוקף שוב ושוב ולהאריך את חלון הניחוש כמעט ללא הגבלה. בנוסף, `register()` לא מוודא בעלות על כתובת המייל לפני יצירת החשבון — תרחיש מוחמר: תוקף נרשם עם מייל אמיתי של קורבן שמעולם לא נרשם, מפציץ ניחושים תוך שימוש חוזר ב-resend כדי למנוע פקיעה, ואז מחזיק חשבון PENDING_APPROVAL תחת זהות הקורבן. | 🔴 קריטי | פתוח |
| A-08 | `core/guards/role.guard.ts` | באג | TBD | `roleGuard` (שורות 21-25) בודק `auth.currentUser()` באופן סינכרוני בעוד `loadCurrentUser()` עדיין רץ אסינכרונית מה-constructor של `AuthService` — ברענון דף / רשת איטית, אדמין/מבקר מחובר לגמרי מנותק חזרה ל-`/login` | 🟠 גבוה | פתוח |
| A-09 | `core/services/auth.service.ts` | באג | TBD | signal `currentUser` (שורות 127-129) מתעדכן רק ב-login/bootstrap ולא מתרענן אחרי שינוי סטטוס/תפקיד בשרת — משתמש שאושר/שונה תפקידו ע"י אדמין בזמן שהיה מחובר נשאר נעול על ההרשאות הישנות עד רענון דף מלא | 🟡 בינוני | פתוח |
| A-10 | `features/auth/register/register.component.html` | UX | TBD | טופס הרשמה שלב 2 (שורות 79-84) — שדה סיסמה יחיד ללא שדה אימות/השוואה; טעות הקלדה מתגלה רק בניסיון ההתחברות הראשון | 🟡 בינוני | פתוח |
| A-11 | `services/auth_service.py` | אבטחה | §9.1 | `_generate_otp()` (שורות 13, 30) משתמש ב-`random.choices` (Mersenne Twister) במקום `secrets` (CSPRNG) ליצירת קוד ה-OTP בן 6 הספרות | 🟠 גבוה | פתוח |
| A-12 | `models/user.py` · `services/auth_service.py` | אבטחה | §2.1 | אין אילוץ ייחודיות (לא באפליקציה, לא ב-DB) על `id_number` או `phone` — רק `email` נבדק; אותה ת"ז יכולה להירשם תחת כמה חשבונות שונים | 🟠 גבוה | פתוח |
| A-13 | `core/guards/auth.guard.ts` | אבטחה | §8.4 | `authGuard` (שורות 12-29) מטפל רק ב-`PENDING_APPROVAL`/`PARTIALLY_APPROVED`, לא ב-`SUSPENDED`/`REJECTED`/`CANCELLED` — משתמש בסטטוס כזה עלול להיכנס לאזורים מוגנים ללא הפניה למסך הסבר | 🟠 גבוה | פתוח |
| A-14 | `core/interceptors/auth.interceptor.ts` | ארכיטקטורה | §9.2 | `authInterceptor` (שורות 13-33) ללא נעילת single-flight סביב רענון טוקן — בקשות 401 מקבילות מפעילות כל אחת `refreshToken()` נפרד; אם refresh token מתחלף (rotation), עלול לגרום logout שגוי של session תקף. **[דיוק]:** אימתנו ב-`auth_service.py::refresh_token()` שהשרת **לא** מבצע token rotation בפועל כרגע (מחזיר את אותו refresh_token שהתקבל) — כך שהתרחיש המדויק שמתואר כאן לא מתממש היום; ההשפעה בפועל מוגבלת לבזבוז בקשות רשת מיותרות. חוסר ה-rotation עצמו הוא סיכון נפרד (טוקן אחד נשאר תקף לשימוש חוזר בלתי מוגבל למשך 7 ימים) ששווה לתעד/לתקן ללא קשר לממצא זה. | 🟠 גבוה | פתוח |
| A-15 | `models/user.py` · `services/auth_service.py` | אבטחה | §9.1 | `email`/`id_number`/`phone` מתועדים `# encrypted` (models/user.py שורות 50-72) ומפנים ל"encryption helpers" ב-auth_service.py, אך `register()` (שורות 54-80) לא מבצע כל הצפנה — נשמרים בטקסט גלוי ב-DB. **[דיוק]:** אימתנו בחיפוש מלא בכל `backend/app` — אין שום ספריית הצפנה מיובאת בפרויקט כלל, "עזרי ההצפנה" שהתיעוד מפנה אליהם לא קיימים בשום מקום. בנוסף, אותה הערת "# encrypted" כוזבת קיימת גם ב-`professional.py` (`ProfessionalQuery.content`/`answer`) וב-`forum.py` (`DirectMessage.content`) — היקף הבעיה רחב יותר מ-`user.py` בלבד וכולל תוכן שאלות משפטיות/פסיכולוגיות/רבניות מאוכלוסייה פגיעה. | 🔴 קריטי | פתוח |
| A-16 | `endpoints/users.py` | חסר | §9.7 | `DELETE /users/me` (שורות 44-58) — `delete_my_account()` מכילה `pass` בלבד: הבקשה מצליחה (204) ללא כל פעולה בפועל — המשתמש לא נמחק, נתוניו לא מוסרים, Audit Log לא נרשם. זכות המחיקה לפי GDPR (§9.7) נכשלת בשקט | 🔴 קריטי | פתוח |
| A-17 | `backend/migrations/versions/91c4a53eec32_initial.py` | אבטחה | §9.1 | `otp_code` מאוחסן ב-DB כ-`String(10)` טקסט גלוי — קוד OTP לא מגובב (hash) בטבלת users; גישה ישירה לDB חושפת קודי OTP פעילים | 🟠 גבוה | פתוח |
| A-18 | `services/auth_service.py` · `endpoints/auth.py` | חסר | §8.1 | `register()` לא מאמת גיל מינימום 18+ בצד השרת — `birth_date` נשמר אך אין בדיקה שהמשתמש מלאו 18 שנים; האפיון §8.1 מגדיר "חובה: 18+ בעת ההרשמה" | 🟠 גבוה | פתוח |
| A-19 | `frontend/src/app/core/services/auth.service.ts` (+ `auth.guard.ts`, `auth.interceptor.ts`) | באג | TBD | בעריכת שורת ה-URL בדפדפן על מסלול מוגן (למשל הסרת segment מהנתיב, /forum/{id} ← /forum), תוך session מחובר עם טוקן תקף — access_token ו-refresh_token נמחקים לחלוטין מ-localStorage וההפניה קופצת ל-/login, גם כאשר רגעים קודם לכן נשלחו בהצלחה בקשות API עם אותו טוקן (200). נבדק ונשלל כגורם: (1) קוד אפליקטיבי מפורש — הפונקציה היחידה שמוחקת את שני המפתחות היא clearTokens(); (2) שינוי origin; (3) כישלון HTTP רגיל דרך auth.interceptor.ts — כי בלוג הרשת המשומר אין שום בקשת HTTP חדשה בין הפעולה התקינה האחרונה לבין ההפניה. ניווט פנימי (routerLink, ללא reload מלא) לעולם לא משחזר את התופעה — רק reload מלא גורם לה. שורש הבעיה טרם אותר — פער נבדל מ-A-08 (roleGuard race condition) ומ-A-17 (OTP לא-מגובב) שכבר קיימים כאן. | 🟠 גבוה | פתוח |
| A-20 | `backend/app/services/email_service.py::send_otp_email()` (+ `core/config.py::SMTP_HOST`) | אבטחה | TBD | `send_otp_email()` בודקת אם `settings.SMTP_HOST` ריק (ברירת המחדל שלו) — ואם כן, כותבת את קוד ה-OTP בטקסט גלוי ללוג (`logger.info(f"[DEV EMAIL] OTP {otp_code} -> {email}")`) במקום לשלוח מייל אמיתי. אין שום דגל סביבה (ENVIRONMENT/DEBUG) שמבחין בין dev לפרודקשן. תרחיש: אם בפריסה לפרודקשן שוכחים להגדיר SMTP_HOST — (א) אף משתמש לא מקבל בפועל את קוד ה-OTP שלו; (ב) כל קוד OTP נכתב בטקסט גלוי ללוגים המרכזיים. שונה מ-A-17 (שעוסק באחסון ה-OTP במסד הנתונים) ומ-I-04 (כישלון שליחת SMTP בפועל) — כאן הבעיה היא הנתיב החלופי המכוון כש-SMTP כלל לא מוגדר. | 🔴 קריטי | פתוח |
| A-21 | `backend/app/api/v1/endpoints/users.py` (מול `core/constants.py::AuditAction.DATA_EXPORTED`) | חסר | §9.7 | אין שום endpoint לייצוא/גישה למידע אישי — §9.7 (GDPR ופרטיות ישראלית) קובע במפורש: "זכות גישה: משתמש יכול לבקש העתק של כל המידע שנשמר עליו". הערך `AuditAction.DATA_EXPORTED` מוגדר אך אף פעם לא נקרא. שונה מ-A-16 (זכות מחיקה) — זו זכות גישה נפרדת, גם היא תחת §9.7. | 🟠 גבוה | פתוח |
| A-22 | `backend/app/services/user_service.py` (תהליך האישור הכפול) | חסר | §8.2 | **בוטל לאחר קריאת SPEC.md v3.0 §8.2 במלואו:** דרישת "תזכורת 72 השעות" (למנהל השני, כשרק מנהל אחד אישר) שהתבססנו עליה **הוסרה מהאפיון** בגרסה v3.0. §8.2 העדכני מגדיר SLA יחיד: "7 ימי עסקים לאישור מלא (שני מנהלים). לאחר 7 ימים ללא אישור מלא — התראה למנהל הבכיר." אין עוד שלב-ביניים של 72 שעות לתעד. הממצא היה מבוסס על גרסת אפיון ישנה יותר. | 🟡 בינוני | לא רלוונטי |
| A-23 | `backend/app/services/user_service.py::escalate_overdue_registrations()` | חסר | §8.2 | ההסלמה של 7 ימים מיושמת נכון (`SLA_ESCALATION_DAYS=7`), אך נקראת אך ורק מטסטים — אין scheduler/cron בכל הפרויקט, כך שבפרודקשן היא לעולם לא תרוץ בפועל. **[דיוק]:** בנוסף, `timedelta(days=SLA_ESCALATION_DAYS)` סופר 7 **ימי לוח** (calendar days), בעוד §8.2 קובע במפורש "7 **ימי עסקים**" — לא אותו דבר (7 ימי עסקים ≈ 9-10 ימי לוח, כולל סופ"שים). פער נוסף, נפרד מהיעדר התזמון: גם כשהפונקציה כן תרוץ, הספירה עצמה לא תואמת במדויק את דרישת האפיון. | 🟡 בינוני | פתוח |
| A-24 | `backend/app/services/user_service.py::escalate_overdue_registrations()` | אי-דיוק | §8.2 | האפיון מזכיר "מנהל בכיר" יחיד — אין שדה כזה במודל User; ההתראה נשלחת בפועל לכל המנהלים. | 🟢 נמוך | פתוח |
| A-25 | `frontend/.../core/interceptors/auth.interceptor.ts` | ארכיטקטורה | TBD | ה-interceptor משכפל ידנית `clearTokens()`+`navigate(['/login'])` כשריענון טוקן נכשל, במקום לקרוא ל-`auth.logout()` הקיימת ב-`auth.service.ts` שכבר עושה בדיוק את שתי הפעולות יחד. סיכון תחזוקה: אם `logout()` ישתנה בעתיד, קל לשכוח לעדכן גם כאן. | 🟢 נמוך | פתוח |

---

## AD | Admin Dashboard

> קבצים עיקריים: `endpoints/admin.py` · `services/user_service.py` · `services/audit_service.py`
> · `frontend/src/app/features/admin/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| AD-01 | `features/admin/pending-registrations/pending-registrations.component.ts` | ארכיטקטורה | TBD | הקומפוננטה משתמשת ב-inline `template` (כ-48 שורות HTML, כולל inline styles כגון `style="padding: 1rem; direction: rtl"`) בתוך קובץ ה-`.ts` במקום `templateUrl` לקובץ `.html` נפרד — בניגוד לדפוס העקבי בשאר הקומפוננטות באפליקציה (`button`, `card`, `report-button` וכו') שמפרידות logic/template/style לשלושה קבצים; פוגע בקריאות ובתחזוקה | 🟢 נמוך | פתוח |
| AD-02 | `endpoints/admin.py` | חסר | §8.2 | `GET /admin/registrations/{user_id}` (שורות 54-62): raises `NotImplementedError` — מנהל הבוחן פרטי הגשה ומסמכים (תעודת פטירה, ת"ז) לפני אישור מקבל 500 במקום הנתונים; תהליך אישור הרשמה הכפול (§8.2) לא ניתן לביצוע בפועל | 🔴 קריטי | פתוח |
| AD-03 | `endpoints/admin.py` | חסר | §6.1 | ניהול אנשי מקצוע: `GET /admin/professionals` (שורות 102-107) מחזיר `[]` תמיד; `PUT /admin/professionals/{id}` (שורות 109-118) raises `NotImplementedError` — המנהל לא יכול לנהל את קטלוג אנשי המקצוע | 🟠 גבוה | פתוח |
| AD-04 | `endpoints/admin.py` | חסר | §9.3 | `GET /admin/audit-log` (שורות 135-147) מחזיר `[]` תמיד — לוח הבקרה לא מציג כל לוג פעולות; Audit Trail קיים בDB אך אינו נגיש | 🟠 גבוה | פתוח |
| AD-05 | `features/admin/manage-professionals/` · `features/admin/audit-log/` | חסר | §6.1 / §9.3 | שתי קומפוננטות admin מרונדרות כ-stub גמור: `manage-professionals.component.ts` מציגה `TODO: implement professionals management`; `audit-log.component.ts` מציגה `TODO: implement audit log viewer` — אין קריאות API | 🟠 גבוה | פתוח |
| AD-06 | `backend/app/schemas/user.py::SuspendUserRequest` (+ `services/user_service.py::suspend_user`, frontend `suspend-dialog.component.ts`) | באג | TBD | `hours: int = Field(48, gt=0)` מוגדר עם גבול תחתון בלבד, בלי גבול עליון — אותו חוסר בדיוק בפרונטאנד (`min="1"` בלי `max`). אימתנו בהרצה ישירה בפייתון: `datetime.now(UTC) + timedelta(hours=999999999999)` מייצר `OverflowError`. תרחיש: מנהל שולח `hours` גדול מדי בטעות — `suspend_user()` קורס עם שגיאת שרת לא-מטופלת (500) במקום ולידציה ברורה. תיקון: להוסיף `le=<ערך סביר>` ל-`Field`. | 🟠 גבוה | פתוח |
| AD-07 | `frontend/src/app/features/admin/pending-registrations/pending-registrations.component.ts` (+ `shared/components/confirm-dialog/`) | UX | TBD | הודעת `actionError()` מוצגת בראש התבנית, אך חלון `app-confirm-dialog` הוא שכבת overlay עם `position: fixed; inset: 0; z-index: 1000` שמכסה את כל המסך. ב-`confirmReject()`, כישלון הבקשה קובע `actionError` אך לא סוגר את הדיאלוג — כך שהדיאלוג נשאר פתוח ומכסה את הודעת השגיאה שמאחוריו. תרחיש: מנהל לוחץ "דחייה", הבקשה נכשלת, אך לא רואה שום משוב עד שילחץ "ביטול". אותו דפוס ב-`active-users.component.ts` עם `suspend-dialog`. | 🟠 גבוה | פתוח |
| AD-08 | `frontend/src/app/shared/components/confirm-dialog/confirm-dialog.component.ts` (+ `suspend-dialog.component.ts`) | UX | TBD | שני הדיאלוגים בודקים רק אורך מינימלי בלי בדיקת אורך מקסימלי, בעוד השרת מגביל את אותם שדות ל-`max_length=100`. מנהל שמקליד מעל 100 תווים לא נחסם בצד לקוח, ומגלה את הבעיה רק אחרי שליחה, דרך שגיאת 422. | 🟢 נמוך | פתוח |
| AD-09 | `backend/app/services/audit_service.py::get_audit_log()` | באג | TBD | מעבר לכך ש-`GET /admin/audit-log` עצמו stub (AD-04) — גם פונקציית השירות שמאחוריו, `get_audit_log()`, מקבלת `action_filter`/`entity_type_filter` כפרמטרים אך אף פעם לא מיישמת אותם על ה-query (יש הערת `# TODO` מעל query שמתעלם משניהם) — כשל שקט שיישאר גם אחרי ש-AD-04 יתוקן, אם לא יתוקן גם כאן. | 🟢 נמוך | פתוח |
| AD-10 | `backend/app/api/v1/endpoints/admin.py` | חסר | §3.2 | מעבר לניהול אנשי מקצוע (AD-03) — טבלת ההרשאות (§3.2) מגדירה גם "ניהול מבקרים" ו"ייצוא נתונים" כיכולות מנהל ייעודיות; לשתיהן אין שום מימוש, אפילו לא stub. `AuditAction.MODERATOR_ASSIGNED` ו-`AuditAction.DATA_EXPORTED` מוגדרים ב-`constants.py` אך אף פעם לא בשימוש — אין דרך להקצות `moderator_cells` למבקר דרך ה-API כלל. | 🟡 בינוני | פתוח |

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
| F-05 | `services/forum_service.py` · `endpoints/forum.py` | אבטחה | §4.2 | `create_post()` (שורות 241-279) לא בודק `role` לפני אישור `group_visibility=ALL` או `sector_visibility=ALL` — הקוד מדלג על בדיקת הגבלת קבוצה/מגזר כשהערך הוא ALL, כך שכל משתמש פעיל (לא רק admin/professional) יכול לפרסם שידור רחב לכל הקבוצות/מגזרים, בניגוד מוחלט לאפיון §4.2 שאוסר על user רגיל לפרסם "לקבוצה שלמה, למגזר שלם, ולא ל'כולם'". **[דיוק]:** מחמיר עוד יותר בפועל — `new-post.component.ts` (שורות 59-60) מאתחל את טופס הפרונטאנד עם `group_visibility=ALL` ו-`sector_visibility=ALL` **כברירת מחדל**, כך שמשתמש רגיל שלא נוגע כלל בשתי הרשימות הנפתחות מפרסם באופן שגרתי, בטעות תמימה, לכל המערכת — לא רק תרחיש אפשרי אלא נתיב ברירת-המחדל בפועל. **[דיוק נוסף — היקף רחב יותר]:** §5.1 ב-SPEC.md v3.0 קובע במפורש ש**גם** "שידור לקבוצה" **וגם** "שידור למגזר" (לא רק שידור ל"כולם") מוגבלים ל"מנהל / איש מקצוע בלבד". לפי לוגיקת הקוד (`if data.group_visibility != ALL and (...)`), משתמש רגיל שמגדיר **רק ציר אחד** ל-ALL (למשל `group_visibility=ALL` עם `sector_visibility` השייך לו) כנראה עוקף גם את בדיקת אותו ציר בלבד — כלומר הפרצה עשויה לחול גם על "שידור לקבוצה שלמה" ו"שידור למגזר שלם" בנפרד, לא רק על שילוב ALL+ALL המלא. שווה לאמת ולתקן את שני המקרים. | 🔴 קריטי | פתוח |
| F-06 | `services/forum_service.py` | חסר | §9.3 | `update_post()` (שורות 288-316) מבצע `db.commit()` ישירות ללא קריאה ל-`log_action()` — עריכת הודעה אינה נרשמת ב-Audit Trail, בניגוד ל-`delete_post()` (שורה 179) שכן קורא ל-`log_action()` וב-§9.3 שמחייב תיעוד כל פעולה רגישה | 🟠 גבוה | פתוח |
| F-07 | `backend/app/services/forum_service.py` | ארכיטקטורה | TBD | `_content_filter()` ו-`_matches_content_filter()` משתמשות ב-`assert` לבדיקת `user_type`/`sector` — `assert` מוסר לגמרי תחת `python -O`/`PYTHONOPTIMIZE=1`, מה שהופך את הבדיקה ללא-אמינה. תיקון: להחליף `assert cond, msg` ב-`if not cond: raise AssertionError(msg)`. לא פעיל כרגע (וידאנו: `-O` לא בשימוש בפרויקט), אך סיכון רדום. | 🟡 בינוני | פתוח |
| F-08 | `frontend/src/app/features/forum/edit-post/edit-post.component.ts` (+ `forum-post/forum-post.component.ts`) | באג | TBD | `ngOnInit()` קורא את פרמטר ה-`id` דרך `this.route.snapshot.paramMap.get('id')` — קריאה חד-פעמית, לא הרשמה ל-`paramMap`. אימתנו ב-`app.routes.ts` ששני המסלולים (`:id` ו-`:id/edit`) הם כל אחד רשומת מסלול יחידה, כך שברירת המחדל של Angular (`RouteReuseStrategy`) משתמשת חוזר באותה instance כשעוברים בין שני URL-ים שתואמים לאותה רשומה — ו-`ngOnInit` לא רץ שוב. תרחיש: משתמש עורך פוסט A ב-`/forum/A/edit`, עובר (בלי לצאת מהמסלול) ל-`/forum/B/edit` — `postId` נשאר `'A'`, הטופס עדיין מציג את תוכן פוסט A. עריכה ושמירה **דורסת את פוסט A** בתוכן שהתכוון עבור B, בלי שגיאה ובלי סימן חזותי. תיקון: להירשם ל-`route.paramMap` (Observable) במקום snapshot. | 🔴 קריטי | פתוח |
| F-09 | `backend/app/schemas/forum.py::ForumPostCreate`/`BroadcastCreate` (+ frontend `new-post.component.ts`, `broadcast.component.ts`) | באג | TBD | `Validators.required`/`minLength` באנגולר בודקים אורך מחרוזת גולמי בלי גזירת רווחים (trim); `Field(..., min_length=1)` בשרת גם הוא לא גוזר רווחים. מחרוזת `" "` עוברת את שתי הבדיקות. תרחיש: פוסט עם כותרת/תוכן שהם בפועל רק רווחים מתקבל בהצלחה ומופיע ריק לגמרי. אותה בעיה ב-`broadcast.component.ts`. תיקון: `str_strip_whitespace=True` ב-`model_config` בשרת + טרימה מקבילה בפרונטאנד. | 🟠 גבוה | פתוח |
| F-10 | `backend/app/models/forum.py::ForumPost.reports` (שורות 75-80) | באג | TBD | `primaryjoin="and_(Report.target_id == ForumPost.id, Report.target_type == 'forum_post')"` משווה את `Report.target_type` מול ה-`.value` הנמוך-אותיות של ה-enum. אך SQLAlchemy, בברירת המחדל שלו עבור `Enum(ReportTargetType)`, שומר במסד הנתונים את ה-`.name` (`'FORUM_POST'`) — אימתנו אמפירית מול SQLAlchemy 2.0.51 המותקנת בפרויקט. כתוצאה, `ForumPost.reports` יחזיר תמיד רשימה ריקה. כרגע לא ניתן לניצול כי היחס לא נקרא משום מקום אחר — קוד מת עם באג לוגי חבוי. תיקון: `ReportTargetType.FORUM_POST.name`. | 🟡 בינוני | פתוח |
| F-11 | `backend/app/services/forum_service.py::create_post()` | חסר | §5.2 | §5.2 (שלב 4 בתרשים הזרימה) דורש במפורש שלפני פרסום, המערכת תבדוק "תוכן עומד במדיניות? (בדיקה אוטומטית בסיסית — סריקת מילות מפתח)", לצד בדיקות active/not-suspended. חיפוש מלא בכל הקוד אחר policy/profanity/banned_word/content_check/keyword לא העלה שום התאמה — התכונה נעדרת לגמרי, בלי אפילו TODO שמסמן אותה כמתוכננת. | 🟡 בינוני | פתוח |

---

## M | Moderator

> קבצים עיקריים: `endpoints/moderator.py` · `services/report_service.py`
> · `frontend/src/app/features/moderator/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| M-01 | `services/report_service.py` | אי-דיוק | TBD | `file_report()` (שורה 74) בודק ליטרלית `report_count == 2` במקום לקרוא את `settings.AUTO_HIDE_REPORT_COUNT` — שינוי הסף בקונפיגורציה לא משפיע בפועל על ההסתרה האוטומטית | 🟡 בינוני | פתוח |
| M-02 | `endpoints/moderator.py` | חסר | §7.1–7.3 | כל שלושת נקודות הקצה: `GET /moderator/reports` מחזיר `items=[], total=0, pending_count=0` תמיד; `GET /moderator/reports/{id}` ו-`POST /moderator/reports/{id}/decide` raises `NotImplementedError` — תהליך הטיפול בדיווח (UC-05) לא פועל כלל | 🔴 קריטי | פתוח |
| M-03 | `services/report_service.py` | חסר | §7.2–7.3 | `decide_report()` (שורה 183) ו-`get_pending_reports()` (שורה 197) raises `NotImplementedError`; `_check_auto_suspension()` (שורות 200-211) הוא `pass` — כללי ההשעיה האוטומטית (§7.2: 3 דיווחים מוצדקים ב-7 ימים) לא יופעלו גם לאחר מימוש `decide_report()` בלא תיקון נוסף | 🔴 קריטי | פתוח |
| M-04 | `services/report_service.py` | אי-דיוק | §4.3 / §7.1 | `_moderator_emails_for()` (שורות 145-157) שולח התראת דיווח לכל המבקרים במערכת — מתעלם מ-`moderator_cells` לגמרי. האפיון §4.3 + §7.1 מגדיר שמבקר מקבל התראה רק על דיווחים בתאים שהוגדרו לאחריותו. **[דיוק]:** בנוסף, `forum_service.py::delete_post()` מאפשרת לכל מבקר למחוק כל פוסט במערכת, ללא שום הגבלת תא — אותה בעיית-שורש בדיוק, במקום נוסף שלא מכוסה כאן. | 🟠 גבוה | פתוח |
| M-07 | `backend/app/models/report.py` | ארכיטקטורה | TBD | אין `UniqueConstraint` על `(reporter_id, target_type, target_id)` בטבלת reports. ההגנה מפני דיווח כפול קיימת רק ברמת קוד האפליקציה (`_ensure_not_duplicate_report()`, עם נעילת שורה שמונעת מרוץ במקרה הנוכחי) — אך זו no-op על SQLite, ולא תגן אם ייווספו נתיבי קוד נוספים ליצירת Report (למשל דיווח על DIRECT_MESSAGE/PROFESSIONAL_QUERY). תיקון: `UniqueConstraint` כגיבוי ברמת מסד הנתונים. | 🟢 נמוך | פתוח |
| M-08 | `backend/app/core/config.py` (+ `services/report_service.py`) | אי-דיוק | §7.2 | **אומת במלואו מול טקסט §7.2 ב-SPEC.md v3.0** — המבנה הדו-שכבתי קיים שם ללא שינוי משמעותי: (א) "3+ דיווחים-מוצדקים ב-30 יום" → "התראה למנהל + עיון בהשעיה" (לא אוטומטי); (ב) "2+ אירועים-מוצדקים ב-7 ימים" → "השעיה אוטומטית זמנית (48ש') + התראה למנהל". בפועל `config.py` מגדיר הגדרה אחת בלבד (`AUTO_SUSPEND_VALID_REPORTS=3`, `AUTO_SUSPEND_DAYS_WINDOW=7`) שלוקחת את המספר מדרגה א' (3) ואת החלון מדרגה ב' (7 ימים) ומפעילה עליהם את פעולת דרגה ב' (השעיה אוטומטית) — כלל שלא קיים באפיון בשום צורה. גם M-03 בטבלה זו מתאר את הכלל בתמציתיות כ"3 דיווחים מוצדקים ב-7 ימים" — אותה מיזוג-דרגות-בטעות בדיוק כמו בקוד, לא תיאור מדויק של שני הכללים הנפרדים. תיקון: לפצל ל-2 סטים נפרדים של הגדרות (ספירה+חלון+פעולה) לכל דרגה, גם ב-`config.py` וגם בתיעוד M-03. | 🟠 גבוה | פתוח |
| M-05 | `services/report_service.py` | אבטחה | §4.2 / §7.1 | `file_report()` (שורות 35-89) טוען `ForumPost` לפי ID ישירות ללא `_content_filter()` — משתמש יכול לדווח על הודעות שאינן שייכות לתאו/קבוצתו, ובכך לגלות קיום תוכן חוצה-קבוצות | 🟠 גבוה | פתוח |
| M-06 | `features/moderator/reports/reports.component.ts` | חסר | §7.3 | `ngOnInit()` (שורות 65-68) מגדיר `isLoading = false` מיידית ללא קריאת API; `decide()` (שורות 71-75) לא קורא לשרת — לוח הבקרה מציג רשימה ריקה ולחיצה על "טפל" לא עושה דבר | 🟠 גבוה | פתוח |

---

## P | ייעוץ מקצועי

> קבצים עיקריים: `endpoints/professional.py` · `services/professional_service.py`
> · `frontend/src/app/features/advice/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| P-01 | `features/advice/advice-list/advice-list.component.ts` | ארכיטקטורה | TBD | inline `template` בתוך ה-`.ts` במקום `templateUrl` נפרד — כמו AD-01 | 🟢 נמוך | פתוח |
| P-02 | `services/professional_service.py` | חסר | §6.2–6.3 | `answer_query()` (שורה 190), `get_public_qa()` (שורה 212) ו-`get_pending_questions()` (שורה 244) raises `NotImplementedError` — תשובות מאנשי מקצוע, תצוגת שאלות ממתינות ו-Q&A ציבורי לא פועלים; צד ה-Frontend קיים (my-questions, ask-question) אך לא ניתן לקבל תשובות | 🔴 קריטי | פתוח |
| P-03 | `features/advice/qa-feed/qa-feed.component.ts` | חסר | §6.3 | `loadQA()` (שורות 46-50) מגדיר `isLoading = false` מיידית ללא קריאת API — גם בצד ה-Frontend, תצוגת "ידע קהילתי" (שאלות-תשובות ציבוריות) אינה עובדת | 🟡 בינוני | פתוח |
| P-04 | `frontend/src/app/app.routes.ts` | חסר | TBD | אין route כלשהו לתפקיד PROFESSIONAL (לא path, לא roleGuard) — למרות שהערת התיעוד בראש הקובץ עצמו מבטיחה "Professional: /professional/**". תואם להחלטה ידועה מ-FAB-44 (כרטיס Professional ב-home בלי routerLink פעיל, כי אין route). | 🟡 בינוני | פתוח |
| P-05 | `backend/app/schemas/professional.py::ProfessionalQueryCreate` (+ frontend `ask-question.component.ts`) | באג | §6.2 | `content: str = Field(..., min_length=10, max_length=2000)` בלי `str_strip_whitespace`; באנגולר `Validators.minLength(10)` גם בלי trim. מחרוזת בת 10+ תווי רווח עוברת את שתי הבדיקות. `create_query()` ממומשת במלואה ונגישה דרך `POST /advice/questions` הפעיל. תרחיש: שאלה ריקה בפועל נשמרת, איש/י מקצוע מקבל/ת התראת מייל על שאלה ריקה. אותו דפוס בדיוק כמו F-09. | 🟡 בינוני | פתוח |
| P-06 | `frontend/src/app/core/services/professional.service.ts::getPendingQuestions()`/`answerQuestion()` (+ כלל הפרונטאנד) | חסר | §6.1 | שתי הפונקציות (מסומנות "professional role only") אף פעם לא נקראות משום קומפוננטה בכל הפרונטאנד — פער נבדל מ-P-02 (שעוסק בכך שהשרת עצמו stub): גם אם P-02 יתוקן, אין כרגע שום צרכן UI בצד הלקוח שיציג את זה למשתמש. בשילוב עם P-04 וכרטיס "בקרוב" בעמוד הבית — משתמש PROFESSIONAL שמתחבר אין לו שום פעולה אפשרית במוצר מעבר לצפייה בקטלוג הציבורי, כאילו היה USER. | 🟠 גבוה | פתוח |

---

## DM | הודעות פרטיות

> קבצים עיקריים: `endpoints/messages.py` (עדיין לא קיים — Sprint 5)
> · `frontend/src/app/features/messages/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| DM-01 | `services/forum_service.py` · `endpoints/forum.py` | חסר | §5.3 | כל מחסנית ה-DM לא ממומשת: `send_direct_message()` (שורה 365), `get_conversation()` (שורה 381) ו-`search_users_for_dm()` (שורה 399) raises `NotImplementedError`; `POST /messages` (forum.py שורה 184) raises `NotImplementedError`; `GET /messages` ו-`GET /messages/{user_id}` מחזירים `[]` תמיד. Frontend: `InboxComponent` ו-`ChatComponent` אינם קוראים ל-API כלל | 🔴 קריטי | פתוח |
| DM-02 | `endpoints/users.py` · `core/services/forum.service.ts` | חסר | §5.3 | `GET /users/search` (שורות 26-41) מחזיר `[]` תמיד ללא שאילתת DB; `ForumService.searchUsers()` זורקת `Error` — חיפוש נמען ל-DM (§5.3: "חיפוש לפי שם בלבד בתוך קבוצתו/מגזרו") לא פועל בשני הצדדים | 🟠 גבוה | פתוח |

---

## I | תשתית, DevOps ואבטחה

> קבצים עיקריים: `core/security.py` · `core/dependencies.py`
> · `.github/workflows/` · `docker-compose.yml` · `Dockerfile`s

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| I-01 | `core/security.py` · `core/dependencies.py` | אבטחה | §9.2 | `decode_access_token()` (security.py שורה 19) לא בודק את שדה `type` בתוך ה-JWT — refresh token (תוקף 7 ימים) מתקבל כ-access token תקין בכל endpoint מוגן ב-`get_current_user()`. **[דיוק]:** אימתנו שהקוד כן מיישם את הבדיקה הנכונה **בכיוון ההפוך** — `refresh_token()` בודק `payload.get("type") != "refresh"` ודוחה access token שמנסים להשתמש בו כרענון. הדפוס הנכון כבר קיים וממומש חלקית בקוד, מה שהופך את היעדרו בכיוון השני ל-oversight בולט וקל-לתקן, לא פער תיאורטי-בלבד. | 🔴 קריטי | פתוח |
| I-02 | `core/config.py` | אבטחה | §9.2 | `SECRET_KEY` (שורה 24) בעל ערך דיפולטי ידוע וקבוע בקוד (`dev-secret-change-in-production`), ללא בדיקת startup החוסמת עלייה בפרודקשן עם הערך הזה | 🔴 קריטי | פתוח |
| I-03 | `backend/migrations/versions/91c4a53eec32_initial.py` | באג | §9.3 | ה-`sa.Enum` של `audit_logs.action` (שורה 27) חסר את `USER_PARTIALLY_APPROVED` ו-`BROADCAST_SENT` שבשימוש פעיל ב-`user_service.py`/`forum_service.py` — מול DB עם enum אמיתי (Postgres), אישור הרשמה ראשון או broadcast יכשלו ב-constraint violation (500). **תיקון נתיב:** הקובץ נמצא תחת `backend/migrations/` לא `backend/app/migrations/`. **[דיוק]:** אימתנו גם למה זה לא מתגלה בטסטים: `conftest.py` בונה את הסכימה מ-`Base.metadata.create_all()` (מהמודלים הפייתוניים העדכניים) ולא דרך Alembic — כך שפער ה-migration אף פעם לא בא לידי ביטוי בסביבת הטסטים, גם אם כל שאר הבדיקות עוברות בירוק. | 🔴 קריטי | פתוח |
| I-04 | `services/email_service.py` | ארכיטקטורה | TBD | שגיאות SMTP נתפסות ב-`except Exception` גורף ומתועדות ללוג בלבד ללא alerting — תקלת SMTP מלאה בפרודקשן (OTP / אישור / השעיה) תיכשל בשקט מוחלט וללא התראה לצוות | 🟡 בינוני | פתוח |
| I-05 | `core/security.py` | אבטחה | TBD | `bcrypt` חותך שקט ל-72 בייט (אין `bcrypt__truncate_error=True`) בעוד הסכמה (`schemas/auth.py` שורה 28) מתירה סיסמה עד 128 תווים — שתי סיסמאות שחולקות 72 בייט ראשונים נחשבות זהות | 🟡 בינוני | פתוח |
| I-06 | `core/config.py` · `main.py` | אבטחה | §9.2 | **הרחבה ל-I-02:** מעבר לחוסר ה-validator, אין גם `startup` event ב-FastAPI שחוסם הפעלה עם `SECRET_KEY` ברירת המחדל — deployment לפרודקשן עם הערך `dev-secret-change-in-production` יאפשר לכל מפתח לזייף JWT חתום תקין | 🔴 קריטי | פתוח |
| I-07 | `backend/app/api/v1/router.py` (+ `endpoints/*.py`) | ארכיטקטורה | TBD | prefix/tags מוגדרים לא-אחיד: ברוב קבצי ה-endpoint בתוך `APIRouter()` עצמו, ב-`health.py` דווקא דרך `include_router()` ב-`router.py`. מומלץ לרכז הכל ב-`router.py` כנקודת אמת יחידה לטופולוגיית ה-URL. | 🟢 נמוך | פתוח |
| I-08 | `backend/app/models/audit.py` | אי-דיוק | §9.3 | §9.3 דורש שיומן הביקורת יהיה "append-only (חתומים)". בפועל `AuditLog` הוא טבלה רגילה — בלי עמודת hash/HMAC/חתימה, בלי שרשור לשורה הקודמת. "Append-only" קיים רק כהערת קוד — שום מנגנון DB לא אוכף בפועל שאי אפשר לערוך/למחוק שורות. חשוב לצורך קבילות משפטית (שמירה 7 שנים). תיקון: עמודת hash (HMAC) על תוכן השורה + hash השורה הקודמת (שרשור). | 🟠 גבוה | פתוח |
| I-09 | `backend/app` (כלל הפרויקט — אין scheduler) | חסר | §9.4 | טבלת §9.4 מגדירה 7 קטגוריות נתונים עם תקופת שמירה ופעולה במחיקת חשבון. חיפוש מלא בכל backend אחר cron/scheduled/celery/APScheduler/retention/anonymiz/cleanup/purge לא העלה שום מימוש. הנתונים פשוט מצטברים ללא הגבלה. | 🟡 בינוני | פתוח |
| I-10 | `backend/app/main.py` | חסר | §9.1 | §9.1 דורש HSTS. `main.py` רושם רק `CORSMiddleware` — אין middleware שמוסיף header של Strict-Transport-Security. הסתייגות: ייתכן שזה מטופל ברמת הפריסה (Vercel/Render) — נקודה לבירור, לא בהכרח פער וודאי. | 🟡 בינוני | פתוח |
| I-11 | `backend/app/core/security.py::pwd_context` | אי-דיוק | §9.1 | §9.1 דורש bcrypt עם cost factor ≥ 12. `CryptContext(schemes=["bcrypt"], deprecated="auto")` לא מגדיר `bcrypt__rounds` במפורש — מסתמך על ברירת המחדל של הספרייה (כרגע 12, מתקיים בפועל, אך מרומז ותלוי-גרסה). שונה מ-I-05 (חיתוך שקט ב-72 בייט) — כאן הבעיה היא ה-cost factor עצמו. | 🟢 נמוך | פתוח |
| I-12 | `backend/Dockerfile` | אי-דיוק | §10.2 | `CMD` מקובע ל-port 8000 בצורת exec-form, שלא מבצעת הרחבת `$PORT` — Render מזריק פורט דרך משתנה סביבה `PORT` לשירותי Docker; קונטיינר זה לעולם לא יכול לקרוא אותו. תרחיש: ניסיון פריסה ראשון ל-Render — health check נכשל. תיקון: `CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`. | 🟡 בינוני | פתוח |
| I-13 | `backend/app/core/config.py` (+ `.env.example`) | אי-דיוק | §10.3 | הגדרות אחסון הקבצים לא מזכירות בכלל Cloudflare R2 או Supabase Storage — שני היעדים ש-§10.3 בוחר עבורם במפורש. אין שדה `endpoint_url` שR2 היה דורש. לא חוסם כרגע (אין עדיין קוד העלאה), אך יידרש תיקון קונפיגורציה לפני מימוש ההעלאה. | 🟡 בינוני | פתוח |
| I-14 | `.github/workflows/deploy.yml` | אי-דיוק | §10.1 | job ה-`deploy-frontend` הוא שלד (ידני בלבד) לבניית Docker image ופריסתו — אך §10.1 קובע Vercel כיעד, שפורס ישירות מ-git push, לא מ-image שנדחף. שווה לתקן לפני שהשלד יושלם בכיוון הלא-נכון. | 🟢 נמוך | פתוח |

---

## S | Shared Components & Cross-Cutting

> קומפוננטות משותפות, routing, guards, interceptors, מודלים, Enums

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| S-01 | `src/index.html` | UX | TBD | `<title>` נותר `Frontend` — ערך ברירת המחדל שיצר Angular CLI, לא הוחלף לשם האתר בפועל | 🟢 נמוך | פתוח |
| S-02 | `public/favicon.ico` | UX | TBD | ה-favicon הוא אייקון ברירת המחדל של Angular CLI ולא הוחלף בלוגו/אייקון של האתר | 🟢 נמוך | פתוח |
| S-03 | `src/app/app.html` | ארכיטקטורה | TBD | קובץ template יתום משאריות ה-scaffold של Angular CLI — `App` (`app.ts`) משתמש ב-inline `template` משלו (לא `templateUrl`), כך ש-`app.html` (ובו `<router-outlet />` נוסף, כפול לזה שב-inline template) אינו נטען כלל ואינו מוצג באפליקציה; מומלץ למחיקה | 🟢 נמוך | פתוח |
| S-04 | `src/app/shared/components/button/` | ארכיטקטורה | TBD | `ButtonComponent` (`app-button`) קיימת ומוכנה (4 variants, 3 sizes, loading state) אך אינה בשימוש באף feature באפליקציה — 0 הפניות ל-`<app-button>` בכל ה-templates; קומפוננטות אחרות (למשל `report-button`) בונות `<button>` עצמאי במקום לעשות שימוש חוזר בה, מה שעלול ליצור חוסר עקביות עיצובית/נגישות | 🟢 נמוך | פתוח |
| S-05 | `shared/components/file-upload/file-upload.component.ts` | אבטחה | TBD | `onFileChange()` (שורות 30-53) מאמת גודל קובץ בלבד; ה-`[accept]` הוא רמז UI בדפדפן בלבד וניתן לעקיפה בקלות — אין בדיקת `file.type`/סיומת בפועל לפני `fileSelected.emit()`. **[דיוק]:** קומפוננטה זו משמשת ב-`register.component.html` להעלאת מסמכי זהות. כרגע לא ניתן לניצול בפועל כי `submitStep4()` לא שולח את הקבצים לשרת (אין endpoint להעלאת קבצים כלל), אך שווה תיקון לפני שחיווט ההעלאה ייבנה. | 🟡 בינוני | פתוח |
| S-06 | `src/index.html` | UX | §9.5 | `<html lang="en">` (שורה 2) ללא `dir="rtl"` על ה-root, למרות שכל האפליקציה עברית/RTL — האפיון §9.5 מגדיר במפורש: `<html lang="he" dir="rtl">` על ה-root כחובה חוקית; משפיע על native UI (confirm/autofill), title, וקוראי מסך. **[דיוק]:** מיפינו שה-RTL בפועל מיושם באופן פרטני, ב-3 שיטות שונות ברחבי הקוד, בלי מקור-אמת יחיד: (1) `dir="rtl"` כ-attribute HTML ברוב הקומפוננטות; (2) `direction: rtl` ב-`.scss` בחלק מהן (קבצי ה-`.html` המקבילים חסרי `dir` לגמרי); (3) `style="direction: rtl"` inline בקומפוננטות עם template inline — תבנית שברירית שדף עתידי עלול לשכוח, בלי שום טסט שיתפוס זאת. | 🟠 גבוה | פתוח |
| S-07 | `features/profile/` · `layout/header/` | ארכיטקטורה | TBD | `ProfileComponent` בנוי במלואו ומנותב ל-`/profile`, אך אין אף `routerLink`/קישור אליו בשום מקום באפליקציה — משתמש לא יכול להגיע לפרופיל שלו בלי להקליד URL ידנית | 🟡 בינוני | פתוח |
| S-08 | `frontend/src/app/app.routes.ts` | ארכיטקטורה | §3.2 | מסלולי `/forum` ו-`/advice` משתמשים רק ב-`canActivate: [authGuard]`, בלי `roleGuard(...)` — בעוד השרת מגביל `GET /forum/posts` ל-`role in (USER, ADMIN)` ו-`/advice/questions` ל-USER בלבד. תרחיש: מבקר/איש-מקצוע שמקליד `/forum` ב-URL מקבל 403, וה-error handler הכללי מציג "אירעה שגיאה בטעינת הפוסטים. נסה לרענן" — הודעה מטעה שמרמזת על תקלה זמנית, בעוד הסיבה היא דחיית הרשאה קבועה. | 🟡 בינוני | פתוח |
| S-09 | `backend/app/models/forum.py` (+ שאר המודלים עם timestamps) מול שימושי DatePipe בפרונטאנד | באג | TBD | עמודות `created_at`/`updated_at` מוגדרות כ-`DateTime` בלי `timezone=True` — timestamps "נאיביים", נשלחים ללקוח ללא ציון אזור זמן ב-JSON. לפי ECMA-262, JavaScript מפרש מחרוזת תאריך-ISO בלי offset כזמן מקומי, לא UTC. תרחיש: פוסט שנוצר ב-21:30 UTC יוצג בישראל כ-"21:30" במקום "00:30" למחרת. משפיע על כל תצוגת תאריך/שעה באתר. תיקון: `timezone=True` לכל עמודות ה-DateTime. | 🟠 גבוה | פתוח |
| S-10 | `frontend/src/app/app.config.ts` | UX | TBD | אין `registerLocaleData`/`LOCALE_ID` בשום מקום באפליקציה. כל שימוש ב-`\| date` נופל אוטומטית לברירת המחדל `en-US`, בתוך ממשק עברי/RTL מלא. | 🟡 בינוני | פתוח |

---

## NG | נגישות — WCAG 2.1 AA / תקן ישראלי 5568

> **רקע:** אפיון v3.0 §9.5 מגדיר תאימות תקן ישראלי 5568 / WCAG 2.1 AA כ**דרישת MVP** וחובה חוקית לפי תקנות שוויון זכויות לאנשים עם מוגבלות (2013). כל ממצאי הנגישות הם לפחות 🟠 גבוה.
>
> קבצים עיקריים: `src/index.html` · `features/auth/register/register.component.html`
> · `features/forum/forum-post/forum-post.component.html` · `shared/components/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| NG-01 | `src/index.html` | UX | §9.5 | `<html lang="en">` ללא `dir="rtl"` — האפיון דורש במפורש `<html lang="he" dir="rtl">` כחובה חוקית; קוראי מסך מכריזים על השפה כאנגלית וממיינים RTL שגוי. (ראו גם S-06) | 🟠 גבוה | פתוח |
| NG-02 | `features/auth/register/register.component.html` | UX | §9.5 | אינדיקטור שלב ההרשמה (`<p>שלב {{ currentStep() }} מתוך 4</p>`) ללא `aria-live="polite"` ו-`aria-current` — מעבר בין שלבים אינו מוכרז לקורא מסך; משתמשי מקלדת/עיוורים אינם יודעים שהטופס השתנה | 🟠 גבוה | פתוח |
| NG-03 | `shared/components/` · כל ה-features | UX | §9.5 | הודעות שגיאה (`<app-error-display>`) ומצבי טעינה (`<app-loading-spinner>`) מוצגים ויזואלית אך ללא `role="alert"` / `aria-live="assertive"` — קוראי מסך אינם מכריזים על שגיאות בזמן אמת. **[דיוק/תיקון]:** אימתנו ש-`error-display.component.ts` **עצמו** כן מגדיר נכון `role="alert"` — הרכיב המשותף תקין. הבאג האמיתי הוא **שימוש לא-עקבי** בו: `pending-registrations.component.ts` מציגה שגיאת פעולה כ-`<p class="error-message">` גולמי בלי `role="alert"` במקום להשתמש ב-`<app-error-display>` (בעוד `active-users.component.html` כן משתמשת בו נכון לאותו סוג שגיאה), וכנ"ל הודעת הצלחה גולמית ב-`broadcast.component.html`. תיקון: להשתמש ב-`<app-error-display>`/רכיב מקביל באופן עקבי בכל המסכים, לא לתקן את הרכיב המשותף עצמו. | 🟠 גבוה | פתוח |
| NG-04 | `forum-post.component.html` · `reports.component.ts` | UX | §9.5 | כפתורי פעולה ("מחק", "ערוך", "דיווח") ללא `aria-label` מפורש — כפתורים הנשענים על טקסט גלוי בלבד אינם נגישים כשהטקסט תלוי בהקשר ויזואלי | 🟡 בינוני | פתוח |
| NG-05 | `shared/components/file-upload/file-upload.component.ts` | UX | §9.5 | רכיב העלאת קבצים (הרשמה) ללא `aria-label` על שדה הקובץ ו-`aria-describedby` לתיאור סוגי הקבצים המותרים — משתמשי קורא מסך אינם יודעים מה להעלות | 🟡 בינוני | פתוח |
| NG-06 | `src/index.html` · `frontend/angular.json` | UX | §9.6 | **דרישת פריסה חדשה (v3.0 §9.6):** יש לוודא שכל CSS/JS/פונטים self-hosted ולא נטענים מ-CDN חיצוני (Google Fonts, jsdelivr וכד') — נטפרי חוסם CDNs לעתים; טרם נבדק בבנייה אמיתית לפרודקשן | 🟡 בינוני | פתוח |
| NG-07 | `frontend/src/app/shared/components/confirm-dialog/`, `suspend-dialog/`, `report-button/` (תבניות הדיאלוג) | UX | §9.5 | שלושת קומפוננטות הדיאלוג (משמשות למחיקת פוסט, דחיית הרשמה, השעיית משתמש, ודיווח על תוכן — כל פעולה הרסנית/חשובה במוצר) חסרות `role="dialog"`, `aria-modal`, ניהול focus (focus trap), ויציאה במקש Escape. חיפוש מלא בפרונטאנד לא העלה שום התאמה לאף אחד מהם. תרחיש: משתמש/ת קורא-מסך שמפעיל/ה "מחיקה" לא מקבל/ת שום הכרזה שנפתח דיאלוג; משתמש/ת מקלדת עובר/ת ב-Tab היישר דרך הדיאלוג לתוכן שמאחוריו. בעיה מערכתית בכל זרימת אישור/הרסני במוצר — רלוונטי ישירות לדרישת ה-MVP של §9.5. | 🟠 גבוה | פתוח |
