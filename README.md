<p align="center">
  <img src="https://github.com/ajdavis25/paper-scraper/blob/main/assets/banner.png" 
       alt="astro-ph digest bot — built out of spite 💥" 
       width="100%">
</p>

<p align="center">
  <a href="https://github.com/ajdavis25/paper-scraper/actions/workflows/daily_digest.yml">
    <img src="https://github.com/ajdavis25/paper-scraper/actions/workflows/daily_digest.yml/badge.svg" alt="Build">
  </a>
  <img src="https://img.shields.io/github/license/ajdavis25/paper-scraper" alt="License">
  <img src="https://img.shields.io/github/stars/ajdavis25/paper-scraper?style=social" alt="Stars">
</p>

built out of spite because stanford gatekept vox charta

---

### WHAT THIS DOES
this bot automatically fetches the latest **astro-ph arXiv papers**, filters them by keywords and author preferences, and emails a **daily curated digest** to the mailing list.  

it includes:
- a default topic profile (`defaults.yaml`) for new subscribers.
- personalization logic to build individual profiles over time (based on what papers you click/like — coming soon).
- a subscription system (send “subscribe” / “unsubscribe” to join or leave the list).
- daily automation via github actions.

---

### REPO STRUCTURE
```text
astroph-bot/
├── .env                             # environment variables (api keys, credentials, gmail app password, etc.)
├── .github/workflows/               # github actions for automation
│   ├── check_subscriptions.yml      # validates and cleans up subscriber list on schedule
│   └── daily_digest.yml             # runs the daily paper curation + email digest pipeline
├── assets/                          # branding and static assets (banner.png, icons, etc.)
├── bot.py                           # main entrypoint for running the daily astro-ph digest bot
├── config.py
├── config.yaml                      # central configuration (arXiv filters, smtp settings, output options)
├── curator.py                       # handles paper ranking, keyword filtering, and relevance scoring
├── database.db                      # sqlite database used by the web dashboard and feedback tracker
├── filters.py                       # keyword filters and paper scoring logic
├── mailer.py                        # shared email sending helper used by both bot and web app
├── shared/                          # cross-module utilities shared between bot and flask webapp
│   ├── mail.py                      # email helpers (smtp, html/plaintext formatting)
│   ├── utils.py                     # general helper functions (yaml io, arXiv query builders, etc.)
│   └── db.py                        # lightweight database connector for user feedback
├── scripts/                         # command-line tools for direct subscription control
│   ├── subscribe_bot.py             # adds new users to the mailing list
│   └── unsubscribe_bot.py           # removes users from the mailing list
├── webapp/                          # flask front-end + backend for user interaction
│   ├── routes_frontend.py           # user-facing pages (dashboard, preferences, feedback, etc.)
│   ├── routes_backend.py            # api routes for preferences, recommendations, and feedback
│   ├── templates/                   # html templates (jinja2) for all web views
│   ├── static/                      # front-end assets served by flask
│   │   ├── css/style.css            # main site stylesheet
│   │   ├── js/                      # javascript modules for interactive pages
│   │   │   ├── dashboard.js         # manages preferences + feedback form submission
│   │   │   ├── recommendations.js   # handles like/dislike actions on recommended papers
│   │   │   └── subscriptions.js     # handles subscribe/unsubscribe ui
│   │   └── img/                     # local images (banner, icons)
│   ├── feedback.db                  # stores like/dislike history and user feedback
│   ├── user_feedback.txt            # plaintext fallback log for feedback (optional)
│   └── user_prefs.yaml              # stores each user's saved preferences (keywords, authors, etc.)
├── notebooks/                       # dev notes or experimental analysis in jupyter
├── secrets/                         # oauth tokens and gmail credentials (never commit these!)
│   ├── credentials.json
│   └── token.json
├── tests/                           # unit tests and verification scripts
├── vercel.json                      # deployment configuration for vercel hosting
└── README.md                        # this documentation file
```

---

### HOW TO RUN LOCALLY

