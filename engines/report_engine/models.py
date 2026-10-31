"""
engines/report_engine/models.py
报告引擎领域模型
说明：定义报告生成相关全部dataclass与枚举；纯数据载体，无业务逻辑。
"""
from dataclasses import dataclass
from enum import Enum

from engines.contracts.judgement import SectionJudgement


@dataclass(slots=True)
class ReportInput:
    """综合报告生成所需的输入
    承载报告渲染全部上游输入数据：任务id、查询query、双agent原始报告、host结构化研判列表
    """
    generation_id: str
    task_id: str
    query: str
    insight_report: str    #私域的报告文本
    media_report: str      #公域的报告文本
    host_judgements: list[SectionJudgement]  # 研判结果

#        3个产物 <- ReportInput <-report -> 完整报告 -> ReportOutput -> 前端


@dataclass(slots=True)
class ReportOutput:
    """综合报告生成后的输出
    保存渲染产物：内存html文本、磁盘html路径/文件名、磁盘md路径/文件名
    """
    html_content: str  #预览
    report_filepath: str  # html的地址
    report_filename: str  # html文件名字
    markdown_filepath: str  # md的地址
    markdown_filename: str  # md的名字


# 检查报告是否可以生成  3个产物凑齐
class ReportGenerationStatus(str, Enum):
    """综合报告生成状态枚举
    RUNNING：报告生成任务运行中
    COMPLETED：报告生成执行成功完成
    ERROR：报告生成流程发生异常失败
    """
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


# 完整报告信息存储对象
@dataclass(slots=True)
class ReportGeneration:
    """单次综合报告生成过程记录
    保存一次报告生成全生命周期数据；内存存储，进程重启丢失。
    """
    report_input: ReportInput
    report_output: ReportOutput | None = None
    status: ReportGenerationStatus = ReportGenerationStatus.RUNNING
    error_message: str = ""

    @property
    def generation_id(self) -> str:
        """获取本次报告生成标识"""
        return self.report_input.generation_id

    @property
    def task_id(self) -> str:
        """获取关联的研究任务标识"""
        return self.report_input.task_id

    def complete(self, report_output: ReportOutput):
        """记录报告输出并标记生成完成：状态置COMPLETED，绑定ReportOutput产物"""
        self.report_output = report_output

        self.status = ReportGenerationStatus.COMPLETED

    def fail(self, message: str):
        """记录错误并标记生成失败：状态置ERROR，写入错误描述信息"""
        self.error_message = message
        self.status = ReportGenerationStatus.ERROR