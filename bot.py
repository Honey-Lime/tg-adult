from config_reader import config
import database

import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.bot_token.get_secret_value())
dp = Dispatcher()
router = Router()

# Теперь храним не одно, а до 10 последних сообщений на чат
message_history = {}  # chat_id -> list of message_id (макс. 10)


# ----- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ -----
async def send_and_track(chat_id: int, text: str = None, photo=None, reply_markup=None):
	"""Отправляет сообщение, сохраняет его ID и удаляет самое старое, если в истории уже 10."""
	# Получаем список сообщений для этого чата
	history = message_history.get(chat_id, [])

	# Если уже есть 10 сообщений, удаляем самое старое
	if len(history) >= 10:
		oldest_id = history.pop(0)  # удаляем из списка
		try:
			await bot.delete_message(chat_id, oldest_id)
		except Exception as e:
			# Сообщение могло быть уже удалено или слишком старое
			print(f"Не удалось удалить самое старое сообщение {oldest_id}: {e}")

	# Отправляем новое сообщение
	if photo:
		sent = await bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=reply_markup)
	else:
		sent = await bot.send_message(chat_id, text=text, reply_markup=reply_markup)

	# Добавляем новый ID в историю
	history.append(sent.message_id)
	message_history[chat_id] = history  # обновляем словарь
	return sent


# ----- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ ИД ИЗ ИСТОРИИ -----
def remove_from_history(chat_id: int, message_id: int):
	"""Убирает конкретный message_id из истории чата, если он там есть."""
	if chat_id in message_history and message_id in message_history[chat_id]:
		message_history[chat_id].remove(message_id)


# ----- КОМАНДЫ -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
	# await create_user(message.chat.id)
	await send_menu(message.chat.id)


@dp.message(Command("next"))
async def cmd_next(message: types.Message):
	await send_picture(message.chat.id)


# ----- ОБРАБОТЧИК КНОПОК -----
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
	await callback.answer()
	chat_id = callback.message.chat.id
	message_id = callback.message.message_id

	if callback.data in ["anime", "real"]:
		# Удаляем сообщение, на котором нажата кнопка (оно исчезает сразу)
		try:
			await bot.delete_message(chat_id, message_id)
			# Убираем его ID из истории, чтобы не пытаться удалить позже
			remove_from_history(chat_id, message_id)
		except Exception as e:
			print(f"Не удалось удалить сообщение {message_id}: {e}")

	# Обрабатываем действие
	if callback.data == "anime":
		await set_style(chat_id, "anime")
		await send_picture(chat_id)
	elif callback.data == "real":
		await set_style(chat_id, "real")
		await send_picture(chat_id)
	elif callback.data == "dislike":
		await send_and_track(chat_id, text="dislike")
	elif callback.data == "menu":
		await send_menu(chat_id)
	elif callback.data == "like":
		await send_and_track(chat_id, text="like")


# ----- ФУНКЦИИ ОТПРАВКИ (используют send_and_track) -----
async def send_menu(chat_id: int):
	keyboard = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="Anime", callback_data="anime"),
		 InlineKeyboardButton(text="Real", callback_data="real")]
	])
	await send_and_track(chat_id, text="Выбери стиль картинок", reply_markup=keyboard)


async def send_picture(chat_id: int):
	image = FSInputFile('test.jpg')
	keyboard = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="😐", callback_data="dislike"),
		 InlineKeyboardButton(text="Menu", callback_data="menu"),
		 InlineKeyboardButton(text="❤️", callback_data="like")]
	])
	await send_and_track(chat_id, photo=image, reply_markup=keyboard)


# ----- ЗАГЛУШКИ ДЛЯ БАЗЫ -----
async def set_style(chat_id: int, style: str):
	print("устанавливаем стиль")


# ----- ЗАПУСК -----
async def main():
	dp.include_router(router)
	await dp.start_polling(bot)


if __name__ == "__main__":
	asyncio.run(main())