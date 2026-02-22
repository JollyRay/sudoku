from typing import Any, Awaitable, Awaitable, List, Union

from redis.asyncio import Redis

from common.dataclass.singleton import Singleton
from sudoku.settings import REDIS_HOST


class RedisClient(metaclass=Singleton):
    def __init__(self: 'RedisClient') -> None:
        self.redis_client = self.get_redis_client()
    
    @staticmethod
    def get_redis_client() -> Redis:
        return Redis(
            host=REDIS_HOST,
            port=6379,
            db=1,
            decode_responses=True,
        )

    async def push(self, name: str, value: Any) -> int:
        result = self.redis_client.rpush(name, value)
        if isinstance(result, Awaitable):
            result = await result
        return result

    async def rem(self, name: str, value: Any) -> int:
        result = self.redis_client.lrem(name, 1, value)
        if isinstance(result, Awaitable):
            result = await result
        return result

    async def has(self, name: str) -> bool:
        result = self.redis_client.exists(name)
        if isinstance(result, Awaitable):
            result = await result
        return result

    async def get(self, name: str, default: Any = None) -> Any:
        result = self.redis_client.get(name)
        if isinstance(result, Awaitable):
            result = await result
        if result is None:
            return default
        return result

    async def range(self, name: str) -> List[Any]:
        result = self.redis_client.lrange(name, 0, -1)
        if isinstance(result, Awaitable):
            result = await result
        return result
    
    async def exist_in(self, name: str, value: str) -> Union[str, None]:
        result: Union[str, None, Awaitable[str | None]] = self.redis_client.lpos(name, value) # type: ignore
        if isinstance(result, Awaitable):
            result = await result
        return result

    async def set(self, name: str, value: Any) -> None:
        result = self.redis_client.set(name, value, ex=7200)
        if isinstance(result, Awaitable):
            await result
    
    async def delete(self, name: str) -> None:
        result = self.redis_client.delete(name)
        if isinstance(result, Awaitable):
            await result

    async def lenght(self, name: str) -> int:
        result: Union[int, Awaitable[int]] = self.redis_client.llen(name)
        if isinstance(result, Awaitable):
            result = await result
        return result
        