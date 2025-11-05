"""
Handler: create order
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import config
import requests
from logger import Logger
from handlers.handler import Handler
from order_saga_state import OrderSagaState

class CreateOrderHandler(Handler):
    """ Handle order creation. Delete order in case of failure. """

    def __init__(self, order_data):
        """ Constructor method """
        self.order_data = order_data
        self.order_id = 0
        super().__init__()

    def run(self):
        """Call StoreManager to create order"""
        try:
            response = requests.post(
                f'{config.API_GATEWAY_URL}/store-manager-api/orders',
                json=self.order_data,
                headers={'Content-Type': 'application/json'}
            )
            if response.ok:
                data = response.json()
                self.order_id = data.get('order_id', 0)
                self.logger.debug("La création de la commande a réussi")
                return OrderSagaState.DECREASING_STOCK
            else:
                try:
                    text = response.json()
                except Exception:
                    text = response.text
                self.logger.error(f"Erreur {response.status_code} : {text}")
                return OrderSagaState.COMPLETED

        except Exception as e:
            self.logger.error("La création de la commande a échoué : " + str(e))
            return OrderSagaState.COMPLETED

    def rollback(self):
        """Call StoreManager to delete order"""
        try:
            response = requests.delete(
                f'{config.API_GATEWAY_URL}/store-manager-api/orders/{self.order_id}'
            )

            if response.ok:
                try:
                    data = response.json()
                    self.order_id = data.get('order_id', self.order_id)
                except Exception:
                    pass
                self.logger.debug("La supression de la commande a réussi")
                return OrderSagaState.COMPLETED

            else:
                try:
                    text = response.json()
                except Exception:
                    text = response.text
                self.logger.error(f"Erreur {response.status_code} : {text}")
                return OrderSagaState.COMPLETED

        except Exception as e:
            self.logger.error("La supression de la commande a échoué : " + str(e))
            return OrderSagaState.COMPLETED
