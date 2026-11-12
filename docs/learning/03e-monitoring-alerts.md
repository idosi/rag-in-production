<div dir="rtl">

# ‏שלב 3ה: monitoring והתראות

## ‏1. הבעיה

‏בשלב 3ג בנינו שורת JSON אחת לכל שאלה. זה מצוין כשיודעים איזו בקשה לבדוק. אבל כשהשירות רץ בענן, אף אחד לא יושב וקורא לוגים. הבאג של Neon (3ד) הוכיח את זה: כל שאלה קיבלה 500, ומי שגילה את זה היינו אנחנו, כי חיכינו בכוונה. בלי זה, השירות היה נשבר בשקט עד שמשתמש היה כותב.

‏הבדל שכדאי לזכור: **לוג** עונה על "מה קרה לבקשה הזאת?". **Monitoring** עונה על "איך השירות מרגיש עכשיו?". **התראה** עונה על "מתי להעיר מישהו?". אנלוגיה: לוג הוא תיק רפואי, monitoring הוא מד חום, והתראה היא האזעקה שמצפצפת כשהחום עובר 39.

## ‏2. מה מודדים: RED ועוד אחד

| ‏אות | ‏שאלה | ‏אצלנו (שדה בשורת ה-trace) |
|---|---|---|
| ‏Rate | ‏כמה בקשות? | ‏ספירת שורות |
| ‏Errors | ‏כמה נכשלו? | ‏`status` מ-500 ומעלה, חוץ מ-503 |
| ‏Duration | ‏כמה לקח? | ‏`total_ms`, ובעיקר p95 |
| ‏Cost (ספציפי ל-LLM) | ‏כמה שרפנו? | ‏`cost_usd`, וגם 503 של התקציב |

‏שני דברים שכדאי להבין:

- **‏p95 ולא ממוצע.** ב-99 בקשות של שנייה ואחת של 100 שניות הממוצע הוא 2 שניות ונראה סביר, אבל אחד מכל מאה משתמשים חיכה דקה וחצי. p95 אומר: "95% מהבקשות הסתיימו תוך X". האחוזון נקרא nearest rank: ממיינים ולוקחים את הערך במקום `ceil(p/100 × n)`.
- **‏503 של התקציב הוא לא שגיאה, אבל הוא כן סיבה להתראה.** הוא אומר שהמערכת הגנה על הכסף שלנו כמו שתכננו. אבל גם אומר שמישהו כבר לא מקבל תשובות, ושווה לדעת למה. לכן הוא נספר בנפרד (`rejected`) ויש לו התראה משלו.

## ‏3. התרגילים (אתה כותב)

‏הכול בקובץ אחד: `exercises/monitor/my_monitor.py`, והטסטים ב-`test_my_monitor.py` (13 טסטים, כולם נכשלים עכשיו). ההוראות המלאות והרמזים נמצאים בראש הקובץ.

| ‏תרגיל | ‏מה | ‏טסטים |
|---|---|---|
| ‏3ה-1 | ‏`percentile` ו-`summarize`: הופכים הרבה שורות לכמה מספרים | ‏1-8 |
| ‏3ה-2 | ‏`check_alerts`: מחליטים אילו מספרים מצדיקים להעיר מישהו | ‏9-13 |

‏הרצה: `uv run pytest exercises/monitor -q`. תעשה commit אחרי כל טסט ירוק.

### ‏שאלות לחשוב עליהן (נדבר אחרי שהטסטים ירוקים)

- ‏למה `min_requests`? שתי בקשות ושגיאה אחת הן 50% שגיאות. מה יקרה לאזעקה מבוססת-אחוזים בשלוש בלילה, כשאף אחד לא משתמש?
- ‏למה 503 של התקציב לא נספר כשגיאה, ובכל זאת יש לו התראה?
- ‏סיכום של 5 הדקות האחרונות וסיכום של 24 השעות האחרונות עונים על שאלות שונות. על איזה מהם מתריעים, ואיזה שמים בדשבורד?

## ‏4. מה אני מחבר אחרי התרגילים

1. ‏`src/rag/logreport.py`: הקוד שלך עובר לשם, ועוד פקודה שקוראת לוגים מ-Cloud Run, מסכמת, ומדפיסה אילו התראות היו נורות.
2. ‏`make report`: אותה פקודה בלחיצה אחת. זה ה-monitoring "מהמחשב", בלי הגדרות בענן, והוא מראה בדיוק מה ש-Cloud Monitoring יחשב.
3. ‏הקבצים והפקודות להגדרת אותן התראות בענן (סעיף 5).

## ‏5. אותו דבר בענן: log-based metrics והתראות

