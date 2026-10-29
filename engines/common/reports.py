"""
报告与任务产物公共IO工具
职责：
1. get_output_dir：根据task_id、agent角色生成隔离的产物输出目录；读取全局settings.RUNTIME_DIR，禁止业务代码硬编码路径。
2. save_report：通用文本产物落盘工具；自动创建父目录、统一utf‑8编码；用于md报告、json证据、中间产物文件写入。

- 多任务、多角色天然目录隔离：{RUNTIME_DIR}/{task_id}/{role}
"""
from pathlib import Path
from engines.contracts.settings import get_settings
from engines.contracts.agent_rules import ROLE_KEY


def get_output_dir(task_id: str, role: ROLE_KEY) -> str:
    """
    根据task_id与agent角色，生成该角色专属产物输出根目录路径。
    - 根目录取自全局配置 settings.RUNTIME_DIR，不硬编码var路径；
    - 目录格式：`{RUNTIME_DIR}/{task_id}/{role}`
    - 同一个task_id下，insight/media各自独立子目录，产物隔离，不会互相覆盖。

    :param task_id: 本次研究任务唯一UUID标识
    :param role: 智能体角色key，insight / media / host / report
    :return: 字符串格式的完整产物根目录
    """
    runtime_base = Path(get_settings().RUNTIME_DIR)
    return str(runtime_base / f"{task_id}/{role}")


def save_report(
    output_dir: str | Path,
    filename: str,
    content: str,
) -> Path:
    """
    使用明确文件名将文本报告/产物写入指定目录；自动兜底创建父级目录。
    适用：Agent输出md报告、中间产物文本文件、证据json文本。

    流程：
    1. 拼接完整文件路径 output_dir / filename
    2. 若上级目录不存在，递归创建目录(parents=True, exist_ok=True)
    3. 使用utf‑8编码写入文本内容
    4. 返回写入完成的Path对象，上层可以用于日志打印、后续读取文件

    :param output_dir: 产物输出根目录（调用get_output_dir返回的目录）
    :param filename: 目标文件名，例如 report.md / evidences.json / section_01.md
    :param content: 需要写入的字符串文本内容
    :return: Path 已经写入完成的文件绝对路径对象
    """
    target_path = Path(output_dir) / filename
    # 保证目录一定存在，多任务并发不会因为目录未创建抛FileNotFound
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # utf‑8固定编码，避免Windows/linux编码乱码问题
    target_path.write_text(content, encoding="utf-8")
    return target_path