"""
# common/events.py
## 模块定位：进程内存内事件总线（同步回调式事件系统）
> 重要：这是**单机进程内内存事件总线，不是分布式MQ**；仅用于本服务内部模块解耦通信，不能跨机器。

## 核心能力
1. 定义全系统标准事件枚举 EventType；
2. 定义标准事件Pydantic数据模型：
   - SectionReadyEvent：Agent单章节产出完成事件；HostAgent的输入事件
   - HostDiscussionMessageEvent：Host主持人输出的虚拟研讨会消息事件，供给前端
3. 提供底层原语：subscribe / publish / unsubscribe，实现订阅‑回调模式；
4. 提供业务层快捷发布工具函数 publish_section_ready / publish_host_discussion_message；
   > 业务代码优先调用快捷发布函数，不要直接调用底层publish，便于统一埋点、日志、格式校验。

## 关键实现约束（踩坑点）
1. publish发布时，调用 event.model_dump()，**总线流转的是普通dict字典，不是Pydantic对象实例**；
   订阅者回调拿到payload是dict；需要手动解析为Pydantic模型，不要直接强转。
2. 事件回调是**同步执行**：publish会串行调用所有订阅者callback；回调内部不要做耗时IO、不要长时间阻塞；耗时逻辑丢到后台协程队列。
3. 内置异常隔离：单个订阅callback抛异常，只打印error日志，**不会打断其他订阅者执行，也不会向上抛给发布方**。
4. unsubscribe：传入callback函数对象，会从全部事件类型的订阅集合移除该回调。
5. 内存总线：进程重启，内存订阅关系、队列中未分发事件全部丢失；生产如需持久化/跨实例，需要外接MQ。

## 事件流转一览
### 1. SECTION_READY
生产方：insight_agent / media_agent（上游两个研究Agent）
消费方：host_agent/section_ready_listener.py（Host监听器）
数据：task_id、source(agent角色)、section_key章节id、body章节正文

### 2. HOST_DISCUSSION_MESSAGE
生产方：host_agent/nodes.py（Host LangGraph节点）
消费方：
  ① host_agent/service.py：内存缓冲讨论消息，给API查询前端展示
  ② 可扩展：日志、事件落库持久化组件
数据：task_id、source[insight/media/host]、content渲染后markdown、section_key
"""

from enum import Enum
from typing import Any, Callable, Literal, Mapping

from loguru import logger
from pydantic import BaseModel

from engines.contracts.agent_rules import role_display_name


class EventType(str, Enum):
    """
    全系统事件类型枚举。
    所有业务事件都在此注册，统一管理事件字符串常量，避免魔法字符串散落业务代码。

    事件分类：
    - ROLE_*：Agent执行进度、错误、最终结果类通用事件
    - SECTION_READY：【核心】Agent单章节生成完毕，通知下游Host主持人模块
    - HOST_DISCUSSION_MESSAGE：【核心】Host主持人产出虚拟研讨会消息事件，用于前端讨论区
    """
    ROLE_PROGRESS = "role_progress"          # Agent执行进度更新事件
    ROLE_ERROR = "role_error"                # Agent执行报错事件
    ROLE_RESULT = "role_result"              # Agent整体全部执行完成返回总结果
    # 以上 media/insight -> 前端返回进度
    
    # 
    SECTION_READY = "section_ready"         # 单章节产出就绪事件；Host模块输入源
    # 接收 media/insight -> host 
    HOST_DISCUSSION_MESSAGE = "host_discussion_message"  # Host输出讨论消息事件
    # host -> 前端

# todo 新添加内容
class RoleProgressEvent(BaseModel):
    """
    角色增量进度更新事件（对应EventType.ROLE_PROGRESS）
    触发时机：角色启动、内部各个业务节点执行完成、百分比变更；可多次发布。
    注意：当前模型**不携带结构化section_key**；单章节信息只能放在message字符串内；
    字段：
        task_id: 全局任务唯一id
        role: 角色枚举 "insight" / "media"
        status: 状态字符串：starting/searching/planning/summary 等，由各个node上报传入
        message: 人类可读进度描述文案，前端UI展示用
        progress_pct: 当前角色整体进度百分比，0‑100整数
    """
    task_id: str
    role: str
    status: str
    message: str
    progress_pct: int = 0

