from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Engagement:
    """互动指标契约：点赞、评论、分享、收藏、回复"""
    likes: float
    comments: float
    shares: float
    collects: float
    replies: float


@dataclass(slots=True)
class EvidenceDocument:
    """
    文档本体：来自MySQL/Milvus归一化后的原始舆情文档。
    不变本体：同一篇帖子/评论，无论多少次检索，本体字段内容不会变化；
    不存放每次检索会变化的信息：比如本次检索命中分数、命中哪些query关键词；
    【可变的召回信息】放到独立的 RetrievalMeta。

    字段说明：
    platform: 平台，如 weibo / douyin
    source_table: 来源数据库表名
    mysql_primary_key: mysql数据表原始自增主键
    content: 帖子/评论正文内容
    published_at: 发布时间datetime对象
    engagement: 互动指标字典，key对应Engagement字段
    hotness_score: SQL计算得到的业务热度分数
    url / title / source_name: 预留字段，后续MediaAgent公域爬虫产出文档本体使用
    """
    platform: str                # 平台，如 weibo / douyin
    source_table: str            # 来源数据库表名
    mysql_primary_key: int       # mysql数据表主键 / 也代表网络数据的唯一标识
    content: str                 # 帖子/评论正文内容
    published_at: datetime       # 发布时间
    engagement: dict[str, float] = field(default_factory=dict)  # 互动数据字典
    hotness_score: float = 0.0   # 热度分值

    # 添加网络查询的数据参数[后续media_agent会使用]
    # media_agent -> 数据
    url: str = ""
    title: str = ""
    source_name: str = ""

    @property
    def doc_id(self) -> str:
        """
        生成全局唯一文档ID
        格式：平台:表名:主键，解决多表之间id冲突问题

        作用：
        1. 解决多张业务表自增主键数字重复冲突；
        2. Milvus向量库主键，用于upsert增量更新；
        3. hybrid_recall两路召回结果基于doc_id做业务去重；
        4. Host裁判Agent跨Agent证据配对、冲突识别的唯一标识。
        """
        return f"{self.platform}:{self.source_table}:{self.mysql_primary_key}"

@dataclass(slots=True)
class RetrievalMeta:
    """
    召回元数据 ,**每次检索会发生变化！**
    同一个EvidenceDocument文档，可以被多次检索命中，每次命中的查询词、分数不一样。

    matched_queries：触发这条记录命中的搜索词列表，支持多query召回场景，后续会做去重
    channel_scores：各个检索通道得分；key=通道名(db_call / semantic_recall)，value=对应通道分数
        - db_call通道：值为hotness_score业务热度分
        - semantic_recall通道：值为Milvus混合检索RRF融合排序分
    """
    matched_queries: list[str] = field(default_factory=list)  # 后续会去重复
    channel_scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class EvidenceRecord:
    """
    流水线全程流转的证据对象
    =【不变文档本体 EvidenceDocument】 +【可变召回元信息 RetrievalMeta】
    全系统统一契约：InsightAgent、MediaAgent输出该对象；HostAgent读取evidence.json；LLM分析输入证据集合。
    """
    document: EvidenceDocument
    retrieval: RetrievalMeta = field(default_factory=RetrievalMeta)

    @property
    def id(self) -> str:
        """快捷获取全局唯一文档id，用于去重、映射、路由；直接复用document.doc_id"""
        return self.document.doc_id

# ===================== LLM渲染上下文（后续五维分析章节使用，本章仅占位 =====================
@dataclass(slots=True)
class EvidenceContext:
    """
    供 LLM 提示词使用的已渲染证据上下文。
    把原始证据对象，加工成可以直接塞进Prompt的纯文本容器。
    retrieval_text: 用户原始检索/研究query
    evidence_text: 多条证据格式化之后拼接完成的大文本，直接喂给大模型
    内存临时对象，**不做磁盘持久化**，仅在调用LLM的生命周期内有效。
    """
    retrieval_text: str = ""
    evidence_text: str = ""


def build_evidence_context(
        retrieval_text: str,
        records: list[EvidenceRecord],
        max_rendered: int,
) -> EvidenceContext:
    """
    统计命中数并渲染有限证据，构建 LLM 提示词上下文。
    :param retrieval_text: 用户原始查询词/研究主题
    :param records: 当前章节对应的全部证据对象列表
    :param max_rendered: 最多送入LLM的证据条数，防止prompt超长上下文溢出
    :return: EvidenceContext 封装好的上下文对象，输出给PromptTemplate使用
    """
    return EvidenceContext(
        retrieval_text=retrieval_text,
        # 切片取前N条证据，每一条渲染成文本块，用两个换行分隔多条证据
        evidence_text="\n\n".join(
            _render_evidence_records(records[:max_rendered])
        ),
    )


def _render_evidence_records(records: list[EvidenceRecord]) -> list[str]:
    """
    将证据记录渲染为带稳定编号的 LLM 文本块。
    :param records: 需要渲染的证据列表（已经经过max_rendered切片）
    :return: list[str] 每条证据对应一段字符串，外层再做join拼接
    """
    # enumerate start=1：证据编号从1开始，方便LLM引用证据序号，不要0
    return [
        _render_evidence_record(record, evidence_number)
        for evidence_number, record in enumerate(records, start=1)
    ]


def _render_evidence_record(record: EvidenceRecord, evidence_number: int) -> str:
    """
    单条证据 → 格式化可读文本块。
    输出样例：
    [证据 1]
    平台/检索提供方: douyin
    来源表/工具: douyin_aweme
    命中查询: 高考
    内容: xxxxx
    发布时间/抓取时间: 2026‑06‑07
    热度分: 12345.0
    互动数据: 点赞 100 / 评论 20 ...
    """
    document = record.document
    # 定义需要输出给LLM的字段：(展示标签, 取值)
    fields = (
        ("平台/检索提供方", document.platform),
        ("来源表/工具", document.source_table),
        ("命中查询", " / ".join(record.retrieval.matched_queries)),
        ("内容", _truncate_content(document.content)),
        ("发布时间/抓取时间", document.published_at),
        ("热度分", document.hotness_score),
        ("互动数据", _render_engagement(document.engagement))
    )
    lines = [f"[证据 {evidence_number}]"]
    # if value：过滤掉值为空/None的字段，不输出无用行
    lines.extend(f"{label}: {value}" for label, value in fields if value)
    return "\n".join(lines)


def _truncate_content(content: str, max_length: int = 3000) -> str:
    """
    对单条证据正文做截断保护，避免单条文本过长撑爆prompt。
    :param content: 原始舆情文本
    :param max_length: 单条证据最大字符上限
    :return: 原始文本或者截断+省略号
    """
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def _render_engagement(engagement: dict[str, Any]) -> str:
    """
    将互动数字字典，渲染成一行可读字符串给LLM。
    输出示例：点赞 2040392.0 / 评论 194848.0 / 转发 3644422.0 / 收藏 59823.0 / 回复 0.0
    """
    values = (
        ("点赞", engagement.get('likes')),
        ("评论", engagement.get('comments')),
        ("转发", engagement.get('shares')),
        ("收藏", engagement.get('collects')),
        ("回复", engagement.get('replies')),
    )
    return " / ".join(f"{label} {value}" for label, value in values)