"""
app/services/lifecycle_service.py
应用生命周期管理器:统一启动与关闭后台服务组件及引擎共享资源

职责：
1. 编排全部后台组件**启动注册顺序**；这是SSE事件总线绑定真正被调用的入口；
2. 编排shutdown关闭顺序，反向执行注册；依次解绑回调、释放连接、取消全部后台任务。


依赖注入说明：
__init__不内部new对象；HostService、ResearchProgressStream实例由外部main.py(lifespan)实例化之后传入；
目的：单元测试的时候，可以传入mock实例，不需要真实启动整套服务。
"""
from app.services.host.host_service import HostService
# from app.services.sse.research_progress_stream import ResearchProgressStream
from engines.common.research_tasks import research_task_manager


class AppLifecycleManager:
    """应用生命周期管理器:统一启动与关闭后台服务组件及引擎共享资源"""
    def __init__(self,
                 host_service: HostService,
                #  research_progress_stream: ResearchProgressStream
        ):
        """初始化生命周期管理器并注入依赖组件
        :param host_service: host主持人服务实例
        :param research_progress_stream: SSE进度流服务实例；main.py lifespan中实例化之后传入；
        """
        self.host_service = host_service
        # self.research_progress_stream = research_progress_stream

    def register(self):
        """统一注册并启动所有关联的后台服务组件【SSE事件总线绑定的真正调用入口！】
        顺序不可修改：
        1.优先调用research_progress_stream.register_progress_update()完成事件总线回调绑定；
        2.之后才启动Host讨论buffer、HostListener；之后业务Agent任务提交。
        """
        # 1. 启动前端实时广播服务：内部调用subscribe，完成事件总线回调绑定
        # self.research_progress_stream.register_progress_update()
        # 2. 启动研判讨论缓冲服务：订阅HOST_DISCUSSION_MESSAGE事件
        self.host_service.register_discussion_buffer()
        # 3. 启动 Host 章节研判监听器：开始消费SECTION_READY事件，Host业务正式开始
        self.host_service.register_host_listener()

    async def shutdown(self):
        """统一注销并停止所有关联的后台服务组件,释放持有的资源
        关闭顺序：和register启动顺序反向；先关闭广播输出，再关闭业务消费，最后取消全部后台任务。
        """
        # 1. 停止广播服务，断开事件订阅：unsubscribe解绑总线回调；清空全部浏览器SSE队列
        # self.research_progress_stream.stop_progress_update()
        # 2. 停止讨论缓冲服务，释放监听
        self.host_service.stop_discussion_buffer()
        # 3. 停止 Host 章节监听 worker，不再消费SECTION_READY事件
        self.host_service.stop_host_listener()
        # 4. 取消仍在执行的研究/报告后台任务
        await research_task_manager.cancel_all_tasks()