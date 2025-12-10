import os
import re
from pathlib import Path
from typing import Optional, List

from main.lang_ru import ru_to_en
from main.utils.fuzzy import fuzzy_match

# Импортируем индексатор файлов
try:
    from main.file_indexer import smart_search, search_windows_index_folders
    HAS_FILE_INDEXER = True
except ImportError:
    try:
        from file_indexer import smart_search, search_windows_index_folders
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


def _parse_folder_query(query: str) -> tuple[str, Optional[str]]:
    """Парсит запрос: 'bb на диске d' -> ('bb', 'D')"""
    query = query.strip().lower()
    
    # Паттерны для указания диска
    # "на диске d", "на диск d", "на d диске", "диск d", "на d"
    patterns = [
        r'(.+?)\s+на\s+диск[еу]?\s+([a-zа-я])\s*$',  # "bb на диске d"
        r'(.+?)\s+на\s+([a-zа-я])\s+диск[еу]?\s*$',  # "bb на d диске"
        r'(.+?)\s+диск\s+([a-zа-я])\s*$',             # "bb диск d"
        r'(.+?)\s+на\s+([a-zа-я])\s*$',               # "bb на d"
        r'(.+?)\s+([a-zа-я]):\s*$',                   # "bb d:"
    ]
    
    # Особые случаи: русские буквы которые звучат как английские диски
    # 'в' звучит как 'B', 'и' как 'E'
    ru_sound_to_drive = {'в': 'b', 'и': 'e'}
    
    for pattern in patterns:
        if m := re.search(pattern, query):
            folder_name = m.group(1).strip()
            drive_letter = m.group(2).lower()
            
            # Конвертируем русскую букву в латинскую
            if drive_letter in ru_sound_to_drive:
                drive_letter = ru_sound_to_drive[drive_letter]
            elif ord(drive_letter) >= ord('а'):  # Русская буква
                drive_letter = ru_to_en(drive_letter)[0]  # Первая буква транслита
            
            # Проверяем что это валидная буква диска
            if drive_letter in 'abcdefghijklmnopqrstuvwxyz':
                return folder_name, drive_letter.upper()
    
    return query, None


def execute_folder_command(text: str) -> Optional[str]:
    """Обрабатывает команды поиска и открытия папок."""
    lowered = text.lower().strip()
    
    # Открыть/найти папку
    if m := re.search(r"\b(открой|найди|найти|открыть)\s+папк[уа]\s+(.+)", lowered):
        folder_name = m.group(2).strip()
        return _find_and_open_folder(folder_name)
    
    return None


def _fuzzy_match_filename(query: str, candidates: List[Path], drive_filter: Optional[str] = None) -> Optional[Path]:

    query_clean = query.lower().strip()
    query_translit = ru_to_en(query_clean)  # Транслитерация для поиска
    
    # Фильтруем по диску если указан
    if drive_filter:
        drive_prefix = f"{drive_filter.upper()}:"
        candidates = [c for c in candidates if str(c).upper().startswith(drive_prefix)]
    
    if not candidates:
        return None
    
    # Собираем кандидатов с оценками
    scored_candidates = []
    
    for candidate in candidates:
        name = candidate.name.lower()  # Полное имя папки/файла
        name_no_ext = candidate.stem.lower()  # Без расширения
        
        # Точное совпадение - максимальный приоритет
        if query_clean == name or query_clean == name_no_ext:
            return candidate
        if query_translit == name or query_translit == name_no_ext:
            return candidate
        
        # Вычисляем оценку
        score = 0.0
        
        # Начинается с запроса (высокий приоритет)
        if name.startswith(query_clean) or name.startswith(query_translit):
            # Бонус за короткое имя (чем короче - тем лучше совпадение)
            length_bonus = max(0, 1 - (len(name) - len(query_clean)) / 20)
            score = 0.95 + length_bonus * 0.04
        # Вхождение подстроки
        elif query_clean in name or query_translit in name:
            # Штраф за длинные имена при коротком запросе
            # "bb" в "MicrosoftTeams_8wekyb3d8bbwe" получит низкий score
            query_len = len(query_clean)
            name_len = len(name)
            if query_len <= 3 and name_len > query_len * 4:
                # Короткий запрос в длинном имени - низкий приоритет
                score = 0.5
            else:
                length_ratio = query_len / name_len
                score = 0.7 + length_ratio * 0.2
        else:
            # Нечёткое сравнение через общий модуль
            score = max(
                fuzzy_match(query_clean, name_no_ext, boost_substring=False),
                fuzzy_match(query_translit, name_no_ext, boost_substring=False)
            )
        
        if score >= 0.5:
            scored_candidates.append((score, candidate))
    
    if not scored_candidates:
        return None
    
    # Сортируем по убыванию score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    
    best_score, best_match = scored_candidates[0]
    
    # Возвращаем только если совпадение достаточно хорошее
    return best_match if best_score >= 0.6 else None


