import asyncio, random, sqlite3, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, F, types
from datetime import datetime

BOT_TOKEN = "9133436334:AAGHSaxwW0lQKZ7quPdjIwISaNm-2dxXEXw"
ADMIN_ID = 8990817653
DB_PATH = "/root/zetup/zetup.db"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_db()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, total_deposited REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT, amount_raw REAL, stars_credited REAL, status TEXT, payload TEXT)")
    c.commit()
    c.close()

init_db()

def get_user(uid, uname=""):
    c = get_db()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    if uname:
        c.execute("UPDATE users SET username = ? WHERE user_id = ?", (uname, uid))
    c.commit()
    row = c.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    c.close()
    return dict(row)

def add_balance(uid, amount, is_dep=False):
    c = get_db()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, '')", (uid,))
    if is_dep:
        c.execute("UPDATE users SET balance = ROUND(balance + ?, 2), total_deposited = ROUND(total_deposited + ?, 2) WHERE user_id = ?", (amount, amount, uid))
    else:
        c.execute("UPDATE users SET balance = MAX(0, ROUND(balance + ?, 2)) WHERE user_id = ?", (amount, uid))
    c.commit()
    row = c.execute("SELECT balance, total_deposited FROM users WHERE user_id = ?", (uid,)).fetchone()
    c.close()
    return row[0], row[1]

online_pings = {}
crash_state = {
    "round_id": 1,
    "phase": "waiting",
    "start_ts": time.time() + 8.0,
    "mult": 1.00,
    "crash_point": 1.50,
    "bets": {},
    "history": [1.45, 2.30, 1.12, 4.85, 1.67, 9.20, 1.05, 3.10]
}

def gen_crash_point():
    r = random.random()
    if r < 0.06: return 1.00
    if r < 0.58: return round(random.uniform(1.01, 1.75), 2)
    if r < 0.85: return round(random.uniform(1.75, 4.00), 2)
    if r < 0.96: return round(random.uniform(4.00, 12.00), 2)
    if r < 0.99: return round(random.uniform(12.00, 35.00), 2)
    return round(random.uniform(35.00, 100.00), 2)

async def crash_loop():
    while True:
        now = time.time()
        ph = crash_state["phase"]
        if ph == "waiting" and now >= crash_state["start_ts"]:
            crash_state["phase"] = "flying"
            crash_state["start_ts"] = now
            crash_state["mult"] = 1.00
            crash_state["crash_point"] = gen_crash_point()
        elif ph == "flying":
            dt = now - crash_state["start_ts"]
            m = round(1.0 + 0.06 * dt + 0.013 * (dt ** 2), 2)
            if m >= crash_state["crash_point"]:
                crash_state["mult"] = crash_state["crash_point"]
                crash_state["phase"] = "crashed"
                crash_state["start_ts"] = now + 3.5
                crash_state["history"].insert(0, crash_state["crash_point"])
                crash_state["history"] = crash_state["history"][:12]
            else:
                crash_state["mult"] = m
        elif ph == "crashed" and now >= crash_state["start_ts"]:
            crash_state["round_id"] += 1
            crash_state["phase"] = "waiting"
            crash_state["start_ts"] = now + 8.0
            crash_state["mult"] = 1.00
            crash_state["bets"] = {}
        await asyncio.sleep(0.1)

class StateReq(BaseModel):
    user_id: int = 0
    username: str = ""

class BetReq(BaseModel):
    user_id: int
    username: str = ""
    delta: float

class CrashBetReq(BaseModel):
    user_id: int
    username: str = ""
    bet: float

class CrashCashReq(BaseModel):
    user_id: int

class InvoiceReq(BaseModel):
    user_id: int
    stars: int

class WithdrawReq(BaseModel):
    user_id: int
    username: str = ""
    stars: float
    wallet: str

@app.post("/api/state")
async def get_state(req: StateReq):
    now = time.time()
    bal, td = 0.0, 0.0
    if req.user_id > 0:
        online_pings[req.user_id] = now
        u = get_user(req.user_id, req.username)
        bal, td = u["balance"], u["total_deposited"]
    for k in [k for k, v in online_pings.items() if now - v >= 15]:
        del online_pings[k]
    rem = max(0.0, round(crash_state["start_ts"] - now, 1)) if crash_state["phase"] == "waiting" else 0.0
    return {
        "balance": bal,
        "total_deposited": td,
        "online": max(1, len(online_pings)),
        "crash": {
            "round_id": crash_state["round_id"],
            "phase": crash_state["phase"],
            "mult": crash_state["mult"],
            "remaining": rem,
            "history": crash_state["history"],
            "bets": list(crash_state["bets"].values())
        }
    }

