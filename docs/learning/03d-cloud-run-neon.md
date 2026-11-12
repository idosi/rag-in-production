<div dir="rtl">

# ‏שלב 3ד: פריסה ל-Cloud Run עם Neon

## ‏1. הבעיה

‏עד עכשיו המערכת רצה רק על המחשב שלך: Postgres ב-docker compose, ה-API ב-`make api`. בשלב הזה היא עוברת לענן ומקבלת כתובת HTTPS ציבורית שכל אחד יכול לשלוח אליה שאלה (עם מפתח).

‏אנלוגיה: עד עכשיו בישלת במטבח של הבית. עכשיו פותחים מסעדה. המתכון (הקוד) זהה, אבל פתאום יש דברים שבבית לא קרו: הגז נסגר לבד בלילה (Neon נרדם), צריך לנעול את הקופה (secrets), ומשלמים שכירות לפי שעה (עלות).

| ‏מה | ‏איפה רץ | ‏למה |
|---|---|---|
| ‏ה-API (ה-container מ-3א) | ‏Google Cloud Run | ‏מריץ container כמו שהוא, עולה מ-0 לפי בקשות, HTTPS בחינם |
| ‏Postgres + pgvector | ‏Neon | ‏Postgres מנוהל עם pgvector, יש שכבה חינמית, נרדם כשאין שימוש |
| ‏המפתחות (Claude, DB, API keys) | ‏Secret Manager | ‏הסודות לא בקוד, לא ב-image ולא במשתני סביבה גלויים |
| ‏בניית ה-image | ‏Cloud Build | ‏בונה linux/amd64 (ה-Mac שלך בונה arm64) |
| ‏ה-image עצמו | ‏Artifact Registry | ‏"מחסן" ה-images של Google, באותו אזור כמו Cloud Run |

## ‏2. התמונה הכוללת

<div dir="ltr">

```
 laptop                                Google Cloud (europe-west3, Frankfurt)
 ------                                --------------------------------------
 git commit
 make gcp-build  ── source ──────────> Cloud Build ── image ──> Artifact Registry
 make deploy     ─────────────────────────────────────────────> Cloud Run: rag-api
                                                                  |   reads at start:
                                                                  |   Secret Manager
 curl /ask ── HTTPS ──> https://rag-api-xxxx.run.app ──> container(s) 0..2
                                                                  |
 make ingest (once) ── TLS ──────────────────────────────> Neon Postgres (Frankfurt)
                                                           aws-eu-central-1
```

</div>

‏שים לב לשני דברים בשרטוט:
- **‏ה-ingest רץ מהמחשב שלך** ישר אל Neon. ה-container בענן רק קורא. ככה לא צריך להוריד את התיעוד ולחשב embeddings בענן.
- **‏ה-API ו-Neon באותה עיר (פרנקפורט).** כל שאלה עושה 2 עד 3 פניות ל-DB. בין ישראל לפרנקפורט זה ‎~60ms לפנייה, ובתוך פרנקפורט ‎~1ms. אין ל-Neon אזור בישראל, ולכן מעבירים את ה-API אל ה-DB, לא להפך.

## ‏3. למה דווקא אלה

### ‏למה Cloud Run
- **‏כבר יש לנו container** (3א). Cloud Run מריץ אותו בלי שינוי, חוץ מהפורט (תרגיל 3ד-0).
- **‏Scale to zero:** כשאין בקשות אין containers ואין חיוב. ל-portfolio שמקבל עשר שאלות ביום זה ההבדל בין 0 דולר ל-30 דולר בחודש.
- **‏HTTPS, תעודה, load balancer ולוגים** מגיעים בחינם.
- **‏Revisions:** כל deploy יוצר גרסה שלא משתנה. חזרה לאחור היא פקודה אחת.

| ‏חלופה | ‏למה לא כאן |
|---|---|
| ‏GKE (Kubernetes) | ‏מתאים לעשרות שירותים. לשירות אחד זה אשכול שצריך לתחזק |
| ‏מכונה (VM) | ‏רצה 24/7, אתה מעדכן את מערכת ההפעלה ומטפל ב-TLS |
| ‏Lambda / Cloud Functions | ‏בנויים לפונקציות קטנות. אצלנו image של ‎~900MB עם מודלים |
| ‏Render / Fly.io | ‏אפשריים לגמרי. בחרנו Google כי זה מה שמבקשים במשרות |

