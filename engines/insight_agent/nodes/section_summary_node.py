"""
私域：单章摘要生成节点（子类）
文件：engines/insight_agent/nodes/section_summary_node.py

> 只覆写父类配置：system_prompt、max_rendered_evidence；
> __call__执行逻辑100%继承公共BaseSectionSummaryNode，**不重写**；
> Media公域Agent同样只需要写一个子类，替换自己的prompt、max证据数即可。

## 输入 state字段（继承基类）
query、role、sections、section_evidence_records、cursor

## 输出 state增量字段（继承基类）
sections（更新body）、cursor（+1）
"""
from engines.common.section_summary import BaseSectionSummaryNode
from engines.prompts.insight import (
    INSIGHT_SECTION_SUMMARY_SYSTEM_PROMPT,
)


class SectionSummaryNode(BaseSectionSummaryNode):
    """基于私域证据生成章节正文；仅注入私域专属Prompt与参数，复用公共循环摘要流程。"""
    # 覆写父类配置；业务执行逻辑全部继承基类，无需重写__call__
    system_prompt = INSIGHT_SECTION_SUMMARY_SYSTEM_PROMPT
    max_rendered_evidence = 20