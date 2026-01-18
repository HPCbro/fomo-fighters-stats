# /root/ff/handlers/clan.py
import json
import asyncio
from datetime import datetime, timezone
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from api import FomoAPI
from database import db_get_user, db_update_clan_config, db_set_active
from keyboards import main_kb
from config import active_tasks

router = Router()

ALL_CLAN_REWARDS = [f"clan_{i}" for i in range(1, 26)]

@router.callback_query(F.data == "clan_rewards")
async def clan_rewards_menu(callback: types.CallbackQuery):
    uid = callback.from_user.id; user = db_get_user(uid)
    if not user: return
    api = FomoAPI(user['init_data'], user['proxy_port']); await callback.message.edit_text("⏳ Проверяю таймеры...")
    res = await api.get_full_data()
    if not res.get("success"): await callback.message.edit_text("❌ Ошибка.", reply_markup=main_kb(uid)); return
    data = res['data']
    available_rewards = {r['key'] for r in data.get('dbData', {}).get('dbClanRewards', [])}
    cooldowns = {r['key']: datetime.strptime(r['dateEnd'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) for r in data.get('stClanRewards', [])}
    now = datetime.now(timezone.utc); status_text = "<b>🏛️ Настройка авто-сбора:</b>\n\n"; buttons = []
    clan_config = json.loads(user.get('clan_config', '[]'))
    for key in sorted(list(available_rewards), key=lambda x: int(x.split('_')[1])):
        is_enabled = key in clan_config
        emoji = "✅" if is_enabled else "☑️"
        status = "ГОТОВО"
        if key in cooldowns and cooldowns[key] > now: status = f"ждем {str(cooldowns[key] - now).split('.')[0]}"
        buttons.append([InlineKeyboardButton(text=f"{emoji} {key} ({status})", callback_data=f"toggle_clan:{key}")])
    is_running = user['is_clan_active'] == 1
    buttons.append([InlineKeyboardButton(text="🔴 Остановить" if is_running else "🟢 Запустить", callback_data="stop_clan" if is_running else "start_clan")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(status_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("toggle_clan:"))
async def toggle_clan_reward(callback: types.CallbackQuery):
    uid = callback.from_user.id; reward_key = callback.data.split(":")[1]; user = db_get_user(uid)
    clan_config = json.loads(user.get('clan_config', '[]'))
    if reward_key in clan_config: clan_config.remove(reward_key)
    else: clan_config.append(reward_key)
    db_update_clan_config(uid, clan_config)
    await clan_rewards_menu(callback)

async def clan_reward_worker(user_id,bot):
    print(f"🚀 Clan worker for {user_id} started")
    while True:
        user = db_get_user(user_id)
        if not user or user.get('is_clan_active') == 0:
            print(f"🛑 Clan worker for {user_id} stopped"); break
        clan_config = json.loads(user.get('clan_config', '[]'))
        if not clan_config: await asyncio.sleep(60); continue
        api = FomoAPI(user['init_data'], user['proxy_port'])
        res = await api.get_full_data()
        if not res.get("success"): 
            error_msg = res.get('error')
            if error_msg == "EXPIRED_TOKEN":
                db_set_active(user_id, "clan", False)
                try:
                    await bot.send_message(
                        user_id, 
                        "🚨 <b>Авто-сбор клана остановлен.</b>\n\ninitData истекла. Обновите данные!",
                        parse_mode="HTML"
                    )
                except: pass
                break
            await asyncio.sleep(60); continue
        data = res.get('data', {})
        available = {r['key'] for r in data.get('dbData', {}).get('dbClanRewards', [])}
        cooldowns = {r['key']: datetime.strptime(r['dateEnd'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) for r in data.get('stClanRewards', [])}
        now = datetime.now(timezone.utc); min_wait_time = None
        for key in clan_config:
            if key in available and (key not in cooldowns or cooldowns[key] <= now):
                print(f"User {user_id} [Clan]: Claiming {key}...")
                await api.claim_clan_reward(key); await asyncio.sleep(1) 
            elif key in cooldowns:
                wait = (cooldowns[key] - now).total_seconds()
                if min_wait_time is None or wait < min_wait_time: min_wait_time = wait
        sleep_time = min_wait_time + 5 if min_wait_time and min_wait_time > 0 else 300
        print(f"User {user_id} [Clan]: Sleeping for {int(sleep_time)}s")
        await asyncio.sleep(sleep_time)

@router.callback_query(F.data == "start_clan")
async def start_clan_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    db_set_active(uid, "clan", True)
    if uid not in active_tasks or 'clan' not in active_tasks[uid] or active_tasks[uid]['clan'].done():
        if uid not in active_tasks: active_tasks[uid] = {}
        active_tasks[uid]['clan'] = asyncio.create_task(clan_reward_worker(uid, callback.bot))
    await callback.message.edit_reply_markup(reply_markup=main_kb(uid))
    await callback.answer("Авто-сбор наград запущен ✅")

@router.callback_query(F.data == "stop_clan")
async def stop_clan_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    db_set_active(uid, "clan", False)
    await callback.message.edit_reply_markup(reply_markup=main_kb(uid))
    await callback.answer("Авто-сбор наград остановлен 🔴")