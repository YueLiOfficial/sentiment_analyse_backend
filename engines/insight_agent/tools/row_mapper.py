"""
MySQL数据库行字典 → 全局契约 EvidenceDocument 公共映射工具
真实项目架构：取消中间仓储层DocumentRecord；数据库查询结果直接映射contracts层EvidenceDocument。
使用位置：
 1. DataBaseSearchRepository（在线MySQL关键词召回）
 2. DocumentRecordReader（离线同步脚本，全量读取MySQL）
"""
from dataclasses import fields
from datetime import datetime
from typing import Any

from engines.contracts.evidence import Engagement, EvidenceDocument


def map_db_row_to_evidence_document(row: dict[str, Any]) -> EvidenceDocument:
    """
    将MySQL UNION‑ALL查询返回的行字典，映射为全局契约 EvidenceDocument
    :param row: dict，数据库行字典，来自 result.mappings() 转换得到
    :return: EvidenceDocument 全局契约实体
    """
    # 反射组装互动指标字典，适配Engagement契约字段
    engage_dict = {
        field.name: float(row[f"eng_{field.name}"])
        for field in fields(Engagement)
    }

    return EvidenceDocument(
        platform=row["platform"],
        source_table=row["source_table"],
        mysql_primary_key=row["mysql_primary_key"],
        content=row.get("title_or_content") or row.get("content"), # type: ignore
        published_at=datetime.fromtimestamp(row["published_at"]),
        engagement=engage_dict,
        hotness_score=float(row["hotness_score"])
    )