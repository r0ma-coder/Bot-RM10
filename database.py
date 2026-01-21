# database.py
import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskDatabase:
    def __init__(self, db_name="tasks.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и таблиц"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица для задач
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parsing_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_link TEXT NOT NULL,
                limit_count INTEGER DEFAULT 300,
                status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL,
                result_filename TEXT NULL,
                users_found INTEGER DEFAULT 0,
                error_message TEXT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"База данных {self.db_name} инициализирована")
    
    def create_task(self, user_id, chat_link, limit_count):
        """Создание новой задачи"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO parsing_tasks (user_id, chat_link, limit_count, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, chat_link, limit_count))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Создана задача #{task_id} для user_id {user_id}")
        return task_id
    
    def get_pending_task(self):
        """Получение следующей задачи для обработки"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, user_id, chat_link, limit_count 
            FROM parsing_tasks 
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT 1
        ''')
        
        task = cursor.fetchone()
        conn.close()
        
        if task:
            logger.info(f"Найдена задача #{task[0]} для обработки")
            return {
                'id': task[0],
                'user_id': task[1],
                'chat_link': task[2],
                'limit_count': task[3]
            }
        return None
    
    def update_task_status(self, task_id, status, result_filename=None, users_found=0, error_message=None):
        """Обновление статуса задачи"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        if status == 'completed':
            cursor.execute('''
                UPDATE parsing_tasks 
                SET status = ?, 
                    completed_at = CURRENT_TIMESTAMP,
                    result_filename = ?,
                    users_found = ?
                WHERE id = ?
            ''', (status, result_filename, users_found, task_id))
        elif status == 'failed':
            cursor.execute('''
                UPDATE parsing_tasks 
                SET status = ?, 
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
            ''', (status, error_message, task_id))
        else:
            cursor.execute('''
                UPDATE parsing_tasks 
                SET status = ?
                WHERE id = ?
            ''', (status, task_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Задача #{task_id} обновлена: статус={status}")
    
    def get_user_tasks(self, user_id, limit=5):
        """Получение задач пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, chat_link, limit_count, status, 
                   created_at, completed_at, users_found, error_message
            FROM parsing_tasks 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'id': row[0],
                'chat_link': row[1],
                'limit_count': row[2],
                'status': row[3],
                'created_at': row[4],
                'completed_at': row[5],
                'users_found': row[6],
                'error_message': row[7]
            })
        
        conn.close()
        return tasks

# Глобальный экземпляр базы данных
db = TaskDatabase()