"""
web/main.py — FastAPI sayt (Render.com uchun)
Login: Telegram widget EAS, username + password bilan
"""

import sys, os, hashlib, sqlite3
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Loyiha ildiz papkasini Python yo'liga qo'shish
import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Endi bu import xato bermaydi
from shared_config import WEB_SECRET_KEY, BOT_USERNAME, SITE_URL, DB_NAME, SUBSCRIPTION_PLANS

app = FastAPI(title="O'zbekiston Ta'lim")
app.add_middleware(SessionMiddleware, secret_key=WEB_SECRET_KEY,
                   max_age=60*60*24*30)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.globals["BOT_USERNAME"] = BOT_USERNAME
templates.env.globals["SITE_URL"]     = SITE_URL


# ===================== DB =====================

def db_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "bot", "uzbekistan_bot.db")
    return path


def db_conn():
    conn = sqlite3.connect(db_path())
    print(f"DEBUG: Bazaga ulanish: {db_path()}")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            coin_spent INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup():
    init_db()


# ===================== HELPERS =====================

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def get_uid(request: Request) -> Optional[int]:
    return request.session.get("user_id")


def get_user(user_id: int):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    conn.close()
    return u


def get_user_by_username(username: str):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username.lower(),))
    u = c.fetchone()
    conn.close()
    return u


def get_active_sub(user_id: int):
    today = str(date.today())
    conn  = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM subscriptions
        WHERE user_id=? AND is_active=1 AND expires_at>=?
        ORDER BY expires_at DESC LIMIT 1
    """, (user_id, today))
    sub = c.fetchone()
    conn.close()
    return sub


# ===================== SAHIFALAR =====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if get_uid(request):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "plans": SUBSCRIPTION_PLANS,
        "error": request.query_params.get("error", ""),
    })


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Username + password bilan kirish."""
    user = get_user_by_username(username.strip().lower())

    if not user:
        return RedirectResponse("/?error=notfound", status_code=303)

    if user["password_hash"] != hash_password(password):
        return RedirectResponse("/?error=wrongpass", status_code=303)

    request.session["user_id"]    = user["user_id"]
    request.session["first_name"] = user["first_name"]
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Ro'yxatdan o'tish — botda /start yuboring deb yo'naltiradi."""
    return templates.TemplateResponse("register.html", {
        "request": request,
        "bot_username": BOT_USERNAME,
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    uid = get_uid(request)
    if not uid:
        return RedirectResponse("/")
    user = get_user(uid)
    if not user:
        request.session.clear()
        return RedirectResponse("/")
    active_sub  = get_active_sub(uid)
    active_plan = SUBSCRIPTION_PLANS.get(active_sub["plan_id"]) if active_sub else None
    return templates.TemplateResponse("dashboard.html", {
        "request":     request,
        "user":        user,
        "active_sub":  active_sub,
        "active_plan": active_plan,
        "plans":       SUBSCRIPTION_PLANS,
    })


@app.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    uid = get_uid(request)
    if not uid:
        return RedirectResponse("/")
    user       = get_user(uid)
    active_sub = get_active_sub(uid)
    return templates.TemplateResponse("plans.html", {
        "request":    request,
        "user":       user,
        "active_sub": active_sub,
        "plans":      SUBSCRIPTION_PLANS,
    })


@app.post("/buy/{plan_id}")
async def buy_plan(plan_id: str, request: Request):
    uid = get_uid(request)
    if not uid:
        return RedirectResponse("/", status_code=303)
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        return RedirectResponse("/plans?error=notfound", status_code=303)
    user = get_user(uid)
    cost = plan["narx_coin"]
    if user["coins"] < cost:
        return RedirectResponse(
            f"/plans?error=nocoin&need={cost}&have={user['coins']}",
            status_code=303
        )
    conn = db_conn()
    c = conn.cursor()
    c.execute("UPDATE subscriptions SET is_active=0 WHERE user_id=? AND is_active=1", (uid,))
    c.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (cost, uid))
    started = str(date.today())
    expires = str(date.today() + timedelta(days=plan["muddat_kun"]))
    c.execute("""
        INSERT INTO subscriptions (user_id, plan_id, started_at, expires_at, coin_spent)
        VALUES (?,?,?,?,?)
    """, (uid, plan_id, started, expires, cost))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/dashboard?success={plan_id}", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/subscription/{user_id}")
async def api_sub(user_id: int, request: Request):
    from fastapi import HTTPException
    from shared_config import BOT_TOKEN
    if request.headers.get("X-API-Key","") != BOT_TOKEN[:20]:
        raise HTTPException(401)
    sub = get_active_sub(user_id)
    if sub:
        plan = SUBSCRIPTION_PLANS.get(sub["plan_id"], {})
        return {
            "has_subscription": True,
            "plan_id":    sub["plan_id"],
            "plan_name":  plan.get("nomi",""),
            "expires_at": sub["expires_at"],
            "emoji":      plan.get("emoji",""),
        }
    return {"has_subscription": False}
