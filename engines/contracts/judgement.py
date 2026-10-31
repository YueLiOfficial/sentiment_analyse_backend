"""主持人结构化裁决契约:Host 与 Report 引擎共享的裁决模型与 Markdown 渲染。"""

from pydantic import BaseModel, Field


def format_markdown_list(items: list[str]) -> str:
    """渲染无序列表"""
    return "\n".join(f"- {item}" for item in items) or "- 暂无"


def render_judgement_markdown(judgement: "SectionJudgement") -> str:
    """将结构化裁决渲染为 Markdown,标题层级按嵌入上下文调整。"""
    heading_level = "#" * 3
    blocks = [
        judgement.host_judgement or "暂无研判",
        f"{heading_level} 双方一致观点\n"
        f"{format_markdown_list(judgement.aligned_points)}",
        f"{heading_level} 关键分歧\n"
        f"{format_markdown_list(judgement.conflicts)}",
        f"{heading_level} 证据情况与信息缺口\n"
        f"{judgement.evidence_review or '暂无补充'}",
    ]
    return "\n\n".join(blocks)


class SectionJudgement(BaseModel):
    """主持人对单个章节的结构化裁决。
    跨模块公共契约：Host产出、磁盘judgements.json序列化、报告引擎读取全部复用；
    .content 是@property运行时计算属性，**不会序列化写入磁盘json**；磁盘仅保存原始结构化字段。
    """
    #aligned_points：哪些是两边都认可的确定事实（共识，list）
    # conflicts：哪些是两边都有信息但是真的打架（真冲突，list）
    # evidence_review：哪些资料缺、哪边视角没覆盖、证据质量怎么样（证据缺口，长文本，不输出观点）
    # host_judgement：主持人综合全部信息，给出本章最终综合研判（主持人总结，长文本，面向决策者）
    # section_key：元数据：标记这份裁决归属哪一章，用于路由、索引、回填报告
    section_key: str
    aligned_points: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    evidence_review: str
    host_judgement: str

    @property
    def content(self) -> str:
        """渲染讨论区展示用的 Markdown 文本。运行时动态计算，不落地磁盘。"""
        return render_judgement_markdown(self)