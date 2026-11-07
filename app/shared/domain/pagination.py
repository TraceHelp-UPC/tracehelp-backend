"""Paginación de consultas (TS08): página pedida, validación de rango y página de resultados."""
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.shared.domain.exceptions import DomainValidationError

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class InvalidPageRequestError(DomainValidationError):
    """Número o tamaño de página no válido, o página fuera de rango (HTTP 400)."""


@dataclass(frozen=True)
class PageRequest:
    """Página pedida por el cliente. Las páginas empiezan en 1."""

    page: int = 1
    size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.page < 1:
            raise InvalidPageRequestError("El número de página debe ser 1 o mayor.")
        if not 1 <= self.size <= MAX_PAGE_SIZE:
            raise InvalidPageRequestError(f"El tamaño de página debe estar entre 1 y {MAX_PAGE_SIZE}.")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    def ensure_in_range(self, total: int) -> None:
        """Una página posterior a la última es un error; la página 1 de un resultado vacío no lo es."""
        pages = total_pages(total, self.size)
        if self.page > max(pages, 1):
            raise InvalidPageRequestError(
                f"La página {self.page} no existe: hay {pages} página(s) de {self.size} resultados."
                if pages
                else f"La página {self.page} no existe: no hay resultados."
            )


def total_pages(total: int, size: int) -> int:
    return math.ceil(total / size) if total else 0


@dataclass(frozen=True)
class Page(Generic[T]):
    items: Sequence[T]
    page: int
    size: int
    total: int

    @property
    def total_pages(self) -> int:
        return total_pages(self.total, self.size)
