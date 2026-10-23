import secrets
from collections import defaultdict
from datetime import datetime, date, timedelta

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import ml_client
from app.config import BASIC_AUTH_USER, BASIC_AUTH_PASS
from app.database import get_db, init_db
from app.models import MLAuth, Order, OrderItem, ProductCost, AdSpend

app = FastAPI(title="Painel Mercado Livre")
templates = Jinja2Templates(directory="app/templates")


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if not BASIC_AUTH_USER or not BASIC_AUTH_PASS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            user, _, password = decoded.partition(":")
        except Exception:
            user, password = "", ""
        if secrets.compare_digest(user, BASIC_AUTH_USER) and secrets.compare_digest(password, BASIC_AUTH_PASS):
            return await call_next(request)

    return Response(
        status_code=401,
        headers={"WWW-Authenticate": "Basic realm=\"Painel Mercado Livre\""},
        content="Autenticação necessária",
    )

try:
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
except RuntimeError:
    pass


@app.on_event("startup")
def on_startup():
    init_db()


def current_auth(db: Session) -> MLAuth | None:
    return db.query(MLAuth).first()


# ---------- Autenticação ----------

@app.get("/auth/login")
def auth_login():
    return RedirectResponse(ml_client.authorize_url())


@app.get("/auth/callback")
def auth_callback(code: str, db: Session = Depends(get_db)):
    token_data = ml_client.exchange_code_for_token(code)
    me = ml_client.get_me(token_data["access_token"])
    ml_client.save_token(db, token_data, ml_user_id=me.get("id"))
    return RedirectResponse("/")


@app.get("/auth/logout")
def auth_logout(db: Session = Depends(get_db)):
    auth = current_auth(db)
    if auth:
        db.delete(auth)
        db.commit()
    return RedirectResponse("/")


# ---------- Sincronização de pedidos ----------

@app.post("/sync")
def sync_orders(db: Session = Depends(get_db), days: int = 30):
    auth = ml_client.get_valid_token(db)
    me = ml_client.get_me(auth.access_token)
    seller_id = str(me["id"])

    date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000-00:00")

    offset = 0
    imported = 0
    shipment_cache: dict[str, str] = {}

    while True:
        page = ml_client.search_orders(auth.access_token, seller_id, offset=offset, date_from=date_from)
        results = page.get("results", [])
        if not results:
            break

        for o in results:
            order_id = o["id"]
            existing = db.query(Order).filter(Order.id == order_id).first()
            if existing:
                db.delete(existing)
                db.flush()

            order_items_raw = o.get("order_items", [])
            sale_fee = sum(oi.get("sale_fee") or 0 for oi in order_items_raw)

            shipping_label = "Sem envio / Combinado"
            logistic_type = None
            shipping = o.get("shipping") or {}
            shipment_id = shipping.get("id")
            if shipment_id:
                shipment_id = str(shipment_id)
                if shipment_id in shipment_cache:
                    logistic_type = shipment_cache[shipment_id]
                else:
                    try:
                        shipment = ml_client.get_shipment(auth.access_token, shipment_id)
                        logistic_type = shipment.get("logistic_type")
                    except Exception:
                        logistic_type = None
                    shipment_cache[shipment_id] = logistic_type
                shipping_label = ml_client.logistic_label(logistic_type)

            order = Order(
                id=order_id,
                date_created=datetime.fromisoformat(o["date_created"].replace("Z", "+00:00")).replace(tzinfo=None),
                status=o.get("status"),
                total_amount=o.get("total_amount") or 0,
                sale_fee=sale_fee,
                shipping_logistic_type=logistic_type,
                shipping_label=shipping_label,
                buyer_nickname=(o.get("buyer") or {}).get("nickname"),
            )
            db.add(order)

            for oi in order_items_raw:
                item = oi.get("item", {})
                db.add(OrderItem(
                    order_id=order_id,
                    item_id=item.get("id"),
                    title=item.get("title"),
                    sku=item.get("seller_sku") or item.get("seller_custom_field"),
                    quantity=oi.get("quantity") or 1,
                    unit_price=oi.get("unit_price") or 0,
                    sale_fee=oi.get("sale_fee") or 0,
                ))
            imported += 1

        db.commit()
        offset += len(results)
        if offset >= page.get("paging", {}).get("total", 0):
            break

    return RedirectResponse(f"/?synced={imported}", status_code=303)


