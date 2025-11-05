"""
Handler: create order
SPDX - License - Identifier: LGPL - 3.0 - or -later
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
    def _try_endpoints(self, attempts):
        """
        attempts: liste de tuples (method, url, json_payload)
        Retourne (ok: bool, status: int, text: str)
        """
        last_status = None
        last_text = ""
        for method, url, payload in attempts:
            try:
                if method == "PUT":
                    resp = requests.put(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
                else:
                    resp = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
                if resp.ok:
                    return True, resp.status_code, resp.text
                last_status = resp.status_code
                try:
                    last_text = resp.json()
                except Exception:
                    last_text = resp.text
                # si 405, on continue sur l’essai suivant
                if resp.status_code == 405:
                    continue
                # autre erreur -> stop
                break
            except Exception as e:
                last_status = -1
                last_text = str(e)
                break
        return False, last_status, last_text
     def run(self):
        """Call StoreManager to check out from stock"""
        try:
            # TRY PUT
            attempts = [
                (
                    "PUT",
                    f'{config.API_GATEWAY_URL}/store-manager-api/stocks',
                    {"items": self.order_item_data, "operation": "-"}
                ),
                # Try Post
                (
                    "POST",
                    f'{config.API_GATEWAY_URL}/store-manager-api/stock/decrease',
                    {"items": self.order_item_data}
                )
            ]
            ok, status, text = self._try_endpoints(attempts)
            if ok:
                self.logger.debug("La sortie des articles du stock a réussi")
                return OrderSagaState.CREATING_PAYMENT
            else:
                self.logger.error(f"Erreur {status} : {text}")
                return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("La sortie des articles du stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER
        
    def rollback(self):
        """ Call StoreManager to revert stock check out (check-in) """
        try:
            # Try PUT
            attempts = [
                (
                    "PUT",
                    f'{config.API_GATEWAY_URL}/store-manager-api/stocks',
                    {"items": self.order_item_data, "operation": "+"}
                ),
                # Try Post
                (
                    "POST",
                    f'{config.API_GATEWAY_URL}/store-manager-api/stock/increase',
                    {"items": self.order_item_data}
                )
            ]
            ok, status, text = self._try_endpoints(attempts)
            if ok:
                self.logger.debug("L'entrée des articles dans le stock a réussi")
            else:
                self.logger.error(f"Erreur {status} : {text}")
            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("L'entrée des articles dans le stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER