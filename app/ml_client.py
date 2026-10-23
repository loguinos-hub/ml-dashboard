from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import (
    ML_API_BASE,
    ML_AUTH_URL,
    ML_CLIENT_ID,
    ML_CLIENT_SECRET,
    ML_REDIRECT_URI,
)
from app.models import MLAuth

LOGISTIC_LABELS = {
    "fulfillment": "Full",
    "cross_docking": "Coleta",
    "drop_off": "Agência/Correios",
    "self_service": "Flex",
    "not_specified": "Combinado com comprador",
    "default": "Padrão",
}


class MLAuthError(Exception):
    pass


def authorize_url() -> str:
    return (
        f"{ML_AUTH_URL}?response_type=code&client_id={ML_CLIENT_ID}"
        f"&redirect_uri={ML_REDIRECT_URI}"
    )


def exchange_code_for_token(code: str) -> dict:
    resp = httpx.post(
        f"{ML_API_BASE}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "code": code,
            "redirect_uri": ML_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    resp = httpx.post(
        f"{ML_API_BASE}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def save_token(db: Session, token_data: dict, ml_user_id: str | None = None) -> MLAuth:
    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 21600))
    auth = db.query(MLAuth).first()
    if auth is None:
        auth = MLAuth(
            ml_user_id=str(ml_user_id or token_data.get("user_id", "")),
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=expires_at,
        )
        db.add(auth)
    else:
        auth.access_token = token_data["access_token"]
        auth.refresh_token = token_data["refresh_token"]
        auth.expires_at = expires_at
        if ml_user_id:
            auth.ml_user_id = str(ml_user_id)
    db.commit()
    db.refresh(auth)
    return auth


def get_valid_token(db: Session) -> MLAuth:
    auth = db.query(MLAuth).first()
    if auth is None:
        raise MLAuthError("Nenhuma conta do Mercado Livre conectada ainda. Faça login primeiro.")
    if auth.expires_at <= datetime.utcnow() + timedelta(minutes=2):
        token_data = refresh_access_token(auth.refresh_token)
        auth = save_token(db, token_data, auth.ml_user_id)
    return auth


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_me(access_token: str) -> dict:
    resp = httpx.get(f"{ML_API_BASE}/users/me", headers=_headers(access_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_orders(access_token: str, seller_id: str, offset: int = 0, limit: int = 50, date_from: str | None = None) -> dict:
    params = {
        "seller": seller_id,
        "offset": offset,
        "limit": limit,
        "sort": "date_desc",
    }
    if date_from:
        params["order.date_created.from"] = date_from
    resp = httpx.get(
        f"{ML_API_BASE}/orders/search",
        headers=_headers(access_token),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_shipment(access_token: str, shipment_id: str) -> dict:
    resp = httpx.get(
        f"{ML_API_BASE}/shipments/{shipment_id}",
        headers=_headers(access_token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def logistic_label(logistic_type: str | None) -> str:
    if not logistic_type:
        return "Desconhecido"
    return LOGISTIC_LABELS.get(logistic_type, logistic_type)


def search_items(access_token: str, seller_id: str, offset: int = 0, limit: int = 50) -> dict:
    resp = httpx.get(
        f"{ML_API_BASE}/users/{seller_id}/items/search",
        headers=_headers(access_token),
        params={"offset": offset, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_item(access_token: str, item_id: str) -> dict:
    resp = httpx.get(f"{ML_API_BASE}/items/{item_id}", headers=_headers(access_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_item(access_token: str, item_id: str, payload: dict) -> dict:
    resp = httpx.put(
        f"{ML_API_BASE}/items/{item_id}",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_item(access_token: str, payload: dict) -> dict:
    resp = httpx.post(
        f"{ML_API_BASE}/items",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
