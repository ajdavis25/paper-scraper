![Daily astro-ph Digest](https://github.com/ajdavis25/astro-ph-digest-bot/actions/workflows/daily_digest.yml/badge.svg)


built out of spite because stanford gatekept vox charta


astroph-bot/
 ├─ bot.py
 ├─ filters.py
 ├─ mailer.py
 ├─ parsers.py
 ├─ config.yaml
 ├─ requirements.txt
 └─ .github/
     └─ workflows/
         └─ daily_digest.yml


### HOW TO RUN LOCALLY

1. you can fork and clone your own version

2. create a .env file with the structure

``# .env
EMAIL_FROM=youremail@email.com
EMAIL_PASS=app_password``

you can use any email you'd like and the app_password IS NOT THE PASSWORD TO THE EMAIL ADDRESS
gmail let's you make free app passwords, go to:
    - Account -> Settings -> `search` "app passwords"
    create a new app password name it whatever you like it will look like
        `abcd efgh ijkl mnop`
        COPY THIS AND GO TO GITHUB

    in the github fork you made go to the settings
    Settings -> under `Security` look for Secrets and variables -> Actions
    click `New repository secret`
        name one EMAIL_PASS
            paste your app password like this:
                `abcdefghijklmnop`
        name another EMAIL_FROM
            youremail@gmail.com

* note: special characters require logic to romanize the characters (see filters.py)

now you can create a config.yaml and add authors, keywords, whatever you'd like!

have fun, and bite me stanford!