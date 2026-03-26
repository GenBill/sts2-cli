# Telegram Remote Deploy Guide

This guide is for running the Telegram remote-play bot on your **home PC** so you can play Slay the Spire 2 remotely from Telegram.

## What this bot does

- Runs the real `sts2-cli` headless engine locally on your home PC
- Accepts Telegram commands / inline button clicks
- Sends game state back as text
- Does **not** require AI to play

## Prerequisites

On the home PC, install:

- Steam
- Slay the Spire 2
- .NET 9+
- Python 3.9+
- Git

## 1. Clone your fork

```bash
git clone git@github.com:GenBill/sts2-cli.git
cd sts2-cli
git checkout genbill/telegram-remote-bot
```

## 2. First-time game setup

The project needs the real game files from your Steam install.

```bash
./setup.sh
```

If auto-detection fails, pass the game directory explicitly.

## 3. Install Python bot dependency

```bash
pip install -r requirements-telegram.txt
```

## 4. Prepare a Telegram bot token

Create a Telegram bot via BotFather and export the token:

```bash
export STS2_TELEGRAM_BOT_TOKEN="<your-bot-token>"
```

## 5. Run the bot

```bash
python3 python/telegram_bot.py
```

## 6. Telegram commands

```text
/start_run [character] [ascension]
/state
/map
/play <card_index> [target_index]
/end
/choose <index>
/skip
/quit_run
```

## 7. Recommended usage flow

- `/start_run Ironclad 0`
- Read the returned state
- Use inline buttons when available
- Fall back to commands for targeted actions

## Notes

- This is currently **single-process, in-memory session storage**
- If you restart the bot process, the current run is lost
- Best deployed on a machine that stays on at home
- For first deployment, run it in a terminal/tmux and watch logs

## Next upgrade ideas

- persistent save/reconnect support
- richer shop/event handling
- target selection buttons
- multiple concurrent authorized users
- OpenClaw integration layer