1. clone this repo:
   ```bash
   `git clone https://github.com/ajdavis25/astro-ph-digest-bot.git`
   `cd astroph-bot`
   ```
2. create a virtual environment:
    ```bash
    `python -m venv venv`
    `.\venv\Scripts\Activate.ps1`
    ```

3. install dependencies:
    ```bash
    `pip install -r requirements.txt`
    ```

4. create a .env file:
    `EMAIL_FROM=youremail@gmail.com`
    `EMAIL_PASS=your_app_password`
    ### *NOTE:* gmail app passwords are **NOT** your real password.
    create one under:
        google account -> security -> app passwords
    
5. run the bot:
    ```bash
    `python bot.py`
    ```

---

### HOW TO SUBSCRIBE/UNSUBSCRIBE
- **subscribe:** send an email with the subject `subscribe` to `arxivastrophbot@gmail.com`
- **unsubscribe:** send an email with the subject `unsubscribe`

the bot will automatically update the mailing list every 15 minutes and send a welcome/farewell message

---

### DEFAULT TOPICS
by default, new users will receive digests including:

```yaml
any_keywords:
  - black hole
  - neutron star
  - accretion
  - jet
  - AGN
  - galaxy
  - cosmology
  - exoplanet
  - star formation
  - polarization
  - GRMHD
  - radiative transfer
authors:
  - Anantua
  - Curd
  - Gußmann
  - Quataert
  - Blandford
  - Tchekhovskoy
  - Narayan
  - Event Horizon Telescope
```

---

### DEPARTMENT SETUP (for admins)
if you're setting this up for a department or research group:

1. create a gmail account for the bot (e.g. `arxivastrophbot@gmail.com`)

2. enable **app passwords** in the google account and create one for “mail”.

3. in your forked github repo, go to:  
   **settings -> secrets and variables -> actions -> new repository secret**
   - `EMAIL_FROM` = the bot’s gmail address  
   - `EMAIL_PASS` = the app password from step 2

4. the bot will automatically run daily at **8 am central** and email all subscribed users.  
   to test manually, go to the **actions** tab and run **“daily astro-ph digest”** using the “run workflow” button.

> optional: to enable subscription emails, upload your gmail API `credentials.json` and `token.json` inside a `secrets/` folder (not tracked by git).

---

### EXTENDING THE BOT
want to modify how the bot works? here’s how to extend or customize it safely:

#### change the daily run time
open `.github/workflows/daily_digest.yml` and update the `cron` line:

```yaml
on:
  schedule:
    - cron: "0 13 * * *"  # 8am central
```

the `13` here means `1300 utc = 8:00 am central`
to run at 9am central, change it to `"0 14 * * *"`

### add or adjust topics
edit `defaults.yaml` (used for new subscribers) or your own `config.yaml` to update the keyword filters:

```yaml
any_keywords:
  - black hole
  - neutron star
  - exoplanet
  - high-energy astrophysics
authors:
  - Anantua
  - Blandford
  - Quataert
```

you can make these as broad or specific as you like. the bot scores each paper based on keyword frequency and relevance.

#### add new filters
custom logic lives in `filters.py`
for example, to exclude reviews or tutorials automatically, you can add:

```python
EXCLUDE_TERMS = ["review", "tutorial", "conference summary"]

def is_relevant(paper, prefs):
    title = paper["title"].lower()
    if any(term in title for term in EXCLUDE_TERMS):
        return False
    return True
```

#### customize the email template
html and plain-text bodies are built in `mailer.py`
you can tweak formatting, add emojis, or include links to institutional papers easily.

#### for developers
- flask backend (in `webapp/`) can be used for future user dashboards or manual curation.
- the bot is modular: new sources (ADS, NASA, etc.) can be integrated with new parser modules under `parsers.py`.
- PRs are welcome - just don't break the 8am cst vibe.

---

### CREDITS
built by ashton davis @ utsa
runs daily at 8:00 am cst via github actions.
this project is open-source and hackable, PRs welcome.

have fun, and bite me stanford!
