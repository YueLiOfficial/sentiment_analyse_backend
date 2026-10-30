from collections import defaultdict
from functools import lru_cache
from typing import Any, List

import numpy as np
from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.evidence import EvidenceRecord
from engines.contracts.section_definitions import get_insight_routing_rules, SECTION_DEFINITIONS
from engines.contracts.settings import get_settings
from engines.insight_agent.state import InsightState
# 导入路由专用向量化单例；该工具仅用于章节语义路由，和Milvus向量检索互相独立
from engines.insight_agent.tools.vector.embedder_small import routing_embedder


class SectionEvidenceRoutingNode(ResearchNode):
    """
    章节证据路由节点
    职责：将召回重排完成的证据，分配到5个预定义报告章节。
    只做证据ID映射归类；**不修改证据本体内容、不调用LLM、不生成报告正文**。

    输入：
        state["records_by_id"]: dict[str, EvidenceRecord]
            key=证据doc_id, value=完整EvidenceRecord对象；N2产出的全局权威证据索引

    输出增量：
        {"section_record_ids": dict[str, list[str]]}
            key=章节section_key，value=归属该章节的**证据doc_id字符串列表**
            下游N4装配节点，拿着doc_id回查records_by_id拿到完整证据对象

    两套工作模式：
        1. 规则关键词匹配(兜底降级方案，无模型依赖，确定性强，可复现)
        2. embedding语义向量匹配(增强方案，需要embedding模型配置，解决关键词漏召回语义相关证据)

    语义模式启用【全部条件必须同时满足】，任意条件不满足自动回退规则路径：
        ①输入证据列表非空
        ②配置项 INSIGHT_SEMANTIC_ROUTING_ENABLED = true
        ③路由embedding模型配置项有效可加载
    """
    async def __call__( # type: ignore
        self,
        state: InsightState,
    ) -> dict[str, Any]:
        """
        业务入口：进行章节证据路由
        :param state: graph全局状态，携带所有召回完成的证据集合
        :return: 状态增量，携带章节‑证据doc_id映射字典
        """
        role = state["role"]
        role_info = ROLE_INFOS.get(role)
        logger.info(f"{role_info.agent_name} 开始为章节选择证据") # type: ignore

        # 读取N2产出的全局证据索引，取出全部待路由的证据对象
        # {doc_id: EvidenceRecord} -> .values() -> list -> [EvidenceRecord]
        evidence_records: List[EvidenceRecord] = list(state["records_by_id"].values())

        # 判断是否全部条件满足，开启语义向量路由；不满足自动降级关键词规则路由
        if is_semantic_enabled(evidence_records):
            logger.info("开始进行语义匹配证据路由【增强模式】")
            # key -> 章节的key  :  list -> [doc_id...]
            section_record_ids:dict[str,list[str]] = _route_by_semantics(evidence_records)
        else:
            logger.info("开始进行规则关键词匹配证据路由【兜底降级模式】")
            section_record_ids:dict[str,list[str]] = _route_by_rules(evidence_records)

        logger.info(f"{role_info.agent_name} 章节候选证据分配完成") # type: ignore
        # 返回状态增量，由LangGraph框架合并到graph的全局state；只输出本节点产出字段
        return {"section_record_ids": section_record_ids}


def is_semantic_enabled(evidence_records: List[EvidenceRecord]) -> bool:
    """
    判断是否可以开启语义向量路由；**全部条件必须同时成立才返回True**；任意不满足，返回False切规则兜底
    返回True：启用语义向量路由；False：走关键词规则兜底
    """
    settings = get_settings()
    # 条件1：总开关开启
    if not settings.INSIGHT_SEMANTIC_ROUTING_ENABLED:
        return False
    # 条件2：待处理证据集合不为空；空证据列表不需要做向量编码，直接走规则路径
    if not bool(evidence_records):
        return False
    # 条件3：路由embedding模型配置不为空；工具内部会做模型加载校验
    if not settings.INSIGHT_SEMANTIC_ROUTING_MODEL:
        return False
    return True


