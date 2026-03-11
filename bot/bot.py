# bot.py
"""
Telegram Bot для оценки и сохранения изображений (аниме/реальные фото).
ООП-версия с инкапсуляцией состояний и обработчиков.
"""

import logging
import asyncio
from typing import Dict, Optional, List
import os

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters.command import Command
from aiogram.types import (
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	FSInputFile,
	BotCommand,
	CallbackQuery,
	Message,
	WebAppInfo,
)

from config_reader import config
import database

logging.basicConfig(level=logging.INFO)


class BotController:
	"""
	Контроллер телеграм-бота.
	Управляет состояниями пользователей и обработкой всех команд/колбэков.
	"""

	def __init__(self, token: str, admin_ids: List[int]):
		self.bot = Bot(token=token)
		self.dp = Dispatcher()
		self.router = Router()
		self.admin_ids = admin_ids
		self.bot_username = None

		# Хранилища данных для каждого пользователя (in-memory)
		self.message_history: Dict[int, List[int]] = {}		  # chat_id -> список ID сообщений (макс. 10)
		self.last_image_path: Dict[int, str] = {}				# chat_id -> путь к последней картинке
		self.last_image_data: Dict[int, dict] = {}			   # chat_id -> данные последней картинки (id, type, ...)
		self.last_image_message_id: Dict[int, int] = {}		  # chat_id -> message_id последней картинки
		self.user_processing: Dict[int, bool] = {}			   # chat_id -> флаг обработки (защита от повторных нажатий)
		self.moderation_queues: Dict[int, List[dict]] = {}  # очередь модерации для каждого админа
		self.last_moderation_message_id: Dict[int, int] = {}  # последнее сообщение модерации

		# +++ Защита от спама +++
		self.last_picture_time: Dict[int, float] = {}			# chat_id -> время последней отправки картинки (для rate limit)
		self.sending_picture: Dict[int, bool] = {}			   # chat_id -> флаг, выполняется ли сейчас отправка картинки

		self._register_handlers()
		# Инициализация БД для истории сообщений
		database.init_db()
		self._load_message_history_from_db()


	def _register_handlers(self) -> None:
		self.router.message.register(self.cmd_start, Command("start"))
		self.router.message.register(self.cmd_app, Command("app"))
		self.router.message.register(self.cmd_admin, Command("admin"))
		self.router.callback_query.register(self.process_callback)


	# ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

	async def set_bot_commands(self) -> None:
		commands = [
			BotCommand(command="start", description="Запустить бота / сменить тип"),
			BotCommand(command="app", description="Открыть мини-приложение"),
			BotCommand(command="admin", description="Админ-панель"),
		]
		await self.bot.set_my_commands(commands)

	async def send_and_track(
			self,
			chat_id: int,
			text: Optional[str] = None,
			photo=None,
			reply_markup: Optional[InlineKeyboardMarkup] = None,
			track: bool = True,
	) -> types.Message:
		# Проверяем лимит и удаляем самое старое, если нужно
		if track:
			count = database.count_messages(chat_id)
			if count >= 10:
				oldest_id = database.get_oldest_message(chat_id)
				if oldest_id:
					try:
						await self.bot.delete_message(chat_id, oldest_id)
					except Exception as e:
						print(f"Не удалось удалить самое старое сообщение {oldest_id}: {e}")
					# В любом случае удаляем запись из БД
					database.delete_message_record(chat_id, oldest_id)
					# Также удаляем из in-memory списка
					if chat_id in self.message_history and oldest_id in self.message_history[chat_id]:
						self.message_history[chat_id].remove(oldest_id)

		# Отправка сообщения
		if photo:
			sent = await self.bot.send_photo(
				chat_id,
				photo=photo,
				caption=text,
				reply_markup=reply_markup,
				protect_content=True,
			)
		else:
			sent = await self.bot.send_message(
				chat_id,
				text=text or "",
				reply_markup=reply_markup,
			)

		# Если нужно отслеживать – сохраняем в БД и в память
		if track:
			database.add_message_record(chat_id, sent.message_id)
			self.message_history.setdefault(chat_id, []).append(sent.message_id)

		return sent

	def remove_from_history(self, chat_id: int, message_id: int) -> None:
		if chat_id in self.message_history and message_id in self.message_history[chat_id]:
			self.message_history[chat_id].remove(message_id)
		# Удаляем из БД в любом случае
		database.delete_message_record(chat_id, message_id)

	def _load_message_history_from_db(self):
		"""Восстанавливает message_history из базы данных."""
		db_history = database.load_all_message_history()
		for chat_id, msg_ids in db_history.items():
			# Оставляем только последние 10 (на случай, если в БД больше)
			self.message_history[chat_id] = msg_ids[-10:]
		print(f"[INFO] Loaded message history for {len(self.message_history)} chats")


	async def edit_message_to_save_button(self, chat_id: int, message_id: int, image_id: int) -> None:
		keyboard = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Сохранить 25🪙", callback_data=f"save_{image_id}")]
		])
		try:
			await self.bot.edit_message_reply_markup(
				chat_id=chat_id,
				message_id=message_id,
				reply_markup=keyboard,
				business_connection_id=None,
			)
			print(f"[OK] Сообщение {message_id} отредактировано, добавлена кнопка save_{image_id}")
		except Exception as e:
			print(f"[ОШИБКА] Не удалось отредактировать сообщение {message_id}: {type(e).__name__}: {e}")


	async def delete_current(self, chat_id: int, message_id: int) -> None:
		try:
			await self.bot.delete_message(chat_id, message_id)
			self.remove_from_history(chat_id, message_id)
			if chat_id in self.last_image_message_id and self.last_image_message_id[chat_id] == message_id:
				del self.last_image_message_id[chat_id]
		except Exception as e:
			print(f"Не удалось удалить сообщение {message_id}: {e}")


	async def remove_keyboard(self, chat_id: int, message_id: int) -> None:
		"""Убирает клавиатуру с сообщения (оставляет только контент)."""
		try:
			await self.bot.edit_message_reply_markup(
				chat_id=chat_id,
				message_id=message_id,
				reply_markup=None,
				business_connection_id=None
			)
		except Exception as e:
			print(f"Не удалось убрать клавиатуру с сообщения {message_id}: {e}")


	# ==================== ОБРАБОТЧИКИ КОМАНД ====================

	async def cmd_start(self, message: Message) -> None:
		chat_id = message.chat.id
		referrer_id = None

		# Ручной разбор аргументов команды
		if message.text and ' ' in message.text:
			parts = message.text.split(maxsplit=1)
			if len(parts) == 2 and parts[1].isdigit():
				referrer_id = int(parts[1])
				if referrer_id == chat_id:
					referrer_id = None

		# Получаем пользователя и флаг создания
		user, created = database.get_or_create_user(chat_id, referrer_id)

		if user is None:
			# Ошибка при получении/создании пользователя
			await message.answer("❌ Произошла ошибка при регистрации. Попробуйте позже.")
			return

		print(user)  # для отладки

		# Если пользователь только что создан – уведомляем админов
		if created:
			for admin_id in self.admin_ids:
				try:
					await self.bot.send_message(
						admin_id,
						f"🆕 Новый пользователь: {chat_id}"
					)
				except Exception as e:
					print(f"Не удалось отправить уведомление админу {admin_id}: {e}")
			print(f"Новый пользователь зарегистрирован: {chat_id}, реферер: {referrer_id}")

		# Удаляем последнюю картинку, если она есть
		if chat_id in self.last_image_message_id:
			try:
				await self.bot.delete_message(chat_id, self.last_image_message_id[chat_id])
				self.remove_from_history(chat_id, self.last_image_message_id[chat_id])
			except Exception as e:
				print(f"Не удалось удалить последнюю картинку: {e}")
			finally:
				del self.last_image_message_id[chat_id]

		await self.send_menu(chat_id)


	async def cmd_app(self, message: Message) -> None:
		chat_id = message.chat.id
		# URL вашего мини-приложения (замените на реальный домен с HTTPS)
		app_url = f"https://hotpicturesbot.ru/app?user_id={chat_id}"
		keyboard = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Открыть мини-приложение", web_app=WebAppInfo(url=app_url))]
		])
		await message.answer("Нажмите кнопку, чтобы открыть мини-приложение:", reply_markup=keyboard)

	async def cmd_admin(self, message: Message) -> None:
		chat_id = message.chat.id
		if chat_id not in self.admin_ids:
			await message.answer("⛔ У вас нет прав для этой команды.")
			return

		keyboard = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
			[InlineKeyboardButton(text="🛡 Модерация", callback_data="admin_moderation")]
		])
		await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard)

	async def show_moderation_image(self, chat_id: int, current_message_id: int = None):
		if current_message_id:
			await self.delete_current(chat_id, current_message_id)
		images = database.get_images_for_moderation()
		if not images:
			await self.send_and_track(chat_id, text="✅ Нет изображений на модерации.", track=False)
			return
		self.moderation_queues[chat_id] = images
		await self.send_next_moderation_image(chat_id)

	async def send_next_moderation_image(self, chat_id: int):
		# Удаляем предыдущее сообщение модерации, если есть
		if chat_id in self.last_moderation_message_id:
			try:
				await self.bot.delete_message(chat_id, self.last_moderation_message_id[chat_id])
			except:
				pass
			del self.last_moderation_message_id[chat_id]

		if chat_id not in self.moderation_queues or not self.moderation_queues[chat_id]:
			images = database.get_images_for_moderation()
			if not images:
				await self.send_and_track(chat_id, text="✅ Нет изображений на модерации.", track=False)
				return
			self.moderation_queues[chat_id] = images

		image = self.moderation_queues[chat_id][0]
		remaining = len(self.moderation_queues[chat_id]) - 1

		base_path = database.IMAGE_DIR_ANIME if image['type'] == 0 else database.IMAGE_DIR_REAL
		full_path = os.path.join(base_path, image['path'])

		if not os.path.isfile(full_path):
			# Файл отсутствует – удаляем из очереди и пропускаем
			self.moderation_queues[chat_id].pop(0)
			await self.send_next_moderation_image(chat_id)
			return

		caption = f"🛡 Модерация: {image['id']}\nОсталось: {remaining}"
		keyboard = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="❌ Удалить", callback_data=f"mod_delete_{image['id']}"),
			 InlineKeyboardButton(text="✅ Восстановить", callback_data=f"mod_restore_{image['id']}")]
		])
		image_file = FSInputFile(full_path)
		sent = await self.send_and_track(chat_id, photo=image_file, text=caption, reply_markup=keyboard)
		self.last_moderation_message_id[chat_id] = sent.message_id

	# ==================== ОБРАБОТЧИК КОЛБЭКОВ ====================

	async def process_callback(self, callback: CallbackQuery) -> None:
		chat_id = callback.message.chat.id
		message_id = callback.message.message_id

		if self.user_processing.get(chat_id):
			await callback.answer("Подождите, предыдущее действие ещё выполняется")
			return
		self.user_processing[chat_id] = True

		try:
			await callback.answer()

			if callback.data in ["anime", "real"]:
				await self.delete_current(chat_id, message_id)


			# --- Выбор типа контента ---
			if callback.data == "anime":
				database.user_set_type(chat_id, 0)
				await self.send_picture(chat_id)

			elif callback.data == "real":
				database.user_set_type(chat_id, 1)
				await self.send_picture(chat_id)


			# --- Меню ---
			elif callback.data == "menu":
				await self.delete_current(chat_id, message_id)
				await self.send_menu(chat_id)


			# --- Дизлайк ---
			elif callback.data == "dislike":
				user = database.get_user(chat_id)
				if user and user.get('last_watched'):
					image_id = user['last_watched']
					await self.edit_message_to_save_button(chat_id, message_id, image_id)
				else:
					await self.delete_current(chat_id, message_id)
				database.dislike(chat_id)
				await self.send_picture(chat_id)


			# --- Лайк ---
			elif callback.data == "like":
				user = database.get_user(chat_id)
				if user and user.get('last_watched'):
					image_id = user['last_watched']
					await self.edit_message_to_save_button(chat_id, message_id, image_id)
				else:
					await self.delete_current(chat_id, message_id)
				database.like(chat_id)
				await self.send_picture(chat_id)


			# --- Сохранение из истории (кнопка на старом сообщении) ---
			elif callback.data.startswith("save_"):
				try:
					image_id = int(callback.data.split('_')[1])
				except (IndexError, ValueError):
					await callback.answer("Ошибка идентификатора")
					await self.delete_current(chat_id, message_id)
					return

				success = database.save(chat_id, image_id)

				if success:
					await self.remove_keyboard(chat_id, message_id)
					await self.send_and_track(
						chat_id,
						text="✅ Изображение сохранено! 🪙-25",
						track=False,
					)
				else:
					await self.send_and_track(
						chat_id,
						text="❌ Недостаточно монет",
						track=False,
					)


			# --- Сохранение текущей картинки ---
			elif callback.data == "save":
				user = database.get_user(chat_id)
				if not user:
					await self.send_picture(chat_id)
					return
				image_id = user.get('last_watched')
				if image_id is None:
					await self.send_picture(chat_id)
					return

				if user.get('coins', 0) < 25:
					await self.send_and_track(
						chat_id,
						text="❌ Недостаточно монет",
						track=False,
					)
					return

				database.like(chat_id)
				success = database.save(chat_id, image_id)

				if success:
					await self.remove_keyboard(chat_id, message_id)
					await self.send_and_track(
						chat_id,
						text="✅ Изображение сохранено! 🪙-25",
						track=False,
					)
					await self.send_picture(chat_id)
				else:
					await self.send_and_track(
						chat_id,
						text="❌ Ошибка при сохранении",
						track=False,
					)

			elif callback.data == "admin_moderation":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return
				await self.show_moderation_image(chat_id, message_id)

			elif callback.data.startswith("mod_delete_"):
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return
				image_id = int(callback.data.split('_')[2])
				success = database.delete_image(image_id)
				if success:
					await callback.answer("🗑 Изображение удалено")
				else:
					await callback.answer("❌ Ошибка при удалении")
				# Убираем текущее изображение из очереди
				if chat_id in self.moderation_queues and self.moderation_queues[chat_id]:
					self.moderation_queues[chat_id].pop(0)
				await self.send_next_moderation_image(chat_id)

			elif callback.data.startswith("mod_restore_"):
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return
				image_id = int(callback.data.split('_')[2])
				success = database.clear_moderation(image_id)
				if success:
					await callback.answer("✅ Изображение восстановлено")
				else:
					await callback.answer("❌ Ошибка при восстановлении")
				if chat_id in self.moderation_queues and self.moderation_queues[chat_id]:
					self.moderation_queues[chat_id].pop(0)
				await self.send_next_moderation_image(chat_id)


			# --- Жалоба (открывает меню выбора причины) ---
			elif callback.data == "report":
				await self.delete_current(chat_id, message_id)
				keyboard = InlineKeyboardMarkup(inline_keyboard=[
					[InlineKeyboardButton(text="У изображения не тот тип", callback_data="report_wrong_type")],
					[InlineKeyboardButton(text="Контент неприемлем", callback_data="report_inappropriate")],
					[InlineKeyboardButton(text="Отмена", callback_data="report_cancel")]
				])
				await self.send_and_track(
					chat_id,
					text="Выберите причину жалобы:",
					reply_markup=keyboard,
				)


			# --- Подтверждение смены типа ---
			elif callback.data == "report_wrong_type":
				await self.delete_current(chat_id, message_id)
				user = database.get_user(chat_id)
				if not user:
					await self.send_picture(chat_id)
					return
				image_id = user.get('last_watched')
				if image_id is None:
					await self.send_picture(chat_id)
					return

				# Проверяем, является ли пользователь администратором
				if chat_id in self.admin_ids:
					# Админ: сразу меняем тип
					database.toggle_type(chat_id)
					database.add_coins(chat_id, 1)  # начисляем монету
					await self.send_picture(chat_id)
				else:
					# Обычный пользователь: проверяем not_real_type
					not_real = database.get_not_real_type(image_id)
					if not_real is None:
						await self.send_picture(chat_id)
						return
					if not_real:
						# Уже была жалоба – меняем тип
						database.toggle_type(chat_id)
						database.add_coins(chat_id, 1)
						await self.send_picture(chat_id)
					else:
						# Первая жалоба – ставим флаг
						database.set_not_real_type(image_id, True)
						database.add_coins(chat_id, 1)  # начисляем монету
						# Отправляем новую картинку
						await self.send_picture(chat_id)


			# --- Жалоба на неприемлемый контент ---
			elif callback.data == "report_inappropriate":
				await self.delete_current(chat_id, message_id)
				user = database.get_user(chat_id)
				if user and user.get('last_watched'):
					database.set_need_moderate(user['last_watched'])
					database.add_coins(chat_id, 1)  # начисляем монету
				await self.send_picture(chat_id)


			# --- Отмена жалобы ---
			elif callback.data == "report_cancel":
				await self.delete_current(chat_id, message_id)
				await self.send_picture(chat_id)

			elif callback.data == "referral":
				if not self.bot_username:
					# Если по какой-то причине username не получен, получим сейчас
					bot_info = await self.bot.me()
					self.bot_username = bot_info.username
				link = f"https://t.me/{self.bot_username}?start={chat_id}"
				await self.send_and_track(
					chat_id,
					text=f"🔗 Ваша реферальная ссылка:\n{link}\n\nПриглашайте друзей! За каждого нового пользователя вы получите 250 монет.",
					track=False,
				)

			elif callback.data == "admin_users":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				users = database.get_all_users_stats()
				if not users:
					text = "❌ Нет данных о пользователях."
				else:
					lines = ["📊 Статистика пользователей (ID | просмотрено):"]
					for u in users:
						lines.append(f"• {u['user_id']} – {u['viewed_count']} картинок")
					text = "\n".join(lines)

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text=text, track=False)

				# Возвращаем админ-меню
				keyboard = InlineKeyboardMarkup(inline_keyboard=[
					[InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")]
				])
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)


		finally:
			self.user_processing.pop(chat_id, None)


	# ==================== МЕТОДЫ ОТПРАВКИ СООБЩЕНИЙ ====================

	async def send_menu(self, chat_id: int) -> None:
		keyboard = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Anime", callback_data="anime"),
			 InlineKeyboardButton(text="Real", callback_data="real")],
			[InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="referral")]
		])
		await self.send_and_track(chat_id, text="Выбери стиль картинок или получи реферальную ссылку:",
								  reply_markup=keyboard)


	async def send_picture(self, chat_id: int) -> None:
		# +++ Защита от одновременной отправки +++
		if self.sending_picture.get(chat_id, False):
			logging.warning(f"Send picture already in progress for {chat_id}")
			return
		self.sending_picture[chat_id] = True

		try:
			# +++ Rate limit: не чаще 1 раза в секунду +++
			now = asyncio.get_event_loop().time()
			last_time = self.last_picture_time.get(chat_id, 0)
			if now - last_time < 1.0:
				await self.send_and_track(
					chat_id,
					text="⏳ Слишком часто, подождите секунду",
					track=False  # не сохраняем в историю, чтобы не забивать
				)
				return

			result = database.get_image(chat_id)
			if result is None or result[0] is None:
				await self.send_and_track(chat_id, text="Нет доступных изображений")
				return

			image_path, image_data = result
			self.last_image_path[chat_id] = image_path
			self.last_image_data[chat_id] = image_data

			user = database.get_user(chat_id)
			coins = user.get('coins', 0) if user else 0

			current_type = "Аниме" if image_data['type'] == 0 else "Фото"
			caption_text = f"{current_type} | {coins}🪙"

			buttons = [
				InlineKeyboardButton(text="😐", callback_data="dislike"),
				InlineKeyboardButton(text="❤️", callback_data="like"),
				InlineKeyboardButton(text="⚠️ Не тот тип\Жалоба", callback_data="report"),
				# InlineKeyboardButton(text="Menu", callback_data="menu"),
				InlineKeyboardButton(text="Сохранить 25🪙", callback_data="save")
			]
			keyboard_rows = [buttons[:2], buttons[2:]]
			keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

			image = FSInputFile(image_path)
			sent = await self.send_and_track(
				chat_id,
				photo=image,
				text=caption_text,
				reply_markup=keyboard,
			)

			self.last_image_message_id[chat_id] = sent.message_id

			# +++ Обновляем время последней успешной отправки картинки +++
			self.last_picture_time[chat_id] = now

		finally:
			self.sending_picture[chat_id] = False


	# ==================== ЗАПУСК БОТА ====================

	async def start_polling(self) -> None:
		await self.set_bot_commands()
		bot_info = await self.bot.me()
		self.bot_username = bot_info.username

		# Уведомление о запуске
		for admin_id in self.admin_ids:
			try:
				await self.bot.send_message(
					admin_id,
					f"✅ Бот {self.bot_username} запущен и готов к работе!"
				)
			except Exception as e:
				print(f"Не удалось отправить уведомление админу {admin_id}: {e}")

		self.dp.include_router(self.router)
		await self.dp.start_polling(self.bot)


def main() -> None:
	controller = BotController(
		token=config.bot_token.get_secret_value(),
		admin_ids=[7413924512, 5186349076],
	)
	asyncio.run(controller.start_polling())


if __name__ == "__main__":
	main()