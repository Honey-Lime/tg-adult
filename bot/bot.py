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

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters.command import Command
from aiogram.types import (
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	FSInputFile,
	BotCommand,
	CallbackQuery,
	Message,
	WebAppInfo,
	PreCheckoutQuery,
)

from config_reader import config
import database
import keyboards
import image_loader
from logging_config import setup_logging
from locales import get_text, get_language_name

# Импорты обработчиков
from handlers.content_handlers import handle_content_type, handle_menu
from handlers.video_handlers import (
    handle_video_menu,
    handle_video_selection,
    handle_video_like,
    handle_video_dislike,
    handle_video_save,
    handle_video_report_menu,
    handle_video_report,
)
from handlers.user_handlers import (
    handle_like,
    handle_dislike,
    handle_save_from_history,
    handle_save_current,
)
from handlers.report_handlers import (
    handle_report_menu,
    handle_report_wrong_type,
    handle_report_inappropriate,
    handle_report_cancel,
)
from handlers.admin import (
    handle_admin_users,
    handle_admin_moderation,
    handle_moderation_delete,
    handle_moderation_restore,
    handle_admin_notifications,
    handle_notification_callbacks,
    handle_admin_promo_links,
    handle_promo_create,
    handle_promo_stats,
    handle_promo_delete,
)
from handlers.admin.promo_handler import handle_promo_menu_back

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

		# Состояние ожидания пользовательского сообщения для рассылки
		self.waiting_for_custom_message: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода сообщения)
		self.pending_custom_message: Dict[int, str] = {}	   # chat_id -> текст сообщения для рассылки
		
		# Состояние ожидания имени для рекламной ссылки
		self.waiting_for_promo_name: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода имени ссылки)
		self.waiting_for_promo_delete: Dict[int, bool] = {}  # chat_id -> bool (ожидает ли админ ввода номера для удаления)

		self._register_handlers()
		# История сообщений загружается лениво при первом использовании
		self._message_history_loaded = False


	def _register_handlers(self) -> None:
		self.router.message.register(self.cmd_start, Command("start"))
		self.router.message.register(self.cmd_app, Command("app"))
		self.router.message.register(self.cmd_donut, Command("donut"))
		self.router.message.register(self.cmd_admin, Command("admin"))
		self.router.message.register(self.handle_message)
		self.router.pre_checkout_query.register(self.handle_pre_checkout_query)
		self.router.message.register(self.handle_successful_payment, F.successful_payment)
		self.router.callback_query.register(self.process_callback)


	# ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

	async def set_bot_commands(self) -> None:
		commands = [
			BotCommand(command="start", description="Старт / Главное меню"),
			BotCommand(command="app", description="Мини приложение(ТОП, Сохраненные)"),
			BotCommand(command="donut", description="Пополнить баланс"),
			BotCommand(command="admin", description="Админ-панель"),
		]
		await self.bot.set_my_commands(commands)

	async def send_and_track(
			self,
			chat_id: int,
			text: Optional[str] = None,
			photo=None,
			video=None,
			reply_markup: Optional[InlineKeyboardMarkup] = None,
			track: bool = True,
	) -> types.Message:
		# Проверяем лимит и удаляем самое старое, если нужно
		if track:
			self._ensure_message_history_loaded()
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
		if video:
			sent = await self.bot.send_video(
				chat_id,
				video=video,
				caption=text,
				reply_markup=reply_markup,
				protect_content=True,
			)
		elif photo:
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
		self._ensure_message_history_loaded()
		if chat_id in self.message_history and message_id in self.message_history[chat_id]:
			self.message_history[chat_id].remove(message_id)
		# Удаляем из БД в любом случае
		database.delete_message_record(chat_id, message_id)

	def _ensure_message_history_loaded(self):
		"""Ленивая загрузка истории сообщений из БД (вызывается один раз)."""
		if self._message_history_loaded:
			return
		db_history = database.load_all_message_history()
		for chat_id, msg_ids in db_history.items():
			# Оставляем только последние 10 (на случай, если в БД больше)
			self.message_history[chat_id] = msg_ids[-10:]
		logging.info(f"Loaded message history for {len(self.message_history)} chats")
		self._message_history_loaded = True

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
		language_code = user.language_code
		database.update_user_profile(chat_id, first_name, last_name, username, language_code)

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
		language_code = user.language_code
		database.update_user_profile(chat_id, first_name, last_name, username, language_code)

	async def edit_message_to_save_button(self, chat_id: int, message_id: int, image_id: int, lang: str) -> None:
		keyboard = keyboards.get_save_button_keyboard(image_id, lang)
		logging.info(f"[EDIT_TO_SAVE] chat_id={chat_id}, message_id={message_id}, image_id={image_id}")
		logging.info(f"[EDIT_TO_SAVE] Before edit: last_image_message_id={self.last_image_message_id.get(chat_id)}")
		try:
			await self.bot.edit_message_reply_markup(
				chat_id=chat_id,
				message_id=message_id,
				reply_markup=keyboard,
				business_connection_id=None,
			)
			logging.info(f"[EDIT_TO_SAVE] Success: edited message {message_id}, added button save_{image_id}")
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
		logging.info(f"[REMOVE_KEYBOARD] chat_id={chat_id}, message_id={message_id}")
		if message_id is None:
			logging.warning("[REMOVE_KEYBOARD] message_id is None, skipping")
			return
		try:
			await self.bot.edit_message_reply_markup(
				chat_id=chat_id,
				message_id=message_id,
				reply_markup=None,
				business_connection_id=None
			)
			logging.info(f"[REMOVE_KEYBOARD] Success: removed keyboard from message {message_id}")
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

		# Определяем язык пользователя из данных Telegram
		user_lang = 'ru'  # язык по умолчанию
		if message.from_user and message.from_user.language_code:
			# Если язык начинается с 'ru', используем русский, иначе английский
			if message.from_user.language_code.startswith('ru'):
				user_lang = 'ru'
			else:
				user_lang = 'en'

		# Получаем пользователя и флаг создания
		user, created = database.get_or_create_user(chat_id, referrer_id, user_lang)

		if user is None:
			# Ошибка при получении/создании пользователя
			await message.answer(get_text(lang, 'registration_error'))
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
		lang = self.get_user_lang(chat_id)
		keyboard = keyboards.get_web_app_keyboard(chat_id, lang)
		text = get_text(lang, 'miniapp_prompt')
		await message.answer(text=text, reply_markup=keyboard)

	async def cmd_admin(self, message: Message) -> None:
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)
		chat_id = message.chat.id
		lang = self.get_user_lang(chat_id)
		if chat_id not in self.admin_ids:
			await message.answer(get_text(lang, 'admin_denied'))
			return

		keyboard = keyboards.get_admin_panel_keyboard(lang)
		text = get_text(lang, 'admin_menu_text')
		await self.send_and_track(chat_id, text=text, reply_markup=keyboard)

	async def cmd_donut(self, message: Message) -> None:
		"""Обработчик команды /donut для пополнения баланса."""
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)
		chat_id = message.chat.id
		lang = self.get_user_lang(chat_id)
		
		# Получаем баланс пользователя
		user = database.get_user(chat_id)
		coins = user.get('coins', 0) if user else 0
		
		keyboard = keyboards.get_donate_keyboard(lang)
		text = get_text(lang, 'donate_menu_text', coins=coins)
		await self.send_and_track(chat_id, text=text, reply_markup=keyboard)

	async def handle_message(self, message: Message) -> None:
		"""
		Обработчик текстовых сообщений (не команд).
		Используется для захвата пользовательского сообщения для рассылки.
		"""
		chat_id = message.chat.id
		lang = self.get_user_lang(chat_id)
		# Обновляем профиль пользователя
		await self._update_user_profile_from_message(message)

		if chat_id in self.waiting_for_custom_message and self.waiting_for_custom_message[chat_id]:
			if not message.text:
				await message.answer(get_text(lang, 'enter_message'))
				return
			# Сохраняем текст и предлагаем подтверждение
			self.pending_custom_message[chat_id] = message.text
			self.waiting_for_custom_message[chat_id] = False
			keyboard = keyboards.get_notification_confirm_keyboard("custom", lang)
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
				await message.answer(get_text(lang, 'enter_name'))
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
				keyboard = keyboards.get_promo_links_menu_keyboard(lang)
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
				await message.answer(get_text(lang, 'enter_number'))
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
			keyboard = keyboards.get_promo_links_menu_keyboard(lang)
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

	async def handle_pre_checkout_query(self, pre_checkout_query: PreCheckoutQuery) -> None:
		"""Обработчик pre_checkout_query для подтверждения платежа."""
		try:
			await self.bot.answer_pre_checkout_query(
				pre_checkout_query_id=pre_checkout_query.id,
				ok=True
			)
			logging.info(f"Pre-checkout query approved for user {pre_checkout_query.from_user.id}")
		except Exception as e:
			logging.error(f"Error in pre_checkout_query: {e}")

	async def handle_successful_payment(self, message: Message) -> None:
		"""Обработчик successful_payment для зачисления монет после оплаты."""
		chat_id = message.chat.id
		lang = self.get_user_lang(chat_id)
		logging.info(f"=== SUCCESSFUL PAYMENT RECEIVED === user={chat_id}, currency={message.successful_payment.currency}, total_amount={message.successful_payment.total_amount}, payload={message.successful_payment.invoice_payload}")
		try:
			# Парсим payload для получения суммы пополнения
			payload = message.successful_payment.invoice_payload
			parts = payload.split('_')
			if len(parts) >= 3 and parts[0] == 'donate':
				amount = int(parts[1])
				
				# Получаем сумму в звездах из сообщения
				stars_paid = message.successful_payment.total_amount
				
				logging.info(f"Payment received: user {chat_id}, amount={amount} coins, stars_paid={stars_paid}, payload={payload}")
				
				# Начисляем монеты пользователю
				coins_added = database.add_coins(chat_id, amount)
				if not coins_added:
					logging.error(f"Failed to add coins to user {chat_id}, amount={amount}")
					await self.send_and_track(
						chat_id,
						text="❌ Ошибка при начислении монет. Обратитесь к администрации.",
						track=False
					)
					return
				
				# Добавляем запись о транзакции
				transaction_added = database.add_transaction(chat_id, amount, stars_paid)
				if not transaction_added:
					logging.error(f"Failed to add transaction for user {chat_id}")
				
				# Проверяем баланс после начисления
				user = database.get_user(chat_id)
				current_balance = user.get('coins', 0) if user else 0
				logging.info(f"Coins added successfully. User {chat_id} new balance: {current_balance}")
				
				# Отправляем подтверждение
				await self.send_and_track(
					chat_id,
					text=f"✅ Оплата прошла успешно!\n\nВаш баланс пополнен на {amount}🪙\nСписано: {stars_paid} ⭐\nТекущий баланс: {current_balance}🪙",
					track=False
				)
				
				logging.info(f"Payment successful: user {chat_id}, {amount} coins, {stars_paid} stars, new_balance={current_balance}")
			else:
				logging.error(f"Invalid payment payload: {payload} for user {chat_id}")
				await self.send_and_track(
					chat_id,
					text="❌ Ошибка обработки платежа. Обратитесь к администрации.",
					track=False
				)
		except Exception as e:
			logging.error(f"Error processing successful payment: {e}")
			await self.send_and_track(
				chat_id,
				text=get_text(lang, 'payment_error'),
				track=False
			)

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
		"""
		Главный обработчик callback-запросов.
		Делегирует логику специализированным обработчикам из модуля handlers.
		"""
		chat_id = callback.message.chat.id
		message_id = callback.message.message_id
		lang = self.get_user_lang(chat_id)

		# Защита от повторных нажатий
		if self.user_processing.get(chat_id):
			await callback.answer(get_text(lang, 'processing_wait'))
			return
		self.user_processing[chat_id] = True

		try:
			# Обновляем профиль пользователя
			await self._update_user_profile_from_callback(callback)
			await callback.answer()

			# === КОНТЕНТ (аниме/фото) ===
			if callback.data in ["anime", "real"]:
				await self.delete_current(chat_id, message_id)
				await handle_content_type(self, callback.data, chat_id, lang)

			# === МЕНЮ ===
			elif callback.data == "menu":
				await handle_menu(self, chat_id)

			# === ВИДЕО ===
			elif callback.data == "video":
				await handle_video_menu(self, chat_id, message_id, lang)
			elif callback.data.startswith("video_"):
				if callback.data in ["video_top25", "video_good", "video_free"]:
					await handle_video_selection(self, callback.data, chat_id, lang)
				elif callback.data == "video_like":
					await handle_video_like(self, chat_id, message_id, lang)
				elif callback.data == "video_dislike":
					await handle_video_dislike(self, chat_id, message_id, lang)
				elif callback.data == "video_save":
					await handle_video_save(self, chat_id, message_id, lang)
				elif callback.data.startswith("video_save_"):
					# Обработка кнопки "Сохранить 50" после оценки видео
					video_id = int(callback.data.split("_")[2])
					await handle_video_save(self, chat_id, message_id, lang, video_id, show_menu=False)
				elif callback.data == "video_report":
					await handle_video_report_menu(self, chat_id, message_id, lang)
				elif callback.data == "video_report_inappropriate":
					await handle_video_report(self, chat_id, lang)
				elif callback.data == "video_report_cancel":
					await handle_video_report(self, chat_id, lang)  # Возврат в меню

			# === ДЕЙСТВИЯ С КОНТЕНТОМ ===
			elif callback.data == "like":
				await handle_like(self, chat_id, message_id, lang)
			elif callback.data == "dislike":
				await handle_dislike(self, chat_id, message_id, lang)
			elif callback.data.startswith("save_"):
				await handle_save_from_history(self, callback.data, chat_id, message_id, lang)
			elif callback.data == "save":
				await handle_save_current(self, chat_id, message_id, lang)

			# === ЖАЛОБЫ ===
			elif callback.data == "report":
				await handle_report_menu(self, chat_id, message_id, lang)
			elif callback.data == "report_wrong_type":
				await handle_report_wrong_type(self, chat_id, lang)
			elif callback.data == "report_inappropriate":
				await handle_report_inappropriate(self, chat_id, lang)
			elif callback.data == "report_cancel":
				await handle_report_cancel(self, chat_id, lang)

			# === РЕФЕРАЛЬНАЯ ССЫЛКА ===
			elif callback.data == "referral":
				await self._handle_referral(chat_id)

			# === ДОНАТ ===
			elif callback.data == "donate":
				await self._handle_donate_menu(chat_id, message_id, lang)
			elif callback.data.startswith("donate_"):
				await self._handle_donate_purchase(chat_id, callback.data, lang)

			# === ЯЗЫК ===
			elif callback.data == "language":
				await self._handle_language_menu(chat_id, message_id)
			elif callback.data.startswith("lang_"):
				await self._handle_language_select(chat_id, callback.data)

			# === АДМИН-ПАНЕЛЬ ===
			elif callback.data == "admin_users":
				await handle_admin_users(self, chat_id, message_id, lang)
			elif callback.data == "admin_moderation":
				await handle_admin_moderation(self, chat_id, message_id, lang)
			elif callback.data.startswith("mod_delete_"):
				await handle_moderation_delete(self, callback.data, chat_id, lang)
			elif callback.data.startswith("mod_restore_"):
				await handle_moderation_restore(self, callback.data, chat_id, lang)
			elif callback.data == "admin_notifications":
				await handle_admin_notifications(self, chat_id, message_id, lang)
			elif callback.data.startswith("notification_"):
				await handle_notification_callbacks(self, callback.data, chat_id, message_id, lang)
			elif callback.data == "admin_load_images":
				await self._handle_admin_load_images(chat_id, message_id, lang)
			elif callback.data == "admin_clear_import_folder":
				await self._handle_admin_clear_folder(chat_id, message_id, lang)
			elif callback.data in ["admin_clear_import_folder_confirm", "admin_clear_import_folder_cancel"]:
				await self._handle_admin_clear_folder_action(chat_id, callback.data, lang)
			elif callback.data == "admin_cleanup_json":
				await self._handle_admin_cleanup_json(chat_id, message_id, lang)
			elif callback.data == "admin_logs":
				await self._handle_admin_logs(chat_id, message_id, lang)
			elif callback.data == "admin_promo_links":
				await handle_admin_promo_links(self, chat_id, message_id, lang)
			elif callback.data == "promo_create":
				await handle_promo_create(self, chat_id, message_id, lang)
			elif callback.data == "promo_stats":
				await handle_promo_stats(self, chat_id, message_id, lang)
			elif callback.data == "promo_delete":
				await handle_promo_delete(self, chat_id, message_id, lang)
			elif callback.data == "promo_links_menu":
				await handle_promo_menu_back(self, chat_id, message_id, lang)
			elif callback.data == "admin_menu":
				await handle_promo_menu_back(self, chat_id, message_id, lang)  # Возврат в админ-меню

			else:
				logging.warning(f"Неизвестная команда: {callback.data}")

		finally:
			self.user_processing.pop(chat_id, None)


	# ==================== ХЕЛПЕРЫ ДЛЯ CALLBACK ====================

	async def _handle_referral(self, chat_id: int) -> None:
		"""Отправка реферальной ссылки пользователю"""
		if not self.bot_username:
			bot_info = await self.bot.me()
			self.bot_username = bot_info.username
		link = f"https://t.me/{self.bot_username}?start={chat_id}"
		await self.send_and_track(
			chat_id,
			text=f"🔗 Ваша реферальная ссылка:\n{link}\n\nПриглашайте друзей! За каждого нового пользователя вы получите 250 монет.",
			track=False,
		)

	async def _handle_donate_menu(self, chat_id: int, message_id: int, lang: str) -> None:
		"""Показ меню пополнения баланса"""
		await self.delete_current(chat_id, message_id)
		user = database.get_user(chat_id)
		coins = user.get('coins', 0) if user else 0
		keyboard = keyboards.get_donate_keyboard(lang)
		await self.send_and_track(
			chat_id,
			text=f"💰 Ваш баланс: {coins}🪙\n\nВыберите тариф для пополнения баланса за Telegram Stars:",
			reply_markup=keyboard
		)

	async def _handle_donate_purchase(self, chat_id: int, callback_data: str, lang: str) -> None:
		"""Обработка покупки монет"""
		try:
			amount = int(callback_data.split('_')[1])
		except (IndexError, ValueError):
			await self.send_and_track(chat_id, text="Ошибка тарифа", track=False)
			return

		stars_map = {100: 10, 500: 45, 1000: 90, 5000: 400}
		stars = stars_map.get(amount)
		if not stars:
			await self.send_and_track(chat_id, text="Неверный тариф", track=False)
			return

		logging.info(f"Sending invoice: chat_id={chat_id}, amount={amount} coins, stars={stars}, payload=donate_{amount}_{chat_id}")
		
		await self.bot.send_invoice(
			chat_id=chat_id,
			title=f"Пополнение баланса на {amount}🪙",
			description=f"Пополнение баланса бота на {amount} монет. После оплаты монеты будут зачислены на ваш баланс.",
			payload=f"donate_{amount}_{chat_id}",
			provider_token=None,  # Для Telegram Stars не требуется
			currency="XTR",
			prices=[types.LabeledPrice(label=f"{amount} 🪙", amount=stars)],
			start_parameter="donate",
		)
		logging.info(f"Invoice sent successfully to {chat_id}")

	async def _handle_language_menu(self, chat_id: int, message_id: int) -> None:
		"""Показ меню выбора языка"""
		await self.delete_current(chat_id, message_id)
		current_lang = database.get_user_language(chat_id)
		keyboard = keyboards.get_language_keyboard(current_lang)
		lang_name = get_language_name(current_lang)
		text = get_text(current_lang, 'language_menu_text', lang=lang_name)
		await self.send_and_track(chat_id, text=text, reply_markup=keyboard, track=False)

	async def _handle_language_select(self, chat_id: int, callback_data: str) -> None:
		"""Обработка выбора языка"""
		if callback_data == "lang_ru":
			database.set_user_language(chat_id, "ru")
		elif callback_data == "lang_en":
			database.set_user_language(chat_id, "en")
		await self.send_menu(chat_id)

	async def _handle_admin_load_images(self, chat_id: int, message_id: int, lang: str) -> None:
		"""Загрузка контента из JSON"""
		if chat_id not in self.admin_ids:
			await self.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
			return
		await self.delete_current(chat_id, message_id)
		await self.send_and_track(chat_id, text="🔄 Загрузка контента...", track=False)
		import time
		start_time = time.time()
		try:
			result = image_loader.load_from_import_json()
			elapsed = time.time() - start_time
			photos_added, videos_added, errors_count = result
			report_lines = [
				f"✅ Загрузка завершена.",
				f"Добавлено фото: {photos_added}",
				f"Добавлено видео: {videos_added}",
				f"Ошибок: {errors_count}",
				f"Время выполнения: {elapsed:.2f} сек."
			]
			report = "\n".join(report_lines)
		except Exception as e:
			report = f"❌ Ошибка при загрузке: {e}"
			logging.error(f"Ошибка в admin_load_images: {e}")
		await self.send_and_track(chat_id, text=report, track=False)
		# Возвращаем админ-меню
		keyboard = keyboards.get_admin_panel_keyboard(lang)
		await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

	async def _handle_admin_clear_folder(self, chat_id: int, message_id: int, lang: str) -> None:
		"""Очистка папки импорта - показ подтверждения"""
		if chat_id not in self.admin_ids:
			await self.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
			return
		await self.delete_current(chat_id, message_id)
		# Показываем подтверждение с уточнением
		keyboard = keyboards.get_clear_folder_confirm_keyboard(lang)
		await self.send_and_track(
			chat_id,
			text="🗑 Очистка папки загрузки\n\n⚠️ Все файлы и папки в папке 'images/new' будут удалены без возможности восстановления.\n\nВы уверены?",
			reply_markup=keyboard,
			track=False
		)

	async def _handle_admin_clear_folder_action(self, chat_id: int, callback_data: str, lang: str) -> None:
		"""Обработка действия очистки папки"""
		if chat_id not in self.admin_ids:
			await self.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
			return

		if callback_data == "admin_clear_import_folder_confirm":
			await self.delete_current(chat_id, callback_data.message_id if hasattr(callback_data, 'message_id') else None)
			await self.send_and_track(chat_id, text="🗑 Очистка папки загрузки...", track=False)
			
			try:
				files_count, folders_count = image_loader.clear_import_folder()
				report = f"✅ Папка загрузки очищена.\n\nУдалено файлов: {files_count}\nУдалено папок: {folders_count}"
			except Exception as e:
				report = f"❌ Ошибка при очистке: {e}"
				logging.error(f"Ошибка в admin_clear_import_folder: {e}")
			
			await self.send_and_track(chat_id, text=report, track=False)
			# Возвращаем админ-меню
			keyboard = keyboards.get_admin_panel_keyboard(lang)
			await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

		elif callback_data == "admin_clear_import_folder_cancel":
			await self.delete_current(chat_id, callback_data.message_id if hasattr(callback_data, 'message_id') else None)
			keyboard = keyboards.get_admin_panel_keyboard(lang)
			await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

	async def _handle_admin_cleanup_json(self, chat_id: int, message_id: int, lang: str) -> None:
		"""Чистка базы данных по JSON"""
		if chat_id not in self.admin_ids:
			await self.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
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
		keyboard = keyboards.get_admin_panel_keyboard(lang)
		await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

	async def _handle_admin_logs(self, chat_id: int, message_id: int, lang: str) -> None:
		"""Просмотр логов"""
		if chat_id not in self.admin_ids:
			await self.send_and_track(chat_id, text="⛔ Доступ запрещён", track=False)
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
		keyboard = keyboards.get_admin_panel_keyboard(lang)
		await self.send_and_track(chat_id, text="Админ-панель. Выберите действие:", reply_markup=keyboard, track=False)

	# ==================== МЕТОДЫ ОТПРАВКИ СООБЩЕНИЙ ====================

	def get_user_lang(self, chat_id: int) -> str:
		"""Получает язык пользователя из базы данных."""
		return database.get_user_language(chat_id)

	async def send_menu(self, chat_id: int) -> None:
		lang = self.get_user_lang(chat_id)
		keyboard = keyboards.get_main_menu_keyboard(lang)
		text = get_text(lang, 'main_menu_text')
		await self.send_and_track(chat_id, text=text, reply_markup=keyboard)


	async def send_picture(self, chat_id: int) -> None:
		# +++ Защита от одновременной отправки +++
		if self.sending_picture.get(chat_id, False):
			logging.warning(f"Send picture already in progress for {chat_id}")
			return
		self.sending_picture[chat_id] = True

		try:
			lang = self.get_user_lang(chat_id)
			logging.info(f"[SEND_PICTURE] chat_id={chat_id}, before: last_image_message_id={self.last_image_message_id.get(chat_id)}")
			# +++ Rate limit: не чаще 1 раза в секунду +++
			now = asyncio.get_event_loop().time()
			last_time = self.last_picture_time.get(chat_id, 0)
			if now - last_time < 1.0:
				await self.send_and_track(
					chat_id,
					text=get_text(lang, 'too_often'),
					track=False
				)
				return

			result = database.get_image(chat_id)
			if result is None or result[0] is None:
				await self.send_and_track(chat_id, text=get_text(lang, 'no_images'))
				return

			image_path, image_data = result
			self.last_image_path[chat_id] = image_path
			self.last_image_data[chat_id] = image_data

			user = database.get_user(chat_id)
			coins = user.get('coins', 0) if user else 0

			# Тип картинки на языке пользователя
			pic_type = 'Anime' if image_data['type'] == database.ImageType.ANIME.value else 'Photo'
			if lang == 'ru':
				pic_type = 'Аниме' if image_data['type'] == database.ImageType.ANIME.value else 'Фото'
			
			caption_text = get_text(lang, 'picture_caption', type=pic_type, coins=coins)
			keyboard = keyboards.get_picture_keyboard(lang)

			image = FSInputFile(image_path)
			sent = await self.send_and_track(
				chat_id,
				photo=image,
				text=caption_text,
				reply_markup=keyboard,
			)

			self.last_image_message_id[chat_id] = sent.message_id
			self.last_picture_time[chat_id] = now
			logging.info(f"[SEND_PICTURE] chat_id={chat_id}, after: last_image_message_id={sent.message_id}")

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
			lang = self.get_user_lang(chat_id)
			# Получаем видео в зависимости от типа
			video_path = None
			video = None
			if video_type == 'top25':
				video_path, video = database.get_video_top25(chat_id)
			elif video_type == 'good':
				video_path, video = database.get_video_good(chat_id)
			elif video_type == 'free':
				video_path, video = database.get_video_free(chat_id)

			if not video:
				await self.send_and_track(chat_id, text=get_text(lang, 'no_videos'))
				return

			if not os.path.isfile(video_path):
				logging.error(f"Файл видео не найден: {video_path}")
				await self.send_and_track(chat_id, text=get_text(lang, 'video_file_missing'))
				return

			# Обновляем состояние пользователя (просмотр видео)
			database.user_watched_video(chat_id, video['id'])

			# Сохраняем данные видео
			self.last_video_path[chat_id] = video_path
			self.last_video_data[chat_id] = video
			user = database.get_user(chat_id)
			coins = user.get('coins', 0) if user else 0

			caption_text = f"Видео | {coins}🪙"
			keyboard = keyboards.get_video_keyboard(lang)

			video_file = FSInputFile(video_path)
			sent = await self.send_and_track(
				chat_id,
				video=video_file,
				text=caption_text,
				reply_markup=keyboard,
			)

			self.last_video_message_id[chat_id] = sent.message_id

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
	# Инициализация БД (создание таблиц и миграции)
	database.init_db()
	
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