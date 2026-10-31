# engines/media_agent/search_plan_schema.py
"""
搜索规划节点LLM结构化输出Pydantic Schema
仅SearchPlanningNode使用；不存入LangGraph State；解析完成提取字段转为普通dict写入MediaSectionState。
"""
from pydantic import BaseModel, Field

from engines.media_agent.web_search.search_results import SearchTool


class MediaSearchPlanItem(BaseModel):
    """单个章节搜索规划项，对应五章中某一章"""
    search_tool: SearchTool = Field(
        description=(
            "从三种可用搜索工具选择一个；"
            "严格使用给定枚举字符串，不能自行创造工具；"
            "依据章节职责、问题的实时性、工具描述做匹配。"
        )
    )

    # query

    search_keywords: list[str] = Field(
        min_length=1,
        max_length=3,
        description=(
            "1‑3个中文补充检索短语；"
            "不是完整问句，不要复制原始query；"
            "每个关键词代表一个检索侧重点，尽量角度差异化，避免同义重复。"
        )
    )


class MediaSearchPlanOutput(BaseModel):
    """LLM搜索规划顶层输出；固定5项，顺序与系统内置SECTION_DEFINITIONS严格保持一致，不能重排增删。"""
    sections: list[MediaSearchPlanItem] = Field(
        min_length=5,
        max_length=5,
        description="必须恰好5个规划项，一一对应五章原始顺序，禁止新增、删除、调换顺序。"
    )