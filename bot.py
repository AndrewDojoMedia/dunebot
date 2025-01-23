import telebot
from telebot import types
from datetime import datetime, timedelta
import config
from subscription_handler import SubscriptionHandler
import uuid
import logging
import os

# Определяем базовый путь
BASE_DIR = '/var/botvpn'

# Пути к файлам
LOG_FILE = os.path.join(BASE_DIR, 'bot.log')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Настройка логирования
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(config.BOT_TOKEN)
sub_handler = SubscriptionHandler()

@bot.message_handler(commands=['start'])
def start(message):
    try:
        subscriptions = sub_handler.get_user_subscriptions(message.from_user.id)
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        # Обновленный текст с тарифами
        welcome_text = (
            "🌍 VPN DUNE 🌍\n\n"
            "💡 Для покупки подписки нажмите '💎 Купить подписку'\n"
            "👉 Для просмотра ваших подписок нажмите '🌟 Мой VPN'\n\n"
            "📝 Доступные тарифы:\n"
            "• 1 месяц - 299₽\n"
            "• 3 месяца - 852₽ (✨ скидка 5%)\n"
            "• 6 месяцев - 1615₽ (🌟 скидка 10%)\n"
            "• 12 месяцев - 3052₽ (💫 скидка 15%)"
        )
        
        if subscriptions:
            # Если есть активные подписки
            buttons = [
                "🌟 Мой VPN",
                "🔗 Ссылка на подписку",
                "💡 Помощь"
            ]
        else:
            # Если подписок нет
            buttons = [
                "💎 Купить подписку",
                "🌟 Мой VPN",
                "🔗 Ссылка на подписку",
                "💡 Помощь"
            ]
        
        # Создаем ряды кнопок по 2 в каждом
        for i in range(0, len(buttons), 2):
            row_buttons = buttons[i:i+2]
            markup.row(*row_buttons)
        
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in start: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка. Попробуйте позже."
        )

@bot.message_handler(func=lambda message: message.text == "💎 Купить подписку")
def subscription_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=1)  # Ставим кнопки в столбик
    buttons = [
        types.InlineKeyboardButton(
            "1 месяц - 299₽", 
            callback_data="sub_1_299"
        ),
        types.InlineKeyboardButton(
            "3 месяца - 852₽\n✨ Скидка 5%", 
            callback_data="sub_3_852"
        ),
        types.InlineKeyboardButton(
            "6 месяцев - 1615₽\n🌟 Скидка 10%", 
            callback_data="sub_6_1615"
        ),
        types.InlineKeyboardButton(
            "12 месяцев - 3052₽\n💫 Скидка 15%", 
            callback_data="sub_12_3052"
        )
    ]
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id,
        "✨ <b>Выберите длительность подписки:</b>\n\n"
        "• 🚀 Безлимитный трафик\n"
        "• ⚡️ Высокая скорость\n"
        "• 💫 Поддержка 24/7",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def handle_subscription(call):
    try:
        # Проверяем формат данных
        parts = call.data.split('_')
        if len(parts) == 4:  # Для продления существующей подписки
            _, duration, price, device_id = parts
        else:  # Для новой подписки
            _, duration, price = parts
            device_id = str(uuid.uuid4())[:8]
        
        user_id = call.from_user.id
        
        # Создаем платеж
        payment_url = sub_handler.create_payment(int(duration), int(price))
        
        # Пока у нас нет платежной системы, просто создаем/продлеваем подписку
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "Тестовая оплата", 
            callback_data=f"pay_{duration}_{device_id}"
        ))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Подписка на {duration} мес.\n"
                 f"Стоимость: {price}₽\n\n"
                 f"Для тестовой оплаты нажмите кнопку ниже:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_subscription: {e}")
        bot.answer_callback_query(
            call.id,
            text="Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Добавляем обработчик "оплаты"
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def handle_payment(call):
    duration, device_id = call.data.split('_')[1:]
    user_id = call.from_user.id
    
    try:
        result = sub_handler.add_subscription(user_id, int(duration), device_id)
        
        if result['success']:
            config_link = sub_handler.xui_client.get_client_config(result['uuid'], device_id)
            
            # Отправляем основное сообщение
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Подписка успешно активирована!\n"
                     f"Длительность: {duration} мес.\n"
                     f"ID устройства: {device_id}\n\n"
                     f"🔗 Ваша ссылка для подключения:\n\n"
                     f"{config_link}\n\n"
                     f"Скопируйте ссылку ниже и импортируйте в приложение.\n"
                     f"Инструкция по настройке: /help_setup"
            )
            
            # Отправляем ссылку отдельным сообщением без форматирования
            bot.send_message(
                chat_id=call.message.chat.id,
                text=config_link,  # Отправляем без форматирования
                disable_web_page_preview=True  # Отключаем предпросмотр ссылки
            )
        else:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Ошибка при создании подписки: {result.get('error', 'Неизвестная ошибка')}"
            )
    except Exception as e:
        logger.error(f"Error in handle_payment: {str(e)}")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"❌ Произошла ошибка: {str(e)}"
        )

