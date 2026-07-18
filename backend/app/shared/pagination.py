"""Пагинация. ТЗ §7 / архитектура §6: обязательна на всех списках.

Здесь — offset-пагинация для справочников М1: они малы и не растут, а
номера страниц заказчику нужнее курсора. Keyset-пагинация обязательна для
stock_movements (AP-5) и появится в modules/stock на этапе 2 — на длинной
истории offset деградирует.
"""

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    size: int = settings.page_size_default

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def get_page_params(
    page: Annotated[int, Query(ge=1, description="Номер страницы, с 1")] = 1,
    size: Annotated[int, Query(ge=1, le=settings.page_size_max)] = settings.page_size_default,
) -> PageParams:
    return PageParams(page=page, size=size)


PageParamsDep = Annotated[PageParams, Depends(get_page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> "Page[T]":
        pages = (total + params.size - 1) // params.size if params.size else 0
        return cls(items=items, total=total, page=params.page, size=params.size, pages=pages)
