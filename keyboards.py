# /root/ff/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_get_user

# keyboards.py (изменяем main_kb)
from config import ADMIN_IDS # Не забудь импортировать

def main_kb(user_id):
    user = db_get_user(user_id)
    recruit_running = user and user.get('is_recruit_active') == 1
    clan_running = user and user.get('is_clan_active') == 1
    recruit_status = "🟢" if recruit_running else "🔴"
    clan_status = "🟢" if clan_running else "🔴"
    
    kb = [
        [InlineKeyboardButton(text="👤 Профиль и Ресурсы", callback_data="profile")],
        [InlineKeyboardButton(text=f"{recruit_status} Авто-найм", callback_data="recruit_menu")],
        [InlineKeyboardButton(text=f"{clan_status} Авто-сбор наград", callback_data="clan_rewards")],
        [InlineKeyboardButton(text="🔄 Обновить initData", callback_data="add_account")]
    ]

    if user_id in ADMIN_IDS:
        # Добавляем ряд кнопок для админа
        kb.append([
            InlineKeyboardButton(text="🕵️‍♂️ Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="⚔️ Война", callback_data="war_menu") # <--- НОВАЯ КНОПКА
        ])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def profile_kb():
    """Клавиатура для меню профиля."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Войска в городе", callback_data="show_troops")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def back_kb(menu_callback="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=menu_callback)]])