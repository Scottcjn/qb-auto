#!/usr/bin/env python3
"""Minimal QuickBooks Online REST client using only requests."""

from __future__ import annotations

import base64
import os
from typing import Any

import requests

_BASE_BY_ENV = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
    "production": "https://quickbooks.api.intuit.com",
}
BASE_URL = _BASE_BY_ENV[os.environ.get("QBO_ENV", "production").lower()]
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
MINORVERSION = "75"
TIMEOUT = 30


def _escape_qbo(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class QBOClient:
    def __init__(self) -> None:
        self.client_id = os.environ["QBO_CLIENT_ID"]
        self.client_secret = os.environ["QBO_CLIENT_SECRET"]
        self.refresh_token = os.environ["QBO_REFRESH_TOKEN"]
        self.realm_id = os.environ["QBO_REALM_ID"]
        self.access_token = ""

    def _basic_auth(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _refresh_access_token(self) -> dict[str, Any]:
        response = requests.post(
            TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {self._basic_auth()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        self.access_token = payload["access_token"]
        self.refresh_token = payload.get("refresh_token", self.refresh_token)
        return payload

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{BASE_URL}/v3/company/{self.realm_id}/{path}"

    def _parse(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {"text": response.text}
        if isinstance(payload, dict):
            payload.setdefault("_meta", {})
            payload["_meta"]["status_code"] = response.status_code
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        text_body: str | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        if not self.access_token:
            self._refresh_access_token()

        query = {"minorversion": MINORVERSION}
        if params:
            query.update(params)

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if text_body is not None:
            headers["Content-Type"] = "application/text"

        response = requests.request(
            method,
            self._url(path),
            params=query,
            headers=headers,
            json=json_body,
            data=text_body,
            timeout=TIMEOUT,
        )
        if response.status_code == 401 and retry_on_401:
            self._refresh_access_token()
            return self._request(
                method,
                path,
                params=params,
                json_body=json_body,
                text_body=text_body,
                retry_on_401=False,
            )
        return self._parse(response)

    def _query(self, sql: str) -> dict[str, Any]:
        return self._request("POST", "query", text_body=sql)

    def _read(self, entity: str, entity_id: str) -> dict[str, Any]:
        return self._request("GET", f"{entity}/{entity_id}")

    def list_recurring(self) -> dict[str, Any]:
        sql = "SELECT * FROM RecurringTransaction STARTPOSITION 1 MAXRESULTS 1000"
        return self._query(sql)

    def delete_recurring(self, entity_id: str) -> dict[str, Any]:
        existing = self._read("recurringtransaction", entity_id)
        txn = existing.get("RecurringTransaction")
        if not txn:
            return existing
        body = {"Id": txn["Id"], "SyncToken": txn["SyncToken"]}
        return self._request(
            "POST",
            "recurringtransaction",
            params={"operation": "delete"},
            json_body=body,
        )

    def query_invoices_by_customer(self, name: str) -> dict[str, Any]:
        escaped = _escape_qbo(name)
        customer_sql = f"SELECT * FROM Customer WHERE DisplayName = '{escaped}'"
        customer_response = self._query(customer_sql)
        customers = customer_response.get("QueryResponse", {}).get("Customer", [])
        if not customers:
            customer_sql = (
                f"SELECT * FROM Customer WHERE FullyQualifiedName = '{escaped}'"
            )
            customer_response = self._query(customer_sql)
            customers = customer_response.get("QueryResponse", {}).get("Customer", [])

        invoices: list[dict[str, Any]] = []
        invoice_queries: list[dict[str, Any]] = []
        for customer in customers:
            sql = (
                "SELECT * FROM Invoice "
                f"WHERE CustomerRef = '{customer['Id']}' AND Balance > '0' "
                "ORDERBY TxnDate DESC STARTPOSITION 1 MAXRESULTS 1000"
            )
            response = self._query(sql)
            invoice_queries.append(response)
            invoices.extend(response.get("QueryResponse", {}).get("Invoice", []))

        return {
            "customer_name": name,
            "customer_query": customer_response,
            "customers": customers,
            "invoices": invoices,
            "invoice_queries": invoice_queries,
        }

    def void_invoice(self, entity_id: str) -> dict[str, Any]:
        existing = self._read("invoice", entity_id)
        invoice = existing.get("Invoice")
        if not invoice:
            return existing
        body = {"Id": invoice["Id"], "SyncToken": invoice["SyncToken"]}
        return self._request(
            "POST",
            "invoice",
            params={"operation": "void"},
            json_body=body,
        )

    def get_company_info(self) -> dict[str, Any]:
        return self._request("GET", f"companyinfo/{self.realm_id}")


_CLIENT: QBOClient | None = None


def _client() -> QBOClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = QBOClient()
    return _CLIENT


def list_recurring() -> dict[str, Any]:
    return _client().list_recurring()


def delete_recurring(entity_id: str) -> dict[str, Any]:
    return _client().delete_recurring(entity_id)


def query_invoices_by_customer(name: str) -> dict[str, Any]:
    return _client().query_invoices_by_customer(name)


def void_invoice(entity_id: str) -> dict[str, Any]:
    return _client().void_invoice(entity_id)


def get_company_info() -> dict[str, Any]:
    return _client().get_company_info()
