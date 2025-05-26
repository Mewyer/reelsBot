import httpx
import json
from typing import Optional, Dict, Any
from config import config
import logging
from urllib.parse import urlencode
import asyncio

logger = logging.getLogger(__name__)

class CryptoBot:
    def __init__(self):
        self.token = config.CRYPTOBOT_TOKEN
        self.base_url = config.CRYPTOBOT_API_URL
        self.timeout = 30.0
        self.retries = 3
        self.retry_delay = 2.0
        self.supported_btn_names = ['viewItem', 'openChannel', 'openBot', 'callback']

    async def _make_api_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Универсальный метод для API запросов с обработкой ошибок"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Crypto-Pay-API-Token": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        for attempt in range(self.retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method == "GET":
                        response = await client.get(
                            url,
                            headers=headers,
                            params=params
                        )
                    else:
                        response = await client.post(
                            url,
                            headers=headers,
                            json=params
                        )

                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                error_detail = e.response.json() if e.response.content else {}
                logger.error(
                    f"Attempt {attempt + 1} failed for {endpoint}: "
                    f"{e.response.status_code} - {error_detail}"
                )
                if attempt == self.retries - 1 or e.response.status_code in (400, 401, 403, 404):
                    break

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {endpoint}: {str(e)}")
                if attempt == self.retries - 1:
                    break

            await asyncio.sleep(self.retry_delay * (attempt + 1))

        return None

    async def get_exchange_rate(self) -> Optional[float]:
        """Получаем курс USDT к RUB"""
        params = {
            "source": config.CRYPTOBOT_CURRENCY,
            "target": "RUB"
        }
        
        result = await self._make_api_request("GET", "getExchangeRates", params)
        
        if result and isinstance(result.get("result"), list):
            for rate in result["result"]:
                if (isinstance(rate, dict) and 
                    rate.get("source") == config.CRYPTOBOT_CURRENCY and 
                    rate.get("target") == "RUB"):
                    try:
                        return float(rate["rate"])
                    except (ValueError, TypeError):
                        continue
        return None

    async def create_invoice(
        self,
        amount: float,
        user_id: int,
        description: str = "Premium subscription"
    ) -> Optional[Dict[str, Any]]:
        """Создаем инвойс с корректными параметрами"""
        params = {
            "asset": config.CRYPTOBOT_CURRENCY,
            "amount": str(amount),
            "description": description,
            "payload": str(user_id),
            "paid_btn_name": "openBot",  # Используем поддерживаемое значение
            "paid_btn_url": f"https://t.me/{config.BOT_USERNAME}",
            "allow_comments": False
        }
        
        result = await self._make_api_request("POST", "createInvoice", params)
        return result.get("result") if result else None

    async def check_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Проверяем статус инвойса"""
        params = {"invoice_ids": invoice_id}
        result = await self._make_api_request("GET", "getInvoices", params)
        
        if result and isinstance(result.get("result"), dict):
            items = result["result"].get("items", [])
            if items and isinstance(items, list):
                return items[0]
        return None

cryptobot = CryptoBot()