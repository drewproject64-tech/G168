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

# ============================================================
# G168 SPORT - Telegram Sports Schedule Utility
# ============================================================
# Environment variable required:
#   BOT_TOKEN = your Telegram bot token
#
# Storage:
#   SQLite database (DATABASE_PATH, defaults to g168_sport.db)
#
# This bot is intentionally a sports organization utility.
# It does NOT provide betting tips, odds, predictions, gambling
# services, or financial/sports wagering recommendations.
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("g168_sport")

BOT_NAME = "G168 SPORT"
DATABASE_PATH = os.getenv("DATABASE_PATH", "g168_sport.db")

ADD_MATCH, ADD_NOTE = range(2)


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                match_text TEXT NOT NULL,
                match_time TEXT,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_match(user_id: int, match_text: str, match_time: str = "", note: str = "") -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO matches (user_id, match_text, match_time, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, match_text, match_time, note, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def get_matches(user_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM matches WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()


def get_match(user_id: int, match_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM matches WHERE id = ? AND user_id = ?",
            (match_id, user_id),
        ).fetchone()


def delete_match(user_id: int, match_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM matches WHERE id = ? AND user_id = ?",
            (match_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_matches(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM matches WHERE user_id = ?", (user_id,))
        conn.commit()


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Match", callback_data="add"),
                InlineKeyboardButton("📋 My Matches", callback_data="matches"),
            ],
            [
                InlineKeyboardButton("📅 Schedule", callback_data="schedule"),
                InlineKeyboardButton("❓ How It Works", callback_data="help"),
            ],
            [InlineKeyboardButton("🗑️ Clear Matches", callback_data="clear")],
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
    )


def format_match(row):
    text = f"⚽ <b>{row['match_text']}</b>"
    if row["match_time"]:
        text += f"\n🕒 {row['match_time']}"
    if row["note"]:
        text += f"\n📝 {row['note']}"
    return text


WELCOME_TEXT = (
    "⚽ <b>Welcome to G168 SPORT!</b>\n\n"
    "Your simple sports schedule organizer.\n\n"
    "Use G168 SPORT to:\n"
    "📅 Add upcoming matches\n"
    "📋 View your saved matches\n"
    "📝 Keep personal match notes\n"
    "🗑️ Remove matches you no longer need\n\n"
    "<b>Example:</b>\n"
    "Tap ➕ Add Match and send:\n"
    "<code>Arsenal vs Chelsea | Saturday 18:30</code>\n\n"
    "Your match is saved to your personal list."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_match", None)
    await update.message.reply_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>How G168 SPORT works</b>\n\n"
        "1. Tap <b>➕ Add Match</b>.\n"
        "2. Send a match in this format:\n"
        "<code>Team A vs Team B | Saturday 18:30</code>\n"
        "3. The match is saved to your personal list.\n"
        "4. Open <b>📋 My Matches</b> to view or remove saved matches.\n\n"
        "You can also use /start, /add, /matches, /schedule, /help, and /clear.\n\n"
        "G168 SPORT is an organization utility and does not provide betting tips, odds, predictions, or gambling services.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_match", None)
    await update.message.reply_text(
        "➕ <b>Add a match</b>\n\n"
        "Send it as:\n"
        "<code>Team A vs Team B | Saturday 18:30</code>\n\n"
        "The time is optional. Example:\n"
        "<code>Arsenal vs Chelsea</code>",
        parse_mode="HTML",
    )
    return ADD_MATCH


async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_match", None)
    await query.message.reply_text(
        "➕ <b>Add a match</b>\n\n"
        "Send it as:\n"
        "<code>Team A vs Team B | Saturday 18:30</code>\n\n"
        "The time is optional. Example:\n"
        "<code>Arsenal vs Chelsea</code>",
        parse_mode="HTML",
    )
    return ADD_MATCH


async def receive_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if len(raw) < 3 or len(raw) > 200:
        await update.message.reply_text("Please send a short match name, up to 200 characters.")
        return ADD_MATCH

    parts = [part.strip() for part in raw.split("|", 1)]
    match_text = parts[0]
    match_time = parts[1] if len(parts) == 2 else ""

    if len(match_text) < 3:
        await update.message.reply_text("Please include the teams or event name.")
        return ADD_MATCH

    context.user_data["pending_match"] = {
        "match_text": match_text,
        "match_time": match_time,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📝 Add Note", callback_data="note_yes"),
                InlineKeyboardButton("⏭️ Skip Note", callback_data="note_no"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_add")],
        ]
    )

    await update.message.reply_text(
        f"✅ Got it:\n\n⚽ <b>{match_text}</b>"
        + (f"\n🕒 {match_time}" if match_time else "")
        + "\n\nWould you like to add a personal note?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return ADD_NOTE


async def note_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_match")
    if not pending:
        await query.edit_message_text("Your add-match session expired. Tap Add Match again.")
        return ConversationHandler.END

    if query.data == "note_yes":
        await query.edit_message_text(
            "📝 Send your personal note now.\n\nExample: <code>Watch second half</code>",
            parse_mode="HTML",
        )
        return ADD_NOTE

    if query.data == "note_no":
        return await save_pending_match(update, context, note="")

    if query.data == "cancel_add":
        context.user_data.pop("pending_match", None)
        await query.edit_message_text("❌ Match not saved.")
        return ConversationHandler.END

    return ADD_NOTE


async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    if len(note) > 300:
        await update.message.reply_text("Please keep the note under 300 characters.")
        return ADD_NOTE
    return await save_pending_match(update, context, note=note)


async def save_pending_match(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str):
    pending = context.user_data.pop("pending_match", None)
    if not pending:
        target = update.effective_message
        await target.reply_text("Your add-match session expired. Please use /add again.")
        return ConversationHandler.END

    match_id = add_match(
        update.effective_user.id,
        pending["match_text"],
        pending["match_time"],
        note,
    )

    target = update.effective_message
    await target.reply_text(
        "✅ <b>Match saved!</b>\n\n"
        f"⚽ {pending['match_text']}"
        + (f"\n🕒 {pending['match_time']}" if pending["match_time"] else "")
        + (f"\n📝 {note}" if note else "")
        + f"\n\nID: #{match_id}",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_match", None)
    await update.message.reply_text("❌ Cancelled. Nothing was saved.", reply_markup=main_keyboard())
    return ConversationHandler.END


async def matches_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_matches(query.message, query.from_user.id, edit=True)


async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_matches(update.message, update.effective_user.id, edit=False)


async def show_matches(message, user_id: int, edit: bool = False):
    rows = get_matches(user_id)
    if not rows:
        text = (
            "📋 <b>My Matches</b>\n\n"
            "You haven't saved any matches yet.\n\n"
            "Tap ➕ Add Match to create your first one."
        )
        markup = main_keyboard()
    else:
        lines = [f"📋 <b>Your saved matches ({len(rows)})</b>\n"]
        buttons = []
        for row in rows[:20]:
            lines.append(format_match(row) + f"\n🔹 ID: #{row['id']}\n")
            buttons.append(
                [InlineKeyboardButton(f"🗑️ Delete #{row['id']}", callback_data=f"delete:{row['id']}")]
            )
        if len(rows) > 20:
            lines.append("\nShowing the latest 20 matches.")
        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
        text = "\n".join(lines)
        markup = InlineKeyboardMarkup(buttons)

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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


async def schedule_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = get_matches(query.from_user.id)
    if not rows:
        await query.edit_message_text(
            "📅 <b>Your Schedule</b>\n\nYour schedule is empty. Add a match to get started.",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return

    with_time = [r for r in rows if r["match_time"]]
    without_time = [r for r in rows if not r["match_time"]]
    lines = ["📅 <b>Your Sports Schedule</b>\n"]
    if with_time:
        lines.append("<b>Upcoming / timed items</b>")
        for row in with_time[:20]:
            lines.append(f"⚽ {row['match_text']} — 🕒 {row['match_time']}")
    if without_time:
        lines.append("\n<b>Saved without a time</b>")
        for row in without_time[:20]:
            lines.append(f"⚽ {row['match_text']}")

    await query.edit_message_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def clear_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = get_matches(query.from_user.id)
    if not rows:
        await query.edit_message_text(
            "🗑️ There are no saved matches to clear.", reply_markup=main_keyboard()
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes, clear all", callback_data="clear_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="home"),
            ]
        ]
    )
    await query.edit_message_text(
        f"🗑️ <b>Clear all matches?</b>\n\nThis will permanently remove your {len(rows)} saved match(es).",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def clear_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Matches cleared.")
    clear_matches(query.from_user.id)
    await query.edit_message_text(
        "✅ All saved matches have been cleared.", reply_markup=main_keyboard()
    )


async def home_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=main_keyboard())


async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❓ <b>How G168 SPORT works</b>\n\n"
        "• <b>➕ Add Match</b> — save a match or sports event.\n"
        "• <b>📋 My Matches</b> — view and delete saved items.\n"
        "• <b>📅 Schedule</b> — see saved events and times.\n"
        "• <b>🗑️ Clear Matches</b> — remove your saved list.\n\n"
        "Example:\n<code>Arsenal vs Chelsea | Saturday 18:30</code>\n\n"
        "G168 SPORT is a sports organization utility. It does not provide betting tips, odds, predictions, or gambling services.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


async def text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I can help you organize your sports schedule. Use the buttons below or try /add.",
        reply_markup=main_keyboard(),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled bot error", exc_info=context.error)


def build_application():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    application = Application.builder().token(token).build()

    add_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_command),
            CallbackQueryHandler(add_button, pattern=r"^add$"),
        ],
        states={
            ADD_MATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_match)],
            ADD_NOTE: [
                CallbackQueryHandler(note_button, pattern=r"^(note_yes|note_no|cancel_add)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("matches", matches_command))
    application.add_handler(CommandHandler("schedule", matches_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("clear", clear_button))
    application.add_handler(add_conversation)

    application.add_handler(CallbackQueryHandler(matches_button, pattern=r"^matches$"))
    application.add_handler(CallbackQueryHandler(schedule_button, pattern=r"^schedule$"))
    application.add_handler(CallbackQueryHandler(help_button, pattern=r"^help$"))
    application.add_handler(CallbackQueryHandler(clear_button, pattern=r"^clear$"))
    application.add_handler(CallbackQueryHandler(clear_yes, pattern=r"^clear_yes$"))
    application.add_handler(CallbackQueryHandler(delete_button, pattern=r"^delete:\d+$"))
    application.add_handler(CallbackQueryHandler(home_button, pattern=r"^home$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_fallback))
    application.add_error_handler(error_handler)

    return application


def main():
    init_db()
    application = build_application()
    logger.info("Starting %s", BOT_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
