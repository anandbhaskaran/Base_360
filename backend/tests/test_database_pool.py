import asyncio
from unittest.mock import MagicMock, patch


def test_database_pool_initializes_from_database_url():
    """initialize() must build the URL from settings.database_url with the asyncpg
    driver. Previously it reached for settings.supabase_db_* which don't exist,
    hitting AttributeError → session_factory=None → every request 503s."""
    from app.core import database_pool as dp

    with (
        patch.object(dp, "create_async_engine") as engine,
        patch.object(dp, "async_sessionmaker") as maker,
    ):
        engine.return_value = MagicMock()
        maker.return_value = MagicMock()
        pool = dp.DatabasePool()
        asyncio.run(pool.initialize())

    assert pool.session_factory is not None, "init silently failed — check settings attrs"
    called_url = engine.call_args[0][0]
    assert called_url.startswith("postgresql+asyncpg://"), called_url
    # Async engines must NOT be given the sync QueuePool.
    assert "poolclass" not in engine.call_args.kwargs, "async engine cannot use sync QueuePool"
