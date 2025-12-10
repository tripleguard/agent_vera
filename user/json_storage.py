import json
from pathlib import Path
from typing import Any, Optional


def load_json(file_path: Path, default: Any = None) -> Any:
    """Загружает данные из JSON файла. Возвращает default при ошибке."""
    try:
        if file_path.exists():
            return json.loads(file_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[JSON] Ошибка загрузки {file_path.name}: {e}")
    return default if default is not None else {}


def save_json(file_path: Path, data: Any, log_name: str = "JSON") -> bool:
    """Сохраняет данные в JSON файл. Возвращает True при успехе."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return True
    except Exception as e:
        print(f"[{log_name}] Ошибка сохранения: {e}")
        return False
