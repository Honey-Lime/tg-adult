# database.py
import psycopg2
import logging
from psycopg2 import pool
from psycopg2 import sql
from config_reader import config
import os
import shutil

from enum import Enum


class ImageType(Enum):
  """Типы изображений."""
  ANIME = 0
  REAL = 1


# Базовая директория проекта (там, где лежит database.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR_ANIME = os.path.join(BASE_DIR, 'images', 'anime')
IMAGE_DIR_REAL = os.path.join(BASE_DIR, 'images', 'real')
VIDEO_DIR = os.path.join(BASE_DIR, 'images', 'videos')

# Создаём пул соединений
try:
	connection_pool = psycopg2.pool.SimpleConnectionPool(
		1,
		10,
		database=config.db_name,
		user=config.db_user,
		password=config.db_password.get_secret_value(),
		host=config.db_host,
		port=config.db_port
	)
	if connection_pool:
		logging.info("Connection pool created successfully")
except Exception as e:
	logging.error(f"Error creating connection pool: {e}")
	connection_pool = None

def get_connection():
	if connection_pool:
		return connection_pool.getconn()
	return None

def return_connection(conn):
	if connection_pool and conn:
		connection_pool.putconn(conn)

def close_all_connections():
	if connection_pool:
		connection_pool.closeall()


def add_post_record(pic_type, date):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				INSERT INTO posts (type, date)
				VALUES (%s, %s)
				RETURNING id
			""", (pic_type, date))
			post_id = cur.fetchone()[0]
			conn.commit()
			return post_id
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)

def add_picture_record(pic_type, post_id, filename):
	"""
	Добавляет запись о картинке и возвращает её ID при успехе, иначе False.
	"""
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				INSERT INTO pictures (type, post_id, path)
				VALUES (%s, %s, %s)
				RETURNING id
			""", (pic_type, post_id, filename))
			picture_id = cur.fetchone()[0]
			conn.commit()
			return picture_id
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def update_picture_path(picture_id, new_filename):
	"""
	Обновляет путь (имя файла) для указанной картинки.
	Возвращает True при успехе, False при ошибке.
	"""
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				UPDATE pictures
				SET path = %s
				WHERE id = %s
			""", (new_filename, picture_id))
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error updating picture path: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def add_video_record(post_id, path):
	"""
	Добавляет запись о видео в таблицу videos.
	Возвращает ID видео при успехе, иначе False.
	"""
	if not post_id:
		logging.error(f"add_video_record: Invalid post_id={post_id}")
		return False
	
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			# Проверяем, существует ли пост
			cur.execute("SELECT id FROM posts WHERE id = %s", (post_id,))
			if not cur.fetchone():
				logging.error(f"add_video_record: Post {post_id} does not exist")
				return False
			
			cur.execute("""
				INSERT INTO videos (post_id, path)
				VALUES (%s, %s)
				RETURNING id
			""", (post_id, path))
			video_id = cur.fetchone()[0]
			conn.commit()
			return video_id
	except Exception as e:
		logging.error(f"Error adding video record: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def update_post_have_video(post_id):
	"""
	Устанавливает have_video = TRUE для указанного поста.
	Возвращает True при успехе, False при ошибке.
	"""
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				UPDATE posts
				SET have_video = TRUE
				WHERE id = %s
			""", (post_id,))
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error updating post have_video: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def get_post_by_date_and_type(date, pic_type):
	"""
	Ищет пост по дате и типу.
	Возвращает post_id или None, если не найден.
	"""
	conn = get_connection()
	if not conn:
		return None
	try:
		with conn.cursor() as cur:
			cur.execute("""
				SELECT id FROM posts
				WHERE date = %s AND type = %s
				LIMIT 1
			""", (date, pic_type))
			row = cur.fetchone()
			return row[0] if row else None
	except Exception as e:
		logging.error(f"Error getting post by date and type: {e}")
		return None
	finally:
		return_connection(conn)


