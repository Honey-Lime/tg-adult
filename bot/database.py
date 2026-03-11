# database.py
import psycopg2
from psycopg2 import pool
from config_reader import config
import os

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
		print("Connection pool created successfully")
except Exception as e:
	print(f"Error creating connection pool: {e}")
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
		print(f"Error adding post record {date}: {e}")
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
		print(f"Error adding picture record {filename}: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def get_all_users_stats():
	"""
	Возвращает список пользователей с количеством просмотренных картинок.
	Каждый элемент: {'user_id': id, 'viewed_count': int}
	"""
	conn = get_connection()
	if not conn:
		return []
	try:
		with conn.cursor() as cur:
			cur.execute("""
				SELECT id,
					   COALESCE(array_length(viewed_anime, 1), 0) +
					   COALESCE(array_length(viewed_real, 1), 0) as viewed_count
				FROM users
				ORDER BY id
			""")
			rows = cur.fetchall()
			result = [{'user_id': row[0], 'viewed_count': row[1]} for row in rows]
			return result
	except Exception as e:
		print(f"Error getting users stats: {e}")
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
		print(f"Error getting user {user_id}: {e}")
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
				print(f"[DEBUG] User {user_id} already exists")
				return dict(zip(columns, row)), False

			# Пользователь не найден, создаём нового
			# Проверяем существование реферера, если он указан
			valid_referrer = False
			if referrer_id is not None:
				cur.execute("SELECT id FROM users WHERE id = %s", (referrer_id,))
				if cur.fetchone():
					valid_referrer = True
				else:
					print(f"[WARNING] Referrer {referrer_id} not found, will create user without bonus")

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
				print(f"[DEBUG] New user inserted: {user_id}")
				if valid_referrer:
					# Начисляем бонус рефереру
					cur.execute("UPDATE users SET coins = coins + 250 WHERE id = %s", (referrer_id,))
					if cur.rowcount == 0:
						print(f"[ERROR] Failed to award coins to referrer {referrer_id} (should not happen)")
					else:
						print(f"[INFO] Referrer {referrer_id} awarded 250 coins for new user {user_id}")
				conn.commit()
				# Получаем свежесозданного пользователя
				cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
				row = cur.fetchone()
				if row:
					columns = [desc[0] for desc in cur.description]
					return dict(zip(columns, row)), True
				else:
					print(f"[ERROR] Could not fetch newly created user {user_id}")
					return None, False
			else:
				# Конкурентная вставка – повторяем поиск
				print(f"[DEBUG] User {user_id} was not inserted (race condition), re-fetching...")
				cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
				row = cur.fetchone()
				if row:
					columns = [desc[0] for desc in cur.description]
					return dict(zip(columns, row)), False
				else:
					return None, False
	except Exception as e:
		print(f"[ERROR] Error in get_or_create_user {user_id}: {e}")
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
		print(f"Error set type for user: {user_id}: {e}")
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
		print(f"Error set type for user: {user_id}: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def user_watched_image(user_id, image):
	if image['type'] == 0:
		viewed_name = 'viewed_anime'
	else:
		viewed_name = 'viewed_real'
	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			query = f"""
				UPDATE users
				SET {viewed_name} = array_append(coalesce({viewed_name}, ARRAY[]::integer[]), %s),
					last_watched = %s
				WHERE id = %s
			"""
			cur.execute(query, (image['id'], image['id'], user_id))
			conn.commit()
		return True
	except Exception as e:
		print(f"Error updating watched for user {user_id}: {e}")
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
			cur.execute(f"SELECT * FROM pictures WHERE type = {type} and need_moderate = false ORDER BY value DESC OFFSET 25")
			columns = [desc[0] for desc in cur.description]
			rows = cur.fetchall()
			result = [dict(zip(columns, row)) for row in rows]
			return result
	except Exception as e:
		print(f"Error getting all images: {e}")
		return []
	finally:
		return_connection(conn)


def get_noname_images(type):
	conn = get_connection()
	if not conn:
		return []
	try:
		with conn.cursor() as cur:
			cur.execute(f"SELECT * FROM pictures WHERE value > -10 and type = {type} and need_moderate = false ORDER BY total ASC")
			columns = [desc[0] for desc in cur.description]
			rows = cur.fetchall()
			result = [dict(zip(columns, row)) for row in rows]
			return result
	except Exception as e:
		print(f"Error getting all images: {e}")
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
		print(f"Error getting not_real_type: {e}")
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
		print(f"Error setting not_real_type: {e}")
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
			# Меняем тип и сбрасываем not_real_type
			cur.execute("""
				UPDATE pictures
				SET type = 1 - type,
					not_real_type = false
				WHERE id = %s
			""", (image_id,))
			conn.commit()
			if cur.rowcount == 0:
				return "Изображение не найдено"
			return "Тип успешно изменён"
	except Exception as e:
		print(f"Error toggling type: {e}")
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
		print(f"Error setting need_moderate for image {image_id}: {e}")
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
		print(f"Error adding saved image: {e}")
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
			viewed_field = 'viewed_anime' if pic_type == 0 else 'viewed_real'

			cur.execute(f"""
				UPDATE users
				SET saved_images = array_append(coalesce(saved_images, ARRAY[]::integer[]), %s),
					coins = coins - 25,
					{viewed_field} = CASE
						WHEN NOT (%s = ANY(coalesce({viewed_field}, ARRAY[]::integer[])))
						THEN array_append(coalesce({viewed_field}, ARRAY[]::integer[]), %s)
						ELSE {viewed_field}
					END
				WHERE id = %s AND coins >= 25
				RETURNING coins
			""", (image_id, image_id, image_id, user_id))
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
		print(f"Error in save: {e}")
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

	viewed_field = 'viewed_anime' if user['type'] == 0 else 'viewed_real'
	liked_field = 'liked_anime' if user['type'] == 0 else 'liked_real'

	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute(f"""
				UPDATE users
				SET {viewed_field} = array_append(coalesce({viewed_field}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""", (image_id, user_id))
			cur.execute(f"""
				UPDATE users
				SET {liked_field} = array_append(coalesce({liked_field}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""", (image_id, user_id))
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
		print(f"Error liking: {e}")
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

	viewed_field = 'viewed_anime' if user['type'] == 0 else 'viewed_real'

	conn = get_connection()
	if not conn:
		return False
	try:
		with conn.cursor() as cur:
			cur.execute(f"""
				UPDATE users
				SET {viewed_field} = array_append(coalesce({viewed_field}, ARRAY[]::integer[]), %s)
				WHERE id = %s
			""", (image_id, user_id))
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
		print(f"Error disliking: {e}")
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
		print(f"[ERROR] add_coins: no connection")
		return False
	try:
		with conn.cursor() as cur:
			cur.execute("UPDATE users SET coins = coins + %s WHERE id = %s", (amount, user_id))
			if cur.rowcount == 0:
				print(f"[ERROR] add_coins: user {user_id} not found")
				conn.rollback()
				return False
			conn.commit()
			print(f"[DEBUG] add_coins: added {amount} to user {user_id}")
			return True
	except Exception as e:
		print(f"[ERROR] add_coins: {e}")
		conn.rollback()
		return False
	finally:
		return_connection(conn)


def get_image(user_id):
	user = get_user(user_id)
	if not user:
		return None, None

	if user['type'] == 0:
		exclude = set(user['viewed_anime'])
		base_path = IMAGE_DIR_ANIME
	else:
		exclude = set(user['viewed_real'])
		base_path = IMAGE_DIR_REAL

	if user['cycle'] == 0:
		database_images = get_good_images(user['type'])
	else:
		database_images = get_noname_images(user['type'])

	for img in database_images:
		if img['id'] not in exclude:
			full_path = os.path.join(base_path, img['path'])
			if os.path.isfile(full_path):
				# Обновляем last_watched
				conn = get_connection()
				if conn:
					try:
						with conn.cursor() as cur:
							cur.execute("UPDATE users SET last_watched = %s WHERE id = %s", (img['id'], user_id))
							conn.commit()
					except Exception as e:
						print(f"Error updating last_watched: {e}")
						conn.rollback()
					finally:
						return_connection(conn)
				user_set_cycle(user_id, user['cycle'])

				# Логируем выдачу картинки
				# print(f"[IMAGE] выдана: id={img['id']}, likes={img['likes']}, dislikes={img['dislikes']}, total={img['total']}, value={img['value']}")
				return full_path, img

	print(f"User {user_id} has no available images with existing files")
	return None, None