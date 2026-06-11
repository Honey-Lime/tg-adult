import os


# Общие тестовые значения окружения для всех pytest-тестов.
# Устанавливаются до импорта тестовых модулей и модулей приложения.
os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('DB_NAME', 'test-db')
os.environ.setdefault('DB_USER', 'test-user')
os.environ.setdefault('DB_PASSWORD', 'test-password')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('ADMIN_IDS', '')
