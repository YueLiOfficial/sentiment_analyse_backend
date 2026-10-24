from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.rest.config import config_router
from app.exceptions.exception_handler import register_exception_handlers

app = FastAPI()

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