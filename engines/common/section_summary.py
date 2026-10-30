"""
跨Agent公共：章节摘要生成基类
文件：engines/common/section_summary.py

> Insight私域、Media公域共用本套循环执行逻辑；子类仅覆盖prompt、最大证据条数、降级fallback文案等配置；
> __call__完整通用流程：
> 1. 读取cursor，定位当前待处理章节sections[cursor]、对应章节证据section_evidence_records[cursor]
> 2. 读取全局静态章节配置，拿到当前章节role专属写作guidance
> 3. 对当前章节证据做切片，最多取max_rendered_evidence条，防止Prompt过长
> 4. 内存临时构造EvidenceContext（Prompt渲染中间对象；仅本调用栈存活；**绝不存入state，用完销毁**）
> 5. system_prompt + user_prompt_template + 证据上下文，组装完整LLM请求
> 6. 调用LLM生成章节body正文；捕获LLM异常，使用fallback_body降级兜底
> 7. 高频大坑：**禁止原地修改state["sections"]！做浅拷贝副本，给副本中当前section新增body字段**
> 8. cursor = cursor + 1；
> 9. 调用context.progress_callback上报细粒度进度：例如「正在生成第 {cursor+1}/{总章节数} 章节」
> 10. 返回增量字典：更新后的完整sections数组 + 新cursor；

## 子类可覆盖配置（子类只改这些，不用碰执行流程）
- system_prompt：系统提示词
- user_prompt_template：用户侧prompt模板
- fallback_body：LLM调用失败时的降级兜底章节文案
- max_rendered_evidence：单章送入LLM最大证据条数，做截断，控prompt长度

## 输入 state（通用，Insight/Media都兼容）
- query：用户原始查询
- role：Agent角色枚举
- sections：list[SectionState]，章节骨架；部分章节可能已经生成body（断点恢复场景）
- section_evidence_records：list[list[EvidenceRecord]]；下标与sections、cursor对齐
- cursor：int；当前待处理章节下标

## 输出 state增量字段
- sections：list[SectionState]；浅拷贝后的新数组；当前cursor对应章节新增body字段
- cursor：int；自增之后的游标
"""
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode


class BaseSectionSummaryNode(ResearchNode):
    """Insight 与 Media 共享的章节摘要节点基类；子类仅覆写配置，复用全部__call__执行逻辑。"""
    # ========== 子类可覆写配置项 ==========
    system_prompt: str = ""
    user_prompt_template: str = ""
    fallback_body: str = "【本章内容生成失败：大模型调用异常，无法产出章节正文】"
    max_rendered_evidence: int = 8

    async def __call__(self, state: dict[str, Any]) -> Dict[str, Any]:
        # 完整通用业务流程，下一章补齐；当前占位pass
        pass