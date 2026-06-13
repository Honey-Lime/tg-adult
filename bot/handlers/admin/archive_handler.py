"""
Обработчик раздела "Архив" в админ-панели.
Показывает статистику по картинкам и видео в базе данных.
"""

import database
from locales import get_text


def _low_rating_percent(stats: dict) -> float:
    total = stats.get('total', 0) or 0
    if total == 0:
        return 0
    return stats.get('low_rating', 0) / total * 100


async def handle_admin_archive(controller, chat_id: int, message_id: int, lang: str):
    """
    Показывает статистику архива по total и доле лайков.
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        await controller.delete_current(chat_id, message_id)
        return

    stats = database.get_archive_stats()
    anime = stats['images']['anime']
    real = stats['images']['real']
    videos = stats['videos']

    text = (
        f"📦 Архив контента\n\n"
        f"🖼 Картинки аниме:\n"
        f"  Всего: {anime['total']}\n"
        f"  Низкооценённых: {_low_rating_percent(anime):.1f}%\n"
        f"  total = 0: {anime['total_eq_0']}\n"
        f"  total < 5: {anime['total_lt_5']}\n"
        f"  total >= 5: {anime['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {anime['low_rating']}\n\n"
        f"📷 Картинки фото:\n"
        f"  Всего: {real['total']}\n"
        f"  Низкооценённых: {_low_rating_percent(real):.1f}%\n"
        f"  total = 0: {real['total_eq_0']}\n"
        f"  total < 5: {real['total_lt_5']}\n"
        f"  total >= 5: {real['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {real['low_rating']}\n\n"
        f"🎞 Видео:\n"
        f"  Всего: {videos['total']}\n"
        f"  Низкооценённых: {_low_rating_percent(videos):.1f}%\n"
        f"  total = 0: {videos['total_eq_0']}\n"
        f"  total < 5: {videos['total_lt_5']}\n"
        f"  total >= 5: {videos['total_gte_5']}\n"
        f"  total >= 5 и likes / total <= 0.2: {videos['low_rating']}"
    )

    await controller.send_and_track(chat_id, text=text, track=False)
