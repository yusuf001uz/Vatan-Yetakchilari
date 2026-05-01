"""
handlers/ai_chat.py — Groq AI bilan suhbat
Model: llama-3.3-70b-versatile
"""
import html
import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import GROQ_API_KEY, AI_CHAT_COST
from places_data import PLACES

router = Router()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
AI_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


async def groq(system: str, messages: list, max_tokens=500) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": AI_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "messages": [{"role": "system", "content": system}] + messages,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(GROQ_URL, headers=headers, json=body,
                              timeout=aiohttp.ClientTimeout(total=25)) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["choices"][0]["message"]["content"]
                return f"❌ API xatosi ({r.status})"
    except Exception as e:
        return f"❌ Xato: {str(e)[:80]}"


class ChatState(StatesGroup):
    active = State()


def exit_kb():
    b = InlineKeyboardBuilder()
    b.button(text="❌ Suhbatni tugatish", callback_data="ai_exit")
    return b.as_markup()


@router.message(F.text == "🤖 AI Suhbat")
async def cmd_ai(message: Message, state: FSMContext):
    if not db.is_registered(message.from_user.id):# type: ignore
        await message.answer("❌ Avval /start yozing!")
        return
    coins = db.get_user_coins(message.from_user.id)# type: ignore
    await message.answer(
        "🤖 <b>AI Suhbat — Groq AI</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "O'zbekiston tarixi, yodgorliklar, geografiya yoki\n"
        "istalgan mavzu bo'yicha savol bering!\n\n"
        f"💰 Har bir savol: <b>{AI_CHAT_COST} 🪙</b>\n"
        f"💳 Sizda: <b>{coins} 🪙</b>\n\n"
        "<i>Savolingizni yozing...</i>",
        reply_markup=exit_kb(),
        parse_mode="HTML"
    )
    await state.set_state(ChatState.active)
    await state.update_data(history=[])


@router.callback_query(F.data == "ai_exit")
async def ai_exit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✅ AI suhbatdan chiqdingiz.")# type: ignore


@router.message(ChatState.active)
async def ai_reply(message: Message, state: FSMContext):
    uid  = message.from_user.id# type: ignore
    text = (message.text or "").strip()
    if not text:
        return

    # Coin tekshiruvi
    if AI_CHAT_COST > 0:
        if db.get_user_coins(uid) < AI_CHAT_COST:
            await message.answer(
                f"❌ Coin yetarli emas!\n"
                f"Kerak: {AI_CHAT_COST} 🪙 | Sizda: {db.get_user_coins(uid)} 🪙\n"
                "Quiz ishlang va coin yig'ing! 📝",
                parse_mode="HTML"
            )
            return
        db.deduct_coins(uid, AI_CHAT_COST)

    thinking = await message.answer("⏳ <i>AI o'ylayapti...</i>", parse_mode="HTML")

    data    = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": text})

    system = (
        "Siz O'zbekiston Ta'lim botining AI yordamchisisiz. "
        "Foydalanuvchi — o'zbek maktab o'quvchisi. "
        "O'zbek tilida, qisqa (3-5 jumla), tushunarli va qiziqarli javob bering. "
        "Emoji ishlating. Agar bilmasangiz, halol aytib bering."
    )

    ai_text = await groq(system, history[-8:])
    history.append({"role": "assistant", "content": ai_text})
    safe_ai_text = html.escape(ai_text)
    await state.update_data(history=history[-12:])

    await thinking.delete()
    coins_left = db.get_user_coins(uid)

    await message.answer(
        f"🤖 {safe_ai_text}\n\n"
        f"<i>💳 {coins_left} 🪙 qoldi | Yana savol yoki ❌ chiqish</i>",
        reply_markup=exit_kb(),
        parse_mode="HTML"
    )


# ===================== AI IZOHLA (joy uchun, bepul) =====================

@router.callback_query(F.data.startswith("ai_explain_"))
async def ai_explain(callback: CallbackQuery):
    place_id = callback.data.replace("ai_explain_", "")# type: ignore
    place    = PLACES.get(place_id)
    if not place:
        await callback.answer("❌ Joy topilmadi!", show_alert=True)
        return

    await callback.answer("⏳ AI tayyorlanmoqda...")
    thinking = await callback.message.answer(# type: ignore
        f"🧠 <i>AI {place['nomi']} haqida tushuntiryapti...</i>",
        parse_mode="HTML"
    )

    system = (
        "Siz O'zbekiston tarixi bo'yicha ekspertsiz. "
        "O'zbek tilida, maktab o'quvchisiga tushunarli, "
        "qiziqarli va mazmunli tushuntirish bering. "
        "5-7 jumla, emoji ishlating."
    )
    prompt = (
        f"'{place['nomi']}' haqida qiziqarli tushuntirish ber. "
        f"Joylashuvi: {place['viloyat']}. "
        f"Qisqa ma'lumot: {place['tavsif'][:250]}. "
        f"O'quvchi uchun 3-4 ta muhim faktni ajratib ko'rsat."
    )

    ai_text = await groq(system, [{"role": "user", "content": prompt}], max_tokens=400)
    await thinking.delete()

    b = InlineKeyboardBuilder()
    b.button(text="📝 Quiz ishlash",    callback_data=f"start_quiz_{place_id}")
    b.button(text="⬅️ Orqaga",          callback_data="back_to_learn")
    b.adjust(1)

    await callback.message.answer(# type: ignore
        f"🧠 <b>AI Tushuntirish: {place['emoji']} {place['nomi']}</b>\n"
        f"━━━━━━━━━━━━━━━\n\n{ai_text}",
        reply_markup=b.as_markup(),
        parse_mode="HTML"
    )