def fix_videos_sequence():
	"""
	Исправляет последовательность для поля id в таблице videos.
	Вызывается автоматически при инициализации БД.
	Не удаляет данные, только настраивает автоинкремент.
	"""
	conn = get_connection()
	if not conn:
		return False
	
	try:
		with conn.cursor() as cur:
			# Проверяем, существует ли таблица videos
			cur.execute("""
				SELECT EXISTS (
					SELECT FROM information_schema.tables 
					WHERE table_name = 'videos'
				)
			""")
			if not cur.fetchone()[0]:
				return False  # Таблицы ещё нет
			
			# Проверяем текущую последовательность
			cur.execute("""
				SELECT pg_get_serial_sequence('videos', 'id')
			""")
			seq_name = cur.fetchone()[0]
			
			if not seq_name:
				# Последовательности нет - пересоздаём поле id как SERIAL
				logging.warning("Последовательность videos не найдена. Пересоздание...")
				cur.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_pkey;")
				cur.execute("ALTER TABLE videos DROP COLUMN id;")
				cur.execute("ALTER TABLE videos ADD COLUMN id SERIAL PRIMARY KEY;")
				logging.info("✓ Поле id таблицы videos пересоздано как SERIAL")
				conn.commit()
				return True
			
			# Проверяем, нужно ли исправлять последовательность
			cur.execute("""
				SELECT 
					COALESCE((SELECT MAX(id) FROM videos), 0) as max_id,
					(SELECT COUNT(*) FROM videos) as row_count
			""")
			row = cur.fetchone()
			max_id = row[0]
			row_count = row[1]
			
			if row_count == 0:
				# Таблица пустая - устанавливаем sequence в 1
				cur.execute("SELECT setval(%s, 1, false)", (seq_name,))
				logging.info("✓ Последовательность videos_id_seq установлена в 1 (таблица пустая)")
			else:
				# Проверяем текущее значение последовательности
				cur.execute(f"SELECT last_value, is_called FROM {seq_name}")
				seq_info = cur.fetchone()
				last_value = seq_info[0]
				is_called = seq_info[1]
				
				# Если последовательность уже настроена правильно (last_value >= max_id и is_called=true)
				if is_called and last_value >= max_id:
					logging.debug(f"Последовательность videos_id_seq уже настроена (last={last_value}, max={max_id})")
					return True
				
				# Исправляем последовательность
				cur.execute("SELECT setval(%s, %s, false)", (seq_name, max_id + 1))
				logging.info(f"✓ Последовательность videos_id_seq исправлена (max_id={max_id}, next={max_id + 1})")
			
			conn.commit()
			return True
			
	except Exception as e:
		logging.error(f"Ошибка при исправлении последовательности videos: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def init_db():
	"""Создаёт таблицу message_history, если её нет, и добавляет недостающие столбцы в users."""
	conn = get_connection()
	if not conn:
		return
	try:
		with conn.cursor() as cur:
			# Создание таблицы message_history
			cur.execute("""
				CREATE TABLE IF NOT EXISTS message_history (
					id SERIAL PRIMARY KEY,
					chat_id BIGINT NOT NULL,
					message_id BIGINT NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_message_history_chat_id ON message_history(chat_id);
			""")
			# Добавление столбцов first_name, last_name, username в таблицу users, если их нет
			cur.execute("""
				ALTER TABLE users
				ADD COLUMN IF NOT EXISTS first_name TEXT,
				ADD COLUMN IF NOT EXISTS last_name TEXT,
				ADD COLUMN IF NOT EXISTS username TEXT;
			""")
			# Проверка и добавление столбца language (отдельно, т.к. ADD COLUMN IF NOT EXISTS не работает с DEFAULT в некоторых версиях PostgreSQL)
			cur.execute("""
				SELECT column_name 
				FROM information_schema.columns 
				WHERE table_name = 'users' AND column_name = 'language'
			""")
			if not cur.fetchone():
				cur.execute("""
					ALTER TABLE users
					ADD COLUMN language TEXT DEFAULT 'ru'
				""")
				logging.info("✓ Добавлен столбец language в таблицу users")
			# Проверка и добавление столбца promo_code (рекламная ссылка, по которой зарегистрировался)
			cur.execute("""
				SELECT column_name 
				FROM information_schema.columns 
				WHERE table_name = 'users' AND column_name = 'promo_code'
			""")
			if not cur.fetchone():
				cur.execute("""
					ALTER TABLE users
					ADD COLUMN promo_code TEXT
				""")
				logging.info("✓ Добавлен столбец promo_code в таблицу users")

			# Добавление столбца have_video в таблицу posts, если его нет
			cur.execute("""
				ALTER TABLE posts
				ADD COLUMN IF NOT EXISTS have_video BOOLEAN DEFAULT FALSE;
			""")
			# Создание таблицы videos, если её нет
			cur.execute("""
				CREATE TABLE IF NOT EXISTS videos (
					id SERIAL PRIMARY KEY,
					post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
					path TEXT NOT NULL,
					likes INTEGER DEFAULT 0,
					dislikes INTEGER DEFAULT 0,
					total INTEGER DEFAULT 0,
					value INTEGER DEFAULT 0,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_videos_post_id ON videos(post_id);
			""")
			# Добавление столбцов для видео в таблицу users, если их нет
			cur.execute("""
				ALTER TABLE users
				ADD COLUMN IF NOT EXISTS watched_videos INTEGER[] DEFAULT ARRAY[]::INTEGER[],
				ADD COLUMN IF NOT EXISTS liked_videos INTEGER[] DEFAULT ARRAY[]::INTEGER[],
				ADD COLUMN IF NOT EXISTS saved_videos INTEGER[] DEFAULT ARRAY[]::INTEGER[],
				ADD COLUMN IF NOT EXISTS last_video_time TIMESTAMP;
			""")
			conn.commit()
			logging.info("Database initialization completed (message_history, users columns, have_video, videos, video stats)")
			
			# Инициализация таблиц для рекламных ссылок
			cur.execute("""
				CREATE TABLE IF NOT EXISTS promo_links (
					id SERIAL PRIMARY KEY,
					name TEXT NOT NULL,
					code TEXT UNIQUE NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE TABLE IF NOT EXISTS promo_link_stats (
					id SERIAL PRIMARY KEY,
					promo_link_id INTEGER NOT NULL REFERENCES promo_links(id) ON DELETE CASCADE,
					user_id BIGINT NOT NULL,
					clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_promo_links_code ON promo_links(code);
				CREATE INDEX IF NOT EXISTS idx_promo_link_stats_promo_id ON promo_link_stats(promo_link_id);
			""")
			conn.commit()
			logging.info("Promo links tables initialized")
			
			# Создание таблицы транзакций для хранения истории пополнений
			cur.execute("""
				CREATE TABLE IF NOT EXISTS transactions (
					id SERIAL PRIMARY KEY,
					user_id BIGINT NOT NULL,
					amount INTEGER NOT NULL,
					stars_paid INTEGER NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
			""")
			conn.commit()
			logging.info("Transactions table initialized")
			
			# Создание таблицы для хранения оценок пользователей (лайки/дизлайки)
			cur.execute("""
				CREATE TABLE IF NOT EXISTS user_ratings_log (
					id SERIAL PRIMARY KEY,
					user_id BIGINT NOT NULL,
					image_id INTEGER,
					video_id INTEGER,
					rating_type INTEGER NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_user_ratings_log_user_id ON user_ratings_log(user_id);
				CREATE INDEX IF NOT EXISTS idx_user_ratings_log_created_at ON user_ratings_log(created_at);
			""")
			conn.commit()
			logging.info("User ratings log table initialized")
			
			# Создание таблицы для обратной связи
			cur.execute("""
				CREATE TABLE IF NOT EXISTS feedback_messages (
					id SERIAL PRIMARY KEY,
					user_id BIGINT NOT NULL,
					message TEXT NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				);
				CREATE INDEX IF NOT EXISTS idx_feedback_messages_user_id ON feedback_messages(user_id);
				CREATE INDEX IF NOT EXISTS idx_feedback_messages_created_at ON feedback_messages(created_at);
			""")
			conn.commit()
			logging.info("Feedback messages table initialized")
			
			# Исправление последовательности videos (если проблема с id)
			fix_videos_sequence()
			
	except Exception as e:
		logging.error(f"Error in init_db: {e}")
	finally:
		return_connection(conn)

def add_message_record(chat_id, message_id):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				INSERT INTO message_history (chat_id, message_id)
				VALUES (%s, %s)
			""", (chat_id, message_id))
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)

def delete_message_record(chat_id, message_id):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				DELETE FROM message_history
				WHERE chat_id = %s AND message_id = %s
			""", (chat_id, message_id))
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)

def count_messages(chat_id):
	conn = get_connection()
	if not conn:
		return 0
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT COUNT(*) FROM message_history WHERE chat_id = %s", (chat_id,))
			return cur.fetchone()[0]
	except Exception as e:
		logging.error(f"Error in count_messages: {e}, chat_id={chat_id}")
		return 0
	finally:
		return_connection(conn)

def get_oldest_message(chat_id):
	conn = get_connection()
	if not conn:
		return None
	try:
		with conn.cursor() as cur:
			cur.execute("""
				SELECT message_id FROM message_history
				WHERE chat_id = %s
				ORDER BY created_at ASC
				LIMIT 1
			""", (chat_id,))
			row = cur.fetchone()
			return row[0] if row else None
	except Exception as e:
		logging.error(f"Error : {e}")
		return None
	finally:
		return_connection(conn)

def load_all_message_history():
	"""Загружает всю историю сообщений из БД в виде словаря {chat_id: [message_id, ...]}"""
	conn = get_connection()
	if not conn:
		return {}
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT chat_id, message_id FROM message_history ORDER BY created_at ASC")
			rows = cur.fetchall()
			history = {}
			for chat_id, msg_id in rows:
				history.setdefault(chat_id, []).append(msg_id)
			return history
	except Exception as e:
		logging.error(f"Error in load_all_message_history: {e}")
		return {}
	finally:
		return_connection(conn)


def get_all_users_stats(limit=25):
    """
    Возвращает список пользователей с детальной статистикой,
    отсортированный по убыванию общего кол-ва оценок.
    Каждый элемент: {
        'user_id': int,
        'first_name': str или None,
        'last_name': str или None,
        'username': str или None,
        'viewed_anime_count': int,
        'viewed_real_count': int,
        'viewed_video_count': int,
        'viewed_total': int,
        'today_ratings': int
    }
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,
                       first_name,
                       last_name,
                       username,
                       COALESCE(array_length(viewed_anime, 1), 0) as viewed_anime_count,
                       COALESCE(array_length(viewed_real, 1), 0) as viewed_real_count,
                       COALESCE(array_length(watched_videos, 1), 0) as viewed_video_count,
                       COALESCE(array_length(viewed_anime, 1), 0) +
                       COALESCE(array_length(viewed_real, 1), 0) +
                       COALESCE(array_length(watched_videos, 1), 0) as viewed_total,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM user_ratings_log r
                           WHERE r.user_id = users.id
                             AND r.created_at >= CURRENT_DATE
                       ), 0) as today_ratings
                FROM users
                ORDER BY viewed_total DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'user_id': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'username': row[3],
                    'viewed_anime_count': row[4],
                    'viewed_real_count': row[5],
                    'viewed_video_count': row[6],
                    'viewed_total': row[7],
                    'today_ratings': row[8]
                })
            return result
    except Exception as e:
        logging.error(f"Error in get_all_users_stats: {e}")
        return []
    finally:
        return_connection(conn)


def get_global_users_stats():
    """
    Возвращает агрегированную статистику по всем пользователям.
    {
        'total_users': int,
        'avg_anime': float,
        'avg_real': float,
        'avg_video': float,
        'total_ratings': int,
        'today_ratings': int
    }
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_users,
                    COALESCE(AVG(COALESCE(array_length(viewed_anime, 1), 0)), 0) as avg_anime,
                    COALESCE(AVG(COALESCE(array_length(viewed_real, 1), 0)), 0) as avg_real,
                    COALESCE(AVG(COALESCE(array_length(watched_videos, 1), 0)), 0) as avg_video,
                    COALESCE(SUM(
                        COALESCE(array_length(viewed_anime, 1), 0) +
                        COALESCE(array_length(viewed_real, 1), 0) +
                        COALESCE(array_length(watched_videos, 1), 0)
                    ), 0) as total_ratings,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM user_ratings_log r
                        WHERE r.created_at >= CURRENT_DATE
                    ), 0) as today_ratings
                FROM users
            """)
            row = cur.fetchone()
            if row:
                return {
                    'total_users': row[0],
                    'avg_anime': round(row[1], 1),
                    'avg_real': round(row[2], 1),
                    'avg_video': round(row[3], 1),
                    'total_ratings': row[4],
                    'today_ratings': row[5]
                }
            return None
    except Exception as e:
        logging.error(f"Error in get_global_users_stats: {e}")
        return None
    finally:
        return_connection(conn)


def get_all_user_ids():
    """
    Возвращает список всех ID пользователей (chat_id).
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users ORDER BY id")
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logging.error(f"Error in get_all_user_ids: {e}")
        return []
    finally:
        return_connection(conn)


