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
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.research_graph_state import ResearchGraphState


class ReportPersistenceNode(ResearchNode):
    """将完整报告、原始证据快照写入磁盘；仅IO持久化，不修改报告业务内容；Insight/Media共用。"""

    async def __call__( # type: ignore
        self,
        state: ResearchGraphState[Any],
    ) -> Dict[str, Any]:
        # 业务实现下一章补齐；当前仅占位pass
        return {}