# /root/ff/handlers/recruit.py
import json
import asyncio
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from api import FomoAPI
from database import db_get_user, db_update_config, db_set_active
from keyboards import main_kb, back_kb
from config import active_tasks

router = Router()

class RecruitForm(StatesGroup):
    setting_count = State()

# Конфигурация типов войск
# Ключ API здания -> (API суффикс юнита, Русское название)
BUILDINGS_MAP = {
    "barracks":       ("barracks", "⚔️ Пехота"),
    "archery_range":  ("archer",   "🏹 Луки"),
    "stable":         ("stable",   "🐴 Кони"),
    "scout_camp":     ("scout",    "👁️ Разведка"),
    "siege_workshop": ("siege",    "💣 Осада")
}

# Доступные уровни (Tiers)
AVAILABLE_TIERS = [10, 30, 50]

@router.callback_query(F.data == "recruit_menu")
async def recruit_menu(callback: types.CallbackQuery):
    uid = callback.from_user.id; user = db_get_user(uid)
    is_running = user and user.get('is_recruit_active') == 1
    
    status_emoji = "🟢" if is_running else "🔴"
    action_text = "Остановить" if is_running else "Запустить"
    action_data = "stop_recruit" if is_running else "start_recruit"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{status_emoji} {action_text}", callback_data=action_data)],
        [InlineKeyboardButton(text="⚙️ Настроить войска", callback_data="setup_recruit")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]])
    
    await callback.message.edit_text("🎯 <b>Управление авто-наймом:</b>", parse_mode="HTML", reply_markup=kb)

# --- ШАГ 1: Выбор типа войск ---
@router.callback_query(F.data == "setup_recruit")
async def setup_recruit(callback: types.CallbackQuery):
    uid = callback.from_user.id; user = db_get_user(uid);
    
    # Получаем актуальные лимиты с сервера
    api = FomoAPI(user['init_data'], user['proxy_port'])
    res = await api.get_full_data()
    if not res.get('success'): 
        return await callback.answer("Ошибка получения данных", show_alert=True)
    
    data = res['data']
    race = data['hero']['race']
    props = data['hero'].get('propsCompiled') or data['hero']['props']['skills']
    
    buttons = []
    
    for build_key, (unit_sfx, ru_name) in BUILDINGS_MAP.items():
        # Пытаемся найти лимит обучения для этого здания
        cap_key = "trainingCapacity" + "".join([p.capitalize() for p in build_key.split('_')])
        limit = props.get(cap_key, 0)
        
        if limit == 0: # Fallback
             limit = props.get(f"trainingCapacity{unit_sfx.capitalize()}", 0)
        
        # Передаем: build_key, limit, race
        buttons.append([InlineKeyboardButton(
            text=f"{ru_name} (Лимит: {limit})", 
            callback_data=f"sel_cat:{build_key}:{limit}:{race}"
        )])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="recruit_menu")])
    await callback.message.edit_text(f"⚙️ <b>Выберите тип войск ({race.upper()}):</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# --- ШАГ 2: Выбор Тира (Tier) ---
@router.callback_query(F.data.startswith("sel_cat:"))
async def select_tier_category(callback: types.CallbackQuery):
    # Разбираем данные из кнопки
    _, build_key, limit, race = callback.data.split(":")
    unit_sfx, ru_name = BUILDINGS_MAP[build_key]
    
    uid = callback.from_user.id
    user = db_get_user(uid)
    config = json.loads(user.get('config', '{}'))
    
    buttons = []
    
    for tier in AVAILABLE_TIERS:
        # Формируем ключ: frog_archer_10
        unit_key = f"{race}_{unit_sfx}_{tier}"
        current_target = config.get(unit_key, 0)
        
        status = f"✅ {current_target}" if current_target > 0 else "❌ Откл"
        
        buttons.append([InlineKeyboardButton(
            text=f"Tier {int(tier/10)} | {status}", 
            callback_data=f"set_unit:{unit_key}:{limit}"
        )])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад к типам", callback_data="setup_recruit")])
    
    await callback.message.edit_text(
        f"⚙️ <b>Настройка: {ru_name}</b>\nMax лимит очереди: {limit}\n\nВыберите уровень войск:", 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# --- ШАГ 3: Установка количества ---
@router.callback_query(F.data.startswith("set_unit:"))
async def set_unit_count(callback: types.CallbackQuery, state: FSMContext):
    _, unit_key, limit = callback.data.split(":")
    await state.update_data(unit_key=unit_key, limit=limit)
    
    # Красивое название для заголовка
    parts = unit_key.split('_') # frog, archer, 10
    tier = int(parts[-1]) // 10
    name = parts[1].upper()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"На все ({limit})", callback_data=f"save_unit:{limit}")],
        [InlineKeyboardButton(text="Отключить (0)", callback_data="save_unit:0")],
        [InlineKeyboardButton(text="Ввести вручную", callback_data="manual_input")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="setup_recruit")] # Возврат в начало
    ])
    await callback.message.edit_text(f"Сколько нанимать <b>{name} (T{tier})</b>?", parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "manual_input")
