import os
import re
import subprocess
import difflib
import ctypes
from pathlib import Path
from typing import Optional
import psutil

from main.config_manager import get_config
from main.app_indexer import load_app_index, build_app_index

# Загрузка индекса приложений (автоматически обновляется если устарел)
try:
    APP_INDEX = load_app_index()
except Exception as e:
    print(f"[APP_INDEX] Ошибка: {e}")
    APP_INDEX = []


# Глобальные переменные
_config = get_config()
COMMANDS_CFG = _config.get("commands", default={})


def _current_username() -> str:
    """Возвращает текущее имя пользователя."""
    return os.environ.get("USERNAME") or os.environ.get("USER") or Path.home().name


def _expand_config_placeholders(s: str) -> str:
    """Раскрывает плейсхолдеры в конфигурации."""
    return s.replace("${USER}", _current_username())


def kill_process(name: str) -> bool:
    """Завершает процесс по имени."""
    found = False
    for proc in psutil.process_iter(['name']):
        try:
            if name.lower() in (proc.info.get('name') or '').lower():
                proc.kill()
                found = True
        except Exception:
            pass
    return found


def _shell_execute(path: str, params: Optional[str] = None, runas: bool = False) -> bool:
    """Выполняет команду через ShellExecute."""
    try:
        verb = "runas" if runas else "open"
        rc = ctypes.windll.shell32.ShellExecuteW(None, verb, path, params, None, 1)
        return rc > 32
    except Exception:
        return False


def execute_predefined_command(text: str) -> Optional[str]:
    """Выполняет предопределённые команды из config.json."""
    lowered = text.lower()
    
    for key, meta in COMMANDS_CFG.items():
        if key not in lowered:
            continue
        
        if 'запусти' in lowered or 'открой' in lowered:
            cmd = meta.get('open')
            if not cmd:
                continue
            try:
                if isinstance(cmd, (list, tuple)):
                    subprocess.Popen(list(cmd))
                    return f"Запускаю {key}."
                
                s = _expand_config_placeholders(str(cmd))
                # Поиск исполняемого файла
                for ext in (".exe", ".bat", ".cmd", ".com", ".ps1"):
                    idx = s.lower().find(ext)
                    if idx != -1:
                        exe_path = s[:idx + len(ext)].strip().strip('"')
                        args = s[idx + len(ext):].strip().split() if s[idx + len(ext):].strip() else []
                        subprocess.Popen([exe_path, *args])
                        return f"Запускаю {key}."
                return f"Ошибка: команда не содержит исполняемый файл."
            except Exception as e:
                return f"Ошибка запуска {key}: {e}"
        
        elif 'закрой' in lowered or 'выключи' in lowered:
            process_name = meta.get('close')
            if not process_name:
                continue
            success = kill_process(process_name)
            return f"Закрываю {key}." if success else f"{key.capitalize()} не запущен."
    
    return None


def _ru_to_en(s: str) -> str:
    table = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
        'и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh',
        'щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    }
    return "".join(table.get(ch, ch) for ch in s)


def _best_app_match(query: str) -> Optional[dict]:
    q = re.sub(r"[^a-zа-я0-9]+", "", query.lower())
    q_en = _ru_to_en(q)
    best_item, best_score = None, 0.0
    
    for item in APP_INDEX:
        for cand in [item.get("display_name", "").lower(), 
                     item.get("exe_name", "").lower(),
                     Path(item.get("lnk_path", "")).stem.lower()]:
            if not cand:
                continue
            
            c_norm = re.sub(r"[^a-zа-я0-9]+", "", cand)
            score = max(
                difflib.SequenceMatcher(None, q, c_norm).ratio(),
                difflib.SequenceMatcher(None, q_en, c_norm).ratio()
            )
            
            if (q in c_norm) or (q_en in c_norm):
                score += 0.2
            
            if score > best_score:
                best_score = score
                best_item = item
    
    return best_item if best_score >= 0.55 else None


def execute_app_command(text: str) -> Optional[str]:
    """Универсальный запуск/закрытие приложений через индекс."""
    lowered = text.lower().strip()
    
    # Исключаем системные команды (компьютер - это power_command)
    if re.search(r"\bкомпьютер\b", lowered):
        return None
    
    # Определение действия
    if re.search(r"\b(закрой|выключи)\b", lowered):
        action = "close"
    elif re.search(r"\b(открой|запусти)\b", lowered):
        action = "open"
    else:
        return None
    
    # Извлечение цели
    m = re.search(r"(?:открой|запусти|закрой|выключи)\s+(.+)", lowered)
    if not m or re.search(r"\bисточник\w*\b", m.group(1)):
        return None
    
    cand = _best_app_match(m.group(1))
    if not cand:
        return None
    
    if action == "open":
        return _open_app(cand)
    else:
        return _close_app(cand)


