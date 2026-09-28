"""
Finura Global FAQ Telegram Bot

Features:
- /start menu with FAQ categories (tap to browse)
- Type any question in private chat -> bot finds the best matching answer
- Contact support, announcement channel, and website buttons
- Works in groups via commands (/faq, /support, /help)
"""

import html
import logging
import os
import re
from difflib import SequenceMatcher

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

from faqs import CATEGORIES

# ---------------------------------------------------------------------------
# Settings (from environment variables or a .env file)
# ---------------------------------------------------------------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@finuraglobalsupport").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "").strip()
WEBSITE_URL = os.getenv("WEBSITE_URL", "").strip()
MIN_WITHDRAWAL = os.getenv("MIN_WITHDRAWAL", "$10 USDT").strip()

if not SUPPORT_USERNAME.startswith("@"):
    SUPPORT_USERNAME = "@" + SUPPORT_USERNAME
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}"

PLACEHOLDERS = {
    "support": SUPPORT_USERNAME,
    "channel": CHANNEL_URL or "the official Finura Global announcement channel",
    "website": WEBSITE_URL or "shown in the official Finura Global announcement channel",
    "min_withdrawal": MIN_WITHDRAWAL,
}

PAGE_SIZE = 8  # questions per page in a category

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("finura-faq-bot")

# ---------------------------------------------------------------------------
# Search index
# ---------------------------------------------------------------------------
STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "been", "i", "me", "my",
    "you", "your", "we", "our", "it", "its", "to", "of", "in", "on", "for", "at", "by",
    "and", "or", "if", "do", "does", "did", "can", "could", "will", "would", "should",
    "what", "how", "why", "when", "where", "which", "who", "this", "that", "there",
    "with", "from", "get", "got", "any", "not", "no", "please", "pls", "plz", "tell",
    "about", "have", "has", "had", "much", "many", "so", "just", "still", "yet",
}
GREETINGS = {"hi", "hii", "hello", "hey", "hlo", "start", "menu", "help", "gm", "yo"}


def _stem(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9.%$]+", text.lower())
    return {_stem(w.strip(".")) for w in words if w.strip(".") and w not in STOPWORDS}


def _match(a: str, b: str) -> bool:
    if a == b:
        return True
    # prefix match handles withdraw/withdrawal, refer/referral, invest/investment
    return len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))


FAQS: list[dict] = []
for cat_index, cat in enumerate(CATEGORIES):
    cat["ids"] = []
    for item in cat["faqs"]:
        question, answer = item[0], item[1]
        keywords = item[2] if len(item) > 2 else ""
        faq_id = len(FAQS)
        FAQS.append({
            "id": faq_id,
            "cat": cat_index,
            "q": question,
            "a": answer.format(**PLACEHOLDERS),
            "q_tokens": tokenize(question + " " + keywords),
            "k_tokens": tokenize(keywords),
            "a_tokens": tokenize(answer),
        })
        cat["ids"].append(faq_id)


def search(query: str, limit: int = 4) -> list[dict]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    query_lower = query.lower().strip()
    results = []
    for faq in FAQS:
        q_hits = sum(1 for t in q_tokens if any(_match(t, x) for x in faq["q_tokens"]))
        a_hits = sum(1 for t in q_tokens if any(_match(t, x) for x in faq["a_tokens"]))
        k_hits = sum(1 for t in q_tokens if t in faq["k_tokens"])
        ratio = SequenceMatcher(None, query_lower, faq["q"].lower()).ratio()
        n = len(q_tokens)
        score = (q_hits / n) * 3 + (a_hits / n) * 1 + (k_hits / n) * 1.5 + ratio * 2
        if q_hits or ratio > 0.6:
            results.append((score, faq))
    results.sort(key=lambda r: r[0], reverse=True)
    return [faq for score, faq in results[:limit] if score >= 1.6]


