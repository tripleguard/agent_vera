#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vera Voice Assistant - Entry Point
Точка входа для PyInstaller и прямого запуска.
"""

import sys
import os
import json
import ctypes

# Устанавливаем корректный путь для PyInstaller bundle
if getattr(sys, 'frozen', False):
    # Запуск из PyInstaller bundle
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
    # Добавляем BASE_DIR в путь поиска модулей
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    # Устанавливаем рабочую директорию
    os.chdir(EXE_DIR)
else:
    # Обычный запуск из исходников
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)


def init_data_folder():
    """Создаёт папку data и необходимые файлы при первом запуске."""
    data_dir = os.path.join(EXE_DIR, 'data')
    
    # Создаём папку data если не существует
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"[INIT] Создана папка data: {data_dir}")
    
    # Файлы с начальным содержимым
    default_files = {
        'history.json': {'history': [], 'total_interactions': 0, 'last_updated': 0},
        'user_profile.json': {},
        'tasks.json': {'tasks': []},
        'reminders.json': [],
    }
    
    for filename, default_content in default_files.items():
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default_content, f, ensure_ascii=False, indent=2)
            print(f"[INIT] Создан файл: {filename}")


def create_desktop_shortcut():
    """Создает ярлык на рабочем столе, если его нет."""
    try:
        import win32com.client
        from pathlib import Path
        
        # Используем WScript.Shell для получения правильного пути к рабочему столу
        # Это работает корректно даже если рабочий стол в OneDrive или перенесен
        shell = win32com.client.Dispatch("WScript.Shell")
        desktop = Path(shell.SpecialFolders("Desktop"))
        shortcut_path = desktop / "Vera.lnk"
        
        # Если ярлык уже есть - выходим
        if shortcut_path.exists():
            return

        target = os.path.join(EXE_DIR, "Vera.exe")
        # Если запускаем не из exe (разработка), то ярлык не нужен или указываем на python
        if not getattr(sys, 'frozen', False):
            return

        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = target
        shortcut.WorkingDirectory = EXE_DIR
        shortcut.IconLocation = target
        shortcut.Description = "Vera"
        shortcut.Save()
        print(f"[INIT] Создан ярлык на рабочем столе: {shortcut_path}")
    except Exception as e:
        print(f"[INIT] Не удалось создать ярлык: {e}")


def set_console_title(title: str):
    """Устанавливает заголовок окна консоли."""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def _console_handler(ctrl_type):
    """Обработчик событий консоли. Игнорирует закрытие окна."""
    # CTRL_CLOSE_EVENT = 2
    if ctrl_type == 2:
        # Скрываем консоль вместо закрытия
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        return True  # Предотвращаем завершение
    return False


def setup_console_handler():
    """Устанавливает обработчик для перехвата закрытия консоли."""
    try:
        # Тип обработчика: BOOL WINAPI HandlerRoutine(DWORD dwCtrlType)
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
        handler = handler_type(_console_handler)
        # Сохраняем ссылку чтобы GC не удалил
        setup_console_handler._handler = handler
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    except Exception:
        pass

def activate_existing_window(title: str):
    """Находит и активирует окно с заданным заголовком."""
    try:
        import win32gui
        import win32con
        
        def callback(hwnd, target_title):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text == target_title:
                    # Восстанавливаем если свернуто
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    # Выводим на передний план
                    win32gui.SetForegroundWindow(hwnd)
                    return False # Stop enumeration
            return True

        win32gui.EnumWindows(callback, title)
    except Exception as e:
        print(f"[INIT] Ошибка активации окна: {e}")

if __name__ == "__main__":
    # Проверка на единственный экземпляр (только для Windows)
    try:
        import win32event
        import win32api
        import winerror
        
        # Создаем именованный мьютекс
        mutex_name = "Global\\VeraVoiceAssistant_Mutex"
        mutex = win32event.CreateMutex(None, False, mutex_name)
        last_error = win32api.GetLastError()
        
        if last_error == winerror.ERROR_ALREADY_EXISTS:
            print("[INIT] Приложение уже запущено. Активация существующего окна...")
            activate_existing_window("Vera Voice Assistant")
            sys.exit(0)
    except Exception as e:
        print(f"[INIT] Ошибка проверки экземпляра: {e}")
        # Продолжаем запуск если проверка не удалась

    # Устанавливаем заголовок окна для поиска
    set_console_title("Vera Voice Assistant")
    
    # Устанавливаем обработчик закрытия консоли
    setup_console_handler()

    # Инициализируем папку data при первом запуске
    init_data_folder()
    
    # Создаем ярлык при первом запуске (только для exe)
    create_desktop_shortcut()
    
    # Запускаем иконку в трее и главный цикл агента
    from main.tray import start_tray
    from main import agent
    start_tray(shutdown_callback=agent._safe_shutdown)
    agent.run_main_loop()