# ---------- Dashboard / relatório ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, days: int = 30, db: Session = Depends(get_db)):
    auth = current_auth(db)
    if auth is None:
        return templates.TemplateResponse(request, "login.html", {})

    since = datetime.utcnow() - timedelta(days=days)
    orders = db.query(Order).filter(Order.date_created >= since).order_by(Order.date_created.desc()).all()

    costs_by_sku = {c.sku: c.cost_price for c in db.query(ProductCost).all()}
    ad_spend_by_day = {a.spend_date: a.amount for a in db.query(AdSpend).all()}

    daily = defaultdict(lambda: {"vendas": 0.0, "taxas_ml": 0.0, "custo_produto": 0.0, "pedidos": 0, "unidades": 0})

    for order in orders:
        day = order.date_created.date()
        bucket = daily[day]
        bucket["vendas"] += order.total_amount
        bucket["taxas_ml"] += order.sale_fee
        bucket["pedidos"] += 1
        for oi in order.items:
            cost = costs_by_sku.get(oi.sku, 0.0)
            bucket["custo_produto"] += cost * oi.quantity
            bucket["unidades"] += oi.quantity

    rows = []
    totals = {"vendas": 0.0, "taxas_ml": 0.0, "custo_produto": 0.0, "ads": 0.0, "lucro": 0.0}
    for day in sorted(daily.keys(), reverse=True):
        b = daily[day]
        ads = ad_spend_by_day.get(day, 0.0)
        lucro = b["vendas"] - b["taxas_ml"] - b["custo_produto"] - ads
        rows.append({
            "date": day,
            "vendas": b["vendas"],
            "taxas_ml": b["taxas_ml"],
            "custo_produto": b["custo_produto"],
            "ads": ads,
            "lucro": lucro,
            "pedidos": b["pedidos"],
            "unidades": b["unidades"],
        })
        totals["vendas"] += b["vendas"]
        totals["taxas_ml"] += b["taxas_ml"]
        totals["custo_produto"] += b["custo_produto"]
        totals["ads"] += ads
        totals["lucro"] += lucro

    missing_cost_skus = sorted({
        oi.sku for order in orders for oi in order.items
        if oi.sku and oi.sku not in costs_by_sku
    })

    return templates.TemplateResponse(request, "dashboard.html", {
        "rows": rows,
        "totals": totals,
        "days": days,
        "missing_cost_skus": missing_cost_skus,
        "has_orders": len(orders) > 0,
        "orders": orders[:100],
    })


# ---------- Vendas detalhadas ----------