# ---------------------------------------------------------------------------
# Keyboards & text
# ---------------------------------------------------------------------------
def short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def support_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("💬 Contact Support", url=SUPPORT_URL)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, cat in enumerate(CATEGORIES):
        row.append(InlineKeyboardButton(cat["title"], callback_data=f"c:{i}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    links = [InlineKeyboardButton("💬 Support", url=SUPPORT_URL)]
    if CHANNEL_URL.startswith("http"):
        links.append(InlineKeyboardButton("📢 Updates", url=CHANNEL_URL))
    rows.append(links)
    if WEBSITE_URL.startswith("http"):
        rows.append([InlineKeyboardButton("🌐 Official Website", url=WEBSITE_URL)])
    return InlineKeyboardMarkup(rows)


WELCOME_TEXT = (
    "👋 <b>Welcome to Finura Global Support!</b>\n\n"
    "I can answer your questions about wallets, investing, daily ROI, referrals, and withdrawals.\n\n"
    "📚 Pick a topic below, or just <b>type your question</b>\n"
    "(for example: <i>how do I withdraw?</i>)\n\n"
    "🔒 Never share your seed phrase or private key with anyone."
)

HELP_TEXT = (
    "ℹ️ <b>How to use this bot</b>\n\n"
    "• Tap /faq to browse questions by topic\n"
    "• Or type your question in this chat, like <i>minimum investment</i> or <i>withdrawal pending</i>\n"
    "• Tap /support to reach the official support team\n\n"
    f"Official support: {html.escape(SUPPORT_USERNAME)}"
)


def category_view(cat_index: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    cat = CATEGORIES[cat_index]
    ids = cat["ids"]
    pages = max(1, (len(ids) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = ids[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    rows = [[InlineKeyboardButton(short(FAQS[i]["q"]), callback_data=f"q:{i}")] for i in chunk]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"c:{cat_index}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"c:{cat_index}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="m")])

    text = f"<b>{html.escape(cat['title'])}</b>\n\nTap a question to see the answer:"
    return text, InlineKeyboardMarkup(rows)


def answer_text(faq: dict) -> str:
    return f"<b>❓ {html.escape(faq['q'])}</b>\n\n{html.escape(faq['a'])}"


def answer_keyboard(faq: dict, related: list[dict] | None = None) -> InlineKeyboardMarkup:
    rows = []
    for r in related or []:
        rows.append([InlineKeyboardButton("🔹 " + short(r["q"], 56), callback_data=f"q:{r['id']}")])
    cat_index = faq["cat"]
    page = CATEGORIES[cat_index]["ids"].index(faq["id"]) // PAGE_SIZE
    rows.append([
        InlineKeyboardButton("⬅️ Back", callback_data=f"c:{cat_index}:{page}"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="m"),
    ])
    rows.append(support_row())
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def safe_edit(query, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, reply_markup=main_menu_keyboard())


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "💬 <b>Official Support</b>\n\n"
        f"Contact: {html.escape(SUPPORT_USERNAME)}\n\n"
        "To get help faster, include:\n"
        "• Your wallet address\n"
        "• Transaction hash (if any)\n"
        "• Amount and date\n"
        "• A screenshot, if possible\n\n"
        "⚠️ Support will <b>never</b> ask for your seed phrase or private key. "
        "Beware of fake accounts that message you first."
    )
    await update.effective_message.reply_text(
        text, reply_markup=InlineKeyboardMarkup([support_row()])
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    await query.answer()

    if data == "noop":
        return
    if data == "m":
        await safe_edit(query, WELCOME_TEXT, main_menu_keyboard())
    elif data.startswith("c:"):
        _, cat_index, page = data.split(":")
        text, markup = category_view(int(cat_index), int(page))
        await safe_edit(query, text, markup)
    elif data.startswith("q:"):
        faq_id = int(data.split(":")[1])
        if 0 <= faq_id < len(FAQS):
            faq = FAQS[faq_id]
            await safe_edit(query, answer_text(faq), answer_keyboard(faq))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        return

    words = set(re.findall(r"[a-z]+", text.lower()))
    if words and words <= GREETINGS:
        await cmd_start(update, context)
        return

    results = search(text)
    if not results:
        await message.reply_text(
            "🤔 Sorry, I couldn't find an answer to that.\n\n"
            "Try different words, browse the topics below, or contact official support: "
            f"{html.escape(SUPPORT_USERNAME)}",
            reply_markup=main_menu_keyboard(),
        )
        return

    best, related = results[0], results[1:]
    reply = answer_text(best)
    if related:
        reply += "\n\n<i>Related questions:</i>"
    await message.reply_text(reply, reply_markup=answer_keyboard(best, related))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error while handling an update", exc_info=context.error)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Add it to your .env file or hosting variables.")

    defaults = Defaults(
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("faq", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("support", cmd_support))
    app.add_handler(CallbackQueryHandler(on_button))
    # Free-text search only in private chats, so the bot stays quiet in groups
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text))
    app.add_error_handler(on_error)

    log.info("Bot started with %d FAQs in %d categories", len(FAQS), len(CATEGORIES))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
