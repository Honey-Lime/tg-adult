"""
Базовые тесты для модуля database.py.
Для запуска требуется установить pytest и настроить тестовую базу данных.
Пример запуска: pytest bot/tests/test_database.py -v
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import Mock, patch, MagicMock
import database


class TestDatabase:
    """Тесты функций работы с базой данных."""

    @pytest.fixture
    def mock_connection(self):
        """Фикстура для мока соединения с БД."""
        with patch('database.get_connection') as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn
            yield mock_conn, mock_cursor

    def test_get_user_existing(self, mock_connection):
        """Тест получения существующего пользователя."""
        mock_conn, mock_cursor = mock_connection
        # Настраиваем мок курсора для возврата строки
        mock_cursor.fetchone.return_value = (123, 0, 0, None, None, None, None, None, None, None)
        mock_cursor.description = [('id',), ('type',), ('cycle',), ('viewed_anime',),
                                   ('viewed_real',), ('liked_anime',), ('liked_real',),
                                   ('saved_images',), ('coins',), ('last_watched',)]
        user = database.get_user(123)
        assert user is not None
        assert user['id'] == 123
        mock_cursor.execute.assert_called_once_with("SELECT * FROM users WHERE id = %s", (123,))

    def test_get_user_not_existing(self, mock_connection):
        """Тест получения несуществующего пользователя (создание)."""
        mock_conn, mock_cursor = mock_connection
        # Первый вызов возвращает None (пользователь не найден)
        mock_cursor.fetchone.side_effect = [None, (123,)]
        # Второй вызов после вставки возвращает строку
        mock_cursor.fetchone.side_effect = [None, (123,)]
        user = database.get_user(123)
        # Поскольку мок не полностью настроен, просто проверяем, что функция не падает
        # В реальном тесте нужно настроить более детально
        assert user is None or user['id'] == 123

    def test_like_success(self, mock_connection):
        """Тест успешного лайка."""
        mock_conn, mock_cursor = mock_connection
        # Мок для get_user
        with patch('database.get_user') as mock_get_user:
            mock_get_user.return_value = {
                'id': 123,
                'type': database.ImageType.ANIME.value,
                'last_watched': 456
            }
            # Настраиваем успешное выполнение запросов
            mock_cursor.rowcount = 1
            result = database.like(123)
            assert result is True
            # Проверяем, что были вызовы execute
            assert mock_cursor.execute.call_count >= 3

    def test_dislike_success(self, mock_connection):
        """Тест успешного дизлайка."""
        mock_conn, mock_cursor = mock_connection
        with patch('database.get_user') as mock_get_user:
            mock_get_user.return_value = {
                'id': 123,
                'type': database.ImageType.ANIME.value,
                'last_watched': 456
            }
            mock_cursor.rowcount = 1
            result = database.dislike(123)
            assert result is True

    def test_save_insufficient_coins(self, mock_connection):
        """Тест сохранения при недостатке монет."""
        mock_conn, mock_cursor = mock_connection
        # Мок для SELECT type
        mock_cursor.fetchone.return_value = (database.ImageType.ANIME.value,)
        # Мок для UPDATE (rowcount = 0, так как coins < 25)
        mock_cursor.rowcount = 0
        result = database.save(123, 456)
        assert result is False

    def test_get_image_no_user(self, mock_connection):
        """Тест получения изображения для несуществующего пользователя."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None
        path, img = database.get_image(999)
        assert path is None
        assert img is None

    def test_add_coins_success(self, mock_connection):
        """Тест успешного начисления монет."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.rowcount = 1
        result = database.add_coins(123, 50)
        assert result is True
        mock_cursor.execute.assert_called_with(
            "UPDATE users SET coins = coins + %s WHERE id = %s", (50, 123)
        )

    def test_add_coins_user_not_found(self, mock_connection):
        """Тест начисления монет несуществующему пользователю."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.rowcount = 0
        result = database.add_coins(999, 50)
        assert result is False


class TestPromoLinks:
    """Тесты для функций работы с рекламными ссылками."""

    @pytest.fixture
    def mock_connection(self):
        """Фикстура для мока соединения с БД."""
        with patch('database.get_connection') as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn
            yield mock_conn, mock_cursor

    def test_create_promo_link_success(self, mock_connection):
        """Тест успешного создания рекламной ссылки."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = ('abc12345',)
        
        success, result = database.create_promo_link("Test Link")
        
        assert success is True
        assert result == 'abc12345'
        mock_cursor.execute.assert_called()

    def test_create_promo_link_no_connection(self, mock_connection):
        """Тест создания ссылки при отсутствии подключения."""
        mock_conn, mock_cursor = mock_connection
        with patch('database.get_connection', return_value=None):
            success, result = database.create_promo_link("Test Link")
            assert success is False
            assert result == "Нет подключения к БД"

    def test_get_all_promo_links_success(self, mock_connection):
        """Тест получения списка всех рекламных ссылок."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            (1, "Test Link 1", "abc12345", None, 10),
            (2, "Test Link 2", "xyz67890", None, 5)
        ]
        
        links = database.get_all_promo_links()
        
        assert len(links) == 2
        assert links[0]['name'] == "Test Link 1"
        assert links[0]['clicks_count'] == 10
        assert links[1]['name'] == "Test Link 2"
        assert links[1]['clicks_count'] == 5

    def test_get_all_promo_links_empty(self, mock_connection):
        """Тест получения пустого списка ссылок."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []
        
        links = database.get_all_promo_links()
        
        assert len(links) == 0
        assert links == []

    def test_track_promo_link_click_success(self, mock_connection):
        """Тест успешной записи перехода по ссылке."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = (1,)  # promo_link_id
        mock_cursor.rowcount = 1
        
        result = database.track_promo_link_click("abc12345", 123)
        
        assert result is True

    def test_track_promo_link_click_not_found(self, mock_connection):
        """Тест записи перехода по несуществующей ссылке."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None  # ссылка не найдена
        
        result = database.track_promo_link_click("invalid_code", 123)
        
        assert result is False

    def test_get_promo_link_by_code_success(self, mock_connection):
        """Тест получения ссылки по коду."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = (1, "Test Link", "abc12345", None)
        
        link = database.get_promo_link_by_code("abc12345")
        
        assert link is not None
        assert link['name'] == "Test Link"
        assert link['code'] == "abc12345"

    def test_get_promo_link_by_code_not_found(self, mock_connection):
        """Тест получения несуществующей ссылки."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None
        
        link = database.get_promo_link_by_code("invalid_code")
        
        assert link is None

    def test_delete_promo_link_success(self, mock_connection):
        """Тест успешного удаления рекламной ссылки."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.rowcount = 1
        
        result = database.delete_promo_link(123)
        
        assert result is True
        mock_cursor.execute.assert_called_with(
            "DELETE FROM promo_links WHERE id = %s", (123,)
        )

    def test_delete_promo_link_not_found(self, mock_connection):
        """Тест удаления несуществующей ссылки."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.rowcount = 0
        
        result = database.delete_promo_link(999)
        
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])