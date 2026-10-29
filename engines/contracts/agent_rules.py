"""
角色元数据定义
1. 为每一个业务Agent角色绑定对应的配置前缀，用于从settings读取.env对应的模型参数；
2. 新增agent_name：角色中文展示名称，用于日志打印、SSE事件、前端页面展示；
3. 对外提供工具函数 role_display_name()，输入role_key返回可读中文角色名；
4. 可扩展：未来可以继续扩充字段：temperature、max_tokens、角色系统描述、权限标签等。

角色key枚举：Literal["insight","media","host","report"]
"""
from dataclasses import dataclass
from typing import Literal

# 角色key字面量类型别名：约束系统全部合法角色标识
ROLE_KEY = Literal["insight", "media", "host", "report"]


@dataclass(slots=True)
class RoleInfo:
    """
    角色元数据结构体
    :param confix_prefix: 配置前缀，拼接 _MODEL_NAME / _API_KEY / _BASE_URL，读取settings全局配置
    :param agent_name: 角色中文展示名称，用于日志、事件推送、前端页面展示；例："私域检索智能体专家"
    """
    confix_prefix: str     # 角色的配置前缀，读取.env配置使用
    agent_name: str        # 新增：智能体中文名称，用于日志打印、SSE事件、前端展示


# 业务角色key → 角色完整元数据映射表
ROLE_INFOS: dict[ROLE_KEY, RoleInfo] = {
    "insight": RoleInfo(confix_prefix="INSIGHT_ENGINE", agent_name="私域检索智能体专家"),
    "media": RoleInfo(confix_prefix="MEDIA_ENGINE", agent_name="公域检索智能体专家"),
    "host": RoleInfo(confix_prefix="HOST", agent_name="研判智能体专家"),
    "report": RoleInfo(confix_prefix="REPORT_ENGINE", agent_name="报告引擎")
}


def role_display_name(role_key: ROLE_KEY) -> str:
    """
    根据角色key，返回角色的中文展示名称。
    使用场景：
    1. 日志打印：日志中输出中文角色名，排错阅读友好；
    2. SSE实时事件：推送给前端页面，展示当前是哪个Agent在执行；
    3. 报告产物、进度提示文案；

    :param role_key: 系统内部角色标识：insight / media / host / report
    :return str: 中文可读角色名称
    """
    return ROLE_INFOS[role_key].agent_name