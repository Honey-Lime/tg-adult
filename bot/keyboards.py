"""
Модуль для создания клавиатур бота.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import WebAppInfo
import database


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура главного меню (выбор типа контента и реферальная ссылка).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼Аниме", callback_data="anime"),
         InlineKeyboardButton(text="🖼Фото", callback_data="real")],
        [InlineKeyboardButton(text="🎞Видео", callback_data="video")],
        [InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="referral")]
    ])


def get_video_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора видео (цена указана в названии).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ТОП25 🪙500", callback_data="video_top25")],
        [InlineKeyboardButton(text="Хорошее 🪙200", callback_data="video_good")],
        [InlineKeyboardButton(text="Без оценки", callback_data="video_free")]
    ])


def get_picture_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для изображения (лайк, дизлайк, жалоба, сохранение).
    """
    buttons = [
        InlineKeyboardButton(text="😐", callback_data="dislike"),
        InlineKeyboardButton(text="❤️", callback_data="like"),
        InlineKeyboardButton(text="⚠️ Не тот тип\Жалоба", callback_data="report"),
        InlineKeyboardButton(text="Сохранить 25🪙", callback_data="save")
    ]
    keyboard_rows = [buttons[:2], buttons[2:]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def get_save_button_keyboard(image_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура с одной кнопкой "Сохранить" для уже отправленного изображения.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сохранить 25🪙", callback_data=f"save_{image_id}")]
    ])


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура админ-панели.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🛡 Модерация", callback_data="admin_moderation")],
        [InlineKeyboardButton(text="📢 Оповещения", callback_data="admin_notifications")],
        [InlineKeyboardButton(text="📥 Загрузить изображения", callback_data="admin_load_images")]
    ])


def get_moderation_keyboard(image_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для модерации изображения.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"mod_delete_{image_id}"),
         InlineKeyboardButton(text="✅ Восстановить", callback_data=f"mod_restore_{image_id}")]
    ])


def get_report_reasons_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора причины жалобы.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="У изображения не тот тип", callback_data="report_wrong_type")],
        [InlineKeyboardButton(text="Контент неприемлем", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="Отмена", callback_data="report_cancel")]
    ])


def get_web_app_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой открытия мини-приложения.
    """
    app_url = f"https://hotpicturesbot.ru/app?user_id={chat_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть мини-приложение", web_app=WebAppInfo(url=app_url))]
    ])
def get_notifications_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора оповещения для рассылки.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Работа бота восстановлена", callback_data="notification_restored")],
        [InlineKeyboardButton(text="Свое сообщение", callback_data="notification_custom")],
        [InlineKeyboardButton(text="Отмена", callback_data="notification_cancel")]
    ])


def get_notification_confirm_keyboard(notification_type: str) -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения отправки оповещения.
    notification_type - тип оповещения (например, "restored").
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data=f"notification_confirm_{notification_type}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="notification_cancel")]
    ])