from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import time
from functools import lru_cache, wraps
from dotenv import load_dotenv
import sys
from pathlib import Path
import subprocess
import tempfile
import hashlib

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

app = FastAPI()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверка наличия ffmpeg при старте
def check_ffmpeg():
    """Проверяет наличие ffmpeg в системе."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info("ffmpeg найден: " + result.stdout.split('\n')[0])
            return True
        else:
            logger.warning("ffmpeg не найден. Превью видео не будут генерироваться.")
            return False
    except FileNotFoundError:
        logger.warning("ffmpeg не найден в PATH. Превью видео не будут генерироваться.")
        logger.warning("Установите ffmpeg: https://ffmpeg.org/download.html")
        return False
    except Exception as e:
        logger.warning(f"Ошибка проверки ffmpeg: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Проверка ffmpeg при запуске приложения."""
    check_ffmpeg()

# Обработчик ошибок валидации
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error for request {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Раздача статических файлов (фронтенд)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Раздача изображений
app.mount("/images", StaticFiles(directory="../bot/images"), name="images")

# Раздача видео
app.mount("/videos", StaticFiles(directory="../bot/images/videos"), name="videos")

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_db_connection():
	return psycopg2.connect(
		host=DB_HOST,
		database=DB_NAME,
		user=DB_USER,
		password=DB_PASSWORD,
		cursor_factory=RealDictCursor
	)

# Простой кэш с TTL
_cache = {}
_CACHE_TTL = 30  # секунды

def clear_saved_cache(user_id: int):
    """Очищает кэш для конкретного пользователя."""
    keys_to_delete = [
        key for key in _cache.keys()
        if key[0] == 'get_saved' and len(key[1]) > 0 and key[1][0] == user_id
    ]
    for key in keys_to_delete:
        del _cache[key]
    logger.info(f"Cleared saved cache for user_id={user_id}, cleared {len(keys_to_delete)} keys")

def cached_with_ttl(ttl):
    """Декоратор для кэширования результата функции с TTL."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = (func.__name__, args, tuple(kwargs.items()))
            now = time.time()
            if key in _cache:
                value, timestamp = _cache[key]
                if now - timestamp < ttl:
                    return value
            # Выполняем функцию
            result = await func(*args, **kwargs)
            _cache[key] = (result, now)
            return result
        return wrapper
    return decorator

@app.get("/api/top")
@cached_with_ttl(ttl=30)
async def get_top(image_type: int = Query(..., alias="type")):
    """
    Возвращает топ-25 изображений указанного типа (0 - аниме, 1 - реальные).
    """
    logger.info(f"get_top called with type={image_type}")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, path, likes, dislikes, value, type
                FROM pictures
                WHERE type = %s
                ORDER BY value DESC
                LIMIT 25
            """, (image_type,))
            images = cur.fetchall()
            logger.info(f"Found {len(images)} images")
            return images
    except Exception as e:
        logger.error(f"Error in get_top: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/saved")
