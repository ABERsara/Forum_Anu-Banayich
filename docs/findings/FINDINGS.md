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
| A-07 | `services/auth_service.py` | אבטחה | §9.2 | `verify_otp()` (שורה 92) ללא הגבלת ניסיונות/קצב — קוד בן 6 ספרות ניתן לניחוש בברוטפורס בתוך חלון התוקף של 10 דקות | 🔴 קריטי | פתוח |
| A-08 | `core/guards/role.guard.ts` | באג | TBD | `roleGuard` (שורות 21-25) בודק `auth.currentUser()` באופן סינכרוני בעוד `loadCurrentUser()` עדיין רץ אסינכרונית מה-constructor של `AuthService` — ברענון דף / רשת איטית, אדמין/מבקר מחובר לגמרי מנותק חזרה ל-`/login` | 🟠 גבוה | פתוח |
| A-09 | `core/services/auth.service.ts` | באג | TBD | signal `currentUser` (שורות 127-129) מתעדכן רק ב-login/bootstrap ולא מתרענן אחרי שינוי סטטוס/תפקיד בשרת — משתמש שאושר/שונה תפקידו ע"י אדמין בזמן שהיה מחובר נשאר נעול על ההרשאות הישנות עד רענון דף מלא | 🟡 בינוני | פתוח |
| A-10 | `features/auth/register/register.component.html` | UX | TBD | טופס הרשמה שלב 2 (שורות 79-84) — שדה סיסמה יחיד ללא שדה אימות/השוואה; טעות הקלדה מתגלה רק בניסיון ההתחברות הראשון | 🟡 בינוני | פתוח |
| A-11 | `services/auth_service.py` | אבטחה | §9.1 | `_generate_otp()` (שורות 13, 30) משתמש ב-`random.choices` (Mersenne Twister) במקום `secrets` (CSPRNG) ליצירת קוד ה-OTP בן 6 הספרות | 🟠 גבוה | פתוח |
| A-12 | `models/user.py` · `services/auth_service.py` | אבטחה | §2.1 | אין אילוץ ייחודיות (לא באפליקציה, לא ב-DB) על `id_number` או `phone` — רק `email` נבדק; אותה ת"ז יכולה להירשם תחת כמה חשבונות שונים | 🟠 גבוה | פתוח |
| A-13 | `core/guards/auth.guard.ts` | אבטחה | §8.4 | `authGuard` (שורות 12-29) מטפל רק ב-`PENDING_APPROVAL`/`PARTIALLY_APPROVED`, לא ב-`SUSPENDED`/`REJECTED`/`CANCELLED` — משתמש בסטטוס כזה עלול להיכנס לאזורים מוגנים ללא הפניה למסך הסבר | 🟠 גבוה | פתוח |
| A-14 | `core/interceptors/auth.interceptor.ts` | ארכיטקטורה | §9.2 | `authInterceptor` (שורות 13-33) ללא נעילת single-flight סביב רענון טוקן — בקשות 401 מקבילות מפעילות כל אחת `refreshToken()` נפרד; אם refresh token מתחלף (rotation), עלול לגרום logout שגוי של session תקף | 🟠 גבוה | פתוח |
| A-15 | `models/user.py` · `services/auth_service.py` | אבטחה | §9.1 | `email`/`id_number`/`phone` מתועדים `# encrypted` (models/user.py שורות 50-72) ומפנים ל"encryption helpers" ב-auth_service.py, אך `register()` (שורות 54-80) לא מבצע כל הצפנה — נשמרים בטקסט גלוי ב-DB | 🔴 קריטי | פתוח |
| A-16 | `endpoints/users.py` | חסר | §9.7 | `DELETE /users/me` (שורות 44-58) — `delete_my_account()` מכילה `pass` בלבד: הבקשה מצליחה (204) ללא כל פעולה בפועל — המשתמש לא נמחק, נתוניו לא מוסרים, Audit Log לא נרשם. זכות המחיקה לפי GDPR (§9.7) נכשלת בשקט | 🔴 קריטי | פתוח |
| A-17 | `backend/migrations/versions/91c4a53eec32_initial.py` | אבטחה | §9.1 | `otp_code` מאוחסן ב-DB כ-`String(10)` טקסט גלוי — קוד OTP לא מגובב (hash) בטבלת users; גישה ישירה לDB חושפת קודי OTP פעילים | 🟠 גבוה | פתוח |
| A-18 | `services/auth_service.py` · `endpoints/auth.py` | חסר | §8.1 | `register()` לא מאמת גיל מינימום 18+ בצד השרת — `birth_date` נשמר אך אין בדיקה שהמשתמש מלאו 18 שנים; האפיון §8.1 מגדיר "חובה: 18+ בעת ההרשמה" | 🟠 גבוה | פתוח |

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
| F-05 | `services/forum_service.py` · `endpoints/forum.py` | אבטחה | §4.2 | `create_post()` (שורות 241-279) לא בודק `role` לפני אישור `group_visibility=ALL` או `sector_visibility=ALL` — הקוד מדלג על בדיקת הגבלת קבוצה/מגזר כשהערך הוא ALL, כך שכל משתמש פעיל (לא רק admin/professional) יכול לפרסם שידור רחב לכל הקבוצות/מגזרים, בניגוד מוחלט לאפיון §4.2 שאוסר על user רגיל לפרסם "לקבוצה שלמה, למגזר שלם, ולא ל'כולם'" | 🔴 קריטי | פתוח |
| F-06 | `services/forum_service.py` | חסר | §9.3 | `update_post()` (שורות 288-316) מבצע `db.commit()` ישירות ללא קריאה ל-`log_action()` — עריכת הודעה אינה נרשמת ב-Audit Trail, בניגוד ל-`delete_post()` (שורה 179) שכן קורא ל-`log_action()` וב-§9.3 שמחייב תיעוד כל פעולה רגישה | 🟠 גבוה | פתוח |

