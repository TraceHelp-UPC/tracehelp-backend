"""Endpoints REST del Bounded Context Analytics.

Métricas, auditoría, ROI y reportes.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Analytics"])
