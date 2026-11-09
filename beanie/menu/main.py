"""Menu: what the cafe sells and what it costs. Read only, no database."""

from __future__ import annotations

from fastapi import HTTPException

from beanie.common.app import Service
from beanie.common.config import Settings

ITEMS = [
    {"id": "espresso", "name": "Espresso", "price_cents": 220, "available": True},
    {"id": "flat-white", "name": "Flat white", "price_cents": 340, "available": True},
    {"id": "cappuccino", "name": "Cappuccino", "price_cents": 330, "available": True},
    {"id": "cold-brew", "name": "Cold brew", "price_cents": 390, "available": True},
    {"id": "croissant", "name": "Butter croissant", "price_cents": 280, "available": True},
    {"id": "banana-bread", "name": "Banana bread", "price_cents": 310, "available": False},
]


def create_app(settings: Settings | None = None, tracer_provider=None):
    settings = settings or Settings.from_env()
    service = Service("menu", settings, tracer_provider=tracer_provider)
    app = service.app

    @app.get("/items", tags=["menu"])
    async def list_items():
        return ITEMS

    @app.get("/items/{item_id}", tags=["menu"])
    async def get_item(item_id: str):
        for item in ITEMS:
            if item["id"] == item_id:
                return item
        raise HTTPException(404, "no such item")

    app.state.service = service
    return app
