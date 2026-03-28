# bot.py
#
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

		# +++ Видео +++
		self.last_video_path: Dict[int, str] = {}				# chat_id -> путь к последнему видео
		self.last_video_data: Dict[int, dict] = {}			   # chat_id -> данные последнего видео (id, path, ...)
		self.last_video_message_id: Dict[int, int] = {}		  # chat_id -> message_id последнего видео
		self.sending_video: Dict[int, bool] = {}				# chat_id -> флаг, выполняется ли сейчас отправка видео
		self.last_video_send_time: Dict[int, float] = {}		# chat_id -> время последней отправки видео (для rate limit)

		# Состояние ожидания пользовательского сообщения для рассылки
		self.waiting_for_custom_message: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода сообщения)
		self.pending_custom_message: Dict[int, str] = {}	   # chat_id -> текст сообщения для рассылки
		
		# Состояние ожидания имени для рекламной ссылки
		self.waiting_for_promo_name: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода имени ссылки)
		self.waiting_for_promo_delete: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода номера для удаления)

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
		promo_code = None

		# Ручной разбор аргументов команды
		if message.text and ' ' in message.text:
			parts = message.text.split(maxsplit=1)
			if len(parts) == 2:
				arg = parts[1]
				# Проверяем, это цифровой ID (реферер) или промо-код
				if arg.isdigit():
					referrer_id = int(arg)
					if referrer_id == chat_id:
						referrer_id = None
				else:
					# Это промо-код
					promo_code = arg

		# Если это переход по промо-ссылке, записываем статистику
		if promo_code:
			promo_link = database.get_promo_link_by_code(promo_code)
			if promo_link:
				database.track_promo_link_click(promo_link['id'], chat_id)
				logging.info(f"Переход по промо-ссылке: {promo_code}, пользователь: {chat_id}")

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

		# Обработка имени для рекламной ссылки
		if chat_id in self.waiting_for_promo_name and self.waiting_for_promo_name[chat_id]:
			if not message.text:
				await message.answer("Пожалуйста, отправьте текстовое сообщение с именем ссылки.")
				return
			# Создаём промо-ссылку с первым сообщением как именем
			promo_name = message.text
			success, result = database.create_promo_link(promo_name)
			
			# Сбрасываем состояние ожидания
			self.waiting_for_promo_name[chat_id] = False
			
			if success:
				bot_info = await self.bot.me()
				promo_url = f"https://t.me/{bot_info.username}?start={result}"
				await self.send_and_track(
					chat_id,
					text=f"✅ Рекламная ссылка создана:\n\n📛 Название: {promo_name}\n🔗 Ссылка: {promo_url}",
					track=False
				)
				# Возвращаем в меню рекламных ссылок
				keyboard = keyboards.get_promo_links_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text="🔗 Рекламные ссылки. Выберите действие:",
					reply_markup=keyboard,
					track=False
				)
			else:
				await self.send_and_track(
					chat_id,
					text=f"❌ Ошибка при создании ссылки: {result}",
					track=False
				)
			
			# Удаляем сообщение админа
			try:
				await message.delete()
			except:
				pass

		# Обработка номера для удаления промо-ссылки
		if chat_id in self.waiting_for_promo_delete and self.waiting_for_promo_delete[chat_id]:
			if not message.text or not message.text.isdigit():
				await message.answer("Пожалуйста, отправьте номер ссылки для удаления.")
				return
			
			link_number = int(message.text)
			promo_links = database.get_all_promo_links()
			
			if link_number < 1 or link_number > len(promo_links):
				await self.send_and_track(
					chat_id,
					text=f"❌ Неверный номер. Введите число от 1 до {len(promo_links)}.",
					track=False
				)
				return
			
			# Удаляем ссылку по номеру (индекс на 1 меньше)
			link_to_delete = promo_links[link_number - 1]
			success = database.delete_promo_link(link_to_delete['id'])
			
			if success:
				await self.send_and_track(
					chat_id,
					text=f"🗑 Ссылка \"{link_to_delete['name']}\" удалена.",
					track=False
				)
			else:
				await self.send_and_track(
					chat_id,
					text="❌ Ошибка при удалении ссылки.",
					track=False
				)
			
			# Сбрасываем состояние и возвращаем меню
			self.waiting_for_promo_delete[chat_id] = False
			keyboard = keyboards.get_promo_links_menu_keyboard()
			await self.send_and_track(
				chat_id,
				text="🔗 Рекламные ссылки. Выберите действие:",
				reply_markup=keyboard,
				track=False
			)
			
			# Удаляем сообщение админа
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
				await self.send_video(chat_id, 'top25')

			elif callback.data == "video_good":
				await self.delete_current(chat_id, message_id)
				await self.send_video(chat_id, 'good')

			elif callback.data == "video_free":
				await self.delete_current(chat_id, message_id)
				await self.send_video(chat_id, 'free')

			elif callback.data == "video_like":
				# Лайк на видео
				if chat_id not in self.last_video_data:
					await callback.answer("Нет активного видео")
					return
				video = self.last_video_data[chat_id]
				video_id = video['id']
				success = database.video_like(chat_id, video_id)
				if success:
					await self.remove_keyboard(chat_id, message_id)
					await callback.answer("✅ +5 монет")
				else:
					await callback.answer("❌ Ошибка")

			elif callback.data == "video_dislike":
				# Дизлайк на видео
				if chat_id not in self.last_video_data:
					await callback.answer("Нет активного видео")
					return
				video = self.last_video_data[chat_id]
				video_id = video['id']
				success = database.video_dislike(chat_id, video_id)
				if success:
					await self.remove_keyboard(chat_id, message_id)
					await callback.answer("✅ +5 монет")
				else:
					await callback.answer("❌ Ошибка")

			elif callback.data == "video_report":
				await self.delete_current(chat_id, message_id)
				keyboard = keyboards.get_video_report_keyboard()
				await self.send_and_track(
					chat_id,
					text="Выберите причину жалобы на видео:",
					reply_markup=keyboard,
				)

			elif callback.data == "video_report_inappropriate":
				await self.delete_current(chat_id, message_id)
				if chat_id not in self.last_video_data:
					await self.send_and_track(chat_id, text="Ошибка: видео не найдено")
					return
				video = self.last_video_data[chat_id]
				video_id = video['id']
				database.video_report(chat_id, video_id)
				database.add_coins(chat_id, 1)
				await self.send_and_track(chat_id, text="Жалоба отправлена. Спасибо! +1 монета")
				# Возвращаем меню выбора видео
				user = database.get_user(chat_id)
				coins = user.get('coins', 0) if user else 0
				keyboard = keyboards.get_video_menu_keyboard()
				await self.send_and_track(
					chat_id,
					text=f"Баланс: {coins}🪙\nВыберите видео:",
					reply_markup=keyboard,
				)

			elif callback.data == "video_report_cancel":
				await self.delete_current(chat_id, message_id)
				# Возвращаем меню выбора видео
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

			# --- Рекламные ссылки ---
			elif callback.data == "admin_promo_links":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					await self.delete_current(chat_id, message_id)
					return

				await self.delete_current(chat_id, message_id)
				keyboard = keyboards.get_promo_links_menu_keyboard()
				await self.send_and_track(chat_id, text="🔗 Рекламные ссылки. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "promo_create":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				self.waiting_for_promo_name[chat_id] = True
				await self.send_and_track(
					chat_id,
					text="📝 Введите название для рекламной ссылки.\n\nПервое отправленное сообщение станет названием ссылки, а ссылка сгенерируется автоматически.",
					track=False
				)

			elif callback.data == "promo_stats":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				promo_links = database.get_all_promo_links()
				
				if not promo_links:
					text = "📊 Статистика по рекламным ссылкам:\n\n❌ Пока нет созданных ссылок."
				else:
					lines = ["📊 Статистика по рекламным ссылкам:\n"]
					for link in promo_links:
						bot_info = await self.bot.me()
						promo_url = f"https://t.me/{bot_info.username}?start={link['code']}"
						lines.append(
							f"📛 {link['name']}\n"
							f"👥 Переходов: {link['clicks_count']}\n"
							f"🔗 {promo_url}\n"
						)
					text = "\n".join(lines)

				keyboard = keyboards.get_promo_links_menu_keyboard()
				await self.send_and_track(chat_id, text=text, reply_markup=keyboard, track=False)

			elif callback.data == "promo_delete":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				promo_links = database.get_all_promo_links()
				
				if not promo_links:
					text = "🗑 Удаление ссылок:\n\n❌ Пока нет созданных ссылок."
					keyboard = keyboards.get_promo_links_menu_keyboard()
					await self.send_and_track(chat_id, text=text, reply_markup=keyboard, track=False)
				else:
					# Формируем пронумерованный список
					lines = ["🗑 Удаление ссылок. Отправьте номер ссылки для удаления:\n"]
					for i, link in enumerate(promo_links, 1):
						lines.append(f"{i}. 📛 {link['name']} | 👥 {link['clicks_count']} переходов")
					text = "\n".join(lines)
					
					self.waiting_for_promo_delete[chat_id] = True
					await self.send_and_track(chat_id, text=text, track=False)

			elif callback.data == "promo_links_menu":
				if chat_id not in self.admin_ids:
					await callback.answer("⛔ Доступ запрещён")
					return

				await self.delete_current(chat_id, message_id)
				keyboard = keyboards.get_promo_links_menu_keyboard()
				await self.send_and_track(chat_id, text="🔗 Рекламные ссылки. Выберите действие:", reply_markup=keyboard, track=False)

			elif callback.data == "admin_menu":
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


	async def send_video(self, chat_id: int, video_type: str) -> None:
		"""
		Отправляет видео пользователю в зависимости от типа.
		video_type: 'top25', 'good', 'free'
		"""
		# +++ Защита от одновременной отправки +++
		if self.sending_video.get(chat_id, False):
			logging.warning(f"Send video already in progress for {chat_id}")
			return
		self.sending_video[chat_id] = True

		try:
			# +++ Rate limit: не чаще 1 раза в секунду +++
			now = asyncio.get_event_loop().time()
			last_time = self.last_video_send_time.get(chat_id, 0)
			if now - last_time < 1.0:
				await self.send_and_track(
					chat_id,
					text="⏳ Слишком часто, подождите секунду",
					track=False
				)
				return

			# Проверяем, можно ли смотреть видео (ограничение 30 секунд)
			if not database.can_watch_video(chat_id):
				await self.send_and_track(
					chat_id,
					text="⏳ Подождите 30 секунд перед просмотром следующего видео.",
					track=False
				)
				return

			# Получаем видео в зависимости от типа
			video = None
			if video_type == 'top25':
				video = database.get_video_top25(chat_id)
			elif video_type == 'good':
				video = database.get_video_good(chat_id)
			elif video_type == 'free':
				video = database.get_video_free(chat_id)

			if not video:
				await self.send_and_track(chat_id, text="Нет доступных видео")
				return

			video_path = os.path.join(database.VIDEO_DIR, video['path'])
			if not os.path.isfile(video_path):
				logging.error(f"Файл видео не найден: {video_path}")
				await self.send_and_track(chat_id, text="Ошибка: файл видео отсутствует")
				return

			# Обновляем состояние пользователя (просмотр видео)
			database.user_watched_video(chat_id, video['id'])

			# Сохраняем данные видео
			self.last_video_path[chat_id] = video_path
			self.last_video_data[chat_id] = video
			user = database.get_user(chat_id)
			coins = user.get('coins', 0) if user else 0

			caption_text = f"Видео | {coins}🪙"
			keyboard = keyboards.get_video_keyboard()

			video_file = FSInputFile(video_path)
			sent = await self.send_and_track(
				chat_id,
				video=video_file,
				caption=caption_text,
				reply_markup=keyboard,
			)

			self.last_video_message_id[chat_id] = sent.message_id
			self.last_video_send_time[chat_id] = now

		finally:
			self.sending_video[chat_id] = False


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