def get_user(user_id, referrer_id=None):
	"""
	Получает пользователя по id. Если не существует – создаёт.
	Если передан referrer_id и пользователь только что создан, начисляет рефереру 250 монет.
	"""
	conn = get_connection()
	if not conn:
		return None
	try:
		with conn.cursor() as cur:
			# Пытаемся найти пользователя
			cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if row:
				columns = [desc[0] for desc in cur.description]
				return dict(zip(columns, row))

			# Пользователь не найден – вставляем с рефералом или без
			if referrer_id is not None:
				cur.execute("""
					INSERT INTO users (id, referrer_id)
					VALUES (%s, %s)
					ON CONFLICT (id) DO NOTHING
					RETURNING id
				""", (user_id, referrer_id))
			else:
				cur.execute("""
					INSERT INTO users (id)
					VALUES (%s)
					ON CONFLICT (id) DO NOTHING
					RETURNING id
				""", (user_id,))

			inserted = cur.fetchone()
			if inserted and referrer_id is not None:
				# Если вставка произошла и был указан реферер – начисляем монеты
				add_coins(referrer_id, 250)

			# Получаем данные пользователя (теперь он точно есть)
			cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if row:
				columns = [desc[0] for desc in cur.description]
				return dict(zip(columns, row))
			else:
				return None
	except Exception as e:
		logging.error(f"Error in get_user: {e}, user_id={user_id}, referrer_id={referrer_id}")
		conn.rollback()
		return None
	finally:
		return_connection(conn)


def get_or_create_user(user_id, referrer_id=None, language='ru', promo_code=None):
	"""
	Получает пользователя по id. Если не существует – создаёт.
	Если передан referrer_id и реферер существует, начисляет ему 250 монет.
	Если передан promo_code, сохраняет его в профиле пользователя.
	Возвращает кортеж (user_dict, created), где created=True если пользователь только что создан.
	При ошибке возвращает (None, False).
	"""
	conn = get_connection()
	if not conn:
		return None, False
	try:
		with conn.cursor() as cur:
			# Сначала проверяем, существует ли пользователь
			cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
			row = cur.fetchone()
			if row:
				columns = [desc[0] for desc in cur.description]
				logging.debug(f"User found in database")
				return dict(zip(columns, row)), False

			# Пользователь не найден, создаём нового
			# Проверяем существование реферера, если он указан
			valid_referrer = False
			if referrer_id is not None:
				cur.execute("SELECT id FROM users WHERE id = %s", (referrer_id,))
				if cur.fetchone():
					valid_referrer = True
				else:
					logging.warning(f"Referrer {referrer_id} not found, skipping bonus")

			# Проверяем наличие колонки language
			cur.execute("""
				SELECT column_name 
				FROM information_schema.columns 
				WHERE table_name = 'users' AND column_name = 'language'
			""")
			has_language_column = cur.fetchone() is not None

			# Проверяем наличие колонки promo_code
			cur.execute("""
				SELECT column_name 
				FROM information_schema.columns 
				WHERE table_name = 'users' AND column_name = 'promo_code'
			""")
			has_promo_code_column = cur.fetchone() is not None

			# Вставка нового пользователя
			if has_language_column and has_promo_code_column:
				if valid_referrer:
					cur.execute("""
						INSERT INTO users (id, referrer_id, coins, language, promo_code)
						VALUES (%s, %s, 0, %s, %s)
						RETURNING id
					""", (user_id, referrer_id, language, promo_code))
				else:
					cur.execute("""
						INSERT INTO users (id, coins, language, promo_code)
						VALUES (%s, 0, %s, %s)
						RETURNING id
					""", (user_id, language, promo_code))
			elif has_language_column:
				if valid_referrer:
					cur.execute("""
						INSERT INTO users (id, referrer_id, coins, language)
						VALUES (%s, %s, 0, %s)
						RETURNING id
					""", (user_id, referrer_id, language))
				else:
					cur.execute("""
						INSERT INTO users (id, coins, language)
						VALUES (%s, 0, %s)
						RETURNING id
					""", (user_id, language))
			else:
				if valid_referrer:
					cur.execute("""
						INSERT INTO users (id, referrer_id, coins)
						VALUES (%s, %s, 0)
						RETURNING id
					""", (user_id, referrer_id))
				else:
					cur.execute("""
						INSERT INTO users (id, coins)
						VALUES (%s, 0)
						RETURNING id
					""", (user_id,))

			inserted = cur.fetchone()
			if inserted:
				logging.debug(f"New user created with id {user_id}")
				if valid_referrer:
					# Начисляем бонус рефереру
					cur.execute("UPDATE users SET coins = coins + 250 WHERE id = %s", (referrer_id,))
					if cur.rowcount == 0:
						logging.error(f"Failed to add referral bonus to user {referrer_id}")
					else:
						logging.info(f"Referral bonus added to user {referrer_id}")
				conn.commit()
				# Получаем свежесозданного пользователя
				cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
				row = cur.fetchone()
				if row:
					columns = [desc[0] for desc in cur.description]
					return dict(zip(columns, row)), True
				else:
					logging.error(f"Failed to retrieve newly created user {user_id}")
					return None, False
			else:
				# Конкурентная вставка – повторяем поиск
				logging.debug(f"Concurrent insert detected, retrying")
				cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
				row = cur.fetchone()
				if row:
					columns = [desc[0] for desc in cur.description]
					return dict(zip(columns, row)), False
				else:
					return None, False
	except Exception as e:
		logging.error(f"Error in get_or_create_user: {e}")
		conn.rollback()
		return None, False
	finally:
		return_connection(conn)


def user_set_type(user_id, type):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				UPDATE users
				SET type = %s
				WHERE id = %s
			""", (type, user_id))
			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error in user_set_type: {e}, user_id={user_id}, type={type}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def user_set_cycle(user_id, cycle):
	if cycle == 0:
		new_cycle = 1
	else:
		new_cycle = 0
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				UPDATE users
				SET cycle = %s
				WHERE id = %s
			""", (new_cycle, user_id))
			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error in user_set_cycle: {e}, user_id={user_id}, cycle={cycle}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def user_watched_image(user_id, image):
	if image['type'] == ImageType.ANIME.value:
		viewed_name = 'viewed_anime'
	else:
		viewed_name = 'viewed_real'
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			query = sql.SQL("""
				UPDATE users
				SET {} = array_append(coalesce({}, ARRAY[]::integer[]), %s),
					last_watched = %s
				WHERE id = %s
			""").format(
				sql.Identifier(viewed_name),
				sql.Identifier(viewed_name)
			)
			cur.execute(query, (image['id'], image['id'], user_id))
			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error in user_watched_image: {e}, user_id={user_id}, image_id={image['id'] if image else None}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def get_images_for_moderation():
    """Возвращает список изображений, у которых need_moderate = true."""
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pictures WHERE need_moderate = true ORDER BY id")
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            result = [dict(zip(columns, row)) for row in rows]
            return result
    except Exception as e:
        logging.error(f"Error in get_images_for_moderation: {e}")
        return []
    finally:
        return_connection(conn)

def delete_image(image_id):
    """
    Удаляет изображение из базы данных и файл с диска.
    Возвращает True при успехе, False при ошибке.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Получаем тип и путь изображения
            cur.execute("SELECT type, path FROM pictures WHERE id = %s", (image_id,))
            row = cur.fetchone()
            if row:
                img_type, img_path = row
                # Определяем базовую директорию
                base_dir = IMAGE_DIR_ANIME if img_type == ImageType.ANIME.value else IMAGE_DIR_REAL
                full_path = os.path.join(base_dir, img_path)
                # Удаляем файл, если существует
                if os.path.isfile(full_path):
                    try:
                        os.remove(full_path)
                        logging.info(f"Файл изображения удалён: {full_path}")
                    except OSError as e:
                        logging.warning(f"Не удалось удалить файл {full_path}: {e}")
                else:
                    logging.warning(f"Файл изображения не найден: {full_path}")
            # Удаляем запись из базы
            cur.execute("DELETE FROM pictures WHERE id = %s", (image_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка при удалении изображения {image_id}: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)

def move_image_to_correct_folder(image_id, new_type):
    """
    Перемещает файл изображения в папку, соответствующую новому типу.
    Возвращает новый путь (имя файла) при успехе, None при ошибке.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            # Получаем текущий тип и путь изображения
            cur.execute("SELECT type, path FROM pictures WHERE id = %s", (image_id,))
            row = cur.fetchone()
            if not row:
                logging.error(f"Image {image_id} not found in database")
                return None
            current_type, current_path = row
            # Если тип уже совпадает, ничего не делаем
            if current_type == new_type:
                logging.info(f"Image {image_id} already has type {new_type}, no move needed")
                return current_path

            # Определяем исходную и целевую папки
            src_dir = IMAGE_DIR_ANIME if current_type == ImageType.ANIME.value else IMAGE_DIR_REAL
            dst_dir = IMAGE_DIR_ANIME if new_type == ImageType.ANIME.value else IMAGE_DIR_REAL

            # Убедимся, что целевая директория существует
            os.makedirs(dst_dir, exist_ok=True)

            src_path = os.path.join(src_dir, current_path)
            if not os.path.isfile(src_path):
                logging.error(f"Source file not found: {src_path}")
                return None

            # Определяем целевое имя файла (может быть таким же, если нет конфликта)
            dst_filename = current_path
            dst_path = os.path.join(dst_dir, dst_filename)
            counter = 1
            # Если файл уже существует, добавляем суффикс (_1, _2, ...)
            while os.path.exists(dst_path):
                name, ext = os.path.splitext(current_path)
                dst_filename = f"{name}_{counter}{ext}"
                dst_path = os.path.join(dst_dir, dst_filename)
                counter += 1
                if counter > 100:
                    logging.error(f"Too many conflicts for image {image_id}")
                    return None

            # Перемещаем файл
            try:
                shutil.move(src_path, dst_path)
                logging.info(f"Moved image {image_id} from {src_path} to {dst_path}")
            except Exception as e:
                logging.error(f"Failed to move file: {e}")
                return None

            # Если имя файла изменилось, обновляем путь в БД
            if dst_filename != current_path:
                cur.execute("UPDATE pictures SET path = %s WHERE id = %s", (dst_filename, image_id))
                conn.commit()
                logging.info(f"Updated path for image {image_id} to {dst_filename}")
            else:
                conn.commit()
            return dst_filename
    except Exception as e:
        logging.error(f"Error moving image {image_id}: {e}")
        conn.rollback()
        return None
    finally:
        return_connection(conn)


def clear_moderation(image_id):
    """Снимает флаг need_moderate с изображения."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE pictures SET need_moderate = false WHERE id = %s", (image_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in clear_moderation: {e}, image_id={image_id}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def get_good_images(type):
	conn = get_connection()
	if not conn:
		return []
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT * FROM pictures WHERE type = %s and need_moderate = false ORDER BY value DESC OFFSET 25", (type,))
			columns = [desc[0] for desc in cur.description]
			rows = cur.fetchall()
			result = [dict(zip(columns, row)) for row in rows]
			return result
	except Exception as e:
		logging.error(f"Error in get_good_images: {e}, type={type}")
		return []
	finally:
		return_connection(conn)


def get_noname_images(type):
	conn = get_connection()
	if not conn:
		return []
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT * FROM pictures WHERE value > -10 and type = %s and need_moderate = false ORDER BY total ASC", (type,))
			columns = [desc[0] for desc in cur.description]
			rows = cur.fetchall()
			result = [dict(zip(columns, row)) for row in rows]
			return result
	except Exception as e:
		logging.error(f"Error in get_noname_images: {e}, type={type}")
		return []
	finally:
		return_connection(conn)


def get_not_real_type(image_id):
	"""Возвращает текущее значение поля not_real_type для изображения."""
	conn = get_connection()
	if not conn:
		return None
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT not_real_type FROM pictures WHERE id = %s", (image_id,))
			row = cur.fetchone()
			return row[0] if row else None
	except Exception as e:
		logging.error(f"Error in get_not_real_type: {e}, image_id={image_id}")
		return None
	finally:
		return_connection(conn)


def set_not_real_type(image_id, value):
	"""Устанавливает not_real_type = value для указанного изображения."""
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("UPDATE pictures SET not_real_type = %s WHERE id = %s", (value, image_id))
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error in set_not_real_type: {e}, image_id={image_id}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def toggle_type(user_id):
	"""
	Переключает тип текущего изображения и сбрасывает not_real_type в false.
	Перемещает файл в соответствующую папку.
	Возвращает сообщение для пользователя.
	"""
	user = get_user(user_id)
	if not user:
		return "Пользователь не найден"
	image_id = user.get('last_watched')
	if not image_id:
		return "Нет текущего изображения"
	conn = get_connection()
	if not conn:
		return "Ошибка подключения"
	try:
		with conn.cursor() as cur:
			# Получаем текущий тип изображения
			cur.execute("SELECT type FROM pictures WHERE id = %s", (image_id,))
			row = cur.fetchone()
			if not row:
				return "Изображение не найдено"
			current_type = row[0]
			# Определяем новый тип с помощью Enum
			if current_type == ImageType.ANIME.value:
				new_type = ImageType.REAL.value
			else:
				new_type = ImageType.ANIME.value

			# Перемещаем файл в соответствующую папку
			new_path = move_image_to_correct_folder(image_id, new_type)
			if new_path is None:
				logging.error(f"Failed to move file for image {image_id}")
				# Можно продолжить, но лучше откатить?
				# Пока просто продолжим, но файл останется в старой папке

			# Обновляем тип и сбрасываем not_real_type
			cur.execute("""
				UPDATE pictures
				SET type = %s,
					not_real_type = false
				WHERE id = %s
			""", (new_type, image_id))
			conn.commit()
			if cur.rowcount == 0:
				return "Изображение не найдено"
			return "Тип успешно изменён"
	except Exception as e:
		logging.error(f"Error in toggle_type: {e}")
		conn.rollback()
		return "Ошибка при изменении типа"
	finally:
		return_connection(conn)


def set_need_moderate(image_id):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("UPDATE pictures SET need_moderate = TRUE WHERE id = %s", (image_id,))
			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error in set_need_moderate: {e}, image_id={image_id}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def add_saved_image(user_id, image_id):
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				UPDATE users
				SET saved_images = array_append(coalesce(saved_images, ARRAY[]::integer[]), %s),
					coins = coins - 25
				WHERE id = %s AND coins >= 25
				RETURNING coins
			""", (image_id, user_id))
			if cur.rowcount == 0:
				return False
			conn.commit()
			return True
	except Exception as e:
	    logging.error(f"Error in add_saved_image: {e}, user_id={user_id}, image_id={image_id}")
	    conn.rollback()
	    return False
	finally:
		return_connection(conn)


