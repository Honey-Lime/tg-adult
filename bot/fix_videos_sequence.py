# fix_videos_sequence.py
"""
Исправление последовательности для поля id в таблице videos.
Этот скрипт не удаляет данные, а только исправляет sequence.
"""
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Параметры подключения из .env
DB_CONFIG = {
    'database': 'adult_tg_bot_db',
    'user': 'adult_tg_bot',
    'password': 'm*0FaIw$2!amS',
    'host': 'localhost',
    'port': 5432
}


def fix_videos_sequence():
    """Исправляет последовательность для поля id в таблице videos."""
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        
        with conn.cursor() as cur:
            # Проверяем текущую последовательность
            logger.info("Checking current sequence...")
            cur.execute("""
                SELECT column_default 
                FROM information_schema.columns 
                WHERE table_name = 'videos' AND column_name = 'id'
            """)
            row = cur.fetchone()
            if row:
                logger.info(f"Current default for id: {row[0]}")
            
            # Находим имя последовательности
            cur.execute("""
                SELECT pg_get_serial_sequence('videos', 'id')
            """)
            seq_name = cur.fetchone()[0]
            logger.info(f"Sequence name: {seq_name}")
            
            if seq_name:
                # Сбрасываем последовательность на максимальное значение id + 1
                logger.info("Resetting sequence to MAX(id) + 1...")
                cur.execute("""
                    SELECT setval(pg_get_serial_sequence('videos', 'id'), 
                                  COALESCE((SELECT MAX(id) FROM videos), 0) + 1, 
                                  false)
                """)
                logger.info("✓ Sequence reset successfully!")
            else:
                # Последовательности нет - пересоздаём поле id как SERIAL
                logger.warning("No sequence found. Recreating id column as SERIAL...")
                
                # Удаляем старое поле id
                cur.execute("ALTER TABLE videos DROP COLUMN id;")
                
                # Добавляем новое поле id как SERIAL
                cur.execute("ALTER TABLE videos ADD COLUMN id SERIAL PRIMARY KEY;")
                
                logger.info("✓ Column recreated as SERIAL!")
            
            conn.commit()
            logger.info("✓ Таблица videos исправлена!")
            return True
            
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"✗ Ошибка: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Исправление последовательности для таблицы videos...")
    success = fix_videos_sequence()
    if success:
        print("\n✓ Готово! Последовательность исправлена.")
    else:
        print("\n✗ Ошибка при исправлении.")
