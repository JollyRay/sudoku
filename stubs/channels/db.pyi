from typing import (
    Any,
    TypeVar,
    Callable,
    Awaitable,
    ParamSpec,
)

P = ParamSpec('P')
R = TypeVar('R')

def database_sync_to_async(
    func: Callable[P, R],
    *,
    thread_sensitive: bool = True
) -> Callable[P, Awaitable[R]]: ...
