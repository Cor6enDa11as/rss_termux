#!/usr/bin/env python3

import os
import json
import feedparser
import requests
import time
import logging
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from urllib.parse import urlparse

# ==================== ЗАГРУЗКА .env ====================
load_dotenv()

# ==================== НАСТРОЙКИ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Получаем настройки из .env
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# ==================== ЗАГРУЗКА RSS ЛЕНТ ====================
def load_rss_feeds():
    """📰 Загружает RSS ленты из .env файла - ПРОСТО И БЫСТРО"""
    feeds_str = os.getenv('RSS_FEEDS', '')

    if not feeds_str:
        logger.error("❌ RSS_FEEDS не найден в .env файле!")
        exit(1)

    # Разбиваем по переносу строки
    feeds = []
    for line in feeds_str.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            feeds.append(line)

    if not feeds:
        logger.error("❌ Нет RSS лент в .env файле!")
        exit(1)

    logger.info(f"📰 Загружено {len(feeds)} RSS лент")
    return feeds

RSS_FEEDS = load_rss_feeds()

# Проверяем обязательные настройки
if not BOT_TOKEN or not CHANNEL_ID:
    logger.error("❌ Установите BOT_TOKEN и CHANNEL_ID в .env файле!")
    exit(1)

# Настройки из .env
REQUEST_DELAY_MIN = int(os.getenv('REQUEST_DELAY_MIN', '2'))
REQUEST_DELAY_MAX = int(os.getenv('REQUEST_DELAY_MAX', '5'))
MAX_HOURS_BACK = int(os.getenv('MAX_HOURS_BACK', '48'))  # За сколько часов проверяем новости

# Случайные User-Agent
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
]