---

## M | Moderator

> קבצים עיקריים: `endpoints/moderator.py` · `services/report_service.py`
> · `frontend/src/app/features/moderator/`

| # | קובץ / קומפוננטה | סוג | סעיף | תיאור הממצא | חומרה | סטטוס |
|---|---|---|---|---|---|---|
| M-01 | `services/report_service.py` | אי-דיוק | TBD | `file_report()` (שורה 74) בודק ליטרלית `report_count == 2` במקום לקרוא את `settings.AUTO_HIDE_REPORT_COUNT` — שינוי הסף בקונפיגורציה לא משפיע בפועל על ההסתרה האוטומטית | 🟡 בינוני | פתוח |
| M-02 | `endpoints/moderator.py` | חסר | §7.1–7.3 | כל שלושת נקודות הקצה: `GET /moderator/reports` מחזיר `items=[], total=0, pending_count=0` תמיד; `GET /moderator/reports/{id}` ו-`POST /moderator/reports/{id}/decide` raises `NotImplementedError` — תהליך הטיפול בדיווח (UC-05) לא פועל כלל | 🔴 קריטי | פתוח |
| M-03 | `services/report_service.py` | חסר | §7.2–7.3 | `decide_report()` (שורה 183) ו-`get_pending_reports()` (שורה 197) raises `NotImplementedError`; `_check_auto_suspension()` (שורות 200-211) הוא `pass` — כללי ההשעיה האוטומטית (§7.2: 3 דיווחים מוצדקים ב-7 ימים) לא יופעלו גם לאחר מימוש `decide_report()` בלא תיקון נוסף | 🔴 קריטי | פתוח |
| M-04 | `services/report_service.py` | אי-דיוק | §4.3 / §7.1 | `_moderator_emails_for()` (שורות 145-157) שולח התראת דיווח לכל המבקרים במערכת — מתעלם מ-`moderator_cells` לגמרי. האפיון §4.3 + §7.1 מגדיר שמבקר מקבל התראה רק על דיווחים בתאים שהוגדרו לאחריותו | 🟠 גבוה | פתוח |
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
| I-01 | `core/security.py` · `core/dependencies.py` | אבטחה | §9.2 | `decode_access_token()` (security.py שורה 19) לא בודק את שדה `type` בתוך ה-JWT — refresh token (תוקף 7 ימים) מתקבל כ-access token תקין בכל endpoint מוגן ב-`get_current_user()` | 🔴 קריטי | פתוח |
| I-02 | `core/config.py` | אבטחה | §9.2 | `SECRET_KEY` (שורה 24) בעל ערך דיפולטי ידוע וקבוע בקוד (`dev-secret-change-in-production`), ללא בדיקת startup החוסמת עלייה בפרודקשן עם הערך הזה | 🔴 קריטי | פתוח |
| I-03 | `backend/migrations/versions/91c4a53eec32_initial.py` | באג | §9.3 | ה-`sa.Enum` של `audit_logs.action` (שורה 27) חסר את `USER_PARTIALLY_APPROVED` ו-`BROADCAST_SENT` שבשימוש פעיל ב-`user_service.py`/`forum_service.py` — מול DB עם enum אמיתי (Postgres), אישור הרשמה ראשון או broadcast יכשלו ב-constraint violation (500). **תיקון נתיב:** הקובץ נמצא תחת `backend/migrations/` לא `backend/app/migrations/` | 🔴 קריטי | פתוח |
| I-04 | `services/email_service.py` | ארכיטקטורה | TBD | שגיאות SMTP נתפסות ב-`except Exception` גורף ומתועדות ללוג בלבד ללא alerting — תקלת SMTP מלאה בפרודקשן (OTP / אישור / השעיה) תיכשל בשקט מוחלט וללא התראה לצוות | 🟡 בינוני | פתוח |
| I-05 | `core/security.py` | אבטחה | TBD | `bcrypt` חותך שקט ל-72 בייט (אין `bcrypt__truncate_error=True`) בעוד הסכמה (`schemas/auth.py` שורה 28) מתירה סיסמה עד 128 תווים — שתי סיסמאות שחולקות 72 בייט ראשונים נחשבות זהות | 🟡 בינוני | פתוח |
| I-06 | `core/config.py` · `main.py` | אבטחה | §9.2 | **הרחבה ל-I-02:** מעבר לחוסר ה-validator, אין גם `startup` event ב-FastAPI שחוסם הפעלה עם `SECRET_KEY` ברירת המחדל — deployment לפרודקשן עם הערך `dev-secret-change-in-production` יאפשר לכל מפתח לזייף JWT חתום תקין | 🔴 קריטי | פתוח |

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
| S-06 | `src/index.html` | UX | §9.5 | `<html lang="en">` (שורה 2) ללא `dir="rtl"` על ה-root, למרות שכל האפליקציה עברית/RTL — האפיון §9.5 מגדיר במפורש: `<html lang="he" dir="rtl">` על ה-root כחובה חוקית; משפיע על native UI (confirm/autofill), title, וקוראי מסך | 🟠 גבוה | פתוח |
| S-07 | `features/profile/` · `layout/header/` | ארכיטקטורה | TBD | `ProfileComponent` בנוי במלואו ומנותב ל-`/profile`, אך אין אף `routerLink`/קישור אליו בשום מקום באפליקציה — משתמש לא יכול להגיע לפרופיל שלו בלי להקליד URL ידנית | 🟡 בינוני | פתוח |

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
| NG-03 | `shared/components/` · כל ה-features | UX | §9.5 | הודעות שגיאה (`<app-error-display>`) ומצבי טעינה (`<app-loading-spinner>`) מוצגים ויזואלית אך ללא `role="alert"` / `aria-live="assertive"` — קוראי מסך אינם מכריזים על שגיאות בזמן אמת | 🟠 גבוה | פתוח |
| NG-04 | `forum-post.component.html` · `reports.component.ts` | UX | §9.5 | כפתורי פעולה ("מחק", "ערוך", "דיווח") ללא `aria-label` מפורש — כפתורים הנשענים על טקסט גלוי בלבד אינם נגישים כשהטקסט תלוי בהקשר ויזואלי | 🟡 בינוני | פתוח |
| NG-05 | `shared/components/file-upload/file-upload.component.ts` | UX | §9.5 | רכיב העלאת קבצים (הרשמה) ללא `aria-label` על שדה הקובץ ו-`aria-describedby` לתיאור סוגי הקבצים המותרים — משתמשי קורא מסך אינם יודעים מה להעלות | 🟡 בינוני | פתוח |
| NG-06 | `src/index.html` · `frontend/angular.json` | UX | §9.6 | **דרישת פריסה חדשה (v3.0 §9.6):** יש לוודא שכל CSS/JS/פונטים self-hosted ולא נטענים מ-CDN חיצוני (Google Fonts, jsdelivr וכד') — נטפרי חוסם CDNs לעתים; טרם נבדק בבנייה אמיתית לפרודקשן | 🟡 בינוני | פתוח |
