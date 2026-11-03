"""Endpoints REST del Bounded Context IAM.

Autenticación, usuarios, roles y configuración RAG.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter

router = APIRouter(tags=["IAM"])
