from fastapi import APIRouter

from app.dependences import ResearchDepends
from app.schemas.research_schema import ResearchRequest, ResearchResponse, ResearchResultsResponse

research_router = APIRouter(prefix="/api/research", tags=["分析任务路由"])

@research_router.post(path="", response_model=ResearchResponse, description="分析任务开始任务接口")
async def research(req: ResearchRequest, service: ResearchDepends):
    query = req.query

    task_id = service.research(query)

    return ResearchResponse(
        task_id=task_id
    )

@research_router.get("/results", response_model=ResearchResultsResponse, description="获取分析任务结果接口")
def get_result(task_id: str, service: ResearchDepends):
    res_task_id, results = service.get_research_results(task_id)

    return ResearchResultsResponse(
        task_id=res_task_id,
        results=results
    )