"""
公共节点：报告与证据快照落盘持久化节点
文件：engines/common/report_persistence_node.py

> 完全通用；Insight、Media共用；**不修改任何报告业务内容，只负责IO持久化**；
> 数据源：
> 1. final_report：完整markdown报告文本，写入report.md；
> 2. retrieved_records：**Step1原始召回证据全集，写入evidence.json证据快照**；
>    > 快照使用原始全集，而不是重排/分章子集；目的：完整复现本次任务全部原始证据，人工核验报告结论、做评估回归测试。
> 3. 输出目录不从state读取！输出目录属于运行环境配置，从self.context.output_dir（ResearchRunContext）获取；state不存文件路径。

## 输入 state字段
- final_report：str，完整markdown报告文本
- retrieved_records：list[EvidenceRecord]，原始召回证据全集，用于输出evidence.json快照
- task_id：任务唯一标识，用于拼接子目录

## 输出 state增量字段
- 本节点**只做磁盘IO，不产出新业务state字段；返回空增量字典 {}**；
> 全部业务产物输出到磁盘文件：
> - {output_dir}/{task_id}/report.md
> - {output_dir}/{task_id}/evidence.json

## 上下游
上游：AgentReportGenerationNode
下游：Graph END，任务结束
"""
from typing import Any

from loguru import logger

# 通用报告保存工具，多个Agent共用
from engines.common.reports import save_report
from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.research_graph_state import ResearchGraphState


class ReportPersistenceNode(ResearchNode):
    """将 Agent 独立报告落盘并注册到研究运行。"""

    async def __call__(self, state: ResearchGraphState[Any]) -> dict[str, Any]: # type: ignore
        """
        LangGraph节点入口，报告持久化落盘
        :param state: 研究图状态，需要包含role、query、final_report
        :return: 空字典，本节点不更新graph状态，只做文件IO副作用
        """
        # 获取角色信息，仅用于日志打印，不参与文件逻辑
        role = state['role']
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始进行独立报告落盘")
        self.context.report_progress("completed", f"{role_info.agent_name} 开始保存独立报告", 90)
        # 读取上游节点生成完毕的完整markdown报告文本
        final_report = state["final_report"]

        # 调用公共保存工具：输出目录来自运行上下文，文件名使用query，传入报告文本
        md_path = save_report(
            self.context.output_dir,
            f"report.md",
            final_report,
        )

        logger.info(f"{role_info.agent_name} 独立报告落盘完成：{md_path}")
        self.context.report_progress("completed", f"{role_info.agent_name} 独立报告保存完成", 100)
        # 节点约定：无状态变更，返回空字典
        return {}