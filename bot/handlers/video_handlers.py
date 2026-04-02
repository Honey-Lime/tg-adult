"""
Обработчики видео: выбор типа видео, просмотр, лайки/дизлайки.
"""

import database
from keyboards import get_video_menu_keyboard, get_video_keyboard, get_video_report_keyboard
from locales import get_text


async def handle_video_menu(controller, chat_id: int, message_id: int, lang: str):
    """
    Показ меню выбора видео.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    await controller.delete_current(chat_id, message_id)
    
    user = database.get_user(chat_id)
    coins = user.get('coins', 0) if user else 0
    
    keyboard = get_video_menu_keyboard(lang)
    text = get_text(lang, 'video_menu_text', coins=coins)
    
    await controller.send_and_track(chat_id, text=text, reply_markup=keyboard)


async def handle_video_selection(controller, callback_data: str, chat_id: int, lang: str):
    """
    Обработка выбора конкретного типа видео.
    
    Args:
        controller: Экземпляр BotController
        callback_data: Данные callback (video_top25/video_good/video_free)
        chat_id: ID чата пользователя
        lang: Язык пользователя
    """
    if callback_data == "video_top25":
        await _handle_video_top25(controller, chat_id, lang)
    elif callback_data == "video_good":
        await _handle_video_good(controller, chat_id, lang)
    elif callback_data == "video_free":
        await _handle_video_free(controller, chat_id, lang)


async def _handle_video_top25(controller, chat_id: int, lang: str):
    """Просмотр ТОП-25 видео (стоимость 500 монет)"""
    user = database.get_user(chat_id)
    coins = user.get('coins', 0) if user else 0
    
    if coins < 500:
        await controller.send_and_track(
            chat_id,
            text=f"❌ Недостаточно средств. Для просмотра этого видео нужно 500🪙.\nВаш баланс: {coins}🪙\n\nПополните баланс через /donut",
            track=False
        )
        return
    
    if database.spend_coins(chat_id, 500):
        await controller.send_video(chat_id, 'top25')
    else:
        await controller.send_and_track(chat_id, text=get_text(lang, 'spending_error'), track=False)


async def _handle_video_good(controller, chat_id: int, lang: str):
    """Просмотр 'хорошего' видео (стоимость 200 монет)"""
    user = database.get_user(chat_id)
    coins = user.get('coins', 0) if user else 0
    
    if coins < 200:
        await controller.send_and_track(
            chat_id,
            text=f"❌ Недостаточно средств. Для просмотра этого видео нужно 200🪙.\nВаш баланс: {coins}🪙\n\nПополните баланс через /donut",
            track=False
        )
        return
    
    if database.spend_coins(chat_id, 200):
        await controller.send_video(chat_id, 'good')
    else:
        await controller.send_and_track(chat_id, text=get_text(lang, 'spending_error'), track=False)


async def _handle_video_free(controller, chat_id: int, lang: str):
    """Просмотр бесплатного видео"""
    await controller.send_video(chat_id, 'free')


async def handle_video_like(controller, chat_id: int, message_id: int, lang: str):
    """
    Лайк видео.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления клавиатуры
        lang: Язык пользователя
    """
    if chat_id not in controller.last_video_data:
        await controller.send_and_track(chat_id, text=get_text(lang, 'no_active_video'), track=False)
        return
    
    video = controller.last_video_data[chat_id]
    video_id = video['id']
    
    success = database.video_like(chat_id, video_id)
    
    if success:
        # Оставляем кнопку "Сохранить 50" после оценки
        from keyboards import get_video_save_only_keyboard
        keyboard = get_video_save_only_keyboard(video_id, lang)
        await controller.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )
    else:
        await controller.send_and_track(chat_id, text=get_text(lang, 'error'), track=False)


async def handle_video_dislike(controller, chat_id: int, message_id: int, lang: str):
    """
    Дизлайк видео.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления клавиатуры
        lang: Язык пользователя
    """
    if chat_id not in controller.last_video_data:
        await controller.send_and_track(chat_id, text=get_text(lang, 'no_active_video'), track=False)
        return
    
    video = controller.last_video_data[chat_id]
    video_id = video['id']
    
    success = database.video_dislike(chat_id, video_id)
    
    if success:
        # Оставляем кнопку "Сохранить 50" после оценки
        from keyboards import get_video_save_only_keyboard
        keyboard = get_video_save_only_keyboard(video_id, lang)
        await controller.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )
    else:
        await controller.send_and_track(chat_id, text=get_text(lang, 'error'), track=False)


async def handle_video_report_menu(controller, chat_id: int, message_id: int, lang: str):
    """
    Показ меню выбора причины жалобы на видео.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления
        lang: Язык пользователя
    """
    await controller.delete_current(chat_id, message_id)
    
    keyboard = get_video_report_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text="Выберите причину жалобы на видео:",
        reply_markup=keyboard,
    )


async def handle_video_save(controller, chat_id: int, message_id: int, lang: str, video_id: int = None):
    """
    Сохранение видео (стоимость 50 монет).
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        message_id: ID сообщения для удаления клавиатуры
        lang: Язык пользователя
        video_id: ID видео (опционально, для кнопки после оценки)
    """
    if video_id is None:
        if chat_id not in controller.last_video_data:
            await controller.send_and_track(chat_id, text=get_text(lang, 'no_active_video'), track=False)
            return
        video = controller.last_video_data[chat_id]
        video_id = video['id']
    
    # Проверка баланса
    user = database.get_user(chat_id)
    coins = user.get('coins', 0) if user else 0
    
    if coins < 50:
        await controller.send_and_track(
            chat_id,
            text=f"❌ Недостаточно средств. Для сохранения видео нужно 50🪙.\nВаш баланс: {coins}🪙\n\nПополните баланс через /donut",
            track=False
        )
        return
    
    success = database.video_save(chat_id, video_id)
    
    if success:
        await controller.remove_keyboard(chat_id, message_id)
        
        # Возврат в меню выбора видео
        user = database.get_user(chat_id)
        coins = user.get('coins', 0) if user else 0
        keyboard = get_video_menu_keyboard(lang)
        await controller.send_and_track(
            chat_id,
            text=f"Баланс: {coins}🪙\nВыберите видео:",
            reply_markup=keyboard,
        )
    else:
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'insufficient_coins'),
            track=False,
        )


async def handle_video_report(controller, chat_id: int, lang: str):
    """
    Отправка жалобы на видео.
    
    Args:
        controller: Экземпляр BotController
        chat_id: ID чата пользователя
        lang: Язык пользователя
    """
    if chat_id not in controller.last_video_data:
        await controller.send_and_track(chat_id, text="Ошибка: видео не найдено", track=False)
        return
    
    video = controller.last_video_data[chat_id]
    video_id = video['id']
    
    database.video_report(chat_id, video_id)
    database.add_coins(chat_id, 1)
    
    await controller.send_and_track(chat_id, text=get_text(lang, 'complaint_sent'), track=False)
    
    # Возврат в меню выбора видео
    user = database.get_user(chat_id)
    coins = user.get('coins', 0) if user else 0
    keyboard = get_video_menu_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text=f"Баланс: {coins}🪙\nВыберите видео:",
        reply_markup=keyboard,
    )
