"""
QuickBooks Online Webhook Receiver, Signature Verification & Event Processor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import PaymentStatus, SyncLogEntry
from qb_invoicing.payment_tracker import PaymentStatusTracker
from qb_invoicing.qbo_client import QuickBooksClient

logger = logging.getLogger(__name__)


def generate_qbo_webhook_signature(payload_bytes: bytes, verifier_token: str) -> str:
    """
    Computes the base64-encoded HMAC-SHA256 signature for Intuit webhooks.
    """
    secret = verifier_token.encode("utf-8")
    h = hmac.new(secret, payload_bytes, hashlib.sha256)
    return base64.b64encode(h.digest()).decode("utf-8")


def verify_qbo_webhook_signature(payload_bytes: bytes, signature_header: Optional[str], verifier_token: str) -> bool:
    """
    Cryptographically verifies the 'intuit-signature' header.
    Returns True if valid, False otherwise.
    """
    if not signature_header or not verifier_token:
        return False
    expected_sig = generate_qbo_webhook_signature(payload_bytes, verifier_token)
    return hmac.compare_digest(signature_header.strip(), expected_sig.strip())


class WebhookProcessor:
    """
    Processes incoming Intuit QuickBooks Online webhook payloads.
    Ensures idempotency and updates local ledger states.
    """

    def __init__(self, client: QuickBooksClient, ledger: LedgerRepository, tracker: PaymentStatusTracker):
        self.client = client
        self.ledger = ledger
        self.tracker = tracker

    def process_payload(
        self,
        payload_bytes: bytes,
        signature: Optional[str],
        verifier_token: str,
    ) -> Dict[str, Any]:
        """
        Verifies signature, extracts event notifications, routes entity events,
        and returns a summary of actions taken.
        """
        # 1. Verify HMAC-SHA256 signature
        if not verify_qbo_webhook_signature(payload_bytes, signature, verifier_token):
            raise PermissionError("Invalid intuit-signature: Webhook cryptographic verification failed.")

        try:
            data = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Malformed JSON in webhook payload: {e}")

        event_notifications = data.get("eventNotifications", [])
        results: List[Dict[str, Any]] = []

        for notification in event_notifications:
            realm_id = notification.get("realmId", "")
            data_change_events = notification.get("dataChangeEvent", {})
            entities = data_change_events.get("entities", [])

            for entity in entities:
                name = entity.get("name")  # e.g. "Payment", "Invoice"
                eid = str(entity.get("id"))
                operation = entity.get("operation")  # e.g. "Create", "Update", "Void", "Delete"
                event_uid = f"{realm_id}:{name}:{eid}:{operation}:{entity.get('lastUpdated', '')}"

                # 2. Check Idempotency
                if self.ledger.is_webhook_event_processed(event_uid):
                    results.append({
                        "event_id": event_uid,
                        "status": "SKIPPED_DUPLICATE",
                        "entity": name,
                        "id": eid,
                    })
                    continue

                action_result = self._route_entity_event(realm_id, name, eid, operation, notification)

                # Record event to prevent double-processing
                self.ledger.record_webhook_event(
                    event_id=event_uid,
                    realm_id=realm_id,
                    event_type=f"{name}.{operation}",
                    entity_name=name,
                    entity_id=eid,
                    operation=operation,
                    payload=json.dumps(entity),
                )

                results.append({
                    "event_id": event_uid,
                    "status": "PROCESSED",
                    "entity": name,
                    "id": eid,
                    "operation": operation,
                    "detail": action_result,
                })

        return {
            "status": "SUCCESS",
            "events_processed": len(results),
            "details": results,
        }

    def _route_entity_event(
        self,
        realm_id: str,
        entity_name: str,
        entity_id: str,
        operation: str,
        raw_notification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Routes single entity lifecycle change."""
        if entity_name == "Payment":
            return self._handle_payment_event(entity_id, operation)
        elif entity_name == "Invoice":
            return self._handle_invoice_event(entity_id, operation)
        else:
            return {"message": f"Entity '{entity_name}' ignored"}

    def _handle_payment_event(self, payment_id: str, operation: str) -> Dict[str, Any]:
        """
        Handles Payment Create/Update event by discovering linked invoice(s)
        and synchronizing balances.
        """
        # Find which invoices this payment is linked to
        # In mock or live mode, query all open invoices or sync state
        open_invoices = self.ledger.list_invoices(limit=200)
        reconciled = []

        for inv in open_invoices:
            if inv.payment_status != PaymentStatus.PAID:
                synced = self.tracker.sync_invoice_status(inv.qbo_invoice_id)
                if synced and synced.payment_status != inv.payment_status:
                    reconciled.append({
                        "invoice_id": synced.qbo_invoice_id,
                        "doc_number": synced.doc_number,
                        "new_status": synced.payment_status.value,
                        "new_balance": float(synced.balance_due),
                    })

        self.ledger.log_sync_event(
            SyncLogEntry(
                event_type="WEBHOOK_PAYMENT_PROCESSED",
                entity_id=payment_id,
                status="SUCCESS",
                message=f"Webhook processed Payment {payment_id} ({operation})",
                details={"reconciled_invoices": reconciled},
            )
        )
        return {"reconciled_invoices": reconciled}

    def _handle_invoice_event(self, invoice_id: str, operation: str) -> Dict[str, Any]:
        """
        Handles Invoice Update/Void event.
        """
        if operation.lower() in ("void", "delete"):
            ok = self.ledger.void_invoice(invoice_id)
            self.ledger.log_sync_event(
                SyncLogEntry(
                    event_type="WEBHOOK_INVOICE_VOIDED",
                    entity_id=invoice_id,
                    status="SUCCESS",
                    message=f"Invoice {invoice_id} marked as VOIDED via webhook",
                )
            )
            return {"action": "VOIDED", "success": ok}
        else:
            # Re-sync invoice balance
            synced = self.tracker.sync_invoice_status(invoice_id)
            return {
                "action": "SYNCED",
                "doc_number": synced.doc_number if synced else None,
                "status": synced.payment_status.value if synced else None,
            }
