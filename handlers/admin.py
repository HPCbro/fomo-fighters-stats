# /root/ff/handlers/admin.py
import asyncio
import io
import re
from aiogram import Router, F, types
from aiogram.types import BufferedInputFile
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from api import FomoAPI
from database import db_get_all_users, db_get_user
from config import ADMIN_IDS
from utils.html_generator import update_website_logic 
router = Router()

@router.callback_query(F.data == "admin_stats")
async def admin_menu_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Отчет по ферме", callback_data="admin_farm_report")],
        [InlineKeyboardButton(text="🌐 Обновить сайт статистики", callback_data="admin_trigger_site_update")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    users_count = len(db_get_all_users())
    await callback.message.edit_text(
        f"<b>Панель администратора</b>\n\n"
        f"Всего пользователей в базе: {users_count}",
        reply_markup=kb,
        parse_mode="HTML"
    )

# --- Обработчик для отчета по ферме ---
@router.callback_query(F.data == "admin_farm_report")
async def admin_farm_report_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text("🕵️‍♂️ <b>Сбор данных со всех аккаунтов...</b>\nЭто может занять время.", parse_mode="HTML")

    users = db_get_all_users()
    if not users:
        await callback.message.edit_text("В базе нет пользователей.", reply_markup=back_kb("admin_stats"))
        return

    results = []
    sem = asyncio.Semaphore(5) # Ограничиваем до 5 одновременных запросов

    async def fetch_user_data(user):
        async with sem:
            try:
                api = FomoAPI(user['init_data'], user['proxy_port'])
                res = await api.get_full_data()
                if res.get('error') == 'EXPIRED_TOKEN':
                    try:
                        await callback.bot.send_message(
                            user['user_id'],
                            "⚠️ <b>Ваша initData устарела.</b>\nПожалуйста, обновите данные в боте.",
                            parse_mode="HTML"
                        )
                    except: pass
                return { "username": user.get('username', f"ID_{user['user_id']}"), "success": res.get("success"), "data": res.get("data"), "error": res.get("error") }
            except Exception as e:
                return {"username": user.get('username', f"ID_{user['user_id']}"), "success": False, "error": str(e)}

    tasks = [fetch_user_data(u) for u in users]
    data_list = await asyncio.gather(*tasks)

    report_lines = [f"📊 ОТЧЕТ ПО ФЕРМЕ ({len(users)} аккаунтов)\n" + "="*30 + "\n"]
    
    for info in sorted(data_list, key=lambda x: x['username']):
        name = info['username']
        
        if not info['success']:
            report_lines.append(f"❌ {name}: Ошибка - {info.get('error')}")
            report_lines.append("-" * 20)
            continue

        data = info.get('data', {})
        res = data.get('hero', {}).get('resources', {})
        troops = data.get('troops', {})
        
        food = int(res.get('food', {}).get('value', 0))
        wood = int(res.get('wood', {}).get('value', 0))
        stone = int(res.get('stone', {}).get('value', 0))
        gem = int(res.get('gem', {}).get('value', 0))
        
        troops_str = "Нет войск"
        if troops:
            t_list = []
            iter_troops = troops.items() if isinstance(troops, dict) else []
            if isinstance(troops, list):
                parsed = {}
                for t in troops:
                    k = t.get('troopKey') or t.get('key')
                    c = t.get('count', 0)
                    if k: parsed[k] = parsed.get(k, 0) + c
                iter_troops = parsed.items()

            for k, v in iter_troops:
                if v > 0:
                    short = re.sub(r'^(frog|cat|dog)_', '', k)
                    t_list.append(f"{short}:{v}")
            
            if t_list: troops_str = ", ".join(t_list)

        report_lines.append(f"✅ {name}")
        report_lines.append(f"   💰 Еда: {food:,} | Дер: {wood:,} | Кам: {stone:,} | Гем: {gem:,}")
        report_lines.append(f"   ⚔️ {troops_str}")
        report_lines.append("-" * 20)

    report_content = "\n".join(report_lines)

    # Клавиатура для возврата в админ-меню
    back_to_admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в админ-меню", callback_data="admin_stats")]
    ])

    if len(report_content.encode('utf-8')) < 4000:
        await callback.message.edit_text(f"<pre>{report_content}</pre>", parse_mode="HTML", reply_markup=back_to_admin_kb)
    else:
        file_bytes = io.BytesIO(report_content.encode('utf-8'))
        file_doc = BufferedInputFile(file_bytes.getvalue(), filename="farm_report.txt")
        await callback.message.delete()
        await callback.message.answer_document(document=file_doc, caption="📊 Полный отчет по всем аккаунтам", reply_markup=back_to_admin_kb)

# --- Обработчик для обновления сайта ---
@router.callback_query(F.data == "admin_trigger_site_update")
async def trigger_update(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    
    await callback.message.edit_text("⏳ Загружаю данные игры и обновляю сайт...")
    
    admin_user = db_get_user(callback.from_user.id)
    
    if not admin_user:
        await callback.message.edit_text("❌ Ошибка: Админ не найден в базе (нужен initData).")
        return

    api = FomoAPI(admin_user['init_data'], admin_user['proxy_port'])
    resp = await api.get_game_dbs()
    
    if not resp.get('success'):
        await callback.message.edit_text(f"❌ Ошибка API: {resp.get('error')}")
        return
        
    db_data = resp.get('data', {})
    
    # Запускаем генератор и пуш в Git
    # Эта функция может быть долгой, поэтому даем боту "понять", что мы работаем
    await callback.bot.send_chat_action(callback.from_user.id, 'typing')
    
    loop = asyncio.get_running_loop()
    # Выполняем синхронный код в отдельном потоке, чтобы не блокировать бота
    success, msg = await loop.run_in_executor(None, update_website_logic, db_data)
    
    if success:
        await callback.message.edit_text(f"✅ Сайт успешно обновлен!\nGit: {msg}")
    else:
        await callback.message.edit_text(f"⚠️ Ошибка генерации/git: {msg}")