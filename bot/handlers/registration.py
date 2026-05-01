"""
handlers/registration.py — Ro'yxatdan o'tish
username + password bilan (sayt login uchun ham shu ma'lumotlar ishlatiladi)
"""

import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from keyboards import main_menu_keyboard

router = Router()


class Reg(StatesGroup):
    first_name   = State()
    last_name    = State()
    age          = State()
    phone        = State()
    grade        = State()
    username     = State()
    password     = State()
    confirm_pass = State()


def cancel_kb():
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bekor qilish", callback_data="cancel_reg")
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id# type: ignore
    if db.is_registered(uid):
        user = db.get_user(uid)

        # Kunlik bonus tekshiruvi
        bonus = db.claim_daily_bonus(uid)
        bonus_text = ""
        if bonus["given"]:
            bonus_text = f"\n\n🎁 <b>Kunlik bonus: +{bonus['amount']} 🪙</b> olindi!"

        await message.answer(
            f"👋 Xush kelibsiz, <b>{user['first_name']}</b>!{bonus_text}\n\n"
            f"🪙 Coinlar: <b>{db.get_user_coins(uid)}</b>\n"
            f"Menyudan tanlang:",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    await message.answer(
        "🇺🇿 <b>O'zbekiston Ta'lim Botiga Xush Kelibsiz!</b>\n\n"
        "📚 Yodgorliklarni o'rganing\n"
        "📝 Quiz ishlang va coin yig'ing\n"
        "🤖 AI bilan suhbat quring\n"
        "🌐 Saytda obuna oling\n\n"
        "━━━━━━━━━━━━━━━\n"
        "👤 <b>Ismingizni kiriting:</b>",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await state.set_state(Reg.first_name)


@router.callback_query(F.data == "cancel_reg")
async def cancel_reg(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(# type: ignore
        "❌ Bekor qilindi. Qaytadan boshlash uchun /start yozing."
    )


@router.message(Reg.first_name)
async def step_first_name(message: Message, state: FSMContext):
    name = message.text.strip()# type: ignore
    if len(name) < 2:
        await message.answer("⚠️ Ism kamida 2 harf bo'lishi kerak.")
        return
    await state.update_data(first_name=name)
    await message.answer(f"✅ Ism: <b>{name}</b>\n\n👤 <b>Familiyangiz:</b>",
                         parse_mode="HTML")
    await state.set_state(Reg.last_name)


@router.message(Reg.last_name)
async def step_last_name(message: Message, state: FSMContext):
    name = message.text.strip()# type: ignore
    if len(name) < 2:
        await message.answer("⚠️ Familiya kamida 2 harf bo'lishi kerak.")
        return
    await state.update_data(last_name=name)
    await message.answer(f"✅ Familiya: <b>{name}</b>\n\n🔢 <b>Yoshingiz (masalan: 13):</b>",
                         parse_mode="HTML")
    await state.set_state(Reg.age)


@router.message(Reg.age)
async def step_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())# type: ignore
        assert 6 <= age <= 18
    except:
        await message.answer("⚠️ Yosh 6-18 oralig'ida bo'lishi kerak.")
        return
    await state.update_data(age=age)
    await message.answer(f"✅ Yosh: <b>{age}</b>\n\n📱 <b>Telefon raqamingiz:</b>\n"
                         "Misol: +998901234567", parse_mode="HTML")
    await state.set_state(Reg.phone)


@router.message(Reg.phone)
async def step_phone(message: Message, state: FSMContext):
    phone = message.text.strip()# type: ignore
    clean = phone.replace('+','').replace(' ','').replace('-','')
    if not clean.isdigit() or len(clean) < 9:
        await message.answer("⚠️ Telefon noto'g'ri. Misol: +998901234567")
        return
    await state.update_data(phone=phone)
    await message.answer(f"✅ Telefon: <b>{phone}</b>\n\n"
                         "🏫 <b>Nechinchi sinfda o'qiysiz? (1-11):</b>",
                         parse_mode="HTML")
    await state.set_state(Reg.grade)


@router.message(Reg.grade)
async def step_grade(message: Message, state: FSMContext):
    try:
        grade = int(message.text.strip())# type: ignore
        assert 1 <= grade <= 11
    except:
        await message.answer("⚠️ Sinf 1-11 oralig'ida bo'lishi kerak.")
        return
    await state.update_data(grade=grade)
    await message.answer(
        f"✅ Sinf: <b>{grade}-sinf</b>\n\n"
        "🔑 <b>Foydalanuvchi nomi (username) o'ylab toping:</b>\n\n"
        "Bu nom saytga kirish uchun ishlatiladi.\n"
        "<i>Faqat lotin harflari, raqamlar va _ belgisi. "
        "Kamida 4 ta belgi.</i>",
        parse_mode="HTML"
    )
    await state.set_state(Reg.username)


@router.message(Reg.username)
async def step_username(message: Message, state: FSMContext):
    uname = message.text.strip().lower()# type: ignore
    if not re.match(r'^[a-z0-9_]{4,20}$', uname):
        await message.answer(
            "⚠️ Username noto'g'ri!\n"
            "• Faqat lotin harflari (a-z), raqamlar, _ belgisi\n"
            "• 4-20 ta belgi\n"
            "• Masalan: ali_2025"
        )
        return
    if db.is_username_taken(uname):
        await message.answer(f"⚠️ <b>@{uname}</b> allaqachon band. Boshqa nom tanlang.",
                             parse_mode="HTML")
        return
    await state.update_data(username=uname)
    await message.answer(
        f"✅ Username: <b>@{uname}</b>\n\n"
        "🔒 <b>Parol o'ylab toping:</b>\n\n"
        "<i>Kamida 6 ta belgi. Raqam va harf aralashtirilsa yaxshi.</i>",
        parse_mode="HTML"
    )
    await state.set_state(Reg.password)


@router.message(Reg.password)
async def step_password(message: Message, state: FSMContext):
    pw = message.text.strip()# type: ignore
    # Xabarni o'chirish (xavfsizlik uchun)
    try:
        await message.delete()
    except:
        pass
    if len(pw) < 6:
        await message.answer("⚠️ Parol kamida 6 ta belgi bo'lishi kerak.")
        return
    await state.update_data(password=pw)
    await message.answer(
        "🔒 <b>Parolni tasdiqlang (qayta kiriting):</b>",
        parse_mode="HTML"
    )
    await state.set_state(Reg.confirm_pass)


@router.message(Reg.confirm_pass)
async def step_confirm(message: Message, state: FSMContext):
    pw2 = message.text.strip()# type: ignore
    try:
        await message.delete()
    except:
        pass

    data = await state.get_data()
    if pw2 != data['password']:
        await message.answer("⚠️ Parollar mos kelmadi! Qayta kiriting:")
        await state.set_state(Reg.password)
        return

    # Ro'yxatdan o'tkazish
    db.register_user(
        user_id     = message.from_user.id,# type: ignore
        tg_username = message.from_user.username or "",# type: ignore
        first_name  = data['first_name'],
        last_name   = data['last_name'],
        age         = data['age'],
        phone       = data['phone'],
        school_grade= data['grade'],
        username    = data['username'],
        password    = data['password'],
    )
    await state.clear()

    # Birinchi kunlik bonus
    bonus = db.claim_daily_bonus(message.from_user.id)# type: ignore

    await message.answer(
        f"🎉 <b>Tabriklaymiz! Ro'yxatdan o'tdingiz!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 {data['first_name']} {data['last_name']}\n"
        f"🏫 {data['grade']}-sinf | 🎂 {data['age']} yosh\n\n"
        f"🔑 <b>Saytga kirish ma'lumotlari:</b>\n"
        f"   Username: <code>{data['username']}</code>\n"
        f"   Parol: <tg-spoiler>Kiritgan parolingiz</tg-spoiler>\n\n"
        f"🎁 <b>Xush kelibsiz bonusi: +{bonus['amount']} 🪙</b>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 Quiz ishlang va coin yig'ing!\n"
        f"🌐 Saytda obuna oling!",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