‏Cloud Run כבר שולח את שורות ה-trace כ-`jsonPayload` (3ד). Cloud Monitoring יכול להפוך שדה בלוג למדד, ועל מדד אפשר להגדיר התראה. זה בדיוק מה שה-`summarize` וה-`check_alerts` שלך עושים בקטן.

‏הפקודות כאן הן התוכנית, ולא הורצו על ידי (אין לי גישה לפרויקט שלך). אם יש שגיאה, תדביק אותה ונתקן.

**‏א. ערוץ התראות (מייל):**

<div dir="ltr">

```
gcloud beta monitoring channels create \
  --display-name="rag-api owner" --type=email \
  --channel-labels=email_address=YOU@example.com
gcloud beta monitoring channels list --format="value(name)"     # save the channel name
```

</div>

**‏ב. מדד: שגיאות (counter).** כל שורה שמתאימה לפילטר מוסיפה 1:

<div dir="ltr">

```
gcloud logging metrics create rag_errors \
  --description="rag-api requests that ended in 5xx, except the budget 503" \
  --log-filter='resource.type="cloud_run_revision"
                resource.labels.service_name="rag-api"
                jsonPayload.status>=500 jsonPayload.status!=503'

gcloud logging metrics create rag_budget_rejections \
  --description="rag-api requests refused because the daily budget is used up" \
  --log-filter='resource.type="cloud_run_revision"
                resource.labels.service_name="rag-api"
                jsonPayload.status=503'
```

</div>

**‏ג. מדד: latency (distribution).** כאן צריך קובץ, כי מדד כזה מוציא ערך מהשורה:

<div dir="ltr">

```yaml
# monitoring/rag_latency.yaml
name: rag_latency_ms
description: total_ms of every /ask request
filter: >
  resource.type="cloud_run_revision" resource.labels.service_name="rag-api"
  jsonPayload.total_ms>=0
metricDescriptor: {metricKind: DELTA, valueType: DISTRIBUTION, unit: ms}
valueExtractor: EXTRACT(jsonPayload.total_ms)
bucketOptions:
  exponentialBuckets: {numFiniteBuckets: 20, growthFactor: 1.5, scale: 50}
```

</div>

<div dir="ltr">

```
gcloud logging metrics create rag_latency_ms --config-from-file=monitoring/rag_latency.yaml
```

</div>

**‏ד. מדיניות התראה על השגיאות:**

<div dir="ltr">

```yaml
# monitoring/alert_errors.yaml
displayName: rag-api: 5xx errors
combiner: OR
conditions:
  - displayName: more than 3 errors in 10 minutes
    conditionThreshold:
      filter: >
        metric.type="logging.googleapis.com/user/rag_errors"
        resource.type="cloud_run_revision"
      comparison: COMPARISON_GT
      thresholdValue: 3
      duration: 0s
      aggregations:
        - {alignmentPeriod: 600s, perSeriesAligner: ALIGN_SUM}
alertStrategy: {autoClose: 1800s}
```

</div>

<div dir="ltr">

```
gcloud alpha monitoring policies create --policy-from-file=monitoring/alert_errors.yaml \
  --notification-channels=CHANNEL_NAME_FROM_STEP_A
```

</div>

‏אותה צורה לשני האחרים: `rag_budget_rejections` עם סף 0, ו-`rag_latency_ms` עם `perSeriesAligner: ALIGN_PERCENTILE_95` וסף 8000.

### ‏הגבלות שכדאי להכיר (ובראיון להגיד אותן)

- **‏אחוז שגיאות מול ספירה.** התראה על "יותר מ-3 שגיאות ב-10 דקות" מתאימה לתנועה קטנה כמו שלנו. בתנועה גבוהה מתריעים על **אחוז** (שגיאות חלקי בקשות), וזה ה-`min_requests` שלך בתרגיל.
- **‏p95 על תנועה נמוכה רועש.** עם 10 בקשות בשעה, בקשה איטית אחת מזיזה את ה-p95. אותה סיבה ל-`min_requests`.
- **‏מדד על לוג מתעכב בכמה דקות** ועולה כסף בנפח גבוה. לנפח גדול משתמשים במדדים ישירים (OpenTelemetry).
- **‏תקציב בחשבון Google.** ההתראה על `cost_usd` מהלוג מכסה רק את Claude. את חשבון הענן עצמו מכסה Billing budget (`gcloud billing budgets create`), וכדאי להגדיר אותו בנפרד.

## ‏6. מה לא עשינו, ולמה

