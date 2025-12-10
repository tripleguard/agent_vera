import asyncio, re
from datetime import timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.types import User

API_ID, API_HASH = 2040, "b18441a1ff607e10a989891a5462e627"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_client: Optional[TelegramClient] = None
_auth = {"phone": None, "hash": None, "code": False, "2fa": False}

def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def _norm_name(name: str) -> str:
    name = name.strip()
    # Дательный/родительный падеж
    for end, repl in [("у", ""), ("ю", "я"), ("е", "а"), ("и", "я"), ("ы", "а")]:
        if len(name) > 2 and name.endswith(end):
            base = name[:-1] + repl if repl else name[:-1]
            if len(base) >= 2: return base
    return name

async def _client_get() -> TelegramClient:
    global _client
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _client:
        _client = TelegramClient(str(DATA_DIR/"telegram_session"), API_ID, API_HASH,
            device_model="Windows 10", system_version="10.0", app_version="5.9.0", lang_code="ru")
    if not _client.is_connected(): await _client.connect()
    return _client

async def _auth_start(phone: str) -> str:
    client = await _client_get()
    phone = re.sub(r"[\s\-\(\)]", "", phone)
    if not phone.startswith("+"): phone = "+" + phone
    try:
        r = await client.send_code_request(phone)
        _auth.update({"phone": phone, "hash": r.phone_code_hash, "code": True, "2fa": False})
        return f"Код отправлен на {phone}. Скажи код."
    except Exception as e: return f"Ошибка: {e}"

async def _auth_code(code: str) -> str:
    if not _auth["code"]: return "Сначала укажи номер телефона."
    client = await _client_get()
    try:
        await client.sign_in(phone=_auth["phone"], code=code, phone_code_hash=_auth["hash"])
        _auth.update({"code": False, "2fa": False})
        return f"Telegram подключен!"
    except SessionPasswordNeededError:
        _auth.update({"code": False, "2fa": True})
        return "Нужен 2FA пароль."
    except PhoneCodeInvalidError: return "Неверный код."
    except Exception as e: return f"Ошибка: {e}"

async def _auth_2fa(pwd: str) -> str:
    if not _auth["2fa"]: return "2FA не требуется."
    try:
        await (await _client_get()).sign_in(password=pwd)
        _auth.update({"code": False, "2fa": False})
        return "Telegram подключен!"
    except Exception as e: return f"Ошибка: {e}"

async def _logout() -> str:
    global _client
    if not _client: return "Telegram не был подключен."
    try:
        await _client.log_out()
        _client = None
        return "Вышла из Telegram."
    except Exception as e: return f"Ошибка: {e}"

async def _find(name: str) -> Optional[Dict]:
    client = await _client_get()
    name = _norm_name(name).lower()
    best, score = None, 0
    async for d in client.iter_dialogs(limit=100):
        dn = (d.name or "").lower()
        if dn == name: return {"id": d.id, "name": d.name, "entity": d.entity}
        fn = (d.entity.first_name or "").lower() if isinstance(d.entity, User) else ""
        for n in [dn, fn]:
            if n and name in n:
                s = len(name) / len(n)
                if s > score: score, best = s, {"id": d.id, "name": d.name, "entity": d.entity}
    return best

async def _send(contact: str, msg: str) -> str:
    client = await _client_get()
    if not await client.is_user_authorized(): return "Telegram не подключен."
    d = await _find(contact)
    if not d: return f"Не нашла '{_norm_name(contact)}'."
    try:
        await client.send_message(d["id"], msg)
        return f"Написала {d['name']}: \"{msg}\""
    except Exception as e: return f"Ошибка: {e}"

async def _send_batch(recipients: List[Dict]) -> str:
    return " ".join([await _send(r["contact"], r["message"]) for r in recipients if r.get("contact") and r.get("message")])

async def _read(contact: str) -> str:
    client = await _client_get()
    if not await client.is_user_authorized(): return "Telegram не подключен."
    d = await _find(contact)
    if not d: return f"Не нашла чат с '{_norm_name(contact)}'."
    me = await client.get_me()
    msgs = []
    async for m in client.iter_messages(d["id"], limit=5):
        if m.text:
            is_me = m.sender_id == me.id
            t = m.date.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=3))).strftime("%H:%M") if m.date else ""
            msgs.append({"text": m.text[:300], "time": t, "is_me": is_me})
    if not msgs: return f"Нет сообщений с {d['name']}."
    if msgs[0]["is_me"]:
        return f"{d['name']} пока не ответил(а). Твоё ({msgs[0]['time']}): \"{msgs[0]['text']}\""
    their = [m for m in msgs if not m["is_me"]]
    their = their[:next((i for i,m in enumerate(msgs) if m["is_me"]), len(msgs))]
    if len(their) == 1:
        return f"{d['name']} ({their[0]['time']}): \"{their[0]['text']}\""
    return f"{d['name']} написал(а) {len(their)} сообщений:\n" + "\n".join(f"[{m['time']}] {m['text']}" for m in reversed(their))

async def _who_wrote() -> str:
    client = await _client_get()
    if not await client.is_user_authorized(): return "Telegram не подключен."
    me = await client.get_me()
    res = []
    async for d in client.iter_dialogs(limit=30):
        if not isinstance(d.entity, User): continue
        async for m in client.iter_messages(d.id, limit=1):
            if m.sender_id != me.id and m.text:
                t = m.date.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=3))).strftime("%H:%M") if m.date else ""
                res.append(f"• {d.name} ({t}): {m.text[:80]}{'...' if len(m.text)>80 else ''}")
            break
        if len(res) >= 10: break
    return "Никто не писал." if not res else "В личке писали:\n" + "\n".join(res)

def execute_telegram_tool(args: dict) -> str:
    a, get = args.get("action", "send_message"), args.get
    req = {"start_auth": [("phone",)], "enter_code": [("code",)], "enter_password": [("password",)],
           "send_message": [("contact",), ("message",)], "send_batch": [("recipients",)], "read_chat": [("contact",)]}
    for k, in req.get(a, []):
        if not get(k): return f"Укажи {k}."
    try:
        if a == "check_auth":
            async def _chk(): return await (await _client_get()).is_user_authorized()
            return "Подключен." if _run(_chk()) else "Не подключен."
        if a == "start_auth": return _run(_auth_start(get("phone")))
        if a == "enter_code": return _run(_auth_code(get("code")))
        if a == "enter_password": return _run(_auth_2fa(get("password")))
        if a == "send_message": return _run(_send(get("contact"), get("message")))
        if a == "send_batch": return _run(_send_batch(get("recipients")))
        if a == "read_chat": return _run(_read(get("contact")))
        if a == "check_who_wrote": return _run(_who_wrote())
        if a == "logout": return _run(_logout())
        return f"Неизвестное: {a}"
    except Exception as e: return f"Ошибка: {e}"
