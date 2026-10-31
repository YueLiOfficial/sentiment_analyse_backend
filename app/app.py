from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.rest.config import config_router
from app.routers.rest.research import research_router
from app.routers.rest.host import host_router
from app.routers.rest.report import report_router
from app.routers.sse.research_progress import search_progress_router
from app.exceptions.exception_handler import register_exception_handlers
from app.dependences import get_lifecycle_manager

async def lifespan(app: FastAPI):
    """应用启停时注册与关闭生命周期管理器。"""
    lifecycle_manager = get_lifecycle_manager()
    try:
        # 初始化方法
        lifecycle_manager.register()

        # 之上 都是初始化
        yield # 调用fastapi
        # 之下 都是资源释放
    finally:
        # 销毁
        await lifecycle_manager.shutdown()

app = FastAPI(lifespan=lifespan) # type: ignore

# 跨域配置  跨域 =  客户端(独立部署) - 服务端接口(独立部署) 非同源(协议 + 主机 + 端口) 被拒绝访问了!!
# 解决方案1: 前端解决 配置代理
# 解决方案2: 后端解决 在响应头添加特殊的头 运行访问!  app.add_middleware(
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局异常处理器
register_exception_handlers(app)

app.include_router(config_router)
app.include_router(research_router)
app.include_router(host_router)
app.include_router(report_router)
app.include_router(search_progress_router)