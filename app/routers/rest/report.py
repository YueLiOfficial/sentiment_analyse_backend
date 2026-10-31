"""
app/api/report_router.py
报告模块FastAPI路由层
职责：
1. HTTP接口入参解析、参数校验；
2. 直接调用ReportService对外公开方法；业务逻辑全部下沉service，路由不实现业务；
3. 将service返回对象转换为pydantic响应模型；下载接口组装FileResponse；

注意：
- service层抛出的RuntimeError / LookupError / ValueError，需要项目全局异常处理器捕获，映射为400/404 HTTP业务错误；
- GET /result/{generation_id}直接返回内存HTML字符串；超大报告优先使用download下载接口，避免HTTP响应体过大。
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from app.dependences import ReportServiceDep
from app.schemas.report_schema import (
    GenerateReportRequest,
    GenerateReportResponse,
    ReportStatusResponse
)

report_router = APIRouter(prefix="/api/report", tags=["报告路由"])


@report_router.get("/status", response_model=ReportStatusResponse, description="获取报告状态")
def get_report_status_endpoint(
        service: ReportServiceDep,
        task_id: str
):
    """
    查询报告生成前置输入文件准备状态
    返回prepared布尔标记、已经扫描到的产物文件清单；
    prepared=True仅代表磁盘文件全部存在，不等于文件内容合法、可以生成报告。
    """
    input_status = service.get_report_status(task_id)
    return ReportStatusResponse(
        task_id=input_status.task_id,
        prepared=input_status.prepared,
        found_files=input_status.found_files
    )


@report_router.post("/generate", response_model=GenerateReportResponse, description="开始生成报告")
async def generate_report_endpoint(payload: GenerateReportRequest, service: ReportServiceDep):
    """
    异步触发生成报告任务
    说明：
    1. 接口不会阻塞等待报告渲染完成；提交后台协程后立刻返回generation_id；
    2. 前端拿到generation_id后，轮询 /result/{generation_id} 接口，判断是否生成完成；
    3. 前置校验：磁盘三份输入文件必须全部存在；同task不能有正在RUNNING的报告任务。
    """
    generation = service.request_report_generation(payload.task_id)
    return GenerateReportResponse(
        generation_id=generation.generation_id,
        task_id=generation.task_id
    )


@report_router.get("/result/{generation_id}", description="获取报告生成结果")
def get_generate_result_endpoint(generation_id: str, service: ReportServiceDep):
    """
    获取已完成报告 HTML
    直接返回内存中的 HTML 字符串，用于报告网页预览。
    异常场景：generation_id不存在 / 任务ERROR失败 / 任务还RUNNING未完成；service层抛异常，由全局异常处理器转换HTTP响应。
    """
    report_output = service.get_completed_report_output(generation_id)
    # 直接返回内存中的 HTML 字符串，用于报告预览
    return Response(content=report_output.html_content, media_type="text/html")


@report_router.get("/download/{generation_id}/{file_type}", description="下载HTML/MD格式报告")
def download_report_endpoint(
        generation_id: str,
        file_type: str,
        service: ReportServiceDep
):
    """
    下载 HTML 或 MD 报告文件
    file_type 枚举：html / md；
    返回FileResponse，浏览器触发文件下载；读取磁盘真实报告文件。
    """
    file_info = service.get_download_file(generation_id, file_type)
    # 读取磁盘文件并设置附件响应头，用于文件下载
    return FileResponse(
        file_info["file_path"],
        media_type=file_info["media_type"],
        filename=file_info["file_name"]   # 下载必须要  不添加 filename 返回的数据类型 html文件 -> 浏览器会自动打开
                                          # filename 下载头 -> 响应头 content_disposition:attachment;filename=文件名
    )