def _open_app(app: dict) -> str:
    exe_path = app.get("exe_path", "")
    exe_name = app.get("exe_name", "").strip()
    lnk_path = app.get("lnk_path", "")
    
    try:
        # Приоритет: lnk -> exe -> имя
        if lnk_path and os.path.isfile(lnk_path):
            os.startfile(lnk_path)
        elif exe_path and os.path.isfile(exe_path):
            try:
                os.startfile(exe_path)
            except OSError as e:
                if getattr(e, "winerror", 0) == 740:  # Требуются права администратора
                    if not _shell_execute(exe_path, runas=True):
                        raise
                else:
                    raise
        elif exe_name:
            if not _shell_execute(exe_name) and not _shell_execute(exe_name, runas=True):
                raise OSError("ShellExecute не удалось запустить процесс")
        else:
            return "Не удалось запустить: недостаточно данных."
        
        return f"Запускаю {app.get('display_name') or exe_name or 'приложение'}."
    except Exception as e:
        return f"Ошибка запуска: {e}"


def _close_app(app: dict) -> str:
    candidates = []
    
    if exe_name := app.get("exe_name", "").strip():
        candidates.extend([exe_name, Path(exe_name).stem])
    
    if disp := app.get("display_name", "").strip():
        candidates.append(disp)
    
    # Добавляем имя родительской папки (кроме системных)
    for path in [app.get("exe_path"), app.get("lnk_path")]:
        if path:
            parent = Path(path).parent.name
            if parent and parent.lower() not in {
                "system32", "windows", "program files", 
                "program files (x86)", "microsoft", "microsoft office"
            }:
                candidates.append(parent)
    
    # Уникализация
    seen = set()
    unique = []
    for c in candidates:
        c_low = str(c).strip().lower()
        if c_low and len(c_low) >= 2 and c_low not in seen:
            seen.add(c_low)
            unique.append(c)
    
    # Попытка завершить процесс
    any_killed = any(kill_process(c) for c in unique)
    return "Закрываю приложение." if any_killed else "Приложение не найдено среди процессов."


def execute_browser_command(text: str) -> Optional[str]:
    """Открывает браузер по умолчанию."""
    lowered = text.lower().strip()
    
    # Проверяем команду открытия браузера
    if not re.search(r"\b(открой|запусти)\b", lowered):
        return None
    
    if not re.search(r"\bбраузер\w*\b", lowered):
        return None
    
    try:
        # Получаем браузер по умолчанию из реестра Windows
        import winreg
        try:
            # Пытаемся получить путь к браузеру из реестра
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]
            
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 
                               rf"{prog_id}\shell\open\command") as key:
                command = winreg.QueryValueEx(key, "")[0]
            
            # Извлекаем путь к exe из команды
            if command:
                # Убираем параметры командной строки
                exe_path = command.split('"')[1] if '"' in command else command.split()[0]
                subprocess.Popen([exe_path])
                return "Открываю браузер по умолчанию."
        except Exception:
            # Если не удалось через реестр, используем простой способ
            os.startfile("http://")  # type: ignore
            return "Открываю браузер по умолчанию."
    except Exception as e:
        return f"Ошибка открытия браузера: {e}"


def execute_rebuild_index_command(text: str) -> Optional[str]:
    """Обновляет индекс приложений по команде пользователя."""
    lowered = text.lower().strip()
    
    if not re.search(r"\b(обнови|обновить|переиндексир|переиндексируй|пересканируй)\b", lowered):
        return None
    
    if not re.search(r"\b(приложени|программ|индекс)\w*\b", lowered):
        return None
    
    try:
        global APP_INDEX
        print("[APP_INDEX] Запуск переиндексирования...")
        APP_INDEX = build_app_index()
        return f"Индекс приложений обновлён. Найдено приложений: {len(APP_INDEX)}."
    except Exception as e:
        return f"Ошибка обновления индекса: {e}"


def execute_coin_flip_command(text: str) -> Optional[str]:
    """Подбрасывает монетку."""
    if not any(t in text.lower() for t in ['подбрось монет', 'орёл или решк', 'монетк']):
        return None
    
    import random
    result = random.choice(['орёл', 'решка'])
    return f"{'Выпал' if result == 'орёл' else 'Выпала'} {result}"
