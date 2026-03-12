from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Optional

# import os
# print("Текущая рабочая папка:", os.getcwd())

class Settings(BaseSettings):
	# Желательно вместо str использовать SecretStr
	# для конфиденциальных данных, например, токена бота
	bot_token: SecretStr
	db_name: str
	db_user: str
	db_password: SecretStr
	db_host: str = "localhost"
	db_port: int = 5432
	# Список ID администраторов через запятую (например, "7413924512,5186349076")
	admin_ids: str = ""

	# Начиная со второй версии pydantic, настройки класса настроек задаются
	# через model_config
	# В данном случае будет использоваться файла .env, который будет прочитан
	# с кодировкой UTF-8
	model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')


# При импорте файла сразу создастся
# и провалидируется объект конфига,
# который можно далее импортировать из разных мест
config = Settings()