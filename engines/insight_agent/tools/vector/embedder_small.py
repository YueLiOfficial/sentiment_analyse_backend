"""
embedder_small.py
语义路由专用 SentenceTransformer 向量化工具
仅用于 SectionEvidenceRoutingNode 章节语义路由；**完全不参与Milvus入库、检索**
输出已经L2归一化的numpy向量矩阵，可以直接np.dot计算余弦相似度
优先级：INSIGHT_SEMANTIC_ROUTING_MODEL > INSIGHT_EMBEDDING_MODEL
"""
from functools import lru_cache
from typing import List
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from engines.contracts.settings import get_settings


class RoutingSentenceEmbedder:
    """语义路由专用向量化器，全局单例懒加载"""

    @lru_cache(maxsize=None)
    def _get_model(self) -> SentenceTransformer:
        settings = get_settings()
        if settings.INSIGHT_SEMANTIC_ROUTING_MODEL:
            model_name = settings.INSIGHT_SEMANTIC_ROUTING_MODEL
        else:
            model_name = settings.INSIGHT_EMBEDDING_MODEL
        logger.info(f"[RoutingSentenceEmbedder] 加载路由模型: {model_name}")
        return SentenceTransformer(str(model_name))

    def encode(self, texts: List[str]) -> np.ndarray:
        """
        :param texts: 待编码文本列表
        :return: np.ndarray shape=(N,D) L2已经归一化，点积等价余弦相似度
        """
        model = self._get_model()
        emb = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return emb


# 全局单例，上层业务直接导入使用
routing_embedder = RoutingSentenceEmbedder()