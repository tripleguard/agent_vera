import re
import time
import datetime
import threading
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, asdict
from user.json_storage import load_json, save_json
from main.lang_ru import replace_number_words
from main.config_manager import get_data_dir

# Формат времени для хранения
_TIME_FORMAT = "%Y-%m-%d-%H-%M"

# Путь к файлу запланированных запусков
_SCHEDULED_APPS_FILE = get_data_dir() / "scheduled_apps.json"


@dataclass
class ScheduledApp:
    app_name: str           # Название приложения (для поиска в индексе)
    time: str               # Время запуска "HH:MM"
    recurring: str          # "once", "daily", "weekdays", "weekends"
    created_at: str         # Дата создания в формате YYYY-MM-DD-HH-MM
    last_run: Optional[str] = None  # Дата последнего запуска
    enabled: bool = True    # Активна ли задача
    target_date: Optional[str] = None  # Для одноразовых: дата "YYYY-MM-DD"
    action: str = "open"    # "open" или "close"


_scheduled_apps: list[ScheduledApp] = []
_scheduler_started = False
_SPEAK_CB: Optional[Callable] = None
_OPEN_APP_CB: Optional[Callable] = None
_CLOSE_APP_CB: Optional[Callable] = None
_shutdown_event: Optional[threading.Event] = None


def set_shutdown_event(event: threading.Event) -> None:
    global _shutdown_event
    _shutdown_event = event


def set_speak_callback(cb: Callable) -> None:
    global _SPEAK_CB
    _SPEAK_CB = cb


def set_open_app_callback(cb: Callable) -> None:
    global _OPEN_APP_CB
    _OPEN_APP_CB = cb


def set_close_app_callback(cb: Callable) -> None:
    global _CLOSE_APP_CB
    _CLOSE_APP_CB = cb


def _now_str() -> str:
    return datetime.datetime.now().strftime(_TIME_FORMAT)


def _today_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _save_scheduled_apps() -> None:
    data = [asdict(s) for s in _scheduled_apps]
    save_json(_SCHEDULED_APPS_FILE, data, "SCHEDULED_APPS")


def _load_scheduled_apps() -> None:
    global _scheduled_apps
    data = load_json(_SCHEDULED_APPS_FILE, [])
    if not data:
        return
    
    loaded = []
    for item in data:
        try:
            loaded.append(ScheduledApp(
                app_name=item["app_name"],
                time=item["time"],
                recurring=item.get("recurring", "once"),
                created_at=item.get("created_at", _now_str()),
                last_run=item.get("last_run"),
                enabled=item.get("enabled", True),
                target_date=item.get("target_date"),
                action=item.get("action", "open")
            ))
        except Exception as e:
            print(f"[SCHEDULED_APPS] Ошибка загрузки: {e}")
    
    _scheduled_apps = loaded
    print(f"[SCHEDULED_APPS] Загружено {len(_scheduled_apps)} запланированных запусков")


def _should_run_today(task: ScheduledApp) -> bool:
    """Проверяет, должна ли задача запуститься сегодня."""
    if not task.enabled:
        return False
    
    today = datetime.datetime.now()
    weekday = today.weekday()  # 0=пн, 6=вс
    today_str = today.strftime("%Y-%m-%d")
    
    if task.recurring == "once":
        # Одноразовая — если ещё не запускалась
        if task.last_run is not None:
            return False
        # Если указана конкретная дата — проверяем
        if task.target_date:
            return task.target_date == today_str
        return True
    elif task.recurring == "daily":
        return True
    elif task.recurring == "weekdays":
        return weekday < 5  # Пн-Пт
    elif task.recurring == "weekends":
        return weekday >= 5  # Сб-Вс
    
    return False


def _was_run_today(task: ScheduledApp) -> bool:
    """Проверяет, запускалась ли задача сегодня."""
    if not task.last_run:
        return False
    try:
        last = datetime.datetime.strptime(task.last_run, _TIME_FORMAT)
        return last.date() == datetime.datetime.now().date()
    except Exception:
        return False


