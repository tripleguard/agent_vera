import re
import ctypes
from typing import Optional

try:
    import win32com.client
    import win32gui
    import win32con
    _RECYCLE_SUPPORT = True
except Exception:
    win32com = win32gui = win32con = None  # type: ignore
    _RECYCLE_SUPPORT = False


def _recyclebin_count_and_names(limit: int = 5) -> Optional[tuple[int, list[str]]]:
    """Получает количество и имена файлов в корзине."""
    if not _RECYCLE_SUPPORT:
        return None
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        bin_ns = shell.NameSpace(10)
        if not bin_ns:
            return None
        items = bin_ns.Items()
        count = int(items.Count)
        names = [str(items.Item(i).Name) for i in range(min(limit, count)) 
                 if hasattr(items.Item(i), "Name")]
        return count, names
    except Exception as e:
        print(f"[RECYCLE] enumerate error: {e}")
        return None


def _recyclebin_open() -> bool:
    """Открывает корзину в проводнике."""
    try:
        import os
        os.startfile("shell:RecycleBinFolder")
        return True
    except Exception:
        return False


def _recyclebin_close() -> bool:
    """Закрывает окно корзины."""
    if not _RECYCLE_SUPPORT:
        return False
    
    closed = False
    
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        for w in list(shell.Windows()):
            try:
                name = (getattr(w, "LocationName", None) or "").lower()
                url = (getattr(w, "LocationURL", None) or "").lower()
                if ("корзина" in name) or ("recyclebin" in url) or ("645ff040" in url):
                    w.Quit()
                    closed = True
            except Exception:
                pass
    except Exception:
        pass
    
    try:
        def _find_recycle(hwnd, _):
            nonlocal closed
            try:
                if win32gui.IsWindowVisible(hwnd):
                    cls = win32gui.GetClassName(hwnd)
                    if cls in ("CabinetWClass", "ExploreWClass"):
                        title = win32gui.GetWindowText(hwnd) or ""
                        if "корзина" in title.lower():
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            closed = True
            except Exception:
                pass
        
        win32gui.EnumWindows(_find_recycle, None)
    except Exception:
        pass
    
    return closed


def _recyclebin_empty() -> bool:
    """Очищает корзину."""
    try:
        flags = 0x00000001 | 0x00000002 | 0x00000004  # No confirm, no progress, no sound
        return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags) == 0
    except Exception as e:
        print(f"[RECYCLE] empty error: {e}")
        return False


def execute_recyclebin_command(text: str) -> Optional[str]:
    """Управление корзиной Windows."""
    t = text.lower().strip()
    if not re.search(r"\bкорзин[ауые]\b", t):
        return None
    
    # Очистка
    if re.search(r"\b(очист|почист|опустош|пуст|удал)", t):
        info = _recyclebin_count_and_names(0)
        before = info[0] if info else None
        if not _recyclebin_empty():
            return "Не удалось очистить корзину."
        if before == 0:
            return "Корзина уже была пуста."
        return f"Корзина очищена{f' ({before} объектов)' if before else ''}."
    
    # Закрытие
    if re.search(r"\b(закрой|закрыть)", t):
        return "Закрываю корзину." if _recyclebin_close() else "Не удалось закрыть корзину."
    
    # Открытие
    if re.search(r"\b(открой|покажи|открыть)\b", t):
        return "Открываю корзину." if _recyclebin_open() else "Не удалось открыть корзину."
    
    # Информация
    info = _recyclebin_count_and_names(5)
    if not info:
        return "Не удалось получить содержимое корзины."
    count, names = info
    if count == 0:
        return "Корзина пуста."
    samples = ", ".join(names) if names else ""
    return f"В корзине {count} объектов{f', например: {samples}' if samples else ''}."