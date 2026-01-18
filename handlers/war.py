# /root/ff/handlers/war.py
import asyncio
import re
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from api import FomoAPI
from database import db_get_all_users, db_get_user
from config import ADMIN_IDS

router = Router()

class WarState(StatesGroup):
    selecting_war = State()
    selecting_target = State() # Выбор игрока (или всех)
    selecting_percent = State() # Выбор процента

# --- Шаг 1: Получение списка войн ---
@router.callback_query(F.data == "war_menu")
async def war_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Только для админов!", show_alert=True); return

    uid = callback.from_user.id
    user = db_get_user(uid)
    if not user: await callback.answer("Сначала добавь себя в бота", show_alert=True); return

    await callback.message.edit_text("⏳ Получаю список активных войн...")
    
    api = FomoAPI(user['init_data'], user['proxy_port'])
    res = await api.get_full_data()
    
    if not res.get("success"):
        await callback.message.edit_text(f"❌ Ошибка API: {res.get('error')}"); return

    data = res.get('data', {})
    wars = data.get('tWars', [])
    
    if not wars:
        await callback.message.edit_text("🕊️ <b>Сейчас нет активных войн.</b>", parse_mode="HTML")
        return

    kb = []
    for w in wars:
        w_id = w['id']
        attacker = w['attackerName']
        target = w['targetName']
        # Кнопка: "Attacker vs Target"
        btn_text = f"⚔️ {attacker} 🆚 {target}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"sel_war:{w_id}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    
    await callback.message.edit_text("🔥 <b>Выберите войну:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(WarState.selecting_war)

# --- Шаг 2: Выбор кого отправляем ---
@router.callback_query(F.data.startswith("sel_war:"))
async def select_target_handler(callback: types.CallbackQuery, state: FSMContext):
    war_id = callback.data.split(":")[1]
    await state.update_data(war_id=war_id)

    # Строим клавиатуру выбора пользователей
    users = db_get_all_users()
    kb = []
    
    # Главная кнопка - ВСЕХ
    kb.append([InlineKeyboardButton(text="🌍 ОТПРАВИТЬ ВСЕХ (ALL)", callback_data="war_target:all")])
    
    # Кнопки для отдельных юзеров (ограничим вывод 10-ю последними, чтобы не спамить кнопками, если база большая)
    # Если нужно всех - можно сделать пагинацию, но пока просто список
    for u in users[:20]: 
        kb.append([InlineKeyboardButton(text=f"👤 {u['username']}", callback_data=f"war_target:{u['user_id']}")])
        
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="war_menu")])
    
    await callback.message.edit_text("👮‍♂️ <b>Чьи войска отправляем?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(WarState.selecting_target)

# --- Шаг 3: Выбор процента ---
@router.callback_query(F.data.startswith("war_target:"))
async def select_percent_handler(callback: types.CallbackQuery, state: FSMContext):
    target_uid = callback.data.split(":")[1] # 'all' или ID
    await state.update_data(target_uid=target_uid)
    
    kb = [
        [InlineKeyboardButton(text="💣 100% (Все войска)", callback_data="war_perc:100")],
        [InlineKeyboardButton(text="⚔️ 75%", callback_data="war_perc:75")],
        [InlineKeyboardButton(text="⚔️ 50%", callback_data="war_perc:50")],
        [InlineKeyboardButton(text="🛡️ 25%", callback_data="war_perc:25")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="war_menu")]
    ]
    await callback.message.edit_text("📊 <b>Сколько войск отправить?</b>\n(Берется % от войск, доступных в городе)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(WarState.selecting_percent)

# --- Шаг 4: Исполнение ---
@router.callback_query(F.data.startswith("war_perc:"))
async def execute_war_handler(callback: types.CallbackQuery, state: FSMContext):
    percent = int(callback.data.split(":")[1])
    data = await state.get_data()
    war_id = data['war_id']
    target_uid = data['target_uid']
    
    await callback.message.edit_text(f"🚀 <b>Начинаю отправку {percent}% войск...</b>\nЭто может занять время.", parse_mode="HTML")
    
    # Определяем список пользователей для атаки
    targets = []
    if target_uid == 'all':
        targets = db_get_all_users()
    else:
        user = db_get_user(int(target_uid))
        if user: targets = [user]

    if not targets:
        await callback.message.edit_text("❌ Пользователи не найдены.")
        return

    report = []
    sem = asyncio.Semaphore(5) # Ограничение одновременных запросов

    async def send_task(user):
        async with sem:
            try:
                api = FomoAPI(user['init_data'], user['proxy_port'])
                
                # 1. Получаем данные (чтобы узнать, сколько войск в городе)
                full_res = await api.get_full_data()
                if not full_res.get("success"):
                    return f"❌ {user['username']}: Ошибка получения данных"

                town_troops = full_res['data'].get('troops', {})
                if not town_troops:
                    return f"⚠️ {user['username']}: В городе нет войск"

                # Нормализация структуры войск (иногда list, иногда dict)
                troops_to_send = {}
                
                # Если пришел список [{'key':..., 'count':...}]
                if isinstance(town_troops, list):
                    temp_dict = {}
                    for t in town_troops:
                        k = t.get('troopKey') or t.get('key')
                        c = t.get('count', 0)
                        if k: temp_dict[k] = temp_dict.get(k, 0) + c
                    town_troops = temp_dict

                # 2. Вычисляем процент
                total_sent_count = 0
                if isinstance(town_troops, dict):
                    for t_key, t_count in town_troops.items():
                        send_count = int(t_count * (percent / 100))
                        if send_count > 0:
                            troops_to_send[t_key] = send_count
                            total_sent_count += send_count
                
                if total_sent_count == 0:
                    return f"⚠️ {user['username']}: Слишком мало войск для отправки (0)"

                # 3. Отправляем
                send_res = await api.send_war_troops(war_id, troops_to_send)
                
                if send_res.get("success"):
                    return f"✅ {user['username']}: Отправлено {total_sent_count} юнитов"
                else:
                    return f"❌ {user['username']}: Ошибка API ({send_res.get('error')})"

            except Exception as e:
                return f"❌ {user['username']}: Exception {str(e)}"

    # Запускаем параллельно
    tasks = [send_task(u) for u in targets]
    results = await asyncio.gather(*tasks)
    
    report_text = "\n".join(results)
    
    # Если текст длинный, режем
    if len(report_text) > 4000: report_text = report_text[:4000] + "..."
    
    back_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="main_menu")]])
    await callback.message.edit_text(f"🏁 <b>Результат отправки ({percent}%):</b>\n\n{report_text}", parse_mode="HTML", reply_markup=back_btn)
    await state.clear()