@app.post("/api/bet")
async def apply_bet(req: BetReq):
    if req.user_id <= 0:
        raise HTTPException(400, "No user")
    u = get_user(req.user_id, req.username)
    if req.delta < 0 and u["balance"] + req.delta < -0.001:
        raise HTTPException(400, "Not enough balance")
    bal, td = add_balance(req.user_id, req.delta, False)
    return {"balance": bal, "total_deposited": td}

@app.post("/api/crash/bet")
async def crash_bet(req: CrashBetReq):
    if req.user_id <= 0 or req.bet < 1:
        raise HTTPException(400, "Invalid bet")
    if crash_state["phase"] != "waiting":
        raise HTTPException(400, "Round already started")
    uid_str = str(req.user_id)
    if uid_str in crash_state["bets"]:
        raise HTTPException(400, "Already bet")
    u = get_user(req.user_id, req.username)
    if u["balance"] < req.bet:
        raise HTTPException(400, "Not enough stars")
    bal, td = add_balance(req.user_id, -req.bet, False)
    name = req.username.lstrip("@") or f"ID-{str(req.user_id)[-4:]}"
    crash_state["bets"][uid_str] = {"user_id": req.user_id, "name": name, "bet": round(req.bet, 2), "cash_mult": None, "win": None}
    return {"balance": bal, "total_deposited": td}

@app.post("/api/crash/cash")
async def crash_cash(req: CrashCashReq):
    if crash_state["phase"] != "flying":
        raise HTTPException(400, "Not flying")
    uid_str = str(req.user_id)
    b = crash_state["bets"].get(uid_str)
    if not b or b["cash_mult"] is not None:
        raise HTTPException(400, "Nothing to cash")
    m = crash_state["mult"]
    win = round(b["bet"] * m, 2)
    b["cash_mult"] = m
    b["win"] = win
    bal, td = add_balance(req.user_id, win, False)
    return {"balance": bal, "total_deposited": td, "mult": m, "win": win}

@app.post("/api/stars/invoice")
async def create_stars_invoice(req: InvoiceReq):
    if req.stars < 1 or req.user_id <= 0:
        raise HTTPException(400, "Invalid amount")
    payload = f"stars_{req.user_id}_{int(datetime.now().timestamp())}"
    link = await bot.create_invoice_link(
        title=f"ZetUP: {req.stars} Stars",
        description="Пополнение ZetUP (+5%)",
        payload=payload,
        currency="XTR",
        prices=[types.LabeledPrice(label=f"{req.stars} Stars", amount=req.stars)]
    )
    return {"invoice_link": link}

@app.post("/api/withdraw")
async def withdraw(req: WithdrawReq):
    u = get_user(req.user_id, req.username)
    if u["total_deposited"] < 500 or u["balance"] < req.stars or req.stars < 1500:
        raise HTTPException(400, "Not eligible")
    bal, _ = add_balance(req.user_id, -req.stars, False)
    await bot.send_message(ADMIN_ID, f"Вывод: {u['user_id']} (@{req.username}) | {req.stars} ⭐ | Кошелёк: {req.wallet}")
    return {"ok": True, "balance": bal}

@dp.pre_checkout_query()
async def pre_checkout(q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(m: types.Message):
    p = m.successful_payment
    uid = int(p.invoice_payload.split("_")[1])
    stars_paid = p.total_amount
    credit = round(stars_paid * 1.05, 2)
    add_balance(uid, credit, True)
    c = get_db()
    c.execute("INSERT INTO payments (user_id, method, amount_raw, stars_credited, status, payload) VALUES (?, 'stars', ?, ?, 'paid', ?)", (uid, stars_paid, credit, p.invoice_payload))
    c.commit()
    c.close()
    await bot.send_message(ADMIN_ID, f"Stars +5%: {stars_paid} -> {credit} ⭐ (ID {uid})")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(crash_loop())
    asyncio.create_task(dp.start_polling(bot))