def _scheduler():
    """Фоновый планировщик запуска приложений."""
    while not (_shutdown_event and _shutdown_event.is_set()):
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        
        for task in _scheduled_apps:
            if not task.enabled:
                continue
            
            # Проверяем время (с точностью до минуты)
            if task.time != current_time:
                continue
            
            # Проверяем, не запускалась ли уже сегодня
            if _was_run_today(task):
                continue
            
            # Проверяем, должна ли запуститься сегодня
            if not _should_run_today(task):
                continue
            
            # Выполняем действие (открытие или закрытие)
            action_name = "Закрытие" if task.action == "close" else "Запуск"
            print(f"[SCHEDULED_APPS] {action_name}: {task.app_name}")
            
            try:
                if task.action == "close" and _CLOSE_APP_CB:
                    result = _CLOSE_APP_CB(task.app_name)
                    if _SPEAK_CB and result:
                        _SPEAK_CB(f"Запланированное закрытие: {task.app_name}")
                elif task.action == "open" and _OPEN_APP_CB:
                    result = _OPEN_APP_CB(task.app_name)
                    if _SPEAK_CB and result:
                        _SPEAK_CB(f"Запланированный запуск: {task.app_name}")
            except Exception as e:
                print(f"[SCHEDULED_APPS] Ошибка {action_name.lower()} {task.app_name}: {e}")
            
            # Обновляем last_run
            task.last_run = _now_str()
            
            # Если одноразовая — отключаем
            if task.recurring == "once":
                task.enabled = False
            
            _save_scheduled_apps()
        
        # Используем wait вместо sleep для быстрого реагирования на shutdown
        sleep_time = 60 - now.second
        if _shutdown_event:
            _shutdown_event.wait(timeout=sleep_time)
        else:
            time.sleep(sleep_time)


def start_app_scheduler() -> None:
    """Запускает планировщик приложений."""
    global _scheduler_started
    if not _scheduler_started:
        _load_scheduled_apps()
        threading.Thread(target=_scheduler, daemon=True).start()
        _scheduler_started = True


def add_scheduled_app(app_name: str, time_str: str, recurring: str = "daily", target_date: Optional[str] = None, action: str = "open") -> ScheduledApp:
    """Добавляет запланированный запуск/закрытие."""
    task = ScheduledApp(
        app_name=app_name,
        time=time_str,
        recurring=recurring,
        created_at=_now_str(),
        target_date=target_date,
        action=action
    )
    _scheduled_apps.append(task)
    _save_scheduled_apps()
    return task


def remove_scheduled_app(app_name: str, exact_match: bool = False) -> tuple[bool, int]:
    removed_count = 0
    for task in _scheduled_apps[:]:
        if exact_match:
            match = task.app_name.lower() == app_name.lower()
        else:
            match = app_name.lower() in task.app_name.lower()
        
        if match:
            _scheduled_apps.remove(task)
            removed_count += 1
    
    if removed_count > 0:
        _save_scheduled_apps()
    return (removed_count > 0, removed_count)


def get_scheduled_apps() -> list[ScheduledApp]:
    """Возвращает список запланированных запусков."""
    return _scheduled_apps.copy()


_RECURRING_MAP = {
    "каждый день": "daily",
    "ежедневно": "daily",
    "каждое утро": "daily",
    "каждый вечер": "daily",
    "постоянно": "daily",
    "всегда": "daily",
    "регулярно": "daily",
    "систематически": "daily",
    "по будням": "weekdays",
    "по рабочим": "weekdays",
    "в будни": "weekdays",
    "в рабочие дни": "weekdays",
    "в рабочее время": "weekdays",
    "когда работаю": "weekdays",
    "по выходным": "weekends",
    "в выходные": "weekends",
    "на выходных": "weekends",
    "один раз": "once",
    "однократно": "once",
}

_RECURRING_NAMES = {
    "daily": "ежедневно",
    "weekdays": "по будням",
    "weekends": "по выходным",
    "once": "один раз",
}


def _parse_one_time_schedule(app_name: str, day: str, hour: int, minute: int, action: str = "open") -> str:
    """Общая логика для одноразового запуска/закрытия."""
    if hour > 23 or minute > 59:
        return "Неверное время."
    
    today = datetime.datetime.now()
    if day == "завтра":
        target = today + datetime.timedelta(days=1)
    else:
        target = today
    
    target_date = target.strftime("%Y-%m-%d")
    time_str = f"{hour:02d}:{minute:02d}"
    
    task = add_scheduled_app(app_name, time_str, "once", target_date, action=action)
    day_name = "сегодня" if day == "сегодня" else "завтра"
    action_word = "закрытие" if action == "close" else "запуск"
    return f"Запланировано {action_word}: {task.app_name} {day_name} в {time_str}."


def _parse_smart_schedule(app_name: str, hour: int, minute: int, action: str = "open") -> str:
    """Умное определение даты: если время прошло сегодня - планируем на завтра."""
    if hour > 23 or minute > 59:
        return "Неверное время."
    
    now = datetime.datetime.now()
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Если указанное время уже прошло сегодня - планируем на завтра
    if target_time <= now:
        target = now + datetime.timedelta(days=1)
        day_name = "завтра"
    else:
        target = now
        day_name = "сегодня"
    
    target_date = target.strftime("%Y-%m-%d")
    time_str = f"{hour:02d}:{minute:02d}"
    
    task = add_scheduled_app(app_name, time_str, "once", target_date, action=action)
    action_word = "закрытие" if action == "close" else "запуск"
    return f"Запланировано {action_word}: {task.app_name} {day_name} в {time_str}."


