import json
import os
import re
import queue
import threading
import sys
import time
from pathlib import Path
from collections import deque
import difflib
import sounddevice as sd
import vosk
import pyttsx3
from llama_cpp import Llama
from typing import Optional
import ctypes
import msvcrt
from functools import partial
from web.web_search import web_search_answer, execute_wikipedia_command
from web.weather import execute_weather_command
from web.currency import execute_currency_command
from .lang_ru import convert_years_in_text
from .multitask import execute_multitask
from .commands import HANDLERS, set_speak_callback, set_last_search_urls_ref, execute_user_name_command, stop_timer_ring, is_timer_ringing
from .commands import start_app_scheduler, set_scheduled_speak_callback, set_open_app_callback, set_close_app_callback
from .commands import set_reminder_shutdown_event, set_app_scheduler_shutdown_event
from .commands.time_commands import start_scheduler
from .commands.app_control import open_app_by_name, close_app_by_name
from user.tasks import TaskManager, execute_task_command
from user.user_profile import UserProfile, execute_profile_command
from user.history_logger import HistoryLogger, execute_history_command
from .tools import TOOLS

def _enable_windows_ansi():
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        pass

_ANSI_COLORS = {
    "reset": "\033[0m",
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}

_current_color = "reset"
_mic_muted = False
_mic_muted_lock = threading.Lock()  # Lock для thread-safe доступа к _mic_muted
_shutdown_event = threading.Event()  # Event для graceful shutdown
_shutdown_requested = False  # Флаг для корректного завершения (legacy)

def set_console_color(name: str) -> bool:
    global _current_color
    key = name.strip().lower()
    code = _ANSI_COLORS.get(key)
    if not code:
        return False
    try:
        sys.stdout.write(code)
        sys.stdout.flush()
        _current_color = key
        return True
    except Exception:
        return False

def _print_banner_and_tips(activation_word: str):
    banner = (
        "\n"
        "\033[96m __     _______ ____      _    \033[94m\n"
        "\033[96m \\ \\   / / ____|  _ \\    / \\   \033[94m\n"
        "\033[96m  \\ \\ / /|  _| | |_) |  / _ \\  \033[94m\n"
        "\033[96m   \\ V / | |___|  _ <  / ___ \\ \033[94m\n"
        "\033[96m    \\_/  |_____|_| \\_\\/_/   \\_\\\033[94m\n"
        "\033[0m\n"
        "\033[96mVoice-Enabled Responsive Agent\033[0m\n"
    )
    print(banner)
    print(f"1. Для запуска агента скажите активационное слово \"{activation_word}\".")
    print("2. /help для информации по командам")
    print("3. /color <цвет> для изменения цвета (например: /color green)")

def _safe_shutdown():
    """Безопасное завершение работы агента с сохранением данных."""
    global _shutdown_requested
    print("Завершение работы агента...")
    
    # Устанавливаем флаг и event завершения для остановки всех циклов
    _shutdown_requested = True
    _shutdown_event.set()  # Сигнал всем scheduler'ам
    
    # Очищаем очередь TTS и останавливаем поток
    try:
        while True:
            _tts_queue.get_nowait()
    except queue.Empty:
        pass
    _tts_queue.put({'cmd': 'quit'})
    
    # Даем время на завершение потока TTS
    time.sleep(0.5)
    
    # Сохраняем все данные пользователя (безопасный доступ через globals)
    print("Сохранение данных...")
    g = globals()
    
    if 'task_manager' in g:
        try:
            g['task_manager']._save()
            print("[SAVE] Задачи сохранены")
        except Exception as e:
            print(f"[SAVE] Ошибка сохранения задач: {e}")
    
    if 'user_profile' in g:
        try:
            g['user_profile']._save()
            print("[SAVE] Профиль сохранен")
        except Exception as e:
            print(f"[SAVE] Ошибка сохранения профиля: {e}")
    
    if 'history_logger' in g:
        try:
            g['history_logger']._save()
            print("[SAVE] История сохранена")
        except Exception as e:
            print(f"[SAVE] Ошибка сохранения истории: {e}")
    
    print("Данные сохранены. До свидания!")
    # Не вызываем sys.exit() сразу - даем главному циклу завершиться
    # sys.exit(0) будет вызван из главного цикла

