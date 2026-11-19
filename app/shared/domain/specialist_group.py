"""Grupos de especialistas L2 (shared kernel).

Los usan IAM (grupo del especialista, US09) y Helpdesk (grupo al que se escala un ticket, US17).
"""
from enum import StrEnum


class SpecialistGroup(StrEnum):
    REDES = "REDES"
    APLICACIONES = "APLICACIONES"
    INFRAESTRUCTURA = "INFRAESTRUCTURA"
    SEGURIDAD = "SEGURIDAD"
