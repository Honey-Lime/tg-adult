"""
Обработчик статистики по дням.
"""

import logging
import os
import tempfile
from locales import get_text
from keyboards import get_admin_panel_keyboard
import database


async def handle_admin_daily_stats(controller, chat_id: int, message_id: int, lang: str):
    """
    Показывает статистику за последние 7 дней и отправляет CSV-файл со всей историей.
    
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
    
    # Получаем статистику за 7 дней
    stats = database.get_daily_stats(7)
    
    if not stats:
        await controller.send_and_track(
            chat_id,
            text="📊 Нет данных для отображения.",
            track=False
        )
        keyboard = get_admin_panel_keyboard(lang)
        await controller.send_and_track(
            chat_id,
            text=get_text(lang, 'admin_menu_text'),
            reply_markup=keyboard,
            track=False
        )
        return
    
    # Формируем текстовый отчёт
    text_parts = ["📊 Статистика по дням (последние 7 дней):\n"]
    
    for day in stats:
        total_image_ratings = day['image_likes'] + day['image_dislikes']
        total_video_ratings = day['video_likes'] + day['video_dislikes']
        total_ratings = total_image_ratings + total_video_ratings
        
        text_parts.append(
            f"📅 {day['date']}\n"
            f"  👥 Новые пользователи: {day['new_users']}\n"
            f"  ⭐ Оценки фото: {total_image_ratings} (❤️ {day['image_likes']} | 😐 {day['image_dislikes']})\n"
            f"  ⭐ Оценки видео: {total_video_ratings} (❤️ {day['video_likes']} | 😐 {day['video_dislikes']})\n"
            f"  📈 Активные пользователи: {day['active_users']}\n"
            f"  💾 Сохранения фото: {day['image_saves']}\n"
            f"  💾 Сохранения видео: {day['video_saves']}"
        )
    
    # Итоговая строка
    total_new = sum(d['new_users'] for d in stats)
    total_img_likes = sum(d['image_likes'] for d in stats)
    total_img_dislikes = sum(d['image_dislikes'] for d in stats)
    total_vid_likes = sum(d['video_likes'] for d in stats)
    total_vid_dislikes = sum(d['video_dislikes'] for d in stats)
    total_active = sum(d['active_users'] for d in stats)
    total_img_saves = sum(d['image_saves'] for d in stats)
    total_vid_saves = sum(d['video_saves'] for d in stats)
    
    text_parts.append(
        f"\n📊 Итого за 7 дней:\n"
        f"  👥 Новые: {total_new}\n"
        f"  ❤️ Лайки фото: {total_img_likes} | 😐 Дизлайки фото: {total_img_dislikes}\n"
        f"  ❤️ Лайки видео: {total_vid_likes} | 😐 Дизлайки видео: {total_vid_dislikes}\n"
        f"  📈 Активные: {total_active}\n"
        f"  💾 Сохранения фото: {total_img_saves} | 💾 Сохранения видео: {total_vid_saves}"
    )
    
    await controller.send_and_track(
        chat_id,
        text="\n\n".join(text_parts),
        track=False
    )
    
    # Отправляем CSV-файл со всей историей
    csv_content = database.get_all_daily_stats_csv()
    
    if csv_content and not csv_content.startswith("Ошибка"):
        # Создаём временный файл
        tmp_path = os.path.join(tempfile.gettempdir(), "daily_stats.csv")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            
            from aiogram.types import FSInputFile
            document = FSInputFile(tmp_path, filename="daily_stats.csv")
            await controller.bot.send_document(
                chat_id,
                document,
                caption="📁 Полная статистика по дням (CSV)"
            )
        except Exception as e:
            logging.error(f"Error sending CSV file: {e}")
        finally:
            # Удаляем временный файл
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    else:
        await controller.send_and_track(
            chat_id,
            text="❌ Не удалось сформировать файл статистики.",
            track=False
        )
    
    # Возвращаем в админ-меню
    keyboard = get_admin_panel_keyboard(lang)
    await controller.send_and_track(
        chat_id,
        text=get_text(lang, 'admin_menu_text'),
        reply_markup=keyboard,
        track=False
    )
