"""
engines/report_engine/engine.py
报告生成引擎：负责驱动 LLM 生成 Markdown 报告、渲染 HTML 并落盘
业务流程：
1. _generate_markdown：组装prompt，调用report角色LLM，由大模型整合insight、media、host_judgements生成最终报告markdown；
2. 调用renderer工具：markdown转html片段，再套完整html页面模板；
3. _save_final_report：将md、html两份产物调用公共save_report落盘磁盘，组装ReportOutput返回。
"""
import json

from langchain_core.prompts import PromptTemplate
from loguru import logger

from engines.common.llm import LLMClient
from engines.common.reports import save_report, get_output_dir
from engines.contracts.section_definitions import SECTION_DEFINITIONS
from engines.prompts.report import (
    FINAL_REPORT_GENERATION_SYSTEM_PROMPT,
    FINAL_REPORT_GENERATION_USER_PROMPT
)
from engines.report_engine.models import ReportInput, ReportOutput
from engines.report_engine.renderer import render_html, render_markdown


class ReportEngine:
    """报告生成引擎：负责驱动 LLM 生成 Markdown 报告、渲染 HTML 并落盘"""

    def __init__(self):
        """初始化报告引擎并绑定LLM客户端
        使用role=report专用的LLMClient实例，用于最终综合报告生成
        """
        # 1. 实例化专门用于报告生成角色的 LLM 客户端
        self._llm_client = LLMClient.from_role("report")

    async def generate_report(
            self,
            report_input: ReportInput
    ) -> ReportOutput:
        """完整综合报告生成的工作流：生成 Markdown、渲染 HTML 并保存文件
        入参：ReportInput，包含query、双agent报告、host全部结构化judgements
        返回：ReportOutput，内存html文本 + 两份磁盘产物路径、文件名
        """
        # 1. 以 Host 研判为结论依据，结合双 Agent 报告生成最终 Markdown
        markdown = await self._generate_markdown(report_input)
        # 2. 将 Markdown 渲染为 HTML 格式文本
        html = render_html(render_markdown(markdown), report_input.query)
        # 3. 将生成的 Markdown 和 HTML 文件保存到本地磁盘并返回元数据
        return self._save_final_report(
            report_input.task_id,
            report_input.generation_id,
            markdown,
            html
        )

    async def _generate_markdown(self, report_input: ReportInput) -> str:
        """根据结构化 Host 研判和双 Agent 报告生成最终 Markdown。
        核心：组装system+user prompt，把章节元数据、host裁决json、insight原始md、media原始md全部送入LLM，由大模型输出整合后的完整报告markdown。
        """
        # 1. 提取固定章节定义，构建最终报告的章节上下文
        section_contexts = [
            {
                "section_key": section.key,
                "title": section.title
            }
            for section in SECTION_DEFINITIONS.values()
        ]
        # 2. 将 Host 章节研判转换为可序列化数据
        host_judgements = [
            judgement.model_dump()
            for judgement in report_input.host_judgements
        ]
        # 3. 将章节上下文和 Host 研判序列化为提示词所需的 JSON
        section_contexts_json = json.dumps(
            section_contexts,
            ensure_ascii=False,
            indent=2
        )
        host_judgements_json = json.dumps(
            host_judgements,
            ensure_ascii=False,
            indent=2
        )
        # 4. 结合研究主题、结构化上下文和双 Agent 原始报告构建用户提示词
        user_prompt_template = PromptTemplate.from_template(
            FINAL_REPORT_GENERATION_USER_PROMPT
        )
        user_prompt = user_prompt_template.format(
            research_topic=report_input.query,
            section_contexts=section_contexts_json,
            host_judgements=host_judgements_json,
            insight_report=report_input.insight_report,
            media_report=report_input.media_report
        )
        # 5. 调用报告角色的 LLM 生成最终 Markdown
        return await self._llm_client.generate_text(
            FINAL_REPORT_GENERATION_SYSTEM_PROMPT,
            user_prompt
        )

    def _save_final_report(
            self,
            task_id: str,
            generation_id: str,
            markdown: str,
            html: str
    ) -> ReportOutput:
        """将生成的 Markdown 和 HTML 综合报告写入本地磁盘
        文件命名：使用generation_id作为文件名，区分每一次报告生成产物；
        存储路径：{task_output_dir}/report/
        """
        # 1. 使用本次研究运行的独立最终报告目录(save_report 内部会建目录)
        report_dir = get_output_dir(task_id, "report")
        # 2. 将 Markdown 和 HTML 报告分别保存到磁盘
        markdown_path = save_report(report_dir, f"{generation_id}.md", markdown)
        html_path = save_report(report_dir, f"{generation_id}.html", html)
        # 3. 记录落盘成功日志并组装返回综合报告元数据
        logger.info(f"报告已落盘: {html_path}")
        return ReportOutput(
            html_content=html,
            report_filepath=str(html_path),
            report_filename=html_path.name,
            markdown_filepath=str(markdown_path),
            markdown_filename=markdown_path.name,
        )