# Добавим инструкцию по настройке
@bot.message_handler(commands=['help_setup'])
def help_setup(message):
    setup_text = (
        "📱 Инструкция по настройке:\n\n"
        "1. Скачайте приложение v2rayNG из Google Play\n"
        "2. Откройте приложение\n"
        "3. Нажмите на значок (+) в правом верхнем углу\n"
        "4. Выберите 'Import config from clipboard'\n"
        "5. Вставьте скопированную ссылку\n"
        "6. Нажмите на созданный профиль для подключения\n\n"
        "🔗 Ссылка на приложение v2rayNG:\n"
        "https://play.google.com/store/apps/details?id=com.v2ray.ang"
    )
    bot.send_message(message.chat.id, setup_text)

@bot.message_handler(func=lambda message: message.text == "💡 Помощь")
def help_handler(message):
    try:
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton("🍎 iOS / iPadOS / MacOS", callback_data="help_ios"),
            types.InlineKeyboardButton("📱 Android", callback_data="help_android"),
            types.InlineKeyboardButton("📱 Huawei / Honor", callback_data="help_huawei"),
            types.InlineKeyboardButton("💻 Windows", callback_data="help_windows"),
            types.InlineKeyboardButton("📺 Android TV", callback_data="help_androidtv"),
            types.InlineKeyboardButton("🔄 Обновление подписки", callback_data="help_update")
        ]
        markup.add(*buttons)
        
        # Убираем фразу про поддержку
        bot.send_message(
            message.chat.id,
            "💡 <b>Выберите вашу платформу для получения инструкции:</b>",
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in help_handler: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка. Попробуйте позже."
        )

@bot.message_handler(func=lambda message: message.text == "🌟 Мой VPN")
def my_vpn(message):
    try:
        subscriptions = sub_handler.get_user_subscriptions(message.from_user.id)
        
        if not subscriptions:
            bot.send_message(message.chat.id, 
                "❌ У вас нет активных подписок.\n"
                "Для покупки нажмите '💎 Купить подписку'")
            return
        
        for sub in subscriptions:
            start_date = datetime.fromisoformat(sub[1])
            end_date = datetime.fromisoformat(sub[2])
            device_id = sub[5]
            uuid = sub[7]
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            buttons = [
                types.InlineKeyboardButton(
                    "⭐️ ПРОДЛИТЬ ТАРИФ", 
                    callback_data=f"extend_{device_id}"
                ),
                types.InlineKeyboardButton(
                    "➕ ДОБАВИТЬ УСТРОЙСТВО", 
                    callback_data=f"more_devices_{device_id}"
                ),
                types.InlineKeyboardButton(
                    "🎯 ПОДАРИТЬ ПОДПИСКУ", 
                    callback_data=f"gift_{device_id}"
                ),
                types.InlineKeyboardButton(
                    "🔄 НАСТРОИТЬ АВТОПРОДЛЕНИЕ", 
                    callback_data=f"autopay_{device_id}"
                )
            ]
            markup.add(*buttons)
            
            # Отправляем основную информацию о подписке без фразы про поддержку
            message_text = (
                f"🌟 <b>Информация о подписке</b>\n\n"
                f"📱 ID устройства: {device_id}\n"
                f"📅 Дата активации: {start_date.strftime('%d.%m.%Y')}\n"
                f"📅 Действует до: {end_date.strftime('%d.%m.%Y')}\n"
                f"⏳ Осталось: {(end_date - datetime.now()).days} дней\n"
            )
            
            bot.send_message(
                message.chat.id,
                message_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Error in my_vpn: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка. Попробуйте позже."
        )

