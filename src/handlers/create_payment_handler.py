import os, requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

KRAKEND = os.getenv("KRAKEND_BASE", "http://api-gateway:8080")

class CreatePaymentHandler(Handler):
    def __init__(self, order_data):
        self.order_data = order_data
        super().__init__()

    def run(self):
        try:
            r = requests.post(
                f"{KRAKEND}/payments-api/payments",
                json={
                    "user_id": self.order_data["user_id"],
                    "order_id": self.order_data["order_id"],
                    "total_amount": self.order_data["total_amount"],
                },
                timeout=5,
            )
            if r.ok:
                data = r.json()
                self.order_data["payment_id"] = data.get("payment_id")
                return OrderSagaState.COMPLETED 
            return OrderSagaState.CANCELLING_PAYMENT
        except Exception:
            return OrderSagaState.CANCELLING_PAYMENT

    def rollback(self):
        try:
            pid = self.order_data.get("payment_id")
            if not pid:
                return OrderSagaState.INCREASING_STOCK
            # adapte si tu as cancel au lieu de delete
            r = requests.delete(f"{KRAKEND}/payments-api/payments/{pid}", timeout=5)
            if r.status_code in (200, 204, 404):
                return OrderSagaState.INCREASING_STOCK
            return OrderSagaState.INCREASING_STOCK
        except Exception:
            return OrderSagaState.INCREASING_STOCK
