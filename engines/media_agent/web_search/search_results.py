# engines/media_agent/web_search/search_results.py
"""
web_search/search_results.py
【web_search包第一优先级文件，所有其他模块依赖本文件】
职责：
1. SearchTool：三种搜索策略字面量枚举；全链路共用
2. SEARCH_TOOL_DESCRIPTIONS：给LLM规划Prompt使用的工具自然语言描述
3. WebpageResult：单条网页原始结果（Provider层内部模型，不向上层业务节点暴露）
4. SearchProviderResponse：一次完整搜索请求返回结构体（Provider层内部模型）

注意：
- 本文件只放【数据模型+常量】，不能写业务逻辑、http请求；
- 上层业务节点禁止直接使用WebpageResult / SearchProviderResponse；只允许使用SearchTool、SEARCH_TOOL_DESCRIPTIONS。
"""
from dataclasses import dataclass, field
from typing import Literal

# ========== 搜索策略枚举，业务全链路共用 ==========
SearchTool = Literal["comprehensive_search", "source_search", "realtime_search"]

# ========== LLM规划节点使用：工具能力描述（直接导入Prompt，不要硬编码字符串） ==========
SEARCH_TOOL_DESCRIPTIONS: dict[SearchTool, str] = {
    "comprehensive_search": (
        "不限近期和站点范围的综合检索，适合比较不同媒体与信源的叙事差异，"
        "并分析社会背景、争议成因和潜在影响；优先用于“平台与群体差异”和“深层原因与影响”章节。"
    ),
    "source_search": (
        "限定政府和中央媒体站点的溯源检索，适合核验事件经过、公开通报、官方回应和权威报道；"
        "优先用于“事件背景与概览”章节。"
    ),
    "realtime_search": (
        "限定近一周微博、知乎和今日头条内容的时效性检索，适合追踪热度变化、传播节点、公域可见观点；"
        "优先用于“舆情热度与传播”和“公众情感与观点”章节。"
    ),
}

# ========= Provider内部dataclass模型 ==========
@dataclass(frozen=True, slots=True)
class WebpageResult:
    """
    Provider内部模型：单条网页检索原始返回结果
    业务节点（SearchPlanningNode/SearchNode）禁止直接导入；
    仅在：anspire_client、retrieval_service内部流转；向上转换为EvidenceRecord。
    """
    title: str
    url: str
    content: str
    date: str  # 注意此处的date是字符串,EvidenceDocument中的date是 date_time!
    score: float


@dataclass(frozen=True, slots=True)
class SearchProviderResponse:
    """
    Provider内部模型：一次完整搜索请求返回对象
    业务节点禁止直接导入；仅Provider、检索编排服务内部使用。
    """
    query: str
    webpages: list[WebpageResult] = field(default_factory=list)