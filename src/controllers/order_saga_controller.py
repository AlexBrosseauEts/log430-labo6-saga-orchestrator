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
    """ 
    This class manages states and transitions of an order saga. The current state is persisted only in memory, as an instance variable, therefore it does not allow retrying in case the application fails.
    Please read section 11 of the arc42 document of this project to understand the limitations of this implementation in more detail.
    """

    def __init__(self):
        """ Constructor method """
        super().__init__()
        # NOTE: veuillez lire le commentaire de ce classe pour mieux comprendre les limitations de ce implémentation
        self.current_saga_state = OrderSagaState.CREATING_ORDER
    
    def run(self, request):
        payload = request.get_json() or {}
        order_data = {
            "user_id": payload.get('user_id'),
            "items": payload.get('items', [])
        }

        self.is_error_occurred = False
        self.create_order_handler = CreateOrderHandler(order_data)
        self.stock_handler = None
        self.payment_handler = None

        while self.current_saga_state is not OrderSagaState.COMPLETED:

            if self.current_saga_state == OrderSagaState.CREATING_ORDER:
                self.current_saga_state = self.create_order_handler.run()

            elif self.current_saga_state == OrderSagaState.DECREASING_STOCK:
                self.stock_handler = DecreaseStockHandler(order_data["items"])
                self.current_saga_state = self.stock_handler.run()

            elif self.current_saga_state == OrderSagaState.CREATING_PAYMENT:
                self.payment_handler = CreatePaymentHandler({
                    "order_id": self.create_order_handler.order_id,
                    "items": order_data["items"]
                })
                self.current_saga_state = self.payment_handler.run()

            # ==== Chemin rollback ====

            elif self.current_saga_state == OrderSagaState.CANCELLING_PAYMENT:
                if self.payment_handler:
                    self.payment_handler.rollback()
                self.current_saga_state = OrderSagaState.CANCELLING_STOCK

            elif self.current_saga_state == OrderSagaState.CANCELLING_STOCK:
                if self.stock_handler:
                    self.stock_handler.rollback()
                self.current_saga_state = OrderSagaState.CANCELLING_ORDER

            elif self.current_saga_state == OrderSagaState.CANCELLING_ORDER:
                if self.create_order_handler:
                    self.create_order_handler.rollback()
                self.is_error_occurred = True
                self.current_saga_state = OrderSagaState.COMPLETED

            else:
                self.is_error_occurred = True
                self.logger.debug(f"L'état saga n'est pas valide : {self.current_saga_state}")
                self.current_saga_state = OrderSagaState.COMPLETED

        return {
            "order_id": self.create_order_handler.order_id,
            "status": "OK" if not self.is_error_occurred else "Une erreur s'est produite lors de la création de la commande."
        }
    
