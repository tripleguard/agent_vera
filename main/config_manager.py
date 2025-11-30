import json
import sys
import os
from pathlib import Path
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

# Конфигурация по умолчанию (создаётся при первом запуске)
DEFAULT_CONFIG = {
    "model": {
        "path": "auto",
        "ctx_size": 8192,
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "repeat_penalty": 1.1,
        "max_tokens": 0,
        "seed": 42,
        "chat_format": "chatml"
    },
    "vosk": {
        "model_path": "vosk-model-small-ru-0.22",
        "samplerate": 16000
    },
    "activation_word": "Вера",
    "silence_timeout": 2,
    "tts": {
        "voice_index": 3,
        "rate": 180,
        "volume": 0.8
    },
    "commands": {},
    "sites": {
        "ютуб": "https://www.youtube.com/",
        "хабр": "https://habr.com/ru/",
        "вк": "https://vk.com/"
    },
    "web_search": {
        "max_sources": 3,
        "page_timeout_sec": 2.5,
        "per_page_limit": 1200,
        "llm_max_tokens": 500,
        "oversample_links_factor": 2,
        "oversample_candidates_factor": 2,
        "log_page_errors": False,
        "max_bytes_per_page": 70000,
        "disable_time_limits": True,
        "total_context_limit": 3600,
        "news_max_age_days": 7,
        "cache_ttl_sec": 600,
        "cache_max_entries": 100,
        "early_stop_min_sources": 3,
        "early_stop_timeout": 5.0
    }
}


def _get_base_path() -> Path:
    """Возвращает базовый путь для ресурсов."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle - _MEIPASS содержит упакованные файлы
        return Path(sys._MEIPASS)
    else:
        # Обычный запуск - папка main
        return Path(__file__).resolve().parent


def _get_project_root() -> Path:
    """Возвращает корень проекта (для data/ и моделей)."""
    if getattr(sys, 'frozen', False):
        return Path(os.path.dirname(sys.executable))
    else:
        return Path(__file__).resolve().parent.parent


class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config: Optional[dict] = None
    _config_path: Optional[Path] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: Optional[Path] = None):
        if self._config is None:
            if config_path is None:
                # Конфиг всегда в data/config.json рядом с exe/проектом
                project_root = _get_project_root()
                config_path = project_root / "data" / "config.json"
            self._config_path = config_path
            self._ensure_config_exists()
            self._load_config()
            self._resolve_paths()
    
    def _ensure_config_exists(self) -> None:
        """Создаёт config.json с настройками по умолчанию, если он не существует."""
        if self._config_path.exists():
            return
        
        # Создаём папку data если нужно
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Записываем конфиг по умолчанию
        try:
            with self._config_path.open('w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print(f"[КОНФИГ] Создан файл настроек: {self._config_path}")
            logger.info(f"Created default config: {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")
            raise
    
    def _resolve_paths(self) -> None:
        """Преобразует относительные пути к моделям в абсолютные."""
        if self._config is None:
            return
        
        project_root = _get_project_root()
        
        # Путь к LLM модели (с автоопределением)
        if "model" in self._config and "path" in self._config["model"]:
            model_path = self._config["model"]["path"]
            
            # Автоопределение: если path = "auto" или пустой, ищем .gguf файл
            if not model_path or model_path.lower() == "auto":
                gguf_path = self._find_gguf_model(project_root)
                if gguf_path:
                    self._config["model"]["path"] = str(gguf_path)
                    logger.info(f"LLM model auto-detected: {gguf_path}")
                else:
                    logger.warning("No .gguf model found in project root")
            elif not os.path.isabs(model_path):
                abs_path = project_root / model_path
                if abs_path.exists():
                    self._config["model"]["path"] = str(abs_path)
                    logger.info(f"LLM model path resolved: {abs_path}")
                else:
                    # Попробуем автопоиск если указанный файл не найден
                    gguf_path = self._find_gguf_model(project_root)
                    if gguf_path:
                        self._config["model"]["path"] = str(gguf_path)
                        logger.info(f"Specified model not found, using: {gguf_path}")
        
        # Путь к Vosk модели
        if "vosk" in self._config and "model_path" in self._config["vosk"]:
            vosk_path = self._config["vosk"]["model_path"]
            if not os.path.isabs(vosk_path):
                abs_path = project_root / vosk_path
                if abs_path.exists():
                    self._config["vosk"]["model_path"] = str(abs_path)
                    logger.info(f"Vosk model path resolved: {abs_path}")
    
    def _find_gguf_model(self, search_dir: Path) -> Optional[Path]:
        """Ищет первый .gguf файл в указанной директории."""
        try:
            gguf_files = list(search_dir.glob("*.gguf"))
            if gguf_files:
                # Сортируем по размеру (большие модели обычно лучше)
                gguf_files.sort(key=lambda p: p.stat().st_size, reverse=True)
                return gguf_files[0]
        except Exception as e:
            logger.error(f"Error searching for .gguf files: {e}")
        return None
    
    def _load_config(self) -> None:
        """Загружает конфигурацию из JSON файла."""
        try:
            if not self._config_path.exists():
                raise FileNotFoundError(f"Config file not found: {self._config_path}")
            
            with self._config_path.open(encoding='utf-8') as f:
                self._config = json.load(f)
                logger.info(f"Configuration loaded from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    def reload(self) -> None:
        """Перезагружает конфигурацию из файла."""
        self._config = None
        self._load_config()
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """Получает значение из конфигурации по вложенным ключам."""
        if self._config is None:
            return default
        
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def get_all(self) -> dict:
        """Возвращает весь словарь конфигурации."""
        return self._config or {}
    
    def set(self, *keys: str, value: Any) -> None:
        if self._config is None:
            self._config = {}
        
        current = self._config
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def save(self) -> None:
        """Сохраняет текущую конфигурацию в файл."""
        try:
            with self._config_path.open('w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            logger.info(f"Configuration saved to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise


# Глобальный экземпляр для удобного импорта
_global_config = None

def get_config() -> ConfigManager:
    """Возвращает глобальный экземпляр ConfigManager."""
    global _global_config
    if _global_config is None:
        _global_config = ConfigManager()
    return _global_config
