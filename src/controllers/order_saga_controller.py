"""
Order saga controller
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
from handlers.create_order_handler import CreateOrderHandler
from handlers.create_payment_handler import CreatePaymentHandler
from handlers.decrease_stock_handler import DecreaseStockHandler
from controllers.controller import Controller
from order_saga_state import OrderSagaState

class OrderSagaController(Controller):
    def __init__(self):
        super().__init__()
        self.current_saga_state = OrderSagaState.CREATING_ORDER

    def run(self, request):
        payload = request.get_json() or {}
        order_data = {
            "user_id": payload.get('user_id'),
            "items": payload.get('items', []),
            "total_amount": payload.get('total_amount')
        }
        self.is_error_occurred = False
        self.create_order_handler = CreateOrderHandler(order_data)
        self.decrease_stock_handler = None
        self.create_payment_handler = None

        while self.current_saga_state is not OrderSagaState.COMPLETED:
            if self.current_saga_state == OrderSagaState.CREATING_ORDER:
                self.current_saga_state = self.create_order_handler.run()
                order_data["order_id"] = self.create_order_handler.order_id
                self.decrease_stock_handler = DecreaseStockHandler(order_data)
                self.create_payment_handler = CreatePaymentHandler(order_data)

            elif self.current_saga_state == OrderSagaState.DECREASING_STOCK:
                self.current_saga_state = self.decrease_stock_handler.run()

            elif self.current_saga_state == OrderSagaState.CREATING_PAYMENT:
                self.current_saga_state = self.create_payment_handler.run()

            elif self.current_saga_state == OrderSagaState.CANCELLING_PAYMENT:
                self.current_saga_state = self.create_payment_handler.rollback()

            elif self.current_saga_state == OrderSagaState.INCREASING_STOCK:
                self.current_saga_state = self.decrease_stock_handler.rollback()

            elif self.current_saga_state == OrderSagaState.CANCELLING_ORDER:
                self.current_saga_state = self.create_order_handler.rollback()

            else:
                self.is_error_occurred = True
                self.logger.debug(f"L'état saga n'est pas valide : {self.current_saga_state}")
                self.current_saga_state = OrderSagaState.COMPLETED

        return {
            "order_id": self.create_order_handler.order_id,
            "status": "Une erreur s'est produite lors de la création de la commande." if self.is_error_occurred else "OK"
        }
