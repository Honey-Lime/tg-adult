#!/usr/bin/env python3
"""
Скрипт для проверки соответствия изображений в базе данных и файловой системе.
Запускается на сервере для диагностики проблемы "Нет доступных изображений".
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

import database
import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_images(image_type, limit=None, fix=False):
    """
    Проверяет изображения указанного типа.
    :param image_type: 'real' или 'anime'
    :param limit: максимальное количество записей для проверки (None - все)
    :param fix: если True, удаляет записи о отсутствующих файлах
    """
    if image_type == 'real':
        db_type = database.ImageType.REAL.value
        base_dir = database.IMAGE_DIR_REAL
    elif image_type == 'anime':
        db_type = database.ImageType.ANIME.value
        base_dir = database.IMAGE_DIR_ANIME
    else:
        logger.error(f"Неизвестный тип изображения: {image_type}")
        return

    conn = database.get_connection()
    if not conn:
        logger.error("Не удалось подключиться к базе данных")
        return

    cur = conn.cursor()
    try:
        # Общее количество записей
        cur.execute("SELECT COUNT(*) FROM pictures WHERE type = %s", (db_type,))
        total = cur.fetchone()[0]
        logger.info(f"Всего {image_type.upper()} изображений в БД: {total}")

        # Получаем записи
        query = "SELECT id, path FROM pictures WHERE type = %s"
        params = [db_type]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        cur.execute(query, params)
        rows = cur.fetchall()
        logger.info(f"Проверяем {len(rows)} записей...")

        missing_ids = []
        missing_paths = []
        for img_id, path in rows:
            full_path = os.path.join(base_dir, path)
            exists = os.path.isfile(full_path)
            if not exists:
                missing_ids.append(img_id)
                missing_paths.append((img_id, path, full_path))

        # Статистика
        logger.info(f"Найдено отсутствующих файлов: {len(missing_ids)} из {len(rows)} ({len(missing_ids)/len(rows)*100:.1f}%)")

        if missing_ids:
            logger.info("Первые 10 отсутствующих записей:")
            for img_id, path, full_path in missing_paths[:10]:
                logger.info(f"  ID {img_id}: path='{path}', full='{full_path}'")

        # Если нужно исправить
        if fix and missing_ids:
            logger.warning(f"Удаление {len(missing_ids)} записей из БД...")
            # Удаляем записи pictures
            cur.execute("DELETE FROM pictures WHERE id = ANY(%s)", (missing_ids,))
            deleted = cur.rowcount
            conn.commit()
            logger.info(f"Удалено {deleted} записей.")
            # Также нужно очистить ссылки на эти изображения в других таблицах?
            # В данном проекте, вероятно, только pictures.
        elif fix:
            logger.info("Нет отсутствующих файлов для исправления.")

        # Проверка директории
        if os.path.isdir(base_dir):
            files = [f for f in os.listdir(base_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'))]
            logger.info(f"Файлов в директории {base_dir}: {len(files)}")
            # Можно также проверить, есть ли файлы, которых нет в БД (лишние)
        else:
            logger.error(f"Директория {base_dir} не существует!")

    except Exception as e:
        logger.error(f"Ошибка при проверке: {e}", exc_info=True)
    finally:
        database.return_connection(conn)

def main():
    parser = argparse.ArgumentParser(description='Проверка соответствия изображений в БД и файловой системе.')
    parser.add_argument('--type', choices=['real', 'anime', 'both'], default='real',
                        help='Тип изображений для проверки (по умолчанию real)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Ограничить количество проверяемых записей (для быстрой проверки)')
    parser.add_argument('--fix', action='store_true',
                        help='Удалить записи о отсутствующих файлах из БД')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Подробный вывод (DEBUG)')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.type in ('real', 'anime'):
        check_images(args.type, limit=args.limit, fix=args.fix)
    elif args.type == 'both':
        check_images('real', limit=args.limit, fix=args.fix)
        check_images('anime', limit=args.limit, fix=args.fix)

if __name__ == "__main__":
    main()