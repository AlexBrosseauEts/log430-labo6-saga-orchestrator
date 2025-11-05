"""
Handler: create payment
SPDX - License - Identifier: LGPL-3.0-or-later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import os
import requests
from handlers.handler import Handler
from order_saga_state import OrderSagaState

# Appel direct au microservice de paiement (pas via la gateway)
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://payments_api:5009")

class CreatePaymentHandler(Handler):
    """ Gère la création du paiement. Déclenche le rollback global en cas d'échec. """

    def __init__(self, order_data):
        """ order_data doit contenir au minimum: order_id, user_id (et un montant) """
        self.order_data = order_data or {}
        self.payment_id = None
        super().__init__()

    def _safe_amount(self) -> float:
        """Retourne un montant numérique > 0 (fallback si None/0/invalide)."""
        amt = self.order_data.get("amount")
        if amt is None:
            # Fallback basique: somme des quantités comme pseudo-valeur, sinon 1.0
            items = self.order_data.get("items", [])
            try:
                amt = float(sum((it or {}).get("quantity", 0) for it in items)) or 1.0
            except Exception:
                amt = 1.0
        try:
            amt = float(amt)
            if amt <= 0:
                amt = 1.0
        except Exception:
            amt = 1.0
        return amt

    def run(self):
        """Créer la transaction de paiement (appel direct à payments_api)."""
        try:
            amt = self._safe_amount()

            # Certains labos exigent "value" (et non "amount"). On envoie les deux par compatibilité.
            payload = {
                "order_id":      self.order_data.get("order_id"),
                "user_id":       self.order_data.get("user_id"),
                "value":         amt,                                   # requis par l’API (valeur du paiement)
                "amount":        amt,                                   # compat
                "total_amount":  amt,                                   # compat supplémentaire
                "currency":      self.order_data.get("currency", "CAD"),
                "method":        self.order_data.get("method", "credit_card"),
                # champs supplémentaires si l’API les ignore, ça ne casse rien
                "items":         self.order_data.get("items", []),
                "orderId":       self.order_data.get("order_id"),       # compat camelCase
                "userId":        self.order_data.get("user_id"),
            }

            url = f"{PAYMENT_API_URL}/payments"
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=12
            )

            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    self.payment_id = data.get("id") or data.get("payment_id")
                self.logger.debug("La création du paiement a réussi")
                return OrderSagaState.COMPLETED  # Fin de la saga

            # Échec : journaliser le détail pour diagnostic
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
        Pas d’endpoint d’annulation dans ce microservice mock.
        On journalise et on laisse l’orchestrateur poursuivre la compensation.
        """
        self.logger.debug("Aucun rollback paiement disponible (pas d'endpoint d'annulation).")
        return OrderSagaState.CANCELLING_ORDER
