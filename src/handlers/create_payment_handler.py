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

    def run(self):
        """Call Payment API (via KrakenD) to create payment"""
        try:
            payload = {
                "order_id": self.order_data.get("order_id"),
                "amount": self.order_data.get("amount"),
                "currency": self.order_data.get("currency", "CAD"),
                "method": self.order_data.get("method", "credit_card")
            }

            response = requests.post(
                f"{config.API_GATEWAY_URL}/payment-api/payments",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )

            if response.ok:
                try:
                    data = response.json()
                except Exception:
                    data = None
                self.payment_id = (data or {}).get("id")
                self.logger.debug("La création du paiement a réussi")
                return OrderSagaState.COMPLETED  # ou un état SUCCESS si défini

            else:
                try:
                    text = response.json()
                except Exception:
                    text = response.text
                self.logger.error(f"Erreur {response.status_code} : {text}")
                return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("La création du paiement a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER

    def rollback(self):
        """Compensation: annuler/rembourser le paiement créé (si ID connu)"""
        try:
            if not self.payment_id:
                return OrderSagaState.CANCELLING_ORDER

            url = f"{config.API_GATEWAY_URL}/payment-api/payments/{self.payment_id}/cancel"
            response = requests.post(url, timeout=5)

            if response.ok:
                self.logger.debug("L'annulation du paiement a réussi")
            else:
                try:
                    text = response.json()
                except Exception:
                    text = response.text
                self.logger.error(f"Erreur {response.status_code} : {text}")

            return OrderSagaState.CANCELLING_ORDER

        except Exception as e:
            self.logger.error("L'annulation du paiement a échoué : " + str(e))
            return OrderSagaState.CANCELLING_ORDER
