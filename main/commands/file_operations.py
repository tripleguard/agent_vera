import os
import re
from pathlib import Path
from typing import Optional, List
import difflib

from main.commands.app_control import _ru_to_en

# Импортируем новый индексатор файлов
try:
    from main.file_indexer import smart_search, search_windows_index_folders, get_indexed_directories
    HAS_FILE_INDEXER = True
except ImportError:
    try:
        from file_indexer import smart_search, search_windows_index_folders, get_indexed_directories
        HAS_FILE_INDEXER = True
    except ImportError:
        HAS_FILE_INDEXER = False


# Fallback: стандартные пути для поиска (если индексатор недоступен)
SEARCH_LOCATIONS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
    Path.home() / "Videos",
    Path.home() / "Music",
]

# Добавляем OneDrive если есть
try:
    _onedrive = os.environ.get("OneDrive")
    if _onedrive:
        onedrive_path = Path(_onedrive).expanduser()
        SEARCH_LOCATIONS.extend([
            onedrive_path / "Documents",
            onedrive_path / "Desktop",
        ])
except Exception:
    pass

# Добавляем корни всех дисков для ручного поиска (если Windows Search не проиндексировал)
try:
    import string
    from ctypes import windll
    
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(Path(f"{letter}:/"))
        bitmask >>= 1
    
    SEARCH_LOCATIONS.extend(drives)
    
    # Добавляем текущую рабочую директорию (агента)
    SEARCH_LOCATIONS.append(Path.cwd())
    
except Exception:
    pass


def execute_file_command(text: str) -> Optional[str]:
    """Обрабатывает команды поиска и открытия файлов."""

    lowered = text.lower().strip()
    
    # Открыть/найти файл
    if m := re.search(r"\b(открой|найди|найти|открыть)\s+файл\s+(.+)", lowered):
        file_name = m.group(2).strip()
        return _find_and_open_file(file_name)
    
    return None


def execute_folder_command(text: str) -> Optional[str]:
    """Обрабатывает команды поиска и открытия папок."""
    lowered = text.lower().strip()
    
    # Открыть/найти папку
    if m := re.search(r"\b(открой|найди|найти|открыть)\s+папк[уа]\s+(.+)", lowered):
        folder_name = m.group(2).strip()
        return _find_and_open_folder(folder_name)
    
    return None


def _fuzzy_match_filename(query: str, candidates: List[Path]) -> Optional[Path]:
    """Нечёткое сопоставление названия файла с кандидатами.
    
    Возвращает лучшее совпадение или None.
    Поддерживает транслитерацию русского запроса для поиска по латинским названиям.
    """
    query_clean = query.lower().strip()
    query_translit = _ru_to_en(query_clean)  # Транслитерация для поиска
    best_match = None
    best_score = 0.0
    
    for candidate in candidates:
        # Сравниваем с именем файла без расширения
        name_no_ext = candidate.stem.lower()
        
        # Точное совпадение - высший приоритет
        if query_clean == name_no_ext or query_translit == name_no_ext:
            return candidate
        
        # Вхождение подстроки (оригинал или транслит)
        if query_clean in name_no_ext or query_translit in name_no_ext:
            score = 0.9
        else:
            # Нечёткое сравнение (лучший результат из оригинала и транслита)
            score = max(
                difflib.SequenceMatcher(None, query_clean, name_no_ext).ratio(),
                difflib.SequenceMatcher(None, query_translit, name_no_ext).ratio()
            )
        
        if score > best_score:
            best_score = score
            best_match = candidate
    
    # Возвращаем только если совпадение достаточно хорошее
    return best_match if best_score >= 0.6 else None


def _find_and_open_file(query: str) -> str:
    """Ищет файл и открывает его."""
    try:
        print(f"[FILE] Поиск файла: {query}")
        
        # Используем Windows Search через file_indexer (быстрый поиск по всей системе)
        if HAS_FILE_INDEXER:
            results = smart_search(query, max_results=20, search_folders=False)
            if results:
                # Фильтруем по нечёткому совпадению
                candidates = [Path(r["path"]) for r in results if r.get("path")]
                best_match = _fuzzy_match_filename(query, candidates)
                
                if best_match:
                    os.startfile(str(best_match))  # type: ignore
                    return f"Открываю файл '{best_match.name}'."
        
        # Fallback: быстрый поиск в основных папках
        quick_results = []
        for search_dir in SEARCH_LOCATIONS[:3]:  # Только Documents, Downloads, Desktop
            if not search_dir.exists():
                continue
            
            try:
                # Поиск только в корне папки (быстро)
                for item in search_dir.iterdir():
                    if item.is_file():
                        quick_results.append(item)
            except (PermissionError, OSError):
                continue
        
        # Нечёткое сопоставление
        best_match = _fuzzy_match_filename(query, quick_results)
        
        if best_match:
            # Открываем файл
            os.startfile(str(best_match))  # type: ignore
            return f"Открываю файл '{best_match.name}'."
        
        return f"Файл '{query}' не найден."
    
    except Exception as e:
        print(f"[FILE] Ошибка: {e}")
        return f"Ошибка при поиске файла: {e}"


def _find_and_open_folder(query: str) -> str:
    """Ищет папку и открывает её в проводнике."""
    try:
        print(f"[FOLDER] Поиск папки: {query}")
        
        # Используем Windows Search для поиска папок
        if HAS_FILE_INDEXER:
            results = search_windows_index_folders(query, max_results=20)
            if results:
                candidates = [Path(r["path"]) for r in results if r.get("path")]
                best_match = _fuzzy_match_filename(query, candidates)
                
                if best_match:
                    os.startfile(str(best_match))
                    return f"Открываю папку '{best_match.name}'."
        
        # Fallback: быстрый поиск в стандартных папках
        quick_results = []
        for search_dir in SEARCH_LOCATIONS:
            if not search_dir.exists():
                continue
            
            try:
                # Если это корень диска, ищем только папки на 1 уровне
                is_root = len(search_dir.parts) == 1
                
                # Поиск на первом уровне
                for item in search_dir.iterdir():
                    if item.is_dir():
                        quick_results.append(item)
                
                # Проверка второго уровня для Documents и корней дисков (если не системные)
                if (search_dir.name in ["Documents", "Документы"] or is_root) and search_dir.name not in ["Windows", "Program Files"]:
                    for item in search_dir.iterdir():
                        if item.is_dir():
                            # Пропускаем скрытые и системные папки
                            if item.name.startswith(('.', '$')) or item.name.lower() in ['windows', 'program files', 'program files (x86)', 'users']:
                                continue
                                
                            try:
                                for subitem in item.iterdir():
                                    if subitem.is_dir():
                                        quick_results.append(subitem)
                            except (PermissionError, OSError):
                                continue
            except (PermissionError, OSError):
                continue
        
        # Нечёткое сопоставление
        best_match = _fuzzy_match_filename(query, quick_results)
        
        if best_match:
            # Открываем папку в проводнике
            os.startfile(str(best_match))
            return f"Открываю папку '{best_match.name}'."
        
        return f"Папка '{query}' не найдена."
    
    except Exception as e:
        print(f"[FOLDER] Ошибка: {e}")
        return f"Ошибка при поиске папки: {e}"
