#!/usr/bin/env python3
"""
Скрипт для исправления последовательности id в таблице videos на сервере.
Запускать на Linux сервере: python3 fix_server_sequence.py
"""
import psycopg2
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Параметры подключения
DB_CONFIG = {
    'database': 'adult_tg_bot_db',
    'user': 'adult_tg_bot',
    'password': 'm*0FaIw$2!amS',
    'host': 'localhost',
    'port': 5432
}


def diagnose_and_fix():
    """Диагностика и исправление последовательности videos."""
    
    conn = None
    try:
        logger.info("Подключение к базе данных...")
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        
        with conn.cursor() as cur:
            # 1. Проверяем текущее состояние
            logger.info("=" * 60)
            logger.info("ДИАГНОСТИКА ТАБЛИЦЫ videos")
            logger.info("=" * 60)
            
            # Считаем количество записей
            cur.execute("SELECT COUNT(*) FROM videos")
            count = cur.fetchone()[0]
            logger.info(f"Всего записей в videos: {count}")
            
            # Проверяем максимальный id
            cur.execute("SELECT MAX(id) FROM videos")
            max_id = cur.fetchone()[0]
            logger.info(f"Максимальный id: {max_id}")
            
            # Проверяем минимальный id
            cur.execute("SELECT MIN(id) FROM videos")
            min_id = cur.fetchone()[0]
            logger.info(f"Минимальный id: {min_id}")
            
            # Проверяем column_default
            cur.execute("""
                SELECT column_default 
                FROM information_schema.columns 
                WHERE table_name = 'videos' AND column_name = 'id'
            """)
            row = cur.fetchone()
            if row:
                logger.info(f"Column default для id: {row[0]}")
            else:
                logger.warning("Column default не найден!")
            
            # Проверяем имя последовательности
            cur.execute("""
                SELECT pg_get_serial_sequence('videos', 'id')
            """)
            seq_name = cur.fetchone()[0]
            logger.info(f"Имя последовательности: {seq_name}")
            
            if seq_name:
                # Проверяем текущее значение последовательности
                cur.execute(f"SELECT last_value, is_called FROM {seq_name}")
                seq_info = cur.fetchone()
                logger.info(f"Последовательность: last_value={seq_info[0]}, is_called={seq_info[1]}")
            
            # Проверяем, есть ли записи с NULL id
            cur.execute("SELECT COUNT(*) FROM videos WHERE id IS NULL")
            null_count = cur.fetchone()[0]
            if null_count > 0:
                logger.error(f"НАЙДЕНО ЗАПИСЕЙ С NULL id: {null_count}")
            
            logger.info("=" * 60)
            
            # 2. Исправляем
            logger.info("ИСПРАВЛЕНИЕ...")
            
            if seq_name:
                # Последовательность существует - сбрасываем её
                logger.info(f"Сброс последовательности {seq_name}...")
                cur.execute(f"""
                    SELECT setval('{seq_name}', 
                                  COALESCE((SELECT MAX(id) FROM videos), 0) + 1, 
                                  false)
                """)
                new_val = cur.fetchone()[0]
                logger.info(f"✓ Последовательность установлена в {new_val}")
            else:
                # Последовательности нет - пересоздаём
                logger.warning("Последовательность не найдена. Пересоздание...")
                
                # Удаляем старый PRIMARY KEY
                cur.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_pkey;")
                
                # Удаляем старый column id
                cur.execute("ALTER TABLE videos DROP COLUMN id;")
                
                # Добавляем новый id как SERIAL
                cur.execute("ALTER TABLE videos ADD COLUMN id SERIAL PRIMARY KEY;")
                
                logger.info("✓ Column id пересоздан как SERIAL")
            
            # Проверяем результат
            cur.execute("SELECT pg_get_serial_sequence('videos', 'id')")
            new_seq = cur.fetchone()[0]
            logger.info(f"✓ Новая последовательность: {new_seq}")
            
            # Проверяем, что теперь можно вставить запись
            cur.execute("""
                INSERT INTO videos (post_id, path) 
                VALUES (0, 'test_entry.tmp')
                RETURNING id
            """)
            test_id = cur.fetchone()[0]
            logger.info(f"✓ Тестовая вставка успешна! id={test_id}")
            
            # Удаляем тестовую запись
            cur.execute("DELETE FROM videos WHERE id = %s", (test_id,))
            logger.info("✓ Тестовая запись удалена")
            
            conn.commit()
            
            logger.info("=" * 60)
            logger.info("✓ ИСПРАВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО!")
            logger.info("=" * 60)
            
            return True
            
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"✗ ОШИБКА: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Исправление последовательности videos на сервере")
    print("=" * 60)
    
    success = diagnose_and_fix()
    
    if success:
        print("\n✓ ГОТОВО! Можно перезапускать бота.")
        sys.exit(0)
    else:
        print("\n✗ ОШИБКА! Проверьте логи выше.")
        sys.exit(1)