| ‏דבר | ‏סיבה |
|---|---|
| ‏uptime check על `/ready` | ‏בדיקה כל 5 דקות מעירה את ה-container (עלות, ומבטלת את scale to zero) ומעירה את Neon (ואז הוא אף פעם לא נרדם, ובכך הוא מפסיק להיות חינמי). לשירות עם תנועה קבועה זה בדיוק מה שרוצים |
| ‏התראה על `reconnects` | ‏ב-Neon Free חיבור מחדש הוא **רגיל**: קורה אחרי כל שינה. אני כתבתי קודם "התראה על קפיצה ב-reconnects", וזו הייתה הגזמה. מה שחשוב הוא ש-reconnect מצליח, וזה מה שהתראת השגיאות בודקת. מספר reconnects גבוה בשעה עם תנועה יכול להיות סימן ל-DB לא יציב, וכדאי לראות אותו בגרף |
| ‏דשבורד | ‏שלוש מדדים והתראות מספיקים לשירות אחד. דשבורד הוא ה-"נחמד שיהיה" הבא |
| ‏OpenTelemetry ו-tracing מבוזר | ‏שירות אחד, אין בקשות בין שירותים. הפורמט שלנו (id, spans, שדות) כבר מוכן להמרה |
| ‏on-call, runbook ו-SLO | ‏יש משתמש אחד. אבל הייתי כותב runbook קצר לכל התראה: "מה בודקים קודם" |

## ‏7. שאלות ראיון (תרגול)

<details><summary><b>‏איך תדע שהשירות נשבר בפרודקשן, לפני שמשתמש יגיד לך?</b></summary>

‏שלוש שכבות. לוגים מובנים (שורת JSON לבקשה, עם `request_id`) כדי שאפשר יהיה לחקור. מדדים שנגזרים מהם (שגיאות, p95, עלות) כדי לראות מגמה. והתראות על אלה שדורשות פעולה: שיעור שגיאות, latency וכסף. התראה טובה היא כזו שיש מה לעשות איתה: כל אחת אצלי מתאימה לשאלה "מה בודקים קודם".
</details>

<details><summary><b>‏למה p95 ולא ממוצע?</b></summary>

‏הממוצע מסתיר זנב. 99 בקשות של שנייה ואחת של 100 שניות נותנות ממוצע של 2 שניות, ואחד ממאה משתמשים חיכה דקה וחצי. p95 ו-p99 מראים את מה שהמשתמשים הגרועים רואים. ל-LLM זה חשוב במיוחד: זמן התשובה משתנה הרבה, כי הוא תלוי באורך התשובה ובעומס אצל הספק.
</details>

<details><summary><b>‏איך מונעים עייפות התראות (alert fatigue)?</b></summary>

‏כל התראה צריכה להצדיק התעוררות בשלוש בלילה: דחופה, ויש פעולה ברורה. מה שלא כזה הולך לדשבורד. טכנית: סף על אחוזים ולא על ספירות כשהתנועה משתנה, מינימום בקשות כדי שמדגם קטן לא יפעיל אזעקה (ה-`min_requests`), ו-`autoClose` כדי שהתראה תיסגר לבד כשהבעיה חלפה. ואחרי כל התראה שהתבררה כרעש, מתקנים את הסף או מוחקים אותה.
</details>

<details><summary><b>‏למה 503 של התקציב לא שגיאה, ואיך בכל זאת מתריעים עליו?</b></summary>

‏כי המערכת עשתה בדיוק מה שתכננו: הגנה על הכסף. אם הייתי סופר אותו כשגיאה, כל יום שבו התקציב נגמר היה נראה כמו תקלה, והאזעקה האמיתית (באג) הייתה טובעת. אבל זה כן אומר שמשתמשים נשארו בלי תשובה, ולכן יש לו מדד והתראה משלו: או שהתקציב נמוך מדי, או שמישהו מנצל לרעה.
</details>

<details><summary><b>‏למה לא uptime check על `/ready`?</b></summary>

‏כי הוא היה מעיר את השירות כל כמה דקות. עם scale to zero זה עולה כסף ומבטל את החיסכון, ובנוסף שומר את Neon ער ומבטל את השינה שבגללה הוא חינמי. לשירות פנימי עם תנועה קבועה הייתי מוסיף uptime check בלי היסוס, כי הוא תופס מצב שבו אין בכלל בקשות ולכן גם אין שגיאות בלוג.
</details>

<details><summary><b>‏מה ההבדל בין מדד מהלוגים לבין מדד "אמיתי" (OpenTelemetry/Prometheus)?</b></summary>

‏מדד מלוגים נולד מטקסט: פשוט להגדיר, בלי שינוי בקוד, אבל מתעכב בכמה דקות ועולה כסף בנפח גבוה (משלמים על כל שורת לוג). מדד אמיתי נספר בתוך התהליך ונשלח כמספר מצטבר, ולכן הוא זול, מהיר ומדויק. התחלתי מלוגים כי כבר היו לי, וכי לשירות אחד זה מספיק.
</details>

</div>
