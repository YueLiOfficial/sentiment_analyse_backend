from pathlib import Path

from engines.common.reports import get_output_dir
from engines.contracts.agent_rules import ROLE_KEY
from engines.orchestration.agent_orchestrator import ResearchAgentOrchestrator
from engines.common.research_tasks import research_task_manager, ResearchTask


class ResearchService:
    """
    研究任务服务
    职责：创建研究任务记录、调用编排器分发后台任务、对外提供任务查询
    不负责：初始化LLM、Agent协程创建、Agent业务逻辑、asyncio Task集合管理
    """

    def __init__(self) -> None:
        self._orchestrator = ResearchAgentOrchestrator()

    def research(self, query: str) -> str:
        """
        启动一次研究任务
        :param query: 用户研究主题
        :return: task_id，前端拿到task_id轮询查询任务状态与产物
        """

        task_info = research_task_manager.create_research_task(query)
        self._orchestrator.dispatch_tasks(task_id=task_info.task_id, query=query)

        return task_info.task_id


    def get_research_results(self, task_id: str) -> tuple:
        """对外查询业务任务记录"""
        task_info = research_task_manager.get_research_task(task_id)

        if not task_info:
            raise RuntimeError(f"任务 {task_id} 不存在")

        roles:list[ROLE_KEY] = ["insight", "media"]
        results:dict = {}
        for role in roles:
            output_dir = get_output_dir(task_id, role)
            output_path = Path(output_dir)
            output_file = output_path / "report.md"
            # 判断文件是否存在
            if output_file.exists():
                content = output_file.read_text(encoding="utf-8")
                results[role] = content

        return task_id, results