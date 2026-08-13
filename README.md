# עמותת "אנו בניך" – מערכת קהילה ופורום דיגיטלי

פלטפורמת תמיכה, קהילה, פורום וייעוץ מקצועי לאלמנים, אלמנות, יתומים ויתומות.

> Fullstack: **Angular 22** (frontend) + **FastAPI / Python** (backend) | אפיון גרסה 3.0 — אוגוסט 2026

---

## תוכן עניינים

1. [סקירת הפרויקט](#1-סקירת-הפרויקט)
2. [טכנולוגיות](#2-טכנולוגיות)
3. [הרצה מקומית – שלב אחר שלב](#3-הרצה-מקומית--שלב-אחר-שלב)
4. [מבנה הפרויקט](#4-מבנה-הפרויקט)
5. [ארכיטקטורה](#5-ארכיטקטורה)
6. [תפקידים במערכת (RBAC)](#6-תפקידים-במערכת-rbac)
7. [מודולים ראשיים](#7-מודולים-ראשיים)
8. [API – נקודות קצה](#8-api--נקודות-קצה)
9. [מדיניות שמירת נתונים](#9-מדיניות-שמירת-נתונים)
10. [כללי עבודה ו-Git](#10-כללי-עבודה-ו-git)
11. [Scripts שימושיים](#11-scripts-שימושיים)

---

## 1. סקירת הפרויקט

המערכת היא פלטפורמה **מאובטחת** שמשמשת כמרחב תמיכה לאוכלוסיות שכול.

### עקרונות יסוד – חשוב להבין לפני הכל!

| עקרון | הסבר |
|-------|-------|
| **הפרדה בין קבוצות** | אלמנים / אלמנות / יתומים / יתומות – כל קבוצה לא רואה תוכן של קבוצה אחרת |
| **הפרדה בין מגזרים** | חסידי / ליטאי / ספרדי / כללי – כל מגזר מרחב נפרד |
| **אימות קפדני** | הרשמה מחייבת אישור **2 מנהלים** + מסמכים (תעודת פטירה, ת"ז) |
| **פרטיות כברירת מחדל** | מידע אישי ומסמכים מוצפנים. מנהל **לא** יכול לקרוא הודעות פרטיות |
| **Audit Trail מלא** | כל פעולה מנהלתית ורגישה נרשמת — מי, מה, מתי, מאיפה |

### מטריצת קבוצות-מגזרים (16 "תאים")

| קבוצה \ מגזר | חסידי | ליטאי | ספרדי | כללי |
|-------------|-------|-------|-------|------|
| אלמנים | תא 1א | תא 1ב | תא 1ג | תא 1ד |
| אלמנות | תא 2א | תא 2ב | תא 2ג | תא 2ד |
| יתומים | תא 3א | תא 3ב | תא 3ג | תא 3ד |
| יתומות | תא 4א | תא 4ב | תא 4ג | תא 4ד |

> כל משתמש/ת שייך/ת לתא **אחד בלבד**. התוכן שהוא/היא רואה מסוננות אוטומטית בבאקאנד.

---

## 2. טכנולוגיות

| שכבה | טכנולוגיה | גרסה |
|------|-----------|-------|
| Frontend | Angular (standalone components) | 22 |
| Styling | SCSS + RTL (עברית) | — |
| Backend | FastAPI (Python) | 0.111+ |
| ORM | SQLAlchemy | 2.0 |
| Schemas | Pydantic | v2 |
| Migrations | Alembic | 1.13+ |
| Auth | JWT (python-jose) + bcrypt (cost ≥ 12) | — |
| OAuth (מתוכנן) | Firebase Authentication (Google Sign-In) | — |
| DB (פיתוח) | SQLite | — |
| DB (ייצור) | PostgreSQL (Managed) | — |
| Linting BE | Ruff + mypy | — |
| Linting FE | ESLint + Prettier | — |
| אירוח Frontend | Vercel | — |
| אירוח Backend | Render (Web Service) | — |
| אחסון קבצים | Cloudflare R2 / Supabase Storage | — |

---

## 3. הרצה מקומית – שלב אחר שלב

### דרישות מוקדמות
- Python 3.11+
- Node.js 20+ + npm
- Git

---

### Backend (FastAPI)

```bash
# שלב 1 – עבור לתיקיית הבאקאנד
cd backend

# שלב 2 – צור סביבה וירטואלית (עושים פעם אחת)
python -m venv .venv

# שלב 3 – הפעל את הסביבה (עושים בכל פתיחת terminal)
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# שלב 4 – התקן תלויות (עושים פעם אחת, או כשמשהו נוסף)
pip install -e ".[dev]"

# שלב 5 – צור קובץ .env מהדוגמה (עושים פעם אחת)
cp .env.example .env
# פתח את .env ותמלאי ערכים אמיתיים

# שלב 6 – הרץ migrations (יצירת טבלאות ב-DB)
alembic upgrade head

# שלב 7 – הרץ את השרת
uvicorn app.main:app --reload --port 8000
```

✅ השרת יעלה בכתובת: `http://localhost:8000`
📖 תיעוד API אינטראקטיבי: `http://localhost:8000/api/v1/docs`

---

### Frontend (Angular)

```bash
# פתחי terminal חדש (נפרד מהבאקאנד!)

# שלב 1 – עברי לתיקיית הפרונטאנד
cd frontend

# שלב 2 – התקיני תלויות (פעם אחת)
npm install

# שלב 3 – הריצי את האפליקציה
npm start
```

✅ האפליקציה תעלה בכתובת: `http://localhost:4200`

---

## 4. מבנה הפרויקט

```
practicum-web/
│
├── README.md                        ← אתן כאן
├── docker-compose.yml               ← הרצה עם Docker (אופציונלי)
├── CHECKLIST.md                     ← רשימת בדיקות לפני PR
│
├── frontend/                        ← Angular app
│   └── src/
│       ├── environments/            ← הגדרות פיתוח/ייצור (apiUrl)
│       └── app/
│           ├── core/                ← תשתית – לא נוגעים לעתים קרובות
│           │   ├── constants/
│           │   │   └── index.ts     ← ⭐ כל ה-ENUMS (UserType, Sector...)
│           │   ├── models/
│           │   │   └── index.ts     ← ⭐ כל ה-TypeScript interfaces
│           │   ├── services/        ← HTTP services (אחד לכל פיצ'ר)
│           │   │   ├── api.service.ts
│           │   │   ├── auth.service.ts
│           │   │   ├── forum.service.ts
│           │   │   ├── professional.service.ts
│           │   │   └── report.service.ts
│           │   ├── guards/
│           │   │   ├── auth.guard.ts
│           │   │   └── role.guard.ts
│           │   └── interceptors/
│           │       └── auth.interceptor.ts
│           │
│           ├── features/            ← ⭐ כאן עיקר העבודה
│           │   ├── auth/
│           │   │   ├── login/
│           │   │   └── register/    ← טופס הרשמה רב-שלבי
│           │   ├── forum/
│           │   │   ├── forum-list/
│           │   │   ├── forum-post/
│           │   │   └── new-post/
│           │   ├── advice/
│           │   │   ├── advice-list/
│           │   │   ├── ask-question/
│           │   │   └── qa-feed/
│           │   ├── messages/
│           │   │   ├── inbox/
│           │   │   └── chat/
│           │   ├── profile/
│           │   ├── admin/
│           │   │   ├── dashboard/
│           │   │   ├── pending-registrations/
│           │   │   ├── manage-professionals/
│           │   │   └── audit-log/
│           │   └── moderator/
│           │       └── reports/
│           │
│           ├── layout/
│           │   └── header/
│           └── shared/
│               └── components/
│
└── backend/                         ← FastAPI app
    └── app/
        ├── main.py
        ├── core/
        │   ├── config.py
        │   ├── constants.py         ← ⭐ Python Enums (UserType, Sector...)
        │   ├── security.py          ← JWT + bcrypt
        │   └── dependencies.py      ← get_db(), get_current_user()
        ├── db/
        │   ├── base.py
        │   └── session.py
        ├── models/                  ← ⭐ SQLAlchemy ORM
        │   ├── user.py
        │   ├── forum.py
        │   ├── professional.py
        │   ├── report.py
        │   ├── document.py
        │   └── audit.py
        ├── schemas/                 ← ⭐ Pydantic
        │   ├── auth.py
        │   ├── user.py
        │   ├── forum.py
        │   ├── professional.py
        │   └── report.py
        ├── services/                ← ⭐ לוגיקה עסקית
        │   ├── auth_service.py
        │   ├── user_service.py
        │   ├── forum_service.py
        │   ├── professional_service.py
        │   ├── report_service.py
        │   ├── audit_service.py
        │   └── email_service.py
        ├── api/v1/
        │   ├── router.py
        │   └── endpoints/
        │       ├── auth.py
        │       ├── users.py
        │       ├── forum.py
        │       ├── professional.py
        │       ├── reports.py
        │       ├── admin.py
        │       └── moderator.py
        └── tests/
```

---

## 5. ארכיטקטורה

### זרימת בקשה רגילה

```
Browser (Angular)
    │
    │  1. לחיצה של משתמש → Angular service מכין request
    ▼
Auth Interceptor → מוסיף JWT header לבקשה
    │
    ▼
FastAPI Backend (port 8000)
    │
    │  2. middleware מאמת JWT → מזהה מי המשתמש
    │  3. dependency injection מחבר session ל-DB
    │  4. endpoint קורא ל-service
    │  5. service מבצע לוגיקה עסקית + שאילתות DB עם סינון
    ▼
SQLite (פיתוח) / PostgreSQL (ייצור)
    │
    ▼
JSON Response → Angular מעדכן UI
```

### פריסה בסביבת ייצור

```
Vercel (Frontend)          Render (Backend)
  Angular build       →      FastAPI Web Service
  CDN + HTTPS               PostgreSQL Managed
  Preview Deployments       Environment Variables (מוצפנים)
        │                          │
        └──────── HTTPS ───────────┘
                       │
              Cloudflare R2 / Supabase Storage
              (מסמכי הרשמה, presigned URLs, AES-256)
```

> הערה: בשלב הראשוני נעשה שימוש ב-Free Tier. יש לבדוק מגבלות bandwidth ו-cold start בפועל מול נפח השימוש הצפוי.

### מנגנון סינון תוכן (⚠️ קריטי!)

כל שורת תוכן בDB (פוסט, שאלה) כוללת שני שדות:
- `group_visibility` – לאיזו קבוצה (אלמנים/אלמנות/יתומים/יתומות/כולם)
- `sector_visibility` – לאיזה מגזר (חסידי/ליטאי/ספרדי/כללי/כולם)

הבאקאנד **תמיד** מסנן לפי פרופיל המשתמש המחובר. **אין דרך לעקוף את זה.**

```python
# דוגמה לסינון ב-forum_service.py
posts = db.query(ForumPost).filter(
    or_(
        ForumPost.group_visibility == GroupVisibility.ALL,
        ForumPost.group_visibility == current_user.user_type,
    ),
    or_(
        ForumPost.sector_visibility == SectorVisibility.ALL,
        ForumPost.sector_visibility == current_user.sector,
    )
).all()
```

---

## 6. תפקידים במערכת (RBAC)

| תפקיד | ערך ב-DB | מה רואה | מה יכול |
|--------|----------|---------|---------|
| **USER** | `user` | תוכן של הקבוצה+מגזר **שלו בלבד** | לפרסם, לשאול, לדווח |
| **ADMIN** | `admin` | הכל (לצורכי ניהול) | לאשר הרשמות, לנהל מקצוענים, Audit Log |
| **MODERATOR** | `moderator` | דיווחים בתאים שאחראי עליהם | למחוק הודעות, להשעות משתמשים |
| **PROFESSIONAL** | `professional` | שאלות מופנות אליו/לתחומו | לענות על שאלות מקצועיות |

> ⚠️ **חשוב:** מנהל **לא** יכול לקרוא הודעות פרטיות של משתמשים (הגנת פרטיות מוחלטת)

### JWT
- Access token: תוקף 15 דקות
- Refresh token: תוקף 7 ימים
- ביטול מיידי עם השעיה/ביטול חשבון

---

## 7. מודולים ראשיים

### מודול הרשמה ואימות

```
שלבים: טופס → OTP → העלאת מסמכים → המתנה → 2 מנהלים מאשרים → פעיל
```

**מודל אישור מנהלים (Parallel — מומלץ):**
שני מנהלים מקבלים התראה בו-זמנית ומאשרים באופן עצמאי.
SLA: 72 שעות. לאחר 7 ימים ללא פעולה — התראה למנהל בכיר.

| סטטוס | משמעות |
|-------|--------|
| `ממתין_לאימות` | ממתין לאימות מייל/טלפון (OTP) |
| `ממתין_לאישור` | הוגשה, ממתין לשני מנהלים |
| `אושר_חלקית` | מנהל אחד אישר |
| `פעיל` | שני מנהלים אישרו |
| `נדחה` | אחד/שניים דחו — אפשרות ערעור 30 יום |
| `מושעה` | מנהל/מבקר השעה |
| `מבוטל` | המשתמש ביקש מחיקה (GDPR) |

קבצי backend: `endpoints/auth.py`, `services/auth_service.py`
קבצי frontend: `features/auth/`

#### כניסה עם Google — מתוכנן לספרינט הבא

Google אחראי על אימות המייל, ולכן שלב OTP מדולג. שאר תהליך ההרשמה (מסמכים + אישור 2 מנהלים) נשאר זהה.

**זרימה — משתמש חדש:**
```
לחיצה "כניסה עם Google"
  → Firebase popup → ID token
  → POST /auth/google  (backend מאמת מול Google)
  → type="registration_required" → redirect לטופס הרשמה עם מייל+שם ממולאים מראש
  → User ממלא שאר שדות + מסמכים
  → POST /auth/google/register (ללא OTP, ישר ל-PENDING_APPROVAL)
  → ממתין לאישור 2 מנהלים
```

**זרימה — משתמש קיים ופעיל:**
```
לחיצה "כניסה עם Google"
  → Firebase popup → ID token
  → POST /auth/google → type="login" → JWT pair → כניסה מיידית
```

**מה צריך לממש:**

| צד | קבצים | שינוי |
|----|-------|-------|
| Backend | `models/user.py` | הפוך `password_hash` ל-nullable; הוסף `google_uid` |
| Backend | `core/security.py` | הוסף `verify_firebase_token()` (httpx + python-jose) |
| Backend | `schemas/auth.py` | הוסף `GoogleAuthRequest`, `GoogleRegisterRequest`, `GoogleAuthResponse` |
| Backend | `services/auth_service.py` | הוסף `google_login_or_check()`, `google_register()`; תקן `login()` |
| Backend | `api/v1/endpoints/auth.py` | הוסף `POST /auth/google`, `POST /auth/google/register` |
| Backend | `core/config.py` | הוסף `FIREBASE_PROJECT_ID: str` |
| Backend | Alembic migration | `password_hash` nullable + עמודת `google_uid` |
| Frontend | `package.json` | `npm install firebase` |
| Frontend | `environments/environment*.ts` | הוסף `firebaseConfig` (apiKey, authDomain, projectId) |
| Frontend | `core/firebase.config.ts` (חדש) | `initializeApp(environment.firebaseConfig)` |
| Frontend | `core/models/index.ts` | הוסף `GoogleAuthResponse`, `GoogleRegisterRequest` |
| Frontend | `core/services/auth.service.ts` | הוסף `loginWithGoogle()`, `googleRegister()` |
| Frontend | `features/auth/login/` | הוסף כפתור "כניסה עם Google" |
| Frontend | `features/auth/register/` | טיפול ב-`?via=google` — מלא מראש, דלג על OTP |

> **הגדרת Firebase:** Firebase Console → Authentication → Sign-in method → Google → Enable.
> מפתחות ה-Firebase שייכים ל-`environment.ts` בלבד — **אסור ל-`.env` ולבאקאנד לאחסן את ה-API key הפומבי של Firebase.** הבאקאנד צריך רק את `FIREBASE_PROJECT_ID` לאימות ה-token.

---

### מודול פורום

```
פרסום: לתא שלי (USER) / לכל הקבוצה / לכל המגזר (מנהל/מקצוען בלבד) — אין "לכולם"
מוצפן. עד 5,000 תווים + קובץ עד 5MB (PDF/תמונה)
```

קבצי backend: `endpoints/forum.py`, `services/forum_service.py`
קבצי frontend: `features/forum/`

---

### מודול הודעות פרטיות

```
חיפוש נמען בתוך קבוצה/מגזר בלבד — אין חיפוש חוצה-קבוצות
מוצפן בשרת (server-side encryption), לא נגיש למנהל ולמבקר
```

- **מגבלת אחסון:** עד 1,000 הודעות לשיחה; ניקוי אוטומטי לאחר 3 שנים
- **מה"ק:** לאחר מספר דיווחים חוזרים על אותו שולח — הגבלת שימוש זמנית אוטומטית, לבחינת מבקר
- **E2E encryption:** מתוכנן לגרסה 2 (בשלב זה: server-side)

קבצי frontend: `features/messages/`

---

### מודול ייעוץ מקצועי

```
קטלוג: עו"ד, רו"ח, פסיכולוג, יועץ כלכלי, רב/דיין, רפואה, סוציאל וורקר
שאלה פרטית / ציבורית. ציבורית = "ידע קהילתי" גלוי לכל חברי הקבוצה/מגזר
```

- **הגנת פרטיות:** שם השואל מוצג לאיש המקצוע כינוי בלבד ("אלמנה — ספרדי"), אלא אם השואל בחר לחשוף שמו
- **שאלה כללית:** מייל לכל אנשי המקצוע בתחום, עם ציון שמדובר בשאלה כללית

קבצי backend: `endpoints/professional.py`, `services/professional_service.py`
קבצי frontend: `features/advice/`

---

### מודול דיווח והגנה קהילתית

**זרימת דיווח:**
| מצב | פעולה |
|-----|-------|
| דיווח 1 | התראת מייל למבקר האחראי |
| דיווח 2 (ממשתמש שונה) | הסתרה אוטומטית + התראת דחיפות למבקר |
| דיווח 3+ | יצירת קשר חוזר עם מבקר |

**סף אירועים חריגים:**
| מצב | סף | פעולה |
|-----|-----|-------|
| מדווח-שגוי תכוף | 5+ דיווחי-שגוי ב-30 יום | התראה למבקר + מגבלת דיווח |
| מדווח-עליו תכוף ומוצדק | 3+ דיווחים-מוצדקים ב-30 יום | התראה למנהל + עיון בהשעיה |
| אירוע חוזר משמעותי | 2+ אירועים-מוצדקים ב-7 ימים | השעיה אוטומטית זמנית 48 שעות + התראה למנהל |

קבצי backend: `endpoints/reports.py`, `services/report_service.py`
קבצי frontend: `features/moderator/`

---

### מודול ניהול (Admin)

```
אישור/דחיית הרשמות, ניהול מקצוענים ומבקרים, Audit Log
```

- **Audit Trail:** כל פעולה נרשמת עם מי, מה, מתי, IP. לוגים append-only, שמורים 7 שנים.
- **ייצוא נתונים:** הרשאה לאדמין בלבד

קבצי backend: `endpoints/admin.py`
קבצי frontend: `features/admin/`

---

### מודול תשתית ענן ופריסה

**Frontend — Vercel:**
- פריסה אוטומטית (CI/CD) מכל push לענף הראשי
- HTTPS ו-CDN גלובלי מובנים כברירת מחדל
- Preview Deployments לבדיקת גרסאות לפני פרודקשן

**Backend — Render:**
- Web Service עם פריסה אוטומטית מ-GitHub
- תמיכה ב-Python + PostgreSQL מנוהל
- Environment Variables מוצפנים לשמירת סודות

**אחסון קבצים ומסמכים:**
- Cloudflare R2 או Supabase Storage (Free Tier לשלב ראשון)
- הצפנת מסמכים: AES-256 at rest; presigned URLs מוגבלי-זמן (15 דקות)
- שדות מזהים (ת"ז, מייל): field-level encryption עם מפתח נפרד לכל משתמש

---

### מודול שיחות קבוצתיות (בפיתוח)

יכולת שיחות וידאו קבוצתיות בתוך המערכת, לשימוש מפגשי תמיכה קהילתיים בין חברי אותה קבוצה/מגזר.

- **טכנולוגיה:** WebRTC — פיתוח עצמאי מקצה לקצה (לא שירות חיצוני)
- **הצפנה:** SRTP בזמן אמת
- **הפרדה:** לפי קבוצה/מגזר בהתאם לכללי הסינון
- **הקלטה:** כבויה כברירת מחדל; ניתנת להפעלה רק בהסכמת כל המשתתפים
- **שרתי תיווך:** STUN/TURN להתמודדות עם רשתות מאחורי NAT/Firewall

> היקף המשתתפים המקסימלי ופתרון האירוח (self-hosted מול managed) טעונים בירור מול העמותה.

---

### סוכן AI — זכויות חד-הוריות (ממשק במודול ייעוץ מקצועי)

סוכן המשולב ישירות בתוך מודול השאלות והתשובות המקצועיות — כאפשרות נוספת לצד שאלה לאיש מקצוע אנושי, לא כתחליף לו.

**תחום:** זכויות משפחות חד-הוריות — זכאויות ביטוח לאומי, הטבות מס, סיוע בדיור.

**עקרונות ארכיטקטורה:**
- בסיס ידע ייעודי, מתעדכן תקופתית ע"י איש מקצוע מוסמך
- הגבלת הסוכן למידע שבבסיס הידע בלבד (למניעת מידע שגוי)
- פועל בתוך אותה מסגרת הרשאות קבוצה/מגזר כמו שאר המערכת
- כל שיחה נרשמת ב-Audit Trail
- Disclaimer קבוע: "התשובות הן מידע כללי בלבד ואינן מהוות ייעוץ משפטי/מקצועי מחייב"

> שאר הסוכנים (7 נוספים מתוכננים) ממתינים ב-backlog להשקה ראשונית.

---

## 8. API – נקודות קצה

בסיס: `http://localhost:8000/api/v1`

| Method | Path | תיאור | הרשאה |
|--------|------|-------|-------|
| `POST` | `/auth/register` | הגשת בקשת הרשמה | פומבי |
| `POST` | `/auth/login` | כניסה – מחזיר JWT | פומבי |
| `POST` | `/auth/refresh` | רענון JWT | מחובר |
| `GET` | `/users/me` | פרטי המשתמש הנוכחי | מחובר |
| `GET` | `/forum/posts` | רשימת פוסטים (מסוננת!) | USER |
| `POST` | `/forum/posts` | פרסום פוסט | USER |
| `GET` | `/forum/posts/{id}` | פוסט בודד | USER |
| `PATCH` | `/forum/posts/{id}` | עריכת פוסט | USER (בעלים) |
| `DELETE` | `/forum/posts/{id}` | מחיקת פוסט | USER (בעלים) / MODERATOR |
| `POST` | `/forum/posts/{id}/report` | דיווח על פוסט | USER |
| `GET` | `/advice/professionals` | רשימת אנשי מקצוע | USER |
| `POST` | `/advice/questions` | שאלה מקצועית חדשה | USER |
| `GET` | `/advice/questions/public` | שאלות ציבוריות שנענו | USER |
| `GET` | `/moderator/reports` | דיווחים ממתינים | MODERATOR |
| `POST` | `/moderator/reports/{id}/decide` | החלטה על דיווח | MODERATOR |
| `GET` | `/admin/registrations` | הרשמות ממתינות | ADMIN |
| `POST` | `/admin/registrations/{id}/approve` | אישור הרשמה | ADMIN |
| `POST` | `/admin/registrations/{id}/reject` | דחיית הרשמה | ADMIN |
| `GET` | `/admin/audit-log` | יומן פעולות | ADMIN |

> 📖 תיעוד מלא ואינטראקטיבי: `http://localhost:8000/api/v1/docs`

---

## 9. מדיניות שמירת נתונים

| סוג נתון | תקופת שמירה | עם מחיקת חשבון |
|----------|------------|----------------|
| הודעות פורום | 5 שנים | אנונימיזציה (לא מחיקה) |
| הודעות פרטיות | 3 שנים | מחיקה מלאה |
| שאלות מקצועיות ציבוריות | 7 שנים | אנונימיזציה |
| שאלות מקצועיות פרטיות | 5 שנים | מחיקה מלאה |
| מסמכי הרשמה | 10 שנים | מחיקה עם אישור מנהל |
| Audit Logs | 7 שנים | לא נמחקים |
| דיווחים | 5 שנים | אנונימיזציה |

**זכויות GDPR / חוק הגנת הפרטיות הישראלי:**
- זכות גישה: משתמש יכול לבקש העתק של כל המידע שנשמר עליו
- זכות מחיקה: מחיקה תוך 30 יום, למעט נתונים בעלי חובה חוקית
- הסכמה מפורשת נדרשת בנפרד לכל מטרת עיבוד
- Data Breach: דיווח תוך 72 שעות לרשות הגנת הפרטיות

---

## 10. כללי עבודה ו-Git

### Git Workflow

```bash
# 1. לפני כל עבודה – משכי עדכונים
git fetch origin main
git merge origin/main   # merge, לא rebase

# 2. צרי branch חדש לכל פיצ'ר
git checkout -b feature/forum-list

# 3. עבדי, commit קטנים וברורים
git add frontend/src/app/features/forum/forum-list/
git commit -m "feat: add forum list component with post cards"

# 4. כשסיימת – פתחי Pull Request ל-main
git push origin feature/forum-list
```

### כינויי Commit

| קידומת | מתי להשתמש |
|--------|-----------|
| `feat:` | פיצ'ר חדש |
| `fix:` | תיקון באג |
| `refactor:` | שיפור קוד ללא שינוי פונקציונלי |
| `style:` | שינויי CSS/SCSS |
| `docs:` | תיעוד |

### עקרונות קוד חשובים

- כל פונקציה עושה **דבר אחד**
- שמות משמעותיים – לא `x`, `temp`, `data`
- אל תשאירי `console.log` בקוד
- בבאקאנד – תמיד `db.commit()` אחרי שינויים ב-DB
- **סינון תוכן חייב להיות בבאקאנד** – לא בפרונטאנד בלבד

---

## 11. Scripts שימושיים

### Backend

```bash
# הרצת טסטים
pytest

# בדיקת קוד (lint)
ruff check app/ --fix

# פורמט קוד
ruff format app/

# בדיקת types
mypy app/

# יצירת migration חדש (אחרי שינוי ב-models)
alembic revision --autogenerate -m "add forum posts table"
alembic upgrade head
```

### Frontend

```bash
npm run lint          # ESLint
npm run lint:fix      # ESLint עם תיקון אוטומטי
npm run format        # Prettier
npm test              # Vitest tests
npm run build:prod    # build לייצור
```

---

## Environment Variables

העתיקי `backend/.env.example` ל-`backend/.env`:

| משתנה | תיאור |
|-------|-------|
| `SECRET_KEY` | מפתח JWT – הריצי: `openssl rand -hex 32` |
| `DATABASE_URL` | חיבור ל-DB |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | תוקף JWT (ברירת מחדל: 15 דקות) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | תוקף refresh token (7 ימים) |
| `BACKEND_CORS_ORIGINS` | רשימת origins מורשים |
| `SMTP_HOST` | שרת מייל (לשליחת OTP והתראות) |
| `FIREBASE_PROJECT_ID` | מזהה פרויקט Firebase — נדרש לאימות Google ID tokens |

---

> 📌 לפני PR – ראי [CHECKLIST.md](CHECKLIST.md)
