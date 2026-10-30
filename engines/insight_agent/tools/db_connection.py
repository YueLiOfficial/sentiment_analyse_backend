"""MySQL 异步引擎与会话工厂的生命周期管理。
项目业务仓储、离线同步脚本：全部使用 get_async_session_factory() 获取会话工厂；
统一范式 async with session_factory() as session: 执行数据库操作；
业务代码禁止直接调用 engine.connect()裸连接；仅DDL迁移维护脚本可以使用。
"""
from typing import Optional
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from engines.contracts.settings import get_settings


class DataBaseConnectionManager:
    """封装 MySQL 异步引擎与会话工厂与释放
    核心设计：懒加载 + 全局单例连接池；禁止每个查询新建引擎，防止耗尽数据库连接。
    """
    def __init__(self) -> None:
        self._settings = get_settings()
        self._async_engine: Optional[AsyncEngine] = None
        self._async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def get_async_engine(self) -> AsyncEngine:
        if self._async_engine is None:
            self._async_engine = create_async_engine(
                url=self._build_db_url(),
                echo=False,
            )
        return self._async_engine

    def get_async_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        业务代码统一入口，获取会话工厂；
        使用范式：
            factory = connection_manager.get_async_session_factory()
            async with factory() as session:
                await session.execute(...)
        每一次数据库操作，都新建独立session；上下文退出自动归还连接池。
        """
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                self.get_async_engine(),
                expire_on_commit=False,
            )
        return self._async_session_factory

    async def dispose_engine(self) -> None:
        """优雅释放连接池；脚本结束、服务关闭调用，防止连接泄露"""
        self._async_session_factory = None
        if self._async_engine is not None:
            try:
                await self._async_engine.dispose()
            finally:
                self._async_engine = None

    def _build_db_url(self) -> URL:
        settings = get_settings()
        return URL.create(
            drivername="mysql+aiomysql",
            username=settings.DB_USER,
            password=settings.DB_PASSWORD,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
        )


connection_manager = DataBaseConnectionManager()