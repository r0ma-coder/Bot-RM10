import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from database import db  # Импортируем нашу базу данных

BOT_TOKEN = "8457649746:AAFqlHpszZisrBS21VrMeJrknen6PHtNHHk"  # Замените на токен от @BotFather

# --- Инициализация ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Класс состояний FSM ---
class ParserStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_limit = State()

# --- Обработчики ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "👋 Привет! Я помогу собрать список активных участников из публичных чатов.\n\n"
        "📎 Отправь мне ссылку на публичный чат или канал в формате:\n"
        "• https://t.me/chat_username\n"
        "• @chat_username\n\n"
        "📋 Для просмотра ваших задач используй /tasks"
    )
    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove())
    await state.set_state(ParserStates.waiting_for_link)

@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    """Показывает последние задачи пользователя"""
    user_tasks = db.get_user_tasks(message.from_user.id, limit=5)
    
    if not user_tasks:
        await message.answer("📭 У вас пока нет задач.")
        return
    
    tasks_text = "📋 Ваши последние задачи:\n\n"
    
    for task in user_tasks:
        status_icons = {
            'pending': '⏳',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌'
        }
        
        icon = status_icons.get(task['status'], '📌')
        tasks_text += f"{icon} Задача #{task['id']}\n"
        tasks_text += f"📎 Ссылка: {task['chat_link'][:30]}...\n"
        tasks_text += f"🔢 Лимит: {task['limit_count']}\n"
        tasks_text += f"📊 Статус: {task['status']}\n"
        
        if task['status'] == 'completed':
            tasks_text += f"👥 Найдено: {task['users_found']}\n"
        elif task['status'] == 'failed' and task['error_message']:
            tasks_text += f"⚠️ Ошибка: {task['error_message'][:50]}...\n"
        
        tasks_text += f"🕐 Создана: {task['created_at']}\n"
        tasks_text += "─" * 30 + "\n"
    
    await message.answer(tasks_text)

@dp.message(ParserStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    user_link = message.text.strip()
    
    if not (user_link.startswith("https://t.me/") or user_link.startswith("@")):
        await message.answer("❌ Пожалуйста, отправь корректную ссылку (начинается с https://t.me/ или @).")
        return
    
    await state.update_data(chat_link=user_link)
    
    limit_text = (
        "🔢 Хочешь ли ты ограничить количество юзернеймов в результате?\n\n"
        "• Если ДА — введи число от 1 до 300.\n"
        "• Если НЕТ и хочешь получить максимум — введи 0 (тогда будет собрано до 300 юзернеймов).\n\n"
        "📝 Просто отправь цифру:"
    )
    await message.answer(limit_text)
    await state.set_state(ParserStates.waiting_for_limit)

@dp.message(ParserStates.waiting_for_limit)
async def process_limit(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    
    if not user_input.isdigit():
        await message.answer("❌ Пожалуйста, введи только цифру (0, или от 1 до 300).")
        return
    
    limit = int(user_input)
    
    if limit > 300:
        await message.answer("❌ Слишком большое ограничение. Максимум — 300. Введи число от 0 до 300:")
        return
    
    data = await state.get_data()
    chat_link = data.get("chat_link")
    
    # Определяем итоговый лимит для парсера
    final_limit = 300 if limit == 0 else limit
    limit_message = "без ограничения (максимум 300)" if limit == 0 else f"не более {final_limit}"
    
    # Сохраняем задачу в базу данных
    task_id = db.create_task(
        user_id=message.from_user.id,
        chat_link=chat_link,
        limit_count=final_limit
    )
    
    result_text = (
        f"✅ Задача #{task_id} создана!\n\n"
        f"📎 Ссылка: {chat_link}\n"
        f"🔢 Ограничение: {limit_message}\n\n"
        "⏳ Задача поставлена в очередь на парсинг.\n"
        "Я пришлю тебе файл, когда результат будет готов!\n\n"
        "📋 Используй /tasks, чтобы посмотреть статус всех задач."
    )
    
    await message.answer(result_text, reply_markup=ReplyKeyboardRemove())
    await state.clear()

# --- Запуск бота ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())