"""
Insight 双通道检索编排服务：MySQL关键词召回 + Milvus BGE‑M3混合语义召回
文件路径：engines/insight_agent/tools/retrieval_service.py

## 整体业务职责
1. 使用jieba TF‑IDF提取query核心关键词，扩充MySQL多组检索词，扩大召回样本；
    约束：jieba提取的关键词【仅用于MySQL模糊检索】；Milvus向量检索永远使用完整原始query，不做切分，保护BGE‑M3语义编码效果。
2. async并发执行MySQL多关键词检索，提升多路关键词查询效率；
3. Milvus稠密dense + 稀疏sparse混合向量检索；支持配置化最近N天时间过滤，只召回近期舆情；
4. pymilvus为同步阻塞SDK；使用asyncio.to_thread丢入线程池执行，避免阻塞整个async事件循环；
5. 向量检索原始相似度得分做【组内Min‑Max简化归一化】，缩放到 [0,1] 区间；对齐MySQL通道分数尺度，给后续rerank节点做加权融合；
6. 将底层仓储返回的EvidenceDocument（不变本体），统一包装为Graph标准EvidenceRecord；填充RetrievalMeta召回元数据；
7. SearchResult / SearchHit 属于【仓储层私有临时对象】，仅本服务局部作用域使用；处理完成后释放，绝不对外暴露，绝不流入Graph、绝不存入LangGraph State；

## 通道标识说明
- DB关键词通道：`db_call`
- Milvus语义向量通道：`semantic_recall`

## 第三方依赖
    pip install jieba / uv add jieba
"""
import asyncio
from datetime import datetime, timedelta

import jieba.analyse

from engines.contracts.evidence import EvidenceRecord, EvidenceDocument, RetrievalMeta
from engines.contracts.settings import get_settings
from engines.insight_agent.repositories.db_repository import DataBaseSearchRepository
from engines.insight_agent.repositories.vector_repository import VectorSearchRepository
from engines.insight_agent.tools.search_results import SearchResult, SearchHit


