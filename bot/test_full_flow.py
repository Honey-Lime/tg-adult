# test_full_flow.py
"""Тест полного потока: создание поста + добавление видео"""
import psycopg2
import logging
from psycopg2 import pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'database': 'adult_tg_bot_db',
    'user': 'adult_tg_bot',
    'password': 'm*0FaIw$2!amS',
    'host': 'localhost',
    'port': 5432
}

connection_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)

def get_connection():
    return connection_pool.getconn()

def return_connection(conn):
    connection_pool.putconn(conn)

def add_post_record(pic_type, date):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO posts (type, date)
                VALUES (%s, %s)
                RETURNING id
            """, (pic_type, date))
            post_id = cur.fetchone()[0]
            conn.commit()
            return post_id
    except Exception as e:
        logging.error(f"Error adding post: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)

def add_video_record(post_id, path):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO videos (post_id, path)
                VALUES (%s, %s)
                RETURNING id
            """, (post_id, path))
            video_id = cur.fetchone()[0]
            conn.commit()
            return video_id
    except Exception as e:
        logging.error(f"Error adding video: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)

# Тест полного потока
logger.info("=== Тест: создание поста + добавление видео ===")

# 1. Создаём пост
post_id = add_post_record(777, '03.04.2023 10:00:00')
logger.info(f"Создан пост: {post_id}")

if post_id:
    # 2. Добавляем видео
    video_id = add_video_record(post_id, 'test_video.mp4')
    logger.info(f"Добавлено видео: {video_id}")
    
    if video_id:
        # 3. Проверяем результат
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT v.id, v.post_id, v.path, p.type, p.date
                FROM videos v
                JOIN posts p ON v.post_id = p.id
                WHERE v.id = %s
            """, (video_id,))
            row = cur.fetchone()
            if row:
                logger.info(f"✓ Проверка: video_id={row[0]}, post_id={row[1]}, path={row[2]}, post_type={row[3]}, post_date={row[4]}")
            else:
                logger.error("✗ Видео не найдено!")
        return_connection(conn)
        
        # Удаляем тестовые данные
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
            cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
            conn.commit()
        return_connection(conn)
        logger.info("Тестовые данные удалены")

connection_pool.closeall()
logger.info("\n=== Тест завершён ===")
