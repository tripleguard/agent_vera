import re
from typing import List, Tuple


def parse_multitask(text: str) -> List[str]:
    text = re.sub(r"^\s*Вера[,\s]+", "", text.lower().strip(), flags=re.IGNORECASE)
    
    separators = [
        r"\s+и\s+",           
        r"\s+а\s+также\s+",   
        r"\s+плюс\s+",   
        r"\s+ещё\s+",         
        r"\s+потом\s+",       
    ]
    
    separator_pattern = "|".join(f"({p})" for p in separators)
    
    parts = re.split(separator_pattern, text)
    
    commands = []
    for part in parts:
        if part and not part.strip() in ["и", "а также", "плюс", "ещё", "потом"]:
            part = part.strip()
            if part:
                commands.append(part)
    
    if len(commands) > 1:
        return _expand_implicit_commands(commands)
    
    if m := re.match(r"(открой|запусти|закрой|выключи)\s+(.+)", text):
        action = m.group(1)
        targets_str = m.group(2)
        
        if " и " in targets_str:
            targets = [t.strip() for t in re.split(r"\s+и\s+", targets_str) if t.strip()]
            if len(targets) > 1:
                return [f"{action} {target}" for target in targets]
    
    return [text]


def _expand_implicit_commands(commands: List[str]) -> List[str]:
    expanded = []
    last_action = None
    
    for cmd in commands:
        cmd = cmd.strip()
        
        # Проверяем есть ли в команде глагол действия
        has_action = re.search(
            r"\b(открой|запусти|закрой|выключи|включи|установи|поставь|"
            r"создай|удали|найди|покажи|скажи|расскажи|проверь|измерь|"
            r"сделай|сверни|разверни|переключись|перезагрузи|громкость|"
            r"яркость|таймер|напомни)\b",
            cmd
        )
        
        if has_action:
            # Запоминаем действие
            action_match = has_action.group(1)
            last_action = action_match
            expanded.append(cmd)
        else:
            # Если нет действия - добавляем последнее использованное
            if last_action and last_action in ["открой", "запусти", "закрой", "выключи"]:
                expanded.append(f"{last_action} {cmd}")
            else:
                # Если не можем определить - оставляем как есть
                expanded.append(cmd)
    
    return expanded


def execute_multitask(text: str, route_command_func) -> Tuple[bool, str]:
    commands = parse_multitask(text)
    
    # Если одна команда - возвращаем None (не мультизадача)
    if len(commands) <= 1:
        return False, ""
    
    print(f"[MULTITASK] Обнаружено команд: {len(commands)}")
    for i, cmd in enumerate(commands, 1):
        print(f"  {i}. {cmd}")
    
    # Выполняем каждую команду
    responses = [] 
    for cmd in commands:
        result = route_command_func(cmd)
        if result:
            responses.append(result)
    
    # Формируем общий ответ
    if responses:
        # Если ответов много - объединяем кратко
        if len(responses) > 2:
            return True, f"Выполнено команд: {len(responses)}."
        else:
            return True, " ".join(responses)
    else:
        return True, "Команды выполнены."
