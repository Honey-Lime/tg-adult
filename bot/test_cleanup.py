import sys
sys.path.insert(0, '.')
import database
import os

json_path = os.path.join(os.path.dirname(__file__), 'delete.json')
print(f"Testing cleanup with {json_path}")
if not os.path.exists(json_path):
    print("JSON file not found, creating dummy")
    with open(json_path, 'w') as f:
        f.write('["test1.jpg", "test2.png"]')

deleted, errors = database.cleanup_by_json(json_path)
print(f"Deleted: {deleted}")
print(f"Errors: {errors}")
print("Test completed.")