"""
app/services/report/report_service.py
综合报告服务：协调输入加载、任务状态跟踪与报告引擎生成报告

职责边界：
1. 维护内存全部报告生成任务记录；做同一个task并发生成的互斥保护；
2. 对外提供接口层可调用的能力：查询输入就绪状态、提交报告生成任务、获取已完成报告输出、获取下载文件元数据；
3. 将完整报告生成逻辑交给research_task_manager后台协程执行，HTTP请求不阻塞；
4. 后台协程内部：调用input_loader深度加载输入 → ReportEngine生成报告；成功/失败都回写generation记录状态；
5. 本层不直接处理HTTP请求；路由层调用本服务的公开方法。

重要限制：
- _report_generations 为内存存储；服务进程重启，全部generation记录丢失；
- 并发互斥保护仅单进程内存生效；多进程部署需要引入分布式锁；
- 当前版本仅支持API手动触发报告生成；Host研判完成自动触发属于扩展点，不在本文件实现。
"""
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from app.services.report.input_loader import ReportInputLoader, ReportInputStatus
from engines.report_engine.engine import ReportEngine
from engines.report_engine.models import (
    ReportGeneration,
    ReportGenerationStatus,
    ReportOutput
)
from engines.common.research_tasks import research_task_manager


class ReportService:
    """综合报告服务：协调输入加载、任务状态跟踪与报告引擎生成报告"""

    def __init__(self):
        """初始化最终综合报告服务以及组件"""
        # 内存保存全部报告生成记录；key = generation_id；进程重启全部记录丢失
        self._report_generations: dict[str, ReportGeneration] = {}
        # 报告输入加载器：磁盘文件扫描、读取、反序列化
        self._input_loader = ReportInputLoader()
        # 底层报告渲染引擎：负责ReportInput → ReportOutput（md/html文本）
        self._report_engine = ReportEngine()

    def get_report_status(self, task_id: str) -> ReportInputStatus:
        """
        获取最终报告输入文件的准备状态
        代理调用input_loader快速扫描磁盘三份产物文件是否全部存在；
        注意：返回prepared=True仅代表文件磁盘存在，不代表文件内容合法。
        :param task_id: 舆情任务ID
        :return: ReportInputStatus
        """
        return self._input_loader.get_report_input_status(task_id)

    def request_report_generation(self, task_id: str) -> ReportGeneration:
        """
        创建并异步启动报告生成过程
        业务步骤：
        1. 快速校验输入文件磁盘是否全部就绪；prepared=False直接抛异常，不提交后台任务；
        2. _prepare_report_generation：做task并发互斥；创建generation记录；加载输入文件路径；
        3. 将完整生成逻辑提交给research_task_manager后台协程；HTTP接口立刻返回generation_id，不阻塞。

        :param task_id: 舆情任务ID
        :return: ReportGeneration 报告生成记录实例（此时状态为RUNNING，后台还未执行完毕）
        :raises RuntimeError：输入未就绪 / 当前task已有RUNNING生成任务，禁止重复提交
        """
        # 1. 获取报告状态，快速校验磁盘三份输入文件是否全部存在
        input_status = self._input_loader.get_report_input_status(task_id)
        if not input_status.prepared:
            raise RuntimeError("报告输入尚未就绪")
        generation = self._prepare_report_generation(
            task_id,
            input_status.input_file_paths
        )
        # 2. 丢到后台事件循环中异步执行生成逻辑(纳入统一任务登记)
        research_task_manager.submit_task(self._run_report_generation(generation))
        # 3. 立即返回生成记录供前端轮询
        return generation

    def get_download_file(self, generation_id: str, file_type: str) -> dict[str, Any]:
        """
        获取已生成报告文件的下载路径、文件名和媒体类型
        业务步骤：
        1. 校验generation_id对应报告必须COMPLETED完成，拿到ReportOutput；
        2. 根据file_type选择html/md对应的磁盘路径、文件名、http media_type；
        3. 检查磁盘物理文件真实存在；
        4. 返回字典，交给report_router组装FileResponse下载响应。

        :param generation_id: 报告生成记录ID
        :param file_type: 下载文件类型，枚举："html" / "md"
        :return: dict: file_path、file_name、media_type
        :raises LookupError / ValueError / RuntimeError：记录不存在、类型不支持、报告未完成、磁盘文件丢失
        """
        # 1. 获取已完成的报告输出
        report_output = self.get_completed_report_output(generation_id)
        # 2. 根据文件类型匹配对应的路径和媒体类型
        if file_type == "html":
            file_path = report_output.report_filepath
            file_name = report_output.report_filename
            media_type = "text/html"
        elif file_type == "md":
            file_path = report_output.markdown_filepath
            file_name = report_output.markdown_filename
            media_type = "text/markdown"
        else:
            raise ValueError("不支持的报告文件类型")
        # 3. 确认落盘文件仍然存在
        if not file_path or not Path(file_path).exists():
            raise LookupError("报告文件不存在或已被清理")
        # 4. 返回文件下载所需的元数据
        return {"file_path": file_path, "file_name": file_name, "media_type": media_type}

    def get_completed_report_output(self, generation_id: str) -> ReportOutput:
        """
        获取已完成报告生成过程的输出
        前置校验：
        - generation_id必须存在；
        - generation状态不能是ERROR；
        - generation状态必须是COMPLETED；
        任意条件不满足抛出业务异常。

        :param generation_id:报告生成记录ID
        :return: ReportOutput 报告渲染完成后的输出对象（内存html/md字符串 + 磁盘文件路径）
        """
        generation = self._report_generations.get(generation_id)
        if generation is None:
            raise LookupError("报告生成记录不存在")
        if generation.status == ReportGenerationStatus.ERROR:
            raise RuntimeError(f"报告生成失败: {generation.error_message}")
        if generation.status != ReportGenerationStatus.COMPLETED:
            raise RuntimeError("报告尚未完成")
        return generation.report_output # type: ignore

    def _prepare_report_generation(
            self,
            task_id: str,
            input_file_paths: dict[str, str]
    ) -> ReportGeneration:
        """
        创建报告生成记录，并阻止同一研究任务重复生成
        业务步骤：
        1. 遍历内存全部generation记录：判断该task是否已经存在一条RUNNING状态的生成任务；存在则抛异常，防止并发重复生成；
        2. 生成全局唯一generation_id；
        3. 调用input_loader.load_report_input：深度读取+解析全部输入文件，构造ReportInput；
        4. 实例化ReportGeneration对象，存入内存字典`_report_generations`；
        5. 返回新创建的generation记录（状态RUNNING）。

        :param task_id:舆情任务ID
        :param input_file_paths:已经确认全部存在的三份输入文件路径字典
        :return: ReportGeneration 新建的运行中报告生成记录
        :raises RuntimeError：当前task已有RUNNING报告生成任务，拒绝重复提交
        """
        # 1. 检查是否存在正在运行的生成任务，防止重复提交
        if any(
                generation.task_id == task_id
                and generation.status == ReportGenerationStatus.RUNNING
                for generation in self._report_generations.values()
        ):
            raise RuntimeError("当前研究任务已有报告正在生成")
        # 2. 生成唯一的记录 ID 并加载报告输入数据
        generation_id = f"generation_{uuid4().hex}"
        report_input = self._input_loader.load_report_input(
            generation_id=generation_id,
            task_id=task_id,
            file_paths=input_file_paths
        )
        # 3. 创建报告生成记录并存入_report_generations容器
        generation = ReportGeneration(report_input=report_input)
        # report_agent
        self._report_generations[generation.generation_id] = generation
        # 4. 返回创建好的生成记录实例
        return generation

    async def _run_report_generation(self, generation: ReportGeneration):
        """
        在后台异步执行报告生成的完整工作流
        注意：本协程交给research_task_manager托管；**内部全部异常捕获，不会向外抛出**；
        成功：调用generation.complete(report_output)，状态置COMPLETED，绑定ReportOutput；
        失败：捕获全部Exception，写error日志，调用generation.fail(str(e))，状态置ERROR，保存异常信息；

        :param generation: RUNNING状态的报告生成记录实例
        """
        try:
            # 1. 调用综合报告引擎生成最终报告
            report_output = await self._report_engine.generate_report(
                generation.report_input
            )
            # 2. 将生成结果绑定到本次报告生成过程并标记完成
            generation.complete(report_output)
        except Exception as e:
            # 3. 记录日志并更新任务状态为失败
            logger.exception(f"报告生成失败: {str(e)}")
            generation.fail(str(e))