### ‏למה Neon ולא Cloud SQL
- ‏ל-Cloud SQL אין שכבה חינמית. המכונה הקטנה ביותר רצה כל הזמן, בערך 10 דולר בחודש ומעלה.
- ‏ל-Neon יש שכבה חינמית, pgvector מובנה, והוא נרדם כשאין שימוש.
- **‏המחיר של "נרדם":** החיבור הראשון אחרי שינה לוקח כמה מאות מילישניות, ו**חיבורים פתוחים נסגרים כשהוא נרדם**. זה באג אמיתי שנפגוש בסעיף 7, וזה הסיפור הכי טוב של השלב הזה לראיון.

## ‏4. מה משתנה בקוד

| ‏מה | ‏מי כותב | ‏למה |
|---|---|---|
| ‏`Dockerfile` מאזין ל-`$PORT` | **‏אתה**, תרגיל 3ד-0 | ‏Cloud Run קובע את הפורט, לא אנחנו |
| ‏`redact` ו-`require_tls` ל-URL של ה-DB | **‏אתה**, תרגיל 3ד-1 | ‏לא להדליף סיסמה ללוג, לא להתחבר בלי הצפנה |
| ‏`readiness` (‏`/health` מול `/ready`) | **‏אתה**, תרגיל 3ד-2 | ‏"חי" ו"מוכן לענות" הן שתי שאלות שונות |
| ‏`Reconnector` | **‏אתה**, תרגיל 3ד-3 | ‏לשרוד את השינה של Neon |
| ‏חיבור התרגילים לקוד (`api.py`, `db.py`, `store.py`) | ‏אני, אחרי שתסיים | |
| ‏`dburl.py`, ‏`health.py` (הקוד שלך מהתרגילים) ב-`src/rag`, ‏`database_url` כ-`SecretStr`, ‏`db.connect` בודק TLS ורושם URL בלי סיסמה, ‏`/health` ללא DB ו-`/ready` | אני, כבר בקוד | |
| ‏`API_KEYS` ריק ב-Cloud Run = השירות לא עולה | ‏אני, כבר בקוד | ‏`/ask` פתוח הוא כתובת ציבורית ששורפת כסף |
| ‏`cloudbuild.yaml`, ‏`.gcloudignore`, ‏`make gcp-build/deploy/smoke`, ‏`scripts/smoke.sh` | ‏אני, כבר בקוד | |

‏איך מזהים שאנחנו ב-Cloud Run: הפלטפורמה שמה בכל container את משתנה הסביבה `K_SERVICE` (שם השירות). אם הוא קיים ו-`API_KEYS` ריק, ה-lifespan זורק שגיאה, ה-container לא עולה, וה-deploy נכשל. כישלון רועש עדיף על אזהרה שאף אחד לא קורא.

### ‏סדר העבודה

1. **‏תרגילים 3ד-0, 3ד-1, 3ד-2** (בלי ענן, בלי כסף). מדביקים לי את הקוד ואת הפלט של pytest, ואני מחבר אותם.
2. **‏במקביל, בלי קוד:** פותחים חשבון Neon ופרויקט ב-Google Cloud (סעיף 5).
3. ‏**ingest ל-Neon** מהמחשב, ושאלה אחת מקומית מול Neon.
4. ‏**secrets, build, deploy, smoke test.**
5. **‏מחכים 6 דקות ורואים את הבאג** (סעיף 7), ואז תרגיל 3ד-3, ואני מחבר, ו-deploy שוב.

<div dir="ltr">

```
uv run pytest exercises/deploy -q      # 3d-0  (edit the Dockerfile)
uv run pytest exercises/db_url -q      # 3d-1
uv run pytest exercises/ready -q       # 3d-2
uv run pytest exercises/reconnect -q   # 3d-3  (after section 7)
```

</div>

‏בכל תרגיל ההסבר המלא, המפרט והרמזים נמצאים בראש קובץ ה-`my_*.py` (או בראש קובץ הבדיקה ב-3ד-0). קומיט אחרי כל בדיקה שעוברת.

## ‏5. הגדרה חד-פעמית

**‏כלל לכל הסעיף:** סיסמאות ומפתחות לא מקלידים בתוך פקודה, כי הן נשמרות ב-history של ה-shell. משתמשים ב-`read -rs` (קורא שורה בלי להציג אותה) ומעבירים דרך משתנה.

