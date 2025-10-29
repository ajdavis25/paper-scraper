![Build](https://github.com/ajdavis25/paper-scraper/actions/workflows/daily_digest.yml/badge.svg)
![License](https://img.shields.io/github/license/ajdavis25/paper-scraper)
![Stars](https://img.shields.io/github/stars/ajdavis25/paper-scraper?style=social)

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
astroph-bot/
├─ bot.py                   # main digest script
├─ filters.py               # keyword + author filtering
├─ mailer.py                # email sending logic
├─ parsers.py               # arXiv feed parsing
├─ scripts/
│ ├─ subscribe_bot.py       # handles "subscribe" emails
│ └─ unsubscribe_bot.py     # handles "unsubscribe" emails
├─ defaults.yaml            # default keywords for new users
├─ requirements.txt
├─ .github/workflows/
│ └─ daily_digest.yml       # daily automation (8am CT)
└─ webapp/                  # optional flask frontend

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