def _stdin_listener():
    global _mic_muted
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if line.startswith("/"):
                if line in ("/help", "/h", "/?"):
                    print("Доступные команды:")
                    print("  /help — показать помощь")
                    print("  /color <имя> — установить цвет консоли. Доступно: " + 
                          ", ".join(sorted(k for k in _ANSI_COLORS.keys() if k != "reset")) + 
                          ". Пример: /color green")
                    print("  /color reset — сбросить цвет по умолчанию")
                    print("  /mute — выключить микрофон (распознавание речи)")
                    print("  /unmute — включить микрофон (распознавание речи)")
                    print("  /exit — завершить работу агента")
                    print("  Введите текст без слеша — выполнить команду в текстовом режиме (ответ только в консоли)")
                    continue
                if line.startswith("/color"):
                    parts = line.split(maxsplit=1)
                    if len(parts) == 1:
                        print("Укажите цвет: /color <имя>. Пример: /color blue")
                        continue
                    name = parts[1].strip()
                    if set_console_color(name):
                        print(f"Цвет консоли изменён на: {name}")
                    else:
                        print("Неизвестный цвет. Доступные: " + 
                              ", ".join(sorted(_ANSI_COLORS.keys())))
                    continue
                if line == "/mute":
                    with _mic_muted_lock:
                        _mic_muted = True
                    print("[MIC] Микрофон выключен.")
                    continue
                if line == "/unmute":
                    with _mic_muted_lock:
                        _mic_muted = False
                    print("[MIC] Микрофон включен.")
                    continue
                if line == "/exit":
                    _safe_shutdown()
                # неизвестная команда с префиксом /
                print("Неизвестная команда. Введите /help для списка.")
                continue
            # Текстовый режим: любая строка без префикса '/' — это команда/запрос
            try:
                response = route_command(line)
            except Exception as e:
                response = f"Ошибка обработки запроса: {e}"
            print(f"[Вера] {response}")
            
            # Логирование в память и историю
            try:
                _push_history("user", line)
                _push_history("assistant", response)
                history_logger.add_entry(line, response, command_type="text")
            except Exception as e:
                print(f"[HISTORY] Ошибка логирования: {e}")
        except Exception as e:
            retry_count += 1
            print(f"[STDIN] Ошибка чтения команд (попытка {retry_count}/{max_retries}): {e}")
            if retry_count >= max_retries:
                print("[STDIN] КРИТИЧНО: stdin поток остановлен после множественных сбоев")
                break
            time.sleep(1)

def _flush_stdin_buffer():
    try:
        # Считываем и игнорируем все нажатые ранее клавиши, чтобы они не попали в обработку
        while msvcrt.kbhit():
            try:
                msvcrt.getwch()
            except Exception:
                # На всякий случай пробуем байтовое чтение
                try:
                    msvcrt.getch()
                except Exception:
                    break
    except Exception:
        pass

_enable_windows_ansi()

# Использование ConfigManager для централизованного доступа к конфигурации
from main.config_manager import get_config, get_data_dir

try:
    config = get_config()
    cfg = config.get_all()  # Получаем весь конфиг для обратной совместимости
except Exception as e:
    print(f"[ERROR] Не удалось загрузить конфигурацию: {e}")
    sys.exit(1)

# Функция проверки активационного слова с учётом возможных искажений
def _is_activation(fragment: str) -> bool:
    target = cfg["activation_word"].lower()
    for word in fragment.split():
        if difflib.SequenceMatcher(None, word, target).ratio() >= 0.8:
            return True
    return False

def _remove_activation_words(text: str) -> str:
    target = cfg["activation_word"].lower()
    tokens = text.split()
    kept = []
    for t in tokens:
        if difflib.SequenceMatcher(None, t, target).ratio() >= 0.8:
            continue
        kept.append(t)
    return " ".join(kept).strip()

llama_kwargs = {
    "model_path": cfg["model"]["path"],
    "n_ctx": cfg["model"]["ctx_size"],
    "verbose": False,
}
if "chat_format" in cfg["model"]:
    llama_kwargs["chat_format"] = cfg["model"]["chat_format"]

try:
    llm = Llama(**llama_kwargs)
except Exception as e:
    print(f"[ERROR] Не удалось загрузить модель: {e}")
    sys.exit(1)

_print_banner_and_tips(cfg["activation_word"])

