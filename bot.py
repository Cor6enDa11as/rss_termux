#!/usr/bin/env python3
"""
🚀 RSS to Telegram Bot (Termux Optimized)
"""

import os
import json
import feedparser
import requests
import time
import logging
import random
from datetime import datetime, timezone, timedelta
#from dotenv import load_dotenv
from urllib.parse import urlparse

# ==================== Загрузка настроек ====================
#load_dotenv()
#BOT_TOKEN = os.getenv('BOT_TOKEN')
#CHANNEL_ID = os.getenv('CHANNEL_ID')

#if not BOT_TOKEN or not CHANNEL_ID:
#    logging.error("❌ Установите BOT_TOKEN и CHANNEL_ID в .env файле!")
#    exit(1)

# ✅ ТЕРМИНАЛЬНЫЕ НАСТРОЙКИ TERMUX
CONFIG = {
    'REQUEST_DELAY_MIN': int(os.getenv('REQUEST_DELAY_MIN', '8')),
    'REQUEST_DELAY_MAX': int(os.getenv('REQUEST_DELAY_MAX', '20')),
    'MAX_HOURS_BACK': int(os.getenv('MAX_HOURS_BACK', '4'))
}

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

def send_to_telegram(title, link, feed_url, hashtags_dict, entry):
    """📨 Отправляет сообщение (ПРЕВЬЮ СВЕРХУ!)"""
    try:
        clean_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        hashtag = hashtags_dict.get(feed_url, '#новости')
        
        author = getattr(entry, 'author', '')
        if author:
            author_hashtag = author.replace(" ", "")
            message = f'<a href="{link}">{clean_title}</a>\n\n📌 {hashtag} 👤 #{author_hashtag}'
        else:
            message = f'<a href="{link}">{clean_title}</a>\n\n📌 {hashtag}'

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
        
        if response.status_code == 200:
            time.sleep(random.uniform(20, 30))
            return True
        else:
            logger.error(f"❌ TG ответ: {response.status_code}")
            return False
        
    except Exception as e:
        logger.error(f"🤖 Ошибка отправки: {e}")
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
    logger.info(f"🤖 [{len(RSS_FEEDS)} лент] {datetime.now().strftime('%H:%M')}")
    start_time = time.time()

    dates = load_dates()
    sent_count = 0

    for feed_url in RSS_FEEDS:
        try:
            logger.info(f"📰 Проверка: {feed_url[:50]}...")
            
            last_date = dates.get(feed_url, {}).get('last_date')
            threshold_date = (datetime.now(timezone.utc) - timedelta(hours=CONFIG['MAX_HOURS_BACK']) 
                            if last_date is None else last_date)

            feed = parse_feed(feed_url)
            if not feed:
                time.sleep(random.uniform(CONFIG['REQUEST_DELAY_MIN'], CONFIG['REQUEST_DELAY_MAX']))
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

                    logger.info(f"  📤 Отправка [{pub_date.strftime('%H:%M')}]: {title[:60]}...")
                    
                    if send_to_telegram(title, link, feed_url, HASHTAGS, entry):
                        sent_count += 1
                        dates[feed_url] = {'last_date': pub_date}
                        save_dates(dates)
                    else:
                        logger.error("  ❌ Ошибка отправки")
                        break
            else:
                logger.info(f"  ✅ Нет новых новостей")

            time.sleep(random.uniform(CONFIG['REQUEST_DELAY_MIN'], CONFIG['REQUEST_DELAY_MAX']))

        except Exception as e:
            logger.error(f"  ❌ Ошибка: {e}")
            time.sleep(random.uniform(CONFIG['REQUEST_DELAY_MIN'], CONFIG['REQUEST_DELAY_MAX']))
            continue

    save_dates(dates)
    logger.info(f"📊 Проверка завершена. Отправлено: {sent_count} новостей")
    logger.info(f"⏱ Время выполнения: {time.time() - start_time:.1f} сек")
    logger.info("=" * 60)
    return sent_count

# ==================== Запуск ====================

if __name__ == '__main__':
    logger.info("=" * 60)
    RSS_FEEDS, HASHTAGS = load_rss_feeds()
    logger.info(f"⏰ Задержка между запросами: {CONFIG['REQUEST_DELAY_MIN']}-{CONFIG['REQUEST_DELAY_MAX']} сек")
    logger.info(f"⏳ Проверяем новости за: {CONFIG['MAX_HOURS_BACK']} часов")
    logger.info("=" * 60)
    
    sent_count = check_feeds()
    logger.info(f"✅ Бот завершил работу. Отправлено: {sent_count} постов")
