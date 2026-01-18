import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher
from database import init_db, db_get_all_active, db_get_user
from handlers import core, recruit, clan, admin , war
from handlers.recruit import recruit_worker
from handlers.clan import clan_reward_worker
from config import BOT_TOKEN, active_tasks, ADMIN_IDS
from utils.html_generator import update_website_logic
from api import FomoAPI

# Функция для планировщика
async def scheduled_site_update(bot: Bot):
    print("⏰ Планировщик: Начало обновления сайта...")
    # Берем первого админа для API ключа
    if not ADMIN_IDS: return
    user = db_get_user(ADMIN_IDS[0])
    if not user: return
    
    api = FomoAPI(user['init_data'], user['proxy_port'])
    resp = await api.get_game_dbs()
    
    if resp.get('success'):
        success, msg = update_website_logic(resp.get('data'))
        status = "✅ Успех" if success else f"⚠️ Ошибка: {msg}"
        print(f"⏰ Планировщик: {status}")
        # Можно отправить уведомление админу
        try:
            await bot.send_message(ADMIN_IDS[0], f"📅 Ежедневное обновление сайта:\n{status}")
        except: pass
    else:
        print(f"⏰ Планировщик: Ошибка получения данных {resp.get('error')}")


async def on_startup(dispatcher: Dispatcher, bot: Bot):
    """Функция, которая выполняется при старте бота."""
    active_users = db_get_all_active()
    for u in active_users:
        uid = u['user_id']
        if uid not in active_tasks:
            active_tasks[uid] = {}
            
        # ПЕРЕДАЕМ bot ВНУТРЬ ФУНКЦИЙ
        if u.get('is_recruit_active') == 1:
            active_tasks[uid]['recruit'] = asyncio.create_task(recruit_worker(uid, bot))
        
        if u.get('is_clan_active') == 1:
            active_tasks[uid]['clan'] = asyncio.create_task(clan_reward_worker(uid, bot))
            
    print(f"🔄 Восстановлено {len(active_users)} активных пользователей.")
    # --- ЭТОТ БЛОК НУЖНО ДОБАВИТЬ В КОНЕЦ ФУНКЦИИ on_startup ---
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    # Запускаем раз в 24 часа (можно поменять на hours=1 для теста)
    scheduler.add_job(scheduled_site_update, 'interval', hours=24, args=[bot])
    
    # Немедленный запуск для проверки через 10 секунд после старта бота
    # scheduler.add_job(scheduled_site_update, 'date', run_date=datetime.now() + timedelta(seconds=10), args=[bot])
    
    scheduler.start()
    print("⏰ Планировщик задач запущен.")
    
async def on_shutdown(dispatcher: Dispatcher):
    """Функция, которая выполняется при остановке бота."""
    print("⏳ Остановка фоновых задач...")
    for user_id, tasks in active_tasks.items():
        for task_name, task in tasks.items():
            if task and not task.done():
                task.cancel()
                print(f"   - Задача {task_name} для user {user_id} отменена.")
    # Даем задачам время на завершение
    await asyncio.sleep(2)
    print("✅ Все фоновые задачи остановлены.")


async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Инициализация базы данных
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем функции, которые сработают при старте и остановке
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Подключаем роутеры с обработчиками команд
    dp.include_router(core.router)
    dp.include_router(recruit.router)
    dp.include_router(clan.router)
    dp.include_router(admin.router)
    dp.include_router(war.router) 

    # Удаляем старый вебхук перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("🤖 Бот запущен...")
    # Запускаем бота. Он будет работать, пока не получит сигнал остановки.
    await dp.start_polling(bot)


if __name__ == "__main__":
    if "ВАШ_ТОКЕН" in BOT_TOKEN:
        print("❌ Вставьте токен бота в config.py!")
    else:
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            print("\nБот остановлен вручную.")