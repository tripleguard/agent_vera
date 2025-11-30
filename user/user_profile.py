import time
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from user.json_storage import load_json, save_json


@dataclass
class UserNote:
    key: str  # Уникальный ключ заметки (например, "favorite_color", "birthday")
    value: str  # Значение
    created_at: float
    updated_at: float
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserNote':
        return cls(**data)


class UserProfile:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.name: str = ""
        self.notes: Dict[str, UserNote] = {}
        self.preferences: Dict[str, str] = {}
        self._load()
    
    def _load(self) -> None:
        data = load_json(self.file_path, {})
        self.name = data.get('name', '')
        self.notes = {
            k: UserNote.from_dict(v) 
            for k, v in data.get('notes', {}).items()
        }
        self.preferences = data.get('preferences', {})
    
    def _save(self) -> None:
        data = {
            'name': self.name,
            'notes': {k: v.to_dict() for k, v in self.notes.items()},
            'preferences': self.preferences,
        }
        save_json(self.file_path, data, "PROFILE")
    
    def set_name(self, name: str) -> None:
        self.name = name.strip()
        self._save()
    
    def get_name(self) -> str:
        return self.name
    
    def add_note(self, key: str, value: str) -> None:
        now = time.time()
        if key in self.notes:
            note = self.notes[key]
            note.value = value
            note.updated_at = now
        else:
            self.notes[key] = UserNote(
                key=key,
                value=value,
                created_at=now,
                updated_at=now
            )
        self._save()
    
    def get_note(self, key: str) -> Optional[str]:
        note = self.notes.get(key)
        return note.value if note else None
    
    def delete_note(self, key: str) -> bool:
        if key in self.notes:
            del self.notes[key]
            self._save()
            return True
        return False
    
    def get_all_notes(self) -> List[UserNote]:
        return list(self.notes.values())
    
    def set_preference(self, key: str, value: str) -> None:
        self.preferences[key] = value
        self._save()
    
    def get_preference(self, key: str, default: str = "") -> str:
        return self.preferences.get(key, default)


def execute_profile_command(text: str, user_profile: UserProfile) -> Optional[str]:
    import re
    
    lowered = text.lower().strip()
    
    # Запоминание имени
    if m := re.search(r"запомни\s+(?:что\s+)?мен[яь]\s+зовут\s+([а-яёa-z]+)", lowered):
        name = m.group(1).strip().capitalize()
        user_profile.set_name(name)
        return f"Запомнила, вас зовут {name}."
    
    # Запоминание заметки
    if m := re.search(r"запомни\s+(?:что\s+)?(?:мой|моя|моё|мои)\s+(.+?)\s+(?:это\s+)?(.+)", lowered):
        key = m.group(1).strip().replace(' ', '_')
        value = m.group(2).strip()
        user_profile.add_note(key, value)
        return f"Запомнила: {m.group(1)} — {value}"
    
    # Общий запрос заметки
    if m := re.search(r"запомни\s+(.+)", lowered):
        text_to_remember = m.group(1).strip()
        # Создаём ключ из первых слов
        key = '_'.join(text_to_remember.split()[:3])
        user_profile.add_note(key, text_to_remember)
        return f"Запомнила: {text_to_remember}"
    
    # Что знаешь обо мне
    if re.search(r"(?:что\s+(?:ты\s+)?знаешь|расскажи)\s+(?:обо?\s+)?мне", lowered):
        parts = []
        if user_profile.name:
            parts.append(f"Вас зовут {user_profile.name}")
        
        notes = user_profile.get_all_notes()
        if notes:
            for note in notes[:5]:  # Показываем до 5 заметок
                parts.append(f"{note.key.replace('_', ' ')}: {note.value}")
        
        if not parts:
            return "Я пока ничего не знаю о вас. Используйте команду 'запомни'."
        
        return ". ".join(parts) + "."
    
    # Забыть заметку
    if m := re.search(r"забудь\s+(?:про\s+)?(.+)", lowered):
        key = m.group(1).strip().replace(' ', '_')
        if user_profile.delete_note(key):
            return f"Забыла про {m.group(1)}."
        return f"Не нашла заметку про {m.group(1)}."
    
    return None