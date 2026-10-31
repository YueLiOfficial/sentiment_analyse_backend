from engines.contracts.section_definitions import SECTION_DEFINITIONS
from engines.host_agent.models import AgentSectionOutput, AgentSectionPair
from typing import cast
# 省略导入：AgentSectionOutput, AgentSectionPair, SECTION_DEFINITIONS

# 需要集齐的两个数据源来源标识：insight私域、media公域
_REQUIRED_SOURCES = ("insight", "media")


class SectionPairStore:
    """
    章节配对内存存储
    按章节key累积保存 Insight / Media 两个Agent输出；
    提供判断就绪、获取待研判配对、标记已研判、全局完成状态判断。
    仅内存逻辑，无IO、无LLM调用，可独立单元测试。
    """

    def __init__(self) -> None:
        # key: section_key 章节唯一标识
        # value: dict[source, AgentSectionOutput]，key为来源"insight"/"media"，值为Agent章节输出对象

        # _outputs_by_section insight / mediaagent 所有章节的总结内容
        # key -> 章节  value -> {insight:AgentSectionOutput,media:AgentSectionOutput}
        self._outputs_by_section: dict[str, dict[str, AgentSectionOutput]] = {}
        # 已经完成Host研判的章节key集合，避免重复研判同一章节
        self._judged_sections: set[str] = set()

    def store_output(self, output: AgentSectionOutput) -> None:
        """
        保存单份Agent章节输出。
        :param output: Agent章节输出对象，携带 section_key、source(insight/media)、章节正文等信息
        逻辑：按section_key分组，再按来源source存入字典；同一来源同一章节会覆盖旧数据。
        """
        # 不存在该章节则新建空dict，再把该来源输出存入
        self._outputs_by_section.setdefault(output.section_key, {})[
            output.source
        ] = output

    def has_ready_pair(self) -> bool:
        """
        判断：是否存在【双来源齐全，并且还没有做过研判】的章节配对。
        :return: True 存在待研判配对；False 暂无可以研判的配对
        遍历全局固定五维章节配置，任意一个满足就绪条件即返回True。
        """
        return any(self._is_pair_ready(section_key) for section_key in SECTION_DEFINITIONS)

    def get_ready_pair(self) -> AgentSectionPair:
        """
        获取**第一个**待研判的章节配对，严格遵循SECTION_DEFINITIONS定义的固定章节顺序。
        :raises StopIteration: 没有就绪配对时会抛出（调用方必须先调用 has_ready_pair() 判断）
        :return: 组装完成的 AgentSectionPair，包含 section_key、title、insight、media两份章节输出
        """
        section_key = next(
            section_key
            for section_key in SECTION_DEFINITIONS
            if self._is_pair_ready(section_key)
        )
        return self._build_section_pair(section_key)

    def mark_judged(self, section_key: str) -> None:
        """
        标记指定章节已经完成Host研判。
        :param section_key: 章节唯一key
        加入 _judged_sections集合，后续 _is_pair_ready 会直接跳过该章节，防止重复LLM研判。
        """
        self._judged_sections.add(section_key)

    def all_sections_judged(self) -> bool:
        """
        判断：**全部五维固定章节是否都已经完成研判**。
        :return: True 所有章节研判完毕；False 还有章节待研判
        使用issuperset：判断已研判集合是否包含全部定义的章节key。
        """
        return self._judged_sections.issuperset(SECTION_DEFINITIONS)

    def _is_pair_ready(self, section_key: str) -> bool:
        """
        【私有辅助方法】判断单个章节是否满足研判就绪条件
        就绪两个条件必须同时成立：
        1. 该章节**尚未被标记为已研判**；
        2. 该章节同时集齐 insight、media 两个来源的输出。
        :param section_key: 待检测章节key
        :return: True 配对就绪，可以执行LLM研判；False 不满足条件
        """
        # {section_key:  ->  {insight:总结, media:总结}}
        outputs = self._outputs_by_section.get(section_key, {})
        return section_key not in self._judged_sections and all(
            source in outputs for source in _REQUIRED_SOURCES
        )

    def _build_section_pair(self, section_key: str) -> AgentSectionPair:
        """
        【私有辅助方法】根据section_key组装AgentSectionPair配对对象
        从缓存取出insight、media两份输出，拼接章节标题，构造配对结构体。
        :param section_key: 就绪章节key
        :return: AgentSectionPair 供Host LLM研判器直接消费
        前置调用保证：_is_pair_ready已经为True，两个source一定存在，不会报KeyError。
        """
        outputs = self._outputs_by_section[section_key]
        return AgentSectionPair(
            section_key=section_key,
            title=SECTION_DEFINITIONS[section_key].title,
            insight=outputs["insight"],
            media=outputs["media"]
        )