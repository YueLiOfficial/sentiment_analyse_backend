from __future__ import annotations
from dataclasses import dataclass
from typing import Any, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from pydantic import BaseModel

from engines.contracts.agent_rules import ROLE_KEY, ROLE_INFOS, RoleInfo
from engines.contracts.retrier import with_retry
from engines.contracts.settings import get_settings

# 泛型约束：结构化输出的返回对象必须继承自Pydantic BaseModel
T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True, frozen=True)
class LLMClient:
    """
    LLMClient：大模型客户端参数载体 + 调用工具
    frozen=True：实例属性不可修改，实例是只读对象，避免运行中参数被意外篡改
    slots=True：优化对象内存占用
    """
    model_name: str
    model_provider_name: str
    api_key: str
    base_url: str

    @classmethod
    def from_role(cls, role: ROLE_KEY) -> LLMClient:
        """
        类方法：根据业务角色role，构建对应角色的LLMClient实例
        流程：
        1. 根据role拿到RoleInfo角色元数据；
        2. 获取该角色对应的配置前缀；
        3. 读取全局settings配置，拼接前缀，取出模型名、服务商、api_key、base_url；
        4. 返回填充完成的只读LLMClient实例。

        :param role: 角色标识，支持 insight / media / host / report
        :return: LLMClient 只读客户端实例
        """

        role_info = ROLE_INFOS.get(role)
        if not role_info:
            raise ValueError(f"传入的role错误")

        prefix = role_info.confix_prefix

        settings = get_settings()

        return cls(
            model_name = getattr(settings, f"{prefix}_MODEL_NAME", ""),
            model_provider_name = getattr(settings, f"{prefix}_MODEL_PROVIDER", ""),
            api_key = getattr(settings, f"{prefix}_API_KEY", ""),
            base_url = getattr(settings, f"{prefix}_BASE_URL", "")
        )

    def _build_chat_model(self, is_structured: bool):
        """
        内部工具方法：构建LangChain ChatModel实例
        :param is_structured: True=后续要做结构化输出；False=普通文本输出
        :return: langchain BaseChatModel实例

        厂商兼容坑点：
        Kimi‑k2.6 /k2.5 默认开启思考模式，模型会先输出一段 reasoning_content（思考推理文本），再输出真正的回答内容。
        当你使用 response_format=json_schema 结构化输出时：
        模型会把思考过程混入输出，导致返回的 JSON 被破坏、解析失败；
        关闭 thinking.type:disabled，模型就不会输出推理片段，只输出干净 JSON，适配结构化解析。
        """
        model_name = self.model_name.lower()

        extra_body = {}
        if is_structured and ('kimi' in model_name or 'moonshot' in model_name):
            extra_body = {"thinking": {"type:": "disabled"}}

        return init_chat_model(
            model=self.model_name,
            model_provider=self.model_provider_name,
            api_key = self.api_key,
            base_url = self.base_url,
            extra_body = extra_body
        )


    def _build_input(self, system_prompt: str, user_prompt: str) -> list[BaseMessage]:
        """
        内部工具方法：统一组装LangChain消息列表
        固定格式：SystemMessage(系统提示) + HumanMessage(用户业务输入)
        :param system_prompt: 系统角色提示词
        :param user_prompt: 用户侧业务输入prompt
        :return: langchain消息对象列表，直接可以传给模型调用
        """

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

    @with_retry
    async def generate_text(self,
                            system_prompt: str,
                            user_prompt: str) -> str:
        """
        普通文本生成接口：流式astream调用，把分片chunk文本拼接成完整字符串返回
        适用场景：不需要严格结构化，自由文本输出（例如普通摘要、叙述类文本）
        :param system_prompt: 系统提示词
        :param user_prompt: 用户业务输入
        :return: 完整拼接后的模型输出文本字符串
        """

        # 获取llm客户端
        llm = self._build_chat_model(is_structured=False)
        # 获取消息列表
        messages = self._build_input(system_prompt=system_prompt, user_prompt=user_prompt)
        # 调用llm
        res = await llm.ainvoke(messages)

        return res.content # type: ignore

    @with_retry
    async def generate_object(self,
                              system_prompt: str,
                              user_prompt: str,
                              object_model: type[T]
                              ) -> T:
        """
        结构化输出接口：返回Pydantic校验后的结构化对象
        适用场景：需要强约束返回字段、类型；证据抽取、维度章节输出、Host研判结果等业务场景。

        三种结构化模式选型说明：
        1. method="json_schema"：模型服务端原生json_schema约束，约束最强；但不是所有模型厂商支持；
        2. method="function_calling"：伪装工具调用，兼容性最强，作为通用兜底方案；本项目当前采用该方案；
        3. method="json_mode"：仅保证返回合法JSON字符串，字段结构靠prompt诱导，约束最弱。

        :param system_prompt: 系统提示词
        :param user_prompt: 用户业务输入
        :param object_model: 需要输出的Pydantic模型类
        :return: 已经完成Pydantic校验的结构化模型实例
        :raises ValueError: 模型返回None时抛出业务异常，交给上层全局异常处理器处理
        """

        # 获取llm客户端
        llm = self._build_chat_model(is_structured=True)
        # 获取消息列表
        messages = self._build_input(system_prompt=system_prompt, user_prompt=user_prompt)
        # 定义结构化输出
        structed_llm = llm.with_structured_output(schema=object_model, method="function_calling")
        # 调用模型
        res = await structed_llm.ainvoke(messages)

        if not res:
            raise ValueError(f"调用模型失败，未成功返回结构化数据")
        
        return res # type: ignore




if __name__ == "__main__":
    import asyncio

# ====【测试Demo：仅本地调试使用，业务运行不调用】=========
# 自定义Pydantic返回模型，HOST agent场景：主机信息分析结果，仅用于本地验证LLMClient结构化能力
    class HostAnalyzeResult(BaseModel):
        host_name: str
        os_type: str
        cpu_core: int
        memory_gb: float
        risk_level: str  # low / medium / high
        suggest_actions: list[str]


    async def host_agent_llm():
        """本地调试测试用例：验证普通文本生成 + 结构化对象生成两条链路是否正常工作"""
        # 使用HOST角色构建LLMClient
        client = LLMClient.from_role(role="host")

        print(f"加载HOST角色模型: {client.model_name}")

        # 1. 测试普通文本生成
        print("\n===== 测试 generate_text 文本输出 =====")
        text_resp = await client.generate_text(
            system_prompt="你是主机运维助手，简短回答问题",
            user_prompt="简单描述Linux系统特点"
        )
        print(f"文本返回:\n{text_resp}")

        # 2. 测试结构化对象输出 generate_object
        print("\n===== 测试 generate_object 结构化输出 =====")
        obj_resp: HostAnalyzeResult = await client.generate_object(
            system_prompt="你是主机安全分析专家，按照给定结构输出主机分析结果",
            user_prompt="分析一台Linux服务器：8核CPU，16G内存，存在弱密码风险",
            object_model=HostAnalyzeResult
        )

        print("结构化对象返回：")
        print(f"主机名: {obj_resp.host_name}")
        print(f"系统: {obj_resp.os_type}")
        print(f"CPU核心: {obj_resp.cpu_core}")
        print(f"内存GB: {obj_resp.memory_gb}")
        print(f"风险等级: {obj_resp.risk_level}")
        print(f"建议操作: {obj_resp.suggest_actions}")
        # 可以直接转字典
        print(f"\n完整dict: {obj_resp.model_dump()}")

    asyncio.run(host_agent_llm())
# ====================== 测试代码 END ======================