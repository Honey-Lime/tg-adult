"""
Обработчик статистики рекламных ссылок для админ-панели.
Показывает, сколько пользователей зарегистрировалось через каждую рекламную ссылку.
"""
import logging
from database import get_all_promo_links_registration_stats, get_all_promo_links, get_promo_link_by_code
from locales import get_text
from keyboards import get_admin_panel_keyboard


async def handle_admin_referral_stats(controller, chat_id: int, message_id: int, lang: str) -> None:
    """Показывает статистику по всем рекламным ссылкам (регистрации через promo_code)."""
    await controller.delete_current(chat_id, message_id)

    stats = get_all_promo_links_registration_stats()
    promo_links = get_all_promo_links()

    if not stats:
        text = "📊 Статистика рекламных ссылок:\n\n❌ Пока нет регистраций по рекламным ссылкам."
    else:
        # Строим мапу code -> name для красивого отображения
        name_map = {p['code']: p['name'] for p in promo_links}

        lines = ["📊 Статистика рекламных ссылок (регистрации):\n"]
        for i, stat in enumerate(stats, 1):
            code = stat['promo_code']
            name = name_map.get(code, code)
            lines.append(
                f"{i}. 📛 {name} (`{code}`)\n"
                f"   👥 Всего регистраций: {stat['total_users']} | 📅 Сегодня: {stat['today_users']}\n"
            )

        text = "\n".join(lines)

    await controller.send_and_track(chat_id, text=text, track=False)

    # Возвращаем в админ-меню
    keyboard = get_admin_panel_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text="Админ-панель. Выберите действие:",
        reply_markup=keyboard,
        track=False
    )