# Простая краткосрочная память диалога (в пределах процесса)
# Используем deque для автоматического управления размером
_HISTORY_MAX_TURNS = 8
CONV_HISTORY: deque = deque(maxlen=_HISTORY_MAX_TURNS * 2)

def _push_history(role: str, content: str) -> None:
    if not content:
        return
    CONV_HISTORY.append({"role": role, "content": content.strip()})
    # deque автоматически удаляет старые элементы при достижении maxlen

def _last_by_role(role: str) -> Optional[str]:
    for msg in reversed(CONV_HISTORY):
        if msg.get("role") == role and msg.get("content"):
            return msg["content"]
    return None

_tts_queue: "queue.Queue[dict]" = queue.Queue()
_tts_thread: Optional[threading.Thread] = None

def _tts_worker():
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            voice_index = cfg["tts"]["voice_index"]
            if 0 <= voice_index < len(voices):
                engine.setProperty('voice', voices[voice_index].id)
            engine.setProperty('rate', cfg["tts"]["rate"])
            engine.setProperty('volume', cfg["tts"]["volume"])

            # Непрерывный цикл обработки без повторного запуска run loop
            engine.startLoop(False)
            while True:
                # Обрабатываем команды из очереди (блокируем с таймаутом вместо busy-wait)
                try:
                    cmd = _tts_queue.get(timeout=0.05)
                except queue.Empty:
                    cmd = None

                if cmd is not None:
                    action = cmd.get('cmd')
                    if action == 'say':
                        text = cmd.get('text', '')
                        if text:
                            engine.say(text)
                    elif action == 'stop':
                        try:
                            engine.stop()
                        except Exception:
                            pass
                    elif action == 'quit':
                        try:
                            engine.endLoop()
                        except Exception:
                            pass
                        return  # Нормальное завершение

                # Один тик цикла движка
                try:
                    engine.iterate()
                except Exception as e:
                    print(f"[TTS] Ошибка в цикле: {e}")
        except Exception as e:
            retry_count += 1
            print(f"[TTS] Критическая ошибка TTS потока (попытка {retry_count}/{max_retries}): {e}")
            if retry_count >= max_retries:
                print("[TTS] ФАТАЛЬНО: TTS поток остановлен после множественных сбоев")
                print("[TTS] Агент продолжит работу, но озвучивание недоступно")
                break
            time.sleep(1)  # Пауза перед повторной попыткой

# Запускаем фоновый поток TTS один раз
_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()

def _clean_for_tts(text: str) -> str:
    """Удаляет из ответа источники и ссылки, чтобы TTS их не зачитывал. Преобразует годы в правильное произношение."""
    try:
        s = text or ""
        # Удаляем блок вида "(источники: ... )" в конце
        s = re.sub(r"\s*\(источники?:.*?\)\s*$", "", s, flags=re.IGNORECASE | re.DOTALL)
        # Удаляем строки, начинающиеся с "источники:"
        s = re.sub(r"\bисточники?:.*$", "", s, flags=re.IGNORECASE)
        # Удаляем URL
        s = re.sub(r"https?://\S+", "", s)
        # Сжимаем пробелы
        s = re.sub(r"\s{2,}", " ", s).strip()
        # Преобразуем годы в правильное произношение
        s = convert_years_in_text(s)
        return s
    except Exception:
        return text

def speak(text: str):
    try:
        while True:
            _tts_queue.get_nowait()
    except queue.Empty:
        pass

    _tts_queue.put({'cmd': 'stop'})
    safe_text = _clean_for_tts(text)
    _tts_queue.put({'cmd': 'say', 'text': safe_text})
    return _tts_thread

def interrupt_speech():
    _tts_queue.put({'cmd': 'stop'})

print("Загрузка модели Vosk...")
try:
    # Читаем путь к модели из конфигурации
    vosk_cfg = cfg.get("vosk", {})
    model_path = vosk_cfg.get("model_path", "vosk-model-small-ru-0.22")  # Fallback для совместимости
    samplerate = vosk_cfg.get("samplerate", 16000)
    
    print(f"[VOSK] Загрузка модели из: {model_path}")
    vosk_model = vosk.Model(model_path)
    print(f"[VOSK] Модель успешно загружена")
except Exception as e:
    print(f"[ERROR] Ошибка загрузки модели Vosk из '{model_path}': {e}")
    print(f"[ERROR] Убедитесь, что путь к модели указан правильно в config.json")
    sys.exit(1)

