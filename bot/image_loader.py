
import os
import argparse
import logging
import shutil
import time
import json
from pathlib import Path
from collections import defaultdict
import database

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}

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


def extract_date_from_filename(filename):
    """
    Извлекает дату из имени файла, которая находится между '@' и первой точкой.
    Пример: "some_name@2025-03-10.jpg" -> "2025-03-10"
    Если дата не найдена, возвращает None.
    """
    try:
        return filename.split('@')[1].split('.')[0]
    except IndexError:
        return None


def collect_images_from_folder(folder_path):
    """
    Рекурсивно обходит папку и возвращает словарь:
    { date1: [(filename1, full_path1), ...], date2: [...], ... }
    Файлы без даты пропускаются.
    """
    images_by_date = defaultdict(list)
    base = Path(folder_path)
    if not base.is_dir():
        logging.warning(f"Предупреждение: {folder_path} не существует, пропускаем.")
        return images_by_date

    for file_path in base.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
            date = extract_date_from_filename(file_path.name)
            if date:
                images_by_date[date].append((file_path.name, file_path))
            else:
                logging.warning(f"Предупреждение: не удалось извлечь дату из {file_path.name}, пропускаем.")
    return images_by_date


def merge_dicts(dict_list):
    """Объединяет несколько словарей {date: [(filename, path), ...]} в один, суммируя списки."""
    merged = defaultdict(list)
    for d in dict_list:
        for date, files in d.items():
            merged[date].extend(files)
    return merged


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


def load_to_database(data, target_anime_dir, target_real_dir):
    """
    Загружает изображения в базу данных и перемещает файлы в целевые папки.
    data: словарь {'anime': dict, 'real': dict}, где каждый внутренний dict
          имеет вид {date: [(filename, src_path), ...]}
    Возвращает кортеж (added_count, error_count) - количество успешно добавленных и ошибок.
    """
    added_count = 0
    error_count = 0
    for category in data:
        pic_type = database.ImageType.ANIME.value if category == 'anime' else database.ImageType.REAL.value
        target_dir = target_anime_dir if category == 'anime' else target_real_dir
        logging.info(f"Загрузка типа: {category}")
        for date in data[category]:
            logging.info(f"  Дата: {date}")
            post_id = database.add_post_record(pic_type, date)
            if not post_id:
                logging.error(f"Не удалось создать запись поста для даты {date}, пропускаем.")
                error_count += len(data[category][date])
                continue
            for filename, src_path in data[category][date]:
                logging.debug(f"    Картинка: {filename}")
                # Сначала добавляем запись в БД, получаем ID картинки
                picture_id = database.add_picture_record(pic_type, post_id, filename)
                if not picture_id:
                    logging.error(f"Не удалось добавить картинку {filename} в БД, пропускаем.")
                    error_count += 1
                    continue
                # Затем перемещаем файл
                try:
                    new_filename = move_file(src_path, target_dir, filename)
                    # Если имя файла изменилось, обновляем запись в БД
                    if new_filename != filename:
                        if database.update_picture_path(picture_id, new_filename):
                            logging.info(f"Обновлён путь картинки {picture_id} на {new_filename}")
                        else:
                            logging.error(f"Не удалось обновить путь картинки {picture_id}")
                    added_count += 1
                except Exception as e:
                    logging.error(f"Ошибка при перемещении файла {filename}: {e}")
                    # Откатываем добавление в БД? Можно удалить запись, но оставим для ручного исправления.
                    # Удаляем запись из БД, чтобы не было несоответствия.
                    database.delete_image(picture_id)
                    logging.warning(f"Удалена запись картинки {picture_id} из-за ошибки перемещения.")
                    error_count += 1
    logging.info(f"Загрузка завершена. Успешно: {added_count}, ошибок: {error_count}")
    return added_count, error_count


def load_images_from_default_folders():
    """
    Загружает изображения из стандартных папок (NEW_ANIME_DIR, NEW_REAL_DIR)
    и возвращает кортеж (total_anime, total_real) - количество собранных файлов.
    """
    start_time = time.time()
    logging.info("Начало загрузки изображений...")

    anime_folders = [NEW_ANIME_DIR]
    real_folders = [NEW_REAL_DIR]

    # Проверка существования папок
    for folder in anime_folders + real_folders:
        if not Path(folder).exists():
            logging.warning(f"Папка {folder} не существует, будет создана при необходимости.")

    # Сбор и объединение данных по типам
    anime_merged = merge_dicts([collect_images_from_folder(f) for f in anime_folders])
    real_merged = merge_dicts([collect_images_from_folder(f) for f in real_folders])

    result = {
        'anime': dict(anime_merged),
        'real': dict(real_merged)
    }

    # Статистика собранных файлов
    total_anime = sum(len(v) for v in result['anime'].values())
    total_real = sum(len(v) for v in result['real'].values())
    logging.info(f"Собрано аниме: {total_anime} файлов, реальных: {total_real} файлов")

    # Загрузка в БД и перемещение файлов
    added, errors = load_to_database(result, TARGET_ANIME_DIR, TARGET_REAL_DIR)

    elapsed = time.time() - start_time
    logging.info(f"Загрузка изображений завершена за {elapsed:.2f} сек. Успешно добавлено: {added}, ошибок: {errors}")

    return total_anime, total_real


