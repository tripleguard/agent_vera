import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional

try:
    import win32com.client
except Exception:
    win32com = None

import winreg

from main.config_manager import get_data_dir

# Путь к индексу приложений (теперь в data/)
APP_INDEX_PATH = get_data_dir() / "app_index.json"

START_MENU_DIRS = [
    Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")),
    Path(os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")),
]


def _resolve_lnk_target(lnk_path: Path) -> Optional[str]:
    try:
        if win32com is None:
            return None
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(lnk_path))
        target = shortcut.Targetpath or ""
        if target:
            return target
    except Exception:
        pass
    return None


def _iter_start_menu_shortcuts() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for base in START_MENU_DIRS:
        try:
            if not base.exists():
                continue
            for root, _, files in os.walk(base):
                for fn in files:
                    if fn.lower().endswith(".lnk"):
                        p = Path(root) / fn
                        display_name = p.stem
                        target = _resolve_lnk_target(p)
                        exe_path = target if (target and target.lower().endswith(".exe")) else None
                        exe_name = Path(exe_path).name if exe_path else None
                        items.append({
                            "display_name": display_name,
                            "exe_path": exe_path or "",
                            "exe_name": exe_name or "",
                            "lnk_path": str(p),
                            "source": "start_menu",
                        })
        except Exception:
            continue
    return items


def _extract_exe_from_display_icon(icon_val: str) -> Optional[str]:
    if not icon_val:
        return None
    s = icon_val.strip().strip('"')
    s = re.sub(r",\s*\d+$", "", s)
    m = re.search(r"(?i)(.+?\.exe)\b", s)
    if m:
        return m.group(1)
    return None


def _iter_registry_apps() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                for i in range(0, 4096):
                    try:
                        sub = winreg.EnumKey(key, i)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            try:
                                display_name, _ = winreg.QueryValueEx(sk, "DisplayName")
                            except OSError:
                                continue
                            exe_path = None
                            try:
                                icon_val, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                                exe_path = _extract_exe_from_display_icon(icon_val)
                            except OSError:
                                exe_path = None
                            if not exe_path:
                                for value_name in ("QuietUninstallString", "UninstallString"):
                                    try:
                                        v, _ = winreg.QueryValueEx(sk, value_name)
                                        guessed = _extract_exe_from_display_icon(v)
                                        if guessed and os.path.isfile(guessed):
                                            exe_path = guessed
                                            break
                                    except OSError:
                                        pass
                            exe_name = Path(exe_path).name if exe_path else ""
                            items.append({
                                "display_name": str(display_name),
                                "exe_path": exe_path or "",
                                "exe_name": exe_name,
                                "lnk_path": "",
                                "source": "registry",
                            })
                    except Exception:
                        continue
        except Exception:
            continue
    return items

def build_app_index() -> List[Dict[str, str]]:
    """Создает и сохраняет индекс приложений в app_index.json."""
    start_items = _iter_start_menu_shortcuts()
    reg_items = _iter_registry_apps()

    combined: Dict[str, Dict[str, str]] = {}

    def _key_for(it: Dict[str, str]) -> str:
        k = (it.get("exe_name") or it.get("display_name") or "").strip().lower()
        return k

    for it in start_items + reg_items:
        k = _key_for(it)
        if not k:
            lp = it.get("lnk_path") or ""
            if lp:
                k = Path(lp).stem.lower()
        if not k:
            continue
        if k not in combined:
            combined[k] = it
        else:
            prev = combined[k]
            score_prev = int(bool(prev.get("lnk_path"))) + 2 * int(bool(prev.get("exe_path")))
            score_new = int(bool(it.get("lnk_path"))) + 2 * int(bool(it.get("exe_path")))
            if score_new > score_prev:
                combined[k] = it

    data = list(combined.values())
    try:
        APP_INDEX_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[APP_INDEX] Индекс обновлён. Найдено приложений: {len(data)}")
    except Exception:
        traceback.print_exc()
    return data


def is_index_stale(max_age_hours: int = 24) -> bool:
    if not APP_INDEX_PATH.exists():
        return True
    try:
        mtime = APP_INDEX_PATH.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        return age_hours > max_age_hours
    except Exception:
        return True


def load_app_index() -> List[Dict[str, str]]:
    # Автоматическое переиндексирование, если индекс устарел
    if is_index_stale():
        print("[APP_INDEX] Индекс устарел, переиндексирование...")
        return build_app_index()
    
    try:
        if APP_INDEX_PATH.exists():
            return json.loads(APP_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        traceback.print_exc()
        # При ошибке чтения - пересоздаем индекс
        return build_app_index()
    
    return []