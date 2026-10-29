"""统一任务管理器"""
import asyncio
import uuid
from dataclasses import dataclass
from typing import Coroutine

# 调研任务 -> 查询内容 -> query -> 任务 task_id 唯一 uuid
@dataclass(slots=True)  # dataclass _init_  || slots=True 加速 不允许随意扩展属性
class ResearchTask:
    """业务层研究任务记录，对外给前端/上层服务使用"""
    query: str
    task_id: str
    
# 对象 =ResearchTask()  对象.query = x 对象.task_id = x    对象.没有声明的属性 = 值  
# 底层 __slots__ 声明一个dict -> 对象的属性 -> dict 
# slots=True -> 提高性能 ->  __slots__ 去掉了这个函数 -> 数据不会额外字典存储 -> 对象的属性存储 -> 只能存储声明的属性
# frozen=True  不能修改属性 属性赋值 不能二次赋值


class ResearchTaskManager:
    """研究任务的任务管理器
    区分两层任务：
    1. research_tasks：业务任务记录，存储query、task_id
    2. async_tasks：底层asyncio.Task集合，管理事件循环后台协程生命周期
    """

    def __init__(self):
        """初始化研究任务与异步任务容器"""
        # key = task_id  | value 对象(task_id / query)
        self.research_tasks: dict[str, ResearchTask] = {}  # 后面判断 task_id 在这个字典
        # [协程 -> 运行 -> task] -> 方便批量关闭任务
        self.async_tasks: set[asyncio.Task] = set()

        
    # 开启一个任务 -> ResearchTask对象 -> 存储 -> dict -> 对象返回了 
    def create_research_task(self, query: str) -> ResearchTask:
        """创建并登记新的研究任务"""
        research_task = ResearchTask(query=query, task_id=str(uuid.uuid4().hex))
        self.research_tasks[research_task.task_id] = research_task
        return research_task
    
	# 获取
    def get_research_task(self, task_id: str) -> ResearchTask:
        """按任务标识获取研究任务"""
        return self.research_tasks[task_id]
	
    # 开启task->并且进行存储
    # Coroutine -> 协程 -> async 函数() 
    def submit_task(self, coroutine: Coroutine) -> asyncio.Task:
        """提交协程并跟踪其异步任务
        :param coroutine: 待执行协程对象
        :return: asyncio.Task 事件循环任务实例
        """
        # 执行的
        task = asyncio.create_task(coroutine)
        self.async_tasks.add(task)
        # done回调：任务结束自动把自身task实例从集合剔除，防止内存泄漏
        task.add_done_callback(self.async_tasks.discard)
        return task
    
	# 关闭所有task运行的函数 
    async def cancel_all_tasks(self):
        """取消并等待所有未完成的异步任务；服务关闭生命周期调用"""
        tasks = tuple(task for task in self.async_tasks if not task.done())
        for task in tasks:
            # task.cancel() 不是立刻杀死任务！只是发送一个取消标记。
            # 任务只有恢复到事件循环、执行到下一个 await 点的时候，才会抛出 CancelledError 真正终止。
            task.cancel()
        if tasks:
            # cancel 是发信号；await gather 是等待任务收到信号、跑完收尾逻辑
            # return_exceptions=True：不会因为CancelledError把 gather 本身炸掉，保证服务能继续走完关闭流程。
            await asyncio.gather(*tasks, return_exceptions=True)


# 全局单例，项目全局统一任务管理器实例
research_task_manager = ResearchTaskManager()



# 前端->fastapi->router->service-> 1. create_research_task 2.submit_task