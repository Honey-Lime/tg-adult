# database.py
import psycopg2
import logging
from psycopg2 import pool
from psycopg2 import sql
from config_reader import config
import os

from enum import Enum


class ImageType(Enum):
    """Типы изображений."""
    ANIME = 0
    REAL = 1


# Базовая директория проекта (там, где лежит database.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR_ANIME = os.path.join(BASE_DIR, 'images', 'anime')
IMAGE_DIR_REAL = os.path.join(BASE_DIR, 'images', 'real')

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
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("""
				INSERT INTO pictures (type, post_id, path)
				VALUES (%s, %s, %s)
			""", (pic_type, post_id, filename))
			conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error : {e}")
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
			conn.commit()
			logging.info("Database initialization completed (message_history and users columns)")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
		return {}
	finally:
		return_connection(conn)


def get_all_users_stats():
	"""
	Возвращает список пользователей с детальной статистикой.
	Каждый элемент: {
		'user_id': int,
		'first_name': str или None,
		'last_name': str или None,
		'username': str или None,
		'viewed_anime_count': int,
		'viewed_real_count': int,
		'viewed_total': int
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
					   COALESCE(array_length(viewed_anime, 1), 0) +
					   COALESCE(array_length(viewed_real, 1), 0) as viewed_total
				FROM users
				ORDER BY id
			""")
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
					'viewed_total': row[6]
				})
			return result
	except Exception as e:
		logging.error(f"Error in get_all_users_stats: {e}")
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
		logging.error(f"Error : {e}")
		conn.rollback()
		return None
	finally:
		return_connection(conn)


def get_or_create_user(user_id, referrer_id=None):
	"""
	Получает пользователя по id. Если не существует – создаёт.
	Если передан referrer_id и реферер существует, начисляет ему 250 монет.
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

			# Вставка нового пользователя
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
        logging.error(f"Error : {e}")
        return []
    finally:
        return_connection(conn)

def delete_image(image_id):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pictures WHERE id = %s", (image_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error : {e}")
        conn.rollback()
        return False
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
        logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def toggle_type(user_id):
	"""
	Переключает тип текущего изображения и сбрасывает not_real_type в false.
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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
		logging.error(f"Error : {e}")
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


def update_user_profile(user_id, first_name=None, last_name=None, username=None):
	"""
	Обновляет профиль пользователя (имя, фамилия, юзернейм) в базе данных.
	Если поля не переданы, оставляет существующие значения.
	Возвращает True при успехе, False при ошибке.
	"""
	conn = get_connection()
	if not conn:
		logging.error(f"No connection available in update_user_profile for user {user_id}")
		return False
	try:
		with conn.cursor() as cur:
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

            # Строим запрос в зависимости от цикла
            if cycle == 0:
                # good images: value DESC, OFFSET 25
                query = """
                    SELECT * FROM pictures
                    WHERE type = %s
                      AND need_moderate = false
                      AND id != ALL(%s)
                    ORDER BY value DESC
                    OFFSET 25
                    LIMIT 50
                """
            else:
                # noname images: value > -10, total ASC
                query = """
                    SELECT * FROM pictures
                    WHERE type = %s
                      AND need_moderate = false
                      AND value > -10
                      AND id != ALL(%s)
                    ORDER BY total ASC
                    LIMIT 50
                """
            cur.execute(query, (user_type, viewed_array))
            candidates = cur.fetchall()
            if not candidates:
                logging.warning(f"No candidate images for user {user_id}")
                return None, None

            # Преобразуем в словари
            cand_columns = [desc[0] for desc in cur.description]
            for cand in candidates:
                img = dict(zip(cand_columns, cand))
                full_path = os.path.join(base_path, img['path'])
                if os.path.isfile(full_path):
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
            logging.warning(f"User {user_id} has no available images with existing files")
            return None, None
    except Exception as e:
        logging.error(f"Error in get_image for user {user_id}: {e}")
        conn.rollback()
        return None, None
    finally:
        return_connection(conn)