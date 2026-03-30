# reset_and_test.py
"""Сброс пула соединений и тест"""
import psycopg2
import logging
from psycopg2 import pool
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'database': 'adult_tg_bot_db',
    'user': 'adult_tg_bot',
    'password': 'm*0FaIw$2!amS',
    'host': 'localhost',
    'port': 5432
}

# Закрываем все старые соединения
try:
    existing_pool = pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
    existing_pool.closeall()
    logger.info("Старые соединения закрыты")
except:
    pass

time.sleep(1)

# Создаём новый пул
connection_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
logger.info("Новый пул соединений создан")

def get_connection():
    return connection_pool.getconn()

def return_connection(conn):
    connection_pool.putconn(conn)

# Тест: создание поста и видео
logger.info("\n=== Тест после сброса пула ===")

conn = get_connection()
try:
    with conn.cursor() as cur:
        # Создаём пост
        cur.execute("""
            INSERT INTO posts (type, date)
            VALUES (%s, %s)
            RETURNING id
        """, (777, '04.04.2023 12:00:00'))
        post_id = cur.fetchone()[0]
        conn.commit()
        logger.info(f"✓ Пост создан: {post_id}")
        
        # Добавляем видео
        cur.execute("""
            INSERT INTO videos (post_id, path)
            VALUES (%s, %s)
            RETURNING id
        """, (post_id, 'reset_test.mp4'))
        video_id = cur.fetchone()[0]
        conn.commit()
        logger.info(f"✓ Видео добавлено: {video_id}")
        
        # Проверяем
        cur.execute("""
            SELECT v.id, v.post_id, p.type 
            FROM videos v 
            JOIN posts p ON v.post_id = p.id 
            WHERE v.id = %s
        """, (video_id,))
        row = cur.fetchone()
        logger.info(f"✓ Проверка: video_id={row[0]}, post_id={row[1]}, post_type={row[2]}")
        
        # Удаляем тест
        cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()
        logger.info("Тестовые данные удалены")
        
except Exception as e:
    logger.error(f"✗ Ошибка: {e}")
    conn.rollback()
finally:
    return_connection(conn)

connection_pool.closeall()
logger.info("\n=== Тест завершён ===")
