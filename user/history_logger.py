import re
import time
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime
from user.json_storage import load_json, save_json


@dataclass
class HistoryEntry:
    timestamp: float
    user_text: str
    assistant_response: str
    command_type: str = "general"  # general, web_search, app_control, etc.
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryEntry':
        return cls(**data)
    
    def get_datetime(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")


class HistoryLogger:

    def __init__(self, file_path: Path, max_entries: int = 1000):
        self.file_path = file_path
        self.max_entries = max_entries
        self.entries: List[HistoryEntry] = []
        self._load()
    
    def _load(self) -> None:
        data = load_json(self.file_path, {})
        self.entries = [
            HistoryEntry.from_dict(e) 
            for e in data.get('history', [])
        ]
    
    def _save(self) -> None:
        # Ограничиваем размер истории
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        data = {
            'history': [e.to_dict() for e in self.entries],
            'total_interactions': len(self.entries),
            'last_updated': time.time()
        }
        save_json(self.file_path, data, "История")
    
    def add_entry(
        self, 
        user_text: str, 
        assistant_response: str, 
        command_type: str = "general"
    ) -> None:
        entry = HistoryEntry(
            timestamp=time.time(),
            user_text=user_text.strip(),
            assistant_response=assistant_response.strip(),
            command_type=command_type
        )
        self.entries.append(entry)
        self._save()
    
    def get_recent(self, count: int = 10) -> List[HistoryEntry]:
        return self.entries[-count:] if self.entries else []
    
    def get_by_date(self, date: str) -> List[HistoryEntry]:
        try:
            result = []
            for entry in self.entries:
                entry_date = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d")
                if entry_date == date:
                    result.append(entry)
            return result
        except Exception:
            return []
    
    def search(self, query: str) -> List[HistoryEntry]:
        query_lower = query.lower()
        result = []
        for entry in self.entries:
            if (query_lower in entry.user_text.lower() or 
                query_lower in entry.assistant_response.lower()):
                result.append(entry)
        return result
    
    def clear(self) -> int:
        """Очищает историю. Возвращает количество удалённых записей."""
        count = len(self.entries)
        self.entries.clear()
        self._save()
        return count
    
    def get_statistics(self) -> Dict[str, int]:
        stats = {
            'total': len(self.entries),
            'today': 0,
            'this_week': 0,
        }
        
        if not self.entries:
            return stats
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        week_start = today_start - (6 * 24 * 3600)
        
        for entry in self.entries:
            if entry.timestamp >= today_start:
                stats['today'] += 1
            if entry.timestamp >= week_start:
                stats['this_week'] += 1
        
        return stats


def execute_history_command(text: str, history_logger: HistoryLogger) -> Optional[str]:
    lowered = text.lower().strip()
    
    # Показать историю
    if re.search(r"\b(?:покажи|показать)\s+(?:последн[юи]е?\s+)?истори[юь]", lowered):
        recent = history_logger.get_recent(5)
        if not recent:
            return "История пуста."
        
        lines = []
        for entry in recent:
            time_str = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M")
            lines.append(f"{time_str}: {entry.user_text}")
        
        return "Последние запросы: " + "; ".join(lines)
    
    # Статистика
    if re.search(r"\bстатистик[ау]\b", lowered):
        stats = history_logger.get_statistics()
        return (f"Всего взаимодействий: {stats['total']}. "
                f"Сегодня: {stats['today']}, за неделю: {stats['this_week']}.")
    
    # Очистка истории
    if re.search(r"(очисти|удали|сотри)\s+(всю\s+)?истори[юь]", lowered):
        count = history_logger.clear()
        return f"История очищена. Удалено записей: {count}" if count else "История уже была пуста."
    
    # Поиск в истории
    if m := re.search(r"(?:найди|поищи)\s+в\s+истории\s+(.+)", lowered):
        query = m.group(1).strip()
        results = history_logger.search(query)
        if not results:
            return f"Ничего не найдено по запросу '{query}'."
        
        # Берём последние 3 результата
        lines = []
        for entry in results[-3:]:
            time_str = entry.get_datetime()
            lines.append(f"{time_str}: {entry.user_text}")
        
        return f"Найдено ({len(results)}): " + "; ".join(lines)
    
    return None