class InsightRetrievalService:
    """
    私域双通道检索编排服务
    > 定位：工具适配层，不属于LangGraph业务节点；被evidence_retrieval_node节点调用
    > 特性：完全不依赖LangGraph包；可以脱离整个Agent图，直接对本服务做单元测试，只传入query即可拿到证据列表
    > 降级能力：配置INSIGHT_VECTOR_ENABLED=False，向量库关闭；自动降级为仅MySQL关键词检索，保证服务可用性。
    """

    def __init__(self):
        # 初始化数据库检索仓库
        self._db_repository = DataBaseSearchRepository()
        # 向量仓库：根据配置开关决定是否实例化，关闭则为None
        self._vector_repository = (
            VectorSearchRepository() if get_settings().INSIGHT_VECTOR_ENABLED else None
        )

    async def retrieve_evidence(self, query: str) -> list[EvidenceRecord]:
        """
        对外统一检索入口
        并行执行DB关键词检索、向量语义检索，合并两个通道原始召回结果返回
        返回结果尚未doc_id全局去重，上层必须调用hybrid_recall做合并
        :param query: 用户原始舆情研究查询语句
        :return: 合并后的证据记录列表 EvidenceRecord（未去重）
        """
        db_results, vector_results = await asyncio.gather(
            self._retrieve_db_evidence(query),
            self._retrieve_vector_evidence(query)
        )

        return db_results + vector_results

    async def _retrieve_db_evidence(self, query: str) -> list[EvidenceRecord]:
        """
        MySQL关键词检索分支
        业务流程：
          1. 使用jieba TF‑IDF提取关键词，生成多组检索词（原始query + top2关键词），扩大召回；
          2. 并行对每个检索词执行数据库db_call查询；
          3. 将数据库返回SearchResult里面的原始EvidenceDocument逐条封装为EvidenceRecord；
          4. DB通道统一固定channel_score=1.0；不做仓储层细粒度打分，打分全部后置到rerank节点。

        重要：同一个doc会被多个检索词命中，本函数会输出多条doc_id完全一致记录；不去重，留给上层hybrid_recall合并元数据。
        :param query: 用户原始查询
        :return: DB通道召回的EvidenceRecord列表（允许doc_id重复）
        """
        # jieba分词
        keywords = _build_db_search_terms(query)

        db_results = await asyncio.gather(*[self._db_repository.db_call(keyword,limit=100) for keyword in keywords])

        evidence_records = []

        for keyword, result in zip(keywords, db_results):
            for doc in result.retrieval_results:
                evidence_records.append(
                    map_document_to_evidence(
                        document=doc,
                        retrieval_channel=result.retrieval_channel,
                        matched_query=keyword,
                        channel_score=1.0
                    )
                )

        return evidence_records


    async def _retrieve_vector_evidence(self, query: str) -> list[EvidenceRecord]:
        """
        Milvus向量语义检索分支
        业务流程：
         1. 如果向量功能关闭直接返回空列表；
         2. vector_call底层pymilvus是同步阻塞IO，使用asyncio.to_thread丢线程池执行，不破坏asyncio事件循环；
         3. 向量原始得分做【组内Min‑Max简化归一化】，缩放到[0,1]区间；
            组内归一化：仅针对**本次query返回的全部向量hit做缩放；归一化分数只能同一次任务内部rerank使用，不能跨不同query互相比较分数**
        :param query: 用户原始查询；向量检索永远使用完整原始query，不使用jieba切分关键词
        :return: 向量通道召回的EvidenceRecord列表
        """
        if not self._vector_repository:
            return []
        
        vector_hits = await asyncio.to_thread(
            self._vector_repository.vector_call, 
            query=query, 
            limit=100,
            filter_expression=_build_published_at_filter()
        )

        # 计算本组向量检索的最大分数，用于归一化；default=0.0，防止空列表max抛异常
        max_retrieval_score = max(
            (hit.retrieval_score for hit in vector_hits),
            default=0.0
        )

        evidence_list: list[EvidenceRecord] = []
        for hit in vector_hits:
            # 归一化：本组最高分=1.0；最大分数为0时，归一化分数直接置0，避免除零异常
            if max_retrieval_score > 0:
                normalized_score = hit.retrieval_score / max_retrieval_score
            else:
                normalized_score = 0.0

            evidence_record = map_document_to_evidence(
                document=hit.retrieval_document,
                retrieval_channel=hit.retrieval_channel,
                matched_query=query,  # 向量检索输入是完整原始query，记录原始query作为本次命中触发词
                channel_score=normalized_score,
            )
            evidence_list.append(evidence_record)

        return evidence_list

def _build_db_search_terms(query: str) -> list[str]:
    """
    构建数据库关键词检索词列表
    jieba.analyse.extract_tags：基于TF‑IDF算法提取query的核心关键词

    逻辑：
    1. 原始query作为第一个检索词，保证完整语义的精准召回；
    2. jieba提取top2关键词，过滤长度2‑4字，去重追加到检索词列表；

    目的：扩大MySQL数据库召回范围，避免单纯整句搜索召回过少，漏掉相关讨论；
    注意：**生成的扩充检索词，仅仅供给MySQL使用；Milvus向量检索不使用切分关键词，BGE‑M3需要完整原始query做语义编码。**
    """
    keywords: list[str] = [query]
    for keyword in jieba.analyse.extract_tags(query, topK=5):
        if 2 <= len(keyword) <= 4 and keyword not in keywords:
            keywords.append(keyword) # type: ignore

    return keywords


def _build_published_at_filter() -> str | None:
    """
    构建Milvus向量检索时间过滤条件
    读取配置：INSIGHT_VECTOR_FILTER_DAYS，只检索最近N天舆情数据；久远历史数据过滤，降低无关噪声。
    配置为<=0则不做时间过滤，返回None，向量检索全库检索。

    Milvus存储published_at是int时间戳，过滤表达式语法：`published_at >= 1756123456`；不能传入datetime对象。
    """
    filter_days = get_settings().INSIGHT_VECTOR_FILTER_DAYS
    if filter_days <= 0:
        return None
    start_timestamp = int(
        (
            datetime.now()
            - timedelta(days=filter_days)
        ).timestamp()
    )
    return f"published_at >= {start_timestamp}"


