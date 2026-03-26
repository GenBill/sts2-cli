#!/usr/bin/env python3
"""
Telegram bot for remote-playing sts2-cli.

Current goals:
- text-first state rendering
- inline buttons for common actions
- minimal deployment friction for home PC
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from headless_client import RunConfig, SessionStore

store = SessionStore()


def session_key_from_parts(chat_id: int, user_id: Optional[int]) -> str:
    return f"{chat_id}:{user_id if user_id else 'unknown'}"


def session_key(update: Update) -> str:
    chat = update.effective_chat
    user = update.effective_user
    return session_key_from_parts(chat.id, user.id if user else None)


def fmt_state(state: Dict[str, Any]) -> str:
    dec = state.get("decision", "?")
    lines = [f"🎮 **StS2 Remote**", f"**Decision:** `{dec}`"]

    ctx = state.get("context") or {}
    if ctx:
        act = ctx.get("act_name")
        floor = ctx.get("floor")
        lines.append(f"🗺️ Act/Floor: `{act}` / `{floor}`")

    player = state.get("player") or {}
    if player:
        lines.append(
            f"❤️ HP `{player.get('hp', '?')}/{player.get('max_hp', '?')}`   💰 Gold `{player.get('gold', '?')}`   🃏 Deck `{player.get('deck_size', '?')}`"
        )

    if dec == "combat_play":
        lines.append(f"⚡ Energy `{state.get('energy', '?')}/{state.get('max_energy', '?')}`")
        enemies = state.get("enemies") or []
        if enemies:
            lines.append("**👾 Enemies**")
            for e in enemies[:6]:
                lines.append(
                    f"- `{e.get('index')}` {e.get('name')} HP `{e.get('hp')}/{e.get('max_hp')}` Block `{e.get('block', 0)}`"
                )
        hand = state.get("hand") or []
        if hand:
            lines.append("**🖐️ Hand**")
            for c in hand[:10]:
                playable = "✅" if c.get("can_play") else "⛔"
                lines.append(
                    f"- {playable} `{c.get('index')}` {c.get('name')} cost `{c.get('cost')}` type `{c.get('type')}`"
                )

    elif dec == "map_select":
        choices = state.get("choices") or []
        lines.append("**🗺️ Map choices**")
        for i, ch in enumerate(choices):
            lines.append(f"- `{i}` {ch.get('type')} col `{ch.get('col')}` row `{ch.get('row')}`")

    elif dec == "card_reward":
        cards = state.get("cards") or []
        lines.append("**🎁 Card reward**")
        for c in cards:
            lines.append(f"- `{c.get('index')}` {c.get('name')} ({c.get('type')})")

    elif dec in ("rest_site", "event_choice"):
        opts = state.get("options") or []
        lines.append("**🧭 Options**")
        for o in opts:
            label = o.get("option_id", o.get("title", "option"))
            lines.append(f"- `{o.get('index')}` {label}")

    elif dec == "shop":
        lines.append("🛒 Shop state loaded. Use buttons / commands to continue.")

    elif dec == "game_over":
        lines.append(f"🏁 Victory: `{state.get('victory')}`")

    return "\n".join(lines)


def build_keyboard(state: Dict[str, Any]) -> Optional[InlineKeyboardMarkup]:
    dec = state.get("decision")
    rows: list[list[InlineKeyboardButton]] = []

    if dec == "combat_play":
        hand = state.get("hand") or []
        playable = [c for c in hand if c.get("can_play")]
        for c in playable[:6]:
            rows.append([
                InlineKeyboardButton(
                    f"🃏 {c.get('index')}:{c.get('name')[:18]}",
                    callback_data=f"play:{c.get('index')}",
                )
            ])
        rows.append([
            InlineKeyboardButton("⚡ End Turn", callback_data="end"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
        ])

    elif dec == "map_select":
        choices = state.get("choices") or []
        for i, ch in enumerate(choices[:8]):
            rows.append([
                InlineKeyboardButton(
                    f"🗺️ {i}:{ch.get('type')}",
                    callback_data=f"choose:{i}",
                )
            ])
        rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh")])

    elif dec == "card_reward":
        cards = state.get("cards") or []
        for c in cards[:8]:
            rows.append([
                InlineKeyboardButton(
                    f"🎁 {c.get('index')}:{c.get('name')[:18]}",
                    callback_data=f"choose:{c.get('index')}",
                )
            ])
        rows.append([
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
        ])

    elif dec in ("rest_site", "event_choice"):
        opts = state.get("options") or []
        for o in opts[:8]:
            label = str(o.get("option_id", o.get("title", "opt")))[:20]
            rows.append([
                InlineKeyboardButton(
                    f"✨ {o.get('index')}:{label}",
                    callback_data=f"choose:{o.get('index')}",
                )
            ])
        rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh")])

    elif dec == "game_over":
        rows.append([InlineKeyboardButton("🆕 New Run", callback_data="noop")])

    else:
        rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh")])

    return InlineKeyboardMarkup(rows) if rows else None


async def reply_state(message_target, state: Dict[str, Any]):
    text = fmt_state(state)
    kb = build_keyboard(state)
    await message_target.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def edit_state(query, state: Dict[str, Any]):
    text = fmt_state(state)
    kb = build_keyboard(state)
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def require_session(update: Update):
    key = session_key(update)
    cli = store.get(key)
    if not cli:
        if update.message:
            await update.message.reply_text("还没有运行中的局。先用 /start_run [角色] [ascension]")
        elif update.callback_query:
            await update.callback_query.answer("还没有运行中的局", show_alert=True)
        return None
    return cli


async def cmd_start_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    character = context.args[0] if len(context.args) >= 1 else "Ironclad"
    ascension = int(context.args[1]) if len(context.args) >= 2 else 0
    key = session_key(update)
    cli = store.create(key, RunConfig(character=character, ascension=ascension, lang="zh", log=True))
    await reply_state(update.message, cli.state)


async def cmd_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    await reply_state(update.message, cli.state)


async def cmd_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    data = cli.get_map()
    rows = data.get("rows") or []
    lines = ["**🗺️ Full map**"]
    for row in rows[:8]:
        parts = []
        for n in row:
            parts.append(f"({n.get('row')},{n.get('col')}:{n.get('type')})")
        lines.append(" ".join(parts))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    if not context.args:
        await update.message.reply_text("用法：/play <card_index> [target_index]")
        return
    args: Dict[str, Any] = {"card_index": int(context.args[0])}
    if len(context.args) >= 2:
        args["target_index"] = int(context.args[1])
    state = cli.action("play_card", args)
    await reply_state(update.message, state)


async def cmd_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    state = cli.action("end_turn")
    await reply_state(update.message, state)


async def cmd_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    if not context.args:
        await update.message.reply_text("用法：/choose <index>")
        return
    idx = int(context.args[0])
    dec = (cli.state or {}).get("decision")
    if dec == "map_select":
        choices = (cli.state or {}).get("choices") or []
        pick = choices[idx]
        state = cli.action("select_map_node", {"col": pick["col"], "row": pick["row"]})
    elif dec == "card_reward":
        state = cli.action("select_card_reward", {"card_index": idx})
    else:
        state = cli.action("choose_option", {"option_index": idx})
    await reply_state(update.message, state)


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cli = await require_session(update)
    if not cli:
        return
    dec = (cli.state or {}).get("decision")
    if dec == "card_reward":
        state = cli.action("skip_card_reward")
    else:
        state = cli.action("skip_select")
    await reply_state(update.message, state)


async def cmd_quit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = session_key(update)
    store.close(key)
    await update.message.reply_text("🛑 已结束当前 run。")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cli = await require_session(update)
    if not cli:
        return

    data = query.data or ""
    if data == "refresh":
        await edit_state(query, cli.state)
        return
    if data == "end":
        state = cli.action("end_turn")
        await edit_state(query, state)
        return
    if data == "skip":
        dec = (cli.state or {}).get("decision")
        if dec == "card_reward":
            state = cli.action("skip_card_reward")
        else:
            state = cli.action("skip_select")
        await edit_state(query, state)
        return
    if data.startswith("play:"):
        idx = int(data.split(":", 1)[1])
        state = cli.action("play_card", {"card_index": idx})
        await edit_state(query, state)
        return
    if data.startswith("choose:"):
        idx = int(data.split(":", 1)[1])
        dec = (cli.state or {}).get("decision")
        if dec == "map_select":
            choices = (cli.state or {}).get("choices") or []
            pick = choices[idx]
            state = cli.action("select_map_node", {"col": pick["col"], "row": pick["row"]})
        elif dec == "card_reward":
            state = cli.action("select_card_reward", {"card_index": idx})
        else:
            state = cli.action("choose_option", {"option_index": idx})
        await edit_state(query, state)
        return


def main():
    token = os.environ.get("STS2_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Missing STS2_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start_run", cmd_start_run))
    app.add_handler(CommandHandler("state", cmd_state))
    app.add_handler(CommandHandler("map", cmd_map))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("end", cmd_end))
    app.add_handler(CommandHandler("choose", cmd_choose))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("quit_run", cmd_quit))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
