# UT Plate

UT Plate is a phone app. It reads the J2, JCL and Kins Dining menus every day and tells you what to eat, and how many portions, to hit your daily targets. It can also fill in your Google Sheet when you mark a meal as eaten.

The project has four parts:

| File | What it does |
| --- | --- |
| `scrape.py` | Pulls the menus and nutrition labels for all three halls from UT FoodPro, keeping vegetarian and vegan dishes plus meat-free desserts |
| `.github/workflows/scrape.yml` | A GitHub Action that runs the scraper twice a day and saves `data/menu.json` |
| `index.html`, `planner.js` | The app itself, hosted free on GitHub Pages |
| `sheet-sync.gs` | An optional Google Apps Script that writes eaten meals into your sheet's Food tab |

## Setup (about 10 minutes, on a laptop)

1. Create a **public** GitHub repository, for example `ut-plate`.
2. Upload these files with **Add file → Upload files**: `index.html`, `planner.js`, `scrape.py`, `README.md`, `.nojekyll`, and the `data` folder.
3. Add the workflow with **Add file → Create new file**. Name it `.github/workflows/scrape.yml` and paste in that file's contents. (Mac Finder hides folders that start with a dot.)
4. Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and press Save.
5. Go to **Actions → Update dining menus → Run workflow**. The first run takes about 5–8 minutes because it reads every label once. Later runs are faster.
6. Go to **Settings → Pages** and set Source to **Deploy from a branch**, `main`, `/ (root)`. Your app will be at `https://YOUR-USERNAME.github.io/ut-plate/`.
7. Open that link in Safari on your phone and tap **Share → Add to Home Screen**.

## Link your Google Sheet (optional)

Your sheet needs a tab named **Food** laid out like your mastersheet. Each date goes in column A, with Breakfast, Lunch, Dinner and Snacks rows below it and the 15 nutrient columns in B–P. If you upload `Keshav_MASTERSHEET.xlsx` to Google Drive and open it with Google Sheets, it already matches.

1. In the Google Sheet, open **Extensions → Apps Script**.
2. Delete what's there, paste in `sheet-sync.gs`, and change `TOKEN` to a password of your own.
3. Optional check: choose `testWrite` from the function menu and press **Run**. Allow access when asked. The log should say `"ok":true`.
4. Click **Deploy → New deployment**. Pick type **Web app**, set **Execute as: Me** and **Who has access: Anyone**, and press Deploy. Copy the **Web app URL**, which ends in `/exec`.
5. In the app, open **Settings**. Paste the URL into **Google Sheet link** and your TOKEN into **Sheet password**, then tap **Test link**.

From then on, the app updates your sheet like this:

| In the app | In your Food tab |
| --- | --- |
| **I ate this** | Writes that meal's 15 totals into the meal's row under today's date |
| **Undo eaten** | Clears that row |
| Turning foods on or off under **Outside the dining halls** | Writes their total into the Snacks row |
| **Send this day** (in Settings) | Re-sends every eaten meal for the day |

Brunch goes into the Lunch row.

If you edit the script later, use **Deploy → Manage deployments → Edit → New version** so the URL stays the same.

## Using the app

- Each meal has a hall picker.
    - **Best match** compares J2, JCL and Kins and picks the hall whose menu gets closest to your targets.
    - You can also pick the hall you're actually walking to.
- **I ate this** logs the meal. The meals left in the day are re-planned around whatever is still needed.
- **Another option** gives a different plate.
- **+ / −** change portions, and **×** hides a dish for good.
- **Add a dish** is a dropdown grouped by the station each dish is served at (desserts last). Adding, changing or removing a dish makes your picks a starter, and the app fills the rest of that meal around them. **Stop filling** freezes the plate; **Fill in the rest** turns it back on.
- Foods under **Outside the dining halls** only count for the day you add them. Tick "save it in my list" to reuse one on other days.
- **This week** shows each day's calories, protein, fiber and sodium (green = goal met), how many days hit each goal, and **Adjust daily limits** lets you change any nutrient's limit for one day, from a day onward, or for every day.
- Targets follow your 12-week plan. You can change the start date in Settings.

## If the update fails

The scraper follows the FoodPro page layout but couldn't be tested against the live site. If the Action fails or a hall shows no dishes:

1. Rerun **Update dining menus** with **Save raw pages for troubleshooting** ticked.
2. Download the `debug-pages` file from the finished run.
3. Share it so the parsing can be fixed.
