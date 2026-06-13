"""
Обработчики действий пользователя: лайки, дизлайки, сохранения изображений.
"""

import asyncio
import aiohttp
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import database
from keyboards import get_save_button_keyboard
from locales import get_text

# URL miniapp API для очистки кэша
MINIAPP_API_URL = "http://localhost:8000"


def get_lootbox_again_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_lootbox_again'), callback_data="lootbox")]
    ])


def get_lootbox_top_up_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_top_up_balance'), callback_data="donate")]
    ])

async def clear_miniapp_cache(user_id: int):
    """Очищает кэш miniapp для пользователя после сохранения изображения."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{MINIAPP_API_URL}/api/clear_cache", params={"user_id": user_id}) as response:
                if response.status == 200:
                    import logging
                    logging.info(f"Cleared miniapp cache for user_id={user_id}")
                else:
                    import logging
                    logging.warning(f"Failed to clear miniapp cache: {response.status}")
    except Exception as e:
        import logging
        logging.error(f"Error clearing miniapp cache: {e}")


async def handle_like(controller, chat_id: int, message_id: int, lang: str):
    """
    Лайк изображения.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для редактирования
        lang: Язык пользователя
    """
    import logging
    user = database.get_user(chat_id)
    
    logging.info(f"[HANDLE_LIKE] chat_id={chat_id}, message_id={message_id}, last_watched={user.get('last_watched') if user else None}")
    logging.info(f"[HANDLE_LIKE] Before edit: last_image_message_id={controller.last_image_message_id.get(chat_id)}")
    
    if user and user.get('last_watched'):
        image_id = user['last_watched']
        await controller.edit_message_to_save_button(chat_id, message_id, image_id, lang)
        logging.info(f"[HANDLE_LIKE] Edited message {message_id} to add save button for image {image_id}")
    else:
        await controller.delete_current(chat_id, message_id)
        logging.info(f"[HANDLE_LIKE] Deleted message {message_id}")
    
    database.like(chat_id)
    await controller.send_picture(chat_id)
    logging.info(f"[HANDLE_LIKE] After send_picture: last_image_message_id={controller.last_image_message_id.get(chat_id)}")


async def handle_dislike(controller, chat_id: int, message_id: int, lang: str):
    """
    Дизлайк изображения.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для редактирования
        lang: Язык пользователя
    """
    import logging
    user = database.get_user(chat_id)
    
    logging.info(f"[HANDLE_DISLIKE] chat_id={chat_id}, message_id={message_id}, last_watched={user.get('last_watched') if user else None}")
    logging.info(f"[HANDLE_DISLIKE] Before edit: last_image_message_id={controller.last_image_message_id.get(chat_id)}")
    
    if user and user.get('last_watched'):
        image_id = user['last_watched']
        await controller.edit_message_to_save_button(chat_id, message_id, image_id, lang)
        logging.info(f"[HANDLE_DISLIKE] Edited message {message_id} to add save button for image {image_id}")
    else:
        await controller.delete_current(chat_id, message_id)
        logging.info(f"[HANDLE_DISLIKE] Deleted message {message_id}")
    
    database.dislike(chat_id)
    await controller.send_picture(chat_id)
    logging.info(f"[HANDLE_DISLIKE] After send_picture: last_image_message_id={controller.last_image_message_id.get(chat_id)}")


async def handle_save_from_history(controller, callback_data: str, chat_id: int, message_id: int, lang: str):
    """
    Сохранение изображения из истории (кнопка на старом сообщении).
    
    Args:
        controller: Экземпляр BotController
        callback_data: Данные callback (save_{image_id})
        chat_id: ID чата пользователя
        message_id: ID сообщения, где была нажата кнопка
        lang: Язык пользователя
    """
    import logging
    try:
        image_id = int(callback_data.split('_')[1])
    except (IndexError, ValueError):
        await controller.send_and_track(chat_id, text=get_text(lang, 'callback_error'), track=False)
        return
    
    logging.info(f"[SAVE_FROM_HISTORY] chat_id={chat_id}, image_id={image_id}, message_id={message_id}, callback_data={callback_data}")
    
    success = database.save(chat_id, image_id)
    
    logging.info(f"[SAVE_FROM_HISTORY] database.save result: success={success}")
    
    if success:
        # Очищаем кэш miniapp
        await clear_miniapp_cache(chat_id)
        
        logging.info(f"[SAVE_FROM_HISTORY] Removing keyboard from message_id={message_id}")
        await controller.remove_keyboard(chat_id, message_id)
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'saved_message'),
            track=False,
        )
    else:
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'insufficient_coins'),
            track=False,
        )


async def handle_save_current(controller, chat_id: int, message_id: int, lang: str):
    """
    Сохранение текущего изображения.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения
        lang: Язык пользователя
    """
    user = database.get_user(chat_id)
    
    if not user:
        await controller.send_picture(chat_id)
        return
    
    image_id = user.get('last_watched')
    
    if image_id is None:
        await controller.send_picture(chat_id)
        return
    
    # Проверка баланса
    if user.get('coins', 0) < 25:
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'insufficient_coins'),
            track=False,
        )
        return
    
    # Лайк и сохранение
    database.like(chat_id)
    success = database.save(chat_id, image_id)
    
    if success:
        # Очищаем кэш miniapp
        await clear_miniapp_cache(chat_id)
        
        await controller.remove_keyboard(chat_id, message_id)
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'saved_message'),
            track=False,
        )
        await controller.send_picture(chat_id)
    else:
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'save_error'),
            track=False,
        )


async def handle_lootbox(controller, chat_id: int, lang: str):
    """Лутбокс подписки: списывает 50 монет, кидает кость, при 6 выдаёт 30 минут."""
    if not database.spend_coins(chat_id, 50):
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'lootbox_insufficient_coins'),
            reply_markup=get_lootbox_top_up_keyboard(lang),
            track=False,
        )
        return

    dice_message = await controller.bot.send_dice(chat_id=chat_id, emoji="🎲")
    await asyncio.sleep(4)
    if dice_message.dice and dice_message.dice.value == 6:
        database.add_subscription_time(chat_id, 30 * 60)
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'lootbox_win'),
            reply_markup=get_lootbox_again_keyboard(lang),
            track=False,
        )
    else:
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'lootbox_lose'),
            reply_markup=get_lootbox_again_keyboard(lang),
            track=False,
        )
