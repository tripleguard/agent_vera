import re
import sys
import os
import time
import datetime
import threading
import winsound
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, asdict
from main.lang_ru import TIME_UNITS, replace_number_words
from user.json_storage import load_json, save_json


def _get_reminders_path() -> Path:
    """Возвращает путь к reminders.json - рядом с exe в frozen bundle."""
    if getattr(sys, 'frozen', False):
        return Path(os.path.dirname(sys.executable)) / "data" / "reminders.json"
    else:
        return Path(__file__).resolve().parent.parent.parent / "data" / "reminders.json"


# Путь к файлу напоминаний
_REMINDERS_FILE = _get_reminders_path()

# Импорт модуля уведомлений
try:
    from user.notifications import show_reminder_notification
    _NOTIFICATIONS_ENABLED = True
except ImportError:
    _NOTIFICATIONS_ENABLED = False


@dataclass
class _Reminder:
    ts: float
    message: str
    is_timer: bool = False  # True для таймеров, False для напоминаний


_scheduled: list[_Reminder] = []
_scheduler_started = False
_SPEAK_CB: Optional[Callable] = None
_timer_ringing = False


def set_speak_callback(cb: Callable) -> None:
    global _SPEAK_CB
    _SPEAK_CB = cb


def stop_timer_ring() -> bool:
    """Останавливает звонок таймера."""
    global _timer_ringing
    was_ringing = _timer_ringing
    _timer_ringing = False
    return was_ringing


def is_timer_ringing() -> bool:
    return _timer_ringing


def _start_timer_ring():
    """Запускает звонок таймера в отдельном потоке."""
    global _timer_ringing
    _timer_ringing = True
    def ring():
        while _timer_ringing:
            try:
                winsound.Beep(1000, 500)
                time.sleep(0.3)
            except Exception:
                time.sleep(0.5)
    threading.Thread(target=ring, daemon=True).start()


def _save_reminders() -> None:
    """Сохраняет напоминания в JSON файл."""
    data = [asdict(r) for r in _scheduled]
    save_json(_REMINDERS_FILE, data, "REMINDER")


def _load_reminders() -> None:
    """Загружает напоминания из JSON файла."""
    global _scheduled
    data = load_json(_REMINDERS_FILE, [])
    if not data:
        return
    now = time.time()
    # Загружаем только будущие напоминания (с поддержкой is_timer)
    _scheduled = [
        _Reminder(ts=r["ts"], message=r["message"], is_timer=r.get("is_timer", False))
        for r in data if r["ts"] > now
    ]
    # Сохраняем обновлённый список (без просроченных)
    if len(_scheduled) != len(data):
        _save_reminders()
    print(f"[REMINDER] Загружено {len(_scheduled)} напоминаний")


def _scheduler():
    """Фоновый планировщик напоминаний и таймеров."""
    while True:
        now = time.time()
        for task in _scheduled[:]:
            if now >= task.ts:
                print(f"[{'ТАЙМЕР' if task.is_timer else 'REMINDER'}] {task.message}")
                
                if task.is_timer:
                    # Таймер: сразу звонок, потом голос
                    _start_timer_ring()
                    if _SPEAK_CB:
                        _SPEAK_CB(task.message + ". Скажите стоп чтобы отключить.")
                else:
                    # Напоминание: голос + toast
                    if _SPEAK_CB:
                        _SPEAK_CB(task.message)
                    if _NOTIFICATIONS_ENABLED:
                        try:
                            show_reminder_notification("⏰ Напоминание", task.message)
                        except Exception:
                            pass
                
                _scheduled.remove(task)
                _save_reminders()
        time.sleep(1)


def start_scheduler() -> None:
    """Запускает планировщик напоминаний."""
    global _scheduler_started
    if not _scheduler_started:
        _load_reminders()
        threading.Thread(target=_scheduler, daemon=True).start()
        _scheduler_started = True


def execute_time_command(text: str) -> Optional[str]:
    """Сообщает текущее время."""
    lowered = text.lower().strip()

    time_patterns = [
        r"\bсколько\s+времени\s*[?.!]?\s*$",  # "сколько времени" в конце
        r"^\s*сколько\s+времени\s*[?.!]?\s*$",  # только "сколько времени"
        r"\bкакое\s+время\b",
        r"\bкоторый\s+час\b",
    ]
    
    if any(re.search(p, lowered) for p in time_patterns) or lowered == "время":
        return f"Сейчас {datetime.datetime.now().strftime('%H:%M')}."
    return None


