from engines.contracts.evidence import EvidenceRecord
from engines.contracts.research_graph_state import ResearchGraphState, SectionState

class InsightState(ResearchGraphState[SectionState]):
    """
    Insight(私域)Agent专属LangGraph状态
    1. 继承泛型基类 ResearchGraphState[SectionState]，自动复用公共字段：task_id、query、role、sections、cursor、final_report
    2. 本State只定义字段；**字段的产出节点、消费节点、语义，写下面表格；业务逻辑全部放到06章节实现**
    """
	# mysql milvus
    retrieved_records: list[EvidenceRecord]
    """
    产出节点：evidence_retrieval_node
    消费节点：evidence_reranking_node
    含义：检索完成之后，hybrid_recall输出的**完整原始召回证据集合**；两路召回合并完成，未经过重排、未做章节分配的全部原始证据；
    约束：state中证据的标准载体；SearchResult/SearchHit到此已经全部销毁，不会进入state。
    """
	# 去重后的数据  {doc_id,数据}
    records_by_id: dict[str, EvidenceRecord]
    """
    产出节点：evidence_reranking_node
    消费节点：section_evidence_routing_node、section_preparation_node
    含义：证据id映射表；key=doc_id；value=完整EvidenceRecord对象；
    设计：证据唯一权威副本字典；后续路由、准备节点频繁按doc_id查找完整证据对象；避免反复遍历list做查找，提升路由阶段查找效率；
    架构原则：**完整EvidenceRecord对象尽量只在这个字典保存一份权威副本；其他状态字段优先传递doc_id字符串，不要反复拷贝完整EvidenceRecord对象，防止state序列化体积爆炸**。
    """
	# 每个数据得分 {doc_id,分 = mysql + milvus  +  hotness_score}
    rerank_scores: dict[str, float]
    """
    产出节点：evidence_reranking_node
    消费节点：section_evidence_routing_node
    含义：重排打分结果；key=doc_id，value=重排之后的分数；
    约束：**只存id‑分数映射，不重复存完整EvidenceRecord，控制state体积；分数语义由重排节点业务定义；本章仅定义字段，打分逻辑pass占位06实现**。
    """
	# 章节 -> 章节关联数据的id列表
    section_record_ids: dict[str, list[str]]
    """
    产出节点：section_evidence_routing_node
    消费节点：section_preparation_node
    含义：**章节‑证据ID映射**；key=section_key章节标识；value：分配给该章节的doc_id字符串列表；
    架构强约束：**只存doc_id字符串，绝对不存完整EvidenceRecord对象！！**
    设计意图：解耦“证据分配关系”和“证据实体本身”；降低state体积；后续章节准备节点拿着id，去records_by_id唯一字典查表取出完整证据组装章节证据列表；
    """
	# 章节 -> 真实的数据列表
    section_evidence_records: list[list[EvidenceRecord]]
    """
    产出节点：section_preparation_node
    消费节点：section_summary_node（循环读取cursor下标）
    含义：按章节分组证据集合；**外层数组下标严格对齐state.sections数组下标、cursor游标三者一一对应！！**；
    每一个下标元素，是对应章节裁剪过滤之后、专供该章节摘要使用的证据对象列表；
    循环逻辑：cursor=0，取下标0的证据列表，生成第一章；cursor=1取下标1，生成第二章，以此类推；
    """