def save(user_id, image_id):
	"""
	Сохраняет изображение: добавляет в saved_images, списывает 25 монет,
	добавляет в просмотренные (viewed_*) и увеличивает value на 1.
	Возвращает True при успехе, False при недостатке монет или ошибке.
	"""
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("SELECT type FROM pictures WHERE id = %s", (image_id,))
			pic = cur.fetchone()
			if not pic:
				return False
			pic_type = pic[0]
			viewed_field = 'viewed_anime' if pic_type == ImageType.ANIME.value else 'viewed_real'

			query = sql.SQL("""
				UPDATE users
				SET saved_images = array_append(coalesce(saved_images, ARRAY[]::integer[]), %s),
					coins = coins - 25,
					{viewed_column} = CASE
						WHEN NOT (%s = ANY(coalesce({viewed_column}, ARRAY[]::integer[])))
						THEN array_append(coalesce({viewed_column}, ARRAY[]::integer[]), %s)
						ELSE {viewed_column}
					END
				WHERE id = %s AND coins >= 25
				RETURNING coins
			""").format(viewed_column=sql.Identifier(viewed_field))
			cur.execute(query, (image_id, image_id, image_id, user_id))
			if cur.rowcount == 0:
				return False

			cur.execute("""
				UPDATE pictures
				SET value = value + 1
				WHERE id = %s
			""", (image_id,))

			conn.commit()
			return True
	except Exception as e:
	    logging.error(f"Error in save: {e}, user_id={user_id}, image_id={image_id}")
	    conn.rollback()
	    return False
	finally:
		return_connection(conn)


