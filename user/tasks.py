import re
import subprocess
import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict
from user.json_storage import load_json, save_json

# Формат времени для хранения в JSON (человекочитаемый)
_TIME_FORMAT = "%Y-%m-%d-%H-%M"


def _ts_to_str(ts: float) -> str:
    """Конвертирует unix timestamp в строковый формат."""
    return datetime.datetime.fromtimestamp(ts).strftime(_TIME_FORMAT)


def _now_str() -> str:
    """Возвращает текущее время в строковом формате."""
    return datetime.datetime.now().strftime(_TIME_FORMAT)


@dataclass
class Task:
    id: int
    text: str
    created_at: str  # Формат "2025-12-02-19-57"
    completed: bool = False
    completed_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        # Поддержка старого формата (float)
        created = data.get('created_at')
        if isinstance(created, (int, float)):
            data['created_at'] = _ts_to_str(created)
        
        completed = data.get('completed_at')
        if isinstance(completed, (int, float)):
            data['completed_at'] = _ts_to_str(completed)
        
        return cls(**data)


class TaskManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.tasks: List[Task] = []
        self._load()
    
    def _load(self) -> None:
        data = load_json(self.file_path, {})
        self.tasks = [Task.from_dict(t) for t in data.get('tasks', [])]
    
    def _save(self) -> None:
        data = {'tasks': [t.to_dict() for t in self.tasks]}
        save_json(self.file_path, data, "TASKS")
    
    def add_task(self, text: str) -> Task:
        task_id = max([t.id for t in self.tasks], default=0) + 1
        task = Task(
            id=task_id,
            text=text.strip(),
            created_at=_now_str()
        )
        self.tasks.append(task)
        self._save()
        return task
    
    def complete_task(self, text: str) -> Optional[Task]:
        text_lower = text.lower().strip()
        
        for task in self.tasks:
            if not task.completed and text_lower in task.text.lower():
                task.completed = True
                task.completed_at = _now_str()
                self._save()
                return task
        
        return None
    
    def complete_task_by_id(self, task_id: int) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id and not task.completed:
                task.completed = True
                task.completed_at = _now_str()
                self._save()
                return task
        return None
    
    def delete_task(self, text: str) -> bool:
        text_lower = text.lower().strip()
        
        for i, task in enumerate(self.tasks):
            if text_lower in task.text.lower():
                self.tasks.pop(i)
                self._save()
                return True
        
        return False
    
    def get_pending_tasks(self) -> List[Task]:
        return [t for t in self.tasks if not t.completed]
    
    def get_completed_tasks(self) -> List[Task]:
        return [t for t in self.tasks if t.completed]
    
    def get_all_tasks(self) -> List[Task]:
        return self.tasks.copy()
    
    def clear_completed(self) -> int:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if not t.completed]
        self._save()
        return before - len(self.tasks)


def _parse_ordinal(text: str) -> Optional[int]:
    from main.lang_ru import ORDINAL_WORDS
    
    if text.isdigit():
        return int(text)
    return ORDINAL_WORDS.get(text)


def execute_task_command(text: str, task_manager: TaskManager) -> Optional[str]:
    lowered = text.lower().strip()
    
    # Открытие файла с задачами
    if re.search(r"\b(?:открой|открыть|покажи)\s+(?:файл\s+)?задач", lowered):
        try:
            file_path = str(task_manager.file_path.absolute())
            # Открываем в блокноте по умолчанию
            subprocess.Popen(['notepad.exe', file_path])
            return f"Открываю файл задач."
        except Exception as e:
            print(f"[TASKS] Ошибка открытия файла: {e}")
            return "Не удалось открыть файл задач."
    
    # Добавление задачи
    if m := re.search(r"(?:постав[ьи]|добав[ьи])\s+задач[уи]\s+(.+)", lowered):
        task_text = m.group(1).strip()
        if task_text:
            task = task_manager.add_task(task_text)
            return f"Задача добавлена: {task.text}"
        return "Не указан текст задачи."
    
    # Отметка задачи выполненной по порядковому номеру
    if m := re.search(r"(?:отметь|отмет[иь]|заверш[иь])\s+(первую|вторую|третью|четвертую|четвёртую|пятую|шестую|седьмую|восьмую|девятую|десятую|\d+)[-\s]*(?:ую|ую|уй|ий|ой|ю)?\s*задач[уи]\s+(?:выполненн|завершённ)", lowered):
        task_num = _parse_ordinal(m.group(1).strip())
        
        if task_num:
            pending = task_manager.get_pending_tasks()
            if 1 <= task_num <= len(pending):
                task = pending[task_num - 1]
                task.completed = True
                task.completed_at = _now_str()
                task_manager._save()
                return f"Задача выполнена: {task.text}"
            return f"Нет задачи с номером {task_num}. Всего активных задач: {len(pending)}"
        return "Не удалось определить номер задачи."
    
    # Отметка задачи выполненной по тексту
    if m := re.search(r"(?:отметь|отмет[иь]|заверш[иь])\s+задач[уи]\s+(.+?)\s+(?:выполненн|завершённ)", lowered):
        task_text = m.group(1).strip()
        task = task_manager.complete_task(task_text)
        if task:
            return f"Задача выполнена: {task.text}"
        return f"Задача '{task_text}' не найдена среди активных."
    
    # Удаление задачи по порядковому номеру
    if m := re.search(r"удал[иь]\s+(первую|вторую|третью|четвертую|четвёртую|пятую|шестую|седьмую|восьмую|девятую|десятую|\d+)[-\s]*(?:ую|ую|уй|ий|ой|ю)?\s*задач[уи]", lowered):
        task_num = _parse_ordinal(m.group(1).strip())
        
        if task_num:
            pending = task_manager.get_pending_tasks()
            if 1 <= task_num <= len(pending):
                task = pending[task_num - 1]
                task_manager.tasks.remove(task)
                task_manager._save()
                return f"Задача удалена: {task.text}"
            return f"Нет задачи с номером {task_num}. Всего активных задач: {len(pending)}"
        return "Не удалось определить номер задачи."
    
    # Удаление задачи по тексту
    if m := re.search(r"удал[иь]\s+задач[уи]\s+(.+)", lowered):
        task_text = m.group(1).strip()
        if task_manager.delete_task(task_text):
            return f"Задача удалена."
        return f"Задача не найдена."
    
    # Список задач
    if re.search(r"\b(?:список|покажи|какие)\s+задач", lowered) or lowered in ["задачи", "список задач"]:
        pending = task_manager.get_pending_tasks()
        if not pending:
            return "У вас нет активных задач."
        
        lines = [f"{i+1}. {t.text}" for i, t in enumerate(pending[:10])]
        count_text = f"активных задач: {len(pending)}" if len(pending) > 10 else f"активные задачи"
        return f"{count_text.capitalize()}: " + ", ".join(lines)
    
    # Очистка выполненных
    if re.search(r"(?:очисти|удали)\s+(?:выполненн|завершённ)\w*\s+задач", lowered):
        count = task_manager.clear_completed()
        if count > 0:
            return f"Удалено выполненных задач: {count}"
        return "Нет выполненных задач для удаления."
    
    return None
