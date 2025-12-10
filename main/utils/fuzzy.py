import difflib
from typing import Optional, TypeVar, Callable, Iterable

T = TypeVar('T')


def fuzzy_match(query: str, candidate: str, boost_substring: bool = True) -> float:

    if not query or not candidate:
        return 0.0
    
    q = query.lower().strip()
    c = candidate.lower().strip()
    
    # Точное совпадение
    if q == c:
        return 1.0
    
    # Базовый score через SequenceMatcher
    score = difflib.SequenceMatcher(None, q, c).ratio()
    
    # Бонус за вхождение подстроки
    if boost_substring and q in c:
        score += 0.15
    
    return score


def fuzzy_match_best(
    query: str,
    candidates: Iterable[T],
    key: Callable[[T], str],
    threshold: float = 0.6,
    boost_substring: bool = True
) -> Optional[T]:

    best_item = None
    best_score = 0.0
    
    for item in candidates:
        candidate_str = key(item)
        if not candidate_str:
            continue
        
        score = fuzzy_match(query, candidate_str, boost_substring)
        
        if score > best_score:
            best_score = score
            best_item = item
    
    return best_item if best_score >= threshold else None
