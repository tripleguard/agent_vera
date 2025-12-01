import asyncio
import aiohttp
from typing import List, Tuple

from web.web_utils import DEFAULT_HEADERS, extract_visible_text


async def fetch_url_async(
    url: str,
    session: aiohttp.ClientSession,
    timeout: float = 3.0,
    max_bytes: int = 70000
) -> Tuple[str, str]:

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers=DEFAULT_HEADERS
        ) as response:
            # Читаем контент с ограничением размера
            content = await response.read()
            
            if len(content) > max_bytes:
                content = content[:max_bytes]
            
            # Используем парсер с удалением инфобоксов
            text = extract_visible_text(content.decode('utf-8', errors='ignore'))[:1500]
            return url, text
            
    except asyncio.TimeoutError:
        # Таймаут - возвращаем пустой результат
        return url, ""
    except Exception:
        # Любая другая ошибка - возвращаем пустой результат
        return url, ""


async def fetch_urls_async(
    urls: List[str],
    max_sources: int,
    timeout: float,
    early_stop_min: int,
    early_stop_timeout: float
) -> List[Tuple[str, str]]:

    results = []
    start_time = asyncio.get_event_loop().time()
    
    async with aiohttp.ClientSession() as session:
        # Создаем Task объекты (не coroutines) чтобы можно было их отменять
        tasks = [asyncio.create_task(fetch_url_async(url, session, timeout)) for url in urls]
        
        # Обрабатываем по мере завершения
        for coro in asyncio.as_completed(tasks):
            url, text = await coro
            
            # Добавляем только непустые результаты
            if text:
                results.append((url, text))
                
                elapsed = asyncio.get_event_loop().time() - start_time
                
                # Early stop условия
                if len(results) >= max_sources:
                    print(f"[ASYNC_FETCH] Достигнут максимум: {max_sources} источников")
                    # Отменяем оставшиеся задачи
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    break
                
                if len(results) >= early_stop_min and elapsed >= early_stop_timeout:
                    print(f"[ASYNC_FETCH] Early stop: {len(results)} источников за {elapsed:.1f}с")
                    # Отменяем оставшиеся задачи
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    break
        
        # Ждем завершения всех задач (включая отмененные)
        await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


def fetch_urls_sync(urls: List[str], **kwargs) -> List[Tuple[str, str]]:
    try:
        # Проверяем, есть ли уже запущенный loop (например, в Jupyter)
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop is not None:
        # Если loop уже запущен, создаём новый в отдельном потоке
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, fetch_urls_async(urls, **kwargs))
            return future.result()
    else:
        # Стандартный случай — используем asyncio.run(), который корректно
        # создаёт и закрывает event loop
        return asyncio.run(fetch_urls_async(urls, **kwargs))