### ‏5.1 ‏Neon

1. ‏נרשמים ב-console.neon.tech ויוצרים פרויקט: שם `rag`, ‏Postgres **16** (כמו `pgvector/pgvector:pg16` המקומי), אזור **AWS Europe Central 1 (Frankfurt)**.
2. ‏**Connect** ← מכבים את **Connection pooling** ← מעתיקים את ה-connection string. הוא נראה ככה:

<div dir="ltr">

```
postgresql://neondb_owner:npg_xxxx@ep-xxxx-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

</div>

‏למה בלי pooling: הכתובת עם `-pooler` עוברת דרך PgBouncer, שמחזיק הרבה חיבורי לקוח מעל מעט חיבורים אמיתיים. זה נחוץ כשיש מאות חיבורים (למשל serverless functions). אצלנו יש חיבור אחד לכל container, ולכל היותר 2 containers. חיבור ישיר פשוט יותר, ונמנע מבעיות של PgBouncer עם prepared statements.

3. ‏בודקים חיבור ומכניסים את התיעוד, מהמחשב שלך:

<div dir="ltr">

```
read -rs NEON_URL && export NEON_URL     # paste the string, Enter (nothing is shown)
uv run python -c "import os, psycopg; print(psycopg.connect(os.environ['NEON_URL']).execute('select version()').fetchone())"
DATABASE_URL="$NEON_URL" make ingest     # ~745 chunks, same as local
DATABASE_URL="$NEON_URL" make ask Q="How do I make a query parameter optional?"
```

</div>

‏משתנה סביבה גובר על `.env` (‏`config.py`), ולכן `DATABASE_URL=... make ingest` כותב ל-Neon בלי לגעת ב-`.env`. בשאלה מול Neon תרגיש את המרחק: כל פנייה ל-DB עוברת עכשיו מישראל לפרנקפורט.

### ‏5.2 ‏Google Cloud

<div dir="ltr">

```
gcloud auth login
gcloud projects create rag-ido-2026 --name="RAG in production"   # the id must be unique worldwide
gcloud config set project rag-ido-2026
```

</div>

‏**חיוב:** ב-console ← Billing ← מקשרים חשבון חיוב לפרויקט. בלי זה אף שירות לא יעבוד, גם לא החינמיים. ואז **מיד** Billing ← Budgets & alerts ← תקציב של 5 דולר עם התראות במייל ב-50%, ‏90% ו-100%. חשוב לדעת: תקציב ב-Google **מתריע, הוא לא עוצר**. העצירה האמיתית אצלנו היא `--max-instances` והתקציב היומי שלנו (3ג).

<div dir="ltr">

```
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create rag --repository-format=docker --location=europe-west3
```

</div>

### ‏5.3 ‏Service account: הזהות של ה-container

‏כברירת מחדל Cloud Run מריץ את ה-container בזהות של ה-Compute default service account, שיש לו לרוב הרשאת **Editor** על כל הפרויקט. אם מישהו פורץ ל-container, הוא יכול למחוק את הפרויקט. לכן יוצרים זהות שמותר לה דבר אחד בלבד: לקרוא את שלושת הסודות שלנו (least privilege, כמו `permissions: contents: read` ב-CI).

<div dir="ltr">

```
gcloud iam service-accounts create rag-api --display-name="RAG API runtime"
```

</div>

### ‏5.4 ‏Secrets

<div dir="ltr">

```
printf %s "$NEON_URL" | gcloud secrets create database-url --data-file=-

read -rs ANTHROPIC_KEY                     # paste your sk-ant-... key, Enter
printf %s "$ANTHROPIC_KEY" | gcloud secrets create anthropic-api-key --data-file=-

API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
printf %s "$API_KEY" | gcloud secrets create api-keys --data-file=-
echo "$API_KEY"                            # save it in your password manager: this is how you call /ask

SA=rag-api@$(gcloud config get-value project).iam.gserviceaccount.com
for s in database-url anthropic-api-key api-keys; do
  gcloud secrets add-iam-policy-binding $s --member="serviceAccount:$SA" \
    --role=roles/secretmanager.secretAccessor
