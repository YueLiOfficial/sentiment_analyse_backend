"""
通用异步重试装饰器工具
适用：LLM、向量库、搜索API、数据库等外部瞬时故障重试
特性：最大重试次数、退避策略、可重试异常过滤、重试日志告警；
只处理瞬时外部异常；业务校验异常不重试；重试耗尽向上抛出异常，交给上层业务降级处理。
"""
import asyncio
from functools import wraps

from loguru import logger


class RetryConfig:
    """重试配置类，统一管理重试策略参数"""
    max_retries: int = 3  # 最大重试次数，总共会执行 max_retries+1 次调用(首次+重试)
    init_delay: float = 1.0  # 第一次重试等待初始秒数
    max_delay: float = 60.0  # 重试间隔最大上限，防止无限等待
    backoff_factor: float = 2.0  # 指数退避因子：间隔 = 初始延时 * 因子^重试次数

    def _get_delay(self, attempt: int) -> float:
        """
        根据当前重试次数计算指数退避延迟
        attempt：当前失败的第几次(从0开始)
        公式：init_delay * (backoff_factor ** attempt)，不超过max_delay上限
        """
        # attempt=0 第1次失败，延时=1*2^0=1s
        # attempt=1 第2次失败，延时=1*2^1=2s
        # attempt=2 第3次失败，延时=1*2^2=4s
        # attempt=3 第4次失败，延时=1*2^3=8s
        # 计算结果超过上限时，强制取max_delay
        return min(self.init_delay * (self.backoff_factor ** attempt), self.max_delay)

    def _is_no_retrable(self, exc: Exception) -> bool:
        """
        判断异常是否不允许重试
        返回True：不能重试，直接抛出异常
        返回False：可以重试
        规则：
        - 4xx 客户端错误(400~499)，除了429限流，全部不重试
        - 5xx服务端错误、网络异常、429限流 → 允许重试

        # 不能重试  400 -500 除了 429  || 500 - 599 可以从事  包含 429 模型的访问限制!
        """
        # 优先读取异常对象自带status_code属性
        status_code = getattr(exc, 'status_code', None)
        # 如果异常本身没有status_code，尝试从异常的response对象提取
        if status_code is None:
            resp = getattr(exc, 'response', None)
            status_code = getattr(resp, 'status_code', None)
        # 400~499区间，并且不是429限流 → 判定为不可重试异常
        return isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429

    def get_retry_delay(self,
                        fun_name: str,
                        attempt: int,
                        exc: Exception) -> float | None:
        """
        核心方法：判断是否需要重试，返回等待秒数；返回None代表不再重试
        :param fun_name: 函数名，用于日志打印
        :param attempt: 当前失败的尝试序号，从0开始
        :param exc: 捕获到的异常
        :return: 等待秒数 / None(不重试)
        """
        # 满足任一条件，终止重试：不可重试异常 或者 重试次数已经用尽
        if self._is_no_retrable(exc) or attempt >= self.max_retries:
            return None

        # 根据当前失败序号计算本次重试需要等待的时长
        delay = self._get_delay(attempt)

        # attempt从0开始，展示给人看的计数需要+1
        current_try = attempt + 1
        next_try = current_try + 1
        logger.warning(f"函数 {fun_name} 第 {current_try} 次尝试失败: {exc}")
        logger.info(f"将在 {delay:.1f} 秒后进行第 {next_try} 次尝试...")

        return delay


# 全局重试配置单例：所有@with_retry装饰函数共用一套配置
retry_config = RetryConfig()


def with_retry(func):
    """
    异步重试装饰器，只支持async协程函数
    使用示例：
        @with_retry
        async def llm_call():
            ...
    """
    # 校验：只允许装饰async协程函数，同步函数直接抛类型错误
    if not asyncio.iscoroutinefunction(func):
        raise TypeError(
            "重试装饰器只能装饰 async 函数,"
            f"得到的是同步函数 {func.__name__}"
        )

    @wraps(func)  # 保留原函数名称、docstring，方便日志和调试
    async def wrapper(*args, **kwargs):
        """包装器，循环执行重试逻辑"""
        # 循环次数 = max_retries +1：首次执行 + 最多max_retries次重试
        # 重试循环  range(1 -> start ,2 -> end,3 -> step )  range(1 -> start ,2 -> end )     range(2 -> end )
        #  [ max + 1 )
        for attempt in range(retry_config.max_retries + 1):
            try:
                # 执行目标异步函数，成功直接return，退出循环
                return await func(*args, **kwargs)
            except Exception as exc:
                # 判断是否继续重试，delay=None代表停止重试
                delay = retry_config.get_retry_delay(func.__name__, attempt, exc)
                if delay is None:
                    # 不再重试，向上抛出原始异常
                    raise exc
                # 异步sleep，不阻塞事件循环，等待后进入下一轮重试
                await asyncio.sleep(delay)
    # 返回包装后的wrapper函数
    return wrapper


# ------------------- 简单使用示例 -------------------
if __name__ == "__main__":
    @with_retry
    async def demo_test_llm():
        print("调用llm")
        raise Exception("模拟调用失败")

    asyncio.run(demo_test_llm())