# todo 新添加内容
class RoleResultEvent(BaseModel):
    """
    角色执行成功终态事件（EventType.ROLE_RESULT）
    触发时机：insight/media整个角色全部业务流程完整执行完毕，无异常；一个角色任务只发布一次。
    代表：该role下全部证据检索、证据处理、全部5个章节摘要全部生成完成；
    字段：
        task_id:全局任务id
        role: "insight" / "media"
    """
    task_id: str
    role: str


# todo 新添加内容
class RoleErrorEvent(BaseModel):
    """
    角色执行失败终态事件（EventType.ROLE_ERROR）
    触发时机：orchestrator顶层捕获该role任务的未处理异常；
    局限：仅捕获**整个Agent任务顶层抛出的异常**；如果异常发生在graph内部node，被LangGraph内部捕获吃掉，不会走到这里，不会发布ROLE_ERROR；
    字段：
        task_id:全局任务id
        role:发生异常的角色
        error: 异常字符串描述，前端错误提示展示
    """
    task_id: str
    role: str
    error: str


class SectionReadyEvent(BaseModel):
    """
    章节就绪事件：上游Insight/Media Agent完成**单个章节**之后发布。
    > 生产：insight_agent / media_agent，调用 publish_section_ready
    > 消费：host_agent.section_ready_listener 监听器订阅该事件，作为Host模块入口输入

    注意：
    - source字段为字符串，不一定是严格Literal；角色展示请统一使用 role_display_name(source)，不要硬编码判断字符串；
    - body：该章节完整生成正文，注意正文可能很大，事件总线传递大字符串会占用内存；超长正文建议传对象存储URL。
    - 该事件**每完成一个章节就发一次**；一个task会产生N次SECTION_READY。
    """
    task_id: str          # 任务全局唯一ID，用来区分不同用户的舆情分析任务
    source: str           # 产出该章节的Agent角色："insight" / "media"；通用字符串，不强制Literal
    section_key: str      # 章节唯一标识，来自 SECTION_DEFINITIONS，例如 bg_overview risk_analysis
    body: str             # 该章节Agent生成的完整正文内容


class HostDiscussionMessageEvent(BaseModel):
    """
    Host虚拟研讨会讨论消息事件。
    > 生产：host_agent/nodes.py，构建对象后调用 publish_host_discussion_message
    > 消费：HostService内存缓冲 → FastAPI接口 → 前端页面讨论区；也可以订阅做事件持久化落库

    业务区分source：
    - source="insight"：Insight私域Agent的章节发言，content是截断后的章节正文
    - source="media"：Media公域Agent的章节发言，content是截断后的章节正文
    - source="host"：Host主持人裁决发言，content = SectionJudgement.content 属性渲染完成的Markdown

    重要：content字段**永远是给前端直接展示的渲染后Markdown字符串**；
    结构化原始裁决数据不在这个事件里；结构化数据保存在Host内存快照，由任务管理器写入 judgements.json。
    """
    task_id: str
    source: Literal["insight", "media", "host"]  # 这条讨论消息是谁发出的
    content: str                                 # 前端直接渲染展示的markdown文本
    section_key: str                             # 该消息归属哪个业务章节tab


# ====================== 底层事件总线原语（不要业务直接调用，优先用业务封装函数） ======================

"""
事件回调函数签名定义：
回调入参：(事件类型枚举, model_dump之后的dict载荷)
重点：callback收到的payload是dict，**不是Pydantic模型实例**，需要业务代码手动解析。
"""
EventCallback = Callable[[EventType, dict[str, Any]], None]

# 全局订阅注册表
# key: EventType 事件类型
# value: set[EventCallback] 该事件的全部订阅回调函数集合
# 使用set：避免同一个callback重复订阅造成重复执行
_subscribers: dict[EventType, set[EventCallback]] = {}


def subscribe(event_type: EventType, callback: EventCallback):
    """
    订阅某一类事件。
    :param event_type: 需要监听的事件类型枚举
    :param callback: 回调函数，签名 EventCallback；回调入参是dict载荷，非Pydantic对象
    注意：回调函数内部禁止阻塞、禁止长耗时IO；publish是同步串行调用全部回调；耗时逻辑请丢到asyncio队列。
    重复传入同一个callback函数对象，set会自动去重，不会重复触发。
    """
    _subscribers.setdefault(event_type, set()).add(callback)
    # 方法(事件类型,接收参数dict)-> {事件类型:(方法,方法,方法),其他类型:(1,2,3)}


