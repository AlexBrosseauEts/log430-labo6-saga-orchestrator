"""
Handler: decrease stock
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import config
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

class DecreaseStockHandler(Handler):
    """Handle stock checkout. Trigger rollback in case of failure."""

    def __init__(self, order_item_data):
        """ Constructor method """
        self.order_item_data = order_item_data
        super().__init__()

    def _try_endpoints(self, payload):
        """
        Essaie plusieurs endpoints si le 1er renvoie 405
        Retourne (ok: bool, status: int, text: str)
        """
        attempts = [
            ("PUT",  f"{config.API_GATEWAY_URL}/store-manager-api/stocks"),
            ("POST", f"{config.API_GATEWAY_URL}/store-manager-api/stock/decrease"),
        ]

        last_status = None
        last_text = ""

        for method, url in attempts:
            try:
                if method == "PUT":
                    resp = requests.put(url, json=payload,
                        headers={'Content-Type': 'application/json'}, timeout=5)
                else:
                    resp = requests.post(url, json=payload,
                        headers={'Content-Type': 'application/json'}, timeout=5)

                if resp.ok:
                    return True, resp.status_code, resp.text

                last_status = resp.status_code
                try:
                    last_text = resp.json()
                except Exception:
                    last_text = resp.text

                # si c'est un 405, on teste le prochain endpoint
                if resp.status_code == 405:
                    continue

                break  # autre erreur -> stop

            except Exception as e:
                last_status = -1
                last_text = str(e)
                break

        return False, last_status, last_text


    def run(self):
        """Décrémenter le stock"""
        try:
            ok, status, text = self._try_endpoints({
                "items": self.order_item_data,
                "operation": "-"  # diminuer
            })

            if ok:
                self.logger.debug("La sortie des articles du stock a réussi")
                return OrderSagaState.CREATING_PAYMENT

            self.logger.error(f"Erreur {status} : {text}")
            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("La sortie des articles du stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER


    def rollback(self):
        """Compensation: réinsérer les articles dans le stock"""
        try:
            ok, status, text = self._try_endpoints({
                "items": self.order_item_data,
                "operation": "+"  # ré-ajouter stock
            })

            if ok:
                self.logger.debug("L'entrée des articles dans le stock a réussi")
            else:
                self.logger.error(f"Erreur {status} : {text}")

            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("L'entrée des articles dans le stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER
