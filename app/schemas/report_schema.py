"""
app/schemas/report_schema.py
报告模块API接口Pydantic请求/响应Schema
全部HTTP接口入参出参模型，和业务domain模型做解耦。
"""
from pydantic import BaseModel, Field


class GenerateReportRequest(BaseModel):
    """报告生成请求体
    POST /api/report/generate 的请求json体
    """
    task_id: str = Field(..., min_length=1, description="关联的研究任务 ID")


class ReportStatusResponse(BaseModel):
    """报告生成状态响应体
    GET /api/report/status 返回；返回输入产物文件扫描结果
    prepared：仅代表磁盘文件全部存在，**不代表文件内容合法、可生成报告**
    """
    task_id: str
    prepared: bool = False
    found_files: list[str] = Field(default_factory=list)


class GenerateReportResponse(BaseModel):
    """报告生成过程创建响应体
    POST /api/report/generate 返回；返回生成记录id，前端用来轮询结果
    """
    generation_id: str
    task_id: str