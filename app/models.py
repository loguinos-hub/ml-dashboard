from datetime import datetime, date

from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MLAuth(Base):
    __tablename__ = "ml_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ml_user_id: Mapped[str] = mapped_column(String, nullable=True)
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ProductCost(Base):
    __tablename__ = "product_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
    cost_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdSpend(Base):
    __tablename__ = "ad_spend"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spend_date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    note: Mapped[str] = mapped_column(String, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # ML order id
    date_created: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    sale_fee: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_logistic_type: Mapped[str] = mapped_column(String, nullable=True)  # full, flex, drop_off, self_service...
    shipping_label: Mapped[str] = mapped_column(String, nullable=True)  # texto amigável: Full, Flex, Coleta, Correios
    buyer_nickname: Mapped[str] = mapped_column(String, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=True)
    sku: Mapped[str] = mapped_column(String, nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    sale_fee: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped["Order"] = relationship(back_populates="items")
