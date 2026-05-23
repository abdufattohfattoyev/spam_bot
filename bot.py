import os
import re
import logging
from telegram import Update
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

# Bitta bo'lsa ham yetarli — har biri +4 ball
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
        logger.debug("Message yo'q, o'tkazildi")
        return
    if not msg.text:
        logger.debug("Matnsiz xabar (rasm/fayl), o'tkazildi")
        return

    logger.debug("Xabar keldi | chat_id=%d | chat_type=%s", msg.chat.id, msg.chat.type)

    if msg.chat.id != GROUP_ID:
        logger.debug("Boshqa chat | kelgan=%d | kerak=%d", msg.chat.id, GROUP_ID)
        return

    user = msg.from_user
    if user.is_bot:
        logger.debug("Bot xabari, o'tkazildi")
        return

    try:
        member = await context.bot.get_chat_member(msg.chat.id, user.id)
        if member.status in ("administrator", "creator"):
            logger.debug("Admin xabari, o'tkazildi | %s", user.full_name)
            return
    except Exception as e:
        logger.warning("Admin tekshiruvi xatosi: %s", e)

    logger.debug("--- Tekshirilmoqda | %s (@%s) ---", user.full_name, user.username)
    score = spam_score(msg.text)
    logger.info("Ball=%d | %s (@%s) [%d] | %.80s", score, user.full_name, user.username, user.id, msg.text)

    if score < 3:
        logger.debug("Ball yetmadi (%d < 3)", score)
        return

    logger.info("SPAM | ball=%d | %s (@%s) [%d]", score, user.full_name, user.username, user.id)

    try:
        await msg.delete()
        logger.info("O'chirildi | %s [%d]", user.full_name, user.id)
    except Exception as e:
        logger.error("O'chira olmadi: %s", e)
        return

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🗑 <b>Xabar o'chirildi</b>\n\n"
                f"👤 {user.full_name} (@{user.username or '-'})\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📊 Ball: {score}\n\n"
                f"📝 Xabar:\n{msg.text[:500]}",
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
        f"Reklama aniqlanganda:\n"
        f"• Xabar o'chiriladi\n"
        f"• Faqat sizga bildirish keladi",
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi | Guruh: %d", GROUP_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