def publish(event_type: EventType, data: dict[str, Any]):
    """
    底层通用发布原语：发布一个事件，同步调用该事件全部订阅回调。
    :param event_type: 事件类型枚举
    :param data: 已经model_dump完成的dict载荷；**禁止传入Pydantic实例，必须传dict**

    内置异常隔离：
    遍历订阅者时使用 list()做快照；避免回调内部订阅集合发生变化引发迭代异常；
    单个callback抛出异常，捕获、打印error日志；**不会终止循环，不会把异常抛给发布方**。

    业务代码禁止直接调用本函数；请调用上层业务封装：publish_section_ready / publish_host_discussion_message；
    上层封装会负责Pydantic模型序列化、日志打印、后续统一埋点扩展。
    """
    # 取当前订阅者快照，防止回调中增删订阅导致迭代器异常
    callback_list = list(_subscribers.get(event_type, set()))
    for callback in callback_list:
        try:
            callback(event_type, data)
        except Exception as exc:
            logger.error(f"事件订阅者执行失败 event_type={event_type}, err={exc}")


def unsubscribe(callback: EventCallback):
    """
    取消回调函数在**全部事件类型**上的订阅。
    :param callback: 需要取消的回调函数对象（必须和subscribe传入的是同一个函数引用）
    > 使用场景：服务停止、组件销毁的时候调用，防止内存泄漏、僵尸回调。
    > 注意：只根据函数对象匹配；lambda匿名函数无法取消订阅，不要用lambda做订阅回调。
    """
    for subscribers in _subscribers.values():
        subscribers.discard(callback)


# ====================== 业务层快捷发布封装函数（业务代码优先调用这些） ======================
# media/insight -> host
def publish_section_ready(
        state: Mapping[str, Any],
        section: Mapping[str, Any]
):
    """
    【上游Agent调用】构造并且发布 SECTION_READY 章节就绪事件。
    > 调用方：insight_agent / media_agent 的LangGraph节点，单章节生成完成后触发。
    :param state: Agent graph运行state，从中取出task_id、role角色
    :param section: graph内章节输出dict，包含section_key、body字段
    内部逻辑：
    1. 从graph state提取task_id、role；
    2. 组装SectionReadyEvent Pydantic模型；
    3. model_dump转为dict，调用底层publish；
    4. 打印业务日志，标记哪个Agent、哪个章节发布就绪。
    """
    role = state["role"]
    agent_name = role_display_name(role)
    event = SectionReadyEvent(
        task_id=state["task_id"],
        source=role,
        section_key=section["section_key"],
        body=section.get("body", "")
    )
    publish(EventType.SECTION_READY, event.model_dump())
    logger.info(f"【{agent_name}】 发布 [章节{event.section_key}] SECTION_READY 事件")

# host -> service -> fastapi -> 前端
def publish_host_discussion_message(event: HostDiscussionMessageEvent):
    """
    【Host模块调用】发布HOST_DISCUSSION_MESSAGE虚拟研讨会消息事件。
    > 调用方：host_agent/nodes.py 业务节点；构造完成HostDiscussionMessageEvent对象后调用。
    :param event: 已经填充完成的Pydantic HostDiscussionMessageEvent实例
    内部：模型dump为dict，调用底层publish；
    所有Host对外讨论消息统一走这个入口；后续可以在此处统一加埋点、事件持久化开关。
    """
    publish(EventType.HOST_DISCUSSION_MESSAGE, event.model_dump())

# ------------------- 业务层封装发布工具函数（业务代码统一调用入口） -------------------
def publish_role_progress(event: RoleProgressEvent):
    """发布角色研究进度事件【进度模块】
    入参：强类型RoleProgressEvent pydantic对象；内部model_dump转dict，调用底层publish；
    调用方：orchestrator._publish_progress，接收来自Agent graph各个node的ProgressUpdate回调。
    """
    publish(EventType.ROLE_PROGRESS, event.model_dump())


def publish_role_result(event: RoleResultEvent):
    """发布角色研究结果成功事件【进度模块】
    角色全部执行完成终态；入参RoleResultEvent pydantic模型。
    """
    publish(EventType.ROLE_RESULT, event.model_dump())


def publish_role_error(event: RoleErrorEvent):
    """发布角色研究错误异常事件【进度模块】
    角色顶层执行失败终态；入参RoleErrorEvent pydantic模型。
    """
