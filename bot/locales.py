"""
Файл локализации для бота.
Содержит переводы всех текстов на русский и английский языки.
"""

LOCALES = {
    'ru': {
        # Главное меню
        'main_menu_text': "👋Здесь вы можете выбрать картинки(Аниме, Фото) или видео. \n\n👉В miniapp (/app) вы можете увидеть свои сохраненные картинки, видео и ТОП25.",
        'btn_anime': "🖼Аниме",
        'btn_real': "🖼Фото",
        'btn_video': "🎞Видео",
        'btn_donate': "💰 Пополнить баланс",
        'btn_referral': "🔗 Реферальная ссылка (+250 за пользователя)",
        'btn_feedback': "💬 Обратная связь",
        'feedback_prompt': "Отправьте сообщение и его получит админ бота",
        'btn_feedback_cancel': "❌ Отмена",
        'feedback_sent': "✅ Ваше сообщение успешно отправлено администратору!",
        'feedback_cancelled': "Отменено.",
        'btn_language': "🌐 Language / Язык",
        
        # Выбор языка
        'language_menu_text': "🌐 Выберите язык / Select language:\n\nТекущий язык / Current language: {language}",
        'btn_lang_ru': "🇷🇺 Русский",
        'btn_lang_en': "🇺🇸 English",
        'btn_back': "🔙 Назад",
        
        # Видео меню
        'video_menu_text': "Баланс: {coins}🪙\nВыберите видео:",
        'btn_video_top25': "ТОП25 🪙500",
        'btn_video_good': "Хорошее 🪙200",
        'btn_video_free': "Без оценки",
        
        # Картинка
        'picture_caption': "{type} | {coins}🪙",
        'btn_dislike': "😐",
        'btn_like': "❤️",
        'btn_report': "⚠️ Не тот тип\\Жалоба",
        'btn_save': "Сохранить 25🪙",
        
        # Видео
        'video_caption': "Видео | {coins}🪙",
        'btn_video_save': "Сохранить 50🪙",
        'btn_video_report': "⚠️ Жалоба",
        
        # Жалобы
        'report_reason_text': "Выберите причину жалобы:",
        'btn_report_wrong_type': "У изображения не тот тип",
        'btn_report_inappropriate': "Контент неприемлем",
        'btn_report_cancel': "Отмена",
        
        'video_report_text': "Выберите причину жалобы на видео:",
        'btn_video_report_inappropriate': "Контент неприемлем",
        'btn_video_report_cancel': "Отмена",
        
        # Уведомления
        'saved_message': "✅ Изображение сохранено! 🪙-25",
        'insufficient_coins': "❌ Недостаточно монет",
        'save_error': "❌ Ошибка при сохранении",
        'too_often': "⏳ Слишком часто, подождите секунду",
        'too_often_rating': "⏳ Слишком частые запросы",
        'no_images': "Нет доступных изображений",
        'no_videos': "Нет доступных видео",
        'video_file_missing': "Ошибка: файл видео отсутствует",
        'video_send_error': "❌ Ошибка отправки видео. Попробуйте другое.",
        'coins_added': "✅ +5 монет",
        'error': "❌ Ошибка",
        'complaint_sent': "Жалоба отправлена. Спасибо! +1 монета",
        
        # Пополнение баланса
        'donate_menu_text': "💰 Ваш баланс: {coins}🪙\n\nВыберите тариф для пополнения баланса за Telegram Stars:",
        'btn_donate_100': "100 🪙 - 10 ⭐",
        'btn_donate_500': "500 🪙 - 45 ⭐",
        'btn_donate_1000': "1000 🪙 - 80 ⭐",
        'btn_donate_5000': "5000 🪙 - 350 ⭐",
        'payment_success': "✅ Оплата прошла успешно!\n\nВаш баланс пополнен на {amount}🪙\nСписано: {stars_paid} ⭐",
        'payment_error': "❌ Произошла ошибка при обработке платежа. Пожалуйста, обратитесь к администрации.",
        'insufficient_coins_video': "❌ Недостаточно средств. Для просмотра этого видео нужно {price}🪙.\nВаш баланс: {coins}🪙\n\nПополните баланс через /donut",
        'spending_error': "❌ Ошибка при списании средств. Попробуйте позже.",
        
        # Реферальная ссылка
        'referral_text': "🔗 Ваша реферальная ссылка:\n{link}\n\nПриглашайте друзей! За каждого нового пользователя вы получите 250 монет.",
        
        # Мини-приложение
        'miniapp_prompt': "Нажмите кнопку, чтобы открыть мини-приложение:",
        'btn_open_miniapp': "Открыть мини-приложение",
        
        # Админ-панель
        'admin_menu_text': "Админ-панель. Выберите действие:",
        'admin_denied': "⛔ У вас нет прав для этой команды.",
        'admin_users': "👥 Пользователи",
        'admin_moderation': "🛡 Модерация",
        'admin_notifications': "📢 Оповещения",
        'admin_promo_links': "🔗 Рекламные ссылки",
        'admin_referral_stats': "📊 Статистика рефералов",
        'admin_daily_stats': "📈 Статистика по дням",
        'admin_load_images': "📥 Загрузка контента",
        'admin_clear_folder': "🗑 Очистить папку загрузки",
        'admin_cleanup_json': "🧹 Чистка по json",
        'admin_logs': "📋 Логи",
        
        # Пользователи
        'users_stats_text': "📊 Статистика пользователей (ID | имя | просмотры):",
        'no_users': "❌ Нет данных о пользователях.",
        
        # Модерация
        'moderation_text': "🛡 Модерация: {id}\nОсталось: {remaining}",
        'no_moderation_images': "✅ Нет изображений на модерации.",
        'image_deleted': "🗑 Изображение удалено",
        'image_restore_error': "❌ Ошибка при удалении",
        'image_restored': "✅ Изображение восстановлено",
        'restore_error': "❌ Ошибка при восстановлении",
        'btn_delete': "❌ Удалить",
        'btn_restore': "✅ Восстановить",
        'btn_change_type': "🔄 Сменить тип",
        'type_changed_moderation': "✅ Тип изображения изменён",
        'type_change_error': "❌ Ошибка при смене типа",
        
        # Оповещения
        'notifications_menu_text': "📢 Выберите оповещение для рассылки:",
        'btn_notification_restored': "Работа бота восстановлена",
        'btn_notification_custom': "Свое сообщение",
        'btn_notification_cancel': "Отмена",
        'btn_send': "✅ Отправить",
        'custom_message_prompt': "Следующее сообщение будет отправлено всем пользователям. Напишите текст сообщения:",
        'broadcast_prompt': "📢 Отправить оповещение:\n\n{text}",
        'broadcast_started': "📢 Рассылка сообщения всем пользователям...",
        'no_users_for_broadcast': "❌ Нет пользователей для рассылки.",
        'broadcast_completed': "✅ Рассылка завершена.\nУспешно: {success}\nНе удалось: {fail}",
        'message_not_found': "❌ Не найден текст сообщения. Начните заново.",
        'enter_message': "Пожалуйста, отправьте текстовое сообщение.",
        'restored_message': "Работа бота восстановлена, ждем вас снова",
        
        # Рекламные ссылки
        'promo_links_menu_text': "🔗 Рекламные ссылки. Выберите действие:",
        'btn_promo_create': "➕ Создать ссылку",
        'btn_promo_stats': "📊 Статистика",
        'btn_promo_delete': "🗑 Удалить ссылку",
        'promo_create_prompt': "📝 Введите название для рекламной ссылки.\n\nПервое отправленное сообщение станет названием ссылки, а ссылка сгенерируется автоматически.",
        'promo_created': "✅ Рекламная ссылка создана:\n\n📛 Название: {name}\n🔗 Ссылка: {link}",
        'promo_create_error': "❌ Ошибка при создании ссылки: {error}",
        'promo_stats_text': "📊 Статистика по рекламным ссылкам:\n",
        'promo_stats_empty': "❌ Пока нет созданных ссылок.",
        'promo_delete_text': "🗑 Удаление ссылок. Отправьте номер ссылки для удаления:\n",
        'promo_delete_empty': "🗑 Удаление ссылок:\n\n❌ Пока нет созданных ссылок.",
        'promo_deleted': "🗑 Ссылка \"{name}\" удалена.",
        'delete_error': "❌ Ошибка при удалении ссылки.",
        'invalid_number': "❌ Неверный номер. Введите число от {min} до {max}.",
        'enter_name': "Пожалуйста, отправьте текстовое сообщение с именем ссылки.",
        'enter_number': "Пожалуйста, отправьте номер ссылки для удаления.",
        
        # Загрузка контента
        'loading_content': "🔄 Загрузка контента...",
        'load_complete': "✅ Загрузка завершена.\nДобавлено фото: {photos}\nДобавлено видео: {videos}\nОшибок: {errors}\nВремя выполнения: {time:.2f} сек.",
        'load_error': "❌ Ошибка при загрузке: {error}",
        
        # Очистка папки
        'clear_folder_text': "🗑 Очистка папки загрузки\n\n⚠️ Все файлы и папки в папке 'images/new' будут удалены без возможности восстановления.\n\nВы уверены?",
        'btn_confirm': "✅ Да, удалить все файлы",
        'clear_folder_started': "🗑 Очистка папки загрузки...",
        'clear_folder_complete': "✅ Папка загрузки очищена.\n\nУдалено файлов: {files}\nУдалено папок: {folders}",
        'clear_folder_error': "❌ Ошибка при очистке: {error}",
        
        # Чистка по JSON
        'cleanup_json_started': "🧹 Чистка по JSON...",
        'cleanup_json_complete': "✅ Удалено записей: {deleted}\n⏱ Время выполнения: {time:.2f} сек.\n⚠️ Ошибки:\n{errors}",
        'cleanup_json_no_errors': "✅ Удалено записей: {deleted}\n⏱ Время выполнения: {time:.2f} сек.\n✅ Ошибок нет.",
        
        # Логи
        'getting_logs': "📋 Получение логов...",
        'logs_not_found': "❌ Файл логов не найден.",
        'logs_file_caption': "📁 Файл логов",
        'logs_text': "📋 Последние {count} записей лога:\n```\n{logs}\n```",
        'logs_empty': "Логи пусты.",
        'logs_error': "Ошибка чтения логов: {error}",
        
        # Ошибки
        'registration_error': "❌ Произошла ошибка при регистрации. Попробуйте позже.",
        'callback_error': "Ошибка идентификатора",
        'processing_wait': "Подождите, предыдущее действие ещё выполняется",
        'no_active_video': "Нет активного видео",
        'type_changed': "Тип успешно изменён",
        'user_not_found': "Пользователь не найден",
        'no_current_image': "Нет текущего изображения",
        'image_not_found': "Изображение не найдено",
        'connection_error': "Ошибка подключения",
    },
    'en': {
        # Главное меню
        'main_menu_text': "👋 Here you can choose pictures (Anime, Photo) or videos.\n\n👉 In miniapp (/app) you can see your saved pictures, videos and TOP25.",
        'btn_anime': "🖼 Anime",
        'btn_real': "🖼 Photo",
        'btn_video': "🎞 Video",
        'btn_donate': "💰 Top up balance",
        'btn_referral': "🔗 Referral link (+250 per user)",
        'btn_feedback': "💬 Feedback",
        'feedback_prompt': "Send a message and the bot admin will receive it",
        'btn_feedback_cancel': "❌ Cancel",
        'feedback_sent': "✅ Your message has been successfully sent to the administrator!",
        'feedback_cancelled': "Cancelled.",
        'btn_language': "🌐 Language / Язык",
        
        # Выбор языка
        'language_menu_text': "🌐 Select language:\n\nCurrent language: {language}",
        'btn_lang_ru': "🇷🇺 Русский",
        'btn_lang_en': "🇺🇸 English",
        'btn_back': "🔙 Back",
        
        # Видео меню
        'video_menu_text': "Balance: {coins}🪙\nSelect video:",
        'btn_video_top25': "TOP25 🪙500",
        'btn_video_good': "Good 🪙200",
        'btn_video_free': "Unrated",
        
        # Картинка
        'picture_caption': "{type} | {coins}🪙",
        'btn_dislike': "😐",
        'btn_like': "❤️",
        'btn_report': "⚠️ Wrong type\\Report",
        'btn_save': "Save 25🪙",
        
        # Видео
        'video_caption': "Video | {coins}🪙",
        'btn_video_save': "Save 50🪙",
        'btn_video_report': "⚠️ Report",
        
        # Жалобы
        'report_reason_text': "Select report reason:",
        'btn_report_wrong_type': "Wrong image type",
        'btn_report_inappropriate': "Inappropriate content",
        'btn_report_cancel': "Cancel",
        
        'video_report_text': "Select video report reason:",
        'btn_video_report_inappropriate': "Inappropriate content",
        'btn_video_report_cancel': "Cancel",
        
        # Уведомления
        'saved_message': "✅ Image saved! 🪙-25",
        'insufficient_coins': "❌ Insufficient coins",
        'save_error': "❌ Error saving",
        'too_often': "⏳ Too often, wait a second",
        'too_often_rating': "⏳ Too frequent requests",
        'no_images': "No images available",
        'no_videos': "No videos available",
        'video_file_missing': "Error: video file missing",
        'video_send_error': "❌ Error sending video. Try another one.",
        'coins_added': "✅ +5 coins",
        'error': "❌ Error",
        'complaint_sent': "Report sent. Thank you! +1 coin",
        
        # Пополнение баланса
        'donate_menu_text': "💰 Your balance: {coins}🪙\n\nSelect top-up plan for Telegram Stars:",
        'btn_donate_100': "100 🪙 - 10 ⭐",
        'btn_donate_500': "500 🪙 - 45 ⭐",
        'btn_donate_1000': "1000 🪙 - 80 ⭐",
        'btn_donate_5000': "5000 🪙 - 350 ⭐",
        'payment_success': "✅ Payment successful!\n\nYour balance topped up by {amount}🪙\nCharged: {stars_paid} ⭐",
        'payment_error': "❌ Payment processing error. Please contact administration.",
        'insufficient_coins_video': "❌ Insufficient funds. This video costs {price}🪙.\nYour balance: {coins}🪙\n\nTop up via /donut",
        'spending_error': "❌ Error deducting funds. Try again later.",
        
        # Реферальная ссылка
        'referral_text': "🔗 Your referral link:\n{link}\n\nInvite friends! You'll get 250 coins for each new user.",
        
        # Мини-приложение
        'miniapp_prompt': "Click the button to open mini-app:",
        'btn_open_miniapp': "Open mini-app",
        
        # Админ-панель
        'admin_menu_text': "Admin panel. Select action:",
        'admin_denied': "⛔ Access denied.",
        'admin_users': "👥 Users",
        'admin_moderation': "🛡 Moderation",
        'admin_notifications': "📢 Notifications",
        'admin_promo_links': "🔗 Promo links",
        'admin_referral_stats': "📊 Referral stats",
        'admin_daily_stats': "📈 Daily stats",
        'admin_load_images': "📥 Load content",
        'admin_clear_folder': "🗑 Clear import folder",
        'admin_cleanup_json': "🧹 Cleanup by json",
        'admin_logs': "📋 Logs",
        
        # Пользователи
        'users_stats_text': "📊 User statistics (ID | name | views):",
        'no_users': "❌ No user data.",
        
        # Модерация
        'moderation_text': "🛡 Moderation: {id}\nRemaining: {remaining}",
        'no_moderation_images': "✅ No images for moderation.",
        'image_deleted': "🗑 Image deleted",
        'image_restore_error': "❌ Error deleting",
        'image_restored': "✅ Image restored",
        'restore_error': "❌ Error restoring",
        'btn_delete': "❌ Delete",
        'btn_restore': "✅ Restore",
        'btn_change_type': "🔄 Change type",
        'type_changed_moderation': "✅ Image type changed",
        'type_change_error': "❌ Error changing type",
        
        # Оповещения
        'notifications_menu_text': "📢 Select notification for broadcast:",
        'btn_notification_restored': "Bot restored",
        'btn_notification_custom': "Custom message",
        'btn_notification_cancel': "Cancel",
        'btn_send': "✅ Send",
        'custom_message_prompt': "Next message will be sent to all users. Write the message text:",
        'broadcast_prompt': "📢 Send notification:\n\n{text}",
        'broadcast_started': "📢 Broadcasting message to all users...",
        'no_users_for_broadcast': "❌ No users for broadcast.",
        'broadcast_completed': "✅ Broadcast completed.\nSuccess: {success}\nFailed: {fail}",
        'message_not_found': "❌ Message text not found. Start over.",
        'enter_message': "Please send a text message.",
        'restored_message': "Bot restored, waiting for you again",
        
        # Рекламные ссылки
        'promo_links_menu_text': "🔗 Promo links. Select action:",
        'btn_promo_create': "➕ Create link",
        'btn_promo_stats': "📊 Statistics",
        'btn_promo_delete': "🗑 Delete link",
        'promo_create_prompt': "📝 Enter name for promo link.\n\nFirst sent message will be the link name, link will be generated automatically.",
        'promo_created': "✅ Promo link created:\n\n📛 Name: {name}\n🔗 Link: {link}",
        'promo_create_error': "❌ Error creating link: {error}",
        'promo_stats_text': "📊 Promo links statistics:\n",
        'promo_stats_empty': "❌ No links created yet.",
        'promo_delete_text': "🗑 Delete links. Send link number to delete:\n",
        'promo_delete_empty': "🗑 Delete links:\n\n❌ No links created yet.",
        'promo_deleted': "🗑 Link \"{name}\" deleted.",
        'delete_error': "❌ Error deleting link.",
        'invalid_number': "❌ Invalid number. Enter number from {min} to {max}.",
        'enter_name': "Please send a text message with link name.",
        'enter_number': "Please send link number to delete.",
        
        # Загрузка контента
        'loading_content': "🔄 Loading content...",
        'load_complete': "✅ Loading completed.\nPhotos added: {photos}\nVideos added: {videos}\nErrors: {errors}\nExecution time: {time:.2f} sec.",
        'load_error': "❌ Error loading: {error}",
        
        # Очистка папки
        'clear_folder_text': "🗑 Clear import folder\n\n⚠️ All files and folders in 'images/new' will be deleted without recovery.\n\nAre you sure?",
        'btn_confirm': "✅ Yes, delete all files",
        'clear_folder_started': "🗑 Clearing import folder...",
        'clear_folder_complete': "✅ Import folder cleared.\n\nFiles deleted: {files}\nFolders deleted: {folders}",
        'clear_folder_error': "❌ Error clearing: {error}",
        
        # Чистка по JSON
        'cleanup_json_started': "🧹 Cleaning by JSON...",
        'cleanup_json_complete': "✅ Records deleted: {deleted}\n⏱ Execution time: {time:.2f} sec.\n⚠️ Errors:\n{errors}",
        'cleanup_json_no_errors': "✅ Records deleted: {deleted}\n⏱ Execution time: {time:.2f} sec.\n✅ No errors.",
        
        # Логи
        'getting_logs': "📋 Getting logs...",
        'logs_not_found': "❌ Log file not found.",
        'logs_file_caption': "📁 Log file",
        'logs_text': "📋 Last {count} log entries:\n```\n{logs}\n```",
        'logs_empty': "Logs are empty.",
        'logs_error': "Error reading logs: {error}",
        
        # Ошибки
        'registration_error': "❌ Registration error. Try again later.",
        'callback_error': "Identifier error",
        'processing_wait': "Wait, previous action is still processing",
        'no_active_video': "No active video",
        'type_changed': "Type changed successfully",
        'user_not_found': "User not found",
        'no_current_image': "No current image",
        'image_not_found': "Image not found",
        'connection_error': "Connection error",
    }
}


def get_text(lang: str, key: str, **kwargs) -> str:
    """
    Получает текст для указанного языка и ключа.
    Если язык не найден, использует 'ru' как fallback.
    Поддерживает форматирование через kwargs.
    """
    locale = LOCALES.get(lang, LOCALES['ru'])
    text = locale.get(key, LOCALES['ru'].get(key, f"MISSING:{key}"))
    
    # Форматирование текста, если переданы аргументы
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass  # Игнорируем ошибки форматирования
    
    return text


def get_language_name(lang: str) -> str:
    """Возвращает название языка на соответствующем языке."""
    names = {
        'ru': 'Русский',
        'en': 'English'
    }
    return names.get(lang, 'Русский')
