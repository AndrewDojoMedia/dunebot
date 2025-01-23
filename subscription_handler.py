from datetime import datetime, timedelta
import sqlite3
import uuid
from xui_api import XUIClient
import config
import threading
import logging
import os

logger = logging.getLogger(__name__)

class SubscriptionHandler:
    def __init__(self):
        self.db_lock = threading.Lock()
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subscriptions.db')
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.xui_client = XUIClient(
            config.XUI_BASE_URL,
            config.XUI_USERNAME,
            config.XUI_PASSWORD
        )
        self.create_tables()
    
    def create_tables(self):
        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER,
                start_date TEXT,
                end_date TEXT,
                price REAL,
                status TEXT,
                device_id TEXT,
                xui_email TEXT,
                xui_uuid TEXT
            )
            ''')
            self.conn.commit()
    
    def create_payment(self, duration, price):
        # Здесь будет интеграция с платежной системой
        # Пока возвращаем тестовую ссылку
        return "https://test-payment.com"
    
    def get_next_user_number(self):
        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT device_id FROM subscriptions 
            WHERE device_id LIKE 'user%' 
            ORDER BY CAST(SUBSTR(device_id, 5) AS INTEGER) DESC 
            LIMIT 1
            ''')
            result = cursor.fetchone()
            
            if result:
                last_number = int(result[0][4:])  # Извлекаем число после 'user'
                next_number = last_number + 1
            else:
                next_number = 1
                
            return f"user{next_number:07d}"  # Форматируем как user0000001
    
    def add_subscription(self, user_id, duration, device_id=None):
        with self.db_lock:
            try:
                start_date = datetime.now()
                end_date = start_date + timedelta(days=duration * 30)
                
                # Генерируем новый device_id в формате user0000001
                if not device_id:
                    device_id = self.get_next_user_number()
                
                # Создаем клиента в 3xui
                client_uuid = str(uuid.uuid4())
                email = device_id  # Используем новый формат как email
                
                try:
                    # Создаем пользователя в 3xui
                    xui_response = self.xui_client.create_client(
                        email=email,
                        uuid=client_uuid,
                        duration_days=duration * 30
                    )
                    
                    # Сохраняем информацию в базу данных
                    cursor = self.conn.cursor()
                    cursor.execute('''
                    INSERT INTO subscriptions (
                        user_id, start_date, end_date, status, 
                        device_id, xui_email, xui_uuid
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        user_id, start_date.isoformat(), end_date.isoformat(),
                        'active', device_id, email, client_uuid
                    ))
                    self.conn.commit()
                    
                    logger.info(f"Added subscription: user_id={user_id}, device_id={device_id}, uuid={client_uuid}")
                    
                    return {
                        'success': True,
                        'uuid': client_uuid
                    }
                    
                except Exception as e:
                    logger.error(f"Error in add_subscription: {str(e)}")
                    return {
                        'success': False,
                        'error': str(e)
                    }
            except Exception as e:
                logger.error(f"Database error in add_subscription: {str(e)}")
                if self.conn:
                    self.conn.rollback()
                return {
                    'success': False,
                    'error': str(e)
                }
    
    def get_user_subscriptions(self, user_id):
        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM subscriptions WHERE user_id = ? AND status = "active"', (user_id,))
            subscriptions = cursor.fetchall()
            
            active_subscriptions = []
            for sub in subscriptions:
                uuid = sub[7]  # UUID в 8-м столбце
                if self.xui_client.check_client_exists(uuid):
                    active_subscriptions.append(sub)
                else:
                    # Если конфиг не найден в 3xui, деактивируем его в базе
                    cursor.execute('''
                    UPDATE subscriptions 
                    SET status = 'inactive' 
                    WHERE user_id = ? AND xui_uuid = ?
                    ''', (user_id, uuid))
                    logger.info(f"Deactivated subscription with UUID {uuid} as it no longer exists in 3xui")
            
            self.conn.commit()
            logger.info(f"Got {len(active_subscriptions)} active subscriptions for user {user_id}")
            return active_subscriptions
    
    def deactivate_subscription(self, user_id, device_id):
        with self.db_lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''
                SELECT xui_email FROM subscriptions 
                WHERE user_id = ? AND device_id = ? AND status = 'active'
                ''', (user_id, device_id))
                
                result = cursor.fetchone()
                if result:
                    email = result[0]
                    try:
                        # Удаляем пользователя из 3xui
                        self.xui_client.delete_client(email)
                        
                        # Обновляем статус в базе данных
                        cursor.execute('''
                        UPDATE subscriptions 
                        SET status = 'inactive' 
                        WHERE user_id = ? AND device_id = ? AND status = 'active'
                        ''', (user_id, device_id))
                        self.conn.commit()
                        return True
                    except Exception:
                        self.conn.rollback()
                        return False
                return False
            except Exception:
                if self.conn:
                    self.conn.rollback()
                return False 