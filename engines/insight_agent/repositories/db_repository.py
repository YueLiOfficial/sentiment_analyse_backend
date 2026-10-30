import asyncio
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from engines.insight_agent.tools.db_connection import connection_manager
from engines.insight_agent.tools.search_results import SearchResult
from engines.contracts.evidence import EvidenceDocument
from engines.insight_agent.tools.sql import db_sql_statement
from engines.insight_agent.tools.row_mapper import map_db_row_to_evidence_document


class DataBaseSearchRepository:

    def __init__(self):
        self.connection_manager = connection_manager

    async def db_call(self,query:str,limit:int=100) -> SearchResult:
        """
        MySQL关键词在线召回入口
        :param query: 用户原始检索关键词
        :param limit: 返回topN条数
        :return: SearchResult，retrieval_results内部是EvidenceDocument列表；通道标记db_call
        """
        # 获取session
        factory = connection_manager.get_async_session_factory()
        async with factory() as sesison:
            # 查询结果
            rows = await self._fetch_db_rows(sesison, query, limit)

        # 将结果转换为SearchResult
        return SearchResult(
            retrieval_channel="db_call",
            retrieval_results=[map_db_row_to_evidence_document(row) for row in rows] # type: ignore
        )

    async def _fetch_db_rows(self, session: AsyncSession, query, limit) -> list[dict]:
        """执行SQL，把Result结果集转为dict行列表"""
        # 获取sql语句
        sql = db_sql_statement()
        # 拼接查询条件
        params = {
            "search_term": f"%{query}%",
            "limit": limit
        }
        # 执行sql
        res = await session.execute(sql, params)

        return [dict(r) for r in res.mappings().all()]


# 测试函数
async def main():
    """本地测试入口：直接运行脚本测试MySQL关键词召回"""
    db_r = DataBaseSearchRepository()
    try:
        result = await db_r.db_call("高考", limit=20)
        print(f"一共获取 {len(result.retrieval_results)} 条记录")
        for item in result.retrieval_results[:3]:
            print(item.platform, item.content[:60])
    finally:
        # 在事件循环存活期间，主动释放mysql连接池，避免GC后报错
        await connection_manager.dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())