async def manual_input_ask(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⌨️ Введите число для авто-найма:")
    await state.set_state(RecruitForm.setting_count)

@router.message(RecruitForm.setting_count)
async def manual_input_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): 
        await message.answer("Нужно число!"); return
        
    count = int(message.text)
    data = await state.get_data()
    uid = message.from_user.id
    
    user = db_get_user(uid)
    config = json.loads(user['config'])
    config[data['unit_key']] = count
    db_update_config(uid, config)
    
    await message.answer(f"✅ Цель установлена: {count}", reply_markup=main_kb(uid))
    await state.clear()

@router.callback_query(F.data.startswith("save_unit:"))
async def save_unit_btn(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split(":")[1])
    data = await state.get_data()
    uid = callback.from_user.id
    
    user = db_get_user(uid)
    config = json.loads(user['config'])
    config[data['unit_key']] = count
    db_update_config(uid, config)
    
    await callback.message.edit_text(f"✅ Сохранено.", reply_markup=main_kb(uid))
    await state.clear()

# --- ВОРКЕР (Worker) ---
async def recruit_worker(user_id, bot):
    print(f"🚀 Recruit worker started for {user_id}")
    while True:
        user = db_get_user(user_id)
        if not user or user.get('is_recruit_active') == 0:
            print(f"🛑 Recruit worker stopped for {user_id}"); break
            
        config = json.loads(user.get('config', '{}'))
        if not config or all(v == 0 for v in config.values()): 
            await asyncio.sleep(60); continue
        
        api = FomoAPI(user['init_data'], user['proxy_port'])
        res = await api.get_full_data()
        
        # Обработка истекшего токена
        if not res.get("success"):
            error_msg = res.get('error')
            print(f"User {user_id} [Recruit]: Error - {error_msg}")
            if error_msg == "EXPIRED_TOKEN":
                db_set_active(user_id, "recruit", False)
                try:
                    await bot.send_message(user_id, "🚨 <b>Авто-найм остановлен.</b>\ninitData истекла.", parse_mode="HTML")
                except: pass
                break
            await asyncio.sleep(60); continue

        active_timers = {t['troopKey'] for t in res['data'].get("tTroops", [])}
        
        # Проходимся по конфигу и покупаем всё, что настроено
        # Теперь здесь могут быть ключи разных уровней (frog_barracks_10, frog_barracks_30 и т.д.)
        for u_key, count in config.items():
            if count > 0 and u_key not in active_timers:
                print(f"User {user_id} [Recruit]: Buying {u_key} x{count}")
                buy_res = await api.buy_troops(u_key, count)
                
                # Небольшой лог в консоль для отладки
                if not buy_res.get('success'):
                    print(f"   -> Failed: {buy_res.get('error')}")
                
                await asyncio.sleep(2) # Задержка между покупками разных типов
                
        await asyncio.sleep(60)

# --- Start/Stop Handlers ---
@router.callback_query(F.data == "start_recruit")
async def start_recruit_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id; user = db_get_user(uid)
    config = json.loads(user.get('config', '{}'))
    if not config or all(v == 0 for v in config.values()):
        await callback.answer("Сначала настройте войска!", show_alert=True); return
        
    db_set_active(uid, "recruit", True)
    
    if uid not in active_tasks or 'recruit' not in active_tasks[uid] or active_tasks[uid]['recruit'].done():
        if uid not in active_tasks: active_tasks[uid] = {}
        active_tasks[uid]['recruit'] = asyncio.create_task(recruit_worker(uid, callback.bot))
        
    await callback.message.edit_reply_markup(reply_markup=main_kb(uid))
    await callback.answer("Авто-найм запущен ✅")

@router.callback_query(F.data == "stop_recruit")
async def stop_recruit_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    db_set_active(uid, "recruit", False)
    await callback.message.edit_reply_markup(reply_markup=main_kb(uid))
    await callback.answer("Авто-найм остановлен 🔴")