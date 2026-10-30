from dataclasses import dataclass, field
from typing import List
from engines.contracts.evidence import EvidenceDocument

# mysql结果
@dataclass(slots=True)
class SearchResult:
    """
    MySQL关键词召回结果集合【仓储私有容器】
    retrieval_channel: 来源通道标记，固定 db_call，标识这批文档来自MySQL关键词检索通道
    retrieval_results: 文档本体列表，内部存放EvidenceDocument
    MySQL关键词检索使用hotness_score做排序，没有每条记录独立的向量相似度分数，因此容器不携带单条score。
    仅在db_repository输出，hybrid_recall模块输入；合并之后该容器直接销毁，不向外透出、不持久化。
    """
    # 我们为啥没有分??? mysql就没有分 -> 自定义分
    retrieval_channel: str   # db_call
    retrieval_results: List[EvidenceDocument] = field(default_factory=list)

    # mysql => sql -> 100条 -> 1 SearchResult 对象 -> retrieval_channel | list 
    
	# hotness_score 
    
# milvus
@dataclass(slots=True)
class SearchHit:
    """
    Milvus向量检索单条命中记录【仓储私有容器】
    retrieval_score: Milvus hybrid_search返回RRF融合排序分数，**仅用于排序，不等于原始向量语义相似度**
    retrieval_channel: 来源通道标记，固定 semantic_recall，标识来自向量语义召回通道
    retrieval_document: Milvus还原出的文档本体EvidenceDocument
    仅vector_repository输出，hybrid_recall模块输入；两路合并完成之后容器销毁。
    """
    retrieval_score: float  # 查询相似度 distance 
    retrieval_channel: str  # semantic_recall
    retrieval_document: EvidenceDocument  # 单条查询结果
    
    # milvus -> 100条 -> 100 SearchHit 对象 -> retrieval_channel | retrieval_score | retrieval_document