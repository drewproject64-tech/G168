import logging
import os
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

BOT_NAME = "G168 SPORT"
DATABASE_PATH = os.getenv("DATABASE_PATH", "g168_sport.db")
ADD_MATCH, ADD_NOTE = range(2)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(BOT_NAME)


def db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                match_text TEXT NOT NULL,
                match_time TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        conn.commit()


def save_match(user_id, match_text, match_time="", note=""):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO matches (user_id, match_text, match_time, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, match_text, match_time, note, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def user_matches(user_id):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM matches WHERE user_id=? ORDER BY id DESC", (user_id,)
        ).fetchall()


def delete_match(user_id, match_id):
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM matches WHERE id=? AND user_id=?", (match_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def clear_user_matches(user_id):
    with db() as conn:
        cur = conn.execute("DELETE FROM matches WHERE user_id=?", (user_id,))
        conn.commit()
        return cur.rowcount


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Match", callback_data="add"),
         InlineKeyboardButton("📋 My Matches", callback_data="matches")],
        [InlineKeyboardButton("📅 Schedule", callback_data="schedule"),
         InlineKeyboardButton("❓ How It Works", callback_data="help")],
        [InlineKeyboardButton("🗑️ Clear Matches", callback_data="clear")],
    ])


def home_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]])


WELCOME = (
    "⚽ <b>Welcome to G168 SPORT!</b>\n\n"
    "Your simple sports schedule organizer.\n\n"
    "Use G168 SPORT to:\n"
    "📅 Add upcoming matches\n"
    "📋 View your saved matches\n"
    "📝 Keep personal match notes\n"
    "🗑️ Remove matches you no longer need\n\n"
    "<b>Try this example:</b>\n"
    "Tap ➕ Add Match and send:\n"
    "<code>Arsenal vs Chelsea | Saturday 18:30</code>\n\n"
    "Your match will be saved to your personal list."
)

HELP = (
    "❓ <b>How G168 SPORT works</b>\n\n"
    "• <b>➕ Add Match</b> — save a match or sports event.\n"
    "• <b>📋 My Matches</b> — view and delete saved items.\n"
    "• <b>📅 Schedule</b> — see saved events and times.\n"
    "• <b>🗑️ Clear Matches</b> — remove your saved list.\n\n"
    "<b>Example:</b>\n<code>Arsenal vs Chelsea | Saturday 18:30</code>\n\n"
    "G168 SPORT is a sports organization utility. It does not provide betting tips, odds, predictions, or gambling services."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending", None)
    await update.message.reply_text(WELCOME, parse_mode="HTML", reply_markup=menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode="HTML", reply_markup=home_button())


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending", None)
    await update.message.reply_text(
        "➕ <b>Add a match</b>\n\n"
        "Send the match like this:\n"
        "<code>Team A vs Team B | Saturday 18:30</code>\n\n"
        "The time is optional. Example:\n"
        "<code>Arsenal vs Chelsea</code>\n\n"
        "Use /cancel to stop.",
        parse_mode="HTML",
    )
    return ADD_MATCH


async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending", None)
    await query.message.reply_text(
        "➕ <b>Add a match</b>\n\n"
        "Send the match like this:\n"
        "<code>Team A vs Team B | Saturday 18:30</code>\n\n"
        "The time is optional. Example:\n"
        "<code>Arsenal vs Chelsea</code>\n\n"
        "Use /cancel to stop.",
        parse_mode="HTML",
    )
    return ADD_MATCH


async def receive_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if not 3 <= len(raw) <= 200:
        await update.message.reply_text("Please send a match name between 3 and 200 characters.")
        return ADD_MATCH

    parts = [p.strip() for p in raw.split("|", 1)]
    name = parts[0]
    match_time = parts[1] if len(parts) == 2 else ""
    if len(name) < 3:
        await update.message.reply_text("Please include the teams or event name.")
        return ADD_MATCH

    context.user_data["pending"] = {"name": name, "time": match_time}
    preview = f"⚽ <b>{name}</b>" + (f"\n🕒 {match_time}" if match_time else "")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Add Note", callback_data="note_yes"),
         InlineKeyboardButton("⏭️ Skip Note", callback_data="note_no")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_add")],
    ])
    await update.message.reply_text(
        f"✅ Got it:\n\n{preview}\n\nWould you like to add a personal note?",
        parse_mode="HTML", reply_markup=keyboard,
    )
    return ADD_NOTE


async def note_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("pending"):
        await query.edit_message_text("Your add-match session expired. Tap Add Match again.")
        return ConversationHandler.END

    if query.data == "note_yes":
        await query.edit_message_text(
            "📝 Send your personal note now.\n\nExample: <code>Watch second half</code>",
            parse_mode="HTML",
        )
        return ADD_NOTE

    if query.data == "note_no":
        return await finish_match(update, context, "")

    context.user_data.pop("pending", None)
    await query.edit_message_text("❌ Match not saved.", reply_markup=menu())
    return ConversationHandler.END


async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    if len(note) > 300:
        await update.message.reply_text("Please keep your note under 300 characters.")
        return ADD_NOTE
    return await finish_match(update, context, note)


async def finish_match(update: Update, context: ContextTypes.DEFAULT_TYPE, note=""):
    pending = context.user_data.pop("pending", None)
    if not pending:
        await update.effective_message.reply_text("Your session expired. Please use /add again.")
        return ConversationHandler.END

    match_id = save_match(
        update.effective_user.id, pending["name"], pending["time"], note
    )
    text = "✅ <b>Match saved!</b>\n\n" + f"⚽ {pending['name']}"
    if pending["time"]:
        text += f"\n🕒 {pending['time']}"
    if note:
        text += f"\n📝 {note}"
    text += f"\n\nID: #{match_id}"
    await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=menu())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending", None)
    await update.message.reply_text("❌ Cancelled. Nothing was saved.", reply_markup=menu())
    return ConversationHandler.END


def match_text(row):
    text = f"⚽ <b>{row['match_text']}</b>"
    if row["match_time"]:
        text += f"\n🕒 {row['match_time']}"
    if row["note"]:
        text += f"\n📝 {row['note']}"
    return text


async def show_matches(message, user_id, edit=False):
    rows = user_matches(user_id)
    if not rows:
        text = "📋 <b>My Matches</b>\n\nYou haven't saved any matches yet.\n\nTap ➕ Add Match to create your first one."
        markup = menu()
    else:
        lines = [f"📋 <b>Your saved matches ({len(rows)})</b>\n"]
        buttons = []
        for row in rows[:20]:
            lines.append(match_text(row) + f"\n🔹 ID: #{row['id']}\n")
            buttons.append([InlineKeyboardButton(f"🗑️ Delete #{row['id']}", callback_data=f"delete:{row['id']}")])
        if len(rows) > 20:
            lines.append("Showing the latest 20 matches.")
        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
        text = "\n".join(lines)
        markup = InlineKeyboardMarkup(buttons)

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def matches_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_matches(update.message, update.effective_user.id)


async def matches_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_matches(query.message, query.from_user.id, edit=True)


async def show_schedule(message, user_id, edit=False):
    rows = user_matches(user_id)
    if not rows:
        text = "📅 <b>Your Sports Schedule</b>\n\nYour schedule is empty. Add a match to get started."
    else:
        lines = ["📅 <b>Your Sports Schedule</b>\n"]
        timed = [r for r in rows if r["match_time"]]
        untimed = [r for r in rows if not r["match_time"]]
        if timed:
            lines.append("<b>Saved with time</b>")
            lines.extend(f"⚽ {r['match_text']} — 🕒 {r['match_time']}" for r in timed[:20])
        if untimed:
            lines.append("\n<b>Saved without time</b>")
            lines.extend(f"⚽ {r['match_text']}" for r in untimed[:20])
        text = "\n".join(lines)

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=home_button())
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=home_button())


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_schedule(update.message, update.effective_user.id)


async def schedule_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_schedule(query.message, query.from_user.id, edit=True)


async def delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        match_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Invalid match.", show_alert=True)
        return
    if delete_match(query.from_user.id, match_id):
        await query.answer("Match deleted.")
        await show_matches(query.message, query.from_user.id, edit=True)
    else:
        await query.answer("Match not found.", show_alert=True)


async def clear_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = user_matches(query.from_user.id)
    if not rows:
        await query.edit_message_text("🗑️ There are no saved matches to clear.", reply_markup=menu())
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, clear all", callback_data="clear_yes"),
        InlineKeyboardButton("❌ Cancel", callback_data="home"),
    ]])
    await query.edit_message_text(
        f"🗑️ <b>Clear all matches?</b>\n\nThis will permanently remove your {len(rows)} saved match(es).",
        parse_mode="HTML", reply_markup=keyboard,
    )


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = clear_user_matches(update.effective_user.id)
    await update.message.reply_text(
        f"✅ Cleared {count} saved match(es)." if count else "🗑️ There are no saved matches to clear.",
        reply_markup=menu(),
    )


async def clear_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    count = clear_user_matches(query.from_user.id)
    await query.answer("Matches cleared.")
    await query.edit_message_text(f"✅ Cleared {count} saved match(es).", reply_markup=menu())


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(WELCOME, parse_mode="HTML", reply_markup=menu())


async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(HELP, parse_mode="HTML", reply_markup=home_button())


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I can help you organize your sports schedule. Use the buttons below or try /add.",
        reply_markup=menu(),
    )


async def errors(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)


def build_app():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    app = Application.builder().token(token).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("add", add_start), CallbackQueryHandler(add_button, pattern=r"^add$")],
        states={
            ADD_MATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_match)],
            ADD_NOTE: [
                CallbackQueryHandler(note_button, pattern=r"^(note_yes|note_no|cancel_add)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("matches", matches_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conversation)
    app.add_handler(CallbackQueryHandler(matches_button, pattern=r"^matches$"))
    app.add_handler(CallbackQueryHandler(schedule_button, pattern=r"^schedule$"))
    app.add_handler(CallbackQueryHandler(help_button, pattern=r"^help$"))
    app.add_handler(CallbackQueryHandler(clear_prompt, pattern=r"^clear$"))
    app.add_handler(CallbackQueryHandler(clear_yes, pattern=r"^clear_yes$"))
    app.add_handler(CallbackQueryHandler(delete_button, pattern=r"^delete:\d+$"))
    app.add_handler(CallbackQueryHandler(home, pattern=r"^home$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    app.add_error_handler(errors)
    return app


def main():
    init_db()
    logger.info("Starting %s", BOT_NAME)
    build_app().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
