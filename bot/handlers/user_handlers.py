"""
Обработчики действий пользователя: лайки, дизлайки, сохранения изображений.
"""

import database
from keyboards import get_save_button_keyboard
from locales import get_text


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


async def handle_save_from_history(controller, callback_data: str, chat_id: int, lang: str):
    """
    Сохранение изображения из истории (кнопка на старом сообщении).
    
    Args:
        controller: Экземпляр BotController
        callback_data: Данные callback (save_{image_id})
        chat_id: ID чата пользователя
        lang: Язык пользователя
    """
    import logging
    try:
        image_id = int(callback_data.split('_')[1])
    except (IndexError, ValueError):
        await controller.send_and_track(chat_id, text=get_text(lang, 'callback_error'), track=False)
        return
    
    # Получаем message_id из callback сообщения
    callback_message_id = None
    # LOG: Отладка проблемы с message_id
    logging.info(f"[SAVE_FROM_HISTORY] chat_id={chat_id}, image_id={image_id}, callback_data={callback_data}")
    logging.info(f"[SAVE_FROM_HISTORY] controller.last_image_message_id={controller.last_image_message_id.get(chat_id)}")
    
    success = database.save(chat_id, image_id)
    
    logging.info(f"[SAVE_FROM_HISTORY] database.save result: success={success}")
    
    if success:
        target_message_id = controller.last_image_message_id.get(chat_id)
        logging.info(f"[SAVE_FROM_HISTORY] Removing keyboard from message_id={target_message_id}")
        await controller.remove_keyboard(chat_id, target_message_id)
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
