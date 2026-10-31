"""
app/services/report/input_loader.py
报告输入加载器
职责：
1. get_report_input_status：快速扫描task磁盘输出目录，检查insight/media/host三份必需产物文件是否存在；
   只做文件存在性判断，不解析文件内部内容；用于生成报告前的前置快速校验。
2. load_report_input：深度读取三份磁盘产物；读取md正文、反序列化judgements.json为List[SectionJudgement]；
   关联原始任务query，组装ReportInput输入模型，交给报告引擎做渲染。

注意边界：
- 本模块只负责【读与校验输入】，不参与报告渲染、不参与生成任务调度；
- get_report_input_status ≠ 内容合法性校验；文件存在不代表内容合法；合法性在load_report_input做深度校验；
- 上游输出路径强约定：insight/report.md 、 media/report.md 、 host/judgements.json
"""
import json
from dataclasses import dataclass
from pathlib import Path

from engines.common.reports import get_output_dir
from engines.common.research_tasks import research_task_manager
from engines.contracts.judgement import SectionJudgement
from engines.report_engine.models import ReportInput


@dataclass(slots=True)
class ReportInputStatus:
    """
    综合报告输入文件的准备状态
    用于前置快速判断：磁盘上三份必需产物文件是否全部存在。
    注意：prepared=True 仅代表文件全部存在，**不代表文件内容合法、非空、json可解析**。
    """
    task_id: str
    found_files: list[str]
    input_file_paths: dict[str, str]

    @property
    def prepared(self) -> bool:
        """判断综合报告所需输入文件是否【全部磁盘存在】；不校验内容合法性"""
        return len(self.input_file_paths) == 3


class ReportInputLoader:
    """
    报告输入加载器
    两个对外方法：
    1. get_report_input_status：快速扫描磁盘，返回文件就绪状态，用于接口层前置拦截；
    2. load_report_input：深度读取+解析磁盘文件，组装ReportInput；会抛出IO/JSON/Pydantic校验异常。
    """

    def get_report_input_status(self, task_id: str) -> ReportInputStatus:
        """
        检查所有必需角色的报告文件是否已就绪。
        仅做文件存在性扫描，不读取、不解析文件内容。
        :param task_id: 舆情任务ID
        :return: ReportInputStatus，包含已发现文件清单、输入文件路径字典、prepared布尔标记
        """
        found_files = []
        input_file_paths = {}
        # 约定三份报告输入产物的磁盘相对路径
        expected_files = {
            "insight": Path(get_output_dir(task_id, "insight")) / "report.md",
            "media": Path(get_output_dir(task_id, "media")) / "report.md",
            "host": Path(get_output_dir(task_id, "host")) / "judgements.json"
        }
        for role_key, path in expected_files.items():
            if path.exists():
                found_files.append(f"{role_key}: {path.name}")
                input_file_paths[role_key] = str(path)
        return ReportInputStatus(
            task_id=task_id,
            found_files=found_files,
            input_file_paths=input_file_paths
        )

    def load_report_input(
            self,
            generation_id: str,
            task_id: str,
            file_paths: dict[str, str]
    ) -> ReportInput:
        """
        读取双Agent报告与Host研判，封装最终报告输入
        执行动作：
        1. 从task_manager获取原始research_task，拿到任务原始query；
        2. 读取insight/report.md、media/report.md原始markdown全文；
        3. 读取host/judgements.json，json.loads，再用SectionJudgement.model_validate做pydantic反序列化校验；
        4. 组装ReportInput对象返回，供ReportEngine渲染报告。

        :param generation_id: 本次报告生成记录唯一ID
        :param task_id: 舆情任务ID
        :param file_paths: 已经过get_report_input_status确认存在的三份文件路径字典
        :return: ReportInput 报告引擎输入对象
        :raises: 会抛出IOError、json.JSONDecodeError、pydantic.ValidationError；上层需要捕获异常，标记generation状态为ERROR
        """
        research_task = research_task_manager.get_research_task(task_id)
        raw_judgements = json.loads(Path(file_paths["host"]).read_text(encoding="utf-8"))
        return ReportInput(
            generation_id=generation_id,
            task_id=task_id,
            query=research_task.query,
            insight_report=Path(file_paths["insight"]).read_text(encoding="utf-8"),
            media_report=Path(file_paths["media"]).read_text(encoding="utf-8"),
            host_judgements=[SectionJudgement.model_validate(item) for item in raw_judgements]
        )