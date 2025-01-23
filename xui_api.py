import requests
import json
from datetime import datetime, timedelta
import config  # Добавляем импорт config
import logging

logger = logging.getLogger(__name__)

class XUIClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        print(f"Initializing XUIClient with base_url: {base_url}")
        self.login()
    
    def login(self):
        login_url = f"{self.base_url}/login"
        print(f"Attempting to login at: {login_url}")
        data = {
            "username": self.username,
            "password": self.password
        }
        response = self.session.post(login_url, json=data)
        print(f"Login response status: {response.status_code}")
        if response.status_code != 200:
            raise Exception(f"Ошибка авторизации в 3xui: {response.text}")
    
    def create_client(self, email, uuid, duration_days):
        """Добавляет нового клиента в существующее подключение"""
        try:
            # Получаем список всех подключений
            inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
            response = self.session.get(inbounds_url)
            logger.info(f"Get inbounds response: {response.status_code}")
            
            if response.status_code != 200:
                raise Exception("Ошибка получения списка подключений")
            
            inbounds_data = response.json()
            logger.info(f"Got inbounds data: {inbounds_data}")
            
            # Ищем первое активное подключение VLESS+Reality
            target_inbound = None
            for inbound in inbounds_data.get('obj', []):
                if inbound.get('enable'):
                    try:
                        stream_settings = json.loads(inbound.get('streamSettings', '{}'))
                        if (inbound.get('protocol') == 'vless' and 
                            stream_settings.get('security') == 'reality'):
                            target_inbound = inbound
                            logger.info("Found VLESS+Reality inbound")
                            break
                    except json.JSONDecodeError:
                        continue
            
            if not target_inbound:
                raise Exception("Не найдено активное подключение VLESS+Reality")
            
            # Добавляем нового клиента
            add_client_url = f"{self.base_url}/panel/api/inbounds/addClient"
            client_data = {
                "id": target_inbound.get('id'),
                "settings": json.dumps({
                    "clients": [{
                        "id": uuid,
                        "flow": "",
                        "email": email,
                        "limitIp": 1,
                        "totalGB": 0,
                        "expiryTime": int((datetime.now() + timedelta(days=duration_days)).timestamp() * 1000),
                        "enable": True,
                        "tgId": "",
                        "subId": ""
                    }]
                })
            }
            
            logger.info(f"Adding client with data: {client_data}")
            response = self.session.post(add_client_url, json=client_data)
            logger.info(f"Add client response: {response.status_code} - {response.text}")
            
            if response.status_code != 200:
                raise Exception(f"Ошибка добавления клиента: {response.text}")
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Error in create_client: {str(e)}")
            raise Exception(f"Ошибка создания клиента: {str(e)}")
    
    def _generate_key(self):
        """Генерирует случайный ключ"""
        import random
        import string
        
        # Генерируем случайную строку из 32 символов
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(32))
    
    def delete_client(self, email):
        """Удаляет клиента из подключения"""
        # Получаем список всех подключений
        inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
        response = self.session.get(inbounds_url)
        if response.status_code != 200:
            raise Exception("Ошибка получения списка подключений")
        
        inbounds_data = response.json()
        
        # Ищем клиента во всех подключениях
        for inbound in inbounds_data.get('obj', []):
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            for client in clients:
                if client.get('email') == email:
                    # Удаляем клиента
                    delete_url = f"{self.base_url}/panel/api/inbounds/delClient"
                    data = {
                        "id": inbound['id'],
                        "clientId": client['id']
                    }
                    response = self.session.post(delete_url, json=data)
                    if response.status_code != 200:
                        raise Exception("Ошибка удаления клиента")
                    return
        
        raise Exception("Клиент не найден")
    
    def get_client_config(self, uuid, device_id):
        """Получает конфигурацию клиента в виде ссылки"""
        try:
            # Получаем данные о подключении из 3xui
            inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
            response = self.session.get(inbounds_url)
            logger.info(f"Inbounds response status: {response.status_code}")
            
            if response.status_code != 200:
                raise Exception("Ошибка получения данных о подключении")
            
            inbounds_data = response.json()
            logger.info(f"Got inbounds data: {inbounds_data}")
            
            # Ищем подключение с нужным UUID и получаем его настройки
            target_inbound = None
            target_client = None
            
            for inbound in inbounds_data.get('obj', []):
                if inbound.get('enable'):
                    try:
                        settings = json.loads(inbound.get('settings', '{}'))
                        stream_settings = json.loads(inbound.get('streamSettings', '{}'))
                        logger.info(f"Processing inbound: {inbound.get('id')}")
                        logger.info(f"Stream settings: {stream_settings}")
                        
                        # Проверяем каждого клиента в этом inbound
                        for client in settings.get('clients', []):
                            if client.get('id') == uuid:
                                target_inbound = inbound
                                target_client = client
                                logger.info(f"Found target client: {client}")
                                break
                        
                        if target_inbound:
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        continue
            
            if not target_inbound or not target_client:
                raise Exception("Подключение не найдено")
            
            # Получаем настройки Reality
            stream_settings = json.loads(target_inbound.get('streamSettings', '{}'))
            logger.info(f"Final stream settings: {stream_settings}")
            
            reality_settings = stream_settings.get('realitySettings', {})
            logger.info(f"Reality settings: {reality_settings}")
            
            # Получаем публичный ключ
            public_key = reality_settings.get('publicKey', '')
            logger.info(f"Public key: {public_key}")
            
            if not public_key:
                # Если ключ не найден в realitySettings, поищем в других местах
                public_key = stream_settings.get('publicKey', '')  # Попробуем найти в корне stream_settings
                if not public_key:
                    # Если всё еще нет ключа, используем хардкод (временное решение)
                    public_key = "w67LG56j-uwIwhiWExuqFVrzdWBFP3T_Q5zZrK_K7Rc"
                    logger.warning(f"Using hardcoded public key: {public_key}")
            
            # Получаем адрес сервера из base_url
            server_address = self.base_url.split('://')[1].split('/')[0].split(':')[0]
            
            # Формируем ссылку в формате vless точно как в 3xui
            vless_link = (
                f"vless://{uuid}@{server_address}:443"
                f"?type=tcp"
                f"&security=reality"
                f"&pbk={public_key}"
                f"&fp=chrome"
                f"&sni=google.com"
                f"&sid={reality_settings.get('shortIds', ['b14ce4e7b960'])[0]}"
                f"&spx=%2F"
                f"#VPN-DUNE-{device_id}"
            )
            
            logger.info(f"Generated VLESS link for device {device_id}: {vless_link}")
            return vless_link
            
        except Exception as e:
            logger.error(f"Error in get_client_config: {str(e)}")
            raise Exception(f"Ошибка получения конфигурации: {str(e)}")
    
    def check_client_exists(self, uuid):
        """Проверяет существование клиента в 3xui"""
        try:
            # Получаем список всех подключений
            inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
            response = self.session.get(inbounds_url)
            
            if response.status_code != 200:
                return False
            
            inbounds_data = response.json()
            
            # Ищем клиента во всех подключениях
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('id') == uuid:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking client existence: {str(e)}")
            return False 