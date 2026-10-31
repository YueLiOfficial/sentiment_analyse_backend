from typing import Any

from engines.common.section_summary import BaseSectionSummaryNode
from engines.prompts.media import MEDIA_SECTION_SUMMARY_SYSTEM_PROMPT

FALLBACK_BODY = "【数据缺口】该章节未在可用数据源中检索到相关内容,本章节暂无分析结论。"


class SectionSummaryNode(BaseSectionSummaryNode):
    """公域章节摘要节点:基于全局证据撰写章节分析并发布就绪事件。"""

    system_prompt = MEDIA_SECTION_SUMMARY_SYSTEM_PROMPT
    fallback_body = FALLBACK_BODY

    def _retrieval_text(self, state: dict[str, Any], cursor: int) -> str:
        """返回当前章节的实际检索请求。"""
        return state["section_queries"][cursor]