def find_file(query: str) -> Optional[Path]:
    """
    Публичная функция поиска файла по имени.
    Использует Windows Search и fallback поиск.
    
    Args:
        query: Имя файла (с расширением или без)
    
    Returns:
        Path к найденному файлу или None
    """
    query = query.strip().strip('"\'')
    
    # Если указан полный путь — проверяем его
    if os.path.isabs(query):
        path = Path(query)
        return path if path.exists() and path.is_file() else None
    
    basename = Path(query).name
    
    # 1. Windows Search
    if HAS_FILE_INDEXER:
        try:
            results = smart_search(basename, max_results=20, search_folders=False)
            if results:
                candidates = [Path(r["path"]) for r in results if r.get("path")]
                best_match = _fuzzy_match_filename(basename, candidates)
                if best_match:
                    return best_match
        except Exception as e:
            print(f"[FILE] Ошибка Windows Search: {e}")
    
    # 2. Fallback: поиск в стандартных папках
    quick_results = []
    for search_dir in SEARCH_LOCATIONS[:6]:  # Documents, Downloads, Desktop + OneDrive
        if not search_dir.exists():
            continue
        try:
            for item in search_dir.iterdir():
                if item.is_file():
                    quick_results.append(item)
        except (PermissionError, OSError):
            continue
    
    return _fuzzy_match_filename(basename, quick_results)


def _safe_startfile(path: Path) -> bool:
    try:
        # Преобразуем Path в строку с абсолютным путём
        path_str = str(path.resolve())
        print(f"[OPEN] Открываю: {path_str}")
        os.startfile(path_str)
        return True
    except OSError as e:
        # Пробуем альтернативный способ через explorer
        print(f"[OPEN] os.startfile не удалось ({e}), пробую explorer...")
        try:
            import subprocess
            subprocess.Popen(['explorer', str(path.resolve())])
            return True
        except Exception as e2:
            print(f"[OPEN] explorer тоже не удалось: {e2}")
            return False
    except Exception as e:
        print(f"[OPEN] Ошибка: {e}")
        return False


def _find_and_open_file(query: str) -> str:
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
                    if _safe_startfile(best_match):
                        return f"Открываю файл '{best_match.name}'."
                    return f"Не удалось открыть файл '{best_match.name}'."
        
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
            if _safe_startfile(best_match):
                return f"Открываю файл '{best_match.name}'."
            return f"Не удалось открыть файл '{best_match.name}'."
        
        return f"Файл '{query}' не найден."
    
    except Exception as e:
        print(f"[FILE] Ошибка: {e}")
        return f"Ошибка при поиске файла: {e}"


