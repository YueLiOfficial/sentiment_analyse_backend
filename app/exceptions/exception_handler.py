# app/exceptions/exception_handlers.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger


def register_exception_handlers(app: FastAPI) -> None:
    """
    全局异常处理器注册入口
    将Python语义异常映射成标准HTTP JSON响应；
    业务层只需要raise对应异常，不需要到处写try‑except。
    """

    @app.exception_handler(LookupError) # 处理哪个异常
    async def handle_missing_resource(_request: Request, exc: LookupError) -> JSONResponse:
        # 函数必须是两个参数 参数1: 正常的请求对象  参数2: 异常对象
        # 打印日志
        """资源不存在异常，映射404"""
        return JSONResponse(
            status_code=404, # 200 http协议的响应状态
            content={"detail": str(exc)}  # content => json -> {code:101}
        )

    @app.exception_handler(ValueError)
    async def handle_invalid_input(_request: Request, exc: ValueError) -> JSONResponse:
        """参数、业务校验失败，映射400 Bad Request；配置更新白名单非法会抛出该异常"""
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)}
        )

    @app.exception_handler(RuntimeError)
    async def handle_state_conflict(_request: Request, exc: RuntimeError) -> JSONResponse:
        """业务状态冲突，例如任务已经完成不允许再次操作，映射409 Conflict"""
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)}
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        """兜底全局未知异常
        后端loguru记录完整堆栈，方便排错；
        对外返回简短提示，绝对不能把traceback堆栈返回前端。
        """
        logger.exception(f"服务端未捕获异常: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务内部异常：{str(exc)}"}
        )