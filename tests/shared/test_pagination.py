"""Pruebas unitarias de la paginación (T17, TS08)."""
import pytest

from app.shared.domain.pagination import MAX_PAGE_SIZE, InvalidPageRequestError, Page, PageRequest


def test_offset_starts_at_zero_for_the_first_page():
    assert PageRequest(page=1, size=20).offset == 0
    assert PageRequest(page=3, size=20).offset == 40


@pytest.mark.parametrize("page", [0, -1])
def test_page_must_be_one_or_more(page):
    with pytest.raises(InvalidPageRequestError):
        PageRequest(page=page)


@pytest.mark.parametrize("size", [0, MAX_PAGE_SIZE + 1])
def test_size_must_be_between_one_and_the_maximum(size):
    with pytest.raises(InvalidPageRequestError):
        PageRequest(size=size)


def test_first_page_of_an_empty_result_is_valid():
    PageRequest(page=1).ensure_in_range(0)


@pytest.mark.parametrize(("page", "total"), [(2, 0), (4, 57), (2, 20)])
def test_pages_after_the_last_are_out_of_range(page, total):
    with pytest.raises(InvalidPageRequestError) as exc:
        PageRequest(page=page, size=20).ensure_in_range(total)
    assert f"La página {page} no existe" in exc.value.detail


def test_last_page_is_in_range():
    PageRequest(page=3, size=20).ensure_in_range(57)


def test_total_pages_rounds_up():
    assert Page(items=[], page=1, size=20, total=57).total_pages == 3
    assert Page(items=[], page=1, size=20, total=0).total_pages == 0
