import logging
from dataclasses import dataclass
from typing import Any, Set

from redis import Redis as SyncRedis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, ResponseError, TimeoutError, WatchError

from common.dataclass.singleton import Singleton
from sudoku.settings import REDIS_HOST

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommitGuard:
    key: str
    kind: str
    expected: str | dict[str, str] | None


@dataclass(frozen=True)
class ExpiringValue:
    value: str
    ttl_seconds: int


@dataclass
class RedisConfig:
    host: str = REDIS_HOST
    port: int = 6379
    db: int = 1
    password: str | None = None
    max_connections: int = 50
    socket_keepalive: bool = True
    default_expiry: int = 7200


class RedisClient(metaclass=Singleton):

    def __init__(self: "RedisClient", config: RedisConfig | None = None) -> None:
        self._config: RedisConfig = config or RedisConfig()
        self._redis_client: Redis = self._create_connection()

    def _create_connection(self: "RedisClient") -> Redis:
        try:
            return Redis(
                host=self._config.host,
                port=self._config.port,
                db=self._config.db,
                password=self._config.password,
                decode_responses=True,
                max_connections=self._config.max_connections,
                socket_keepalive=self._config.socket_keepalive,
            )
        except Exception as e:
            logger.error(f"Failed to create Redis connection: {e}")
            raise

    def _create_connection_sync(self: "RedisClient") -> SyncRedis:
        try:
            return SyncRedis(
                host=self._config.host,
                port=self._config.port,
                db=self._config.db,
                password=self._config.password,
                decode_responses=True,
                max_connections=self._config.max_connections,
                socket_keepalive=self._config.socket_keepalive,
            )
        except Exception as e:
            logger.error(f"Failed to create Redis connection: {e}")
            raise

    async def close(self: "RedisClient") -> None:
        try:
            await self._redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    async def get(self: "RedisClient", key: str, default: Any = None) -> Any:
        try:
            result: str | None = await self._redis_client.get(key)
            return result if result is not None else default
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting key '{key}': {e}")
            raise

    async def set(
        self: "RedisClient",
        key: str,
        value: Any,
        expiry: int | None = None,
    ) -> None:
        try:
            expire_time: int = expiry or self._config.default_expiry
            await self._redis_client.set(key, value, ex=expire_time)
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting key '{key}': {e}")
            raise

    async def expire_if_value(
        self,
        key: str,
        value: str,
        expiry: int,
    ) -> bool:
        script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('expire', KEYS[1], ARGV[2])
            end
            return 0
        """
        try:
            result = await self._redis_client.eval(  # type: ignore[misc]
                script,
                1,
                key,
                value,
                str(expiry),
            )
            return bool(result)
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error renewing key '{key}': {e}")
            raise

    async def acquire_room_presence(self, prefix: str, key: str, token: str, expiry: int, epoch: str = '') -> bool:
        """Start/join a room atomically, discarding abandoned data before its first lease."""
        script = """
            if redis.call('exists', KEYS[1]) == 1 then return 0 end
            if #redis.call('keys', ARGV[1] .. ':presence:*') == 0 then
                for _, key in ipairs(redis.call('keys', ARGV[1] .. ':*')) do
                    redis.call('del', key)
                end
                if ARGV[4] ~= '' then redis.call('set', ARGV[1] .. ':epoch', ARGV[4]) end
            end
            redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
            return 1
        """
        return bool(await self._redis_client.eval(script, 1, key, prefix, token, expiry, epoch))

    async def release_room_presence(self, prefix: str, key: str, token: str) -> bool:
        """Release only this lease; last departure removes only this room's keys."""
        script = """
            local current = redis.call('get', KEYS[1])
            if current and current ~= ARGV[2] then return 0 end
            if current then redis.call('del', KEYS[1]) end
            if #redis.call('keys', ARGV[1] .. ':presence:*') == 0 then
                for _, key in ipairs(redis.call('keys', ARGV[1] .. ':*')) do
                    redis.call('del', key)
                end
            end
            return current and 1 or 0
        """
        return bool(await self._redis_client.eval(script, 1, key, prefix, token))

    def exists_sync(self, key: str) -> bool:
        client = self._create_connection_sync()
        try:
            return bool(client.exists(key))
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error checking key '{key}': {e}")
            raise
        finally:
            client.close()  # type: ignore[no-untyped-call]

    async def hset_if_value(
        self,
        condition_key: str,
        expected_value: str,
        key: str,
        field: str,
        value: Any,
    ) -> bool:
        script = """
            if redis.call('get', KEYS[1]) ~= ARGV[1] then
                return 0
            end
            redis.call('hset', KEYS[2], ARGV[2], ARGV[3])
            return 1
        """
        try:
            result = await self._redis_client.eval(  # type: ignore[misc]
                script,
                2,
                condition_key,
                key,
                expected_value,
                field,
                value,
            )
            return bool(result)
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error updating fenced hash field '{field}': {e}")
            raise

    async def read_hashes(self, keys: list[str]) -> list[dict[str, Any]]:
        async with self._redis_client.pipeline(transaction=True) as pipeline:
            for key in keys:
                pipeline.hgetall(key)
            return await pipeline.execute()

    async def compare_and_replace_hashes(
        self, condition_key: str, expected_value: str, version_key: str,
        expected_version: dict[str, str] | None,
        hashes: dict[str, dict[str, Any]],
        *, hash_updates: dict[str, dict[str, Any]] | None = None,
        expected_fields: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        """CAS a snapshot, fenced by the owner's lease. No game rules here."""
        try:
            async with self._redis_client.pipeline(transaction=True) as pipeline:
                await pipeline.watch(condition_key, version_key, *(expected_fields or {}))
                if await pipeline.get(condition_key) != expected_value:
                    return "replaced"
                current = await pipeline.hgetall(version_key)
                if expected_version is None:
                    if current:
                        return "conflict"
                elif any(current.get(key) != value for key, value in expected_version.items()):
                    return "conflict"
                for key, fields in (expected_fields or {}).items():
                    for field, value in fields.items():
                        if await pipeline.hget(key, field) != value:
                            return "conflict"
                pipeline.multi()
                for key, mapping in hashes.items():
                    pipeline.delete(key)
                    if mapping:
                        pipeline.hset(key, mapping=mapping)
                for key, mapping in (hash_updates or {}).items():
                    if mapping:
                        pipeline.hset(key, mapping=mapping)
                await pipeline.execute()
                return "saved"
        except WatchError:
            return "conflict"

    @staticmethod
    async def _guards_match(reader, guards: list[CommitGuard]) -> bool:
        for guard in guards:
            if guard.expected is None:
                if await reader.exists(guard.key):
                    return False
            elif guard.kind == 'string':
                if await reader.get(guard.key) != guard.expected:
                    return False
            elif guard.kind == 'hash':
                fields = await reader.hgetall(guard.key)
                if any(fields.get(key) != value for key, value in guard.expected.items()):
                    return False
            else:
                raise ValueError('Unknown guard kind')
        return True

    async def guards_match(self, guards: list[CommitGuard]) -> bool:
        return await self._guards_match(self._redis_client, guards)

    async def compare_and_write_batch(self, guards: list[CommitGuard],
                                      hashes: dict[str, dict], strings: dict[str, ExpiringValue]) -> str:
        """Commit all guarded snapshots and expiring markers together, or none."""
        if any(type(value.ttl_seconds) is not int or value.ttl_seconds <= 0 for value in strings.values()):
            raise ValueError('A positive integer TTL is required')
        try:
            async with self._redis_client.pipeline(transaction=True) as pipeline:
                if guards:
                    await pipeline.watch(*(guard.key for guard in guards))
                if not await self._guards_match(pipeline, guards):
                    return 'conflict'
                pipeline.multi()
                for key, mapping in hashes.items():
                    pipeline.delete(key)
                    if mapping:
                        pipeline.hset(key, mapping=mapping)
                for key, value in strings.items():
                    pipeline.set(key, value.value, ex=value.ttl_seconds)
                await pipeline.execute()
                return 'saved'
        except WatchError:
            return 'conflict'

    async def incr(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.incr(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error incrementing key '{key}': {e}")
            raise

    async def decr(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.decr(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error decrementing key '{key}': {e}")
            raise

    async def sadd(self: "RedisClient", key: str, value: Any) -> int:
        try:
            result: int = await self._redis_client.sadd(key, value)  # type: ignore
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error adding to set '{key}': {e}")
            raise

    async def srem(self: "RedisClient", key: str, *value: Any) -> int:
        try:
            result: int = await self._redis_client.srem(key, *value) # type: ignore
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error removing from set '{key}': {e}")
            raise
    
    async def sismember(self: "RedisClient", key: str, value: Any) -> bool:
        try:
            result: bool = await self._redis_client.sismember(key, value)  # type: ignore
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error checking membership in set '{key}': {e}")
            raise
    
    async def smembers(self: "RedisClient", key: str) -> Set[Any]:
        try:
            result: set[Any] = await self._redis_client.smembers(key)  # type: ignore
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting members of set '{key}': {e}")
            raise

    async def append(self: "RedisClient", key: str, value: str) -> int:
        try:
            result: int = await self._redis_client.append(key, value)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error appending to key '{key}': {e}")
            raise

    async def getrange(self: "RedisClient", key: str, start: int, end: int) -> str:
        try:
            result: str = await self._redis_client.getrange(key, start, end)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting range from key '{key}': {e}")
            raise

    async def setrange(
        self: "RedisClient", key: str, offset: int, value: str
    ) -> int:
        try:
            result: int = await self._redis_client.setrange(key, offset, value)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting range for key '{key}': {e}")
            raise

    async def mget(self: "RedisClient", keys: list[str]) -> list[Any]:
        try:
            result: list[Any] = await self._redis_client.mget(keys)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting multiple keys: {e}")
            raise

    async def mset(self: "RedisClient", mapping: dict[str, Any]) -> None:
        try:
            await self._redis_client.mset(mapping)  # type: ignore[unused-ignore]
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting multiple keys: {e}")
            raise

    async def strlen(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.strlen(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting string length for key '{key}': {e}")
            raise

    async def getdel(self: "RedisClient", key: str) -> Any:
        try:
            result: Any = await self._redis_client.getdel(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting and deleting key '{key}': {e}")
            raise

    async def push(self: "RedisClient", key: str, value: Any) -> int:
        try:
            result: int = await self._redis_client.rpush(key, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error pushing to list '{key}': {e}")
            raise

    async def lpush(self: "RedisClient", key: str, value: Any) -> int:
        try:
            result: int = await self._redis_client.lpush(key, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error left-pushing to list '{key}': {e}")
            raise

    async def pop(self: "RedisClient", key: str) -> Any:
        try:
            result: Any = await self._redis_client.rpop(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error popping from list '{key}': {e}")
            raise

    async def lpop(self: "RedisClient", key: str) -> Any:
        try:
            result: Any = await self._redis_client.lpop(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error left-popping from list '{key}': {e}")
            raise

    async def rem(self: "RedisClient", key: str, value: Any) -> int:
        try:
            result: int = await self._redis_client.lrem(key, 1, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error removing from list '{key}': {e}")
            raise

    async def range(self: "RedisClient", key: str, start: int = 0, end: int = -1) -> list[Any]:
        try:
            result: list[Any] = await self._redis_client.lrange(key, start, end)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting range from list '{key}': {e}")
            raise

    async def exist_in(self: "RedisClient", key: str, value: str) -> int | None:
        try:
            result: int | None = await self._redis_client.lpos(key, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error finding position in list '{key}': {e}")
            raise

    async def length(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.llen(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting list length for key '{key}': {e}")
            raise

    async def lindex(self: "RedisClient", key: str, index: int) -> Any:
        try:
            result: Any = await self._redis_client.lindex(key, index)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting list element at index {index} for key '{key}': {e}")
            raise

    async def linsert(
        self: "RedisClient", key: str, where: str, pivot: Any, value: Any
    ) -> int:
        try:
            result: int = await self._redis_client.linsert(key, where, pivot, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error inserting in list '{key}': {e}")
            raise

    async def lset(self: "RedisClient", key: str, index: int, value: Any) -> None:
        try:
            await self._redis_client.lset(key, index, value)  # type: ignore[misc]
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting list element at index {index} for key '{key}': {e}")
            raise

    async def ltrim(self: "RedisClient", key: str, start: int, end: int) -> None:
        try:
            await self._redis_client.ltrim(key, start, end)  # type: ignore[misc]
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error trimming list '{key}': {e}")
            raise

    async def blpop(
        self: "RedisClient", key: str, timeout: int = 0
    ) -> tuple[str, Any] | None:
        try:
            result: tuple[str, Any] | None = await self._redis_client.blpop(  # type: ignore[misc]
                [key], timeout=timeout
            )
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error blocking left-pop from list '{key}': {e}")
            raise

    async def brpop(
        self: "RedisClient", key: str, timeout: int = 0
    ) -> tuple[str, Any] | None:
        try:
            result: tuple[str, Any] | None = await self._redis_client.brpop(  # type: ignore[misc]
                [key], timeout=timeout
            )
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error blocking right-pop from list '{key}': {e}")
            raise

    async def hget(self: "RedisClient", key: str, field: str) -> Any:
        try:
            result: Any = await self._redis_client.hget(key, field)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting hash field '{field}' from key '{key}': {e}")
            raise

    async def hset(
        self: "RedisClient", key: str, field: str, value: Any
    ) -> int:
        try:
            result: int = await self._redis_client.hset(key, field, value)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting hash field '{field}' for key '{key}': {e}")
            raise

    async def hdel(self: "RedisClient", key: str, field: str) -> int:
        try:
            result: int = await self._redis_client.hdel(key, field)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error deleting hash field '{field}' from key '{key}': {e}")
            raise

    async def hexist(self: "RedisClient", key: str, field: str) -> bool:
        try:
            result: bool = await self._redis_client.hexists(key, field)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error checking hash field '{field}' for key '{key}': {e}")
            raise

    async def hgetall(self: "RedisClient", key: str) -> dict[str, Any]:
        try:
            result: dict[str, Any] = await self._redis_client.hgetall(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting all fields from hash '{key}': {e}")
            raise

    async def hkeys(self: "RedisClient", key: str) -> list[str]:
        try:
            result: list[str] = await self._redis_client.hkeys(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting hash keys for key '{key}': {e}")
            raise

    async def hvals(self: "RedisClient", key: str) -> list[Any]:
        try:
            result: list[Any] = await self._redis_client.hvals(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting hash values for key '{key}': {e}")
            raise

    async def hlen(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.hlen(key)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting hash length for key '{key}': {e}")
            raise

    async def hincrby(self: "RedisClient", key: str, field: str, increment: int) -> int:
        try:
            result: int = await self._redis_client.hincrby(key, field, increment)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(
                f"Error incrementing hash field '{field}' for key '{key}': {e}"
            )
            raise

    async def hmget(
        self: "RedisClient", key: str, fields: list[str]
    ) -> list[Any]:
        try:
            result: list[Any] = await self._redis_client.hmget(key, fields)  # type: ignore[misc]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting multiple hash fields for key '{key}': {e}")
            raise

    async def hmset(self: "RedisClient", key: str, mapping: dict[str, Any]) -> None:
        try:
            await self._redis_client.hset(key, mapping=mapping)  # type: ignore[misc]
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting multiple hash fields for key '{key}': {e}")
            raise

    async def hscan(
        self: "RedisClient",
        key: str,
        cursor: int = 0,
        match: str | None = None,
        count: int = 10,
    ) -> tuple[int, dict[str, Any]]:
        try:
            result: tuple[int, dict[str, Any]] = await self._redis_client.hscan(  # type: ignore[unused-ignore]
                key, cursor=cursor, match=match, count=count
            )
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error scanning hash '{key}': {e}")
            raise

    async def exists(self: "RedisClient", key: str) -> bool:
        try:
            result: int = await self._redis_client.exists(key)  # type: ignore[unused-ignore]
            return result > 0
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error checking existence of key '{key}': {e}")
            raise

    async def delete(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.delete(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error deleting key '{key}': {e}")
            raise

    async def delete_pattern(self: "RedisClient", pattern: str) -> int:
        try:
            keys = self._redis_client.scan_iter(match=pattern)
            counter = 0
            async for key in keys:
                await self._redis_client.delete(key)
                counter += 1
            return counter
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error deleting keys matching pattern '{pattern}': {e}")
            raise

    async def expire(self: "RedisClient", key: str, time: int) -> bool:
        try:
            result: bool = await self._redis_client.expire(key, time)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error setting expiry for key '{key}': {e}")
            raise

    async def ttl(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.ttl(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting TTL for key '{key}': {e}")
            raise

    async def keys(self: "RedisClient", pattern: str = "*") -> list[str]:
        try:
            result: list[str] = await self._redis_client.keys(pattern)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting keys matching pattern '{pattern}': {e}")
            raise

    async def scan(
        self: "RedisClient",
        cursor: int = 0,
        match: str | None = None,
        count: int = 10,
    ) -> tuple[int, list[str]]:
        try:
            result: tuple[int, list[str]] = await self._redis_client.scan(  # type: ignore[unused-ignore]
                cursor=cursor, match=match, count=count
            )
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error scanning keys: {e}")
            raise

    async def persist(self: "RedisClient", key: str) -> bool:
        try:
            result: bool = await self._redis_client.persist(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error persisting key '{key}': {e}")
            raise

    async def unlink(self: "RedisClient", key: str) -> int:
        try:
            result: int = await self._redis_client.unlink(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error unlinking key '{key}': {e}")
            raise

    async def type(self: "RedisClient", key: str) -> str:
        try:
            result: str = await self._redis_client.type(key)  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting type of key '{key}': {e}")
            raise

    async def randomkey(self: "RedisClient") -> str | None:
        try:
            result: str | None = await self._redis_client.randomkey()  # type: ignore[unused-ignore]
            return result
        except (ResponseError, ConnectionError, TimeoutError) as e:
            logger.error(f"Error getting random key: {e}")
            raise
