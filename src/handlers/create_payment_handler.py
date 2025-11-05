"""
Handler: create payment
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import os
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://payments_api:5009")

class CreatePaymentHandler(Handler):
    """ Handle payment creation. Trigger rollback in case of failure. """

    def __init__(self, order_data):
        """ Constructor method """
        self.order_data = order_data or {}
        self.payment_id = None
        super().__init__()

    def run(self):
        """Créer la transaction de paiement (appel direct au microservice paiement)"""
        try:
            payload = {
                "order_id": self.order_data.get("order_id"),
                "amount": self.order_data.get("amount", 0),
                "currency": self.order_data.get("currency", "CAD"),
                "method": self.order_data.get("method", "credit_card"),
                "user_id": self.order_data.get("user_id"),
                "items": self.order_data.get("items", [])
            }

            url = f"{PAYMENT_API_URL}/payments"
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=12  # un peu plus long pour éviter les faux timeouts
            )

            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    self.payment_id = data.get("id") or data.get("payment_id")
                self.logger.debug("La création du paiement a réussi")
                return OrderSagaState.COMPLETED

            # -> échec côté paiement
            try:
                text = resp.json()
            except Exception:
                text = resp.text
            self.logger.error(f"[PAYMENT] Erreur {resp.status_code} : {text}")
            self.logger.error(f"[PAYMENT DEBUG] URL={url} PAYLOAD={payload}")
            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("La création du paiement a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        """
        Pas d’endpoint d’annulation exposé par ce microservice mock.
        On journalise et on poursuit la compensation.
        """
        self.logger.debug("Aucun rollback paiement disponible (pas d'endpoint d'annulation).")
        return OrderSagaState.CANCELLING_ORDER
