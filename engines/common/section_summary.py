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
import json
from typing import Any

from langchain_core.prompts import PromptTemplate
from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.evidence import EvidenceRecord
from engines.prompts.shared import SECTION_SUMMARY_USER_PROMPT
from engines.contracts.section_definitions import find_section_definition
from engines.contracts.evidence import build_evidence_context, EvidenceContext


class BaseSectionSummaryNode(ResearchNode):
    """章节摘要节点基类:游标推进、证据组装、LLM 生成摘要与事件发布。"""
    # 子类可以重写这几个类变量
    system_prompt: str = ""
    user_prompt_template: str = SECTION_SUMMARY_USER_PROMPT
    max_rendered_evidence: int = 10   # 每个章节最多喂给LLM多少条证据，防止上下文溢出
    fallback_body: str = ""           # 章节无证据时候填充的默认正文

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """按游标取证据包生成章节正文并发布就绪事件。"""
        role = state['role']
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始按游标取章节证据包生成章节正文。")

        # 总结到第几个章节里 !  cursor 0-4
        cursor = state.get("cursor", 0)   # 取出当前游标，默认0
        # 章节信息列表 [章节1(key,title,body), 章节2, 章节3, 章节4, 章节5]
        sections = list(state.get("sections", [])) # copy一份列表，不修改原始state对象
        # 终止条件：游标超过/等于章节总数，循环结束，直接返回sections
        if cursor >= len(sections):
            return {"sections": sections}


        section = sections[cursor]   # 拿到当前需要处理的章节dict

        # 取出当前章节对应的证据列表 section_evidence_records[cursor]
        section_records = self._section_records(state, cursor)
        if not section_records:
            # 当前章节没有证据，跳过LLM调用，直接填充fallback_body
            logger.info(f"【章节 {section.get('section_key')}】证据上下文为空,跳过生成。")
            section["body"] = self.fallback_body
        else:
            # 把证据列表组装成LLM可用的文本上下文对象 EvidenceContext
            #  evidence_context (retrieval_text = 问题 , records = 章节信息整合字符串 "[章节1] x x x \n\n [章节2] xxxx" )
            evidence_context = build_evidence_context(
                retrieval_text=self._retrieval_text(state,cursor),  # 搜索的问题
                records=section_records,  # 证据
                max_rendered=self.max_rendered_evidence, # 需要证据最大的条数  :20
            )
            # 调用LLM生成章节正文body
            section["body"] = await self._generate_section_body(
                state,
                section,
                evidence_context,
            )
        # 把修改完body的章节写回数组对应下标
        # [{key,title,body},{key,title,body=None}]
        sections[cursor] = section

        # TODO 发布摘要生成事件给HostAgent，做章节研判（事件总线预留点）
        # 一个章节总结完毕 -> HostAgent做章节研判

        logger.info(f"{role_info.agent_name} 按游标取章节证据包生成章节正文完成。")
        # 返回：更新后的sections，游标+1，下一轮处理下一章
        return {"sections": sections, "cursor": cursor + 1}

    def _section_records(self, state: dict[str, Any], cursor: int) -> list[EvidenceRecord]:
        """取当前游标章节的证据记录,缺省返回空列表。"""
        # [[],[],[],[],[]]
        section_records = state.get("section_evidence_records", [])
        if cursor >= len(section_records):
            return []
        return section_records[cursor]

    def _retrieval_text(self, state: dict[str, Any],cursor:int) -> str:
        """章节证据对应的检索文本，默认取研究主题query；子类可以重写。"""
        return state["query"]

    async def _generate_section_body(
            self,
            state: dict[str, Any],
            section: dict[str, Any],
            evidence_context: EvidenceContext,
    ) -> str:
        """调用 LLM 生成章节正文并清洗 Markdown"""
        section_key = section["section_key"]
        section_definition = find_section_definition(section_key)

        # 组装章节元信息
        section_context = {
            "title": section.get("title"),
            "section_key": section_key,
            "section_guidance": section_definition.section_guidance_for(state["role"]) # type: ignore
        }

        # PromptTemplate填充用户提示词
        user_prompt = PromptTemplate.from_template(template=self.user_prompt_template).format(
            retrieval_text=evidence_context.retrieval_text,
            section_context=json.dumps(section_context, ensure_ascii=False, indent=2),
            evidence_text=evidence_context.evidence_text,
        )

        # 使用节点持有的llm_client发起调用
        body = await self.context.llm_client.generate_text(self.system_prompt, user_prompt)

        return body