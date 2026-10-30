"""Milvus 集合 schema 与索引参数的构建器。
仅在初始化集合、重建集合的离线脚本调用；在线检索业务不会调用。
"""
from dataclasses import fields
from typing import Any
from pymilvus import DataType
from engines.contracts.evidence import Engagement

MILVUS_OUTPUT_FIELDS: list[str] = [
    "doc_id",
    "platform",
    "source_table",
    "mysql_primary_key",
    "content",
    "published_at",
    *(metric_field.name for metric_field in fields(Engagement)),
    "hotness_score",
]


class CollectionSchemaBuilder:
    """构建 Milvus 集合的 schema 与索引参数。"""
    def __init__(self, milvus_client: Any, dense_vector_dimension: int) -> None:
        self._milvus_client = milvus_client
        self._dense_vector_dimension = dense_vector_dimension

    def build_collection_schema(self) -> Any:
        collection_schema = self._milvus_client.create_schema(
            auto_id=False, enable_dynamic_field=False,
        )
        # doc_id 作为主键，手动业务主键，不使用Milvus自增id；支持upsert增量更新
        collection_schema.add_field("doc_id", DataType.VARCHAR, is_primary=True, max_length=256)
        collection_schema.add_field("platform", DataType.VARCHAR, max_length=32)
        collection_schema.add_field("source_table", DataType.VARCHAR, max_length=64)
        collection_schema.add_field("mysql_primary_key", DataType.INT64)
        collection_schema.add_field("content", DataType.VARCHAR, max_length=65535)
        collection_schema.add_field("published_at", DataType.INT64)
        for metric_field in fields(Engagement):
            collection_schema.add_field(metric_field.name, DataType.FLOAT)
        collection_schema.add_field("hotness_score", DataType.FLOAT)
        collection_schema.add_field(
            "dense_vector",
            DataType.FLOAT_VECTOR,
            dim=self._dense_vector_dimension,
        )
        collection_schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
        return collection_schema

    def build_index_parameters(self) -> Any:
        index_parameters = self._milvus_client.prepare_index_params()
        index_parameters.add_index(
            field_name="dense_vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_parameters.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
        )
        return index_parameters