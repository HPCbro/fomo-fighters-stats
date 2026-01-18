# /root/ff/api.py
import requests
import time
import json
import hashlib
import urllib.parse
import re
import asyncio

from config import PROXY_IP, PROXY_LOGIN, PROXY_PASS

class FomoAPI:
    def __init__(self, init_data, proxy_port):
        self.init_data = init_data
        self.base_url = "https://api.fomofighters.xyz"
        self.proxy_port = proxy_port
        self.proxies = {
            "http": f"http://{PROXY_LOGIN}:{PROXY_PASS}@{PROXY_IP}:{self.proxy_port}",
            "https": f"http://{PROXY_LOGIN}:{PROXY_PASS}@{PROXY_IP}:{self.proxy_port}"
        }
        self.api_key = self._extract_api_key()

    def _extract_api_key(self):
        try:
            parsed = urllib.parse.parse_qs(self.init_data)
            if 'hash' in parsed: return parsed['hash'][0]
            match = re.search(r'hash=([a-f0-9]{64})', self.init_data)
            if match: return match.group(1)
            return None
        except: return None

    def _get_headers(self, payload):
        ts = str(int(time.time()))
        payload_str = json.dumps(payload, separators=(',', ':'))
        raw = f"{ts}_{payload_str}"
        sign = hashlib.md5(urllib.parse.quote(raw, safe="~()*!.'").encode()).hexdigest()
        return {
            "accept": "*/*", "api-key": self.api_key, "content-type": "application/json",
            "api-time": ts, "api-hash": sign, "origin": "https://game.fomofighters.xyz",
            "referer": "https://game.fomofighters.xyz/", "user-agent": "Mozilla/5.0",
        }, payload_str

    async def request(self, endpoint, data_dict):
        url = f"{self.base_url}/{endpoint}"
        headers, data_str = self._get_headers(data_dict)
        try:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: requests.post(
                url, headers=headers, data=data_str, proxies=self.proxies, timeout=15
            ))
            
            if resp.status_code == 200: 
                return resp.json()
            
            # --- ДОБАВЛЕН БЛОК ПРОВЕРКИ ---
            if resp.status_code in [401, 403]:
                return {"success": False, "error": "EXPIRED_TOKEN"}
            # ------------------------------

            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_full_data(self):
        """
        ГИБРИДНЫЙ МЕТОД:
        1. Берет данные профиля, ресурсов, бонусов из /all.
        2. Берет данные армии и таймеров из /after.
        3. Объединяет их.
        """
        # Выполняем оба запроса одновременно
        all_task = self.request("user/data/all", {"data": {}})
        after_task = self.request("user/data/after", {"data": {"lang": "ru"}})
        
        responses = await asyncio.gather(all_task, after_task, return_exceptions=True)
        all_response, after_response = responses

        # --- ИСПРАВЛЕНИЕ: Пробрасываем реальный текст ошибки ---
        
        # Проверка ответа /all
        if isinstance(all_response, Exception):
            return {"success": False, "error": str(all_response)}
        if not all_response.get("success"):
            # Возвращаем именно ту ошибку, которую вернул request (например, EXPIRED_TOKEN)
            real_error = all_response.get("error", "Unknown error in /all")
            return {"success": False, "error": real_error}

        # Проверка ответа /after
        if isinstance(after_response, Exception):
            return {"success": False, "error": str(after_response)}
        if not after_response.get("success"):
            real_error = after_response.get("error", "Unknown error in /after")
            return {"success": False, "error": real_error}
        # -------------------------------------------------------

        all_data = all_response.get("data", {})
        if not isinstance(all_data, dict): all_data = {}
            
        after_data = after_response.get("data", {})
        if not isinstance(after_data, dict): after_data = {}

        merged_data = all_data.copy()
        merged_data.update(after_data)
        
        return {"success": True, "data": merged_data}

    async def buy_troops(self, troop_key, count):
        return await self.request("troops/buy", {"data": {"troopKey": troop_key, "count": count}})

    async def claim_clan_reward(self, reward_key):
        return await self.request("clan/rewards/claim", {"data": reward_key})
    
    async def send_war_troops(self, war_id, troops_dict):
        """
        troops_dict: словарь вида {"frog_archer_10": 10, ...}
        """
        payload = {
            "data": {
                "warId": war_id,
                "troops": troops_dict
            }
        }
        # Endpoint: https://api.fomofighters.xyz/war/troops/send
        return await self.request("war/troops/send", payload)
    
    async def get_game_dbs(self):
        """
        Загружает базу данных игры (параметры юнитов, зданий, квесты и т.д.)
        """
        # Используем payload как в JS коде для получения баз данных
        payload = {
            "data": {
                "dbs": ["all"],
                "lang": "ru" 
            }
        }
        # Эндпоинт из JS кода: loadDb: "/dbs"
        return await self.request("dbs", payload)