# Добавляем обработчик для новой кнопки
@bot.message_handler(func=lambda message: message.text == "🔄 Тест")
def test_handler(message):
    try:
        bot.reply_to(message, "🔄 Тестовая функция")
    except Exception as e:
        logger.error(f"Error in test_handler: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка. Попробуйте позже."
        )

# Добавляем обработчик для новой кнопки
@bot.message_handler(func=lambda message: message.text == "🔗 Ссылка на подписку")
def get_subscription_link(message):
    try:
        subscriptions = sub_handler.get_user_subscriptions(message.from_user.id)
        
        if not subscriptions:
            bot.send_message(message.chat.id, 
                "❌ У вас нет активных подписок.\n"
                "Для покупки нажмите '💎 Купить подписку'")
            return
        
        # Для каждой активной подписки показываем ссылку и меню
        for sub in subscriptions:
            device_id = sub[5]
            uuid = sub[7]
            end_date = datetime.fromisoformat(sub[2])
            
            try:
                config_link = sub_handler.xui_client.get_client_config(uuid, device_id)
                
                # Отправляем сообщение с конфигурацией
                bot.send_message(
                    message.chat.id,
                    f"🔗 <b>Ваша VPN-конфигурация</b>\n\n"
                    f"📱 ID устройства: {device_id}\n"
                    f"📅 Активна до: {end_date.strftime('%d.%m.%y %H:%M')}\n"
                    f"🌍 Регион: 🇫🇮 Хельсинки\n\n"
                    f"<code>{config_link}</code>\n\n"
                    f"Просто <b>обновить</b> средствами приложения\n\n"
                    f"👇 Инструкции по установке 👇",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
                # Создаем клавиатуру с кнопками для разных платформ
                markup = types.InlineKeyboardMarkup(row_width=1)
                buttons = [
                    types.InlineKeyboardButton(
                        "🍎 iOS / iPadOS / MacOS", 
                        callback_data=f"setup_ios_{device_id}_{uuid}"
                    ),
                    types.InlineKeyboardButton(
                        "📱 Android", 
                        callback_data=f"setup_android_{device_id}_{uuid}"
                    ),
                    types.InlineKeyboardButton(
                        "📱 Huawei / Honor", 
                        callback_data=f"setup_huawei_{device_id}_{uuid}"
                    ),
                    types.InlineKeyboardButton(
                        "💻 Windows", 
                        callback_data=f"setup_windows_{device_id}_{uuid}"
                    ),
                    types.InlineKeyboardButton(
                        "📺 Android TV", 
                        callback_data=f"setup_androidtv_{device_id}_{uuid}"
                    ),
                    types.InlineKeyboardButton(
                        "🔄 Обновление подписки", 
                        callback_data=f"refresh_link_{device_id}_{uuid}"
                    )
                ]
                markup.add(*buttons)
                
                # Отправляем меню с кнопками
                bot.send_message(
                    message.chat.id,
                    "Выберите вашу платформу для получения инструкции:",
                    reply_markup=markup
                )
                
            except Exception as e:
                logger.error(f"Error getting config link: {e}")
                bot.send_message(
                    message.chat.id,
                    f"❌ Ошибка получения ссылки для устройства {device_id}.\n"
                    f"Попробуйте позже или обратитесь в поддержку."
                )
                
    except Exception as e:
        logger.error(f"Error in get_subscription_link: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка при получении данных. Попробуйте позже."
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith(('help_', 'setup_')))
def handle_help_callback(call):
    try:
        action, platform = call.data.split('_')[:2]
        logger.info(f"Help callback triggered. Action: {action}, Platform: {platform}")
        
        if call.data == "help_back":
            return handle_back_button(call)
            
        instructions = {
            'ios': (
                "🍎 <b>iOS / iPadOS / MacOS</b>\n\n"
                "1. Установите приложение Streisand из App Store\n"
                "2. Откройте приложение\n"
                "3. Нажмите (+) внизу экрана\n"
                "4. Выберите \"Import from Clipboard\"\n"
                "5. Вставьте скопированную ссылку\n"
                "6. Включите VPN\n\n"
                "📱 <b>Ссылка на приложение:</b>\n"
                "https://apps.apple.com/app/streisand/id6450534064"
            ),
            'android': (
                "📱 <b>Android</b>\n\n"
                "1. Установите приложение v2rayNG из Google Play\n"
                "2. Откройте приложение\n"
                "3. Нажмите (+) в правом верхнем углу\n"
                "4. Выберите \"Import config from clipboard\"\n"
                "5. Вставьте скопированную ссылку\n"
                "6. Включите VPN\n\n"
                "📱 <b>Ссылка на приложение:</b>\n"
                "https://play.google.com/store/apps/details?id=com.v2ray.ang"
            ),
            'huawei': (
                "📱 <b>Huawei / Honor</b>\n\n"
                "1. Установите приложение v2rayNG из AppGallery\n"
                "2. Откройте приложение\n"
                "3. Нажмите (+) в правом верхнем углу\n"
                "4. Выберите \"Import config from clipboard\"\n"
                "5. Вставьте скопированную ссылку\n"
                "6. Включите VPN\n\n"
                "📱 <b>Ссылка на приложение:</b>\n"
                "https://appgallery.huawei.com/app/C102481599"
            ),
            'windows': (
                "💻 <b>Windows</b>\n\n"
                "1. Скачайте приложение v2rayN\n"
                "2. Распакуйте и запустите программу\n"
                "3. Нажмите правой кнопкой на значок в трее\n"
                "4. Выберите \"Import from clipboard\"\n"
                "5. Вставьте скопированную ссылку\n"
                "6. Включите VPN\n\n"
                "💻 <b>Ссылка на программу:</b>\n"
                "https://github.com/2dust/v2rayN/releases"
            ),
            'androidtv': (
                "📺 <b>Android TV</b>\n\n"
                "1. Установите приложение v2rayNG\n"
                "2. Откройте приложение\n"
                "3. Нажмите (+) на пульте\n"
                "4. Выберите \"Import config from clipboard\"\n"
                "5. Вставьте скопированную ссылку\n"
                "6. Включите VPN\n\n"
                "📺 <b>Ссылка на приложение:</b>\n"
                "https://play.google.com/store/apps/details?id=com.v2ray.ang"
            )
        }

        if platform == 'android':
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="help_back"))
            
            video_path = '/var/botvpn/android_guide.mp4'
            if os.path.exists(video_path):
                try:
                    logger.info("Sending Android video guide...")
                    with open(video_path, 'rb') as video:
                        # Удаляем старое сообщение перед отправкой видео
                        try:
                            bot.delete_message(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id
                            )
                        except:
                            pass
                            
                        bot.send_video(
                            chat_id=call.message.chat.id,
                            video=video,
                            caption=instructions['android'],
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                    logger.info("Android video guide sent successfully")
                    return
                except Exception as e:
                    logger.error(f"Error sending video: {e}")
                    
        if platform in instructions:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="help_back"))
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=instructions[platform],
                    reply_markup=markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Если не можем отредактировать, отправляем новое сообщение
                bot.send_message(
                    call.message.chat.id,
                    instructions[platform],
                    reply_markup=markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error in handle_help_callback: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data == "buy_new_device")
