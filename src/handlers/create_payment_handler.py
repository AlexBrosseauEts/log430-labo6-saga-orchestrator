"""
Handler: create payment
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import config
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

class CreatePaymentHandler(Handler):
    """ Handle payment creation. Trigger rollback in case of failure. """

    def __init__(self, order_data):
        """ Constructor method """
        self.order_data = order_data or {}
        self.payment_id = None
        super().__init__()

    # --------- helpers génériques Post/delete,etc----------
    def _send(self, method, url, payload=None):
        try:
            if method == "POST":
                r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
            elif method == "PUT":
                r = requests.put(url, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
            elif method == "DELETE":
                r = requests.delete(url, headers={"Content-Type": "application/json"}, timeout=5)
            else:
                r = requests.get(url, headers={"Content-Type": "application/json"}, timeout=5)

            if r.ok:
                try:
                    data = r.json()
                except Exception:
                    data = None
                return True, r.status_code, data, r.text
            else:
                try:
                    text = r.json()
                except Exception:
                    text = r.text
                return False, r.status_code, None, text
        except Exception as e:
            return False, -1, None, str(e)

    def _create_attempts(self):
        """
        Liste d'essais (method, url, payload) pour CREER un paiement via KrakenD.
        Adapte à ta collection Postman si besoin.
        """
        base = f"{config.API_GATEWAY_URL}/payment-api"
        payload = {
            "order_id": self.order_data.get("order_id"),
            "amount": self.order_data.get("amount"),
            "currency": self.order_data.get("currency", "CAD"),
            "method": self.order_data.get("method", "credit_card")
        }
        return [
            ("POST", f"{base}/payments", payload),
            ("POST", f"{base}/payment", payload),
            ("PUT",  f"{base}/payments", payload),   # au cas où la conf attend PUT
        ]

    def _cancel_attempts(self):
        """
        Liste d'essais pour ANNULER/REMBOURSER un paiement.
        Utilise payment_id si connu, sinon tente par order_id si l'API le supporte.
        """
        base = f"{config.API_GATEWAY_URL}/payment-api"
        pid = self.payment_id
        oid = self.order_data.get("order_id")
        attempts = []
        if pid:
            attempts.extend([
                ("POST", f"{base}/payments/{pid}/cancel", None),
                ("POST", f"{base}/payments/{pid}/refund", None),
                ("DELETE", f"{base}/payments/{pid}", None),
            ])
        if oid:
            attempts.extend([
                ("POST", f"{base}/payments/cancel-by-order/{oid}", None),
                ("POST", f"{base}/payments/refund-by-order/{oid}", None),
            ])
        return attempts

    # --------- run / rollback ----------
    def run(self):
        """Call Payment API to create payment (via KrakenD)"""
        if self.order_data.get("amount") is None:
            self.order_data["amount"] = 0

        for method, url, payload in self._create_attempts():
            ok, status, data, text = self._send(method, url, payload)
            if ok:
                if isinstance(data, dict):
                    self.payment_id = data.get("id") or data.get("payment_id")
                self.logger.debug("La création du paiement a réussi")
                return OrderSagaState.COMPLETED  # succès de la saga
            if status == 404 or status == 405:
                continue
            self.logger.error(f"Erreur {status} : {text}")
            return OrderSagaState.CANCELLING_ORDER

        self.logger.error("Aucun endpoint paiement valide (404/405).")
        return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        """Compensation: annuler/rembourser le paiement créé (si possible)"""
        attempts = self._cancel_attempts()
        if not attempts:
            return OrderSagaState.CANCELLING_ORDER

        for method, url, _ in attempts:
            ok, status, data, text = self._send(method, url)
            if ok:
                self.logger.debug("L'annulation du paiement a réussi")
                return OrderSagaState.CANCELLING_ORDER
            if status in (404, 405):
                continue
            self.logger.error(f"Erreur {status} : {text}")
            return OrderSagaState.CANCELLING_ORDER

        self.logger.error("Impossible d'annuler le paiement : endpoints introuvables (404/405)")
        return OrderSagaState.CANCELLING_ORDER
