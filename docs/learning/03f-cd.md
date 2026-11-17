<div dir="rtl">

# ‏שלב 3ו: CD, פריסה אוטומטית בלי מפתח

## ‏1. הבעיה

‏עד עכשיו פרסנו ביד: `make gcp-build` ואז `make deploy`. זה עובד, אבל תלוי בבן אדם: מישהו צריך לזכור, להיות על המחשב הנכון, ולא לפרוס קוד שה-CI עוד לא אישר. **CD** (Continuous Deployment) אומר: דחיפה ל-`main` שעוברת CI נפרסת על ידי מכונה.

‏שתי בעיות שצריך לפתור טוב, ובכל אחת מהן יש טעות נפוצה:

| ‏בעיה | ‏הטעות הנפוצה | ‏מה עשינו |
|---|---|---|
| ‏איך GitHub מזדהה מול Google? | ‏קובץ מפתח JSON ב-secret של GitHub: אם הוא דולף, הוא תקף לתמיד | ‏Workload Identity Federation: אסימון קצר-חיים, בלי שום סוד שמור |
| ‏איך לא לשלוח קוד שבור לכולם? | ‏לפרוס ישר ולהתפלל | ‏לפרוס revision **בלי תנועה**, לבדוק, ורק אז להעביר תנועה |

## ‏2. Workload Identity Federation, בשפה פשוטה

‏אנלוגיה: בחברה יש שומר בכניסה. הדרך הישנה היא לתת לכל מי שצריך כניסה **מפתח** (קובץ JSON). מפתח אפשר לאבד, לשכפל, ואין לו תאריך תפוגה. הדרך החדשה: שומר שבודק **תעודה מזהה** שהונפקה לפני רגע, ורק אם היא מוכרת (ורק אם היא של החברה הנכונה) פותח דלת ליום אחד.

‏מה קורה בפועל, בכל הרצה:
1. ‏ה-job מבקש מ-GitHub אסימון חתום (OIDC). זה אפשרי רק בגלל `id-token: write`.
2. ‏האסימון אומר, בחתימה של GitHub: "אני ההרצה של הריפו `idosi/rag-in-production`".
3. ‏Google בודקת שהחתימה אמיתית ושהריפו תואם לתנאי שהגדרנו (`attribute-condition`), ומחליפה אותו באסימון גישה של חשבון השירות `github-deployer`, תקף לשעה.
4. ‏עם האסימון הזה דוחפים image ופורסים.

**‏מה מונע מריפו אחר לבקש את הזהות שלנו?** שני דברים: התנאי על ה-provider (`assertion.repository=='idosi/rag-in-production'`) וה-binding שנותן את ההרשאה רק ל-`principalSet` של הריפו הזה. בלי התנאי, כל ריפו ב-GitHub היה יכול לנסות.

## ‏3. הקובץ: `.github/workflows/deploy.yml`

‏הקובץ נכתב על ידך כתרגיל 3ו (12 טסטים), וההסברים ההחלטות כאן:

| ‏מה | ‏למה |
|---|---|
| ‏`on: workflow_run` של `CI`, על `main` | ‏`push` היה רץ **במקביל** ל-CI ויכול לפרוס קוד שהטסטים שלו עדיין רצים או נכשלים |
| ‏`if: ...conclusion == 'success'` | ‏`workflow_run` מופעל גם כש-CI **נכשל**. בלי התנאי, קוד אדום היה נפרס |
| ‏`checkout` עם `ref: ...head_sha` | ‏ברירת המחדל ב-`workflow_run` היא קצה `main` עכשיו, שיכול להיות commit חדש יותר ממה שה-CI בדק |
| ‏`permissions` ברמת ה-workflow: קריאה בלבד, `id-token: write` רק ל-job | ‏הרשאה מינימלית: רק מי שצריך לבקש אסימון מקבל זכות לבקש |
| ‏`concurrency` עם `cancel-in-progress: false` | ‏פריסה אחת בכל פעם, ופריסה שרצה לא מבוטלת באמצע (פריסה חצי-גמורה גרועה מהמתנה). ב-CI ההפך: שם ביטול של run ישן הוא בטוח |
| ‏תג ה-image הוא ה-commit, לא `latest` | ‏רואים בדיוק איזה קוד רץ, וחזרה לאחור היא image ידוע |
| ‏`--no-traffic --tag candidate` | ‏ה-revision החדש עולה בלי שאף משתמש מגיע אליו, ויש לו כתובת משלו: `https://candidate---...` |
| ‏smoke על כתובת ה-candidate, ואז `--to-latest` | ‏אם ה-smoke נכשל, ה-job נעצר ו**לא מגיעים** לצעד שמעביר תנועה. ה-revision הישן ממשיך לשרת, ואין מה להחזיר |

‏הערה על ה-smoke: ב-CD הוא רץ בלי `API_KEY`, כלומר שלוש בדיקות בחינם (`/health`, `/ready`, `/ask` בלי מפתח חייב להחזיר 401). שאלה אמיתית עולה כסף וצריכה מפתח, ולכן לא נתנו ל-deployer גישה אליו. המחיר: ה-smoke לא בודק את הנתיב המלא של Claude. `/ready` כן בודק שה-DB נגיש ושה-index לא ריק.

## ‏4. הגדרה חד-פעמית בענן

‏אותן פקודות שנתתי בצעד ההכנה. מריצים פעם אחת, וכל אחת מהן מסבירה את עצמה:

<div dir="ltr">

```
PROJECT=rag-ido-2026
PN=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
SA=github-deployer@$PROJECT.iam.gserviceaccount.com

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='idosi/rag-in-production'"

# only this repository may become the deployer
gcloud iam service-accounts add-iam-policy-binding $SA --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PN/locations/global/workloadIdentityPools/github/attribute.repository/idosi/rag-in-production"

# what the deployer may do: deploy, push images, and run the service as rag-api
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=roles/run.admin
gcloud artifacts repositories add-iam-policy-binding rag --location=europe-west3 \
  --member=serviceAccount:$SA --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding rag-api@$PROJECT.iam.gserviceaccount.com \
  --member=serviceAccount:$SA --role=roles/iam.serviceAccountUser
```

</div>

‏למה `serviceAccountUser` על `rag-api`? כדי לפרוס שירות שרץ **בזהות** של `rag-api`, צריך הרשאה "להתחזות" אליו. בלי זה, הפריסה נכשלת. זה הכלל: מי שמפעיל משהו בזהות אחרת חייב הרשאה מפורשת לזהות הזאת.

‏ואז שלושה **משתני ריפו** ב-GitHub (Settings ← Secrets and variables ← Actions ← Variables, לא Secrets, כי אלה מזהים ולא סודות): `GCP_PROJECT_ID`, `GCP_DEPLOYER_SERVICE_ACCOUNT` (הערך של `$SA`) ו-`GCP_WORKLOAD_IDENTITY_PROVIDER` (`projects/$PN/locations/global/workloadIdentityPools/github/providers/github-actions`).

## ‏5. מה שחשוב לדעת על ההרצה הראשונה

- ‏`workflow_run` רץ **מקובץ ב-`main`**. אי אפשר לבדוק את ה-deploy לפני שהקובץ ממוזג. כישלון של ה-deploy לא משפיע על ה-CI ועל השירות הקיים.
- ‏ה-build הראשון איטי (כ-5 עד 10 דקות, כי ה-image מוריד מודלים). אחרי זה ה-cache (`type=gha`) מקצר.
- ‏צפה לתקלות הגדרה בהרצה הראשונה, ובעיקר שלוש: שם משתנה שלא תואם ל-`vars.`, הרשאה חסרה, או `attribute-condition` עם שם ריפו שגוי. ההודעה של `google-github-actions/auth` בדרך כלל אומרת איזה.

## ‏6. חזרה לאחור

‏אם משהו נשבר **אחרי** שהתנועה עברה, אותו מנגנון מ-3ד: `gcloud run services update-traffic rag-api --region europe-west3 --to-revisions <revision קודם>=100`. זה שניות, בלי build, כי כל revision לא משתנה וה-image מתויג ב-commit.

## ‏7. מה לא עשינו, ולמה

| ‏דבר | ‏סיבה |
|---|---|
| ‏העברת תנועה הדרגתית (10%, אחר כך 100%) | ‏שירות אחד ומעט משתמשים. ה-smoke על ה-candidate מכסה את הסכנה העיקרית |
| ‏הרצת ה-evals לפני פריסה | ‏עולה כסף (כ-3 דולר) ולא דטרמיניסטי. נכון לשינוי prompt או מודל, לא לכל commit |
| ‏אישור ידני לפני פריסה (`environment` עם reviewers) | ‏שירות אישי. בחברה הייתי מוסיף לפרודקשן |
| ‏Terraform להגדרות ה-IAM | ‏פקודות `gcloud` מתועדות מספיקות לשירות אחד, ומוסיפים כשיש כמה סביבות |
| ‏מיגרציות DB בצעד נפרד | ‏אין לנו כרגע. סכמה משתנה רק בדרך תואמת לאחור (3ד) |

## ‏8. שאלות ראיון (תרגול)

<details><summary><b>‏למה Workload Identity Federation ולא קובץ מפתח JSON ב-secret של GitHub?</b></summary>

‏קובץ מפתח הוא סוד ארוך-חיים: אם הוא דולף (לוג, fork, עובד לשעבר), הוא תקף עד שמישהו שם לב ומבטל אותו. ב-WIF אין שום סוד שמור: בכל הרצה GitHub מנפיק אסימון קצר-חיים, ו-Google מחליפה אותו באסימון גישה לשעה, רק אם הוא הגיע מהריפו שהגדרנו. אין מה לדלוף, אין מה לסובב, וההרשאה קשורה לזהות של הריפו ולא למי שמחזיק קובץ.
</details>

<details><summary><b>‏למה `workflow_run` ולא `push` ל-main?</b></summary>

‏`push` מפעיל את ה-deploy במקביל ל-CI, ולכן יכול לפרוס קוד שהטסטים שלו עדיין רצים או נכשלים. `workflow_run` מחכה שה-CI יסתיים. אבל הוא מופעל גם כש-CI נכשל, ולכן צריך `if: conclusion == 'success'`, וגם `checkout` של `head_sha`, כדי לפרוס בדיוק את ה-commit שנבדק ולא את קצה `main` הנוכחי.
</details>

<details><summary><b>‏איך אתה מוודא שקוד שבור לא מגיע למשתמשים?</b></summary>

‏פורסים revision חדש עם `--no-traffic` ו-tag, שנותן לו כתובת משלו. מריצים עליו smoke test (חיות, מוכנות, ושהגנת ה-API פעילה). רק אם עבר מעבירים תנועה. אם נכשל, ה-job נעצר לפני צעד העברת התנועה, וה-revision הישן לא הפסיק לשרת, אז אין rollback לעשות. מגבלה: ה-smoke לא שולח שאלה אמיתית (זה עולה כסף וצריך מפתח), ולכן נתיב Claude לא נבדק לפני התנועה.
</details>

<details><summary><b>‏מה מגן על זהות ה-deployer מפני ריפו אחר?</b></summary>

‏שני דברים. התנאי על ה-provider (`attribute-condition`) דוחה אסימון שלא מהריפו שלנו עוד לפני ההחלפה. וה-binding (`workloadIdentityUser`) מוגבל ל-`principalSet` שמצביע על הריפו שלנו. אם נשכח את התנאי, כל ריפו ב-GitHub יכול לבקש להחליף אסימון, ולכן זו שורה שבודקים בסקירה.
</details>

<details><summary><b>‏למה ה-deployer צריך `serviceAccountUser` על `rag-api`?</b></summary>

‏Cloud Run מריץ את השירות בזהות של `rag-api` (שיש לה גישה לסודות). כדי לפרוס שירות שרץ בזהות אחרת, צריך הרשאה "להתחזות" אליה, ובלי זה אפשר היה לקבל זהות חזקה דרך פריסה. זה הכלל: להפעיל משהו בזהות אחרת דורש הרשאה מפורשת לזהות הזאת.
</details>

<details><summary><b>‏למה תג ה-image הוא commit ולא `latest`?</b></summary>

‏`latest` זז: אי אפשר לדעת איזה קוד רץ, ואין image ידוע לחזור אליו. עם תג ה-commit, כל revision אומר בדיוק מאיזה קוד נבנה, חזרה לאחור היא להעביר תנועה ל-revision קודם, ואפשר לשחזר כל deploy.
</details>

</div>