done
```

</div>

**‏למה `printf %s` ולא `echo`:** ‏`echo` מוסיף ירידת שורה בסוף. הסוד נשמר כ-`sk-ant-...\n`, ה-SDK שולח מפתח עם `\n`, ומקבלים 401 בלי שום רמז למה. ‏`printf %s` כותב בדיוק את מה שנתת לו.

**‏ההרשאה ניתנת על כל סוד בנפרד**, לא על כל ה-Secret Manager של הפרויקט. אם מחר תוסיף סוד לשירות אחר, ה-API שלנו לא יוכל לקרוא אותו.

## ‏6. ‏Build, deploy, smoke

<div dir="ltr">

```
git status                 # clean: the image tag is the commit
make gcp-build             # ~5-8 minutes the first time
make deploy                # ~1-2 minutes
API_KEY=... make smoke     # /health, /ready, /ask without key (401), /ask with key
```

</div>

### ‏מה כל דגל ב-`make deploy` עושה

| ‏דגל | ‏למה |
|---|---|
| ‏`--image ...:<commit>` | ‏ה-image מתויג ב-commit. רואים בכל revision איזה קוד רץ, וחזרה לאחור = image קודם |
| ‏`--service-account rag-api@...` | ‏הזהות המצומצמת מ-5.3 |
| ‏`--set-secrets NAME=secret:latest` | ‏Cloud Run קורא את הסוד בזמן עליית ה-container ושם אותו במשתנה הסביבה. `config.py` לא יודע את ההבדל |
| ‏`--set-env-vars DAILY_BUDGET_USD=1` | ‏תקציב יומי נמוך לענן: דולר אחד לכל container |
| ‏`--memory 2Gi --cpu 1` | ‏שני מודלי ONNX ו-onnxruntime בזיכרון. מתחילים בנדיבות, מודדים בגרף Memory utilization, ומקטינים |
| ‏`--cpu-boost` | ‏יותר CPU בזמן העלייה, כדי שטעינת המודלים תהיה מהירה יותר. משפר cold start |
| ‏`--concurrency 8` | ‏עד 8 בקשות במקביל לכל container. רוב הזמן מחכים ל-Claude (I/O), אבל ה-reranker הוא CPU (‏‎~160ms), ויש רק vCPU אחד |
| ‏`--min-instances 0` | ‏scale to zero: אין תנועה, אין containers, אין חיוב. המחיר: cold start של כמה שניות לשאלה הראשונה |
| ‏`--max-instances 2` | ‏תקרת עלות, וגם תקרה לתקציב ול-cache שחיים בזיכרון של כל container (3ג): התקרה האמיתית היא 2 × התקציב |
| ‏`--timeout 60` | ‏בקשה שלא נגמרה תוך דקה נחתכת. שאלה רגילה לוקחת 3 עד 10 שניות |
| ‏`--startup-probe httpGet.path=/health,...` | ‏Cloud Run שולח תנועה רק אחרי ש-`/health` ענה. ‏5s × 24 = עד 2 דקות לטעינת מודלים |
| ‏`--liveness-probe httpGet.path=/health,...` | ‏אם `/health` נכשל 3 פעמים ברצף, ה-container מוחלף. לכן `/health` לא נוגע ב-DB (תרגיל 3ד-2) |
| ‏`--allow-unauthenticated` | ‏ראה למטה |

### ‏`--allow-unauthenticated`: האם זה לא פותח את השירות?

‏ל-Cloud Run יש שתי שכבות אפשריות של הגנה:
1. ‏**IAM של Google:** רק מי שיש לו זהות Google עם הרשאה יכול לקרוא לשירות. מתאים לשירות פנימי שמדבר עם שירות אחר.
2. ‏**ה-API key שלנו** (3ב): ‏`X-API-Key` ו-rate limit.

‏אנחנו רוצים שאפליקציה חיצונית תוכל לקרוא עם מפתח פשוט, ולכן משאירים את שכבה 1 פתוחה ומסתמכים על שכבה 2. ‏`/health` ו-`/ready` פתוחים בכוונה. ‏`/ask` מחזיר 401 בלי מפתח, וה-smoke test בודק את זה בכל deploy.

### ‏לוגים

‏Cloud Run אוסף כל מה שנכתב ל-stdout. שורה שהיא JSON תקין (כמו שורת ה-trace שלנו מ-3ג) נשמרת כ-`jsonPayload` עם שדות שאפשר לחפש לפיהם. כלומר ה-tracing שבנינו עובד בענן בלי שורת קוד נוספת:

<div dir="ltr">

```
gcloud run services logs read rag-api --region europe-west3 --limit 30
# in Logs Explorer:  jsonPayload.request_id="a3f9c1"   or   jsonPayload.status=500
```

</div>

### ‏חזרה לאחור (rollback)

<div dir="ltr">

```
gcloud run revisions list --service rag-api --region europe-west3
gcloud run services update-traffic rag-api --region europe-west3 --to-revisions rag-api-00002-abc=100
```

</div>

‏revision לא משתנה אף פעם, ולכן חזרה לאחור היא רק העברת תנועה, בלי build. (לא מחזיר שינויים ב-DB. לכן שינוי schema צריך להיות כזה שגם הקוד הישן עובד איתו.)

## ‏7. הבאג החי: Neon נרדם

‏זה החלק שבשבילו כדאי לעשות את כל השלב. **לא מתקנים לפני שרואים.**

1. ‏אחרי `make smoke` מוצלח, **לא שולחים כלום 6 דקות.** ב-console של Neon רואים שה-compute עובר ל-Idle אחרי 5 דקות.
2. ‏שולחים שאלה אחת עם `curl` (או `make smoke` שוב).
3. ‏מצפים ל-**500**, ו-`/ready` מחזיר 503 ‏`database unreachable`. בלוגים: ‏`psycopg.OperationalError` עם `server closed the connection unexpectedly` או `SSL SYSCALL error: EOF detected`.
4. ‏שולחים שוב. **עדיין 500**, ולא משנה כמה פעמים.

‏מה קרה:

<div dir="ltr">

```
16:00  container starts, opens ONE connection (db.connect in build_pipeline), keeps it forever
16:00  questions work
16:05  no queries for 5 minutes -> Neon suspends the compute -> closes every open connection
       (an idle open connection does NOT keep it awake; Free plan can't disable this)
16:08  question -> our dead connection -> OperationalError -> 500
16:09  question -> same dead connection -> 500 ... until Cloud Run replaces the container
```

</div>

‏למה זה לא קרה אף פעם על המחשב: Postgres ב-docker compose לא נרדם. ולמה Cloud Run לא "מתקן" את זה בעצמו: הוא משאיר container פנוי בחיים יותר מ-5 דקות (כדי לחסוך cold start), וה-liveness probe עובר, כי `/health` לא נוגע ב-DB. התהליך חי, אבל לא מסוגל לענות. בדיוק ההבדל בין liveness ל-readiness.

‏אם במקום 500 קיבלת תשובה רגילה, כנראה ש-Cloud Run כבר החליף את ה-container (cold start עם חיבור חדש). נסה שוב עם המתנה של 6 דקות בדיוק.

**‏התיקון: תרגיל 3ד-3, ‏`Reconnector`.** כשפנייה נכשלת בגלל חיבור שבור, פותחים חיבור חדש (‏Neon מתעורר תוך כמה מאות מילישניות) ומנסים **פעם אחת** נוספת. חיברנו אותו ל-`ChunkStore` (רק לקריאות, כי הן SELECT ולכן בטוחות לחזרה), ועשינו build ו-deploy. אחרי יותר מ-9 דקות בלי פעילות שלחנו שאלה **חדשה**: קיבלנו 200 ותשובה מלאה, ואחריה `/ready` החזיר 200 עם 745 chunks. לפני התיקון אותה בדיקה נתנה 500.

**שלושה לקחים מהבדיקה:**

- ‏cache של תשובות מסתיר כשל במסד: שאלה שכבר נשאלה חוזרת מהזיכרון בלי לגעת ב-DB, ולכן בדיקה חוזרת חייבת שאלה חדשה.
- ‏טסט שרק מחפש טקסט ב-Dockerfile לא תפס באג ב-HEALTHCHECK. הוספנו טסט שמריץ את הקוד באמת.
- ‏Neon עלה כ-Postgres 18 בזמן שהמקומי ו-CI הם 16. כדאי ליישר גרסאות כדי שלא יהיו הפתעות.

### ‏למה לא connection pool

‏הפתרון התעשייתי הוא `psycopg_pool.ConnectionPool` עם `check=ConnectionPool.check_connection` ו-`max_idle`: הוא בודק כל חיבור לפני שהוא נותן אותו, סוגר חיבורים ישנים, ומחלק כמה חיבורים בין threads. בחרנו ב-`Reconnector` כי הוא קטן מספיק לכתוב בעצמך ולהבין עד הסוף, ואצלנו יש חיבור אחד לכל container. בראיון: "כתבתי reconnect-and-retry-once. עם יותר תנועה הייתי עובר ל-pool עם בדיקת חיבור".

## ‏8. כמה זה עולה

‏המספרים נכונים לנובמבר 2026, ומשתנים. בדוק בדפי התמחור לפני שאתה מסתמך עליהם.

| ‏רכיב | ‏שימוש שלנו | ‏בערך |
|---|---|---|
| ‏Cloud Run | ‏חיוב רק בזמן טיפול בבקשה. יש מכסה חינמית חודשית של vCPU-שניות ו-GiB-שניות | ‏0 דולר לעשרות שאלות ביום |
| ‏Artifact Registry | ‏image של ‎~300MB דחוס. יש 0.5GB חינם | ‏מוחקים images ישנים, משאירים 1 עד 2 |
| ‏Cloud Build | ‏‎~6 דקות build. יש מכסה חינמית של דקות build | ‏0 דולר לכמה builds ביום |
| ‏Secret Manager | ‏3 סודות | ‏0 דולר (6 גרסאות חינם) |
| ‏Neon Free | ‏כמה MB של נתונים | ‏0 דולר |
| ‏Claude | ‏‎~0.008 דולר לשאלה (Sonnet) | ‏תקרה: 1 דולר ליום × 2 containers |

‏הסיכון האמיתי הוא לא Google, אלא Claude: מפתח שדלף ולולאה. לכן שלוש שכבות: ‏API key + rate limit (3ב), תקציב יומי (3ג), ‏`--max-instances` (כאן). ומעליהן תקציב והתראות ב-GCP, ומגבלת הוצאה חודשית ב-console של Anthropic.

## ‏9. כשמשהו נכשל

| ‏מה רואים | ‏הסיבה הסבירה | ‏מה עושים |
|---|---|---|
| ‏`failed to start and listen on the port defined by the PORT=8080` | ‏ה-CMD עדיין על 8000 | ‏תרגיל 3ד-0 |
| ‏`exec format error` | ‏image שנבנה על ה-Mac (arm64) | ‏בונים עם `make gcp-build`, לא `docker build` |
| ‏`RuntimeError: API_KEYS is empty` בלוג העלייה | ‏הסוד `api-keys` חסר או ריק | ‏5.4 |
| ‏`Permission denied on secret` | ‏אין `secretAccessor` ל-service account על הסוד הזה | ‏5.4, הלולאה |
| ‏ה-build נכשל ב-push או בלוגים | ‏ה-service account של Cloud Build (‏`PROJECT_NUMBER-compute@developer...`) בלי הרשאות | ‏לתת לו `roles/artifactregistry.writer` ו-`roles/logging.logWriter` |
| ‏401 מ-Claude בענן אבל לא מקומית | ‏ירידת שורה בסוף הסוד (`echo`) | ‏`gcloud secrets versions add anthropic-api-key --data-file=-` עם `printf %s` |
| ‏`/ready` = ‏`index is empty` | ‏ה-ingest רץ על ה-DB המקומי ולא על Neon | ‏`DATABASE_URL="$NEON_URL" make ingest` |
| ‏500 אחרי כמה דקות שקט | ‏Neon נרדם | ‏סעיף 7 |
| ‏השאלה הראשונה לוקחת ‎~15 שניות | ‏cold start: הפעלת container וטעינת מודלים, ו-Neon מתעורר | ‏צפוי עם `min-instances 0`. ‏`min-instances 1` עולה כסף כל הזמן |

## ‏10. מה לא עשינו, ולמה

| ‏דבר | ‏סיבה |
|---|---|
| ‏deploy אוטומטי מ-GitHub Actions | ‏דורש Workload Identity Federation (‏CI מקבל זהות Google בלי מפתח JSON). שלב טבעי הבא, אחרי שה-deploy הידני מובן |
| ‏Terraform | ‏שירות אחד, פעם אחת. הפקודות בסעיף 5 הן ה-"infra as code" שלנו, מתועדות בגיט |
| ‏דומיין משלנו | ‏כתובת `run.app` מספיקה ל-portfolio |
| ‏Redis משותף ל-cache ולתקציב | ‏עם `max-instances 2` הפער ידוע וחסום (פי 2) |
| ‏ingest מתוזמן בענן (Cloud Run Job) | ‏התיעוד נעול לגרסה. כשנרצה רענון, זו העבודה הבאה |
| ‏Cloud Armor או API Gateway | ‏rate limit בתוך התהליך מספיק בהיקף הזה |

## ‏11. שאלות ראיון (תרגול)

<details><summary><b>‏למה ה-image שבנית על ה-Mac לא עולה ב-Cloud Run, ואיך פתרת?</b></summary>

‏Mac עם Apple Silicon בונה images ל-linux/arm64, ו-Cloud Run מריץ linux/amd64. ה-image נטען, והתהליך הראשון נכשל ב-`exec format error`. אפשר `docker buildx build --platform linux/amd64`, אבל זו אמולציה: איטית, ומעמיסה על מחשב עם מעט זיכרון. בנינו ב-Cloud Build (‏`cloudbuild.yaml`), שרץ על amd64, מוריד את המודלים ברשת של Google ודוחף ישר ל-Artifact Registry באותו אזור.
</details>

<details><summary><b>‏מה ההבדל בין liveness ל-readiness, ולמה `/health` שלך לא נוגע ב-DB?</b></summary>

‏liveness עונה על "התהליך חי?". אם הוא נכשל, הפלטפורמה **מחליפה** את ה-container. readiness עונה על "אפשר לשלוח לו תנועה?": ה-DB נגיש וה-index לא ריק. אם ה-DB נפל ו-liveness תלוי בו, כל ה-containers יוחלפו בלולאה. החלפה לא מתקנת DB, ורק מוסיפה cold start מעל התקלה. לכן `/health` תמיד 200, ו-`/ready` מחזיר 503 עם סיבה (‏`database unreachable` או `index is empty: run ingest`) בלי טקסט השגיאה עצמו, כי הוא יכול להכיל host ושם משתמש.
</details>

<details><summary><b>‏ספר על באג שמצאת רק בפרודקשן.</b></summary>

‏ה-API פתח חיבור אחד ל-Postgres בעלייה והחזיק אותו לתמיד. מקומית זה עבד. ב-Neon Free ה-compute נרדם אחרי 5 דקות בלי שאילתות וסוגר את כל החיבורים, אבל Cloud Run השאיר את ה-container בחיים, וה-liveness עבר. התוצאה: אחרי שקט של 5 דקות כל שאלה קיבלה 500 עד שה-container הוחלף. שחזרתי בכוונה (חיכיתי 6 דקות), והתיקון היה `Reconnector`: בשגיאת חיבור (`OperationalError`) פותחים חיבור חדש ומנסים פעם אחת. שגיאות אחרות לא מנסים שוב. בתעבורה גבוהה יותר הייתי עובר ל-connection pool עם בדיקת חיבור.
</details>

<details><summary><b>‏למה לנסות שוב רק פעם אחת, ורק על `OperationalError`?</b></summary>

‏ניסיון חוזר עוזר רק כשהבעיה זמנית ונפתרת בחיבור חדש. שגיאת SQL (`UndefinedTable`, ‏`ProgrammingError`) תחזור בדיוק אותו דבר, אז ניסיון חוזר רק מעכב. ואם ה-DB באמת נפל, לולאת ניסיונות מחזיקה thread ובקשה הרבה זמן ומכה ב-DB בדיוק כשהוא מתאושש (thundering herd). ניסיון אחד מתקן את המקרה הנפוץ (חיבור ישן), ומשאיר את המקרה האמיתי ל-`/ready` ולהתראות. ושאלה שתמיד שואלים על retry: האם הפעולה idempotent? ‏SELECT כן, ו-`replace_document` הוא טרנזקציה אחת של מחיקה והכנסה, אז ניסיון שני מגיע לאותו מצב.
</details>

<details><summary><b>‏איפה הסודות שלך, ומי יכול לקרוא אותם?</b></summary>

‏ב-Secret Manager, שלושה סודות. ‏Cloud Run קורא אותם בעליית ה-container (`--set-secrets`) ושם אותם במשתני סביבה, כך שהקוד (`config.py` עם `SecretStr`) לא השתנה. רק ה-service account ‏`rag-api` יכול לקרוא, ורק את שלושת הסודות האלה (הרשאה לכל סוד בנפרד). הם לא בגיט (‏`.gitignore`), לא ב-image (‏`.dockerignore`), ולא בהעלאה ל-Cloud Build (‏`.gcloudignore`). ה-URL של ה-DB לא נרשם ללוג אף פעם עם סיסמה (`redact`).
</details>

<details><summary><b>‏למה `sslmode=require` ולא ברירת המחדל?</b></summary>

‏ברירת המחדל של libpq היא `prefer`: מנסה TLS, ואם השרת לא מציע, ממשיך בטקסט גלוי בלי להודיע. מישהו באמצע יכול להציג שרת בלי TLS ולקבל את הסיסמה. ‏`require` מסרב לחיבור לא מוצפן. (‏`verify-full` גם בודק שהתעודה שייכת ל-host, וזו ההגנה המלאה מפני התחזות.) ‏Neon מסרב לחיבור לא מוצפן בעצמו, אבל `require_tls` דואג שהקוד שלנו לא יסתמך על זה: הספק הבא אולי לא יסרב.
</details>

<details><summary><b>‏הגדרת `--max-instances 2`. מה זה עושה לעלות ולנכונות?</b></summary>

‏עלות: לכל היותר 2 containers. עם 1 vCPU ו-2GiB לכל אחד, החשבון חסום גם תחת עומס. וגם תקציב Claude חסום: ‏1 דולר × 2. נכונות: ה-cache, התקציב וה-rate limiter חיים בזיכרון של כל container. עם 2 containers, rate limit של 20 לדקה הוא בפועל עד 40, ושאלה שנשמרה ב-cache של אחד היא miss בשני. הפער ידוע וחסום. אם צריך יותר containers, מעבירים את שלושתם ל-Redis משותף. המחיר של התקרה: בעומס גדול, בקשות ממתינות או מקבלות 429 מ-Cloud Run.
</details>

<details><summary><b>‏מה זה cold start אצלכם, ממה הוא מורכב, ואיך מקצרים?</b></summary>

‏שאלה ראשונה אחרי שקט, עם `min-instances 0`: ‏Cloud Run מוריד ומפעיל את ה-image (‏~900MB), ה-lifespan טוען שני מודלי ONNX ופותח חיבור ל-DB, ו-Neon מתעורר. ביחד, כ-10 עד 20 שניות. מקצרים: `--cpu-boost` (יותר CPU בעלייה), ‏image קטן יותר (המודלים כבר אפויים בו, אז אין הורדה מ-Hugging Face), ו-`min-instances 1`, שמשאיר container חם אבל עולה כסף כל הזמן. ל-portfolio בחרנו לשלם ב-latency של השאלה הראשונה, לא בכסף.
</details>

<details><summary><b>‏איך אתה חוזר לגרסה קודמת אם deploy שבר משהו?</b></summary>

‏כל deploy יוצר revision שלא משתנה, וה-image מתויג ב-commit. ‏`gcloud run services update-traffic --to-revisions <previous>=100` מחזיר את כל התנועה לגרסה הקודמת תוך שניות, בלי build. מה שזה לא מחזיר: שינויים ב-DB. לכן שינוי schema נעשה בשני שלבים (קודם מוסיפים עמודה שהקוד הישן מתעלם ממנה, ורק אחר כך משתמשים בה), כמו שעשינו עם `ADD COLUMN IF NOT EXISTS` של `tsv` ב-2ב.
</details>

<details><summary><b>‏למה Neon ולא Cloud SQL, ומה הייתם עושים בחברה אמיתית?</b></summary>

‏Neon: שכבה חינמית, pgvector, נרדם כשאין שימוש. המחיר: cold start של ה-DB, חיבורים נסגרים בשינה, וספק נוסף מחוץ ל-Google (עוד חשבון ועוד תעבורה ברשת הציבורית, מוצפנת). בחברה עם תנועה קבועה: Cloud SQL או AlloyDB באותו VPC, חיבור פרטי בלי אינטרנט, גיבויים והרשאות IAM באותו מקום, ומכונה שלא נרדמת. ההחלטה היא לפי דפוס התנועה: תנועה ספורדית מתאימה ל-serverless, ותנועה קבועה למכונה קבועה.
</details>

</div>
