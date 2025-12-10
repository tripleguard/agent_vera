import re
import random
import requests
from bs4 import BeautifulSoup
from typing import Optional, List
from urllib.parse import urlparse, quote_plus

# Пул User-Agent для ротации (минимизация блокировок)
_USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Базовые заголовки (User-Agent добавляется динамически)
_BASE_HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Для обратной совместимости
DEFAULT_USER_AGENT = _USER_AGENTS[0]
DEFAULT_HEADERS = {**_BASE_HEADERS, "User-Agent": DEFAULT_USER_AGENT}


def get_default_headers() -> dict:
    #Возвращает заголовки со случайным User-Agent.
    headers = _BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(_USER_AGENTS)
    return headers


def _search_brave(query: str, max_results: int = 6) -> List[str]:
    #Поиск ссылок через Brave Search.
    links = []
    try:
        headers = get_default_headers()
        # Brave Search использует стандартный HTML интерфейс
        url = f"https://search.brave.com/search?q={quote_plus(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            seen = set()
            # Brave возвращает результаты в div с классом snippet или a с data-type="web"
            # Ищем ссылки в результатах поиска
            for a_tag in soup.find_all("a", href=True):
                href = a_tag.get("href", "")
                # Фильтруем только внешние ссылки (не brave.com)
                if href.startswith("http") and "brave.com" not in href and "search.brave" not in href:
                    # Пропускаем служебные ссылки
                    if any(skip in href for skip in ["favicon", "icon", "logo", "cdn.", "static."]):
                        continue
                    if href not in seen:
                        links.append(href)
                        seen.add(href)
                        if len(links) >= max_results:
                            break
    except Exception as e:
        print(f"[SEARCH] Brave error: {e}")
    return links


def _search_ddg_lite(query: str, max_results: int = 6) -> List[str]:
    #Поиск ссылок через DuckDuckGo Lite (fallback).
    links = []
    try:
        headers = get_default_headers()
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            seen = set()
            # DDG Lite: ссылки в формате //duckduckgo.com/l/?uddg=<encoded_url>
            for a_tag in soup.find_all("a", href=True):
                href = a_tag.get("href", "")
                if "uddg=" in href:
                    try:
                        encoded_url = href.split("uddg=")[1].split("&")[0]
                        decoded = unquote(encoded_url)
                        if decoded.startswith("http") and decoded not in seen:
                            links.append(decoded)
                            seen.add(decoded)
                            if len(links) >= max_results:
                                break
                    except Exception:
                        continue
    except Exception as e:
        print(f"[SEARCH] DDG Lite error: {e}")
    return links


def search_duckduckgo(query: str, max_results: int = 6) -> List[str]:
    # Пробуем Brave Search
    links = _search_brave(query, max_results)
    if links:
        print(f"[SEARCH] Brave: найдено {len(links)} ссылок")
        return links
    
    # Fallback на DuckDuckGo Lite
    print("[SEARCH] Brave не дал результатов, пробуем DDG Lite...")
    links = _search_ddg_lite(query, max_results)
    if links:
        print(f"[SEARCH] DDG Lite: найдено {len(links)} ссылок")
        return links
    
    print("[SEARCH] Ни один поисковик не вернул результаты")
    return []


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()
    # Удаляем инфобоксы Википедии — они забивают контекст тех.характеристиками
    for infobox in soup.find_all("table", class_=lambda x: x and "infobox" in x):
        infobox.decompose()
    for infobox in soup.find_all("div", class_=lambda x: x and "infobox" in str(x)):
        infobox.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    parts: list[str] = []
    for t in root.find_all(["h1", "h2", "h3", "p", "li"]):
        txt = t.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    for t in root.find_all(["td", "th"]):
        txt = t.get_text(" ", strip=True)
        if txt and (re.search(r"\d", txt) or len(txt) <= 40):
            parts.append(txt)
    for t in root.find_all(["span", "strong", "b", "time"]):
        txt = t.get_text(" ", strip=True)
        if txt and re.search(r"\d", txt):
            parts.append(txt)
    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip()

def fetch_url(url: str, headers: dict, web_cfg: dict, log_page_errors: bool = False) -> Optional[tuple[str, str]]:
    web_connect_timeout = float(web_cfg.get("connect_timeout_sec", web_cfg.get("page_timeout_sec", 3)))
    web_read_timeout = float(web_cfg.get("read_timeout_sec", web_cfg.get("page_timeout_sec", 3)))
    web_per_page_limit = int(web_cfg.get("per_page_limit", 2000))
    max_bytes_per_page = int(web_cfg.get("max_bytes_per_page", 200000))
    no_timeouts = bool(web_cfg.get("disable_time_limits", True))

    try:
        req_kwargs = {
            "headers": headers,
            "allow_redirects": True,
            "stream": True,
        }
        if not no_timeouts:
            req_kwargs["timeout"] = (web_connect_timeout, web_read_timeout)
        resp = requests.get(url, **req_kwargs)
        status = getattr(resp, "status_code", 0)
        if status in (401, 403):
            try:
                parsed = urlparse(url)
                referer = f"{parsed.scheme}://{parsed.netloc}/"
            except Exception:
                referer = "https://www.google.com/"
            headers2 = dict(headers)
            headers2["Referer"] = referer
            req_kwargs2 = dict(req_kwargs)
            req_kwargs2["headers"] = headers2
            resp = requests.get(url, **req_kwargs2)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if ("text/html" not in ct) and ("application/xhtml" not in ct):
            return None
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= max_bytes_per_page:
                break
        enc = resp.encoding or getattr(resp, "apparent_encoding", None) or "utf-8"
        try:
            html = buf.decode(enc, errors="ignore")
        except Exception:
            html = buf.decode("utf-8", errors="ignore")
        text = extract_visible_text(html)[:web_per_page_limit]
        if not text:
            return None
        return url, text
    except Exception as e:
        if log_page_errors:
            print(f"[WEB] Ошибка загрузки {url}: {e}")
        return None