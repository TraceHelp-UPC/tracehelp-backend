"""Endpoints REST del Bounded Context Smart Triage.

Triaje multimodal, diagnóstico RAG y validación HITL.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Smart Triage"])
