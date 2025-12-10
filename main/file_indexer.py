import urllib.parse
from typing import Dict, List

try:
    import win32com.client
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from main.lang_ru import ru_to_en as _ru_to_en


def _build_search_variants(query: str) -> List[str]:
    """Создаёт варианты поиска: оригинал, транслит, отдельные слова."""
    variants = set()
    q = query.strip().lower()
    
    # Оригинальный запрос
    variants.add(q)
    
    # Транслитерация
    translit = _ru_to_en(q)
    if translit != q:
        variants.add(translit)
    
    # Отдельные слова (если несколько)
    words = q.split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 3:  # Только слова >= 3 символов
                variants.add(word)
                translit_word = _ru_to_en(word)
                if translit_word != word:
                    variants.add(translit_word)
    
    return list(variants)


def _query_windows_search(query: str, max_results: int, item_type: str = None) -> List[Dict]:
    if not HAS_WIN32:
        return []
    
    try:
        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        
        # Формируем условие по типу
        type_filter = ""
        if item_type == "file":
            type_filter = "AND System.ItemType <> 'Directory'"
        elif item_type == "folder":
            type_filter = "AND System.ItemType = 'Directory'"
        
        # Создаём варианты поиска (оригинал + транслит + слова)
        variants = _build_search_variants(query)
        like_conditions = " OR ".join([f"System.ItemName LIKE '%{v}%'" for v in variants])
        
        sql = f"""
        SELECT TOP {max_results} System.ItemName, System.ItemUrl, System.ItemType
        FROM SystemIndex WHERE ({like_conditions}) {type_filter}
        """
        
        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open(sql, conn)
        
        results = []
        while not rs.EOF:
            try:
                item_url = str(rs.Fields("System.ItemUrl").Value or "")
                # Преобразуем file:/// URL в реальный путь
                if item_url.startswith("file:"):
                    real_path = urllib.parse.unquote(item_url.replace("file:", "").lstrip("/"))
                    # Исправляем формат пути для Windows (C:/path -> C:\path)
                    if len(real_path) > 1 and real_path[1] == ":":
                        real_path = real_path.replace("/", "\\")
                else:
                    real_path = item_url
                
                results.append({
                    "name": str(rs.Fields("System.ItemName").Value or ""),
                    "path": real_path,
                    "is_dir": rs.Fields("System.ItemType").Value == "Directory",
                })
            except Exception:
                pass
            rs.MoveNext()
        
        rs.Close()
        conn.Close()
        return results
        
    except Exception as e:
        print(f"[FILE_INDEX] Ошибка Windows Search: {e}")
        return []


def search_windows_index(query: str, max_results: int = 50, file_only: bool = True) -> List[Dict]:
    """Ищет файлы через Windows Search."""
    return _query_windows_search(query, max_results, "file" if file_only else None)


def search_windows_index_folders(query: str, max_results: int = 30) -> List[Dict]:
    """Ищет папки через Windows Search."""
    return _query_windows_search(query, max_results, "folder")


def smart_search(query: str, max_results: int = 50, search_folders: bool = False) -> List[Dict]:
    if search_folders:
        return search_windows_index_folders(query, max_results)
    return search_windows_index(query, max_results, file_only=True)
