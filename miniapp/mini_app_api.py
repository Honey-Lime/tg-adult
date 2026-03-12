from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import time
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Раздача статических файлов (фронтенд)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
async def get_top(type: int):
    """
    Возвращает топ-25 изображений указанного типа (0 - аниме, 1 - реальные).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, path, likes, dislikes, value, type
                FROM pictures
                WHERE type = %s
                ORDER BY value DESC
                LIMIT 25
            """, (type,))
            images = cur.fetchall()
            return images
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/saved")
@cached_with_ttl(ttl=10)
async def get_saved(user_id: int):
	conn = get_db_connection()
	try:
		with conn.cursor() as cur:
			# Получаем сохранённые ID пользователя
			cur.execute("SELECT saved_images FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if not row or not row['saved_images']:
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
			return images
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))
	finally:
		conn.close()

@app.get("/app")
async def serve_app():
	return FileResponse("static/index.html")