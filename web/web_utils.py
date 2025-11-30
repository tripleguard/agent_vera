import re
import requests
from bs4 import BeautifulSoup
from typing import Optional, List
from urllib.parse import urlparse, quote_plus, unquote

# Единый User-Agent для всех HTTP-запросов проекта
# Актуальный Chrome 120 на Windows 11
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def get_default_headers() -> dict:
    """Возвращает копию стандартных заголовков для HTTP-запросов."""
    return DEFAULT_HEADERS.copy()


def search_duckduckgo(query: str, max_results: int = 6) -> List[str]:
    """Поиск ссылок через DuckDuckGo HTML. Общая функция для всех модулей."""
    links = []
    try:
        headers = get_default_headers()
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            pattern = r'uddg=([^&"]+)'
            matches = re.findall(pattern, resp.text)
            seen = set()
            for m in matches:
                try:
                    decoded = unquote(m)
                    if decoded.startswith("http") and decoded not in seen:
                        links.append(decoded)
                        seen.add(decoded)
                        if len(links) >= max_results:
                            break
                except Exception:
                    continue
    except Exception as e:
        print(f"[SEARCH] DuckDuckGo error: {e}")
    return links


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