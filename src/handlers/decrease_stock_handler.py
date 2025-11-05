"""
Handler: decrease stock
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import os
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

KRAKEND = os.getenv("KRAKEND_BASE", "http://api-gateway:8080")

class DecreaseStockHandler(Handler):
    def __init__(self, order_data):
        self.order_data = order_data
        super().__init__()

    def run(self):
        try:
            r = requests.post(
                f"{KRAKEND}/store-api/stocks/decrease",
                json={"order_id": self.order_data["order_id"], "items": self.order_data["items"]},
                timeout=5,
            )
            if r.ok:
                return OrderSagaState.CREATING_PAYMENT
            return OrderSagaState.CANCELLING_ORDER
        except Exception:
            return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        try:
            r = requests.post(
                f"{KRAKEND}/store-api/stocks/increase",
                json={"order_id": self.order_data["order_id"], "items": self.order_data["items"]},
                timeout=5,
            )
            if r.ok:
                return OrderSagaState.CANCELLING_ORDER
            return OrderSagaState.CANCELLING_ORDER
        except Exception:
            return OrderSagaState.CANCELLING_ORDER
