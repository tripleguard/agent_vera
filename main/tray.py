# -*- coding: utf-8 -*-
"""Минимальный модуль для работы в системном трее Windows."""

import threading
import ctypes
import sys
import os

_icon = None
_shutdown_callback = None

def _get_console_window():
    """Получает хэндл окна консоли."""
    return ctypes.windll.kernel32.GetConsoleWindow()

def hide_console():
    """Скрывает окно консоли."""
    hwnd = _get_console_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE

def show_console():
    """Показывает окно консоли."""
    hwnd = _get_console_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.SetForegroundWindow(hwnd)

def _on_show(icon, item):
    """Обработчик пункта меню 'Показать'."""
    show_console()

def _on_exit(icon, item):
    """Обработчик пункта меню 'Выход'."""
    global _icon
    if _shutdown_callback:
        _shutdown_callback()
    if _icon:
        _icon.stop()

def start_tray(shutdown_callback=None):
    """Запускает иконку в трее в отдельном потоке."""
    global _icon, _shutdown_callback
    _shutdown_callback = shutdown_callback
    
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return False
    
    # Определяем путь к иконке
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    icon_path = os.path.join(exe_dir, "vera.ico")
    
    try:
        image = Image.open(icon_path)
    except Exception:
        # Создаём простую иконку если файл не найден
        image = Image.new('RGB', (64, 64), color=(0, 150, 200))
    
    menu = pystray.Menu(
        pystray.MenuItem("Показать", _on_show, default=True),
        pystray.MenuItem("Выход", _on_exit)
    )
    
    _icon = pystray.Icon("Vera", image, "Vera Voice Assistant", menu)
    
    # Запускаем в отдельном потоке
    tray_thread = threading.Thread(target=_icon.run, daemon=False)
    tray_thread.start()
    return True

def stop_tray():
    """Останавливает иконку в трее."""
    global _icon
    if _icon:
        _icon.stop()
        _icon = None
