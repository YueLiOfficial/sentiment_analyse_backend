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
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.research_graph_state import ResearchGraphState


class AgentReportGenerationNode(ResearchNode):
    """将已经生成完毕的各章节正文，按固定顺序整合输出完整markdown研究报告；Insight/Media共用。"""

    async def __call__( # type: ignore
        self,
        state: ResearchGraphState[Any],
    ) -> Dict[str, Any]:
        # 业务实现下一章补齐；当前仅占位pass
        pass