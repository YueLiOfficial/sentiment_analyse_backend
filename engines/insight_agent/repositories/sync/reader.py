"""从 MySQL 读取全部文档，作为Milvus同步的原料。
只给离线同步脚本调用；HTTP/Agent在线任务禁止调用，会一次性全量拉取整张表，打爆DB与内存。

统一使用 AsyncSession 会话，和在线db_repository仓储保持完全一致编码范式；
不再使用 engine.connect() 裸连接写法，全项目一套数据库会话写法。
直接映射全局契约 EvidenceDocument，无中间DocumentRecord。
复用 row_mapper 公共转换函数，消除重复映射代码。
"""
import asyncio
from typing import Any

from engines.insight_agent.tools.db_connection import connection_manager
from engines.contracts.evidence import EvidenceDocument
from engines.insight_agent.tools.sql import vector_sql_statement
from engines.insight_agent.tools.row_mapper import map_db_row_to_evidence_document


class DocumentRecordReader:
    def __init__(self):
        self._connection_manager = connection_manager

    async def read_all_document(self) -> list[EvidenceDocument]:
        """
        用于离线查询mysql全量数据，产出EvidenceDocument，交给同步器做向量化写入Milvus
        统一使用session_factory获取AsyncSession，和在线业务仓储写法保持一致
        :return: 标准化全局契约文档实体列表
        """
        session_factory = self._connection_manager.get_async_session_factory()
        async with session_factory() as session:
            stem = vector_sql_statement()
            res = await session.execute(stem)
            rows: list[dict[str, Any]] = [dict(r) for r in res.mappings().all()]

        # 复用公共映射工具，数据库行dict → EvidenceDocument
        result_list: list[EvidenceDocument] = [map_db_row_to_evidence_document(row) for row in rows]
        return result_list


async def main():
    db_r = DocumentRecordReader()
    try:
        result = await db_r.read_all_document()
        print(f"一共获取 {len(result)} 条记录")
    finally:
        # 在事件循环存活期间，主动释放mysql连接池，避免GC后报错
        await connection_manager.dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())