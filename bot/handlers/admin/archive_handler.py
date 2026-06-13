"""
Обработчик раздела "Архив" в админ-панели.
Показывает статистику по картинкам и видео в базе данных.
"""

import database
from locales import get_text


async def handle_admin_archive(controller, chat_id: int, message_id: int, lang: str):
    """
    Показывает статистику архива по total и доле лайков.
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        await controller.delete_current(chat_id, message_id)
        return

    stats = database.get_archive_stats()

    text = (
        f"📦 Архив контента\n\n"
        f"🖼 Картинки аниме:\n"
        f"  total = 0: {stats['images']['anime']['total_eq_0']}\n"
        f"  total = 1: {stats['images']['anime']['total_eq_1']}\n"
        f"  total >= 5: {stats['images']['anime']['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {stats['images']['anime']['low_rating']}\n\n"
        f"📷 Картинки фото:\n"
        f"  total = 0: {stats['images']['real']['total_eq_0']}\n"
        f"  total = 1: {stats['images']['real']['total_eq_1']}\n"
        f"  total >= 5: {stats['images']['real']['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {stats['images']['real']['low_rating']}\n\n"
        f"🎞 Видео:\n"
        f"  total = 0: {stats['videos']['total_eq_0']}\n"
        f"  total = 1: {stats['videos']['total_eq_1']}\n"
        f"  total >= 5: {stats['videos']['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {stats['videos']['low_rating']}"
    )

    await controller.send_and_track(chat_id, text=text, track=False)
