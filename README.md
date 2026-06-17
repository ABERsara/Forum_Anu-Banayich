# עמותת "אנו בניך" – מערכת קהילה ופורום דיגיטלי

פלטפורמת תמיכה, קהילה, פורום וייעוץ מקצועי לאלמנים, אלמנות, יתומים ויתומות.

> Fullstack: **Angular 22** (frontend) + **FastAPI / Python** (backend)

---

## תוכן עניינים

1. [סקירת הפרויקט](#1-סקירת-הפרויקט)
2. [טכנולוגיות](#2-טכנולוגיות)
3. [הרצה מקומית – שלב אחר שלב](#3-הרצה-מקומית--שלב-אחר-שלב)
4. [מבנה הפרויקט](#4-מבנה-הפרויקט)
5. [ארכיטקטורה](#5-ארכיטקטורה)
6. [תפקידים במערכת RBAC](#6-תפקידים-במערכת-rbac)
7. [מודולים ראשיים](#7-מודולים-ראשיים)
8. [API – נקודות קצה](#8-api--נקודות-קצה)
9. [מה לפתח – חלוקת עבודה](#9-מה-לפתח--חלוקת-עבודה)
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

### מטריצת קבוצות-מגזרים (16 "תאים")

| קבוצה\מגזר | חסידי | ליטאי | ספרדי | כללי |
|------------|-------|-------|-------|------|
| אלמנים | תא 1א | תא 1ב | תא 1ג | תא 1ד |
| אלמנות | תא 2א | תא 2ב | תא 2ג | תא 2ד |
| יתומים | תא 3א | תא 3ב | תא 3ג | תא 3ד |
| יתומות | תא 4א | תא 4ב | תא 4ג | תא 4ד |

> כל משתמש/ת שייך/ת לתא **אחד בלבד**. התוכן שהוא/היא רואה מסוננות אוטומטית.

---

## 2. טכנולוגיות

| שכבה | טכנולוגיה | גרסה |
|------|-----------|-------|
| Frontend | Angular (standalone components) | 22 |
| Styling | SCSS + RTL (עברית) | - |
| Backend | FastAPI (Python) | 0.111+ |
| ORM | SQLAlchemy | 2.0 |
| Schemas | Pydantic | v2 |
| Migrations | Alembic | 1.13+ |
| Auth | JWT (python-jose) + bcrypt | - |
| DB (פיתוח) | SQLite | - |
| DB (ייצור) | PostgreSQL | - |
| Linting BE | Ruff + mypy | - |
| Linting FE | ESLint + Prettier | - |

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
│           │   │   ├── api.service.ts      ← wrapper בסיסי ל-HttpClient
│           │   │   ├── auth.service.ts     ← login, register, logout
│           │   │   ├── forum.service.ts    ← פוסטים
│           │   │   ├── professional.service.ts
│           │   │   └── report.service.ts
│           │   ├── guards/
│           │   │   ├── auth.guard.ts       ← מונע כניסה ללא login
│           │   │   └── role.guard.ts       ← מונע כניסה לפי תפקיד
│           │   └── interceptors/
│           │       └── auth.interceptor.ts ← מוסיף JWT לכל בקשה
│           │
│           ├── features/            ← ⭐ כאן עיקר העבודה שלכן
│           │   ├── auth/
│           │   │   ├── login/       ← דף כניסה
│           │   │   └── register/    ← דף הרשמה (רב-שלבי)
│           │   ├── forum/
│           │   │   ├── forum-list/  ← רשימת פוסטים
│           │   │   ├── forum-post/  ← פוסט בודד + תגובות
│           │   │   └── new-post/    ← כתיבת פוסט חדש
│           │   ├── advice/
│           │   │   ├── advice-list/ ← רשימת אנשי מקצוע
│           │   │   ├── ask-question/← שאלה מקצועית
│           │   │   └── qa-feed/     ← שאלות ציבוריות שנענו
│           │   ├── messages/
│           │   │   ├── inbox/       ← רשימת שיחות
│           │   │   └── chat/        ← שיחה פרטית
│           │   ├── profile/         ← פרופיל אישי
│           │   ├── admin/           ← ממשק מנהל
│           │   │   ├── dashboard/
│           │   │   ├── pending-registrations/
│           │   │   ├── manage-professionals/
│           │   │   └── audit-log/
│           │   └── moderator/       ← ממשק מבקר
│           │       └── reports/
│           │
│           ├── layout/
│           │   └── header/          ← header + navigation
│           └── shared/
│               └── components/      ← button, card, loading-spinner
│
└── backend/                         ← FastAPI app
    └── app/
        ├── main.py                  ← נקודת כניסה + CORS
        ├── core/
        │   ├── config.py            ← הגדרות (קרא מ-.env)
        │   ├── constants.py         ← ⭐ Python Enums (UserType, Sector...)
        │   ├── security.py          ← JWT + bcrypt
        │   └── dependencies.py      ← get_db(), get_current_user()
        ├── db/
        │   ├── base.py              ← DeclarativeBase
        │   └── session.py           ← engine + SessionLocal
        ├── models/                  ← ⭐ SQLAlchemy ORM (טבלאות ב-DB)
        │   ├── user.py
        │   ├── forum.py
        │   ├── professional.py
        │   ├── report.py
        │   ├── document.py
        │   └── audit.py
        ├── schemas/                 ← ⭐ Pydantic (מה ה-API מקבל/מחזיר)
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
        │   ├── router.py            ← מאגד את כל ה-routers
        │   └── endpoints/           ← ⭐ FastAPI routes
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
SQLite / PostgreSQL
    │
    ▼
JSON Response → Angular מעדכן UI
```

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

---

## 7. מודולים ראשיים

### מודול הרשמה ואימות
```
שלבים: טופס → OTP → העלאת מסמכים → המתנה → 2 מנהלים מאשרים → פעיל
```
- קבצי backend: `endpoints/auth.py`, `services/auth_service.py`
- קבצי frontend: `features/auth/`

### מודול פורום
```
פרסום: לתא שלי / לכל הקבוצה / לכל המגזר
מוצפן. עד 5,000 תווים + קובץ עד 5MB
```
- קבצי backend: `endpoints/forum.py`, `services/forum_service.py`
- קבצי frontend: `features/forum/`

### מודול הודעות פרטיות
```
חיפוש נמען בתוך קבוצה/מגזר בלבד
מוצפנות. 3 דיווחים = חסימה אוטומטית
```
- קבצי frontend: `features/messages/`

### מודול ייעוץ מקצועי
```
קטלוג: עו"ד, רו"ח, פסיכולוג, יועץ כלכלי, רב/דיין, רפואה, סוציאל וורקר
שאלה פרטית / ציבורית. ציבורית = "ידע קהילתי"
```
- קבצי backend: `endpoints/professional.py`, `services/professional_service.py`
- קבצי frontend: `features/advice/`

### מודול דיווח והגנה
```
דיווח 1 → התראה למבקר
דיווח 2 → הסתרה אוטומטית + התראת דחיפות
3+ דיווחים מוצדקים ב-7 ימים → השעיה אוטומטית 48 שעות
```
- קבצי backend: `endpoints/reports.py`, `services/report_service.py`
- קבצי frontend: `features/moderator/`

### מודול ניהול (Admin)
```
אישור/דחיית הרשמות, ניהול מקצוענים, Audit Log
```
- קבצי backend: `endpoints/admin.py`
- קבצי frontend: `features/admin/`

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

## 9. מה לפתח – חלוקת עבודה

> חפשי `# TODO:` בכל הקוד – אלו המקומות שמחכים למימוש שלכן

### ג'וניורית א – Backend

**שלב 1 (התחלה):**
```
backend/app/models/user.py               ← מודל User (SQLAlchemy)
backend/app/schemas/auth.py              ← RegisterRequest, LoginResponse
backend/app/services/auth_service.py     ← register(), login(), verify_otp()
backend/app/api/v1/endpoints/auth.py     ← POST /auth/register, POST /auth/login
```

**שלב 2:**
```
backend/app/models/forum.py
backend/app/schemas/forum.py
backend/app/services/forum_service.py    ← ⚠️ חשוב: סינון לפי group+sector!
backend/app/api/v1/endpoints/forum.py
```

**שלב 3:**
```
backend/app/models/professional.py
backend/app/schemas/professional.py
backend/app/services/professional_service.py
backend/app/api/v1/endpoints/professional.py
backend/app/api/v1/endpoints/admin.py
backend/app/api/v1/endpoints/moderator.py
```

---

### ג'וניורית ב – Frontend

**שלב 1 (התחלה):**
```
frontend/src/app/core/services/auth.service.ts   ← login(), register(), logout()
frontend/src/app/features/auth/login/            ← טופס כניסה
frontend/src/app/features/auth/register/         ← טופס הרשמה (4 שלבים!)
```

**שלב 2:**
```
frontend/src/app/core/services/forum.service.ts
frontend/src/app/features/forum/forum-list/      ← רשימת פוסטים
frontend/src/app/features/forum/forum-post/      ← פוסט בודד
frontend/src/app/features/forum/new-post/        ← פוסט חדש
```

**שלב 3:**
```
frontend/src/app/features/advice/
frontend/src/app/features/messages/
frontend/src/app/features/admin/
frontend/src/app/features/moderator/
```

---

## 10. כללי עבודה ו-Git

### Git Workflow
```bash
# 1. לפני כל עבודה – משכי עדכונים
git pull origin main

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
| `SMTP_HOST` | שרת מייל (לשליחת OTP) |

---

> 📌 לפני PR – ראי [CHECKLIST.md](CHECKLIST.md)
