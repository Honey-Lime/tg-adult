"""
Обработчик промо-ссылок.
"""

import database
from keyboards import get_promo_links_menu_keyboard, get_admin_panel_keyboard
from locales import get_text


async def handle_admin_promo_links(controller, chat_id: int, message_id: int, lang: str):
    """
    Показ меню управления промо-ссылками.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        await controller.delete_current(chat_id, message_id)
        return
    
    await controller.delete_current(chat_id, message_id)
    
    keyboard = get_promo_links_menu_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text="🔗 Рекламные ссылки. Выберите действие:",
        reply_markup=keyboard,
        track=False
    )


async def handle_promo_create(controller, chat_id: int, message_id: int, lang: str):
    """
    Начало создания промо-ссылки (ожидание имени).
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        return
    
    await controller.delete_current(chat_id, message_id)
    
    controller.waiting_for_promo_name[chat_id] = True
    
    await controller.send_and_track(
        chat_id,
        text="📝 Введите название для рекламной ссылки.\n\nПервое отправленное сообщение станет названием ссылки, а ссылка сгенерируется автоматически.",
        track=False
    )


async def handle_promo_stats(controller, chat_id: int, message_id: int, lang: str):
    """
    Показ статистики промо-ссылок.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        return
    
    await controller.delete_current(chat_id, message_id)
    
    promo_links = database.get_all_promo_links()
    
    if not promo_links:
        text = "📊 Статистика по рекламным ссылкам:\n\n❌ Пока нет созданных ссылок."
    else:
        text = await _format_promo_stats(controller, promo_links)
    
    keyboard = get_promo_links_menu_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text=text,
        reply_markup=keyboard,
        track=False
    )


async def _format_promo_stats(controller, promo_links: list) -> str:
    """Форматирует статистику промо-ссылок"""
    lines = ["📊 Статистика по рекламным ссылкам:\n"]
    
    for link in promo_links:
        bot_info = await controller.bot.me()
        promo_url = f"https://t.me/{bot_info.username}?start={link['code']}"
        registrations = link.get('registrations_count', 0)
        lines.append(
            f"📛 {link['name']}\n"
            f"👥 Регистраций: {registrations} | 🔀 Переходов: {link['clicks_count']}\n"
            f"🔗 {promo_url}\n"
        )
    
    return "\n".join(lines)


async def handle_promo_delete(controller, chat_id: int, message_id: int, lang: str):
    """
    Начало удаления промо-ссылки (показ списка).
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        return
    
    await controller.delete_current(chat_id, message_id)
    
    promo_links = database.get_all_promo_links()
    
    if not promo_links:
        text = "🗑 Удаление ссылок:\n\n❌ Пока нет созданных ссылок."
        keyboard = get_promo_links_menu_keyboard(lang)
        await controller.send_and_track(
            chat_id,
            text=text,
            reply_markup=keyboard,
            track=False
        )
    else:
        # Формируем пронумерованный список
        lines = ["🗑 Удаление ссылок. Отправьте номер ссылки для удаления:\n"]
        for i, link in enumerate(promo_links, 1):
            registrations = link.get('registrations_count', 0)
            lines.append(f"{i}. 📛 {link['name']} | 👥 {registrations} рег. | 🔀 {link['clicks_count']} переходов")
        
        text = "\n".join(lines)
        controller.waiting_for_promo_delete[chat_id] = True
        
        await controller.send_and_track(
            chat_id,
            text=text,
            track=False
        )


async def handle_promo_menu_back(controller, chat_id: int, message_id: int, lang: str):
    """
    Возврат в меню промо-ссылок.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        return
    
    await controller.delete_current(chat_id, message_id)
    
    keyboard = get_promo_links_menu_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text="🔗 Рекламные ссылки. Выберите действие:",
        reply_markup=keyboard,
        track=False
    )
