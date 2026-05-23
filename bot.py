import os
import re
import logging
from telegram import Update, Message
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GROUP_ID = int(os.getenv("GROUP_ID", "0"))

STRONG_PHRASES = [
    "yetqazib berish",
    "yetkazib berish",
    "buyurtma berish",
    "buyurtma qilish",
    "mahsulot narxi",
    "to'lovni mahsulotni",
    "100k.uz",
    "olcha.uz",
]

SPAM_KEYWORDS = [
    "narxi", "mahsulot", "to'lov", "tolov",
    "qo'lingizga", "qolingizga",
    "xizmat mavjud", "xizmati mavjud", "berish xizmati",
    "krossovka", "oyoq kiyim", "ximchistka", "avtoximchistka",
    "chegirma", "aksiya", "optom", "ulgurji",
    "olish mumkin", "zakaz", "dostavka", "sotiladi", "sotamiz",
    "komplektatsiya", "asosiy xususiyatlar",
]

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PRICE_RE = re.compile(r"\d[\d\s]{2,}(?:so[ʻ''']?m|sum|uzs)", re.IGNORECASE)
PHONE_RE = re.compile(r"(\+998|998|8)[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")


def get_text(msg: Message) -> str:
    """Xabardan matnni oladi: text, caption yoki ikkalasi."""
    parts = []
    if msg.text:
        parts.append(msg.text)
    if msg.caption:
        parts.append(msg.caption)
    return " ".join(parts)


def msg_type(msg: Message) -> str:
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.document:
        return "document"
    if msg.animation:
        return "gif"
    if msg.sticker:
        return "sticker"
    if msg.text:
        return "text"
    return "other"


def spam_score(text: str) -> int:
    if not text:
        return 0

    score = 0
    lower = text.lower()

    for phrase in STRONG_PHRASES:
        if phrase in lower:
            score += 4
            logger.debug("Kuchli belgi: '%s'", phrase)

    if URL_RE.search(text):
        score += 2
        logger.debug("URL topildi")
    if PRICE_RE.search(text):
        score += 2
        logger.debug("Narx topildi")
    if PHONE_RE.search(text):
        score += 1
        logger.debug("Telefon topildi")

    kw_hits = [kw for kw in SPAM_KEYWORDS if kw in lower]
    score += len(kw_hits)
    if kw_hits:
        logger.debug("Kalit so'zlar: %s", kw_hits)

    if sum(1 for c in text if ord(c) > 0x1F300) >= 4:
        score += 1
        logger.debug("Ko'p emoji")

    if text.count("--") >= 3 or text.count("- ") >= 5:
        score += 2
        logger.debug("Narxlar ro'yxati")

    return score


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if msg.chat.id != GROUP_ID:
        return

    mtype = msg_type(msg)
    text = get_text(msg)
    is_forwarded = bool(msg.forward_date)

    logger.debug("Xabar | type=%s | forward=%s | text_len=%d",
                 mtype, is_forwarded, len(text))

    if not text:
        logger.debug("Matn yo'q (%s), o'tkazildi", mtype)
        return

    # from_user None bo'lishi mumkin (kanal yoki anonim admin)
    user = msg.from_user
    sender_chat = msg.sender_chat

    if user and user.is_bot:
        return

    # Admin tekshiruvi faqat oddiy foydalanuvchilar uchun
    if user:
        try:
            member = await context.bot.get_chat_member(msg.chat.id, user.id)
            if member.status in ("administrator", "creator"):
                logger.debug("Admin, o'tkazildi | %s", user.full_name)
                return
        except Exception as e:
            logger.warning("Admin tekshiruvi xatosi: %s", e)

    sender_name = (user.full_name if user else
                   (sender_chat.title if sender_chat else "Noma'lum"))
    sender_id = user.id if user else 0
    sender_username = user.username if user else None

    score = spam_score(text)
    logger.info("Ball=%d | type=%s | forward=%s | %s [%d] | %.80s",
                score, mtype, is_forwarded, sender_name, sender_id, text)

    if score < 3:
        return

    logger.info("SPAM | ball=%d | type=%s | %s [%d]",
                score, mtype, sender_name, sender_id)

    try:
        await msg.delete()
        logger.info("O'chirildi | %s [%d]", sender_name, sender_id)
    except Exception as e:
        logger.error("O'chira olmadi: %s", e)
        return

    if ADMIN_ID:
        try:
            forward_note = "📨 <b>Uzatilgan xabar</b>\n" if is_forwarded else ""
            type_note = {"photo": "🖼 Rasm", "video": "🎥 Video",
                         "document": "📎 Fayl", "gif": "🎞 GIF",
                         "text": "💬 Matn"}.get(mtype, mtype)
            await context.bot.send_message(
                ADMIN_ID,
                f"🗑 <b>Xabar o'chirildi</b>\n\n"
                f"{forward_note}"
                f"📌 Tur: {type_note}\n"
                f"👤 {sender_name} (@{sender_username or '-'})\n"
                f"🆔 <code>{sender_id}</code>\n"
                f"📊 Ball: {score}\n\n"
                f"📝 Matn:\n{text[:500]}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Admin xabari yuborilmadi: %s", e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"✅ <b>Spam Blocker Bot</b> ishlamoqda!\n\n"
        f"👁 Guruh ID: <code>{GROUP_ID}</code>\n\n"
        f"Qo'llab-quvvatlanadi:\n"
        f"• 💬 Matnli xabarlar\n"
        f"• 🖼 Rasm + izoh\n"
        f"• 🎥 Video + izoh\n"
        f"• 📨 Uzatilgan xabarlar",
        parse_mode="HTML",
    )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /unban &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(context.args[0])
        await context.bot.unban_chat_member(GROUP_ID, uid, only_if_banned=True)
        await update.message.reply_text(f"✅ {uid} unban qilindi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN ko'rsatilmagan!")
    if not GROUP_ID:
        raise ValueError("GROUP_ID ko'rsatilmagan!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi | Guruh: %d", GROUP_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
