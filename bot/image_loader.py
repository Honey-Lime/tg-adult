import os
import argparse
from pathlib import Path
from collections import defaultdict
import database

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

def extract_date_from_filename(filename):
	"""
	Извлекает дату из имени файла, которая находится между '@' и первой точкой.
	Пример: "some_name@2025-03-10.jpg" -> "2025-03-10"
	Если дата не найдена, возвращает None.
	"""
	try:
		return filename.split('@')[1].split('.')[0]
	except IndexError:
		return None

def collect_images_from_folder(folder_path):
	"""
	Рекурсивно обходит папку и возвращает словарь:
	{ date1: [filename1, filename2, ...], date2: [...], ... }
	Файлы без даты пропускаются.
	"""
	images_by_date = defaultdict(list)
	base = Path(folder_path)
	if not base.is_dir():
		print(f"Предупреждение: {folder_path} не существует, пропускаем.")
		return images_by_date

	for file_path in base.rglob('*'):
		if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
			date = extract_date_from_filename(file_path.name)
			if date:
				images_by_date[date].append(file_path.name)
			else:
				print(f"Предупреждение: не удалось извлечь дату из {file_path.name}, пропускаем.")
	return images_by_date

def merge_dicts(dict_list):
	"""Объединяет несколько словарей {date: [filenames]} в один, суммируя списки."""
	merged = defaultdict(list)
	for d in dict_list:
		for date, files in d.items():
			merged[date].extend(files)
	return merged


def load_to_database(data):
	"""грузит массив изображений в базу данных"""
	for d in data:
		type = 0 if d == 'anime' else 1
		print(d)
		for date in data[d]:
			print(date)
			post_id = database.add_post_record(type, date)
			for picture in data[d][date]:
				print(picture)
				database.add_picture_record(type, post_id, picture)





def main():
	parser = argparse.ArgumentParser(description='Сбор изображений из папок с группировкой по дате.')
	parser.add_argument('--anime', action='append', help='Папка с аниме (можно несколько)')
	parser.add_argument('--real', action='append', help='Папка с реальными фото (можно несколько)')
	parser.add_argument('--output', '-o', required=True, help='Файл для сохранения JSON')
	args = parser.parse_args()

	if not args.anime and not args.real:
		print("Ошибка: укажите хотя бы одну папку через --anime или --real")
		parser.print_help()
		return

	# Сбор и объединение данных по типам
	anime_merged = merge_dicts([collect_images_from_folder(f) for f in (args.anime or [])])
	real_merged = merge_dicts([collect_images_from_folder(f) for f in (args.real or [])])

	result = {
		'anime': dict(anime_merged),
		'real': dict(real_merged)
	}

	load_to_database(result)

	# Статистика
	total_anime = sum(len(v) for v in result['anime'].values())
	total_real = sum(len(v) for v in result['real'].values())
	print(f"Собрано аниме: {total_anime} файлов, реальных: {total_real} файлов")

	# Сохранение в JSON
	import json
	with open(args.output, 'w', encoding='utf-8') as f:
		json.dump(result, f, ensure_ascii=False, indent=2)
	print(f"Результат сохранён в {args.output}")

if __name__ == '__main__':
	main()