def handle_buy_new_device(call):
    try:
        # Получаем device_id из предыдущего состояния
        previous_message = call.message.text
        device_id = None
        
        # Показываем меню выбора тарифа для нового устройства
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(
                "1 месяц - 299₽", 
                callback_data="sub_1_299"
            ),
            types.InlineKeyboardButton(
                "3 месяца - 852₽\n✨ Скидка 5%", 
                callback_data="sub_3_852"
            ),
            types.InlineKeyboardButton(
                "6 месяцев - 1615₽\n🌟 Скидка 10%", 
                callback_data="sub_6_1615"
            ),
            types.InlineKeyboardButton(
                "12 месяцев - 3052₽\n💫 Скидка 15%", 
                callback_data="sub_12_3052"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data=f"more_devices_back"
            )
        ]
        markup.add(*buttons)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "🌟 <b>Добавление нового устройства</b>\n\n"
                "• Каждое устройство требует отдельной подписки\n"
                "• Все подписки независимы друг от друга\n"
                "• Можно использовать разные тарифы\n\n"
                "✨ <b>Выберите тариф для нового устройства:</b>"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_buy_new_device: {e}")
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Добавляем новый обработчик для кнопки "Назад" в меню устройств
@bot.callback_query_handler(func=lambda call: call.data == "more_devices_back")
def handle_more_devices_back(call):
    try:
        # Возвращаемся к предыдущему меню
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(
                "💎 Купить VPN для нового устройства", 
                callback_data="buy_new_device"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data="return_to_main"
            )
        ]
        markup.add(*buttons)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "📱 <b>Дополнительные устройства</b>\n\n"
                "• Для каждого устройства нужна отдельная подписка\n"
                "• Вы можете использовать разные тарифы\n"
                "• Все подписки управляются независимо\n\n"
                "Нажмите кнопку ниже, чтобы добавить новое устройство:"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_more_devices_back: {e}")
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Добавляем обработчик для возврата в главное меню
@bot.callback_query_handler(func=lambda call: call.data == "return_to_main")
def handle_return_to_main(call):
    try:
        # Создаем клавиатуру главного меню
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        subscriptions = sub_handler.get_user_subscriptions(call.from_user.id)
        
        if subscriptions:
            buttons = [
                "🌟 Мой VPN",
                "🔗 Ссылка на подписку",
                "💡 Помощь"
            ]
        else:
            buttons = [
                "💎 Купить подписку",
                "🌟 Мой VPN",
                "🔗 Ссылка на подписку",
                "💡 Помощь"
            ]
        
        # Создаем ряды кнопок по 2 в каждом
        for i in range(0, len(buttons), 2):
            row_buttons = buttons[i:i+2]
            markup.row(*row_buttons)
            
        # Пробуем удалить предыдущее сообщение
        try:
            bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except:
            pass
            
        # Отправляем новое сообщение с главным меню
        bot.send_message(
            call.message.chat.id,
            "🌍 Главное меню",
            reply_markup=markup
        )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error in handle_return_to_main: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.send_message(message.chat.id, 
        "Пожалуйста, используйте кнопки меню для навигации.\n"
        "Если кнопки не отображаются, напишите /start")

