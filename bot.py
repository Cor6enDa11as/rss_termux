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

# ==================== Загрузка настроек ====================
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

if not BOT_TOKEN or not CHANNEL_ID:
    logging.error("❌ Установите BOT_TOKEN и CHANNEL_ID в .env файле!")
    exit(1)

REQUEST_DELAY = (int(os.getenv('REQUEST_DELAY_MIN', '3')),
                 int(os.getenv('REQUEST_DELAY_MAX', '7')))
MAX_HOURS_BACK = int(os.getenv('MAX_HOURS_BACK', '24'))

# ==================== Настройка логирования ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== Функции ====================

def load_rss_feeds():
    """📰 Загружает RSS-ленты и хэштеги"""
    feeds = []
    hashtags = {}

    try:
        with open('feeds.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '#' in line:
                    url, tag = line.split('#', 1)
                    feeds.append(url.strip())
                    hashtags[url.strip()] = '#' + tag.strip()
                else:
                    feeds.append(line)
                    hashtags[line] = '#новости'

    except FileNotFoundError:
        logger.error("❌ Файл feeds.txt не найден")
        exit(1)

    if not feeds:
        logger.error("❌ Нет RSS-лент")
        exit(1)

    logger.info(f"📰 Загружено: {len(feeds)} лент")
    return feeds, hashtags

def load_dates():
    """📁 Загружает историю отправленных постов"""
    try:
        with open('dates.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for url, info in data.items():
                if 'last_date' in info:
                    info['last_date'] = datetime.fromisoformat(info['last_date'])
            return data
    except FileNotFoundError:
        return {}

def save_dates(dates_dict):
    """💾 Сохраняет историю отправленных постов"""
    data_to_save = {}
    for url, info in dates_dict.items():
        if isinstance(info, dict) and 'last_date' in info:
            data_to_save[url] = {'last_date': info['last_date'].isoformat()}

    with open('dates.json', 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=2, ensure_ascii=False)

def is_russian_text(text):
    """🔤 Проверяет, есть ли в тексте русские буквы"""
    return any('а' <= char <= 'я' for char in text.lower())

def translate_text(text):
    """🌐 Переводит текст на русский (если нужно)"""
    try:
        if not text or len(text) < 3:
            return text, False

        url = "https://translate.googleapis.com/translate_a/single"
        params = {'client': 'gtx', 'sl': 'auto', 'tl': 'ru', 'dt': 't', 'q': text[:500]}
        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            translated = response.json()[0][0][0]
            if translated and translated.strip() and translated != text:
                return translated, True
        return text, False
    except Exception:
        return text, False

def send_to_telegram(title, link, feed_url, hashtags_dict):
    """📨 Отправляет сообщение"""
    try:
        clean_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        hashtag = f"🏷️  {hashtags_dict.get(feed_url, '#новости')}"
        message = f'📢  <a href="{link}"><b>{clean_title}</b></a>\n{hashtag}'

        data = {
            'chat_id': CHANNEL_ID,
            'text': message,
            'parse_mode': 'HTML',
            'link_preview_options': json.dumps({
                'is_disabled': False,
                'url': link,
                'show_above_text': True
            })
        }

        response = requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                               data=data, timeout=10)
        return response.status_code == 200

    except Exception as e:
        logger.error(f"🤖 Ошибка: {e}")
        return False

def parse_feed(url):
    """📰 Парсит RSS-ленту"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/rss+xml'}
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.content)
        return feed if hasattr(feed, 'entries') and feed.entries else None
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга {url[:40]}...: {e}")
        return None

def get_entry_date(entry):
    """📅 Получает дату записи"""
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

# ==================== Основная логика ====================

def check_feeds():
    """🔍 Основная функция проверки лент"""
    logger.info("=" * 60)
    logger.info("🔍 Начало проверки новостей")
    start_time = time.time()

    RSS_FEEDS, HASHTAGS = load_rss_feeds()
    dates = load_dates()
    sent_count = 0

    for feed_url in RSS_FEEDS:
        try:
            logger.info(f"📰 Проверка: {feed_url[:50]}...")

            last_date = dates.get(feed_url, {}).get('last_date')
            threshold_date = (datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS_BACK)
                            if last_date is None else last_date)

            feed = parse_feed(feed_url)
            if not feed:
                continue

            new_entries = []
            for entry in feed.entries:
                entry_date = get_entry_date(entry)
                if entry_date > threshold_date:
                    new_entries.append((entry, entry_date))

            if new_entries:
                logger.info(f"  📦 Найдено новых: {len(new_entries)}")
                new_entries.sort(key=lambda x: x[1])

                for entry, pub_date in new_entries:
                    title = getattr(entry, 'title', 'Без названия')
                    link = getattr(entry, 'link', '')

                    if not link:
                        continue

                    if not is_russian_text(title):
                        title, _ = translate_text(title)

                    logger.info(f"  📤 Отправка [{pub_date.strftime('%H:%M')}]: {title[:60]}...")

                    if send_to_telegram(title, link, feed_url, HASHTAGS):
                        sent_count += 1
                        dates[feed_url] = {'last_date': pub_date}
                        save_dates(dates)
                        time.sleep(random.uniform(*REQUEST_DELAY))
                    else:
                        logger.error("  ❌ Ошибка отправки")
                        break
            else:
                logger.info(f"  ✅ Нет новых новостей")

            time.sleep(random.uniform(*REQUEST_DELAY))

        except Exception as e:
            logger.error(f"  ❌ Ошибка: {e}")
            time.sleep(random.uniform(*REQUEST_DELAY))
            continue

    save_dates(dates)

    logger.info(f"📊 Проверка завершена. Отправлено: {sent_count} новостей")
    logger.info(f"⏱ Время выполнения: {time.time() - start_time:.1f} сек")
    logger.info("=" * 60)
    return sent_count

# ==================== Запуск ====================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 RSS to Telegram Bot запущен")
    logger.info(f"⏰ Задержка между запросами: {REQUEST_DELAY[0]}-{REQUEST_DELAY[1]} сек")
    logger.info(f"⏳ Проверяем новости за: {MAX_HOURS_BACK} часов")
    logger.info("=" * 60)

    sent_count = check_feeds()

    logger.info(f"✅ Бот завершил работу. Отправлено: {sent_count} постов")
