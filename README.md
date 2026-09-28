# Finura Global FAQ Bot

A Telegram bot that answers Finura Global FAQs. Users can browse by topic or type a question.

## Files
- `bot.py` - the bot (no need to edit)
- `faqs.py` - all questions and answers (edit this to change content)
- `.env.example` - settings template
- `requirements.txt`, `railway.json`, `.python-version` - for hosting

## Settings
| Name | Example | Notes |
|---|---|---|
| BOT_TOKEN | 123456:ABC... | From BotFather. Keep secret. |
| SUPPORT_USERNAME | @finuraglobalsupport | Support group/account |
| CHANNEL_URL | https://t.me/finuraglobal | Leave empty until created |
| WEBSITE_URL | https://finuraglobal.com | Leave empty until ready |
| MIN_WITHDRAWAL | $10 USDT | Shown in withdrawal answers |

Empty CHANNEL_URL / WEBSITE_URL are fine: the bot hides those buttons and uses neutral wording.

## Test on your computer
```
pip install -r requirements.txt
cp .env.example .env      # then put your token in .env
python bot.py
```
Open your bot in Telegram and send /start. Press Ctrl+C to stop.

## Deploy on Railway
1. Upload this folder to a **private** GitHub repo (never upload `.env`).
2. On railway.com: New Project -> Deploy from GitHub repo -> pick the repo.
3. Open the service -> **Variables** -> add BOT_TOKEN, SUPPORT_USERNAME, MIN_WITHDRAWAL (and CHANNEL_URL / WEBSITE_URL when ready).
4. Railway deploys automatically. Check **Deployments -> Logs** for "Bot started with 120 FAQs".

Only run ONE copy of the bot at a time. Stop your local copy before deploying, or Telegram will show a "Conflict" error.

## Updating FAQs
Edit `faqs.py`, push to GitHub, and Railway redeploys automatically.