# Добавляем функцию для обновления меню VPN
def my_vpn_menu(message, device_id):
    try:
        subscriptions = sub_handler.get_user_subscriptions(message.from_user.id)
        
        for sub in subscriptions:
            if sub[5] == device_id:  # Находим нужную подписку по device_id
                end_date = datetime.fromisoformat(sub[2])
                
                markup = types.InlineKeyboardMarkup(row_width=1)
                buttons = [
                    types.InlineKeyboardButton(
                        "⭐️ ПРОДЛИТЬ ТАРИФ", 
                        callback_data=f"extend_{device_id}"
                    ),
                    types.InlineKeyboardButton(
                        "➕ ДОБАВИТЬ УСТРОЙСТВО", 
                        callback_data=f"more_devices_{device_id}"
                    )
                ]
                markup.add(*buttons)
                
                message_text = (
                    f"⚡️ Протокол:\n"
                    f"└ VLESS\n\n"
                    f"📅 Подписка активна до:\n"
                    f"└ {end_date.strftime('%d.%m.%y %H:%M')}\n\n"
                    f"🌍 Регион:\n"
                    f"└ 🇫🇮 Финляндия\n\n"
                    f"📱 Одновременно работающих устройств:\n"
                    f"└ 1"
                )
                
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=message_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                return
                
    except Exception as e:
        logger.error(f"Error in my_vpn_menu: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text="❌ Произошла ошибка при обновлении меню. Попробуйте позже."
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('return_to_vpn_'))
def handle_return(call):
    try:
        device_id = call.data.split('_')[-1]
        # Получаем подписку
        subscriptions = sub_handler.get_user_subscriptions(call.from_user.id)
        
        for sub in subscriptions:
            if sub[5] == device_id:  # Находим нужную подписку по device_id
                end_date = datetime.fromisoformat(sub[2])
                
                markup = types.InlineKeyboardMarkup(row_width=1)
                buttons = [
                    types.InlineKeyboardButton(
                        "⭐️ ПРОДЛИТЬ ТАРИФ", 
                        callback_data=f"extend_{device_id}"
                    ),
                    types.InlineKeyboardButton(
                        "➕ ДОБАВИТЬ УСТРОЙСТВО", 
                        callback_data=f"more_devices_{device_id}"
                    )
                ]
                markup.add(*buttons)
                
                message_text = (
                    f"⚡️ Протокол:\n"
                    f"└ VLESS\n\n"
                    f"📅 Подписка активна до:\n"
                    f"└ {end_date.strftime('%d.%m.%y %H:%M')}\n\n"
                    f"🌍 Регион:\n"
                    f"└ 🇫🇮 Финляндия\n\n"
                    f"📱 Одновременно работающих устройств:\n"
                    f"└ 1"
                )
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=message_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                return
                
        # Если подписка не найдена
        bot.answer_callback_query(
            call.id,
            text="❌ Подписка не найдена",
            show_alert=True
        )
                
    except Exception as e:
        logger.error(f"Error in handle_return: {e}")
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('more_devices_'))
def handle_more_devices(call):
    try:
        device_id = call.data.split('_')[2]
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(
                "1 месяц - 299₽", 
                callback_data=f"new_sub_1_299_{device_id}"
            ),
            types.InlineKeyboardButton(
                "3 месяца - 852₽\n✨ Скидка 5%", 
                callback_data=f"new_sub_3_852_{device_id}"
            ),
            types.InlineKeyboardButton(
                "6 месяцев - 1615₽\n🌟 Скидка 10%", 
                callback_data=f"new_sub_6_1615_{device_id}"
            ),
            types.InlineKeyboardButton(
                "12 месяцев - 3052₽\n💫 Скидка 15%", 
                callback_data=f"new_sub_12_3052_{device_id}"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data=f"return_to_vpn_{device_id}"
            )
        ]
        markup.add(*buttons)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "🌟 <b>Добавление нового устройства</b>\n\n"
                "• Каждое устройство требует отдельной подписки\n"
                "• Все подписки независимы друг от друга\n"
                "• Можно использовать разные тарифы\n\n"
                "✨ <b>Выберите тариф для нового устройства:</b>"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_more_devices: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('new_sub_'))
