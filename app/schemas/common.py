from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    total_pages: int
    page: int
    page_size: int

    @classmethod
    def create(
        cls,
        *,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PageResponse[T]":
        return cls(
            items=items,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
            page=page,
            page_size=page_size,
        )
