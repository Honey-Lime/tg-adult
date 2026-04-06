"""
Модуль для создания клавиатур бота.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import WebAppInfo
import database
from locales import get_text


def get_main_menu_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура главного меню (выбор типа контента и реферальная ссылка).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_anime'), callback_data="anime"),
         InlineKeyboardButton(text=get_text(lang, 'btn_real'), callback_data="real")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_video'), callback_data="video")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_donate'), callback_data="donate")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_referral'), callback_data="referral")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_feedback'), callback_data="feedback")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_language'), callback_data="language")]
    ])


def get_video_menu_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора видео (цена указана в названии).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_top25'), callback_data="video_top25")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_good'), callback_data="video_good")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_free'), callback_data="video_free")]
    ])


def get_picture_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура для изображения (лайк, дизлайк, жалоба, сохранение).
    """
    buttons = [
        InlineKeyboardButton(text=get_text(lang, 'btn_dislike'), callback_data="dislike"),
        InlineKeyboardButton(text=get_text(lang, 'btn_like'), callback_data="like"),
        InlineKeyboardButton(text=get_text(lang, 'btn_report'), callback_data="report"),
        InlineKeyboardButton(text=get_text(lang, 'btn_save'), callback_data="save")
    ]
    keyboard_rows = [buttons[:2], buttons[2:]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def get_save_button_keyboard(image_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура с одной кнопкой "Сохранить" для уже отправленного изображения.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_save'), callback_data=f"save_{image_id}")]
    ])


def get_admin_panel_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура админ-панели.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'admin_users'), callback_data="admin_users")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_moderation'), callback_data="admin_moderation")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_notifications'), callback_data="admin_notifications")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_daily_stats'), callback_data="admin_daily_stats")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_promo_links'), callback_data="admin_promo_links")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_referral_stats'), callback_data="admin_referral_stats")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_load_images'), callback_data="admin_load_images")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_clear_folder'), callback_data="admin_clear_import_folder")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_cleanup_json'), callback_data="admin_cleanup_json")],
        [InlineKeyboardButton(text=get_text(lang, 'admin_logs'), callback_data="admin_logs")]
    ])


def get_moderation_keyboard(image_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура для модерации изображения.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_delete'), callback_data=f"mod_delete_{image_id}"),
         InlineKeyboardButton(text=get_text(lang, 'btn_restore'), callback_data=f"mod_restore_{image_id}")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_change_type'), callback_data=f"mod_change_type_{image_id}")]
    ])


def get_report_reasons_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора причины жалобы.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_report_wrong_type'), callback_data="report_wrong_type")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_report_inappropriate'), callback_data="report_inappropriate")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_report_cancel'), callback_data="report_cancel")]
    ])


def get_web_app_keyboard(chat_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой открытия мини-приложения.
    """
    app_url = f"https://hotpicturesbot.ru/app?user_id={chat_id}&lang={lang}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_open_miniapp'), web_app=WebAppInfo(url=app_url))]
    ])


def get_notifications_menu_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора оповещения для рассылки.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_notification_restored'), callback_data="notification_restored")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_notification_custom'), callback_data="notification_custom")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_notification_cancel'), callback_data="notification_cancel")]
    ])


def get_notification_confirm_keyboard(notification_type: str, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения отправки оповещения.
    notification_type - тип оповещения (например, "restored").
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_send'), callback_data=f"notification_confirm_{notification_type}"),
         InlineKeyboardButton(text=get_text(lang, 'btn_notification_cancel'), callback_data="notification_cancel")]
    ])


def get_video_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура для видео (лайк, дизлайк, сохранение, жалоба).
    """
    buttons = [
        InlineKeyboardButton(text=get_text(lang, 'btn_dislike'), callback_data="video_dislike"),
        InlineKeyboardButton(text=get_text(lang, 'btn_like'), callback_data="video_like"),
        InlineKeyboardButton(text=get_text(lang, 'btn_video_report'), callback_data="video_report"),
        InlineKeyboardButton(text=get_text(lang, 'btn_video_save'), callback_data="video_save")
    ]
    keyboard_rows = [buttons[:2], buttons[2:]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def get_video_save_only_keyboard(video_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура с одной кнопкой "Сохранить 50" для видео после оценки.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_save'), callback_data=f"video_save_{video_id}")]
    ])


def get_video_report_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора причины жалобы на видео.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_report_inappropriate'), callback_data="video_report_inappropriate")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_video_report_cancel'), callback_data="video_report_cancel")]
    ])


def get_promo_links_menu_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура меню рекламных ссылок.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_promo_create'), callback_data="promo_create")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_promo_stats'), callback_data="promo_stats")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_promo_delete'), callback_data="promo_delete")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="admin_menu")]
    ])


def get_promo_delete_list_keyboard(links: list, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура со списком ссылок для удаления.
    links - список словарей с ключами 'id', 'name', 'clicks_count'.
    """
    buttons = []
    for link in links:
        btn_text = f"{link['name']} ({link['clicks_count']} переходов)"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"promo_del_{link['id']}")])
    buttons.append([InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="promo_links_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_clear_folder_confirm_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения очистки папки загрузки.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_confirm'), callback_data="admin_clear_import_folder_confirm"),
         InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="admin_clear_import_folder_cancel")]
    ])


def get_donate_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура пополнения баланса за Telegram Stars.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_donate_100'), callback_data="donate_100")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_donate_500'), callback_data="donate_500")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_donate_1000'), callback_data="donate_1000")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_donate_5000'), callback_data="donate_5000")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="menu")]
    ])


def get_feedback_prompt_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура для режима обратной связи (кнопка Отмена).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_feedback_cancel'), callback_data="feedback_cancel")]
    ])


def get_language_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора языка.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_lang_ru'), callback_data="lang_ru"),
         InlineKeyboardButton(text=get_text(lang, 'btn_lang_en'), callback_data="lang_en")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="menu")]
    ])
