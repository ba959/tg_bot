import asyncio
import random
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
router = Router()
scheduler = AsyncIOScheduler()

ADMIN_ID = config.ADMIN_ID
BANNED_WORDS = config.BANNED_WORDS

# ========== Посты ==========

def load_posts():
    try:
        with open("posts.txt", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except OSError:
        return ["Заходи на канал! 🎮"]


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def send_post(text=None):
    posts = load_posts()
    if text:
        post = text
    elif posts:
        post = random.choice(posts)
    else:
        return None
    try:
        await bot.send_message(config.CHANNEL_ID, post)
        return post
    except Exception as e:
        logging.error(f"Пост не отправлен: {e}")
        return None


# ========== Клавиатуры ==========

def admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📝 Пост в канал", callback_data="post")],
        [InlineKeyboardButton(text="⏰ Автопостинг", callback_data="auto")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close")],
    ])


# ========== Команды ==========

@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type != "private":
        return
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа. Этот бот управляется владельцем канала.")
        return
    await message.answer(
        "Привет, владелец! 👋\n"
        "Панель управления каналом:",
        reply_markup=admin_menu_kb(),
    )


# ========== Кнопки панели ==========

@router.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    try:
        chat = await bot.get_chat(config.CHANNEL_ID)
        members = await bot.get_chat_member_count(config.CHANNEL_ID)
        text = (
            f"📊 Канал: {chat.title}\n"
            f"👥 Подписчиков: {members}\n"
            f"🔗 @{chat.username}\n\n"
            f"Автопостинг каждые {config.POST_INTERVAL_HOURS} ч: {'ВКЛ' if scheduler.get_jobs() else 'ВЫКЛ'}"
        )
    except Exception as e:
        text = f"Не удалось получить статистику: {e}"
    await call.message.edit_text(text, reply_markup=admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "post")
async def cb_post(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    global _waiting_user
    _waiting_user = "post"
    await call.message.edit_text(
        "Отправь текст для поста в канал.\n"
        "Или /cancel — отмена.\n"
        "Также можно /post_now — скинуть случайный пост из posts.txt",
        reply_markup=admin_menu_kb(),
    )
    await call.answer()


_waiting_user = None


# ========== Обработка текста ==========

@router.message(F.text)
async def handle_text(message: Message):
    global _waiting_user

    # ---- Не личка: только модерация в группе/супергруппе ----
    if message.chat.type != "private":
        if message.chat.type in {"group", "supergroup"} and message.from_user.id != ADMIN_ID:
            low = message.text.lower()
            for w in BANNED_WORDS:
                if w in low:
                    try:
                        await message.delete()
                        logging.info("Сообщение удалено (модерация)")
                    except Exception as e:
                        logging.error(f"Модерация: {e}")
                    return
        return

    # ---- Личка ----
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    # Режим ожидания поста
    if _waiting_user == "post":
        _waiting_user = None
        if message.text.lower() == "/cancel":
            await message.answer("Отменено.", reply_markup=admin_menu_kb())
            return
        result = await send_post(text=message.text)
        if result:
            await message.answer("✅ Пост отправлен!", reply_markup=admin_menu_kb())
        else:
            await message.answer("❌ Ошибка отправки.", reply_markup=admin_menu_kb())
        return

    await message.answer("Используй кнопки панели ниже 👇", reply_markup=admin_menu_kb())


# ========== Автопостинг (панель) ==========

@router.callback_query(F.data == "auto")
async def cb_auto(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    jobs = scheduler.get_jobs()
    state = "ВКЛ" if jobs else "ВЫКЛ (только ручные посты)"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Выключить", callback_data="auto_off")],
        [InlineKeyboardButton(text="▶ Включить", callback_data="auto_on")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back")],
    ])
    await call.message.edit_text(
        f"⏰ Автопостинг: {state}\nИнтервал: {config.POST_INTERVAL_HOURS} ч",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "auto_on")
async def cb_auto_on(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not scheduler.get_jobs():
        scheduler.add_job(send_post, "interval", hours=config.POST_INTERVAL_HOURS,
                          next_run_time=datetime.now() + timedelta(hours=config.POST_INTERVAL_HOURS))
    await call.message.edit_text("✅ Автопостинг включён.", reply_markup=admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "auto_off")
async def cb_auto_off(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    scheduler.remove_all_jobs()
    await call.message.edit_text("⏹ Автопостинг выключен (ручные посты работают).", reply_markup=admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("Панель управления:", reply_markup=admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "close")
async def cb_close(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.delete()
    await call.answer()


# ========== Команды ручного поста ==========

@router.message(F.text == "/post_now")
async def post_now(message: Message):
    if not is_admin(message.from_user.id):
        return
    result = await send_post()
    if result:
        await message.answer("✅ Случайный пост отправлен!", reply_markup=admin_menu_kb())
    else:
        await message.answer("❌ Ошибка.", reply_markup=admin_menu_kb())


@router.message(F.text == "/cancel")
async def cancel_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    global _waiting_user
    _waiting_user = None
    await message.answer("Отменено.", reply_markup=admin_menu_kb())


# ========== Запуск ==========

async def main():
    dp.include_router(router)
    scheduler.add_job(send_post, "interval", hours=config.POST_INTERVAL_HOURS,
                      next_run_time=datetime.now() + timedelta(hours=config.POST_INTERVAL_HOURS))
    scheduler.start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
