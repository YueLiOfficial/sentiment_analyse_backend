# engines/media_agent/nodes/search_planning_node.py
"""
SearchPlanningNode：公域搜索规划节点【3新增节点#1】
职责：
    1. 基于用户query + 固定5章节职责，调用LLM做搜索策略规划；
    2. 为每一章输出：search_tool(三种枚举) + 1~3个补充搜索关键词；
    3. 本节点**不调用网页搜索、不生成章节正文**，仅产出检索策略；
    4. LLM仅输出策略枚举；域名、时间窗口、top_k等底层参数全部在web_search provider层，LLM无感知；
    5. 章节section_key、title全部来自SECTION_DEFINITIONS配置；LLM禁止增删、重排、自定义章节。

输入state：MediaAgentState，需要 query、role
输出增量：{"sections": list[MediaSectionState]}
约束铁律：
    - LLM输出sections必须恰好5项，顺序与系统内置SECTION_DEFINITIONS严格对齐；
    - search_tool只能是SearchTool枚举；
    - search_keywords每一项长度1~3，是补充短语，不是完整query；完整query后续SearchNode内部拼接。
"""
import json
from typing import Any

from langchain_core.prompts import PromptTemplate
from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.section_definitions import (
    SECTION_DEFINITIONS,
    get_section_definitions_for_role,
)
from engines.media_agent.search_plan_schema import MediaSearchPlanOutput
from engines.media_agent.state import MediaAgentState, MediaSectionState
from engines.media_agent.web_search.search_results import SEARCH_TOOL_DESCRIPTIONS
from engines.prompts.media import (
    MEDIA_SEARCH_PLAN_SYSTEM_PROMPT,
    MEDIA_SEARCH_PLAN_USER_PROMPT,
)


class SearchPlanningNode(ResearchNode):
    """公域搜索规划节点：为固定Media五章生成每一章搜索工具与补充搜索关键词"""

    async def __call__(self, state: MediaAgentState) -> dict[str, Any]: # type: ignore
        """
        LangGraph节点统一入口
        :param state: MediaAgentState 公域全局状态
        :return: dict 仅返回变更字段sections，LangGraph自动合并state
        """
        role = state["role"]
        role_info = ROLE_INFOS[role]
        research_topic = state["query"]
        logger.info(f"【{role_info.agent_name}】搜索规划节点开始执行，研究主题={research_topic}")

        # 调用LLM结构化输出，完成搜索策略规划，自带Pydantic强校验
        plan_output = await self._generate_search_plan(research_topic)

        # 重要：section_key、title完全使用配置；LLM输出只取search_tool、search_keywords，拒绝自定义章节
        sections: list[MediaSectionState] = [
            {
                "section_key": section_def.key,
                "title": section_def.title,
                "search_tool": plan_item.search_tool,
                "search_keywords": [kw.strip() for kw in plan_item.search_keywords],
            }
            for section_def, plan_item in zip(
                list(SECTION_DEFINITIONS.values()),
                plan_output.sections
            )
        ]

        logger.info(f"【{role_info.agent_name}】搜索规划完成，共生成{len(sections)}个章节搜索策略配置")
        # LangGraph规范：只返回发生变更的字段
        return {"sections": sections}

    async def _generate_search_plan(self, research_topic: str) -> MediaSearchPlanOutput:
        """
        组装Prompt，调用LLM结构化输出接口，返回校验完成的规划Pydantic对象
        :param research_topic: 用户原始研究query
        :return: MediaSearchPlanOutput 强校验后的规划结果
        :raises ValidationError: LLM输出JSON格式/字段不满足约束抛出；上层可捕获做LLM重试
        """
        # 组装给LLM阅读的工具描述；直接复用web_search导出常量，禁止prompt硬编码工具文本
        tool_desc_list = [
            {"name": tool_name, "description": desc}
            for tool_name, desc in SEARCH_TOOL_DESCRIPTIONS.items()
        ]
        # 获取media角色固定5章节定义（章节key、标题、章节写作职责）
        media_section_defs = get_section_definitions_for_role("media")

        user_prompt = PromptTemplate.from_template(MEDIA_SEARCH_PLAN_USER_PROMPT).format(
            research_topic=research_topic,
            section_contexts=json.dumps(media_section_defs, ensure_ascii=False, indent=2),
            search_tools=json.dumps(tool_desc_list, ensure_ascii=False, indent=2)
        )

        # 调用LLM结构化输出接口；自动完成json解析 + MediaSearchPlanOutput Pydantic校验
        structured_result = await self.context.llm_client.generate_object(
            system_prompt=MEDIA_SEARCH_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            object_model=MediaSearchPlanOutput
        )
        return structured_result