def _route_by_semantics(evidence_records: List[EvidenceRecord]) -> dict[str, list[str]]:
    """
    语义向量匹配路径【增强模式】
    核心原理：使用embedding把证据、章节描述转为向量，计算L2归一化后的余弦相似度，分配给相似度最高的章节

    当前实现业务行为：
        1. 全部证据**强制分配某一个章节，不存在丢弃逻辑**；哪怕全部证据对全部章节相似度整体很低，依然选择相对最高分章节
        2. 章节向量使用@lru_cache进程内存缓存；**进程启动仅编码一次；运行时修改section_definitions路由关键词，缓存不会刷新，必须重启进程**
        3. 本版本为单标签分配：一条证据只能归属相似度最高的单一章节；后续迭代可改造为Top‑N+阈值实现多标签分配

    数据维度示例：
        evidence_records 共3条证据，共5个章节，向量维度D=512(bge‑small‑zh‑v1.5)
        record_vectors shape = (3, 512)   # N条证据 × 向量维度
        section_vectors shape = (5, 512)  # 5个章节 × 向量维度
        similarities = np.dot(record_vectors, section_vectors.T)
            → shape=(3,5)，每一行代表一条证据对5个章节的余弦相似度
    """
    # 批量拼接每一条证据的输入文本：检索匹配词 + 证据正文；拼接文本送入embedding编码
    contents: List[str] = []
    MAX_SAFE_CHAR = 750  # 嵌入式模型的上下文大小!!!  粗略字符上限，规避输入文本过长，模型内部会静默截断，不会抛异常
    for record in evidence_records:
        raw_text = (
            f"{' '.join(record.retrieval.matched_queries)} "
            f"{record.document.content}"
        ).strip()
        safe_text = raw_text[:MAX_SAFE_CHAR]
        contents.append(safe_text)

    # 调用外部工具类获取已经L2归一化向量矩阵；归一化后dot点积等价余弦相似度
    # evidence_records = [EvidenceRecord * 1024]
    # [[512],[]]  len = N  shape = (N -> 数据条目, 512)
    # [[512],]
    record_vectors: np.ndarray = routing_embedder.encode(contents)

    # 获取缓存的有序章节key列表、预编码完成的章节向量矩阵
    # section_keys =[章节key1,2,3,4,5]
    # section_vectors = [[512 章节],[512],[],[],[]]  len = 5  shape = (5, 512)
    #  section_keys = 5   section_vectors = 5
    # section_vectors = [[512],[],[],[],[]]
    section_keys, section_vectors = _get_section_vectors()

    # 矩阵点积计算相似度矩阵 (N,D) @ (D,5) = (N,5)；numpy底层C批量运算，优于双层python for循环
    #                    (N -> 数据条目, 512)  * (512,5)
    #  [ [0.1,0.2,0.3,0.6,0.15]  一条数据的相似度向量
    #    [0.1,0.9,0.3,0.6,0.15]
    #    [0.1,0.2,0.8,0.6,0.15] ]  -> N
    #                          (1024,512)    (512,5)
    #    [1,2,3,[4],5]
    #    [1,2,3,4,5]
    #    [1,2,3,4,5]
    #    [1,2,3,4,5]
    #    [1,2,3,4,5]
    similarities = np.dot(record_vectors, section_vectors.T)

    # axis=1：沿着每一行（单条证据维度），取该行相似度最大值的下标；得到每条证据匹配最佳章节的索引
    # 1 -> 水平 每条数据,关联最高得分章节的   [3,1,2]  index 0 -> 垂直  每个章节关联的最分的数据
    # best_indices =  [3,1,2] = 3 = evidence_records
    best_indices: np.ndarray = np.argmax(similarities, axis=1)

    # defaultdict(list):访问不存在key自动创建空list，避免KeyError，直接append证据doc_id
    section_record_ids: dict[str, list[str]] = defaultdict(list)

    # 证据对象 和 最佳章节下标一一对应，完成doc_id归类
    for record, best_idx in zip(evidence_records, best_indices):
        section_key = section_keys[best_idx]  # 本次证据关联最好的章节 key
        # if section_key not in section_record_ids:  defaultdict(list)
        #     section_record_ids[section_key] = []
        section_record_ids[section_key].append(record.id)  # {key:[doc_id]}
    # {key:[doc_id],key:[]}
    # defaultdict转为普通dict对外输出；避免下游读取不存在key时，defaultdict隐式插入空列表，污染state数据
    return dict(section_record_ids)


