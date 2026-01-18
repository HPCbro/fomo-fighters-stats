# /root/ff/handlers/core.py
import json
import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timezone

from api import FomoAPI
from database import db_get_user, db_add_user
from keyboards import main_kb, profile_kb, back_kb 
from config import START_PORT

router = Router()

class Form(StatesGroup):
    waiting_for_init_data = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    user = db_get_user(uid)
    if user:
        # Приветствие берет имя из нашей БД, которое мы сохранили при регистрации
        await message.answer(f"👋 С возвращением, <b>{user['username']}</b>!\nТвой прокси порт: `{user['proxy_port']}`", parse_mode="HTML", reply_markup=main_kb(uid))
    else:
        text = "👋 <b>Привет!</b>\n\nЯ бот для автоматизации игры Fomo Fighters.\n\n👇 Нажми кнопку, чтобы подключить аккаунт."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")]])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "add_account")
async def ask_init_data(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ <b>Отправь мне свою initData.</b>\n\n(Начинается с <code>query_id=</code> или <code>user=</code>)", parse_mode="HTML")
    await state.set_state(Form.waiting_for_init_data)

@router.message(Form.waiting_for_init_data)
async def process_init_data(message: types.Message, state: FSMContext):
    data = message.text.strip(); uid = message.from_user.id
    if "user=" not in data and "query_id=" not in data: await message.answer("❌ Неверный формат initData."); return
    
    # Теперь мы используем get_full_data() для регистрации, он надежнее
    api = FomoAPI(data, START_PORT) 
    res = await api.get_full_data() 

    if res.get("success") and isinstance(res.get("data"), dict):
        profile = res.get('data', {}).get('profile', {})
        username = profile.get('publicName', 'Unknown')
        
        port = db_add_user(uid, data, username, START_PORT)
        await message.answer(f"✅ <b>Аккаунт добавлен!</b>...", parse_mode="HTML", reply_markup=main_kb(uid))
        await state.clear()
    else:
        await message.answer(f"❌ Ошибка авторизации: {res.get('error', 'Неизвестная ошибка')}", reply_markup=back_kb())

@router.callback_query(F.data == "main_menu")
async def menu_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_kb(callback.from_user.id))

@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    uid = callback.from_user.id; user = db_get_user(uid)
    if not user: return

    await callback.message.edit_text("⏳ Получаю данные...")
    api = FomoAPI(user['init_data'], user['proxy_port'])
    
    # Этот вызов теперь возвращает склеенный результат
    res = await api.get_full_data()
    
    if not res.get("success"):
        err = res.get('error')
        if err == "EXPIRED_TOKEN":
            await callback.message.edit_text("🚨 <b>InitData устарела!</b>\nПожалуйста, обновите данные через 'Добавить аккаунт'.", parse_mode="HTML")
        else:
            await callback.message.edit_text(f"❌ Ошибка: {err}", reply_markup=main_kb(uid))
        return
    
    data = res.get('data', {})
    hero = data.get('hero', {})
    profile = data.get('profile', {})
    res_val = hero.get('resources', {})
    
    text = (f"👤 <b>{profile.get('publicName', 'No Name')}</b> | LVL {hero.get('level')} | {hero.get('race', '').upper()}\n\n"
            f"💰 <b>Ресурсы:</b>\n"
            f"🍖 Еда: {int(res_val.get('food', {}).get('value', 0)):,}\n"
            f"🌲 Дерево: {int(res_val.get('wood', {}).get('value', 0)):,}\n"
            f"🪨 Камень: {int(res_val.get('stone', {}).get('value', 0)):,}\n"
            f"💎 Гемы: {int(res_val.get('gem', {}).get('value', 0)):,}\n").replace(",", " ")

    # Этот блок теперь должен сработать, так как troops придут из /after
    troops_in_town = data.get("troops", {})
    if troops_in_town and isinstance(troops_in_town, dict):
        text += "\n🛡️ <b>Войска в городе:</b>\n"
        sorted_troops = sorted(troops_in_town.items(), key=lambda item: item[0])
        for key, count in sorted_troops:
            if count > 0:
                short_name = re.sub(r'^(frog|cat|dog)_', '', key)
                text += f"<code>- {short_name:<15}: {count:,}</code>\n".replace(",", " ")
    
    # Активные процессы
    now = datetime.now(timezone.utc); active_processes = []
    training_tasks = data.get("tTroops", [])
    # ... (остальной код отображения процессов без изменений)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=profile_kb())

@router.callback_query(F.data == "show_troops")
async def show_troops_callback(callback: types.CallbackQuery):
    """Новый обработчик для показа войск"""
    uid = callback.from_user.id
    user = db_get_user(uid)
    if not user: return
    
    await callback.message.edit_text("⏳ Загружаю список войск...")
    api = FomoAPI(user['init_data'], user['proxy_port'])
    res = await api.get_full_data()
    
    if not res.get("success") or not isinstance(res.get("data"), dict):
        await callback.message.edit_text("❌ Ошибка.", reply_markup=main_kb(uid)); return

    data = res.get('data', {})
    troops_in_town = data.get("troops", {})
    
    text = "🛡️ <b>Войска в городе:</b>\n"
    
    if not troops_in_town:
        text += "<i>Войск нет (или сервер не прислал данные).</i>"
    else:
        # Универсальная обработка
        if isinstance(troops_in_town, list):
            parsed_troops = {}
            for item in troops_in_town:
                key = item.get("troopKey") or item.get("key")
                count = item.get("count", 0)
                if key: parsed_troops[key] = parsed_troops.get(key, 0) + count
            troops_in_town = parsed_troops
        
        if isinstance(troops_in_town, dict) and troops_in_town:
            sorted_troops = sorted(troops_in_town.items(), key=lambda item: item[0])
            for key, count in sorted_troops:
                if count > 0:
                    short_name = re.sub(r'^(frog|cat|dog)_', '', key)
                    text += f"<code>- {short_name:<15}: {count:,}</code>\n".replace(",", " ")
        else:
            text += "<i>Список войск пуст.</i>"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb("profile"))