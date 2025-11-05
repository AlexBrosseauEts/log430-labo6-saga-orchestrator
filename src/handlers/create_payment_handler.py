"""
Handler: create payment
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import os
import config
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

# Optionnel: permet d’override via .env si jamais
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://payments_api:5009")

class CreatePaymentHandler(Handler):
    """ Handle payment creation. Trigger rollback in case of failure. """

    def __init__(self, order_data):
        """ Constructor method """
        self.order_data = order_data or {}
        self.payment_id = None
        super().__init__()

    # ------- helpers ----------
    def _send(self, method, url, payload=None):
        try:
            if method == "POST":
                r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            elif method == "PUT":
                r = requests.put(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            elif method == "DELETE":
                r = requests.delete(url, headers={"Content-Type": "application/json"}, timeout=10)
            else:
                r = requests.get(url, headers={"Content-Type": "application/json"}, timeout=10)

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
        payload = {
            "order_id": self.order_data.get("order_id"),
            "amount": self.order_data.get("amount", 0),
            "currency": self.order_data.get("currency", "CAD"),
            "method": self.order_data.get("method", "credit_card")
        }
        return [
            # 1) via KrakenD (si exposé)
            ("POST", f"{config.API_GATEWAY_URL}/payment-api/payments", payload),
            # 2) direct vers le service payments_api (sans passer par Labo5)
            ("POST", f"{PAYMENT_API_URL}/payments", payload),
        ]

    def _cancel_attempts(self):
        pid = self.payment_id
        oid = self.order_data.get("order_id")
        attempts = []
        # via KrakenD d'abord
        if pid:
            attempts.extend([
                ("POST", f"{config.API_GATEWAY_URL}/payment-api/payments/{pid}/cancel", None),
                ("POST", f"{config.API_GATEWAY_URL}/payment-api/payments/{pid}/refund", None),
                ("DELETE", f"{config.API_GATEWAY_URL}/payment-api/payments/{pid}", None),
            ])
        if oid:
            attempts.extend([
                ("POST", f"{config.API_GATEWAY_URL}/payment-api/payments/cancel-by-order/{oid}", None),
                ("POST", f"{config.API_GATEWAY_URL}/payment-api/payments/refund-by-order/{oid}", None),
            ])

        # puis chemins directs vers le service payments_api
        if pid:
            attempts.extend([
                ("POST", f"{PAYMENT_API_URL}/payments/{pid}/cancel", None),
                ("POST", f"{PAYMENT_API_URL}/payments/{pid}/refund", None),
                ("DELETE", f"{PAYMENT_API_URL}/payments/{pid}", None),
            ])
        if oid:
            attempts.extend([
                ("POST", f"{PAYMENT_API_URL}/payments/cancel-by-order/{oid}", None),
                ("POST", f"{PAYMENT_API_URL}/payments/refund-by-order/{oid}", None),
            ])
        return attempts

    # ------- run / rollback ----------
    def run(self):
        """Créer la transaction de paiement"""
        try:
            # sécurité: ensure amount
            if self.order_data.get("amount") is None:
                self.order_data["amount"] = 0

            for method, url, payload in self._create_attempts():
                ok, status, data, text = self._send(method, url, payload)
                if ok:
                    if isinstance(data, dict):
                        self.payment_id = data.get("id") or data.get("payment_id")
                    self.logger.debug("La création du paiement a réussi")
                    return OrderSagaState.COMPLETED  # succès final de la saga
                if status in (404, 405):
                    # on tente l'essai suivant
                    continue
                # autre erreur → stop et compensation
                self.logger.error(f"Erreur {status} : {text}")
                return OrderSagaState.CANCELLING_ORDER

            # tous les essais gateway/direct ont échoué (souvent 404)
            self.logger.error("Aucun endpoint paiement valide (404/405) via gateway ni direct.")
            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("La création du paiement a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        """Annuler/rembourser le paiement si possible"""
        try:
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

        except Exception as e:
            self.logger.error("L'annulation du paiement a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER
