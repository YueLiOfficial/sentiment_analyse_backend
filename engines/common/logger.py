from contextlib import contextmanager
from pathlib import Path

from loguru import logger

from engines.contracts.agent_rules import ROLE_KEY
from engines.contracts.settings import get_settings


@contextmanager
def route_logs_by_role(role: ROLE_KEY):
    """根据Agent的角色分发日志"""
    log_handler_id = None
    settings = get_settings()
    LOG_DIR = Path(settings.LOG_DIR)

    with logger.contextualize(role=role):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler_id = logger.add(
                str(LOG_DIR / f"{role}.log"),
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss} | {level} | "
                    "[{extra[role]}] {name} - {message}"
                ),
                level="INFO",
                encoding="utf-8",
                rotation="1 MB",
                # 开启filter：只有带role并且等于当前role的记录才进这个文件
                filter=lambda record: record["extra"].get("role") == role,
            )
            yield
        finally:
            if log_handler_id is not None:
                logger.remove(log_handler_id)