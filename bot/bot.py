# bot.py
"""
Telegram Bot для оценки и сохранения изображений (аниме/реальные фото).
ООП-версия с инкапсуляцией состояний и обработчиков.
"""

import logging
import sys
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
import keyboards
import image_loader
from logging_config import setup_logging

# Настройка логирования
setup_logging(detailed=True)


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

		# Состояние ожидания пользовательского сообщения для рассылки
		self.waiting_for_custom_message: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода сообщения)
		self.pending_custom_message: Dict[int, str] = {}	   # chat_id -> текст сообщения для рассылки

		self._register_handlers()
		# Инициализация БД для истории сообщений
		database.init_db()
		self._load_message_history_from_db()


	def _register_handlers(self) -> None:
		self.router.message.register(self.cmd_start, Command("start"))
		self.router.message.register(self.cmd_app, Command("app"))
		self.router.message.register(self.cmd_admin, Command("admin"))
		self.router.message.register(self.handle_message)
		self.router.callback_query.register(self.process_callback)


	# ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

	async def set_bot_commands(self) -> None:
		commands = [
			BotCommand(command="start", description="Старт / Главное меню"),
			BotCommand(command="app", description="Мини приложение(ТОП, Сохраненные)"),
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
						logging.warning(f"Не удалось удалить самое старое сообщение {oldest_id}: {e}")
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
		logging.info(f"Loaded message history for {len(self.message_history)} chats")

	async def _update_user_profile_from_message(self, message: Message) -> None:
		"""
		Обновляет профиль пользователя на основе данных из сообщения Telegram.
		Вызывается при каждом сообщении или колбэке, где есть информация о пользователе.
		"""
		user = message.from_user
		if not user:
			return
		chat_id = message.chat.id
		first_name = user.first_name
		last_name = user.last_name
		username = user.username
		database.update_user_profile(chat_id, first_name, last_name, username)

	async def _update_user_profile_from_callback(self, callback: CallbackQuery) -> None:
		"""
		Обновляет профиль пользователя на основе данных из колбэка Telegram.
		"""
		user = callback.from_user
		if not user:
			return
		chat_id = user.id
		first_name = user.first_name
		last_name = user.last_name
		username = user.username
		database.update_user_profile(chat_id, first_name, last_name, username)

	async def edit_message_to_save_button(self, chat_id: int, message_id: int, image_id: int) -> None:
		keyboard = keyboards.get_save_button_keyboard(image_id)
		try:
			await self.bot.edit_message_reply_markup(
				chat_id=chat_id,
				message_id=message_id,
				reply_markup=keyboard,
				business_connection_id=None,
			)
			logging.info(f"Сообщение {message_id} отредактировано, добавлена кнопка save_{image_id}")
		except Exception as e:
			logging.error(f"Не удалось отредактировать сообщение {message_id}: {type(e).__name__}: {e}")


	async def delete_current(self, chat_id: int, message_id: int) -> None:
		try:
			await self.bot.delete_message(chat_id, message_id)
			self.remove_from_history(chat_id, message_id)
			if chat_id in self.last_image_message_id and self.last_image_message_id[chat_id] == message_id:
				del self.last_image_message_id[chat_id]
		except Exception as e:
			logging.error(f"Не удалось удалить сообщение {message_id}: {e}")


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
			logging.error(f"Не удалось убрать клавиатуру с сообщения {message_id}: {e}")


	# ==================== ОБРАБОТЧИКИ КОМАНД ====================

	async def cmd_start(self, message: Message) -> None:
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)
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

		logging.debug(f"User object: {user}")  # для отладки

		# Если пользователь только что создан – уведомляем админов
		if created:
			for admin_id in self.admin_ids:
				try:
					await self.bot.send_message(
						admin_id,
						f"🆕 Новый пользователь: {chat_id}"
					)
				except Exception as e:
					logging.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
			first_name = user.get('first_name', '')
			last_name = user.get('last_name', '')
			username = user.get('username', '')
			logging.info(f"Новый пользователь зарегистрирован: {chat_id}, имя: {first_name} {last_name}, username: @{username}, реферер: {referrer_id}")

		# Удаляем последнюю картинку, если она есть
		if chat_id in self.last_image_message_id:
			try:
				await self.bot.delete_message(chat_id, self.last_image_message_id[chat_id])
				self.remove_from_history(chat_id, self.last_image_message_id[chat_id])
			except Exception as e:
				logging.error(f"Не удалось удалить последнюю картинку: {e}")
			finally:
				del self.last_image_message_id[chat_id]

		await self.send_menu(chat_id)


	async def cmd_app(self, message: Message) -> None:
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)
		chat_id = message.chat.id
		keyboard = keyboards.get_web_app_keyboard(chat_id)
		await message.answer("Нажмите кнопку, чтобы открыть мини-приложение:", reply_markup=keyboard)

	async def cmd_admin(self, message: Message) -> None:
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)
		chat_id = message.chat.id
		if chat_id not in self.admin_ids:
			await message.answer("⛔ У вас нет прав для этой команды.")
			return

		keyboard = keyboards.get_admin_panel_keyboard()
		await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard)

	async def handle_message(self, message: Message) -> None:
		"""
		Обработчик текстовых сообщений (не команд).
		Используется для захвата пользовательского сообщения для рассылки.
		"""
		chat_id = message.chat.id
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)

		if chat_id in self.waiting_for_custom_message and self.waiting_for_custom_message[chat_id]:
			if not message.text:
				await message.answer("Пожалуйста, отправьте текстовое сообщение.")
				return
			# Сохраняем текст и предлагаем подтверждение
			self.pending_custom_message[chat_id] = message.text
			self.waiting_for_custom_message[chat_id] = False
			keyboard = keyboards.get_notification_confirm_keyboard("custom")
			await self.send_and_track(
				chat_id,
				text=f"📢 Отправить оповещение:\n\n{message.text}",
				reply_markup=keyboard,
				track=False
			)
			# Удаляем сообщение пользователя (опционально)
			try:
				await message.delete()
			except:
				pass

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

		base_path = database.IMAGE_DIR_ANIME if image['type'] == database.ImageType.ANIME.value else database.IMAGE_DIR_REAL
		full_path = os.path.join(base_path, image['path'])

		if not os.path.isfile(full_path):
			# Файл отсутствует – удаляем из очереди и пропускаем
			self.moderation_queues[chat_id].pop(0)
			await self.send_next_moderation_image(chat_id)
			return

		caption = f"🛡 Модерация: {image['id']}\nОсталось: {remaining}"
		keyboard = keyboards.get_moderation_keyboard(image['id'])
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
			# Обновляем профиль пользователя
			await self._update_user_profile_from_callback(callback)
			await callback.answer()

			if callback.data in ["anime", "real"]:
				await self.delete_current(chat_id, message_id)


			# --- Выбор типа контента ---
			if callback.data == "anime":
				database.user_set_type(chat_id, database.ImageType.ANIME.value)
				await self.send_picture(chat_id)

			elif callback.data == "real":
				database.user_set_type(chat_id, database.ImageType.REAL.value)
				await self.send_picture(chat_id)

			elif callback.data == "video":
				await self.delete_current(chat_id, message_id)
				user = database.get_user(chat_id)
				coins = user.get('coins', 0) if user else 0
				keyboard = keyboards.get_video_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text=f"Баланс: {coins}🪙\nВыберите видео:",
					reply_markup=keyboard,
				)


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
				keyboard = keyboards.get_report_reasons_keyboard()
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

			elif callback.data == "video_top25":
				await self.delete_current(chat_id, message_id)
				await self.send_and_track(
					chat_id,
					text="ТОП25",
					track=False,
				)
				# Возвращаем меню выбора видео
				user = database.get_user(chat_id)
				coins = user.get('coins', 0) if user else 0
				keyboard = keyboards.get_video_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text=f"Баланс: {coins}🪙\nВыберите видео:",
					reply_markup=keyboard,
				)

			elif callback.data == "video_good":
				await self.delete_current(chat_id, message_id)
				await self.send_and_track(
					chat_id,
					text="Хорошее",
					track=False,
				)
				user = database.get_user(chat_id)
				coins = user.get('coins', 0) if user else 0
				keyboard = keyboards.get_video_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text=f"Баланс: {coins}🪙\nВыберите видео:",
					reply_markup=keyboard,
				)

			elif callback.data == "video_free":
				await self.delete_current(chat_id, message_id)
				await self.send_and_track(
					chat_id,
					text="Бесплатно",
					track=False,
				)
				user = database.get_user(chat_id)
				coins = user.get('coins', 0) if user else 0
				keyboard = keyboards.get_video_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text=f"Баланс: {coins}🪙\nВыберите видео:",
					reply_markup=keyboard,
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
					lines = ["📊 Статистика пользователей (ID | имя | просмотры):"]
					for u in users:
						# Формируем отображаемое имя
						name_parts = []
						if u['first_name']:
							name_parts.append(u['first_name'])
						if u['last_name']:
							name_parts.append(u['last_name'])
						display_name = ' '.join(name_parts) if name_parts else '—'
						username = f"@{u['username']}" if u['username'] else '—'
						lines.append(
							f"• {u['user_id']} | {display_name} ({username}) | "
							f"Всего: {u['viewed_total']} (аниме: {u['viewed_anime_count']}, фото: {u['viewed_real_count']})"
						)
					text = "\n".join(lines)

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text=text, track=False)

				# Возвращаем админ-меню (идентичное меню вызова /admin)
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)


			elif callback.data == "admin_notifications":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				await self.delete_current(chat_id, message_id)
				keyboard = keyboards.get_notifications_menu_keyboard()
				await self.send_and_track(chat_id, text="📢 Выберите оповещение для рассылки:", reply_markup=keyboard, track=False)

			elif callback.data == "admin_load_images":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="🔄 Загрузка контента...", track=False)
				import time
				start_time = time.time()
				try:
					result = image_loader.load_from_import_json()
					elapsed = time.time() - start_time
					report_lines = [
						f"✅ Загрузка завершена.",
						f"Добавлено аниме: {result.get('anime', 0)}",
						f"Добавлено фото: {result.get('real', 0)}",
						f"Добавлено видео: {result.get('videos', 0)}",
						f"Ошибок: {len(result.get('errors', []))}",
						f"Время выполнения: {elapsed:.2f} сек."
					]
					if result.get('errors'):
						report_lines.append("\nОшибки:")
						for err in result['errors'][:5]:  # показываем первые 5 ошибок
							report_lines.append(f"  - {err}")
					report = "\n".join(report_lines)
				except Exception as e:
					report = f"❌ Ошибка при загрузке: {e}"
					logging.error(f"Ошибка в admin_load_images: {e}")
				await self.send_and_track(chat_id, text=report, track=False)
				# Возвращаем админ-меню
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "admin_cleanup_json":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="🧹 Чистка по JSON...", track=False)
				import time
				start_time = time.time()
				json_path = os.path.join(os.path.dirname(__file__), "delete.json")
				deleted, errors = database.cleanup_by_json(json_path)
				elapsed = time.time() - start_time
				if errors:
					error_text = "\n".join(errors[:5])  # ограничим вывод
					report = (
						f"✅ Удалено записей: {deleted}\n"
						f"⏱ Время выполнения: {elapsed:.2f} сек.\n"
						f"⚠️ Ошибки:\n{error_text}"
					)
				else:
					report = (
						f"✅ Удалено записей: {deleted}\n"
						f"⏱ Время выполнения: {elapsed:.2f} сек.\n"
						f"✅ Ошибок нет."
					)
				await self.send_and_track(chat_id, text=report, track=False)
				# Возвращаем админ-меню
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "admin_logs":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="📋 Получение логов...", track=False)

				log_file = os.path.join(os.path.dirname(__file__), "bot.log")
				if not os.path.exists(log_file):
					await self.send_and_track(chat_id, text="❌ Файл логов не найден.", track=False)
				else:
					# Отправляем файл логов как документ
					document = FSInputFile(log_file)
					await self.bot.send_document(chat_id, document, caption="📁 Файл логов")

					# Читаем последние 25 строк лога
					try:
						with open(log_file, 'r', encoding='utf-8') as f:
							lines = f.readlines()
							last_lines = lines[-25:] if len(lines) >= 25 else lines
							log_preview = "".join(last_lines).strip()
							if not log_preview:
								log_preview = "Логи пусты."
					except Exception as e:
						log_preview = f"Ошибка чтения логов: {e}"

					await self.send_and_track(
						chat_id,
						text=f"📋 Последние {len(last_lines)} записей лога:\n```\n{log_preview}\n```",
						track=False
					)

				# Возвращаем админ-меню
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "notification_restored":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				message_text = "Работа бота восстановлена, ждем вас снова"
				keyboard = keyboards.get_notification_confirm_keyboard("restored")
				await self.send_and_track(chat_id, text=f"📢 Отправить оповещение:\n\n{message_text}", reply_markup=keyboard, track=False)

			elif callback.data == "notification_custom":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="Следующее сообщение будет отправлено всем пользователям. Напишите текст сообщения:", track=False)
				self.waiting_for_custom_message[chat_id] = True
				self.pending_custom_message[chat_id] = ""

			elif callback.data == "notification_confirm_restored":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="📢 Рассылка сообщения всем пользователям...", track=False)

				user_ids = database.get_all_user_ids()
				if not user_ids:
					await self.send_and_track(chat_id, text="❌ Нет пользователей для рассылки.", track=False)
					# Возвращаем админ-меню
					keyboard = keyboards.get_admin_panel_keyboard()
					await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)
					return

				success_count = 0
				fail_count = 0
				message_text = "Работа бота восстановлена, ждем вас снова"

				for user_id in user_ids:
					try:
						await self.bot.send_message(user_id, message_text)
						success_count += 1
						# небольшая задержка, чтобы не превысить лимиты Telegram
						await asyncio.sleep(0.05)
					except Exception as e:
						logging.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
						fail_count += 1

				report = f"✅ Рассылка завершена.\nУспешно: {success_count}\nНе удалось: {fail_count}"
				await self.send_and_track(chat_id, text=report, track=False)

				# Возвращаем админ-меню
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "notification_confirm_custom":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				await self.send_and_track(chat_id, text="📢 Рассылка сообщения всем пользователям...", track=False)

				user_ids = database.get_all_user_ids()
				if not user_ids:
					await self.send_and_track(chat_id, text="❌ Нет пользователей для рассылки.", track=False)
					# Возвращаем админ-меню
					keyboard = keyboards.get_admin_panel_keyboard()
					await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)
					return

				message_text = self.pending_custom_message.get(chat_id)
				if not message_text:
					await self.send_and_track(chat_id, text="❌ Не найден текст сообщения. Начните заново.", track=False)
					keyboard = keyboards.get_admin_panel_keyboard()
					await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)
					return

				success_count = 0
				fail_count = 0

				for user_id in user_ids:
					try:
						await self.bot.send_message(user_id, message_text)
						success_count += 1
						# небольшая задержка, чтобы не превысить лимиты Telegram
						await asyncio.sleep(0.05)
					except Exception as e:
						logging.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
						fail_count += 1

				report = f"✅ Рассылка завершена.\nУспешно: {success_count}\nНе удалось: {fail_count}"
				await self.send_and_track(chat_id, text=report, track=False)

				# Очищаем сохранённое сообщение
				self.pending_custom_message.pop(chat_id, None)

				# Возвращаем админ-меню
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "notification_cancel":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				keyboard = keyboards.get_admin_panel_keyboard()
				await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)
		finally:
			self.user_processing.pop(chat_id, None)


	# ==================== МЕТОДЫ ОТПРАВКИ СООБЩЕНИЙ ====================

	async def send_menu(self, chat_id: int) -> None:
		keyboard = keyboards.get_main_menu_keyboard()
		await self.send_and_track(chat_id, text="👋Здесь вы можете выбрать картинки(Аниме, Фото) или видео. \n\n👉В miniapp (/app) вы можете увидеть свои сохраненные картинки и ТОП25.",
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

			current_type = "Аниме" if image_data['type'] == database.ImageType.ANIME.value else "Фото"
			caption_text = f"{current_type} | {coins}🪙"

			keyboard = keyboards.get_picture_keyboard()

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
				logging.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

		self.dp.include_router(self.router)
		await self.dp.start_polling(self.bot)


def main() -> None:
	# Получаем ID администраторов из конфига
	admin_ids_str = config.admin_ids.strip()
	if admin_ids_str:
		try:
			admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(',')]
		except ValueError:
			logging.warning("Неверный формат ADMIN_IDS в конфиге, используется fallback")
			admin_ids = [7413924512, 5186349076]
	else:
		# Если строка пустая, используем fallback (старые ID)
		admin_ids = [7413924512, 5186349076]
		logging.info("ADMIN_IDS не заданы, используется fallback")

	controller = BotController(
		token=config.bot_token.get_secret_value(),
		admin_ids=admin_ids,
	)
	asyncio.run(controller.start_polling())


if __name__ == "__main__":
	main()