def _search_drive_for_folder(drive: str, folder_name: str, max_depth: int = 2) -> List[Path]:
    results = []
    drive_path = Path(f"{drive}:/")
    
    if not drive_path.exists():
        return results
    
    folder_lower = folder_name.lower()
    folder_translit = ru_to_en(folder_lower)
    
    # Системные папки которые пропускаем
    skip_folders = {'windows', 'program files', 'program files (x86)', 
                    'users', '$recycle.bin', 'system volume information',
                    'recovery', 'perflogs', 'config.msi'}
    
    def search_recursive(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for item in path.iterdir():
                if not item.is_dir():
                    continue
                
                name_lower = item.name.lower()
                
                # Пропускаем системные и скрытые
                if name_lower in skip_folders or name_lower.startswith(('.', '$')):
                    continue
                
                # Проверяем совпадение
                if (folder_lower in name_lower or 
                    folder_translit in name_lower or
                    name_lower.startswith(folder_lower) or
                    name_lower.startswith(folder_translit)):
                    results.append(item)
                
                # Рекурсивно ищем глубже
                if depth < max_depth:
                    search_recursive(item, depth + 1)
                    
        except (PermissionError, OSError):
            pass
    
    search_recursive(drive_path, 1)
    return results


def _find_and_open_folder(query: str) -> str:
    try:
        # Парсим запрос: извлекаем имя папки и диск
        folder_name, drive_letter = _parse_folder_query(query)
        
        print(f"[FOLDER] Поиск папки: {folder_name}" + (f" на диске {drive_letter}" if drive_letter else ""))
        
        # Если указан конкретный диск - сначала ищем напрямую на нём
        if drive_letter:
            print(f"[FOLDER] Прямой поиск на диске {drive_letter}:")
            direct_results = _search_drive_for_folder(drive_letter, folder_name, max_depth=3)
            if direct_results:
                best_match = _fuzzy_match_filename(folder_name, direct_results, drive_filter=drive_letter)
                if best_match:
                    if _safe_startfile(best_match):
                        return f"Открываю папку '{best_match.name}'."
                    return f"Не удалось открыть папку '{best_match.name}'. Проверьте путь."
        
        # Используем Windows Search для поиска папок
        if HAS_FILE_INDEXER:
            try:
                results = search_windows_index_folders(folder_name, max_results=30)
                if results:
                    candidates = [Path(r["path"]) for r in results if r.get("path")]
                    best_match = _fuzzy_match_filename(folder_name, candidates, drive_filter=drive_letter)
                    
                    if best_match:
                        if _safe_startfile(best_match):
                            return f"Открываю папку '{best_match.name}'."
                        return f"Не удалось открыть папку '{best_match.name}'. Проверьте путь."
            except Exception as e:
                print(f"[FOLDER] Windows Search ошибка: {e}")
        
        # Fallback: быстрый поиск в стандартных папках
        quick_results = []
        
        # Если указан диск - ищем только на нём
        search_dirs = SEARCH_LOCATIONS
        if drive_letter:
            search_dirs = [Path(f"{drive_letter}:/")]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            try:
                # Если это корень диска, ищем папки на 1-2 уровнях
                is_root = len(search_dir.parts) == 1
                
                # Поиск на первом уровне
                for item in search_dir.iterdir():
                    if item.is_dir():
                        # Пропускаем системные папки
                        if item.name.startswith(('.', '$')) or item.name.lower() in ['windows', 'program files', 'program files (x86)', 'users', '$recycle.bin']:
                            continue
                        quick_results.append(item)
                
                # Проверка второго уровня
                if (search_dir.name in ["Documents", "Документы"] or is_root):
                    for item in search_dir.iterdir():
                        if item.is_dir():
                            if item.name.startswith(('.', '$')) or item.name.lower() in ['windows', 'program files', 'program files (x86)', 'users', '$recycle.bin']:
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
        best_match = _fuzzy_match_filename(folder_name, quick_results, drive_filter=drive_letter)
        
        if best_match:
            if _safe_startfile(best_match):
                return f"Открываю папку '{best_match.name}'."
            return f"Не удалось открыть папку '{best_match.name}'. Проверьте путь."
        
        return f"Папка '{folder_name}' не найдена."
    
    except Exception as e:
        print(f"[FOLDER] Ошибка: {e}")
        return f"Ошибка при поиске папки: {e}"
