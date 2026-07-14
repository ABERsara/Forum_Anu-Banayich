# פקודות טרמינל שימושיות

## 🐍 Python

### סביבת עבודה (venv)
```bash
python -m venv venv                 # יצירת סביבה וירטואלית
venv\Scripts\activate                # הפעלת הסביבה (Windows)
deactivate                           # יציאה מהסביבה
```

### חבילות (pip)
```bash
pip install -r requirements.txt      # התקנת כל החבילות מהקובץ
pip install <package>                # התקנת חבילה בודדת
pip freeze > requirements.txt        # שמירת החבילות המותקנות לקובץ
pip list                             # רשימת חבילות מותקנות
pip install --upgrade <package>      # עדכון חבילה
```

### הרצת האפליקציה (backend - FastAPI)
```bash
cd backend                           # כניסה לתיקיית ה-backend
uvicorn app.main:app --reload        # הרצת השרת עם הפעלה מחדש אוטומטית (dev)
uvicorn app.main:app --reload --port 8000   # הרצה על פורט ספציפי
```

### מיגרציות (Alembic)
```bash
alembic upgrade head                 # הרצת כל המיגרציות עד הגרסה האחרונה
alembic revision --autogenerate -m "message"  # יצירת מיגרציה חדשה
alembic downgrade -1                 # ביטול מיגרציה אחת אחורה
```

### בדיקות וכלים נפוצים
```bash
python -m pytest                     # הרצת בדיקות (pytest)
python -m pytest -v                  # בדיקות עם פירוט
python script.py                     # הרצת סקריפט
```

---

## 🅰️ Angular

### פרויקט וחבילות
```bash
npm install                          # התקנת כל התלויות
ng new my-app                        # יצירת פרויקט Angular חדש
ng serve                             # הרצת שרת פיתוח (ברירת מחדל: localhost:4200)
ng serve --open                      # הרצה ופתיחה אוטומטית בדפדפן
ng build                             # בנייה לפרודקשן
ng build --configuration production  # בנייה עם קונפיגורציית פרודקשן
```

### יצירת קבצים (generate)
```bash
ng generate component my-component   # יצירת קומפוננטה (ng g c)
ng generate service my-service       # יצירת שירות (ng g s)
ng generate module my-module         # יצירת מודול (ng g m)
ng generate directive my-directive   # יצירת דירקטיבה (ng g d)
ng generate pipe my-pipe             # יצירת pipe (ng g p)
```

### בדיקות ואיכות קוד
```bash
ng test                              # הרצת בדיקות יחידה (Karma/Jasmine)
ng e2e                               # הרצת בדיקות end-to-end
ng lint                              # בדיקת lint
```

---

## 🌿 Git

### התחלה ומצב
```bash
git init                             # יצירת מאגר git חדש
git status                           # הצגת מצב הקבצים
git clone <url>                      # שכפול מאגר
```

### הוספה וקומיט
```bash
git add <file>                       # הוספת קובץ ספציפי
git add .                            # הוספת כל השינויים (זהירות!)
git commit -m "FAB-XX: message"      # יצירת קומיט עם הודעה
git commit --amend                   # עריכת הקומיט האחרון
```

### ענפים (Branches)
```bash
git checkout main                    # מעבר לענף main
git pull                             # משיכת עדכונים מהריפו המרוחק
git checkout -b feat/FAB-XX-desc     # יצירת ענף חדש ומעבר אליו
git branch                           # רשימת ענפים מקומיים
git branch -a                        # רשימת כל הענפים (כולל מרוחקים)
git merge <branch>                   # מיזוג ענף לענף הנוכחי
```

### שינויים והיסטוריה
```bash
git diff                             # הצגת שינויים לא מאונדקסים
git diff --staged                    # הצגת שינויים מאונדקסים
git log                              # היסטוריית קומיטים
git log --oneline --graph            # היסטוריה מקוצרת עם גרף
```

### שליחה ומשיכה
```bash
git push                             # דחיפת שינויים לריפו המרוחק
git push -u origin <branch>          # דחיפת ענף חדש עם מעקב
git fetch                            # משיכת מידע ללא מיזוג
```

### ביטול ושחזור
```bash
git restore <file>                   # ביטול שינויים בקובץ (לא מאונדקס)
git restore --staged <file>          # הוצאת קובץ מהאינדקס
git reset HEAD~1                     # ביטול הקומיט האחרון (שומר שינויים)
git stash                            # שמירת שינויים זמנית בצד
git stash pop                        # החזרת שינויים שנשמרו
```
