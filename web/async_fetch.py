import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
from threading import Lock

from web.web_utils import DEFAULT_HEADERS, extract_visible_text


def _fetch_single_url(
    url: str,
    timeout: float = 3.0,
    max_bytes: int = 70000
) -> Tuple[str, str]:
    try:
        headers = DEFAULT_HEADERS.copy()
        resp = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=True
        )
        resp.raise_for_status()
        
        # Проверяем Content-Type
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in ct and "application/xhtml" not in ct:
            return url, ""
        
        # Читаем контент с ограничением размера
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= max_bytes:
                break
        
        # Декодируем
        enc = resp.encoding or "utf-8"
        try:
            html = buf.decode(enc, errors="ignore")
        except Exception:
            html = buf.decode("utf-8", errors="ignore")
        
        # Парсим текст
        text = extract_visible_text(html)[:1500]
        return url, text
        
    except Exception:
        return url, ""


def fetch_urls_sync(
    urls: List[str],
    max_sources: int = 3,
    timeout: float = 3.0,
    early_stop_min: int = 3,
    early_stop_timeout: float = 5.0
) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    results_lock = Lock()
    start_time = time.time()
    
    # Используем ThreadPoolExecutor для параллельных запросов
    max_workers = min(len(urls), 10)  # Не больше 10 потоков
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Запускаем все задачи
        future_to_url = {
            executor.submit(_fetch_single_url, url, timeout): url 
            for url in urls
        }
        
        # Обрабатываем по мере завершения
        for future in as_completed(future_to_url):
            try:
                url, text = future.result()
                
                if text:
                    with results_lock:
                        results.append((url, text))
                        current_count = len(results)
                    
                    elapsed = time.time() - start_time
                    
                    # Early stop условия
                    if current_count >= max_sources:
                        print(f"[FETCH] Достигнут максимум: {max_sources} источников")
                        # Отменяем оставшиеся задачи
                        for f in future_to_url:
                            f.cancel()
                        break
                    
                    if current_count >= early_stop_min and elapsed >= early_stop_timeout:
                        print(f"[FETCH] Early stop: {current_count} источников за {elapsed:.1f}с")
                        for f in future_to_url:
                            f.cancel()
                        break
                        
            except Exception:
                continue
    
    return results
