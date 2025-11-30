import re
import webbrowser
import difflib
from typing import Optional, List

from main.config_manager import get_config

_config = get_config()
SITES_CFG = _config.get("sites", default={})

# Ссылка на список URL последнего поиска
_LAST_SEARCH_URLS_REF: Optional[List[str]] = None


def set_last_search_urls_ref(ref: List[str]) -> None:
    """Устанавливает ссылку на список URL последнего поиска."""
    global _LAST_SEARCH_URLS_REF
    _LAST_SEARCH_URLS_REF = ref


def execute_open_site_command(text: str) -> Optional[str]:
    """Открывает сайт по алиасу из конфига."""
    lowered = text.lower().strip()
    
    if not (("открой" in lowered) or ("запусти" in lowered)):
        return None
    if re.search(r"\bисточник\w*\b", lowered):
        return None
    
    m = re.search(r"(?:открой|запусти)\s+(.+)$", lowered)
    if not m or not SITES_CFG:
        return None
    
    tail = re.sub(r"\b(сайт|в браузере|браузер)\b", "", m.group(1)).strip()
    if not tail:
        return None
    
    best_key = _fuzzy_match(tail, SITES_CFG)
    if best_key:
        try:
            webbrowser.open(SITES_CFG[best_key], new=2)
            return f"Открываю {best_key}."
        except Exception as e:
            return f"Не удалось открыть {best_key}: {e}"
    return None


def execute_open_sources_command(text: str) -> Optional[str]:
    """Открывает источники последнего веб-поиска."""
    if not re.search(r"\bоткрой\s+источник\w*\b", text.lower()):
        return None
    
    urls = _LAST_SEARCH_URLS_REF or []
    if not urls:
        return "Источники отсутствуют. Сначала выполните поиск."
    
    opened = sum(1 for u in urls if _safe_open_url(u))
    return f"Открываю источники ({opened})."


def execute_ambiguous_clean_command(text: str) -> Optional[str]:
    """Обрабатывает неоднозначные команды очистки."""
    t = text.lower().strip()
    
    # Если явно указан объект очистки - не перехватываем
    if re.search(r"\b(корзин|кэш|буфер|истор|загруз|памят|cookie|temp|временн)\w*\b", t):
        return None
    
    # Глаголы очистки без объекта
    if re.fullmatch(r"(очисти|очистить|почисти|почистить|опустоши|опустошить|сотри|стереть)", t):
        return "Уточните, что очистить: например, 'очисти корзину'."
    
    return None


def _fuzzy_match(query: str, candidates: dict, threshold: float = 0.6) -> Optional[str]:
    """Нечёткое сопоставление запроса со словарём кандидатов."""
    best_key, best_score = None, 0.0
    query_low = query.lower()
    
    for key in candidates:
        key_low = key.lower()
        score = difflib.SequenceMatcher(None, query_low, key_low).ratio()
        if query_low in key_low:
            score += 0.15
        if score > best_score:
            best_score = score
            best_key = key
    
    return best_key if best_score >= threshold else None


def _safe_open_url(url: str) -> bool:
    """Безопасно открывает URL."""
    try:
        webbrowser.open(url, new=2)
        return True
    except Exception:
        return False
