"""
QuickBooks Online Accounting API v3 Client with Native Mock Engine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from qb_invoicing.config import Settings, settings
from qb_invoicing.models import QBOInvoicePayload

logger = logging.getLogger(__name__)


class MockQBOEngine:
    """In-memory and file-backed realistic simulator for QuickBooks Online Accounting API v3."""

    def __init__(self, realm_id: str = "9341452019482710", state_file: Optional[str] = None):
        self.realm_id = realm_id
        self.state_file = state_file
        self._next_invoice_id = 1001
        self._next_payment_id = 5001
        self._next_customer_id = 1
        
        # State stores
        self.customers: Dict[str, Dict[str, Any]] = {
            "1": {
                "Id": "1",
                "SyncToken": "0",
                "DisplayName": "Acme Retail Corporation",
                "PrimaryEmailAddr": {"Address": "billing@acmeretail.com"},
                "Active": True,
            }
        }
        self.invoices: Dict[str, Dict[str, Any]] = {}
        self.payments: Dict[str, Dict[str, Any]] = {}
        self._load_state()

    def _load_state(self) -> None:
        if self.state_file and Path(self.state_file).exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.customers = data.get("customers", self.customers)
                    self.invoices = data.get("invoices", self.invoices)
                    self.payments = data.get("payments", self.payments)
                    self._next_invoice_id = data.get("next_invoice_id", self._next_invoice_id)
                    self._next_payment_id = data.get("next_payment_id", self._next_payment_id)
                    self._next_customer_id = data.get("next_customer_id", self._next_customer_id)
            except Exception:
                pass

    def _save_state(self) -> None:
        if self.state_file:
            try:
                Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "customers": self.customers,
                            "invoices": self.invoices,
                            "payments": self.payments,
                            "next_invoice_id": self._next_invoice_id,
                            "next_payment_id": self._next_payment_id,
                            "next_customer_id": self._next_customer_id,
                        },
                        f,
                        indent=2,
                    )
            except Exception:
                pass

    def create_customer(self, name: str, email: str, company: Optional[str] = None) -> Dict[str, Any]:
        """Simulates POST /v3/company/{realmId}/customer."""
        # Check if customer already exists by email or name
        for cid, cust in self.customers.items():
            if cust.get("DisplayName", "").lower() == name.lower():
                return cust
            if cust.get("PrimaryEmailAddr", {}).get("Address", "").lower() == email.lower():
                return cust

        cust_id = str(self._next_customer_id)
        self._next_customer_id += 1
        record = {
            "Id": cust_id,
            "SyncToken": "0",
            "DisplayName": name,
            "CompanyName": company or name,
            "PrimaryEmailAddr": {"Address": email},
            "Active": True,
            "MetaData": {
                "CreateTime": datetime.now(timezone.utc).isoformat() + "Z",
                "LastUpdatedTime": datetime.now(timezone.utc).isoformat() + "Z",
            },
        }
        self.customers[cust_id] = record
        self._save_state()
        return record

    def create_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates POST /v3/company/{realmId}/invoice."""
        inv_id = str(self._next_invoice_id)
        self._next_invoice_id += 1

        # Calculate TotalAmt from lines if not supplied
        total_amt = Decimal("0.00")
        lines = payload.get("Line", [])
        for line in lines:
            amt = Decimal(str(line.get("Amount", 0)))
            if line.get("DetailType") == "DiscountLineDetail":
                total_amt -= amt
            else:
                total_amt += amt

        total_amt = max(Decimal("0.00"), total_amt)

        created_invoice = {
            "Id": inv_id,
            "SyncToken": "0",
            "domain": "QBO",
            "DocNumber": payload.get("DocNumber", f"INV-{inv_id}"),
            "TxnDate": payload.get("TxnDate", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "DueDate": payload.get("DueDate"),
            "CustomerRef": payload.get("CustomerRef", {"value": "1", "name": "Default Customer"}),
            "Line": lines,
            "TotalAmt": float(total_amt),
            "Balance": float(total_amt),  # Initially balance equals total amount
            "CustomerMemo": payload.get("CustomerMemo"),
            "PrivateNote": payload.get("PrivateNote"),
            "BillAddr": payload.get("BillAddr"),
            "ShipAddr": payload.get("ShipAddr"),
            "CurrencyRef": payload.get("CurrencyRef", {"value": "USD"}),
            "EmailStatus": "NotSent",
            "PrintStatus": "NotSet",
            "MetaData": {
                "CreateTime": datetime.now(timezone.utc).isoformat() + "Z",
                "LastUpdatedTime": datetime.now(timezone.utc).isoformat() + "Z",
            },
        }
        self.invoices[inv_id] = created_invoice
        self._save_state()
        return {"Invoice": created_invoice}

    def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Simulates GET /v3/company/{realmId}/invoice/{id}."""
        inv = self.invoices.get(str(invoice_id))
        if inv:
            return {"Invoice": inv}
        return None

    def query_invoices(self, query: str) -> Dict[str, Any]:
        """Simulates QBO SQL Query syntax: select * from Invoice ..."""
        matched: List[Dict[str, Any]] = []
        q_lower = query.lower()

        # Check for DocNumber filtering: DocNumber = '...'
        doc_filter = None
        if "docnumber" in q_lower and "=" in q_lower:
            parts = query.split("=")
            if len(parts) >= 2:
                doc_filter = parts[1].strip().strip("'\" ;")

        for inv in self.invoices.values():
            if doc_filter:
                if inv.get("DocNumber") == doc_filter:
                    matched.append(inv)
            else:
                matched.append(inv)

        return {"QueryResponse": {"Invoice": matched}}

    def record_payment(
        self,
        invoice_id: str,
        amount: float,
        payment_method: str = "CreditCard",
        txn_date: Optional[str] = None,
        reference_num: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulates POST /v3/company/{realmId}/payment."""
        inv = self.invoices.get(str(invoice_id))
        if not inv:
            raise ValueError(f"Cannot record payment: Invoice ID {invoice_id} not found in QBO.")

        current_balance = Decimal(str(inv["Balance"]))
        pay_amt = Decimal(str(amount))
        new_balance = max(Decimal("0.00"), current_balance - pay_amt)

        inv["Balance"] = float(new_balance)
        inv["SyncToken"] = str(int(inv.get("SyncToken", "0")) + 1)
        inv["MetaData"]["LastUpdatedTime"] = datetime.now(timezone.utc).isoformat() + "Z"

        pay_id = str(self._next_payment_id)
        self._next_payment_id += 1

        payment_record = {
            "Id": pay_id,
            "SyncToken": "0",
            "TotalAmt": float(pay_amt),
            "TxnDate": txn_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "CustomerRef": inv["CustomerRef"],
            "PaymentMethodRef": {"value": payment_method},
            "PaymentRefNum": reference_num or f"PAY-{pay_id}",
            "Line": [
                {
                    "Amount": float(pay_amt),
                    "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
                }
            ],
            "MetaData": {
                "CreateTime": datetime.now(timezone.utc).isoformat() + "Z",
                "LastUpdatedTime": datetime.now(timezone.utc).isoformat() + "Z",
            },
        }
        self.payments[pay_id] = payment_record
        self._save_state()
        return {"Payment": payment_record}

    def query_payments_for_invoice(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Find all payments linked to a specific invoice."""
        linked_payments = []
        for payment in self.payments.values():
            for line in payment.get("Line", []):
                for linked in line.get("LinkedTxn", []):
                    if linked.get("TxnId") == str(invoice_id) and linked.get("TxnType") == "Invoice":
                        linked_payments.append(payment)
                        break
        return linked_payments


class QuickBooksClient:
    """Production and Sandbox Client for Intuit QuickBooks Online Accounting API v3."""

    def __init__(self, cfg: Optional[Settings] = None):
        self.config = cfg or settings
        state_file = None
        if self.config.database_path != ":memory:":
            state_file = str(Path(self.config.database_path).parent / ".mock_qbo_state.json")
        self.mock_engine = MockQBOEngine(realm_id=self.config.realm_id, state_file=state_file)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_or_create_customer(self, name: str, email: str, company: Optional[str] = None) -> Dict[str, Any]:
        """Find an existing customer by name/email or create a new customer record."""
        if self.config.use_mock:
            return self.mock_engine.create_customer(name=name, email=email, company=company)

        # Real QBO API Call: query customer
        query = f"select * from Customer where DisplayName = '{name}'"
        url = f"{self.config.api_url}/query"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"query": query}, headers=self._headers())
            if resp.status_code == 200:
                data = resp.json()
                customers = data.get("QueryResponse", {}).get("Customer", [])
                if customers:
                    return customers[0]

            # Not found, create customer
            create_url = f"{self.config.api_url}/customer"
            payload = {
                "DisplayName": name,
                "CompanyName": company or name,
                "PrimaryEmailAddr": {"Address": email},
            }
            create_resp = client.post(create_url, json=payload, headers=self._headers())
            create_resp.raise_for_status()
            return create_resp.json().get("Customer", {})

    def create_invoice(self, payload: QBOInvoicePayload) -> Dict[str, Any]:
        """
        Creates an invoice in QuickBooks Online.
        Returns the created Invoice dictionary with QBO Id, DocNumber, TotalAmt, Balance.
        """
        body = payload.model_dump(exclude_none=True)

        if self.config.use_mock:
            resp = self.mock_engine.create_invoice(body)
            return resp.get("Invoice", {})

        url = f"{self.config.api_url}/invoice"
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json().get("Invoice", {})

    def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Fetch invoice by QuickBooks Online Id."""
        if self.config.use_mock:
            res = self.mock_engine.get_invoice(invoice_id)
            return res.get("Invoice") if res else None

        url = f"{self.config.api_url}/invoice/{invoice_id}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("Invoice", {})

    def query_invoices(self, query: str) -> List[Dict[str, Any]]:
        """Execute QBO SQL Query for invoices."""
        if self.config.use_mock:
            res = self.mock_engine.query_invoices(query)
            return res.get("QueryResponse", {}).get("Invoice", [])

        url = f"{self.config.api_url}/query"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"query": query}, headers=self._headers())
            resp.raise_for_status()
            return resp.json().get("QueryResponse", {}).get("Invoice", [])

    def record_payment(
        self,
        invoice_id: str,
        amount: float,
        payment_method: str = "CreditCard",
        txn_date: Optional[str] = None,
        reference_num: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records a payment in QBO linked to the specified invoice ID.
        """
        if self.config.use_mock:
            res = self.mock_engine.record_payment(
                invoice_id=invoice_id,
                amount=amount,
                payment_method=payment_method,
                txn_date=txn_date,
                reference_num=reference_num,
            )
            return res.get("Payment", {})

        # Live QBO Payment payload
        inv = self.get_invoice(invoice_id)
        if not inv:
            raise ValueError(f"Invoice {invoice_id} not found on QuickBooks.")

        payload = {
            "TotalAmt": amount,
            "CustomerRef": inv["CustomerRef"],
            "PaymentMethodRef": {"value": payment_method},
            "PaymentRefNum": reference_num,
            "TxnDate": txn_date,
            "Line": [
                {
                    "Amount": amount,
                    "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
                }
            ],
        }
        url = f"{self.config.api_url}/payment"
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json().get("Payment", {})

    def get_payments_for_invoice(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Retrieve all payment records linked to an invoice."""
        if self.config.use_mock:
            return self.mock_engine.query_payments_for_invoice(invoice_id)

        # In Live QBO API, query Payment records
        query = f"select * from Payment where TotalAmt > 0"
        url = f"{self.config.api_url}/query"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params={"query": query}, headers=self._headers())
            resp.raise_for_status()
            all_payments = resp.json().get("QueryResponse", {}).get("Payment", [])
            linked = []
            for p in all_payments:
                for line in p.get("Line", []):
                    for txn in line.get("LinkedTxn", []):
                        if txn.get("TxnId") == invoice_id and txn.get("TxnType") == "Invoice":
                            linked.append(p)
                            break
            return linked
