# database.py
import psycopg2
from psycopg2 import pool
from config_reader import config

# Создаём пул соединений (это эффективнее, чем открывать/закрывать соединение на каждый запрос)
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1,  # минимальное количество соединений в пуле
        10, # максимальное
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
    """Получить соединение из пула"""
    if connection_pool:
        return connection_pool.getconn()
    return None

def return_connection(conn):
    """Вернуть соединение обратно в пул"""
    if connection_pool and conn:
        connection_pool.putconn(conn)

def close_all_connections():
    """Закрыть все соединения (при остановке бота)"""
    if connection_pool:
        connection_pool.closeall()

# Пример простой функции для создания таблицы (вызови её один раз при старте)
def create_tables():
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    registered_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()
            print("Table 'users' checked/created.")
    except Exception as e:
        print(f"Error creating table: {e}")
        conn.rollback()
    finally:
        return_connection(conn)