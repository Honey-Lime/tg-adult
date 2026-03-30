# check_videos_structure.py
"""Проверка структуры таблицы videos"""
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
    with conn.cursor() as cur:
        # Проверяем структуру таблицы
        logger.info("=== Структура таблицы videos ===")
        cur.execute("""
            SELECT column_name, data_type, column_default, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'videos'
            ORDER BY ordinal_position
        """)
        for row in cur.fetchall():
            logger.info(f"  {row[0]}: {row[1]}, default={row[2]}, nullable={row[3]}")
        
        # Проверяем последовательность
        logger.info("\n=== Последовательность ===")
        cur.execute("SELECT pg_get_serial_sequence('videos', 'id')")
        logger.info(f"Sequence: {cur.fetchone()[0]}")
        
        # Проверяем текущее значение последовательности
        cur.execute("SELECT last_value, is_called FROM videos_id_seq")
        logger.info(f"Sequence state: {cur.fetchone()}")
        
        # Проверяем максимальный id
        cur.execute("SELECT MAX(id) FROM videos")
        logger.info(f"MAX(id): {cur.fetchone()[0]}")
        
        # Проверяем наличие триггеров
        logger.info("\n=== Триггеры ===")
        cur.execute("""
            SELECT trigger_name, event_manipulation, action_statement
            FROM information_schema.triggers
            WHERE event_object_table = 'videos'
        """)
        triggers = cur.fetchall()
        if triggers:
            for t in triggers:
                logger.info(f"  {t[0]}: {t[1]} -> {t[2][:50]}...")
        else:
            logger.info("  Триггеров нет")
        
        # Пробуем вставить тестовую запись
        logger.info("\n=== Тестовая вставка ===")
        cur.execute("""
            INSERT INTO videos (post_id, path)
            VALUES (%s, %s)
            RETURNING id
        """, (99999, 'test.mp4'))
        test_id = cur.fetchone()[0]
        logger.info(f"✓ Тестовая вставка успешна! id={test_id}")
        
        # Удаляем тестовую запись
        cur.execute("DELETE FROM videos WHERE id = %s", (test_id,))
        conn.commit()
        logger.info("Тестовая запись удалена")
        
except Exception as e:
    logger.error(f"Ошибка: {e}")
    if conn:
        conn.rollback()
finally:
    if conn:
        conn.close()
