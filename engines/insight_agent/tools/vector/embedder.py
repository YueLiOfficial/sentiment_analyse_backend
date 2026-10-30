"""BGE-M3 向量编码器：负责 Dense 与 Sparse 向量的生成
业务约束：
1. 该编码器主要给【离线同步脚本】批量文档向量化；
2. 在线检索任务，**仅对用户输入query做少量向量化，禁止批量文档向量化**；
3. @cached_property保证模型全局只加载一次，避免重复加载大模型耗尽内存。
"""
from functools import cached_property
from typing import Iterable
from FlagEmbedding import BGEM3FlagModel
from engines.contracts.settings import get_settings


def _normalize_sparse_vector(sparse_vector: dict) -> dict[int, float]:
    """将BGE-M3输出的sparse字典key从str转int，适配Milvus SPARSE_FLOAT_VECTOR字段要求"""
    return {
        int(token_id): float(weight)
        for token_id, weight in sparse_vector.items()
    }


class VectorEmbedder:
    """封装 BGE‑M3 模型的向量编码服务。"""
    @cached_property # 没有参数 property  # @lru_cache -> 有参数
    def model(self) -> BGEM3FlagModel:
        settings = get_settings()
        # cpu
        device = settings.INSIGHT_EMBEDDING_DEVICE
        return BGEM3FlagModel(
            settings.INSIGHT_EMBEDDING_MODEL,
            use_fp16="cpu" not in device.lower(), # type: ignore
            devices=device,
        )

    def encode(
            self, texts: Iterable[str]
    ) -> list[tuple[list[float], dict[int, float]]]:
        """生成稠密与稀疏向量组合。
        :param texts: 待编码文本可迭代对象；支持生成器，降低批量内存峰值
        :return: list[(dense_vec, sparse_weight_dict)]
        """
        # [([稠密],{稀疏}),([],{})]
        text_items = list(texts)
        model_output = self.model.encode(
            text_items,
            return_dense=True,
            return_sparse=True
        )
        return [
            (dense.tolist(), _normalize_sparse_vector(sparse)) # type: ignore
            for dense, sparse in zip(
                model_output["dense_vecs"], model_output["lexical_weights"]
            )
        ]