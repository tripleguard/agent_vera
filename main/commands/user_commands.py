import re
from typing import Optional


def execute_user_name_command(text: str, user_profile) -> Optional[str]:
    """Сообщает имя пользователя из профиля."""
    lowered = text.lower().strip()
    
    # Проверка на различные варианты запроса имени
    patterns = [
        r"\bмо[её]\s+им[яь]\b",
        r"\bкак\s+мен[яь]\s+зовут\b",
        r"\bты\s+знаешь\s+как\s+мен[яь]\s+зовут\b",
        r"\bкак\s+мо[её]\s+им[яь]\b",
        r"\bназови\s+мо[её]\s+им[яь]\b",
    ]
    
    if any(re.search(p, lowered) for p in patterns):
        if user_profile.name:
            return f"Вас зовут {user_profile.name}."
        else:
            return "Я не знаю вашего имени. Скажите мне как вас зовут."
    
    return None