def execute_scheduled_app_command(text: str) -> Optional[str]:
    """Обрабатывает команды запланированного запуска приложений."""
    lowered = text.lower().strip()
    cleaned = replace_number_words(lowered)
    
    # Список запланированных запусков
    if re.search(r"(покажи|список|какие)\s+(запланированн|автозапуск|расписани)", cleaned):
        if not _scheduled_apps:
            return "Нет запланированных запусков приложений."
        
        lines = [f"Запланированных запусков: {len(_scheduled_apps)}"]
        for i, task in enumerate(_scheduled_apps, 1):
            status = "✓" if task.enabled else "✗"
            rec = _RECURRING_NAMES.get(task.recurring, task.recurring)
            lines.append(f"{i}. {status} {task.app_name} в {task.time} ({rec})")
        return "\n".join(lines)
    
    # Удаление запланированного запуска
    if m := re.search(r"(удали|отмени|убери)\s+(?:запланированн\w+\s+)?(?:запуск\s+)?(\w+)", cleaned):
        app_name = m.group(2).strip()
        success, count = remove_scheduled_app(app_name)
        if success:
            if count > 1:
                return f"Удалено запланированных запусков: {count} ({app_name})."
            return f"Запланированный запуск {app_name} удалён."
        return f"Запуск {app_name} не найден в расписании."
    
    # Очистка всех запланированных запусков
    if re.search(r"(удали|очисти|убери)\s+все\s+(запланированн|автозапуск|расписани)", cleaned):
        count = len(_scheduled_apps)
        _scheduled_apps.clear()
        _save_scheduled_apps()
        return f"Удалено запланированных запусков: {count}" if count else "Расписание пусто."
    

    # Закрытие: "закрой телегу в 2 0 4" (формат H M M)
    if m := re.search(r"(?:закрой|выключи)\s+(.+?)\s+в\s+(\d{1,2})\s+(\d)\s+(\d)(?:\s|$)", cleaned):
        if "завтра" not in cleaned and "сегодня" not in cleaned:
            app_name = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3)) * 10 + int(m.group(4))
            return _parse_smart_schedule(app_name, hour, minute, action="close")
    
    # Закрытие: "закрой телегу в 22:30"
    if m := re.search(r"(?:закрой|выключи)\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})(?:\s|$)", cleaned):
        if "завтра" not in cleaned and "сегодня" not in cleaned:
            app_name = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3)) if m.group(3) else 0
            return _parse_smart_schedule(app_name, hour, minute, action="close")
    
    # Закрытие с днём: "закрой телегу сегодня/завтра в 22:00"
    if m := re.search(r"(?:закрой|выключи)\s+(.+?)\s+(сегодня|завтра)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})", cleaned):
        app_name = m.group(1).strip()
        day = m.group(2)
        hour = int(m.group(3))
        minute = int(m.group(4)) if m.group(4) else 0
        return _parse_one_time_schedule(app_name, day, hour, minute, action="close")
    
    # Одноразовый запуск: "запусти телегу сегодня в 20:30" / "запусти телегу завтра в 22:00"
    if m := re.search(r"(?:запусти|открой)\s+(.+?)\s+(сегодня|завтра)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})", cleaned):
        app_name = m.group(1).strip()
        day = m.group(2)
        hour = int(m.group(3))
        minute = int(m.group(4)) if m.group(4) else 0
        return _parse_one_time_schedule(app_name, day, hour, minute)
    
    # Обратный порядок: "сегодня в 20:30 запусти телегу"
    if m := re.search(r"(сегодня|завтра)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})\s+(?:запусти|открой)\s+(.+)", cleaned):
        day = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0
        app_name = m.group(4).strip()
        return _parse_one_time_schedule(app_name, day, hour, minute)
    
    # Время в формате "2 0 4" (час + десятки минут + единицы) - например "в два ноль четыре"
    if m := re.search(r"(?:запусти|открой)\s+(.+?)\s+в\s+(\d{1,2})\s+(\d)\s+(\d)(?:\s|$)", cleaned):
        if "завтра" not in cleaned and "сегодня" not in cleaned:
            app_name = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3)) * 10 + int(m.group(4))  # "0 4" -> 04
            if not any(keyword in cleaned for keyword in ["каждый", "ежедневно", "постоянно", "регулярно", "будням", "выходным", "всегда"]):
                return _parse_smart_schedule(app_name, hour, minute)
    
    # Умное определение даты: "запусти телегу в 22:30" (без указания дня)
    # Если время уже прошло сегодня - планируется на завтра
    if m := re.search(r"(?:запусти|открой)\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})(?:\s|$)", cleaned):
        # Проверяем, что это не совпадение с другими паттернами
        if "завтра" not in cleaned and "сегодня" not in cleaned:
            app_name = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3)) if m.group(3) else 0
            
            # Проверяем, что это не периодический запуск
            if not any(keyword in cleaned for keyword in ["каждый", "ежедневно", "постоянно", "регулярно", "будням", "выходным", "всегда"]):
                return _parse_smart_schedule(app_name, hour, minute)
    
    patterns = [
        # запускай хром каждый день в 9:00
        r"запуска[йи]\s+(.+?)\s+(каждый день|ежедневно|постоянно|всегда|регулярно|систематически|по будням|по рабочим|в будни|в рабочие дни|в рабочее время|когда работаю|по выходным|в выходные|на выходных)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # запускай хром в 9:00 каждый день
        r"запуска[йи]\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})\s+(каждый день|ежедневно|постоянно|всегда|регулярно|по будням|по выходным|в выходные)",
        # каждый день запускай хром в 9:00
        r"(каждый день|ежедневно|постоянно|регулярно|по будням|по выходным|в выходные)\s+запуска[йи]\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # поставь/назначь запуск хром на 9:00
        r"(?:постав[ьи]|назнач[ьи])\s+(?:авто)?запуск\s+(.+?)\s+(?:на|в)\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # включи/настрой автозапуск хром в 9:00
        r"(?:включи|настрой)\s+(?:авто)?запуск\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # пусть хром запускается каждый день в 9:00
        r"пусть\s+(.+?)\s+запуска[её]тся\s+(каждый день|ежедневно|постоянно|регулярно|по будням|по выходным)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # автоматически запускай хром в 9:00
        r"автоматически\s+запуска[йи]\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # организуй/спланируй запуск хром на 9:00
        r"(?:организуй|спланируй)\s+запуск\s+(.+?)\s+(?:на|в)\s+(\d{1,2})[:.\s]?(\d{0,2})",
        # сделай автостарт хром в 9:00
        r"(?:делай|сделай)\s+автостарт\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})",
    ]
    
    for i, pat in enumerate(patterns):
        if m := re.search(pat, cleaned):
            groups = m.groups()
            
            # Определяем позиции параметров для каждого паттерна
            if i == 0:  # запускай <app> <recurring> в <time>
                app_name, recurring_text, hour, minute = groups
            elif i == 1:  # запускай <app> в <time> <recurring>
                app_name, hour, minute, recurring_text = groups
            elif i == 2:  # <recurring> запускай <app> в <time>
                recurring_text, app_name, hour, minute = groups
            elif i in [3, 4, 7, 8]:  # поставь/включи/организуй/сделай <app> на/в <time> (без recurring)
                app_name, hour, minute = groups[0], groups[1], groups[2] if len(groups) > 2 else "0"
                recurring_text = None
            elif i == 5:  # пусть <app> запускается <recurring> в <time>
                app_name, recurring_text, hour, minute = groups
            elif i == 6:  # автоматически запускай <app> в <time>
                app_name, hour, minute = groups
                recurring_text = None
            else:
                continue
            
            hour = int(hour)
            minute = int(minute) if minute else 0
            
            if hour > 23 or minute > 59:
                return "Неверное время."
            
            time_str = f"{hour:02d}:{minute:02d}"
            recurring = _RECURRING_MAP.get(recurring_text.strip(), "daily") if recurring_text else "daily"
            
            task = add_scheduled_app(app_name.strip(), time_str, recurring)
            rec_name = _RECURRING_NAMES.get(recurring, recurring)
            return f"Запланировано: {task.app_name} в {time_str} ({rec_name})."
    
    # Простой паттерн: "запускай хром в 9 утра" (по умолчанию ежедневно)
    if m := re.search(r"запуска[йи]\s+(.+?)\s+в\s+(\d{1,2})[:.\s]?(\d{0,2})(?:\s+(утра|вечера|ночи|дня))?", cleaned):
        app_name = m.group(1).strip()
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0
        period = m.group(4) if m.group(4) else None
        
        # Корректировка для "утра/вечера"
        if period == "вечера" and hour < 12:
            hour += 12
        elif period == "ночи" and hour < 12:
            hour = hour  # 0-11 ночи
        elif period == "дня" and hour < 12:
            hour += 12
        
        if hour > 23 or minute > 59:
            return "Неверное время."
        
        time_str = f"{hour:02d}:{minute:02d}"
        task = add_scheduled_app(app_name, time_str, "daily")
        return f"Запланировано: {task.app_name} в {time_str} (ежедневно)."
    
    return None