def handle_new_subscription(call):
    try:
        logger.info(f"Starting handle_new_subscription with data: {call.data}")
        # new_sub_1_200_cd5f893e
        _, sub, duration, price, device_id = call.data.split('_')
        
        # Сначала показываем меню оплаты
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "💳 Оплатить", 
                callback_data=f"pay_new_{duration}_{device_id}"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад",
                callback_data=f"more_devices_{device_id}"
            )
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"💎 <b>Новая подписка</b>\n\n"
                f"📱 Длительность: {duration} мес.\n"
                f"💵 Стоимость: {price}₽\n\n"
                f"Для подключения нового устройства, нажмите кнопку оплаты:"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except ValueError as e:
        logger.error(f"Error parsing callback data: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Ошибка обработки данных",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error in handle_new_subscription: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Добавляем обработчик оплаты нового устройства
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_new_'))
def handle_new_device_payment(call):
    try:
        _, _, duration, device_id = call.data.split('_')
        new_device_id = str(uuid.uuid4())[:8]
        
        # Тестовая оплата (здесь будет интеграция с платежной системой)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "✅ Тестовая оплата",
                callback_data=f"confirm_new_{duration}_{new_device_id}"
            )
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "💳 <b>Оплата подписки</b>\n\n"
                "Для тестовой оплаты нажмите кнопку ниже:"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_new_device_payment: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Добавляем обработчик подтверждения оплаты
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_new_'))
def handle_new_device_confirmation(call):
    try:
        _, _, duration, new_device_id = call.data.split('_')
        
        # Создаем подписку
        result = sub_handler.add_subscription(
            user_id=call.from_user.id,
            duration=int(duration),
            device_id=new_device_id
        )
        
        if result['success']:
            config_link = sub_handler.xui_client.get_client_config(result['uuid'], new_device_id)
            
            # Отправляем сообщение с конфигурацией
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=(
                    f"✅ <b>Новое устройство успешно добавлено!</b>\n\n"
                    f"📱 ID устройства: {new_device_id}\n"
                    f"⏱ Длительность: {duration} мес.\n\n"
                    f"🔗 <b>Ваша ссылка для подключения:</b>\n\n"
                    f"<code>{config_link}</code>\n\n"
                    f"Скопируйте ссылку и следуйте инструкции для вашего устройства:\n"
                    f"/help_setup"
                ),
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
            # Отправляем ссылку отдельным сообщением для удобного копирования
            bot.send_message(
                chat_id=call.message.chat.id,
                text=config_link,
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Error in handle_new_device_confirmation: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Обработчик для кнопки "ПРОДЛИТЬ ТАРИФ"
@bot.callback_query_handler(func=lambda call: call.data.startswith('extend_'))
def handle_extend(call):
    try:
        logger.info(f"Handling extend callback with data: {call.data}")
        device_id = call.data.split('_')[1]
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(
                "1 месяц - 299₽", 
                callback_data=f"extend_sub_1_299_{device_id}"
            ),
            types.InlineKeyboardButton(
                "3 месяца - 852₽\n✨ Скидка 5%", 
                callback_data=f"extend_sub_3_852_{device_id}"
            ),
            types.InlineKeyboardButton(
                "6 месяцев - 1615₽\n🌟 Скидка 10%", 
                callback_data=f"extend_sub_6_1615_{device_id}"
            ),
            types.InlineKeyboardButton(
                "12 месяцев - 3052₽\n💫 Скидка 15%", 
                callback_data=f"extend_sub_12_3052_{device_id}"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data=f"return_to_vpn_{device_id}"
            )
        ]
        markup.add(*buttons)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "🌟 <b>Продление подписки</b>\n\n"
                "• Подписка продлевается с момента окончания текущей\n"
                "• Можно выбрать любой тариф\n\n"
                "✨ <b>Выберите период продления:</b>"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        logger.info("Successfully sent extend menu")
        
    except Exception as e:
        logger.error(f"Error in handle_extend: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Обработчик для кнопки "ПОДАРИТЬ ПОДПИСКУ"
@bot.callback_query_handler(func=lambda call: call.data.startswith('gift_'))
def handle_gift(call):
    try:
        device_id = call.data.split('_')[1]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data=f"return_to_vpn_{device_id}"
            )
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "🎁 <b>Подарить подписку</b>\n\n"
                "Для передачи подписки другому пользователю, "
                "перешлите ему следующий код:\n\n"
                f"<code>GIFT_{device_id}</code>\n\n"
                "❗️ Внимание: после активации кода текущая "
                "подписка будет привязана к новому пользователю"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_gift: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Обработчик для кнопки "НАСТРОИТЬ АВТОПРОДЛЕНИЕ"