rec = vosk.KaldiRecognizer(vosk_model, samplerate)

q = queue.Queue()

def audio_callback(indata, frames, time_, status):
    if status:
        print(status, file=sys.stderr)
    with _mic_muted_lock:
        if _mic_muted:
            return
    q.put(bytes(indata))

# Настройки веб-поиска
_WEB_CFG = cfg["web_search"]
LAST_SEARCH_URLS: list[str] = []
set_speak_callback(speak)
set_last_search_urls_ref(LAST_SEARCH_URLS)
set_reminder_shutdown_event(_shutdown_event)  # Передаём event для graceful shutdown
start_scheduler()

# Инициализация планировщика запуска/закрытия приложений
set_scheduled_speak_callback(speak)
set_open_app_callback(open_app_by_name)
set_close_app_callback(close_app_by_name)
set_app_scheduler_shutdown_event(_shutdown_event)  # Передаём event для graceful shutdown
start_app_scheduler()

# Инициализация новых модулей
DATA_DIR = get_data_dir()
DATA_DIR.mkdir(exist_ok=True)

task_manager = TaskManager(DATA_DIR / "tasks.json")
user_profile = UserProfile(DATA_DIR / "user_profile.json")
history_logger = HistoryLogger(DATA_DIR / "history.json", max_entries=1000)

print(f"[INFO] Модули задач, профиля и истории инициализированы.")

# Предрасчитанные обработчики для маршрутизации команд
HANDLERS_WITH_MANAGERS = (
    partial(execute_task_command, task_manager=task_manager),
    partial(execute_profile_command, user_profile=user_profile),
    partial(execute_history_command, history_logger=history_logger),
    partial(execute_user_name_command, user_profile=user_profile),
)


# Маршрутизация команд
def route_command(text: str) -> str:
    # Проверка на мультизадачность ПЕРВОЙ
    is_multi, response = execute_multitask(text, route_command)
    if is_multi:
        return response

    # Сначала проверяем обработчики с менеджерами
    for h in HANDLERS_WITH_MANAGERS:
        try:
            res = h(text)
        except Exception as e:
            print(f"[ERROR] handler: {e}")
            res = None
        if res is not None:
            return res
    
    # Проверяем валюты, погоду и википедию (специальные обработчики)
    for h in (execute_currency_command, execute_weather_command, execute_wikipedia_command):
        try:
            res = h(text)
        except Exception as e:
            print(f"[ERROR] {h.__name__}: {e}")
            res = None
        if res is not None:
            return res
    
    # Остальные команды из модулей
    for h in HANDLERS:
        try:
            res = h(text)
        except Exception as e:
            print(f"[ERROR] {h.__name__}: {e}")
            res = None
        if res is not None:
            return res
    
    return ask_llm(text)


SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.txt"
try:
    with SYSTEM_PROMPT_PATH.open(encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
except Exception as e:
    print(f"[ERROR] Не удалось загрузить system_prompt.txt: {e}")
    SYSTEM_PROMPT = "Ты — Вера, голосовая помощница. Отвечаешь кратко на русском."

def _parse_tool_call(text: str) -> Optional[dict]:
    def _maybe_unwrap_code(s: str) -> str:
        s = s.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return s

    try:
        patterns = [
            r"<\|tool_call\|>\s*(.*?)\s*</\|tool_call\|>",  # с закрывающим тегом
            r"<\|tool_call\|>\s*(.*?)\s*<\|tool_call\|>",   # два одинаковых тега
            r"<tool_call>\s*(.*?)\s*</tool_call>",
            r"<\|tool_call\|>\s*(\{.*?\})",                  # один тег + JSON
        ]
        for pat in patterns:
            m = re.search(pat, text, flags=re.DOTALL | re.IGNORECASE)
            if not m:
                continue
            payload = _maybe_unwrap_code(m.group(1))
            try:
                data = json.loads(payload)
                if isinstance(data, dict) and data.get("name"):
                    return data
            except Exception as e:
                continue
        # Фолбэк: если вся строка — JSON с полем name
        candidate = _maybe_unwrap_code(text)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data.get("name"):
                return data
        except Exception:
            pass
    except Exception:
        pass
    return None

_WEB_SEARCH_KEYWORDS = (
    # Финансы
    "курс", "валют", "usd", "eur", "рубл", "btc", "биткоин", "акци", "индекс",
    # Время и актуальность
    "новост", "сегодня", "завтра", "сейчас", "онлайн", "в прямом эфире",
    "расписани", "пробк", "трафик", "ковид", "эпидеми",
    # Даты выпуска и события
    "когда вышел", "когда выпущен", "когда был выпущен", "дата выпуска", "дата выхода",
    "когда появил", "когда создан", "когда основан",
    # Определения и информация
    "что означает", "как расшифровывается", "расшифровка",
    # Рейтинги и позиции
    "какое место", "в топе", "рейтинг", "занимает место", "позиция в",
    "лучш", "топ ", "список",
    # Поисковые команды
    "найди", "найти", "поищи", "поискать", "узнай", "узнать", "проверь", "проверить",
    # Технологии и продукты
    "iphone", "rtx", "gtx", "playstation", "xbox", "nvidia", "amd",
)


def _should_use_web_search(user_text: str) -> bool:
    try:
        t = (user_text or "").lower()
        return any(k in t for k in _WEB_SEARCH_KEYWORDS)
    except Exception:
        return False

def ask_llm(user_text: str) -> str:
    # Быстрый путь: если есть ключевые слова веб-поиска — сразу ищем, минуя модель
    if _should_use_web_search(user_text):
        try:
            # print(f"[FAST_PATH] Веб-поиск по ключевым словам: {user_text}")
            return web_search_answer(user_text, _WEB_CFG, SYSTEM_PROMPT, llm, LAST_SEARCH_URLS)
        except Exception as e:
            print(f"[WEB_SEARCH] Ошибка быстрого поиска: {e}")
            # Продолжаем обычный путь через модель
    
    # Формируем системный промпт с информацией о пользователе
    system_content = SYSTEM_PROMPT
    
    # Добавляем информацию из профиля пользователя
    try:
        profile_info = []
        if user_profile.name:
            profile_info.append(f"Имя пользователя: {user_profile.name}")
        
        notes = user_profile.get_all_notes()
        if notes:
            for note in notes[:5]:  # Берём до 5 заметок
                profile_info.append(f"{note.key.replace('_', ' ')}: {note.value}")
        
        if profile_info:
            system_content += "\n\nИнформация о пользователе:\n" + "\n".join(profile_info)
    except Exception as e:
        print(f"[LLM] Ошибка добавления профиля: {e}")
    
    messages = [{"role": "system", "content": system_content}]
    # Краткая история диалога
    try:
        for m in CONV_HISTORY[-(_HISTORY_MAX_TURNS * 2):]:
            messages.append(m)
    except Exception:
        pass
    messages.append({"role": "user", "content": user_text})
    allowed = {"temperature", "top_p", "top_k", "min_p", "repeat_penalty", "max_tokens", "seed", "stop"}
    mcfg = cfg["model"]
    gen_args = {k: mcfg[k] for k in allowed if k in mcfg}
    # Если max_tokens <= 0 — не ограничиваем длину ответа (не передаём параметр)
    if "max_tokens" in gen_args:
        try:
            if int(gen_args["max_tokens"]) <= 0:
                del gen_args["max_tokens"]
        except Exception:
            pass
    try:
        result = llm.create_chat_completion(messages=messages, **gen_args)
        assistant_reply = result["choices"][0]["message"]["content"].strip()
        # Удаляем теги мышления, если они все же появились
        assistant_reply = re.sub(r"<think>.*?</think>", "", assistant_reply, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"[LLM] Ошибка генерации: {e}")
        return "Сейчас не могу ответить. Проверьте модель в config.json и попробуйте снова."

    # Обработка вызова инструмента от модели
    tool = _parse_tool_call(assistant_reply)
    if tool:
        tool_name = tool.get("name", "")
        args = tool.get("arguments") or {}
        
        # web_search — встроенный инструмент
        if tool_name == "web_search":
            try:
                query = str(args.get("query") or user_text).strip()
                if not query:
                    return "Что искать? Уточните запрос."
                return web_search_answer(query, _WEB_CFG, SYSTEM_PROMPT, llm, LAST_SEARCH_URLS)
            except Exception as e:
                print(f"[WEB_SEARCH] Ошибка: {e}")
                return "Не удалось выполнить веб-поиск сейчас."
        
        # Проверяем плагины из TOOLS
        if tool_name in TOOLS:
            try:
                print(f"[TOOL_CALL] {tool_name}: {args}")
                tool_result = TOOLS[tool_name](args)
                
                # Передаём результат модели для анализа/пересказа
                if tool_result and len(tool_result) > 100:
                    # Просим модель кратко пересказать
                    summary_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": f"Я прочитала документ. Вот его содержимое:\n\n{tool_result}"},
                        {"role": "user", "content": "Кратко перескажи основное содержание."}
                    ]
                    try:
                        result = llm.create_chat_completion(messages=summary_messages, **gen_args)
                        summary = result["choices"][0]["message"]["content"].strip()
                        summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
                        return summary
                    except Exception as e:
                        print(f"[TOOL] Ошибка суммаризации: {e}")
                        # Возвращаем сырой результат, обрезанный
                        return tool_result[:2000] + "..." if len(tool_result) > 2000 else tool_result
                
                return tool_result
            except Exception as e:
                print(f"[TOOL] Ошибка выполнения {tool_name}: {e}")
                return f"Ошибка выполнения {tool_name}: {e}"

    # Очищаем tool call теги из ответа, если они остались (модель вернула их, но они не обработались)
    assistant_reply = re.sub(r"<\|tool_call\|>.*?</\|tool_call\|>", "", assistant_reply, flags=re.DOTALL).strip()
    assistant_reply = re.sub(r"<\|tool_call\|>.*?<\|tool_call\|>", "", assistant_reply, flags=re.DOTALL).strip()
    assistant_reply = re.sub(r"<tool_call>.*?</tool_call>", "", assistant_reply, flags=re.DOTALL).strip()
    assistant_reply = re.sub(r"<\|tool_call\|>\s*\{.*?\}", "", assistant_reply, flags=re.DOTALL).strip()
    
    return assistant_reply

