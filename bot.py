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
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GROUP_ID = int(os.getenv("GROUP_ID", "0"))

SPAM_KEYWORDS = [
    # narx / to'lov
    "narxi", "buyurtma", "mahsulot", "to'lov", "tolov",
    "qo'lingizga", "qolingizga",
    # yetkazib (ikki xil imlo)
    "yetqazib", "yetkazib",
    # xizmat
    "xizmat mavjud", "xizmati mavjud", "berish xizmati",
    "bo'ylab yetkazib", "boylab yetkazib",
    "bo'ylab yetqazib", "boylab yetqazib",
    # mahsulot turlari
    "krossovka", "oyoq kiyim", "ximchistka", "avtoximchistka",
    # savdo so'zlari
    "chegirma", "aksiya", "optom", "ulgurji",
    "olish mumkin", "zakaz", "dostavka", "sotiladi", "sotamiz",
    # komplekt / tavsif
    "komplektatsiya", "asosiy xususiyatlar",
]

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# so'm — turli tutuq belgi variantlarini qamrab oladi: ' ʻ '
PRICE_RE = re.compile(r"\d[\d\s]{2,}(?:so[ʻ''']?m|sum|uzs)", re.IGNORECASE)
PHONE_RE = re.compile(r"(\+998|998|8)[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")


def spam_score(text: str) -> int:
    if not text:
        return 0

    score = 0
    lower = text.lower()

    if URL_RE.search(text):
        score += 2
    if PRICE_RE.search(text):
        score += 2
    if PHONE_RE.search(text):
        score += 1

    score += sum(1 for kw in SPAM_KEYWORDS if kw in lower)

    if sum(1 for c in text if ord(c) > 0x1F300) >= 4:
        score += 1

    if text.count("--") >= 3 or text.count("- ") >= 5:
        score += 2

    return score


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    # Faqat belgilangan guruhda ishlaydi
    if msg.chat.id != GROUP_ID:
        return

    user = msg.from_user
    if user.is_bot:
        return

    # Guruh adminlarini tekshirish
    try:
        member = await context.bot.get_chat_member(msg.chat.id, user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception:
        pass

    score = spam_score(msg.text)
    logger.debug("Score=%d | %s [%d] | %s", score, user.full_name, user.id, msg.text[:80])
    if score < 3:
        return

    logger.info("Spam (score=%d) | %s (@%s) [%d]", score, user.full_name, user.username, user.id)

    try:
        await msg.delete()
        logger.info("Xabar o'chirildi: %s [%d]", user.full_name, user.id)
    except Exception as e:
        logger.warning("O'chira olmadi: %s", e)
        return

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🗑 <b>Xabar o'chirildi</b>\n\n"
                f"👤 {user.full_name} (@{user.username or '-'})\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📊 Spam ball: {score}\n\n"
                f"📝 Xabar:\n{msg.text[:500]}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Admin xabari yuborilmadi: %s", e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"✅ <b>Spam Blocker Bot</b> ishlamoqda!\n\n"
        f"👁 Kuzatilayotgan guruh ID: <code>{GROUP_ID}</code>\n\n"
        f"Reklama aniqlanganda:\n"
        f"• Xabar o'chiriladi\n"
        f"• Faqat sizga bildirish keladi",
        parse_mode="HTML",
    )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin foydalanuvchini unban qiladi: /unban 123456789"""
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
