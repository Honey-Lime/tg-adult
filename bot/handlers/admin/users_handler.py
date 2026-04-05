"""
Обработчик статистики пользователей.
"""

import database
from keyboards import get_admin_panel_keyboard
from locales import get_text


async def handle_admin_users(controller, chat_id: int, message_id: int, lang: str):
    """
    Показ статистики всех пользователей.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    # Проверка прав администратора
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        await controller.delete_current(chat_id, message_id)
        return
    
    # Получение данных
    users = database.get_all_users_stats()
    global_stats = database.get_global_users_stats()
    
    if not users:
        text = "❌ Нет данных о пользователях."
    else:
        text = _format_users_stats(users, global_stats)
    
    # Отправка ответа
    await controller.delete_current(chat_id, message_id)
    await controller.send_and_track(chat_id, text=text, track=False)
    
    # Возврат в админ-меню
    keyboard = get_admin_panel_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text="Админ-панель. Выберите действие:",
        reply_markup=keyboard,
        track=False
    )


def _format_users_stats(users: list, global_stats: dict) -> str:
    """
    Форматирует статистику пользователей в читаемый текст.
    
    Args:
        users: Список словарей с данными пользователей
        global_stats: Словарь с общей статистикой
    
    Returns:
        Отформатированный текст статистики
    """
    lines = []
    
    # Общая статистика
    if global_stats:
        lines.append(
            f"📊 Общая статистика:\n"
            f"👥 Пользователей: {global_stats['total_users']}\n"
            f"🎬 Среднее: аниме {global_stats['avg_anime']}, фото {global_stats['avg_real']}, "
            f"видео {global_stats['avg_video']}, оценок сегодня {global_stats['today_ratings']}\n"
        )
    
    lines.append(f"📊 Топ-25 пользователей (по общему кол-ву оценок):")
    
    for user in users:
        # Формируем отображаемое имя
        name_parts = []
        if user['first_name']:
            name_parts.append(user['first_name'])
        if user['last_name']:
            name_parts.append(user['last_name'])
        
        display_name = ' '.join(name_parts) if name_parts else '—'
        username = f"@{user['username']}" if user['username'] else '—'
        
        lines.append(
            f"{user['user_id']} | {display_name} ({username})"
        )
        lines.append(
            f"  Всего: {user['viewed_total']} "
            f"(аниме: {user['viewed_anime_count']}, фото: {user['viewed_real_count']}, "
            f"видео: {user['viewed_video_count']}, оценок сегодня: {user['today_ratings']})"
        )
        lines.append("")
    
    return "\n".join(lines)
