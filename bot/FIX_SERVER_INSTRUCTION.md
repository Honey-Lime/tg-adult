# Инструкция по исправлению ошибки "null value in column id of relation videos"

## Проблема

На сервере Linux в базе данных нарушена связь между последовательностью `videos_id_seq` и полем `id` таблицы `videos`. При попытке добавить видео PostgreSQL не может автоматически сгенерировать id.

## Решение

### Вариант 1: Запуск Python-скрипта (рекомендуется)

1. **Скопируйте скрипт на сервер:**

   ```bash
   # Из локальной директории проекта
   scp bot/fix_server_sequence.py root@your-server:/root/adult-telegramm-bot/bot/
   ```

2. **Подключитесь к серверу:**

   ```bash
   ssh root@your-server
   cd /root/adult-telegramm-bot/bot
   ```

3. **Запустите скрипт:**

   ```bash
   python3 fix_server_sequence.py
   ```

4. **Перезапустите бота:**

   ```bash
   # Если бот запущен через systemd
   systemctl restart telegram-bot

   # Или если через screen/tmux
   # Остановите текущий процесс и запустите заново
   ```

### Вариант 2: Прямое выполнение SQL через psql

1. **Подключитесь к серверу:**

   ```bash
   ssh root@your-server
   ```

2. **Выполните SQL команды:**

   ```bash
   sudo -u postgres psql -d adult_tg_bot_db -c "
   SELECT setval('videos_id_seq',
                 COALESCE((SELECT MAX(id) FROM videos), 0) + 1,
                 false);
   "
   ```

3. **Проверьте результат:**

   ```bash
   sudo -u postgres psql -d adult_tg_bot_db -c "
   SELECT pg_get_serial_sequence('videos', 'id');
   "
   ```

   Должно вернуть: `public.videos_id_seq`

4. **Перезапустите бота**

## Проверка после исправления

Запустите загрузку видео ещё раз:

```bash
cd /root/adult-telegramm-bot/bot
python3 image_loader.py
```

Ошибки `null value in column "id"` больше не должно быть.

## Диагностика

Если проблема сохраняется, проверьте:

```bash
sudo -u postgres psql -d adult_tg_bot_db -c "
SELECT column_default
FROM information_schema.columns
WHERE table_name = 'videos' AND column_name = 'id';
"
```

Должно вернуть: `nextval('videos_id_seq'::regclass)`