# ==================== УПРОЩЕННЫЕ ФУНКЦИИ ====================
def load_dates():
    """📁 Загружает историю из dates.json - ПРОСТО"""
    try:
        with open('dates.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Конвертируем строки дат в datetime
            for url, info in data.items():
                if isinstance(info, dict) and 'last_date' in info:
                    info['last_date'] = datetime.fromisoformat(info['last_date'])
            return data
    except FileNotFoundError:
        logger.info("📁 dates.json не найден, начинаем с чистого листа")
        return {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки dates.json: {e}")
        return {}

def save_dates(dates_dict):
    """💾 Сохраняет историю в dates.json - ПРОСТО"""
    try:
        # Конвертируем datetime в строки для JSON
        data_to_save = {}
        for url, info in dates_dict.items():
            if isinstance(info, dict) and 'last_date' in info and isinstance(info['last_date'], datetime):
                data_to_save[url] = {
                    'last_date': info['last_date'].isoformat()
                }
            else:
                data_to_save[url] = info

        with open('dates.json', 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения dates.json: {e}")

def is_russian_text_simple(text):
    """🔤 ПРОСТАЯ проверка русского текста"""
    if not text:
        return False
    # Просто проверяем наличие русских букв
    russian_letters = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
    text_lower = text.lower()
    russian_count = sum(1 for char in text_lower if char in russian_letters)
    total_letters = sum(1 for char in text_lower if char.isalpha())

    if total_letters == 0:
        return False

    return russian_count > 0  # Хотя бы одна русская буква

def translate_text_simple(text):
    """🌐 ПРОСТОЙ перевод через Google Translate"""
    try:
        if not text or len(text) < 3:
            return text, False

        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': 'auto',
            'tl': 'ru',
            'dt': 't',
            'q': text[:500]  # Ограничиваем длину
        }

        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            translated = response.json()[0][0][0]
            if translated and translated.strip() and translated != text:
                return translated, True

        return text, False
    except Exception:
        return text, False

def create_simple_hashtag(url):
    """🏷️ ПРОСТОЙ хэштег из URL - только убираем _ и -"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Удаляем www.
        if domain.startswith('www.'):
            domain = domain[4:]

        # Берем первую часть домена до точки
        source_name = domain.split('.')[0]

        # Убираем _ и - (просто заменяем на пустоту)
        hashtag_name = source_name.replace('_', '').replace('-', '')

        # Добавляем эмодзи щита 🛡️ перед хэштегом
        return f"🏷️ #{hashtag_name}"
    except Exception:
        return "🛡️ #news"

def send_to_telegram_simple(title, link, source_url):
    """📨 ПРОСТАЯ отправка в Telegram"""
    try:
        # Экранируем HTML
        clean_title = (title
                      .replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;')
                      .replace('"', '&quot;'))

        # Создаем хэштег
        hashtag = create_simple_hashtag(source_url)

        # Формируем сообщение: 🚀 перед заголовком, 🛡️ перед хэштегом
        message = f'🚀 <a href="{link}">{clean_title}</a> {hashtag}'

        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            data={
                'chat_id': CHANNEL_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            },
            timeout=10
        )

        return response.status_code == 200

    except Exception as e:
        logger.error(f"🤖 Ошибка отправки: {e}")
        return False

def parse_feed_simple(url):
    """📰 ПРОСТОЙ парсинг RSS - без сложных проверок кодировки"""
    try:
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml',
        }

        # ПРОСТО: feedparser сам разберется с кодировкой
        feed = feedparser.parse(url, request_headers=headers, timeout=10)

        # Базовая проверка
        if hasattr(feed, 'bozo') and feed.bozo:
            logger.debug(f"⚠️ Проблемы с парсингом {url[:40]}...")
            return None

        return feed

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга {url[:40]}...: {e}")
        return None

def get_entry_date_simple(entry):
    """📅 ПРОСТОЕ получение даты записи"""
    try:
        # Пробуем published_parsed
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        # Пробуем updated_parsed
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        # Если нет нормальной даты - используем текущую
        return datetime.now(timezone.utc)

    except Exception:
        return datetime.now(timezone.utc)

# ==================== ОСНОВНАЯ ЛОГИКА ====================
def check_feeds_simple():
    """🔍 ПРОСТАЯ проверка всех RSS лент"""
    logger.info("=" * 60)
    logger.info("🚀 Начало проверки новостей")
    start_time = time.time()

    # Загружаем историю
    dates = load_dates()
    sent_count = 0

    # Для каждой ленты
    for feed_url in RSS_FEEDS:
        try:
            logger.info(f"📰 Проверка: {feed_url[:50]}...")

            # Получаем последнюю известную дату
            last_date = None
            if feed_url in dates:
                last_date = dates[feed_url].get('last_date')

            # Парсим ленту (ПРОСТО!)
            feed = parse_feed_simple(feed_url)
            if not feed or not hasattr(feed, 'entries') or not feed.entries:
                logger.error(f"  ❌ Пустая или недоступная лента")
                continue

            # Определяем пороговую дату
            # Если это первая проверка - смотрим только последние MAX_HOURS_BACK часов
            if last_date is None:
                threshold_date = datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS_BACK)
            else:
                threshold_date = last_date

            # Ищем новые записи
            new_entries_found = 0

            for entry in feed.entries:
                # Получаем дату записи (ПРОСТО!)
                entry_date = get_entry_date_simple(entry)

                # Проверяем, новая ли запись
                if entry_date > threshold_date:
                    # Получаем заголовок
                    title = getattr(entry, 'title', 'Без названия')
                    link = getattr(entry, 'link', '')

                    if not link:
                        continue

                    # Проверяем и переводим если нужно
                    if not is_russian_text_simple(title):
                        translated, success = translate_text_simple(title)
                        if success:
                            title = translated
                            logger.debug(f"  🌐 Переведено: {title[:50]}...")

                    # Отправляем (ПРОСТО!)
                    logger.info(f"  📤 Отправка: {title[:60]}...")
                    if send_to_telegram_simple(title, link, feed_url):
                        sent_count += 1
                        new_entries_found += 1

                        # Обновляем последнюю дату для этой ленты
                        dates[feed_url] = {
                            'last_date': entry_date
                        }

                        # Сохраняем после каждого успешного поста
                        save_dates(dates)

                        # Задержка между постами
                        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
                    else:
                        logger.error(f"  ❌ Ошибка отправки")
                        break  # Если не удалось отправить - пропускаем остальные посты этой ленты

            if new_entries_found:
                logger.info(f"  ✅ Найдено новых: {new_entries_found}")
            else:
                if last_date:
                    logger.info(f"  ⏳ Нет новых (последняя: {last_date.strftime('%d.%m %H:%M')})")
                else:
                    logger.info(f"  ✅ Лента проинициализирована")

            # Задержка между лентами
            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        except Exception as e:
            logger.error(f"  ❌ Ошибка обработки ленты: {e}")
            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
            continue

    # Финальное сохранение
    save_dates(dates)

    logger.info(f"📊 Проверка завершена")
    logger.info(f"✅ Отправлено постов: {sent_count}")
    logger.info(f"⏱ Время выполнения: {time.time() - start_time:.1f} сек")
    logger.info("=" * 60)

    return sent_count

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 УПРОЩЕННЫЙ RSS Bot запущен")
    logger.info(f"📰 Отслеживается лент: {len(RSS_FEEDS)}")
    logger.info(f"⏰ Задержка между запросами: {REQUEST_DELAY_MIN}-{REQUEST_DELAY_MAX} сек")
    logger.info(f"⏳ Проверяем новости за последние: {MAX_HOURS_BACK} часов")
    logger.info("=" * 60)

    # Запускаем проверку
    sent_count = check_feeds_simple()

    logger.info(f"✅ Бот завершил работу")
    logger.info(f"📨 Всего отправлено: {sent_count} постов")
    logger.info("💡 Настройте cron для автоматического запуска:")
    logger.info("   */20 * * * * cd /path/to/bot && python3 bot.py")
