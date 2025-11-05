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
        self.order_item_data = order_item_data
        super().__init__()

    def _send(self, method, url, payload):
        try:
            if method == "PUT":
                r = requests.put(url, json=payload, headers={'Content-Type':'application/json'}, timeout=12)
            else:
                r = requests.post(url, json=payload, headers={'Content-Type':'application/json'}, timeout=12)
            ok = 200 <= r.status_code < 300
            txt = r.text
            try:
                js = r.json()
            except Exception:
                js = None
            return ok, r.status_code, js, txt
        except requests.exceptions.Timeout as e:
            # on remonte un statut spécial pour déclencher le fallback
            return False, 598, None, f"timeout: {e}"
        except Exception as e:
            return False, -1, None, str(e)

    def _try_checkout(self):
        payload_minus = {"items": self.order_item_data, "operation": "-"}
        attempts = [
            # 1) Gateway (labo5)
            ("PUT", f"{API_GATEWAY_URL}/store-manager-api/stocks", payload_minus),
            ("POST", f"{API_GATEWAY_URL}/store-manager-api/stock/decrease", {"items": self.order_item_data}),
            # 2) Direct microservice (fallback si gateway 404/405/timeout)
            ("PUT", f"{STORE_MANAGER_URL}/stocks", payload_minus),
            ("POST", f"{STORE_MANAGER_URL}/stock/decrease", {"items": self.order_item_data}),
        ]
        for method, url, payload in attempts:
            ok, status, js, txt = self._send(method, url, payload)
            if ok:
                return True, status, js, txt
            # 404/405/598 (timeout) -> on essaie le prochain
            if status in (404, 405, 598):
                self.logger.error(f"[STOCK FALLBACK] {status} sur {url} -> essai suivant")
                continue
            # autre erreur -> stop
            self.logger.error(f"[STOCK] Erreur {status} : {txt}")
            return False, status, js, txt
        return False, 404, None, "Aucun endpoint stocks valide (gateway et direct)"

    def _try_checkin(self):
        payload_plus = {"items": self.order_item_data, "operation": "+"}
        attempts = [
            ("PUT", f"{API_GATEWAY_URL}/store-manager-api/stocks", payload_plus),
            ("POST", f"{API_GATEWAY_URL}/store-manager-api/stock/increase", {"items": self.order_item_data}),
            ("PUT", f"{STORE_MANAGER_URL}/stocks", payload_plus),
            ("POST", f"{STORE_MANAGER_URL}/stock/increase", {"items": self.order_item_data}),
        ]
        for method, url, payload in attempts:
            ok, status, js, txt = self._send(method, url, payload)
            if ok:
                return True, status, js, txt
            if status in (404, 405, 598):
                self.logger.error(f"[STOCK ROLLBACK FALLBACK] {status} sur {url} -> essai suivant")
                continue
            self.logger.error(f"[STOCK ROLLBACK] Erreur {status} : {txt}")
            return False, status, js, txt
        return False, 404, None, "Aucun endpoint rollback stocks valide (gateway et direct)"

    def run(self):
        """Décrémenter le stock"""
        try:
            ok, status, js, txt = self._try_checkout()
            if ok:
                self.logger.debug("La sortie des articles du stock a réussi")
                return OrderSagaState.CREATING_PAYMENT
            else:
                self.logger.error(f"Erreur {status} : {txt}")
                return OrderSagaState.CANCELLING_ORDER
        except Exception as e:
            self.logger.error("La sortie des articles du stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        """Compensation : ré-entrer le stock"""
        try:
            ok, status, js, txt = self._try_checkin()
            if ok:
                self.logger.debug("L'entrée des articles dans le stock a réussi")
            else:
                self.logger.error(f"Erreur {status} : {txt}")
            return OrderSagaState.CANCELLING_ORDER
        except Exception as e:
            self.logger.error("L'entrée des articles dans le stock a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER