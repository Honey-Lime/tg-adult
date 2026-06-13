"""Тестовые админ-действия."""

import database
from keyboards import get_admin_test_subscription_keyboard


TEST_SUBSCRIPTION_SECONDS = {
    "admin_test_sub_minute": 60,
    "admin_test_sub_day": 24 * 60 * 60,
    "admin_test_sub_month": 30 * 24 * 60 * 60,
}


async def handle_admin_test(controller, chat_id: int, message_id: int, lang: str):
    """Показывает меню тестового добавления подписки."""
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        await controller.delete_current(chat_id, message_id)
        return

    await controller.send_and_track(
        chat_id,
        text="🧪 ТЕСТ: сколько времени добавить в подписку?",
        reply_markup=get_admin_test_subscription_keyboard(lang),
        track=False,
    )


async def handle_admin_test_subscription(controller, callback_data: str, chat_id: int, lang: str):
    """Добавляет админу выбранное время подписки."""
    if chat_id not in controller.admin_ids:
        await controller.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
        return

    seconds = TEST_SUBSCRIPTION_SECONDS.get(callback_data)
    if not seconds:
        await controller.send_and_track(chat_id, text="❌ Неизвестный период", track=False)
        return

    if database.add_subscription_time(chat_id, seconds):
        await controller.send_and_track(chat_id, text="✅ Время добавлено в подписку", track=False)
    else:
        await controller.send_and_track(chat_id, text="❌ Не удалось добавить время", track=False)
