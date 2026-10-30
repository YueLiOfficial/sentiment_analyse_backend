"""Milvus 向量仓储：写入upsert、混合检索
重要：pymilvus是同步阻塞SDK；在asyncio协程里面调用，**上层调用方必须套asyncio.to_thread丢线程池**，本模块内部不做异步封装。
区分两种场景：
1. 离线同步：upsert_documents，批量写入文档向量；
2. 在线检索：vector_call，接收用户query，生成查询向量，执行dense + sparse hybrid_search；

实体说明：
MySQL/Milvus两侧全部映射为全局契约 EvidenceDocument，本项目取消中间仓储DocumentRecord。
"""
from dataclasses import fields
from datetime import datetime
from typing import Any
from loguru import logger
from pymilvus import AnnSearchRequest, MilvusClient, RRFRanker
from engines.contracts.evidence import Engagement, EvidenceDocument
from engines.contracts.settings import get_settings
from engines.insight_agent.tools.search_results import SearchHit
from engines.insight_agent.tools.vector.embedder import VectorEmbedder
from engines.insight_agent.tools.vector.builder import CollectionSchemaBuilder, MILVUS_OUTPUT_FIELDS


class VectorSearchRepository:
    def __init__(self):
        self._settings = get_settings()
        self.collection_name = self._settings.MILVUS_INSIGHT_COLLECTION
        self._embedder = VectorEmbedder()   # BGE‑M3向量化编码器
        self._milvus_client: MilvusClient | None = None

    @property
    def milvus_client(self) -> MilvusClient:
        """懒加载Milvus客户端，第一次访问才创建连接，避免程序启动就建立向量库连接"""
        if self._milvus_client is None:
            self._milvus_client = MilvusClient(
                uri=self._settings.MILVUS_URI,
                db_name=self._settings.MILVUS_DB_NAME
            )
        return self._milvus_client

    def close(self) -> None:
        """关闭Milvus客户端，释放连接；脚本结束调用"""
        if self._milvus_client is not None:
            try:
                self._milvus_client.close()
            finally:
                self._milvus_client = None

    def ensure_collection(self, drop_existing: bool = False) -> None:
        """
        确保集合和索引存在，同步脚本调用
        :param drop_existing: True 删除重建集合；False 存在就直接复用，支持增量upsert
        """
        client = self.milvus_client
        # 需要重建并且集合已存在，则先删除
        if drop_existing and client.has_collection(self.collection_name):
            client.drop_collection(self.collection_name)
        # 集合已经存在直接返回，不重复创建
        if client.has_collection(self.collection_name):
            return
        # 使用SchemaBuilder构建schema与索引参数，创建集合
        builder = CollectionSchemaBuilder(client, self._settings.INSIGHT_DENSE_DIM)
        client.create_collection(
            collection_name=self.collection_name,
            schema=builder.build_collection_schema(),
            index_params=builder.build_index_parameters()
        )
        client.load_collection(self.collection_name)
        logger.info(f"创建Milvus集合 {self.collection_name}")

    def upsert_documents(self, documents: list[EvidenceDocument]) -> int:
        """
        批量写入Milvus；同步脚本调用，同步SDK为阻塞调用，**外层调用必须套asyncio.to_thread**
        :param documents: 标准化全局契约EvidenceDocument文档对象列表
        :return: 成功写入实体条数
        """
        self.ensure_collection()
        # 批量对文档content做向量化，得到dense/sparse向量
        embeddings = self._embedder.encode(d.content for d in documents)
        entities = []
        # 循环：文档 + 对应向量，转为Milvus可写入dict实体
        for doc, (dense_vec, sparse_vec) in zip(documents, embeddings):
            # 向量为空直接跳过这条脏数据
            if not dense_vec or not sparse_vec:
                continue
            entity = self._to_milvus_entity(doc, dense_vec, sparse_vec)
            entities.append(entity)
        if not entities:
            logger.warning("无有效数据插入Milvus")
            return 0
        # upsert: doc_id主键存在则更新，不存在则新增；支持增量同步
        self.milvus_client.upsert(collection_name=self.collection_name, data=entities)
        logger.info(f"Milvus成功写入 {len(entities)} 条")
        return len(entities)

    @staticmethod
    def _to_milvus_entity(doc: EvidenceDocument, dense_vector: list[float], sparse_vector: dict[int, float]) -> dict[str, Any]:
        """EvidenceDocument内存对象 → Milvus写入实体字典
        doc_id直接读取EvidenceDocument契约内置@property，不再手动拼接字符串
        """
        # 通过反射取出全部互动指标字段
        engage_part = {
            f.name: float(doc.engagement.get(f.name, 0.0))
            for f in fields(Engagement)
        }
        return {
            "doc_id": doc.doc_id,                     # 组合主键 platform:table:pk，来自EvidenceDocument内置property
            "platform": doc.platform,
            "source_table": doc.source_table,
            "mysql_primary_key": doc.mysql_primary_key,
            "content": doc.content,
            "published_at": int(doc.published_at.timestamp()), # datetime转时间戳整数存入Milvus
            **engage_part,
            "hotness_score": doc.hotness_score,
            "dense_vector": dense_vector,      # BGE‑M3稠密语义向量
            "sparse_vector": sparse_vector     # BGE‑M3稀疏词法向量
        }

    def vector_call(self, query: str, limit: int, filter_expression: str | None = None) -> list[SearchHit]:
        """
        线上向量混合检索入口；Agent在线任务调用
        :param query: 用户原始查询文本
        :param limit: 返回topN结果数量
        :param filter_expression: Milvus标量过滤表达式，例如 published_at >= 1750000000
        :return: 命中结果列表list[SearchHit]
        """
        # 集合不存在直接返回空列表，不报错
        if not self.milvus_client.has_collection(self.collection_name):
            logger.warning(f"Milvus集合 {self.collection_name}不存在，跳过检索")
            return []
        # 用户query生成dense+sparse向量【在线任务：只对query做向量化，不处理海量文档】
        embeddings = self._embedder.encode([query])
        if not embeddings:
            return []
        # 执行混合检索
        return self._hybrid_search(embeddings[0], limit, filter_expression)

    def _hybrid_search(self, query_emb: tuple[list[float], dict[int, float]], limit: int, filter_expr: str | None) -> list[SearchHit]:
        """执行dense稠密 + sparse稀疏两路AnnSearch，RRF做结果融合
        为什么两路融合：
        dense向量擅长语义相似（关键词不完全匹配，含义接近）；
        sparse向量擅长关键词字面命中；
        RRFRanker：基于排名融合两路结果，**不要直接相加分数，dense余弦、sparse内积值域不一样，分数不能直接算术相加**。
        注意：RRF融合之后返回的distance不是原始向量相似度，是RRF排序得分，仅用于排序，不要当做语义相似度解读。
        """
        dense_vec, sparse_vec = query_emb
        # 组装过滤参数，没有过滤条件就传空字典
        filter_arg = {"expr": filter_expr} if filter_expr else {}
        # 稠密向量检索请求：COSINE余弦相似度
        req_dense = AnnSearchRequest(
            data=[dense_vec], anns_field="dense_vector", param={"metric_type": "COSINE"}, limit=limit,** filter_arg # type: ignore
        )
        # 稀疏向量检索请求：IP内积
        req_sparse = AnnSearchRequest(
            data=[sparse_vec], anns_field="sparse_vector", param={"metric_type": "IP"}, limit=limit, **filter_arg # type: ignore
        )
        # hybrid_search混合检索；RRFRanker 基于排名融合两路结果（不要直接相加分数）
        raw = self.milvus_client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[req_dense, req_sparse],
            ranker=RRFRanker(),
            limit=limit,
            output_fields=MILVUS_OUTPUT_FIELDS  # 指定返回哪些标量字段，用于还原EvidenceDocument
        )
        # Milvus原始返回结果映射为业务SearchHit对象
        return self._map_hits(raw)

    @staticmethod
    def _map_hits(raw_result: Any) -> list[SearchHit]:
        """Milvus原始返回结果 → list[SearchHit]业务模型
        hit.retrieval_score：RRF融合之后排序分数，**不是原始dense/sparse向量相似度**，只用于排序，不做语义相似度解读。
        """
        hits: list[SearchHit] = []
        if not raw_result:
            return hits
        # raw_result外层是list；raw_result[0]代表本次查询的命中集合
        for hit_dict in raw_result[0]:
            entity = hit_dict["entity"]   # Milvus返回的实体字段字典
            # 反射组装互动指标字典
            engage_dict = {
                f.name: float(entity.get(f.name, 0.0))
                for f in fields(Engagement)
            }
            # Milvus时间戳整数转回Python datetime对象
            doc = EvidenceDocument(
                platform=entity["platform"],
                source_table=entity["source_table"],
                mysql_primary_key=entity["mysql_primary_key"],
                content=entity["content"],
                published_at=datetime.fromtimestamp(int(entity["published_at"])),
                engagement=engage_dict,
                hotness_score=float(entity["hotness_score"])
            )
            # SearchHit 携带RRF排序得分、来源通道、嵌套EvidenceDocument文档
            hit = SearchHit(
                retrieval_score=float(hit_dict["distance"]),
                retrieval_channel="semantic_recall",
                retrieval_document=doc
            )
            hits.append(hit)
        return hits


# ===================== 【测试demo，教案使用，if __name__才执行】 =====================
if __name__ == "__main__":
    """本地测试向量检索，注意：必须已经执行过全量同步脚本，Milvus集合内有数据"""
    repo = VectorSearchRepository()
    try:
        test_query = "高考志愿填报焦虑"
        top_k = 5
        # 调用线上向量检索入口
        hit_list = repo.vector_call(query=test_query, limit=top_k)
        print(f"\n=====向量检索测试，query:{test_query}，命中{len(hit_list)}条=====\n")
        for idx, hit in enumerate(hit_list, start=1):
            doc = hit.retrieval_document
            print(f"【{idx}】RRF排序得分:{hit.retrieval_score:.4f}")
            print(f"    平台:{doc.platform} | 表:{doc.source_table} | ID:{doc.mysql_primary_key}")
            print(f"    发布时间:{doc.published_at} | 热度:{doc.hotness_score:.1f}")
            print(f"    内容:{doc.content[:80]}...")
            print("-"*80)
    finally:
        # 测试结束关闭Milvus客户端
        repo.close()