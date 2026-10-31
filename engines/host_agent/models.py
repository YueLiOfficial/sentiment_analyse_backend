# engines/host_agent/models.py
"""
host_agent/models.py
Host本地领域模型；仅host_agent包内部使用。
注意：跨组件公共研判输出模型 SectionJudgement 在 contracts/judgement.py，不要在此拷贝。
"""
from dataclasses import dataclass
from typing import Literal, Any


@dataclass(frozen=True)
class AgentSectionOutput:
    """单一个上游Agent产出的单章节输出；来自SECTION_READY事件解析。"""
    source: Literal["insight", "media"]
    section_key: str    # 总结对应的key!  engines/contracts/section_definitions.py
    body: str           # 章节内容

    @classmethod
    def from_section_ready_event(
            cls,
            event_payload: dict[str, Any]
    ) -> "AgentSectionOutput":
        """从章节就绪事件载荷构造 Agent 章节输出。"""
        return cls(
            source=event_payload["source"],
            section_key=event_payload["section_key"],
            body=event_payload["body"]
        )


@dataclass(frozen=True)
class AgentSectionPair:
    """就绪配对：同一个section_key，同时具备insight和media的输出；送入HostSectionJudge做LLM研判。"""
    section_key: str    # 总结对应的key!
    title: str          # 章节标题
    insight: AgentSectionOutput
    media: AgentSectionOutput