def map_document_to_evidence(
    document: EvidenceDocument,
    retrieval_channel: str,
    matched_query: str,
    channel_score: float,
) -> EvidenceRecord:
    """
    统一转换函数：把底层返回的EvidenceDocument（不变文档本体），包装成Graph标准EvidenceRecord
    填充召回元数据RetrievalMeta：本次命中的查询词、当前单通道召回得分。

    ## 重点设计说明（matched_queries: list[str]而不是str）
    > 当前是**单次检索命中**，所以传入一个matched_query，存入列表后列表内仅有1个元素。
    > 为什么不用字符串str？
    > 同一个doc_id，会被多个检索词、多个通道分别命中；本服务会产生多条EvidenceRecord；
    > 后续hybrid_recall(_dedupe_and_merge)做doc_id去重合并时，需要把多条记录里面所有命中检索词全部收集、去重，存入合并后的EvidenceRecord.matched_queries。
    > 如果字段是简单字符串str，合并阶段会丢失多检索词命中溯源信息，无法评估、debug召回链路。

    约束：
        1. document本体只读，本函数绝不修改document任何字段；本体与召回元数据严格解耦。
        2. 本函数**只填充单通道的channel_scores字典**；如果doc同时被DB+向量命中，会生成两条记录；多通道分数合并交给上层hybrid_recall。
        3. channel_score保存【底层原始召回分数】；rerank节点产出的业务重排分，独立存state.rerank_scores；禁止把rerank分数覆盖写进RetrievalMeta.channel_scores，保护原始召回信号。
    """
    return EvidenceRecord(
        document=document,
        retrieval=RetrievalMeta(
            matched_queries=[matched_query],
            channel_scores={
                retrieval_channel: channel_score,
            },
        ),
    )


# ===================== 真实环境测试函数（连接真实DB + Milvus） =====================
async def demo_test_real_retrieval_service():
    """
    真实环境集成测试：
    前置依赖：数据库、Milvus服务正常连通，配置文件加载正确；离线同步脚本已经把数据写入Milvus集合。
    运行后打印DB召回条数、向量召回条数、每条记录的元数据、归一化分数，方便人工验证双通道召回行为。

    测试脚本区分通道使用硬编码字符串 db_call / semantic_recall；后续如果修改通道名称常量，需要同步修改本测试代码。
    """
    service = InsightRetrievalService()

    # 修改这里为你的测试query
    test_query = "高考是人生的转折点"

    print(f"===== 真实检索测试，查询语句：{test_query} =====")
    print(f"向量检索开关：{get_settings().INSIGHT_VECTOR_ENABLED}")

    try:
        all_records = await service.retrieve_evidence(test_query)

        # 拆分DB和向量结果，方便看各自召回
        db_recs = [r for r in all_records if "db_call" in r.retrieval.channel_scores]
        vec_recs = [r for r in all_records if "semantic_recall" in r.retrieval.channel_scores]

        print(f"\n✅ 总召回记录：{len(all_records)}")
        print(f"✅ DB关键词通道召回：{len(db_recs)} 条")
        print(f"✅ 向量语义通道召回：{len(vec_recs)} 条")

        print("\n----- DB通道结果 -----")
        for idx, rec in enumerate(db_recs):
            print(f"\n【DB-{idx+1}】")
            print(f"文档id: {rec.document.doc_id}")
            print(f"命中查询词: {rec.retrieval.matched_queries}")
            print(f"通道得分: {rec.retrieval.channel_scores}")
            print(f"文档片段: {rec.document.content[:100]}...")

        print("\n----- 向量通道结果 -----")
        for idx, rec in enumerate(vec_recs):
            print(f"\n【VEC-{idx+1}】")
            print(f"文档id: {rec.document.doc_id}")
            print(f"命中查询词: {rec.retrieval.matched_queries}")
            print(f"归一化得分: {rec.retrieval.channel_scores}")
            print(f"文档片段: {rec.document.content[:100]}...")

    except Exception as e:
        print(f"\n❌ 检索发生异常：{repr(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行真实环境集成测试
    asyncio.run(demo_test_real_retrieval_service())