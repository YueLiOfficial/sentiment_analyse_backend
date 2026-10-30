"""Milvus 知识库同步协调器，离线脚本入口
重要：本模块只用于离线脚本；**HTTP/在线Agent任务严禁调用full_sync**；
会全量读取MySQL全部数据，大批量向量化，会直接压垮服务。
"""
import asyncio
from loguru import logger
from engines.insight_agent.repositories.vector_repository import VectorSearchRepository
from engines.insight_agent.repositories.sync.reader import DocumentRecordReader
from engines.contracts.evidence import EvidenceDocument


class DocumentRecordSynchronizer:
    def __init__(self):
        self._vector_repo = VectorSearchRepository()
        self._reader = DocumentRecordReader()

    async def full_sync(self, drop_existing: bool = False) -> int:
        """
        全量同步：MySQL全量数据 → List[EvidenceDocument] → 向量化 → upsert写入Milvus
        pymilvus是【同步阻塞SDK】，不能直接在async协程调用，要用asyncio.to_thread丢线程池，防止阻塞事件循环
        :param drop_existing: True 删除重建集合；False 增量upsert，生产环境一般用False
        :return: 成功写入Milvus文档数量
        """
        logger.info("开始执行全量同步：读取MySQL全部文档...")
        # 1、读取MySQL全量数据，得到标准化EvidenceDocument列表（这一步是async异步MySQL查询）
        all_docs: list[EvidenceDocument] = await self._reader.read_all_document()
        logger.info(f"读取完成，有效文档数量：{len(all_docs)}")
        # ------------------------------
        # 重点：asyncio.to_thread(同步函数对象, 参数...)
        # 注意：第一个参数只写函数对象，【不能加括号()】，加括号会当场执行、to_thread失效！
        # drop_existing=drop_existing 是传给 ensure_collection 的关键字参数
        # 把Milvus同步阻塞操作交给后台子线程执行，主线程asyncio事件循环不被卡住
        # ------------------------------
        await asyncio.to_thread(
            self._vector_repo.ensure_collection,  # 传入函数对象，不要()
            drop_existing=drop_existing            # 函数需要的关键字参数写在这里
        )
        # 把upsert_documents同步方法丢进线程池，all_docs是该函数的位置入参
        count = await asyncio.to_thread(
            self._vector_repo.upsert_documents,   # 传入函数对象，不要()
            all_docs
        )
        logger.success(f"全量同步完成，写入Milvus {count} 条记录")
        return count


async def main():
    """同步脚本主函数，sync_main.py调用"""
    sync = DocumentRecordSynchronizer()
    try:
        await sync.full_sync(drop_existing=False)
    finally:
        sync._vector_repo.close()
        # 脚本测试环境，事件循环存活期间主动释放mysql连接池，避免GC析构报Event loop closed警告
        from engines.insight_agent.tools.db_connection import connection_manager
        await connection_manager.dispose_engine()

if __name__ == "__main__":
    asyncio.run(main())