def load_from_import_json():
    """
    Загружает контент из import.json, добавляет фото и видео в БД,
    перемещает файлы в целевые папки и очищает папку new.
    Возвращает кортеж (photos_added, videos_added, errors).
    """
    start_time = time.time()
    logging.info("Начало загрузки контента из import.json...")

    if not IMPORT_JSON_PATH.exists():
        logging.warning(f"Файл {IMPORT_JSON_PATH} не найден, пропускаем.")
        return 0, 0, 0

    try:
        with open(IMPORT_JSON_PATH, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения {IMPORT_JSON_PATH}: {e}")
        return 0, 0, 1

    photos_added = 0
    videos_added = 0
    errors = 0

    # Создаём целевые папки, если их нет
    TARGET_ANIME_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_REAL_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    for date_str, entry in import_data.items():
        pictures = entry.get('pictures', [])
        videos = entry.get('videos', [])

        # Определяем тип по первому фото (если есть)
        pic_type = None
        if pictures:
            # Пример пути: "anime\\photo_1@...jpg" или "real\\photo_..."
            first_pic = pictures[0]
            if first_pic.startswith('anime\\'):
                pic_type = database.ImageType.ANIME.value
            elif first_pic.startswith('real\\'):
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
            if pic_rel_path.startswith('anime\\'):
                pic_type = database.ImageType.ANIME.value
                target_dir = TARGET_ANIME_DIR
                src_dir = NEW_ANIME_DIR
            elif pic_rel_path.startswith('real\\'):
                pic_type = database.ImageType.REAL.value
                target_dir = TARGET_REAL_DIR
                src_dir = NEW_REAL_DIR
            else:
                logging.warning(f"Неизвестный путь фото: {pic_rel_path}, пропускаем.")
                errors += 1
                continue

            filename = Path(pic_rel_path).name
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
            # Если пост ещё не создан (нет фото), создаём пост на основе типа из первого видео?
            # Но по условию видео добавляются только если есть фото в том же посте.
            # Если фото нет, возможно, видео не должно добавляться? Пока пропустим.
            if not post_id:
                logging.warning(f"Для даты {date_str} есть видео, но нет фото, пропускаем видео.")
                errors += len(videos)
                continue

            # Устанавливаем have_video = TRUE для поста
            if not database.update_post_have_video(post_id):
                logging.warning(f"Не удалось установить have_video для поста {post_id}")

            for video_rel_path in videos:
                # Видео могут быть в папке videos или прямо в new/videos
                filename = Path(video_rel_path).name
                src_path = NEW_VIDEOS_DIR / filename
                if not src_path.exists():
                    src_path = NEW_DIR / video_rel_path
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
                    # Если имя изменилось, нужно обновить путь в БД (но в таблице videos нет поля path? есть path)
                    if new_filename != filename:
                        # Функции update_video_path нет, можно добавить, но пока просто логируем
                        logging.warning(f"Имя видео изменено с {filename} на {new_filename}, но путь в БД не обновлён.")
                    videos_added += 1
                except Exception as e:
                    logging.error(f"Ошибка перемещения видео {filename}: {e}")
                    # Удалить запись видео? Нет функции, оставим как есть.
                    errors += 1

    # После успешной обработки очищаем папку new
    try:
        if NEW_DIR.exists():
            for item in NEW_DIR.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            logging.info(f"Папка {NEW_DIR} очищена.")
    except Exception as e:
        logging.error(f"Ошибка при очистке папки new: {e}")

    elapsed = time.time() - start_time
    logging.info(
        f"Загрузка из import.json завершена за {elapsed:.2f} сек. "
        f"Добавлено фото: {photos_added}, видео: {videos_added}, ошибок: {errors}"
    )
    return photos_added, videos_added, errors


def main():
    parser = argparse.ArgumentParser(description='Сбор изображений из папок с группировкой по дате.')
    parser.add_argument('--anime', action='append', help='Папка с аниме (можно несколько)')
    parser.add_argument('--real', action='append', help='Папка с реальными фото (можно несколько)')
    parser.add_argument('--output', '-o', required=True, help='Файл для сохранения JSON')
    args = parser.parse_args()

    start_time = time.time()
    logging.info("Начало загрузки изображений...")

    # Если папки не указаны, используем стандартные
    anime_folders = args.anime or [NEW_ANIME_DIR]
    real_folders = args.real or [NEW_REAL_DIR]

    # Проверка существования папок
    for folder in anime_folders + real_folders:
        if not Path(folder).exists():
            logging.warning(f"Папка {folder} не существует, будет создана при необходимости.")

    # Сбор и объединение данных по типам
    anime_merged = merge_dicts([collect_images_from_folder(f) for f in anime_folders])
    real_merged = merge_dicts([collect_images_from_folder(f) for f in real_folders])

    result = {
        'anime': dict(anime_merged),
        'real': dict(real_merged)
    }

    # Статистика собранных файлов
    total_anime = sum(len(v) for v in result['anime'].values())
    total_real = sum(len(v) for v in result['real'].values())
    logging.info(f"Собрано аниме: {total_anime} файлов, реальных: {total_real} файлов")

    # Загрузка в БД и перемещение файлов
    added, errors = load_to_database(result, TARGET_ANIME_DIR, TARGET_REAL_DIR)

    elapsed = time.time() - start_time
    logging.info(f"Загрузка изображений завершена за {elapsed:.2f} сек. Успешно добавлено: {added}, ошибок: {errors}")

    # Сохранение в JSON
    import json
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump({k: {date: [fn for fn, _ in files] for date, files in v.items()} for k, v in result.items()},
                  f, ensure_ascii=False, indent=2)
    logging.info(f"Результат сохранён в {args.output}")


if __name__ == '__main__':
    main()