def like(user_id):
	user = get_user(user_id)
	if not user:
		return False
	image_id = user.get('last_watched')
	if image_id is None:
		return False

	viewed_field = 'viewed_anime' if user['type'] == ImageType.ANIME.value else 'viewed_real'
	liked_field = 'liked_anime' if user['type'] == ImageType.ANIME.value else 'liked_real'

	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			# Обновление viewed_field
			query_viewed = sql.SQL("""
				UPDATE users
				SET {} = array_append(coalesce({}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""").format(
				sql.Identifier(viewed_field),
				sql.Identifier(viewed_field)
			)
			cur.execute(query_viewed, (image_id, user_id))
			# Обновление liked_field
			query_liked = sql.SQL("""
				UPDATE users
				SET {} = array_append(coalesce({}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""").format(
				sql.Identifier(liked_field),
				sql.Identifier(liked_field)
			)
			cur.execute(query_liked, (image_id, user_id))
			cur.execute("""
				UPDATE pictures
				SET likes = likes + 1, total = total + 1, value = value + 1
				WHERE id = %s
			""", (image_id,))
			if cur.rowcount == 0:
				conn.rollback()
				return False

			cur.execute("UPDATE users SET coins = coins + 1 WHERE id = %s", (user_id,))
			cur.execute("UPDATE users SET last_watched = NULL WHERE id = %s", (user_id,))
			# Запись в лог оценок
			cur.execute("""
				INSERT INTO user_ratings_log (user_id, image_id, rating_type)
				VALUES (%s, %s, 1)
			""", (user_id, image_id))

			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def dislike(user_id):
	user = get_user(user_id)
	if not user:
		return False
	image_id = user.get('last_watched')
	if image_id is None:
		return False

	viewed_field = 'viewed_anime' if user['type'] == ImageType.ANIME.value else 'viewed_real'

	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			query_viewed = sql.SQL("""
				UPDATE users
				SET {} = array_append(coalesce({}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""").format(
				sql.Identifier(viewed_field),
				sql.Identifier(viewed_field)
			)
			cur.execute(query_viewed, (image_id, user_id))
			cur.execute("""
				UPDATE pictures
				SET dislikes = dislikes + 1, total = total + 1, value = value - 1
				WHERE id = %s
			""", (image_id,))
			if cur.rowcount == 0:
				conn.rollback()
				return False

			cur.execute("UPDATE users SET coins = coins + 1 WHERE id = %s", (user_id,))
			cur.execute("UPDATE users SET last_watched = NULL WHERE id = %s", (user_id,))
			# Запись в лог оценок
			cur.execute("""
				INSERT INTO user_ratings_log (user_id, image_id, rating_type)
				VALUES (%s, %s, -1)
			""", (user_id, image_id))

			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def add_coins(user_id, amount):
	"""
	Добавляет указанное количество монет пользователю.
	Возвращает True при успехе.
	"""
	conn = get_connection()
	if not conn:
		logging.error(f"No connection available in add_coins for user {user_id}")
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("UPDATE users SET coins = coins + %s WHERE id = %s", (amount, user_id))
			if cur.rowcount == 0:
				logging.error(f"User {user_id} not found, cannot add coins")
				conn.rollback()
				return False
			conn.commit()
			logging.debug(f"Added {amount} coins to user {user_id}")
			return True
	except Exception as e:
		logging.error(f"Error adding coins to user {user_id}: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def spend_coins(user_id, amount):
	"""
	Списывает указанное количество монет у пользователя.
	Возвращает True при успехе (если монет достаточно), False при недостатке средств или ошибке.
	"""
	conn = get_connection()
	if not conn:
		logging.error(f"No connection available in spend_coins for user {user_id}")
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("UPDATE users SET coins = coins - %s WHERE id = %s AND coins >= %s", (amount, user_id, amount))
			if cur.rowcount == 0:
				logging.debug(f"User {user_id} not found or insufficient coins (need {amount})")
				conn.rollback()
				return False
			conn.commit()
			logging.debug(f"Spent {amount} coins from user {user_id}")
			return True
	except Exception as e:
		logging.error(f"Error spending coins from user {user_id}: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def cleanup_by_json(json_path):
    """
    Читает JSON-файл со списком имён файлов, находит соответствующие записи в таблице pictures,
    удаляет их из базы и удаляет файлы с диска.
    Возвращает кортеж (удалено_записей, ошибки).
    """
    import json
    if not os.path.isfile(json_path):
        logging.error(f"JSON file not found: {json_path}")
        return 0, ["Файл не найден"]
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to parse JSON {json_path}: {e}")
        return 0, [f"Ошибка чтения JSON: {e}"]
    if not isinstance(data, list):
        logging.error(f"JSON is not a list: {json_path}")
        return 0, ["JSON должен быть списком строк"]
    
    conn = get_connection()
    if not conn:
        return 0, ["Нет подключения к БД"]
    
    deleted = 0
    errors = []
    for filename in data:
        if not isinstance(filename, str):
            continue
        # Ищем записи с таким path (точное совпадение)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, type, path FROM pictures WHERE path = %s", (filename,))
                rows = cur.fetchall()
                if not rows:
                    logging.debug(f"File {filename} not found in database")
                    continue
                for row in rows:
                    image_id, img_type, img_path = row
                    # Удаляем файл
                    base_dir = IMAGE_DIR_ANIME if img_type == ImageType.ANIME.value else IMAGE_DIR_REAL
                    full_path = os.path.join(base_dir, img_path)
                    if os.path.isfile(full_path):
                        try:
                            os.remove(full_path)
                            logging.info(f"Файл изображения удалён: {full_path}")
                        except OSError as e:
                            logging.warning(f"Не удалось удалить файл {full_path}: {e}")
                            errors.append(f"Ошибка удаления файла {filename}: {e}")
                    else:
                        logging.warning(f"Файл изображения не найден: {full_path}")
                    # Удаляем запись из базы
                    cur.execute("DELETE FROM pictures WHERE id = %s", (image_id,))
                    deleted += 1
        except Exception as e:
            logging.error(f"Error deleting image {filename}: {e}")
            errors.append(f"Ошибка БД для {filename}: {e}")
            conn.rollback()
            continue
    conn.commit()
    return_connection(conn)
    return deleted, errors


def update_user_profile(user_id, first_name=None, last_name=None, username=None, language_code=None):
	"""
	Обновляет профиль пользователя (имя, фамилия, юзернейм, язык) в базе данных.
	Если поля не переданы, оставляет существующие значения.
	Возвращает True при успехе, False при ошибке.
	"""
	conn = get_connection()
	if not conn:
		logging.error(f"No connection available in update_user_profile for user {user_id}")
		return False
	try:
		with conn.cursor() as cur:
			# Проверяем наличие колонки language
			cur.execute("""
				SELECT column_name 
				FROM information_schema.columns 
				WHERE table_name = 'users' AND column_name = 'language'
			""")
			has_language_column = cur.fetchone() is not None
			
			# Строим динамический запрос на основе переданных данных
			updates = []
			params = []
			if first_name is not None:
				updates.append("first_name = %s")
				params.append(first_name)
			if last_name is not None:
				updates.append("last_name = %s")
				params.append(last_name)
			if username is not None:
				updates.append("username = %s")
				params.append(username)
			if language_code is not None and has_language_column:
				# Определяем язык из language_code Telegram, но только если у пользователя ещё не установлен язык
				cur.execute("SELECT language FROM users WHERE id = %s", (user_id,))
				user_row = cur.fetchone()
				current_language = user_row[0] if user_row else None
				if not current_language:
					# Язык ещё не установлен — определяем из Telegram
					language = 'ru' if language_code.startswith('ru') else 'en'
					updates.append("language = %s")
					params.append(language)
			if not updates:
				# Нет полей для обновления
				return True
			params.append(user_id)
			query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
			cur.execute(query, params)
			if cur.rowcount == 0:
				logging.warning(f"User {user_id} not found, cannot update profile")
				conn.rollback()
				return False
			conn.commit()
			logging.debug(f"Updated profile for user {user_id}")
			return True
	except Exception as e:
		logging.error(f"Error updating profile for user {user_id}: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def get_image(user_id):
    """
    Возвращает (путь_к_файлу, данные_изображения) для пользователя.
    Оптимизированная версия: использует одно соединение, объединяет запросы.
    """
    conn = get_connection()
    if not conn:
        logging.error(f"No connection available for user {user_id}")
        return None, None

    try:
        with conn.cursor() as cur:
            # Получаем пользователя
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                logging.warning(f"User {user_id} not found")
                return None, None
            columns = [desc[0] for desc in cur.description]
            user = dict(zip(columns, row))

            # Определяем параметры
            user_type = user['type']
            cycle = user['cycle']
            viewed_array = user['viewed_anime'] if user_type == ImageType.ANIME.value else user['viewed_real']
            base_path = IMAGE_DIR_ANIME if user_type == ImageType.ANIME.value else IMAGE_DIR_REAL

            # Проверка существования базовой директории
            if not os.path.isdir(base_path):
                logging.error(f"Base directory does not exist: {base_path}")
                return None, None

            # Строим запрос в зависимости от цикла
            if cycle == 0:
                # good images: value DESC, OFFSET 25
                query = """
                    SELECT * FROM pictures
                    WHERE type = %s
                      AND need_moderate = false
                      AND id != ALL(%s)
                    ORDER BY value DESC, random()
                    OFFSET 25
                    LIMIT 50
                """
            else:
                # noname images: total <= 5 OR likes / total > 0.25
                query = """
                    SELECT * FROM pictures
                    WHERE type = %s
                      AND need_moderate = false
                      AND id != ALL(%s)
                      AND ( total <= 5 OR (total > 0 AND likes::numeric / total > 0.25) )
                    ORDER BY total ASC, random()
                    LIMIT 50
                """
            cur.execute(query, (user_type, viewed_array))
            candidates = cur.fetchall()
            if not candidates:
                logging.warning(f"No candidate images for user {user_id}")
                return None, None

            logging.info(f"Found {len(candidates)} candidate images for user {user_id}, type={user_type}, cycle={cycle}")
            # Преобразуем в словари
            cand_columns = [desc[0] for desc in cur.description]
            missing_count = 0
            for idx, cand in enumerate(candidates):
                img = dict(zip(cand_columns, cand))
                full_path = os.path.join(base_path, img['path'])
                exists = os.path.isfile(full_path)
                if idx == 0:
                    logging.info(f"First candidate: path='{img['path']}', full='{full_path}', exists={exists}")
                if not exists:
                    missing_count += 1
                    logging.debug(f"Candidate {idx} missing: {full_path}")
                if exists:
                    # Нашли подходящее изображение
                    # Обновляем last_watched и cycle в одной транзакции
                    new_cycle = 1 if cycle == 0 else 0
                    cur.execute("""
                        UPDATE users
                        SET last_watched = %s, cycle = %s
                        WHERE id = %s
                    """, (img['id'], new_cycle, user_id))
                    conn.commit()
                    # Логируем выдачу
                    logging.debug(
                        f"Image delivered: id={img['id']}, likes={img['likes']}, "
                        f"dislikes={img['dislikes']}, total={img['total']}, value={img['value']}"
                    )
                    return full_path, img
            # Ни один файл не существует
            logging.warning(
                f"User {user_id} has no available images with existing files "
                f"(checked {len(candidates)} candidates, {missing_count} missing files)"
            )
            return None, None
    except Exception as e:
        logging.error(f"Error in get_image for user {user_id}: {e}")
        conn.rollback()
        return None, None
    finally:
        return_connection(conn)
def get_video_top25(user_id):
    """
    Возвращает видео с наибольшим value (топ 25), исключая просмотренные пользователем.
    Возвращает (путь_к_файлу, данные_видео) или (None, None).
    """
    conn = get_connection()
    if not conn:
        return None, None
    try:
        with conn.cursor() as cur:
            # Получаем список просмотренных видео пользователя
            cur.execute("SELECT watched_videos FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            watched = row[0] if row and row[0] else []
            # Выбираем топ 25 видео по value, исключая просмотренные
            cur.execute("""
                SELECT * FROM videos
                WHERE id != ALL(%s)
                ORDER BY value DESC, random()
                LIMIT 25
            """, (watched,))
            candidates = cur.fetchall()
            if not candidates:
                logging.warning(f"No top25 video candidates for user {user_id}")
                return None, None
            # Преобразуем в словари
            columns = [desc[0] for desc in cur.description]
            for cand in candidates:
                video = dict(zip(columns, cand))
                full_path = os.path.join(VIDEO_DIR, video['path'])
                if os.path.isfile(full_path):
                    return full_path, video
            logging.warning(f"No top25 video files exist for user {user_id}")
            return None, None
    except Exception as e:
        logging.error(f"Error in get_video_top25 for user {user_id}: {e}")
        return None, None
    finally:
        return_connection(conn)


def get_video_good(user_id):
    """
    Возвращает видео не из топ25 (value меньше чем у топ25), с наибольшим value,
    исключая просмотренные.
    """
    conn = get_connection()
    if not conn:
        return None, None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT watched_videos FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            watched = row[0] if row and row[0] else []
            # Выбираем видео, исключая топ25 (можно через OFFSET 25)
            cur.execute("""
                SELECT * FROM videos
                WHERE id != ALL(%s)
                ORDER BY value DESC, random()
                OFFSET 25
                LIMIT 50
            """, (watched,))
            candidates = cur.fetchall()
            if not candidates:
                logging.warning(f"No good video candidates for user {user_id}")
                return None, None
            columns = [desc[0] for desc in cur.description]
            for cand in candidates:
                video = dict(zip(columns, cand))
                full_path = os.path.join(VIDEO_DIR, video['path'])
                if os.path.isfile(full_path):
                    return full_path, video
            logging.warning(f"No good video files exist for user {user_id}")
            return None, None
    except Exception as e:
        logging.error(f"Error in get_video_good for user {user_id}: {e}")
        return None, None
    finally:
        return_connection(conn)


def get_video_free(user_id):
    """
    Возвращает видео с наименьшим total (наименее просмотренные),
    исключая просмотренные.
    """
    conn = get_connection()
    if not conn:
        return None, None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT watched_videos FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            watched = row[0] if row and row[0] else []
            cur.execute("""
                SELECT * FROM videos
                WHERE id != ALL(%s)
                ORDER BY total ASC, random()
                LIMIT 50
            """, (watched,))
            candidates = cur.fetchall()
            if not candidates:
                logging.warning(f"No free video candidates for user {user_id}")
                return None, None
            columns = [desc[0] for desc in cur.description]
            for cand in candidates:
                video = dict(zip(columns, cand))
                full_path = os.path.join(VIDEO_DIR, video['path'])
                if os.path.isfile(full_path):
                    return full_path, video
            logging.warning(f"No free video files exist for user {user_id}")
            return None, None
    except Exception as e:
        logging.error(f"Error in get_video_free for user {user_id}: {e}")
        return None, None
    finally:
        return_connection(conn)


def user_watched_video(user_id, video_id):
    """
    Добавляет видео в watched_videos пользователя и обновляет last_video_time.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET watched_videos = array_append(coalesce(watched_videos, ARRAY[]::INTEGER[]), %s),
                    last_video_time = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (video_id, user_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in user_watched_video: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def video_like(user_id, video_id):
    """
    Лайк видео: увеличивает likes, total, value, добавляет в liked_videos,
    начисляет 5 монет пользователю.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Обновляем статистику видео
            cur.execute("""
                UPDATE videos
                SET likes = likes + 1,
                    total = total + 1,
                    value = value + 1
                WHERE id = %s
            """, (video_id,))
            if cur.rowcount == 0:
                conn.rollback()
                return False
            # Добавляем в liked_videos
            cur.execute("""
                UPDATE users
                SET liked_videos = array_append(coalesce(liked_videos, ARRAY[]::INTEGER[]), %s)
                WHERE id = %s
            """, (video_id, user_id))
            # Начисляем 5 монет
            cur.execute("UPDATE users SET coins = coins + 5 WHERE id = %s", (user_id,))
            # Запись в лог оценок
            cur.execute("""
                INSERT INTO user_ratings_log (user_id, video_id, rating_type)
                VALUES (%s, %s, 1)
            """, (user_id, video_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in video_like: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def video_dislike(user_id, video_id):
    """
    Дизлайк видео: увеличивает dislikes, total, уменьшает value,
    начисляет 5 монет пользователю.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE videos
                SET dislikes = dislikes + 1,
                    total = total + 1,
                    value = value - 1
                WHERE id = %s
            """, (video_id,))
            if cur.rowcount == 0:
                conn.rollback()
                return False
            cur.execute("UPDATE users SET coins = coins + 5 WHERE id = %s", (user_id,))
            # Запись в лог оценок
            cur.execute("""
                INSERT INTO user_ratings_log (user_id, video_id, rating_type)
                VALUES (%s, %s, -1)
            """, (user_id, video_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in video_dislike: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def video_save(user_id, video_id):
    """
    Сохранение видео: добавляет в saved_videos и liked_videos, списывает 50 монет.
    Если видео ещё не в liked_videos - увеличивает likes, total, value на 2 (лайк + сохранение).
    Если видео уже в liked_videos - увеличивает value на 1 (только сохранение).
    Возвращает True при успехе, False при недостатке монет или ошибке.
    """
    conn = get_connection()
    if not conn:
        logging.error(f"video_save: failed to get connection, user_id={user_id}, video_id={video_id}")
        return False
    try:
        with conn.cursor() as cur:
            # Проверяем, есть ли уже видео в saved_videos
            cur.execute("SELECT saved_videos FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            saved_videos = row[0] if row and row[0] else []
            logging.info(f"video_save: user_id={user_id}, video_id={video_id}, saved_videos={saved_videos}, checking_duplicate={video_id in saved_videos}")
            if video_id in saved_videos:
                # Видео уже сохранено
                logging.warning(f"video_save: video already saved, user_id={user_id}, video_id={video_id}")
                return False
            
            # Проверяем, есть ли уже видео в liked_videos
            cur.execute("SELECT liked_videos FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            liked_videos = row[0] if row and row[0] else []
            already_liked = video_id in liked_videos
            logging.info(f"video_save: user_id={user_id}, video_id={video_id}, liked_videos={liked_videos}, already_liked={already_liked}")
            
            # Проверяем баланс перед операцией
            cur.execute("SELECT coins FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            coins = row[0] if row else 0
            logging.info(f"video_save: user_id={user_id}, coins={coins}")
            
            if coins < 50:
                # Недостаточно монет
                logging.warning(f"video_save: insufficient coins, user_id={user_id}, coins={coins}, video_id={video_id}")
                return False
            
            # Списываем 50 монет, добавляем в saved_videos и liked_videos
            if already_liked:
                # Видео уже лайкнуто, добавляем только в saved_videos
                cur.execute("""
                    UPDATE users
                    SET saved_videos = array_append(coalesce(saved_videos, ARRAY[]::INTEGER[]), %s),
                        coins = coins - 50
                    WHERE id = %s
                    RETURNING coins
                """, (video_id, user_id))
            else:
                # Видео ещё не лайкнуто, добавляем в оба списка
                cur.execute("""
                    UPDATE users
                    SET saved_videos = array_append(coalesce(saved_videos, ARRAY[]::INTEGER[]), %s),
                        liked_videos = array_append(coalesce(liked_videos, ARRAY[]::INTEGER[]), %s),
                        coins = coins - 50
                    WHERE id = %s
                    RETURNING coins
                """, (video_id, video_id, user_id))
            
            logging.info(f"video_save: UPDATE rowcount={cur.rowcount}, user_id={user_id}, video_id={video_id}")
            if cur.rowcount == 0:
                # Это не должно произойти, но на всякий случай
                logging.error(f"video_save: UPDATE failed (rowcount=0), user_id={user_id}, video_id={video_id}, already_liked={already_liked}")
                return False
            
            # Увеличиваем статистику видео
            if already_liked:
                # Видео уже лайкнуто - увеличиваем только value на 1
                cur.execute("""
                    UPDATE videos
                    SET value = value + 1
                    WHERE id = %s
                """, (video_id,))
            else:
                # Видео ещё не лайкнуто - увеличиваем likes, total, value на 2 (лайк + сохранение)
                cur.execute("""
                    UPDATE videos
                    SET likes = likes + 1,
                        total = total + 1,
                        value = value + 2
                    WHERE id = %s
                """, (video_id,))
            
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in video_save: {e}, user_id={user_id}, video_id={video_id}", exc_info=True)
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def video_report(user_id, video_id):
    """
    Жалоба на видео: увеличивает total (можно также увеличить dislikes?).
    Пока просто увеличим total на 1.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE videos
                SET total = total + 1
                WHERE id = %s
            """, (video_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error in video_report: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def get_video_by_id(video_id):
    """
    Возвращает данные видео по ID или None.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM videos WHERE id = %s", (video_id,))
            row = cur.fetchone()
            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            return None
    except Exception as e:
        logging.error(f"Error in get_video_by_id: {e}")
        return None
    finally:
        return_connection(conn)


def update_video_path(video_id, new_path):
    """
    Обновляет путь (имя файла) для указанного видео.
    Возвращает True при успехе, False при ошибке.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE videos
                SET path = %s
                WHERE id = %s
            """, (new_path, video_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error updating video path: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def delete_video(video_id):
    """
    Удаляет видео из базы данных и файл с диска.
    Возвращает True при успехе, False при ошибке.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Получаем путь видео
            cur.execute("SELECT path FROM videos WHERE id = %s", (video_id,))
            row = cur.fetchone()
            if row:
                video_path = row[0]
                full_path = os.path.join(VIDEO_DIR, video_path)
                if os.path.isfile(full_path):
                    try:
                        os.remove(full_path)
                        logging.info(f"Файл видео удалён: {full_path}")
                    except OSError as e:
                        logging.warning(f"Не удалось удалить файл {full_path}: {e}")
                else:
                    logging.warning(f"Файл видео не найден: {full_path}")
            # Удаляем запись из базы
            cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка при удалении видео {video_id}: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def can_watch_video(user_id):
    """
    Проверяет, прошло ли 30 секунд с последнего просмотра видео.
    Возвращает True, если можно смотреть (прошло >=30 секунд или last_video_time NULL).
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT last_video_time FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row or row[0] is None:
                return True
            last_time = row[0]
            cur.execute("SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - %s))", (last_time,))
            diff = cur.fetchone()[0]
            return diff >= 30
    except Exception as e:
        logging.error(f"Error in can_watch_video: {e}")
        return False
    finally:
        return_connection(conn)


def init_promo_links_table():
    """Создаёт таблицу для рекламных ссылок, если её нет."""
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS promo_links (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS promo_link_stats (
                    id SERIAL PRIMARY KEY,
                    promo_link_id INTEGER NOT NULL REFERENCES promo_links(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_promo_links_code ON promo_links(code);
                CREATE INDEX IF NOT EXISTS idx_promo_link_stats_promo_id ON promo_link_stats(promo_link_id);
            """)
            conn.commit()
            logging.info("Promo links tables created successfully")
    except Exception as e:
        logging.error(f"Error creating promo links tables: {e}")
        conn.rollback()
    finally:
        return_connection(conn)


def create_promo_link(name: str, code: str = None) -> tuple:
    """
    Создаёт рекламную ссылку с указанным именем.
    Если code не указан, генерируется уникальный код.
    Возвращает кортеж (success, code_or_error).
    """
    import secrets
    import string
    
    conn = get_connection()
    if not conn:
        return False, "Нет подключения к БД"
    try:
        with conn.cursor() as cur:
            # Генерируем уникальный код, если не передан
            if code is None:
                alphabet = string.ascii_letters + string.digits
                while True:
                    code = ''.join(secrets.choice(alphabet) for _ in range(8))
                    cur.execute("SELECT id FROM promo_links WHERE code = %s", (code,))
                    if not cur.fetchone():
                        break
            
            cur.execute("""
                INSERT INTO promo_links (name, code)
                VALUES (%s, %s)
                RETURNING code
            """, (name, code))
            conn.commit()
            return True, code
    except Exception as e:
        logging.error(f"Error creating promo link: {e}")
        conn.rollback()
        return False, str(e)
    finally:
        return_connection(conn)


def get_all_promo_links() -> list:
    """
    Возвращает список всех рекламных ссылок со статистикой кликов и регистраций.
    Каждый элемент: {
        'id': int,
        'name': str,
        'code': str,
        'created_at': datetime,
        'clicks_count': int,
        'registrations_count': int
    }
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    p.id,
                    p.name,
                    p.code,
                    p.created_at,
                    COUNT(DISTINCT s.user_id) as clicks_count,
                    COUNT(DISTINCT u.id) as registrations_count
                FROM promo_links p
                LEFT JOIN promo_link_stats s ON p.id = s.promo_link_id
                LEFT JOIN users u ON u.promo_code = p.code
                GROUP BY p.id, p.name, p.code, p.created_at
                ORDER BY p.created_at DESC
            """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'id': row[0],
                    'name': row[1],
                    'code': row[2],
                    'created_at': row[3],
                    'clicks_count': row[4],
                    'registrations_count': row[5]
                })
            return result
    except Exception as e:
        logging.error(f"Error getting promo links: {e}")
        return []
    finally:
        return_connection(conn)


def track_promo_link_click(code: str, user_id: int) -> bool:
    """
    Записывает переход по рекламной ссылке.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Находим ссылку по коду
            cur.execute("SELECT id FROM promo_links WHERE code = %s", (code,))
            row = cur.fetchone()
            if not row:
                return False
            promo_link_id = row[0]
            
            # Записываем переход (если пользователь ещё не переходил по этой ссылке)
            cur.execute("""
                INSERT INTO promo_link_stats (promo_link_id, user_id)
                SELECT %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM promo_link_stats 
                    WHERE promo_link_id = %s AND user_id = %s
                )
            """, (promo_link_id, user_id, promo_link_id, user_id))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logging.error(f"Error tracking promo link click: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def get_promo_link_by_code(code: str) -> dict:
    """
    Возвращает данные рекламной ссылки по коду.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, code, created_at FROM promo_links WHERE code = %s", (code,))
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'code': row[2],
                    'created_at': row[3]
                }
            return None
    except Exception as e:
        logging.error(f"Error getting promo link by code: {e}")
        return None
    finally:
        return_connection(conn)


def delete_promo_link(link_id: int) -> bool:
    """
    Удаляет рекламную ссылку по ID.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM promo_links WHERE id = %s", (link_id,))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logging.error(f"Error deleting promo link: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def add_transaction(user_id: int, amount: int, stars_paid: int) -> bool:
    """
    Добавляет запись о транзакции пополнения баланса.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        logging.error(f"No connection available in add_transaction for user {user_id}")
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transactions (user_id, amount, stars_paid)
                VALUES (%s, %s, %s)
            """, (user_id, amount, stars_paid))
            conn.commit()
            logging.info(f"Transaction added: user {user_id}, {amount} coins, {stars_paid} stars")
            return True
    except Exception as e:
        logging.error(f"Error adding transaction for user {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def get_user_language(user_id: int) -> str:
    """
    Возвращает язык пользователя (ru/en).
    """
    conn = get_connection()
    if not conn:
        return 'ru'
    try:
        with conn.cursor() as cur:
            # Проверяем наличие колонки language
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'language'
            """)
            if not cur.fetchone():
                # Колонки нет, возвращаем default
                return 'ru'
            
            cur.execute("SELECT language FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else 'ru'
    except Exception as e:
        # Тихо возвращаем default при любой ошибке
        return 'ru'
    finally:
        return_connection(conn)


def set_user_language(user_id: int, language: str) -> bool:
    """
    Устанавливает язык пользователя.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Проверяем наличие колонки language
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'language'
            """)
            if not cur.fetchone():
                # Колонки нет, миграция ещё не выполнена
                logging.warning("language column not found, migration pending")
                return False
            
            cur.execute("UPDATE users SET language = %s WHERE id = %s", (language, user_id))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logging.error(f"Error setting user language: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def set_user_promo_code(user_id: int, promo_code: str) -> bool:
    """
    Устанавливает рекламную ссылку (promo_code) пользователя.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET promo_code = %s WHERE id = %s", (promo_code, user_id))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logging.error(f"Error setting user promo code: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)


def get_promo_link_registration_stats(promo_code: str) -> dict:
    """
    Возвращает статистику по рекламной ссылке (сколько пользователей зарегистрировалось через неё).
    Считает всех пользователей, у кого в профиле стоит этот promo_code.
    """
    conn = get_connection()
    if not conn:
        return {'total_users': 0, 'today_users': 0}
    try:
        with conn.cursor() as cur:
            # Общее количество пользователей с этим promo_code
            cur.execute("""
                SELECT COUNT(*) FROM users WHERE promo_code = %s
            """, (promo_code,))
            total_users = cur.fetchone()[0]

            # Количество пользователей, зарегистрированных сегодня
            cur.execute("""
                SELECT COUNT(*) FROM users 
                WHERE promo_code = %s AND registered_at >= CURRENT_DATE
            """, (promo_code,))
            today_users = cur.fetchone()[0]

            return {
                'total_users': total_users,
                'today_users': today_users
            }
    except Exception as e:
        logging.error(f"Error getting promo link registration stats: {e}")
        return {'total_users': 0, 'today_users': 0}
    finally:
        return_connection(conn)


def get_all_promo_links_registration_stats() -> list:
    """
    Возвращает статистику по всем рекламным ссылкам (регистрации через promo_code).
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    promo_code,
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE registered_at >= CURRENT_DATE) as today_users,
                    MIN(registered_at) as first_registration
                FROM users
                WHERE promo_code IS NOT NULL
                GROUP BY promo_code
                ORDER BY total_users DESC
            """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'promo_code': row[0],
                    'total_users': row[1],
                    'today_users': row[2],
                    'first_registration': row[3]
                })
            return result
    except Exception as e:
        logging.error(f"Error getting all promo links registration stats: {e}")
        return []
    finally:
        return_connection(conn)


def get_user_promo_code(user_id: int) -> str:
    """
    Возвращает promo_code пользователя.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT promo_code FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as e:
        logging.error(f"Error getting user promo code: {e}")
        return None
    finally:
        return_connection(conn)


def get_user_transactions(user_id: int, limit: int = 10) -> list:
    """
    Возвращает последние транзакции пользователя.
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT amount, stars_paid, created_at
                FROM transactions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'amount': row[0],
                    'stars_paid': row[1],
                    'created_at': row[2]
                })
            return result
    except Exception as e:
        logging.error(f"Error getting transactions for user {user_id}: {e}")
        return []
    finally:
        return_connection(conn)


def add_feedback_message(user_id: int, message: str) -> bool:
    """
    Сохраняет сообщение обратной связи в базу данных.
    Возвращает True при успехе, False при ошибке.
    """
    conn = get_connection()
    if not conn:
        logging.error(f"No connection available in add_feedback_message for user {user_id}")
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO feedback_messages (user_id, message)
                VALUES (%s, %s)
            """, (user_id, message))
            conn.commit()
            logging.info(f"Feedback message saved from user {user_id}")
            return True
    except Exception as e:
        logging.error(f"Error saving feedback message from user {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        return_connection(conn)