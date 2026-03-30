# test_video_insert.py
"""Тест вставки видео с реальным post_id"""
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'database': 'adult_tg_bot_db',
    'user': 'adult_tg_bot',
    'password': 'm*0FaIw$2!amS',
    'host': 'localhost',
    'port': 5432
}

conn = None
try:
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False  # Важно: транзакция!
    
    with conn.cursor() as cur:
        # Проверяем, существует ли пост 26789
        logger.info("Проверка поста 26789...")
        cur.execute("SELECT id FROM posts WHERE id = %s", (26789,))
        post = cur.fetchone()
        if post:
            logger.info(f"✓ Пост 26789 существует")
        else:
            logger.error("✗ Пост 26789 НЕ существует!")
        
        # Проверяем последовательность перед вставкой
        cur.execute("SELECT last_value, is_called FROM videos_id_seq")
        logger.info(f"Sequence до вставки: {cur.fetchone()}")
        
        # Пробуем вставку точно так же, как в database.py
        logger.info("\nВставка видео...")
        cur.execute("""
            INSERT INTO videos (post_id, path)
            VALUES (%s, %s)
            RETURNING id
        """, (26789, '4VvTl5Apvy1zmW6N.mp4'))
        
        video_id = cur.fetchone()[0]
        logger.info(f"✓ Вставка успешна! video_id={video_id}")
        
        # Проверяем последовательность после вставки
        cur.execute("SELECT last_value, is_called FROM videos_id_seq")
        logger.info(f"Sequence после вставки: {cur.fetchone()}")
        
        # Откатываем тест
        conn.rollback()
        logger.info("\nТранзакция откатлена")
        
except Exception as e:
    logger.error(f"✗ Ошибка: {e}")
    if conn:
        conn.rollback()
finally:
    if conn:
        conn.close()