@app.get("/sales", response_class=HTMLResponse)
def sales_detail(request: Request, days: int = 90, q: str = "", db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    orders = db.query(Order).filter(Order.date_created >= since).order_by(Order.date_created.desc()).all()

    costs_by_sku = {c.sku: c.cost_price for c in db.query(ProductCost).all()}
    ad_spend_total = sum(
        a.amount for a in db.query(AdSpend).filter(AdSpend.spend_date >= since.date()).all()
    )

    q_lower = q.strip().lower()

    rows = []
    totals = {"vendas": 0.0, "taxas_ml": 0.0, "custo_produto": 0.0, "lucro": 0.0}
    custo_desconhecido = False

    for order in orders:
        for oi in order.items:
            if q_lower and q_lower not in (oi.title or "").lower() and q_lower not in (oi.sku or "").lower():
                continue

            venda = oi.unit_price * oi.quantity
            taxa = oi.sale_fee or 0.0
            custo_unit = costs_by_sku.get(oi.sku)
            if custo_unit is None:
                custo_total = 0.0
                custo_sabido = False
                custo_desconhecido = True
            else:
                custo_total = custo_unit * oi.quantity
                custo_sabido = True

            lucro = venda - taxa - custo_total

            rows.append({
                "order_id": order.id,
                "datetime": order.date_created,
                "shipping_label": order.shipping_label,
                "title": oi.title,
                "sku": oi.sku,
                "quantity": oi.quantity,
                "venda": venda,
                "taxa": taxa,
                "custo_total": custo_total,
                "custo_sabido": custo_sabido,
                "lucro": lucro,
            })

            totals["vendas"] += venda
            totals["taxas_ml"] += taxa
            totals["custo_produto"] += custo_total
            totals["lucro"] += lucro

    totals["ads"] = ad_spend_total
    totals["lucro"] -= ad_spend_total
    totals["investido"] = totals["custo_produto"] + ad_spend_total

    return templates.TemplateResponse(request, "sales.html", {
        "rows": rows,
        "totals": totals,
        "days": days,
        "q": q,
        "custo_desconhecido": custo_desconhecido,
    })


# ---------- Custos por SKU ----------

@app.get("/costs", response_class=HTMLResponse)
def list_costs(request: Request, db: Session = Depends(get_db)):
    costs = db.query(ProductCost).order_by(ProductCost.sku).all()
    return templates.TemplateResponse(request, "costs.html", {"costs": costs})


@app.post("/costs")
def save_cost(sku: str = Form(...), title: str = Form(""), cost_price: float = Form(...), db: Session = Depends(get_db)):
    existing = db.query(ProductCost).filter(ProductCost.sku == sku).first()
    if existing:
        existing.cost_price = cost_price
        if title:
            existing.title = title
    else:
        db.add(ProductCost(sku=sku, title=title, cost_price=cost_price))
    db.commit()
    return RedirectResponse("/costs", status_code=303)


@app.post("/costs/{cost_id}/delete")
def delete_cost(cost_id: int, db: Session = Depends(get_db)):
    cost = db.query(ProductCost).filter(ProductCost.id == cost_id).first()
    if cost:
        db.delete(cost)
        db.commit()
    return RedirectResponse("/costs", status_code=303)


# ---------- Investimento em ads ----------

@app.get("/ads", response_class=HTMLResponse)
def list_ads(request: Request, db: Session = Depends(get_db)):
    ads = db.query(AdSpend).order_by(AdSpend.spend_date.desc()).all()
    return templates.TemplateResponse(request, "ads.html", {"ads": ads})


@app.post("/ads")
def save_ad(spend_date: date = Form(...), amount: float = Form(...), note: str = Form(""), db: Session = Depends(get_db)):
    existing = db.query(AdSpend).filter(AdSpend.spend_date == spend_date).first()
    if existing:
        existing.amount = amount
        existing.note = note
    else:
        db.add(AdSpend(spend_date=spend_date, amount=amount, note=note))
    db.commit()
    return RedirectResponse("/ads", status_code=303)


# ---------- Anúncios (itens) ----------

@app.get("/items", response_class=HTMLResponse)
def list_items(request: Request, db: Session = Depends(get_db)):
    auth = ml_client.get_valid_token(db)
    me = ml_client.get_me(auth.access_token)
    seller_id = str(me["id"])

    result = ml_client.search_items(auth.access_token, seller_id)
    item_ids = result.get("results", [])

    items = []
    for item_id in item_ids:
        try:
            items.append(ml_client.get_item(auth.access_token, item_id))
        except Exception:
            continue

    return templates.TemplateResponse(request, "items.html", {"items": items})


@app.get("/items/new", response_class=HTMLResponse)
def new_item_form(request: Request):
    return templates.TemplateResponse(request, "item_new.html", {})


@app.post("/items/new")
def create_item(
    title: str = Form(...),
    category_id: str = Form(...),
    price: float = Form(...),
    available_quantity: int = Form(...),
    sku: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    auth = ml_client.get_valid_token(db)
    payload = {
        "title": title,
        "category_id": category_id,
        "price": price,
        "currency_id": "BRL",
        "available_quantity": available_quantity,
        "buying_mode": "buy_it_now",
        "condition": "new",
        "listing_type_id": "gold_special",
    }
    if sku:
        payload["seller_custom_field"] = sku
    created = ml_client.create_item(auth.access_token, payload)
    if description:
        try:
            import httpx
            httpx.post(
                f"https://api.mercadolibre.com/items/{created['id']}/description",
                headers={"Authorization": f"Bearer {auth.access_token}"},
                json={"plain_text": description},
                timeout=30,
            )
        except Exception:
            pass
    return RedirectResponse("/items", status_code=303)


@app.get("/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_form(request: Request, item_id: str, db: Session = Depends(get_db)):
    auth = ml_client.get_valid_token(db)
    item = ml_client.get_item(auth.access_token, item_id)
    current_sku = item.get("seller_custom_field")
    cost = None
    if current_sku:
        cost_row = db.query(ProductCost).filter(ProductCost.sku == current_sku).first()
        if cost_row:
            cost = cost_row.cost_price
    return templates.TemplateResponse(request, "item_edit.html", {"item": item, "cost": cost})


@app.post("/items/{item_id}/edit")
def edit_item(
    request: Request,
    item_id: str,
    price: float = Form(...),
    available_quantity: int = Form(...),
    sku: str = Form(""),
    cost_price: str = Form(""),
    db: Session = Depends(get_db),
):
    auth = ml_client.get_valid_token(db)
    payload = {"price": price, "available_quantity": available_quantity}
    if sku:
        payload["seller_custom_field"] = sku
    try:
        ml_client.update_item(auth.access_token, item_id, payload)
    except Exception as exc:
        item = ml_client.get_item(auth.access_token, item_id)
        return templates.TemplateResponse(request, "item_edit.html", {
            "item": item,
            "cost": None,
            "error": str(exc),
        }, status_code=400)

    if sku and cost_price.strip():
        cost_value = float(cost_price)
        existing = db.query(ProductCost).filter(ProductCost.sku == sku).first()
        if existing:
            existing.cost_price = cost_value
        else:
            db.add(ProductCost(sku=sku, cost_price=cost_value))
        db.commit()

    return RedirectResponse("/items", status_code=303)
