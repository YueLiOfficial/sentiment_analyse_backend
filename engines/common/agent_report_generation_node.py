"""
公共节点：报告汇总生成节点
文件：engines/common/agent_report_generation_node.py

> 完全通用；Insight、Media两套Agent共用；**不感知任何私域/公域证据特有字段**；
> 只读取跨Agent公共state字段：query、role、sections；
> 业务：
> 1. 按照**静态SECTION_DEFINITIONS固定顺序**拼接报告,不要直接遍历state["sections"]数组做拼接，防止state数组顺序被bug打乱；
> 2. 组装markdown报告头部：task_id、原始query、报告生成时间、数据来源说明；
> 3. 循环按配置顺序拼接每一章标题 + 已经生成完成的body正文；
> 4. 追加报告尾部风险免责说明（AI生成仅供参考，结论基于现有证据等）；
> 5. 产出完整markdown大文本，写入state["final_report"]；

## 输入 state字段
- query：用户原始查询
- role：Agent角色
- sections：list[SectionState]；**全部章节body字段都已经生成完毕**

## 输出 state增量字段
- final_report：str；完整markdown格式报告文本，内存字符串，尚未落盘

## 上下游
上游：章节循环全部结束，条件边all_done跳转进入本节点
下游：ReportPersistenceNode 报告落盘节点
"""
import json
from typing import Any

from langchain_core.prompts import PromptTemplate
from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.research_graph_state import ResearchGraphState
from engines.prompts.report import (
    AGENT_REPORT_GENERATION_SYSTEM_PROMPT,
    AGENT_REPORT_GENERATION_USER_PROMPT,
)


class AgentReportGenerationNode(ResearchNode):
    """将 Agent 的章节正文整合为独立研究报告。"""

    async def __call__(self, state: ResearchGraphState[Any]) -> dict[str, Any]: # type: ignore
        role = state['role']
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始将章节正文整合为独立研究报告")
        self.context.report_progress("generating", f"{role_info.agent_name} 开始生成独立报告", 70)

        query = state["query"]
        sections = state["sections"]
        logger.info(f"开始生成独立报告,舆论话题: {query},待整合章节数: {len(sections)}")

        report_context = json.dumps(
            # [{"title":"事件背景","body":"章节的内容总结"},{"title":"事件背景","body":"章节的内容总结"} ]
            [{"title": section["title"], "body": section["body"]} for section in sections],
            ensure_ascii=False,
        )

        report = await self._generate_report(report_context, query)
        logger.info(f"{role_info.agent_name} 章节正文整合为独立研究报告完成")
        self.context.report_progress("generating", f"{role_info.agent_name} 独立报告生成完成", 80)
        return {"final_report": report}

    async def _generate_report(self, report_context: str, query: str) -> str:
        prompt_template = PromptTemplate.from_template(template=AGENT_REPORT_GENERATION_USER_PROMPT)

        user_prompt = prompt_template.format(
            research_topic=query,
            report_context=report_context,
        )

        raw_text = await self.context.llm_client.generate_text(
            system_prompt=AGENT_REPORT_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return raw_text