@cached_with_ttl(ttl=10)
async def get_saved(user_id: int, sort: str = "newest", order: str = "desc", filter: str = "all"):
	"""
	Возвращает сохранённые изображения и видео пользователя.
	Параметры:
	- sort: "rating" (по оценкам) или "newest" (по новизне, по умолчанию)
	- order: "asc" (возрастание) или "desc" (убывание, по умолчанию)
	- filter: "all" (все), "photo" (только фото), "video" (только видео)
	"""
	logger.info(f"get_saved called with user_id={user_id}, sort={sort}, order={order}, filter={filter}")
	conn = get_db_connection()
	try:
		with conn.cursor() as cur:
			# Получаем сохранённые ID пользователя
			cur.execute("SELECT saved_images, saved_videos FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if not row:
				logger.info("User not found")
				return []
			
			saved_images_ids = row['saved_images'] or []
			saved_videos_ids = row['saved_videos'] or []
			
			# Определяем порядок сортировки
			order_direction = "ASC" if order == "asc" else "DESC"
			
			# Определяем поле и порядок сортировки
			if sort == "rating":
				order_field = "value"
			else:  # newest по умолчанию
				order_field = "id"
			
			results = []
			
			# Получаем фото
			if filter in ["all", "photo"] and saved_images_ids:
				if sort == "newest":
					# При сортировке по новизне используем порядок в массиве saved_images
					# Последние добавленные (в конце массива) должны быть первыми
					photo_results = []
					for img_id in reversed(saved_images_ids):
						cur.execute("""
							SELECT id, path, likes, dislikes, value, type, 'photo' as media_type
							FROM pictures
							WHERE id = %s
						""", (img_id,))
						row = cur.fetchone()
						if row:
							photo_results.append(row)
					results.extend(photo_results)
				else:
					query = f"""
						SELECT id, path, likes, dislikes, value, type, 'photo' as media_type
						FROM pictures
						WHERE id = ANY(%s)
						ORDER BY {order_field} {order_direction}
					"""
					cur.execute(query, (saved_images_ids,))
					results.extend(cur.fetchall())
			
			# Получаем видео
			if filter in ["all", "video"] and saved_videos_ids:
				if sort == "newest":
					# При сортировке по новизне используем порядок в массиве saved_videos
					# Последние добавленные (в конце массива) должны быть первыми
					video_results = []
					for vid_id in reversed(saved_videos_ids):
						cur.execute("""
							SELECT id, path, likes, dislikes, value, 'video' as media_type
							FROM videos
							WHERE id = %s
						""", (vid_id,))
						row = cur.fetchone()
						if row:
							video_results.append(row)
					# Если фильтр "all", объединяем с фото в порядке добавления
					if filter == "all":
						# results уже содержит фото в порядке "последние добавленные первыми"
						# video_results содержит видео в порядке "последние добавленные первыми"
						# Нужно объединить их в общий порядок по времени добавления
						# Но мы не знаем точный порядок между фото и видео
						# Простое решение: просто объединяем, фото идут первыми, затем видео
						results.extend(video_results)
					else:
						results.extend(video_results)
				else:
					query = f"""
						SELECT id, path, likes, dislikes, value, 'video' as media_type
						FROM videos
						WHERE id = ANY(%s)
						ORDER BY {order_field} {order_direction}
					"""
					cur.execute(query, (saved_videos_ids,))
					results.extend(cur.fetchall())
			
			logger.info(f"Found {len(results)} saved items with sort={sort}, order={order}, filter={filter}")
			return results
	except Exception as e:
		logger.error(f"Error in get_saved: {e}")
		raise HTTPException(status_code=500, detail=str(e))
	finally:
		conn.close()

@app.get("/api/liked_videos")
@cached_with_ttl(ttl=10)
async def get_liked_videos(user_id: int):
	logger.info(f"get_liked_videos called with user_id={user_id}")
	conn = get_db_connection()
	try:
		with conn.cursor() as cur:
			# Получаем ID лайкнутых видео пользователя
			cur.execute("SELECT liked_videos FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if not row or not row['liked_videos']:
				logger.info("No liked videos")
				return []
			liked_video_ids = row['liked_videos']
			# Запрашиваем видео и сортируем по value
			cur.execute("""
				SELECT id, path, likes, dislikes, value, 0 as type
				FROM videos
				WHERE id = ANY(%s)
				ORDER BY value DESC
			""", (liked_video_ids,))
			videos = cur.fetchall()
			logger.info(f"Found {len(videos)} liked videos")
			return videos
	except Exception as e:
		logger.error(f"Error in get_liked_videos: {e}")
		raise HTTPException(status_code=500, detail=str(e))
	finally:
		conn.close()

@app.post("/api/save_video")
async def save_video(user_id: int, video_id: int):
	"""
	Сохраняет видео: добавляет в saved_videos и liked_videos, списывает 50 монет.
	"""
	logger.info(f"save_video called with user_id={user_id}, video_id={video_id}")
	try:
		from bot.database import video_save
		success = video_save(user_id, video_id)
		if success:
			logger.info(f"Video {video_id} saved successfully for user {user_id}")
			# Очищаем кэш сохранённых для пользователя
			clear_saved_cache(user_id)
			return {"status": "success"}
		else:
			logger.warning(f"Failed to save video {video_id} for user {user_id} (insufficient coins or already saved)")
			raise HTTPException(status_code=400, detail="Недостаточно монет или видео уже сохранено")
	except ImportError as e:
		logger.error(f"Failed to import video_save: {e}")
		raise HTTPException(status_code=500, detail="Ошибка иморта функции сохранения")
	except Exception as e:
		logger.error(f"Error in save_video: {e}")
		raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clear_cache")
async def clear_cache(user_id: int):
	"""
	Очищает кэш сохранённых изображений для пользователя.
	Вызывается из бота после сохранения изображения.
	"""
	logger.info(f"clear_cache called with user_id={user_id}")
	clear_saved_cache(user_id)
	return {"status": "success"}

@app.get("/app")
async def serve_app():
	return FileResponse("static/index.html")

@app.get("/api/video_thumbnail")
async def get_video_thumbnail(video_path: str = Query(...)):
	"""
	Генерирует превью (первый кадр) для видео.
	Возвращает JPEG изображение.
	"""
	logger.info(f"get_video_thumbnail called with path={video_path}")
	
	# Полный путь к видео
	video_full_path = os.path.join("../bot/images/videos", video_path)
	
	if not os.path.isfile(video_full_path):
		logger.error(f"Video file not found: {video_full_path}")
		raise HTTPException(status_code=404, detail="Video file not found")
	
	# Генерируем уникальное имя для превью на основе пути к видео
	cache_key = hashlib.md5(video_path.encode()).hexdigest()
	thumbnail_dir = "../bot/images/video_thumbnails"
	os.makedirs(thumbnail_dir, exist_ok=True)
	thumbnail_path = os.path.join(thumbnail_dir, f"{cache_key}.jpg")
	
	# Если превью уже есть в кэше, возвращаем его
	if os.path.isfile(thumbnail_path):
		logger.info(f"Returning cached thumbnail: {thumbnail_path}")
		return FileResponse(thumbnail_path, media_type="image/jpeg")
	
	# Генерируем превью с помощью ffmpeg
	try:
		# Создаем временный файл для превью
		temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
		os.close(temp_fd)
		
		# Команда ffmpeg для создания скриншота первого кадра
		cmd = [
			"ffmpeg",
			"-i", video_full_path,
			"-vf", "select=eq(n\\,0)",
			"-vframes", "1",
			"-q:v", "2",
			temp_path,
			"-y"  # Перезаписать если существует
		]
		
		logger.info(f"Running ffmpeg: {' '.join(cmd)}")
		result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
		
		if result.returncode != 0:
			logger.error(f"ffmpeg error: {result.stderr}")
			raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
		
		# Проверяем, что файл создан
		if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
			logger.error(f"Thumbnail file not created or empty: {temp_path}")
			raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
		
		# Копируем превью в кэш
		import shutil
		shutil.copy2(temp_path, thumbnail_path)
		
		# Удаляем временный файл
		os.remove(temp_path)
		
		logger.info(f"Thumbnail generated: {thumbnail_path}")
		return FileResponse(thumbnail_path, media_type="image/jpeg")
		
	except subprocess.TimeoutExpired:
		logger.error("ffmpeg timeout")
		raise HTTPException(status_code=500, detail="Thumbnail generation timeout")
	except Exception as e:
		logger.error(f"Error generating thumbnail: {e}")
		raise HTTPException(status_code=500, detail=str(e))