def execute_date_command(text: str) -> Optional[str]:
    """Сообщает текущую дату."""
    lowered = text.lower().strip()
    
    # Паттерны для запросов о дате
    patterns = [
        r"\bкакой\s+(?:сейчас\s+)?день\b",
        r"\bкакая\s+(?:сейчас\s+)?дата\b",
        r"\bкакое\s+(?:сейчас\s+)?число\b",
        r"\bсколько\s+(?:сейчас\s+)?число\b",
        r"\bкакой\s+(?:сегодня\s+)?день\b",
        r"\bкакая\s+(?:сегодня\s+)?дата\b",
        r"\bкакое\s+(?:сегодня\s+)?число\b",
    ]
    
    if any(re.search(p, lowered) for p in patterns):
        now = datetime.datetime.now()
        
        # Названия дней недели на русском
        weekdays = [
            "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"
        ]
        
        # Названия месяцев на русском (в родительном падеже)
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря"
        ]
        
        weekday = weekdays[now.weekday()]
        day = now.day
        month = months[now.month - 1]
        year = now.year
        
        return f"Сегодня {weekday}, {day} {month} {year} года."
    
    return None


def execute_reminder_command(text: str) -> Optional[str]:
    """Обрабатывает команды напоминаний и таймеров."""
    lowered = text.lower()
    cleaned = replace_number_words(lowered)
    
    # Удаление всех напоминаний
    if re.search(r"(удали|отмени|очисти)\s+все\s+напоминани", cleaned):
        count = len(_scheduled)
        _scheduled.clear()
        _save_reminders()
        return f"Удалено напоминаний: {count}" if count else "Напоминаний не было."
    
    # Удаление напоминания
    if m := re.search(r"(удали|отмени)\s+напоминани[ея]\s+на\s+(\d{1,2})[:.\s](\d{1,2})", cleaned):
        hour = max(0, min(int(m.group(2)), 23))
        minute = max(0, min(int(m.group(3)), 59))
        target_str = f"{hour:02d}:{minute:02d}"
        
        removed = 0
        for task in list(_scheduled):
            try:
                if datetime.datetime.fromtimestamp(task.ts).strftime("%H:%M") == target_str:
                    _scheduled.remove(task)
                    removed += 1
            except Exception:
                pass
        
        if removed:
            _save_reminders()
        return f"Удалено напоминание на {target_str}" if removed else \
               f"Напоминаний на {target_str} не найдено."
    
    # Удаление всех таймеров
    if re.search(r"(удали|отмени|очисти|\u0441брось?)\s+все\s+таймер", cleaned):
        timers = [t for t in _scheduled if t.is_timer]
        for t in timers:
            _scheduled.remove(t)
        _save_reminders()
        return f"Удалено таймеров: {len(timers)}" if timers else "Таймеров не было."
    
    # Удаление таймера по времени: "удали таймер на 5 минут"
    if m := re.search(r"(удали|отмени|сбрось?)\s+таймер(?:\s+на)?\s+(\d+)\s+([\u0430-\u044f]+)", cleaned):
        n, unit = int(m.group(2)), m.group(3)
        if unit in TIME_UNITS:
            # Ищем таймер с таким сообщением
            target_msg = f"Таймер {n} {unit} завершён."
            for task in list(_scheduled):
                if task.is_timer and task.message == target_msg:
                    _scheduled.remove(task)
                    _save_reminders()
                    return f"Таймер на {n} {unit} удалён."
            return f"Таймер на {n} {unit} не найден."
    
    # Удаление таймера без указания времени: "удали таймер", "отмени таймер"
    if re.search(r"(удали|отмени|сбрось?)\s+таймер\b", cleaned):
        timers = [t for t in _scheduled if t.is_timer]
        if not timers:
            return "Активных таймеров нет."
        # Удаляем последний добавленный таймер
        last_timer = timers[-1]
        _scheduled.remove(last_timer)
        _save_reminders()
        return f"Таймер удалён."
    
    # Таймер: "таймер на 5 минут", "включи таймер на 10 минут", "поставь таймер на 15 минут"
    if m := re.search(r"(?:включи|поставь|установи|запусти)?\s*таймер\s+(?:на\s+)?(\d+)\s+([\u0430-\u044f]+)", cleaned):
        n, unit = int(m.group(1)), m.group(2)
        if unit in TIME_UNITS:
            sec = n * TIME_UNITS[unit]
            _scheduled.append(_Reminder(time.time() + sec, f"Таймер {n} {unit} завершён.", is_timer=True))
            _save_reminders()
            return f"Таймер на {n} {unit} установлен."
    
    # Таймер без числа (по умолчанию 1): "таймер минуту"
    if m := re.search(r"(?:включи|поставь|установи|запусти)?\s*таймер\s+(?:на\s+)?([\u0430-\u044f]+)(?:\s|$)", cleaned):
        unit = m.group(1)
        if unit in TIME_UNITS:
            sec = TIME_UNITS[unit]
            _scheduled.append(_Reminder(time.time() + sec, f"Таймер 1 {unit} завершён.", is_timer=True))
            _save_reminders()
            return f"Таймер на 1 {unit} установлен."
    
    # "напомни позвонить маме через 5 минут"
    if m := re.search(r"(?:напомн(?:и|ить)|поставь\s+напоминани[ея])\s+(.+?)\s+через\s+(\d+)\s+([а-я]+)$", cleaned):
        message, n, unit = m.group(1).strip(), int(m.group(2)), m.group(3)
        if unit in TIME_UNITS:
            sec = n * TIME_UNITS[unit]
            target_ts = time.time() + sec
            target_time = datetime.datetime.fromtimestamp(target_ts).strftime('%H:%M')
            _scheduled.append(_Reminder(target_ts, message))
            _save_reminders()
            return f"Напоминание на {target_time} установлено."
    
    # "напомни позвонить маме через минуту"
    if m := re.search(r"(?:напомн(?:и|ить)|поставь\s+напоминани[ея])\s+(.+?)\s+через\s+([а-я]+)$", cleaned):
        message, unit = m.group(1).strip(), m.group(2)
        if unit in TIME_UNITS:
            sec = TIME_UNITS[unit]
            target_ts = time.time() + sec
            target_time = datetime.datetime.fromtimestamp(target_ts).strftime('%H:%M')
            _scheduled.append(_Reminder(target_ts, message))
            _save_reminders()
            return f"Напоминание на {target_time} установлено."
    
    # "напомни через минуту позвонить маме"
    if m := re.search(r"напомн(?:и|ить)\s+через\s+([а-я]+)\s+(.+)", cleaned):
        unit = m.group(1)
        if unit in TIME_UNITS:
            message = m.group(2).strip()
            sec = TIME_UNITS[unit]
            target_ts = time.time() + sec
            target_time = datetime.datetime.fromtimestamp(target_ts).strftime('%H:%M')
            _scheduled.append(_Reminder(target_ts, message))
            _save_reminders()
            return f"Напоминание на {target_time} установлено."
    
    # "напомни через 5 минут позвонить маме"
    if m := re.search(r"напомн(?:и|ить)\s+через\s+(\d+)\s+([а-я]+)\s+(.+)", cleaned):
        n, unit, message = int(m.group(1)), m.group(2), m.group(3).strip()
        sec = n * TIME_UNITS.get(unit, 60)
        target_ts = time.time() + sec
        target_time = datetime.datetime.fromtimestamp(target_ts).strftime('%H:%M')
        _scheduled.append(_Reminder(target_ts, message))
        _save_reminders()
        return f"Напоминание на {target_time} установлено."
    
    # Напоминание на конкретное время "напоминание на 14:30 позвонить"
    if m := re.search(r"напоминани[ея]\s+на\s+(\d{1,2})[:.\s](\d{1,2})(?:\s+(.+))?$", cleaned):
        hour = max(0, min(int(m.group(1)), 23))
        minute = max(0, min(int(m.group(2)), 59))
        message = (m.group(3) or "Напоминание").strip()
        
        now_dt = datetime.datetime.now()
        target = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_dt:
            target += datetime.timedelta(days=1)
        
        _scheduled.append(_Reminder(target.timestamp(), message))
        _save_reminders()
        return f"Напоминание на {target.strftime('%H:%M')} установлено."
    
    return None


def execute_list_reminders_command(text: str) -> Optional[str]:
    """Показывает список активных напоминаний."""
    lowered = text.lower().strip()
    
    if not re.search(r"(покажи|список|какие|все)\s+напоминани[яй]?", lowered):
        return None
    
    if not _scheduled:
        return "Активных напоминаний нет."
    
    # Сортируем по времени
    sorted_tasks = sorted(_scheduled, key=lambda r: r.ts)
    
    lines = [f"Активных напоминаний: {len(sorted_tasks)}"]
    for i, task in enumerate(sorted_tasks, 1):
        dt = datetime.datetime.fromtimestamp(task.ts)
        time_str = dt.strftime('%H:%M')
        # Если не сегодня, добавляем дату
        if dt.date() != datetime.datetime.now().date():
            time_str = dt.strftime('%d.%m %H:%M')
        lines.append(f"{i}. {time_str} — {task.message}")
    
    return "\n".join(lines)
