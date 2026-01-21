import asyncio
import logging
import time
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.errors import SessionPasswordNeededError
from database import db  # Импортируем нашу базу данных

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parser.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация (замените на свои данные!)
API_ID = 37780238 # Ваш api_id с my.telegram.org
API_HASH = 'fbfe8a419fea2f1ee79b9cc32bc49e18' # Ваш api_hash
PHONE_NUMBER = '+959760950133'  # Номер аккаунта для парсера

class ParserWorker:
    def __init__(self):
        self.client = None
        self.is_running = True
    
    async def initialize_client(self):
        """Инициализация клиента Telegram"""
        if self.client and self.client.is_connected():
            return True
        
        try:
            self.client = TelegramClient('parser_session', API_ID, API_HASH)
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.info("Сессия не авторизована. Запрашиваю код...")
                await self.client.send_code_request(PHONE_NUMBER)
                code = input("Введите код из Telegram: ")
                
                try:
                    await self.client.sign_in(PHONE_NUMBER, code)
                except SessionPasswordNeededError:
                    password = input("Требуется пароль двухфакторной аутентификации: ")
                    await self.client.sign_in(password=password)
            
            logger.info("✅ Клиент Telegram инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации клиента: {e}")
            return False
    
    async def process_task(self, task):
        """Обработка одной задачи"""
        task_id = task['id']
        chat_link = task['chat_link']
        max_users = task['limit_count']
        
        logger.info(f"🔄 Начинаю обработку задачи #{task_id}: {chat_link}")
        
        try:
            # Получаем сущность чата
            chat = await self.client.get_entity(chat_link)
            chat_title = chat.title if hasattr(chat, 'title') else chat.username
            
            active_users = []
            all_participants = await self.client.get_participants(chat)
            logger.info(f"👥 Всего участников в '{chat_title}': {len(all_participants)}")
            
            # Фильтруем пользователей по активности
            for i, user in enumerate(all_participants):
                if len(active_users) >= max_users:
                    logger.info(f"✅ Достигнут лимит в {max_users} пользователей")
                    break
                
                if not user.username:
                    continue
                
                try:
                    # Проверяем активность пользователя
                    history = await self.client(GetHistoryRequest(
                        peer=chat,
                        limit=50,
                        offset_id=0,
                        offset_date=None,
                        add_offset=0,
                        max_id=0,
                        min_id=0,
                        hash=0
                    ))
                    
                    user_msg_count = sum(1 for msg in history.messages 
                                       if hasattr(msg, 'from_id') and msg.from_id == user.id)
                    
                    if user_msg_count >= 2:
                        user_info = {
                            'id': user.id,
                            'username': user.username,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'messages_count': user_msg_count
                        }
                        active_users.append(user_info)
                        
                        if len(active_users) % 10 == 0:
                            logger.info(f"📊 Найдено активных: {len(active_users)}/{max_users}")
                    
                    # Пауза для избежания блокировки
                    if i % 10 == 0:
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при обработке пользователя {user.id}: {e}")
                    continue
            
            # Сохраняем результаты в файл
            filename = await self.save_results(active_users, chat_title)
            
            logger.info(f"✅ Задача #{task_id} завершена. Найдено: {len(active_users)}")
            
            return {
                'success': True,
                'filename': filename,
                'users_found': len(active_users),
                'chat_title': chat_title
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке задачи #{task_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def save_results(self, users, chat_title):
        """Сохраняет результаты в файл"""
        if not users:
            return None
        
        safe_title = "".join(c for c in chat_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        timestamp = int(time.time())
        filename = f"results/{safe_title}_{timestamp}.txt"
        
        # Создаем папку results, если её нет
        import os
        os.makedirs("results", exist_ok=True)
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Активные пользователи из '{chat_title}'\n")
                f.write(f"Всего найдено: {len(users)}\n")
                f.write("=" * 50 + "\n\n")
                
                for user in users:
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    f.write(f"@{user['username']} - {full_name} (сообщений: {user['messages_count']})\n")
            
            logger.info(f"💾 Результаты сохранены в {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения файла: {e}")
            return None
    
    async def worker_loop(self):
        """Основной цикл работника"""
        logger.info("🚀 Парсер запущен и ожидает задачи...")
        
        while self.is_running:
            try:
                # Получаем следующую задачу из базы
                task = db.get_pending_task()
                
                if task:
                    # Обновляем статус задачи на "обрабатывается"
                    db.update_task_status(task['id'], 'processing')
                    
                    # Обрабатываем задачу
                    result = await self.process_task(task)
                    
                    # Обновляем статус задачи в зависимости от результата
                    if result['success']:
                        db.update_task_status(
                            task['id'], 
                            'completed',
                            result_filename=result['filename'],
                            users_found=result['users_found']
                        )
                    else:
                        db.update_task_status(
                            task['id'], 
                            'failed',
                            error_message=result.get('error', 'Unknown error')
                        )
                else:
                    # Нет задач - ждём 10 секунд
                    await asyncio.sleep(10)
                    
            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал прерывания")
                self.is_running = False
                
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                await asyncio.sleep(30)
    
    async def start(self):
        """Запуск работника"""
        # Инициализируем клиент
        if not await self.initialize_client():
            logger.error("❌ Не удалось инициализировать клиент Telegram")
            return
        
        # Запускаем основной цикл
        await self.worker_loop()
        
        # Закрываем соединение при завершении
        if self.client:
            await self.client.disconnect()

# --- Запуск парсера ---
async def main():
    worker = ParserWorker()
    await worker.start()

if __name__ == "__main__":
    asyncio.run(main())