def _route_by_rules(evidence_records: List[EvidenceRecord]) -> dict[str, list[str]]:
    """
    规则关键词匹配路径【兜底降级】
    业务逻辑：
        1. 拼接检索命中词+帖子正文作为待匹配文本
        2. 严格按照section_definitions字典插入顺序遍历5个章节
        3. next生成器逻辑：**找到第一个命中关键词的章节，立刻终止遍历，不再匹配后续章节（顺序优先，单标签）**
        4. 全部章节均未命中：该证据doc_id直接丢弃，不加入输出字典；证据本体仍然保存在全局records_by_id

    注意：
        Python3.7+字典保留插入顺序；**章节定义的先后顺序会直接影响多关键词命中证据的分配结果**
        本版本为单标签分配；后续迭代可移除next截断，遍历全部命中章节实现多标签分配

    输入示例：
        evidence_records: [EvidenceRecord(id="ev001"), EvidenceRecord(id="ev002")]
    返回示例：
        {"market":["ev001"], "risk":["ev002"]}
    """
    section_record_ids: dict[str, list[str]] = defaultdict(list)

    # 获取全部章节路由关键词配置 {"章节key" : [关键词列表]}；来源section_definitions.py的insight_routing_keywords
    rules = get_insight_routing_rules()

    for record in evidence_records:
        # 拼接待匹配文本：检索命中词 + 证据正文
        text = (
            f"{' '.join(record.retrieval.matched_queries)} "
            f"{record.document.content}"
        )

        # next(生成器, None)
        # 遍历rules，按字典插入顺序找到**第一个满足任意关键词子串命中**的section_key
        # 找到匹配 → 返回第一个命中的section_key；立刻终止循环；全部不匹配返回None
        section_key = next(
            (
                section_key
                for section_key, keywords in rules.items()
                if any(keyword in text for keyword in keywords)
            ),
            None
        )
        if section_key is not None:
            section_record_ids[section_key].append(record.id)

    # defaultdict转为普通dict对外输出；防止下游读取不存在key，defaultdict隐式新增空列表，造成state脏数据
    return dict(section_record_ids)


@lru_cache(maxsize=None)
def _get_section_vectors() -> tuple[list[str], np.ndarray]:
    """
    缓存【章节标题 + 路由关键词】编码后的章节向量矩阵
    重要坑点：lru_cache是**进程内存缓存**
        1. 服务进程启动的时候执行一次编码；
        2. 运行时修改section_definitions.py的路由关键词，**缓存不会自动刷新；必须重启进程，新配置才会生效**；
        3. 多worker/多进程部署，每个进程会各自独立做一次编码缓存。
    返回：
        section_keys: list[str]
            有序章节key列表，向量矩阵每一行和列表下标严格一一对应
        section_vectors: np.ndarray
            shape=(5,D)，5个章节的embedding矩阵，D为模型向量维度(512)
    """
    rules = get_insight_routing_rules()
    # 组装每个章节的描述文本：章节标题 + 当前章节全部路由关键词，用于embedding编码
    section_texts = [
        f"{SECTION_DEFINITIONS[section_key].title}: {' '.join(keywords)}"
        for section_key, keywords in rules.items()
    ]
    # 向量化逻辑下沉到路由专用embedder_small工具；输出L2归一化向量
    section_vectors = routing_embedder.encode(section_texts)
    section_keys = list(rules.keys())
    return section_keys, section_vectors