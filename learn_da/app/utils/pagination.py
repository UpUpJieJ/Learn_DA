from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class PaginationResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


def create_pagination_result(
    items: list[T],
    total: int,
    page: int,
    page_size: int,
) -> PaginationResult[T]:
    total_pages = ceil(total / page_size) if total > 0 else 0
    return PaginationResult(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1 and total_pages > 0,
    )
