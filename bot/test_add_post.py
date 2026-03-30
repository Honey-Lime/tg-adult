# test_add_post.py
"""Тест создания поста"""
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

# Создаём пул как в database.py
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
        logging.error(f"Error: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)

# Тест
logger.info("Тест создания поста...")
post_id = add_post_record(777, '02.04.2023 09:05:00')
logger.info(f"Результат: post_id={post_id}, type={type(post_id)}")

if post_id:
    # Проверяем, что пост создан
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, type, date FROM posts WHERE id = %s", (post_id,))
        row = cur.fetchone()
        if row:
            logger.info(f"✓ Пост создан: id={row[0]}, type={row[1]}, date={row[2]}")
        else:
            logger.error("✗ Пост не найден после создания!")
    return_connection(conn)

connection_pool.closeall()
