"""
固定报告章节配置与检索路由规则。
核心作用：
1. 硬编码定义整套舆情报告的全部章节，不交给LLM自由生成章节，保证报告输出结构可控；
2. 同一套章节，同时提供 insight私域、media公域两套不同的写作指导；
3. 保存私域证据路由关键词，用于把证据自动分配到对应章节；
4. 提供工具函数：查询章节、按角色获取章节配置、提取路由关键词。
"""
from dataclasses import dataclass
from engines.contracts.agent_rules import ROLE_KEY


@dataclass(slots=True)
class SectionDefinition:
    """
    单份章节定义【静态配置对象，程序启动就固定，任务运行全程不变】
    key: 章节唯一标识，程序内部使用，和state当中section_key一一对应
    title: 报告最终展示的中文标题，输出markdown/html报告对外展示
    insight_section_guidance: insight私域Agent的章节写作提示要求，给LLM做输出约束
    media_section_guidance: media公域Agent的章节写作提示要求
    insight_routing_keywords: 私域证据路由关键词，命中关键词的证据会倾向分配给该章节
    """
    key: str
    title: str
    insight_section_guidance: str
    media_section_guidance: str
    insight_routing_keywords: tuple[str, ...] = ()

    def section_guidance_for(self, role: ROLE_KEY) -> str:
        """
        根据传入Agent角色，返回对应版本的章节写作指导
        :param role: 角色枚举 insight / media
        :return: 该角色使用的章节guidance文本，送入LLM Prompt
        """
        if role == "insight":
            return self.insight_section_guidance
        if role == "media":
            return self.media_section_guidance
        raise ValueError(f"角色不支持章节写作指导: {role}")


# 全局字典：存放全部5个固定章节配置，程序加载模块时初始化
SECTION_DEFINITIONS: dict[str, SectionDefinition] = {
    "background_overview": SectionDefinition(
        key="background_overview",
        title="事件背景与概览",
        insight_section_guidance=(
            "基于当前可见的微博、抖音帖子和评论样本梳理事件主线、讨论范围和"
            "关键时间点；仅概括材料中明确陈述的信息，不将用户表达视为已核实事实。"
        ),
        media_section_guidance=(
            "基于公开网页梳理事件主线、关键时间点、主要信源和事实框架，"
            "区分信源直接陈述、媒体转述与尚未核实的信息。"
        ),
        insight_routing_keywords=(
            "通报",
            "公告",
            "声明",
            "官方回应",
            "事发",
            "经过",
            "时间线",
            "调查",
            "进展",
            "结果",
            "现场",
        ),
    ),
    "heat_and_spread": SectionDefinition(
        key="heat_and_spread",
        title="舆情热度与传播",
        insight_section_guidance=(
            "结合热度分与点赞、评论、转发等互动数据，分析微博和抖音样本中的"
            "高热内容与传播特征；不同平台指标口径不一致时避免直接比较绝对数值。"
        ),
        media_section_guidance=(
            "梳理公开报道中可识别的传播时间线、扩散节点和平台热度描述；"
            "缺少量化数据时不推断实际传播规模。"
        ),
        insight_routing_keywords=(
            "热搜",
            "热度",
            "话题榜",
            "传播",
            "阅读量",
            "播放量",
            "转发量",
            "讨论量",
            "发酵",
            "刷屏",
            "扩散",
            "引爆",
            "冲上热搜",
        ),
    ),
    "sentiment_and_opinion": SectionDefinition(
        key="sentiment_and_opinion",
        title="公众情感与观点",
        insight_section_guidance=(
            "提炼微博、抖音帖子及评论样本中的主要情绪、观点类型和典型表达，"
            "归纳重复出现或相互冲突的观点，不将当前样本视为总体民意。"
        ),
        media_section_guidance=(
            "分析公开报道的叙事倾向及其引用的公众反馈，"
            "区分媒体表述、受访者观点和用户意见。"
        ),
        insight_routing_keywords=(
            "支持",
            "反对",
            "赞同",
            "质疑",
            "吐槽",
            "愤怒",
            "担心",
            "理解",
            "争议",
            "不满",
            "失望",
            "焦虑",
            "同情",
            "谴责",
            "抵制",
            "期待",
            "嘲讽",
        ),
    ),
    "platform_and_group_diff": SectionDefinition(
        key="platform_and_group_diff",
        title="平台与群体差异",
        insight_section_guidance=(
            "比较微博帖子及评论、抖音作品文案及评论的讨论重点和表达差异；"
            "任一平台样本不足时明确说明，不推断缺乏证据支持的用户画像。"
        ),
        media_section_guidance=(
            "比较不同媒体网站和信源类型的选题重点、叙事角度与表达差异，"
            "说明比较范围和证据限制。"
        ),
        insight_routing_keywords=(
            "微博",
            "抖音",
            "不同平台",
            "群体差异",
            "专家",
            "大V",
            "粉丝",
            "消费者",
            "家长",
            "学生",
            "年轻人",
            "从业者",
            "当地居民",
        ),
    ),
    "deep_causes_and_impact": SectionDefinition(
        key="deep_causes_and_impact",
        title="深层原因与影响",
        insight_section_guidance=(
            "基于微博、抖音可见样本分析争议成因、潜在影响和后续舆情风险，"
            "区分用户归因、材料陈述与分析性推断。"
        ),
        media_section_guidance=(
            "基于公开报道分析社会背景、争议成因、潜在影响和传播风险，"
            "区分信源结论与媒体分析，避免将相关性表述为因果关系。"
        ),
        insight_routing_keywords=(
            "原因",
            "根源",
            "机制",
            "制度",
            "结构性",
            "利益",
            "治理",
            "风险",
            "危机",
            "信任",
            "后果",
            "隐患",
            "公信力",
            "连锁反应",
            "长期影响",
            "监管",
            "问责",
        ),
    ),
}


def find_section_definition(key: str) -> SectionDefinition | None:
    """
    根据章节key查找章节配置对象
    :param key: 章节内部key，例如 background_overview
    :return: 找到返回SectionDefinition，找不到返回None
    """
    return SECTION_DEFINITIONS.get(key)


def get_section_definitions_for_role(role: ROLE_KEY) -> list[dict[str, str]]:
    """
    根据Agent角色，获取该角色全部章节配置列表
    返回简化字典，包含章节key、展示标题、对应角色的写作指导，供给LLM提示词使用
    """
    return [
        {
            "section_key": section.key,
            "title": section.title,
            "section_guidance": section.section_guidance_for(role),
        }
        for section in SECTION_DEFINITIONS.values()
    ]


def get_insight_routing_rules() -> dict[str, tuple[str, ...]]:
    """
    提取私域Agent证据路由规则
    key：章节key；value：该章节匹配的关键词元组
    给证据路由节点使用，用来把证据分配到对应章节
    """
    return {
        section.key: section.insight_routing_keywords
        for section in SECTION_DEFINITIONS.values()
    }