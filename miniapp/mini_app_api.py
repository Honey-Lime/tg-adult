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

load_dotenv()

app = FastAPI()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
async def get_saved(user_id: int):
	logger.info(f"get_saved called with user_id={user_id}")
	conn = get_db_connection()
	try:
		with conn.cursor() as cur:
			# Получаем сохранённые ID пользователя
			cur.execute("SELECT saved_images FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if not row or not row['saved_images']:
				logger.info("No saved images")
				return []
			saved_ids = row['saved_images']
			# Запрашиваем картинки и сортируем по value
			cur.execute("""
				SELECT id, path, likes, dislikes, value, type
				FROM pictures
				WHERE id = ANY(%s)
				ORDER BY value DESC
			""", (saved_ids,))
			images = cur.fetchall()
			logger.info(f"Found {len(images)} saved images")
			return images
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

@app.get("/app")
async def serve_app():
	return FileResponse("static/index.html")