"""Endpoints REST del Bounded Context Knowledge Management.

Carga, ingesta y vectorización de manuales técnicos.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Knowledge Management"])
