from .app_control import (
    execute_predefined_command,
    execute_app_command,
    execute_browser_command,
    execute_rebuild_index_command,
    execute_coin_flip_command,
)

from .system_control import (
    execute_taskmanager_command,
    execute_volume_command,
    execute_brightness_command,
    execute_screenshot_command,
    execute_ip_command,
    execute_internet_speed_command,
    execute_start_menu_command,
    execute_explorer_command,
)

from .window_manager import (
    execute_window_command,
)

from .file_operations import (
    execute_file_command,
    execute_folder_command,
    find_file,  # Публичная функция для поиска файлов
)

from .web_commands import (
    execute_open_site_command,
    execute_open_sources_command,
    execute_ambiguous_clean_command,
    set_last_search_urls_ref,
)

from .time_commands import (
    execute_time_command,
    execute_date_command,
    execute_reminder_command,
    execute_list_reminders_command,
    set_speak_callback,
    stop_timer_ring,
    is_timer_ringing,
    set_shutdown_event as set_reminder_shutdown_event,
)

from .scheduled_apps import (
    execute_scheduled_app_command,
    start_app_scheduler,
    set_speak_callback as set_scheduled_speak_callback,
    set_open_app_callback,
    set_close_app_callback,
    set_shutdown_event as set_app_scheduler_shutdown_event,
)

from .power_manager import (
    execute_power_command,
)

from .recyclebin_commands import (
    execute_recyclebin_command,
)

from .user_commands import (
    execute_user_name_command,
)

# set_last_search_urls_ref экспортируется из web_commands
# set_speak_callback экспортируется из time_commands

# Список всех обработчиков команд в порядке приоритета
HANDLERS = (
    # Управление окнами
    execute_window_command,
    
    # Файловые операции
    execute_file_command,
    execute_folder_command,
    
    # Веб-команды
    execute_open_sources_command,
    execute_open_site_command,
    execute_ambiguous_clean_command,
    
    # Корзина
    execute_recyclebin_command,
    
    # Питание (ПЕРЕД приложениями, чтобы "выключи компьютер" не путалось с закрытием приложений)
    execute_power_command,
    
    # Запланированный запуск (ПЕРЕД обычным запуском, чтобы "запусти в 2:05" не запускало сразу)
    execute_scheduled_app_command,
    
    # Приложения
    execute_predefined_command,
    execute_browser_command,
    execute_rebuild_index_command,
    execute_app_command,
    
    # Система
    execute_start_menu_command,
    execute_explorer_command,
    execute_taskmanager_command,
    execute_volume_command,
    execute_brightness_command,
    execute_screenshot_command,
    execute_ip_command,
    execute_internet_speed_command,
    
    # Время
    execute_time_command,
    execute_date_command,
    execute_reminder_command,
    execute_list_reminders_command,
    
    # Прочее
    execute_coin_flip_command,
)

__all__ = [
    'HANDLERS',
    'set_last_search_urls_ref',
    'set_speak_callback',
    'stop_timer_ring',
    'is_timer_ringing',
    'execute_user_name_command',
    'start_app_scheduler',
    'set_scheduled_speak_callback',
    'set_open_app_callback',
    'set_reminder_shutdown_event',
    'set_app_scheduler_shutdown_event',
]