def run_main_loop():
    """Главный цикл прослушивания и обработки команд."""
    global _shutdown_requested
    
    print("[INFO] Система готова. Скажите ключевое слово.")
    # Теперь можно принимать команды из консоли — запускаем поток чтения stdin
    _flush_stdin_buffer()
    _stdin_thread = threading.Thread(target=_stdin_listener, daemon=True)
    _stdin_thread.start()
    silence_timeout = cfg["silence_timeout"]

    with sd.RawInputStream(samplerate=samplerate, blocksize=8000, dtype='int16', channels=1, callback=audio_callback):
        last_audio_time = time.time()
        listening_for_command = False
        while not _shutdown_requested:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = rec.Result()
                text = json.loads(result)["text"].lower().strip()
                if text:
                    print(f"[ВЫ] {text}")
                if not text:
                    continue

                # Прерываем речь ТОЛЬКО если сказано ключевое слово (активация)
                if _is_activation(text):
                    interrupt_speech()
                
                # Останавливаем звонок таймера при активации или команде "стоп"
                if is_timer_ringing():
                    if _is_activation(text) or text.strip().lower() in ("стоп", "хватит", "отключи", "выключи"):
                        stop_timer_ring()
                        speak("Таймер отключён.")
                        continue

                if not listening_for_command:
                    if _is_activation(text):
                        command_text = _remove_activation_words(text)
                        if command_text:
                            user_command = command_text
                        else:
                            speak("Я слушаю. Какую команду выполнить?")
                            listening_for_command = True
                            last_audio_time = time.time()
                            continue
                    else:
                        # Игнорируем речь без ключевого слова
                        continue
                else:
                    user_command = text
                    listening_for_command = False

                response = route_command(user_command)
                print(f"[Вера] {response}")
                
                # Логирование в память и историю
                try:
                    _push_history("user", user_command)
                    _push_history("assistant", response)
                    history_logger.add_entry(user_command, response)
                except Exception as e:
                    print(f"[HISTORY] Ошибка логирования: {e}")
                
                speak(response)
            else:
                # анализируем промежуточный результат, чтобы ловить ключевое слово без задержки
                partial = json.loads(rec.PartialResult()).get("partial", "").lower().strip()
                if partial:
                    # Пока пользователь говорит — обновляем таймер тишины
                    if listening_for_command:
                        last_audio_time = time.time()

                # проверяем тайм-аут тишины
                if listening_for_command and (time.time() - last_audio_time > silence_timeout):
                    listening_for_command = False
    
    # Главный цикл завершен
    sys.exit(0)


if __name__ == "__main__":
    run_main_loop()