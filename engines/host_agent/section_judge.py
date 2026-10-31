"""
engines/host_agent/section_judge.py
Host LLM研判器｜能力层工具类

归属：Host能力层；被 generate_judgement_node LangGraph节点调用。

职责：接收已经配对就绪 AgentSectionPair，调用Host专用LLM，产出结构化裁决 SectionJudgement。

边界：只做LLM研判；不操作存储、不发布事件、不磁盘IO；纯能力，支持独立单元测试。

数据流：
section_pair_store(取出就绪AgentSectionPair)
        → nodes.generate_judgement_node
            → HostSectionJudge.judge_section(pair)
                → LLM生成结构化输出
                    → 返回 SectionJudgement 回到nodes节点，写入state瞬时字段

关键业务防御点：
1. insight/media正文各自截断前3000字符，控制prompt总token；
2. 组装结构化JSON上下文给到LLM，提升结构化输出稳定性；
3. 强制覆盖section_key：不信任LLM返回的section_key字段；使用输入pair真实section_key做model_copy更新；
   规避大模型幻觉：输入A章节，LLM输出B章节key，造成报告、讨论区全部张冠李戴。

Prompt约束全部下沉prompts/host.py，代码不写业务规则。
业务铁律：单方信息缺失不等于实质性冲突；不能凭空编造原始两份材料不存在的事实。

单元测试提示：
- 可mock llm_client.generate_object返回mock SectionJudgement；
- 重点回归防御逻辑：即使LLM返回错误section_key，输出会被强制覆盖成输入pair的key。

优化建议（仅教案记录，不改业务源码）：
当前 llm_client 是类静态属性；单元测试mock静态属性语法繁琐；建议改为构造函数注入llm_client，build_graph的时候注入judge实例，mock会非常简单。
"""
import json
from langchain_core.prompts import PromptTemplate

from engines.common.llm import LLMClient
from engines.contracts.judgement import SectionJudgement
from engines.host_agent.models import AgentSectionPair
from engines.prompts.host import (
    HOST_SECTION_JUDGE_SYSTEM_PROMPT,
    HOST_SECTION_JUDGE_USER_PROMPT
)


class HostSectionJudge:
    """调用 Host 角色LLM，对 Insight 与 Media 的同章节就绪配对输出，执行结构化研判。"""
    # 静态类属性：Host角色独立LLM配置 role="host"，和insight/media模型配置隔离
    llm_client: LLMClient = LLMClient.from_role("host")

    async def judge_section(
            self,
            section_pair: AgentSectionPair
    ) -> SectionJudgement:
        """
        对一组已经配对就绪的章节，执行Host结构化研判。
        :param section_pair: 就绪配对对象，同一个section_key集齐insight+media双份输出
        :return: SectionJudgement 结构化裁决对象；section_key已经被代码强制覆盖，不使用LLM输出的key
        """
        # 1.组装LLM输入上下文JSON字符串
        judgement_evidence = self._build_judgement_context(section_pair)

        # 2.填充user prompt模板
        prompt = PromptTemplate.from_template(HOST_SECTION_JUDGE_USER_PROMPT).format(
            judgement_evidence=judgement_evidence
        )

        # 3.调用Host角色LLM，指定输出schema=SectionJudgement，做结构化输出校验
        judgement = await self.llm_client.generate_object(
            HOST_SECTION_JUDGE_SYSTEM_PROMPT,
            prompt,
            SectionJudgement,
        )

        # 核心防御：强制覆盖section_key，不信任LLM输出
        # 风险：大模型幻觉，输入是A章节，LLM返回judgement里面section_key错写成别的章节；
        # 使用输入pair的真实section_key覆盖，杜绝后续存储、事件、报告全部张冠李戴BUG
        # judgement -> section_key -> 模型 -> AgentSectionPair 识别出来
        # judgement.model_copy(update={"section_key": section_pair.section_key})
        # 怕key提错了! 手动更新覆盖下!judgement.section_key = section_pair.key
        # judgement.model_copy 复制一个新的对象(默认浅copy) deep=True, update = section_key = section_pair.section_key
        return judgement.model_copy(update={"section_key": section_pair.section_key})

    def _build_judgement_context(
            self,
            section_pair: AgentSectionPair,
    ) -> str:
        """
        组装当前双Agent同章节输出的LLM上下文。
        输出：json字符串给到user prompt；
        处理：insight、media正文各截断前3000字符，防止prompt超长token爆炸；
        结构化JSON入参，相比直接塞大段自由文本，LLM更容易区分两块材料边界，提升结构化输出稳定性。
        """
        judgement_context = {
            "section": {
                "key": section_pair.section_key,
                "title": section_pair.title,
            },
            "insight": {"body": section_pair.insight.body[:3000]},
            "media": {"body": section_pair.media.body[:3000]},
        }
        return json.dumps(judgement_context, ensure_ascii=False)