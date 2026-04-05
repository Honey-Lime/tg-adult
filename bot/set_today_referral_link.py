#!/usr/bin/env python
"""
Разовый скрипт: устанавливает promo_code всем пользователям,
зарегистрированным сегодня.

Использование:
    python set_today_referral_link.py
"""

import sys
import os

# Добавляем директорию с модулями в путь
sys.path.insert(0, os.path.dirname(__file__))

from database import get_connection, return_connection, set_user_promo_code
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Код рекламной ссылки, которую нужно выставить всем зарегистрированным сегодня
PROMO_CODE = "hD5lDhxR"


def main():
    conn = get_connection()
    if not conn:
        logging.error("Нет подключения к БД")
        return

    try:
        with conn.cursor() as cur:
            # Находим всех пользователей, зарегистрированных сегодня, у кого ещё нет promo_code
            cur.execute("""
                SELECT id FROM users
                WHERE registered_at >= CURRENT_DATE
                  AND (promo_code IS NULL OR promo_code = '')
            """)
            rows = cur.fetchall()
            user_ids = [row[0] for row in rows]

            if not user_ids:
                logging.info("Нет пользователей, зарегистрированных сегодня без promo_code")
                return

            logging.info(f"Найдено {len(user_ids)} пользователей для обновления")

            updated_count = 0
            for user_id in user_ids:
                success = set_user_promo_code(user_id, PROMO_CODE)
                if success:
                    updated_count += 1
                else:
                    logging.warning(f"Не удалось обновить пользователя {user_id}")

            logging.info(f"Обновлено {updated_count}/{len(user_ids)} пользователей")
            logging.info(f"Promo code: {PROMO_CODE}")

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        conn.rollback()
    finally:
        return_connection(conn)


if __name__ == "__main__":
    main()
