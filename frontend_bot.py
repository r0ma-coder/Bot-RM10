import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from database import db

# --- Настройки ---
BOT_TOKEN = "8457649746:AAFqlHpszZisrBS21VrMeJrknen6PHtNHHk"  # Замените на токен от @BotFather

# --- Инициализация ---
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# --- Класс состояний FSM ---
class ParserStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_limit = State()

# [Остальные обработчики остаются без изменений: cmd_start, cmd_cancel, cmd_help, process_link, process_limit]

# --- Команда /tasks с кнопками ---
@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    """Показывает последние задачи пользователя с кнопками управления"""
    user_tasks = db.get_user_tasks(message.from_user.id, limit=10)
    
    if not user_tasks:
        await message.answer("📭 <b>У вас пока нет задач.</b>\n\nИспользуйте /start чтобы создать первую задачу.")
        return
    
    tasks_text = "<b>📋 Ваши последние задачи:</b>\n\n"
    
    for task in user_tasks:
        status_icons = {'pending': '⏳', 'processing': '🔄', 'completed': '✅', 'failed': '❌'}
        icon = status_icons.get(task['status'], '📌')
        created_time = task['created_at'][:19] if task['created_at'] else 'N/A'
        
        tasks_text += f"{icon} <b>Задача #{task['id']}</b>\n"
        tasks_text += f"<code>{task['chat_link'][:30]}</code>\n"
        tasks_text += f"Лимит: <b>{task['limit_count']}</b>\n"
        tasks_text += f"Статус: <b>{task['status']}</b>\n"
        
        if task['status'] == 'completed' and task['users_found'] > 0:
            tasks_text += f"Найдено: <b>{task['users_found']}</b> пользователей\n"
        elif task['status'] == 'failed' and task['error_message']:
            tasks_text += f"Ошибка: <i>{task['error_message'][:50]}</i>\n"
        
        tasks_text += f"Создана: <i>{created_time}</i>\n"
        tasks_text += "─" * 30 + "\n"
    
    tasks_text += f"\n<b>Всего задач:</b> {len(user_tasks)}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Отменить задачу", callback_data="cancel_task_menu")]
    ])
    
    await message.answer(tasks_text, reply_markup=keyboard)

# --- Обработчики инлайн-кнопок ---
@dp.callback_query(F.data == "cancel_task_menu")
async def cancel_task_menu(callback: types.CallbackQuery):
    """Показывает меню выбора задачи для отмены"""
    user_tasks = db.get_user_tasks(callback.from_user.id, limit=10)
    cancellable_tasks = [t for t in user_tasks if t['status'] in ['pending', 'processing']]
    
    if not cancellable_tasks:
        await callback.answer("Нет задач, которые можно отменить", show_alert=True)
        return
    
    keyboard_buttons = []
    for task in cancellable_tasks[:10]:
        status_icon = '⏳' if task['status'] == 'pending' else '🔄'
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} Задача #{task['id']}",
                callback_data=f"cancel_task_{task['id']}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_tasks")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        "🗑️ <b>Выберите задачу для отмены:</b>\n\n"
        "• ⏳ - Ожидает обработки\n"
        "• 🔄 - В процессе обработки\n\n"
        "<i>Отменить можно только задачи в статусе 'ожидает' или 'в процессе'.</i>",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("cancel_task_"))
async def cancel_task_confirm(callback: types.CallbackQuery):
    """Подтверждение отмены задачи"""
    task_id = callback.data.split("_")[-1]
    
    if not task_id.isdigit():
        await callback.answer("Неверный ID задачи", show_alert=True)
        return
    
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, status, chat_link FROM parsing_tasks WHERE id = ? AND user_id = ?",
        (task_id, callback.from_user.id)
    )
    task = cursor.fetchone()
    conn.close()
    
    if not task:
        await callback.answer("Задача не найдена или у вас нет доступа", show_alert=True)
        return
    
    task_id, status, chat_link = task
    
    if status not in ['pending', 'processing']:
        await callback.answer(f"Невозможно отменить задачу в статусе '{status}'", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"confirm_cancel_{task_id}"),
            InlineKeyboardButton(text="❌ Нет, вернуться", callback_data="back_to_tasks")
        ]
    ])
    
    await callback.message.edit_text(
        f"⚠️ <b>Вы уверены, что хотите отменить задачу #{task_id}?</b>\n\n"
        f"📎 Ссылка: <code>{chat_link[:30]}...</code>\n"
        f"📊 Статус: <b>{status}</b>\n\n"
        "<i>Это действие нельзя будет отменить.</i>",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_cancel_"))
async def cancel_task_execute(callback: types.CallbackQuery):
    """Выполняет отмену задачи"""
    task_id = callback.data.split("_")[-1]
    
    if not task_id.isdigit():
        await callback.answer("Неверный ID задачи", show_alert=True)
        return
    
    # Используем метод из database.py
    success = db.delete_task(task_id, callback.from_user.id)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Задача #{task_id} успешно отменена!</b>\n\n"
            f"Время отмены: <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>\n\n"
            "Используйте /tasks для просмотра обновленного списка задач."
        )
        logging.info(f"User {callback.from_user.id} отменил задачу #{task_id}")
        await callback.answer(f"Задача #{task_id} отменена")
    else:
        await callback.answer("Ошибка при отмене задачи", show_alert=True)

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: types.CallbackQuery):
    """Возвращает к списку задач"""
    user_tasks = db.get_user_tasks(callback.from_user.id, limit=10)
    
    if not user_tasks:
        await callback.message.edit_text("📭 <b>У вас пока нет задач.</b>\n\nИспользуйте /start чтобы создать первую задачу.")
        await callback.answer()
        return
    
    tasks_text = "<b>📋 Ваши последние задачи:</b>\n\n"
    
    for task in user_tasks:
        status_icons = {'pending': '⏳', 'processing': '🔄', 'completed': '✅', 'failed': '❌'}
        icon = status_icons.get(task['status'], '📌')
        created_time = task['created_at'][:19] if task['created_at'] else 'N/A'
        
        tasks_text += f"{icon} <b>Задача #{task['id']}</b>\n"
        tasks_text += f"<code>{task['chat_link'][:30]}</code>\n"
        tasks_text += f"Лимит: <b>{task['limit_count']}</b>\n"
        tasks_text += f"Статус: <b>{task['status']}</b>\n"
        
        if task['status'] == 'completed' and task['users_found'] > 0:
            tasks_text += f"Найдено: <b>{task['users_found']}</b> пользователей\n"
        elif task['status'] == 'failed' and task['error_message']:
            tasks_text += f"Ошибка: <i>{task['error_message'][:50]}</i>\n"
        
        tasks_text += f"Создана: <i>{created_time}</i>\n"
        tasks_text += "─" * 30 + "\n"
    
    tasks_text += f"\n<b>Всего задач:</b> {len(user_tasks)}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Отменить задачу", callback_data="cancel_task_menu")]
    ])
    
    await callback.message.edit_text(tasks_text, reply_markup=keyboard)
    await callback.answer()

# --- Остальной код остается без изменений ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())