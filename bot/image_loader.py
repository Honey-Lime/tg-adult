
import os
import logging
import shutil
import time
import json
from pathlib import Path
import database

# Пути к папкам (относительно расположения скрипта)
SCRIPT_DIR = Path(__file__).parent
NEW_DIR = SCRIPT_DIR / 'images' / 'new'
NEW_ANIME_DIR = NEW_DIR / 'anime'
NEW_REAL_DIR = NEW_DIR / 'real'
NEW_VIDEOS_DIR = NEW_DIR / 'videos'
IMPORT_JSON_PATH = NEW_DIR / 'import.json'

TARGET_ANIME_DIR = SCRIPT_DIR / 'images' / 'anime'
TARGET_REAL_DIR = SCRIPT_DIR / 'images' / 'real'
TARGET_VIDEOS_DIR = SCRIPT_DIR / 'images' / 'videos'


def move_file(src_path, dest_dir, filename):
    """
    Перемещает файл из src_path в dest_dir с именем filename.
    Если файл с таким именем уже существует, добавляет суффикс _1, _2 и т.д.
    Возвращает новое имя файла (может быть изменено из-за конфликта).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    if dest_path.exists():
        base, ext = os.path.splitext(filename)
        counter = 1
        while dest_path.exists():
            new_filename = f"{base}_{counter}{ext}"
            dest_path = dest_dir / new_filename
            counter += 1
        logging.info(f"Файл {filename} уже существует, переименовываем в {dest_path.name}")
    try:
        shutil.move(str(src_path), str(dest_path))
        logging.debug(f"Перемещён {src_path} -> {dest_path}")
        return dest_path.name
    except Exception as e:
        logging.error(f"Ошибка при перемещении {src_path} в {dest_dir}: {e}")
        raise


def load_from_import_json():
    """
    Загружает контент из import.json, добавляет фото и видео в БД,
    перемещает файлы в целевые папки.
    Возвращает кортеж
    (photos_added, videos_added, skipped_duplicate_photos, skipped_duplicate_videos, errors).
    """
    start_time = time.time()
    logging.info("Начало загрузки контента из import.json...")

    if not IMPORT_JSON_PATH.exists():
        logging.warning(f"Файл {IMPORT_JSON_PATH} не найден, пропускаем.")
        return 0, 0, 0, 0, 0

    try:
        with open(IMPORT_JSON_PATH, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения {IMPORT_JSON_PATH}: {e}")
        return 0, 0, 0, 0, 1

    photos_added = 0
    videos_added = 0
    skipped_duplicate_photos = 0
    skipped_duplicate_videos = 0
    errors = 0

    # Создаём целевые папки, если их нет
    TARGET_ANIME_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_REAL_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    for date_str, entry in import_data.items():
        # Проверяем, что entry - это словарь
        if not isinstance(entry, dict):
            logging.warning(f"Неверный формат записи для даты {date_str}: ожидается dict, получено {type(entry)}, пропускаем.")
            errors += 1
            continue
        
        pictures = entry.get('pictures', [])
        videos = entry.get('videos', [])

        # Нормализуем пути: заменяем обратные слеши на прямые
        pictures = [p.replace('\\', '/') for p in pictures]
        videos = [v.replace('\\', '/') for v in videos]

        # Определяем тип по первому фото (если есть)
        pic_type = None
        if pictures:
            # Пример пути: "anime/photo_1@...jpg" или "real/photo_..."
            first_pic = pictures[0]
            if first_pic.startswith('anime/'):
                pic_type = database.ImageType.ANIME.value
            elif first_pic.startswith('real/'):
                pic_type = database.ImageType.REAL.value
            else:
                logging.warning(f"Не удалось определить тип для даты {date_str} по пути {first_pic}, пропускаем.")
                errors += len(pictures) + len(videos)
                continue

        # Если есть фото, ищем или создаём пост
        post_id = None
        if pictures:
            # Проверяем, есть ли уже пост с такой датой и типом
            existing_post = database.get_post_by_date_and_type(date_str, pic_type)
            if existing_post:
                post_id = existing_post
                logging.info(f"Найден существующий пост {post_id} для даты {date_str}, типа {pic_type}")
            else:
                post_id = database.add_post_record(pic_type, date_str)
                if not post_id:
                    logging.error(f"Не удалось создать пост для даты {date_str}, пропускаем.")
                    errors += len(pictures) + len(videos)
                    continue
                logging.info(f"Создан новый пост {post_id} для даты {date_str}, типа {pic_type}")

        # Обрабатываем фото
        for pic_rel_path in pictures:
            # Определяем тип из пути (на всякий случай)
            if pic_rel_path.startswith('anime/'):
                pic_type = database.ImageType.ANIME.value
                target_dir = TARGET_ANIME_DIR
                src_dir = NEW_ANIME_DIR
            elif pic_rel_path.startswith('real/'):
                pic_type = database.ImageType.REAL.value
                target_dir = TARGET_REAL_DIR
                src_dir = NEW_REAL_DIR
            else:
                logging.warning(f"Неизвестный путь фото: {pic_rel_path}, пропускаем.")
                errors += 1
                continue

            filename = Path(pic_rel_path).name
            if database.picture_exists_by_path(filename):
                logging.info(f"Фото {filename} уже есть в БД, пропускаем повторную загрузку.")
                skipped_duplicate_photos += 1
                continue

            src_path = src_dir / filename
            if not src_path.exists():
                # Возможно файл лежит прямо в new? Проверим NEW_DIR
                src_path = NEW_DIR / pic_rel_path
                if not src_path.exists():
                    logging.error(f"Файл фото не найден: {src_path}, пропускаем.")
                    errors += 1
                    continue

            # Добавляем запись в БД
            picture_id = database.add_picture_record(pic_type, post_id, filename)
            if not picture_id:
                logging.error(f"Не удалось добавить фото {filename} в БД, пропускаем.")
                errors += 1
                continue

            # Перемещаем файл
            try:
                new_filename = move_file(src_path, target_dir, filename)
                if new_filename != filename:
                    if database.update_picture_path(picture_id, new_filename):
                        logging.info(f"Обновлён путь фото {picture_id} на {new_filename}")
                    else:
                        logging.error(f"Не удалось обновить путь фото {picture_id}")
                photos_added += 1
            except Exception as e:
                logging.error(f"Ошибка перемещения фото {filename}: {e}")
                database.delete_image(picture_id)
                errors += 1

        # Обрабатываем видео
        if videos:
            # Если пост ещё не создан (нет фото), создаём пост с типом 777
            if not post_id:
                # Создаём пост для видео (тип 777 = видео без фото)
                post_id = database.add_post_record(777, date_str)
                if not post_id:
                    logging.error(f"Не удалось создать пост для даты {date_str}, пропускаем.")
                    errors += len(videos)
                    continue
                logging.info(f"Создан новый пост {post_id} для даты {date_str} (только видео)")
            else:
                # Устанавливаем have_video = TRUE для поста, если есть фото
                if not database.update_post_have_video(post_id):
                    logging.warning(f"Не удалось установить have_video для поста {post_id}")

            for video_rel_path in videos:
                # Видео могут быть в папке videos, anime, real или прямо в new
                filename = Path(video_rel_path).name
                if database.video_exists_by_path(filename):
                    logging.info(f"Видео {filename} уже есть в БД, пропускаем повторную загрузку.")
                    skipped_duplicate_videos += 1
                    continue

                src_path = NEW_VIDEOS_DIR / filename
                if not src_path.exists():
                    src_path = NEW_DIR / video_rel_path
                    if not src_path.exists():
                        # Проверяем в подпапках anime и real
                        if video_rel_path.startswith('anime/'):
                            src_path = NEW_ANIME_DIR / filename
                        elif video_rel_path.startswith('real/'):
                            src_path = NEW_REAL_DIR / filename
                        if not src_path.exists():
                            logging.error(f"Файл видео не найден: {video_rel_path}, пропускаем.")
                            errors += 1
                            continue

                # Добавляем запись видео в БД
                video_id = database.add_video_record(post_id, filename)
                if not video_id:
                    logging.error(f"Не удалось добавить видео {filename} в БД, пропускаем.")
                    errors += 1
                    continue

                # Перемещаем файл
                try:
                    new_filename = move_file(src_path, TARGET_VIDEOS_DIR, filename)
                    # Если имя изменилось, обновляем путь в БД
                    if new_filename != filename:
                        if database.update_video_path(video_id, new_filename):
                            logging.info(f"Обновлён путь видео {video_id} на {new_filename}")
                        else:
                            logging.error(f"Не удалось обновить путь видео {video_id}")
                    videos_added += 1
                except Exception as e:
                    logging.error(f"Ошибка перемещения видео {filename}: {e}")
                    # Удаляем запись видео из БД
                    database.delete_video(video_id)
                    errors += 1

    elapsed = time.time() - start_time
    logging.info(
        f"Загрузка из import.json завершена за {elapsed:.2f} сек. "
        f"Добавлено фото: {photos_added}, видео: {videos_added}, "
        f"пропущено дублей фото: {skipped_duplicate_photos}, видео: {skipped_duplicate_videos}, ошибок: {errors}"
    )
    return photos_added, videos_added, skipped_duplicate_photos, skipped_duplicate_videos, errors


def clear_import_folder():
    """
    Очищает папку new (IMPORT_DIR) и возвращает статистику удаленных файлов.
    Возвращает кортеж (files_count, folders_count) - количество удаленных файлов и папок.
    """
    files_count = 0
    folders_count = 0
    
    if not NEW_DIR.exists():
        logging.warning(f"Папка {NEW_DIR} не существует.")
        return 0, 0
    
    try:
        for item in NEW_DIR.iterdir():
            if item.is_file():
                item.unlink()
                files_count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                folders_count += 1
        logging.info(f"Папка {NEW_DIR} очищена. Удалено файлов: {files_count}, папок: {folders_count}")
    except Exception as e:
        logging.error(f"Ошибка при очистке папки new: {e}")
        raise
    
    return files_count, folders_count