@bot.callback_query_handler(func=lambda call: call.data.startswith('autopay_'))
def handle_autopay(call):
    try:
        device_id = call.data.split('_')[1]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Включить автопродление", 
                callback_data=f"autopay_on_{device_id}"
            ),
            types.InlineKeyboardButton(
                "❌ Отключить автопродление", 
                callback_data=f"autopay_off_{device_id}"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад", 
                callback_data=f"return_to_vpn_{device_id}"
            )
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                "🔄 <b>Настройка автопродления</b>\n\n"
                "При включенном автопродлении подписка будет "
                "автоматически продлеваться за 24 часа до окончания.\n\n"
                "Текущий статус: ❌ Отключено"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_autopay: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# Обработчик для выбора тарифа продления
@bot.callback_query_handler(func=lambda call: call.data.startswith('extend_sub_'))
def handle_extend_subscription(call):
    try:
        _, _, duration, price, device_id = call.data.split('_')
        
        # Показываем меню оплаты
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "💳 Оплатить", 
                callback_data=f"pay_extend_{duration}_{device_id}"
            ),
            types.InlineKeyboardButton(
                "◀️ Вернуться назад",
                callback_data=f"extend_{device_id}"
            )
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"💎 <b>Продление подписки</b>\n\n"
                f"📱 Длительность: {duration} мес.\n"
                f"💵 Стоимость: {price}₽\n\n"
                f"Для продления подписки нажмите кнопку оплаты:"
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_extend_subscription: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

# 1. Исправляем обработчик основной кнопки "Назад"
@bot.callback_query_handler(func=lambda call: call.data == "help_back")
def handle_back_button(call):
    try:
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton("🍎 iOS / iPadOS / MacOS", callback_data="help_ios"),
            types.InlineKeyboardButton("📱 Android", callback_data="help_android"),
            types.InlineKeyboardButton("📱 Huawei / Honor", callback_data="help_huawei"),
            types.InlineKeyboardButton("💻 Windows", callback_data="help_windows"),
            types.InlineKeyboardButton("📺 Android TV", callback_data="help_androidtv"),
            types.InlineKeyboardButton("🔄 Обновление подписки", callback_data="help_update")
        ]
        markup.add(*buttons)
        
        # Проверяем существование сообщения перед редактированием
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="💡 <b>Выберите вашу платформу для получения инструкции:</b>",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            # Если не можем отредактировать, отправляем новое
            bot.send_message(
                call.message.chat.id,
                "💡 <b>Выберите вашу платформу для получения инструкции:</b>",
                reply_markup=markup,
                parse_mode='HTML'
            )
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Error in handle_back_button: {e}", exc_info=True)
        bot.answer_callback_query(
            call.id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )

def main():
    try:
        logger.info("Бот запущен")
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        main()  # Перезапуск бота при ошибке

if __name__ == '__main__':
    main() 