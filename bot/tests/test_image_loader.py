"""
Тесты для логики импорта контента в image_loader.py.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('DB_NAME', 'test-db')
os.environ.setdefault('DB_USER', 'test-user')
os.environ.setdefault('DB_PASSWORD', 'test-password')

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import image_loader
import database


@pytest.fixture
def import_dirs(tmp_path):
    new_dir = tmp_path / "new"
    new_anime_dir = new_dir / "anime"
    new_real_dir = new_dir / "real"
    new_videos_dir = new_dir / "videos"
    target_anime_dir = tmp_path / "anime"
    target_real_dir = tmp_path / "real"
    target_videos_dir = tmp_path / "videos"

    new_anime_dir.mkdir(parents=True)
    new_real_dir.mkdir(parents=True)
    new_videos_dir.mkdir(parents=True)

    with patch.object(image_loader, 'NEW_DIR', new_dir), \
         patch.object(image_loader, 'NEW_ANIME_DIR', new_anime_dir), \
         patch.object(image_loader, 'NEW_REAL_DIR', new_real_dir), \
         patch.object(image_loader, 'NEW_VIDEOS_DIR', new_videos_dir), \
         patch.object(image_loader, 'IMPORT_JSON_PATH', new_dir / 'import.json'), \
         patch.object(image_loader, 'TARGET_ANIME_DIR', target_anime_dir), \
         patch.object(image_loader, 'TARGET_REAL_DIR', target_real_dir), \
         patch.object(image_loader, 'TARGET_VIDEOS_DIR', target_videos_dir):
        yield {
            'new_dir': new_dir,
            'new_anime_dir': new_anime_dir,
            'new_real_dir': new_real_dir,
            'new_videos_dir': new_videos_dir,
            'target_anime_dir': target_anime_dir,
            'target_real_dir': target_real_dir,
            'target_videos_dir': target_videos_dir,
            'import_json_path': new_dir / 'import.json',
        }


def test_load_from_import_json_returns_zeroes_when_file_missing(import_dirs):
    result = image_loader.load_from_import_json()
    assert result == (0, 0, 0, 0, 0)


def test_load_from_import_json_skips_duplicate_photo_and_video(import_dirs):
    anime_file = import_dirs['new_anime_dir'] / 'photo1.jpg'
    video_file = import_dirs['new_videos_dir'] / 'video1.mp4'
    anime_file.write_bytes(b'photo')
    video_file.write_bytes(b'video')

    import_data = {
        '2026-05-22': {
            'pictures': ['anime/photo1.jpg'],
            'videos': ['videos/video1.mp4'],
        }
    }
    import_dirs['import_json_path'].write_text(json.dumps(import_data), encoding='utf-8')

    with patch.object(database, 'ImageType', database.ImageType), \
         patch.object(database, 'get_post_by_date_and_type', return_value=101), \
         patch.object(database, 'add_post_record') as add_post_record, \
         patch.object(database, 'picture_exists_by_path', return_value=True) as picture_exists, \
         patch.object(database, 'video_exists_by_path', return_value=True) as video_exists, \
         patch.object(database, 'add_picture_record') as add_picture_record, \
         patch.object(database, 'add_video_record') as add_video_record, \
         patch.object(database, 'update_post_have_video', return_value=True) as update_post_have_video, \
         patch.object(image_loader, 'move_file') as move_file:
        result = image_loader.load_from_import_json()

    assert result == (0, 0, 1, 1, 0)
    picture_exists.assert_called_once_with('photo1.jpg')
    video_exists.assert_called_once_with('video1.mp4')
    update_post_have_video.assert_called_once_with(101)
    add_post_record.assert_not_called()
    add_picture_record.assert_not_called()
    add_video_record.assert_not_called()
    move_file.assert_not_called()
    assert anime_file.exists()
    assert video_file.exists()


def test_load_from_import_json_imports_non_duplicate_files(import_dirs):
    anime_file = import_dirs['new_anime_dir'] / 'fresh_photo.jpg'
    video_file = import_dirs['new_videos_dir'] / 'fresh_video.mp4'
    anime_file.write_bytes(b'photo')
    video_file.write_bytes(b'video')

    import_data = {
        '2026-05-23': {
            'pictures': ['anime/fresh_photo.jpg'],
            'videos': ['videos/fresh_video.mp4'],
        }
    }
    import_dirs['import_json_path'].write_text(json.dumps(import_data), encoding='utf-8')

    def fake_move_file(src_path, dest_dir, filename):
        dest_dir.mkdir(parents=True, exist_ok=True)
        destination = dest_dir / filename
        Path(src_path).replace(destination)
        return filename

    with patch.object(database, 'ImageType', database.ImageType), \
         patch.object(database, 'get_post_by_date_and_type', return_value=None), \
         patch.object(database, 'add_post_record', return_value=202) as add_post_record, \
         patch.object(database, 'picture_exists_by_path', return_value=False), \
         patch.object(database, 'video_exists_by_path', return_value=False), \
         patch.object(database, 'add_picture_record', return_value=301) as add_picture_record, \
         patch.object(database, 'add_video_record', return_value=401) as add_video_record, \
         patch.object(database, 'update_post_have_video', return_value=True) as update_post_have_video, \
         patch.object(database, 'update_picture_path') as update_picture_path, \
         patch.object(database, 'update_video_path') as update_video_path, \
         patch.object(database, 'delete_image') as delete_image, \
         patch.object(database, 'delete_video') as delete_video, \
         patch.object(image_loader, 'move_file', side_effect=fake_move_file) as move_file:
        result = image_loader.load_from_import_json()

    assert result == (1, 1, 0, 0, 0)
    add_post_record.assert_called_once_with(database.ImageType.ANIME.value, '2026-05-23')
    add_picture_record.assert_called_once_with(database.ImageType.ANIME.value, 202, 'fresh_photo.jpg')
    add_video_record.assert_called_once_with(202, 'fresh_video.mp4')
    update_post_have_video.assert_called_once_with(202)
    update_picture_path.assert_not_called()
    update_video_path.assert_not_called()
    delete_image.assert_not_called()
    delete_video.assert_not_called()
    assert move_file.call_count == 2
    assert not anime_file.exists()
    assert not video_file.exists()
    assert (import_dirs['target_anime_dir'] / 'fresh_photo.jpg').exists()
    assert (import_dirs['target_videos_dir'] / 'fresh_video.mp4').exists()
