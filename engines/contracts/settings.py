# engines/contracts/settings.py
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：当前文件向上回溯两层
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
# .env配置文件完整磁盘路径
ENV_FILE: str = str(PROJECT_ROOT / ".env")


# from dotenv import load_dotenv
#
# load_dotenv(override=True)  # 从当前的文件逐层向上查询 .env的配置,找到以后,加载!!  override=True 让我们的配置系统的环境变量!
#
# import os
# os.getenv("x")

# 方案1: 加载env配置文件  load_dotenv(override=True)   os.getenv("x")  一个一个读取
# 方案2: BaseSettings 批量读取  1. 类继承 BaseSettings 2. 声明对应key名称的属性 3. 加载的配置信息 model_config = SettingsConfigDict( 从哪个位置加载, 是否忽略大小写的配置
#       extra="forbid" # 不运行配置文件比参数类多,多了就启动报错! 强行校验  .env == 配置类


class Settings(BaseSettings):
    """全局配置：由.env文件加载服务、模型、数据库、检索全部参数"""

    # ############################################################################
    # 1. 服务与网络基础配置 (Server Base Config)
    # ############################################################################
    HOST: str = Field("0.0.0.0", description="监听地址")
    PORT: int = Field(5000, description="监听端口")

    # ############################################################################
    # 2. 关系型数据库配置 (Relational Database Config)
    # ############################################################################
    DB_DIALECT: str = Field("mysql", description="数据库类型:mysql 或 postgresql")
    DB_HOST: str = Field("localhost", description="数据库主机")
    DB_PORT: int = Field(3306, description="数据库端口")
    DB_USER: str = Field("root", description="数据库用户名")
    DB_PASSWORD: str = Field("", description="数据库密码")
    DB_NAME: str = Field("media_crawler", description="数据库名称")
    DB_CHARSET: str = Field("utf8mb4", description="字符集")

    # ############################################################################
    # 3. LLM 引擎与 Agent 模型配置 (LLM Model Engines)
    # ############################################################################
    # --- Insight 角色模型 ---
    INSIGHT_ENGINE_MODEL_PROVIDER: str = Field(
        "openai", description="Insight 角色厂商(langchain provider)"
    )
    INSIGHT_ENGINE_MODEL_NAME: str = Field("kimi‑k2.6", description="Insight 角色模型名")
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field(None, description="Insight 角色 API 密钥")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field(
        "https://api.moonshot.cn/v1", description="Insight 角色 BaseUrl"
    )

    # --- Media 角色模型 ---
    MEDIA_ENGINE_MODEL_PROVIDER: str = Field(
        "openai", description="Media 角色厂商(langchain provider)"
    )
    MEDIA_ENGINE_API_KEY: Optional[str] = Field(None, description="Media 角色 API 密钥")
    MEDIA_ENGINE_MODEL_NAME: str = Field("gemini‑2.5‑pro", description="Media 角色模型名")
    MEDIA_ENGINE_BASE_URL: Optional[str] = Field(
        "https://aihubmix.com/v1", description="Media 角色 BaseUrl"
    )

    # --- Report 报告引擎模型 ---
    REPORT_ENGINE_MODEL_PROVIDER: str = Field(
        "openai", description="报告引擎厂商(langchain provider)"
    )
    REPORT_ENGINE_MODEL_NAME: str = Field("gemini‑2.5‑pro", description="报告引擎模型名")
    REPORT_ENGINE_API_KEY: Optional[str] = Field(None, description="报告引擎 API 密钥")
    REPORT_ENGINE_BASE_URL: Optional[str] = Field(
        "https://aihubmix.com/v1", description="报告引擎 BaseUrl"
    )

    # --- Host Agent 主控模型 ---
    HOST_MODEL_PROVIDER: str = Field("openai", description="HostAgent 厂商(langchain provider)")
    HOST_MODEL_NAME: Optional[str] = Field(None, description="HostAgent 模型名")
    HOST_API_KEY: Optional[str] = Field(None, description="HostAgent API 密钥")
    HOST_BASE_URL: Optional[str] = Field(None, description="HostAgent BaseUrl")

    # ############################################################################
    # 4. Web 外部搜索服务配置 (Web Search Services)
    # ############################################################################
    SEARCH_SWITCH: Literal["TavilyAPI", "AnspireAPI"] = Field(
        "TavilyAPI", description="Web 搜索提供方"
    )
    TAVILY_API_KEY: Optional[str] = Field(None, description="Tavily API 密钥")
    TAVILY_BASE_URL: Optional[str] = Field(
        "https://api.tavily.com/search", description="TAVILY BaseUrl"
    )
    ANSPIRE_API_KEY: Optional[str] = Field(None, description="Anspire API 密钥")
    ANSPIRE_BASE_URL: Optional[str] = Field(
        "https://plugin.anspire.cn/api/ntsearch/search", description="Anspire BaseUrl"
    )

    # ############################################################################
    # 5. 系统运行时与日志目录配置 (Runtime & Directory Paths)
    # ############################################################################
    RUNTIME_DIR: str = Field(str(PROJECT_ROOT / "var"), description="运行时数据根目录")
    LOG_DIR: str = Field(str(PROJECT_ROOT / "var" / "logs"), description="角色日志目录")

    # ############################################################################
    # 6. 向量检索与 Milvus 配置 (Vector Search & Milvus Config)
    # ############################################################################
    INSIGHT_VECTOR_ENABLED: bool = Field(
        False, description="是否为 InsightAgent 启用 Milvus 向量检索"
    )
    MILVUS_URI: str = Field("http://localhost:19530", description="Milvus 服务器地址(URI)")
    MILVUS_DB_NAME: str = Field("default", description="Milvus 数据库名称")
    MILVUS_INSIGHT_COLLECTION: str = Field(
        "insight_evidence", description="Milvus 证据集合(Collection)名称"
    )
    INSIGHT_EMBEDDING_MODEL: str = Field(
        "BAAI/bge‑m3", description="Insight 检索所使用的 Embedding 模型名称/路径"
    )
    INSIGHT_EMBEDDING_DEVICE: Optional[str] = Field(
        None, description="Embedding 模型运行设备，例如 'cuda' 或 'cpu'"
    )
    INSIGHT_DENSE_DIM: int = Field(1024, description="BGE‑M3 稠密向量维度")
    INSIGHT_VECTOR_TOP_K: int = Field(30, description="Milvus 每个检索通道的召回数量(Top K)")
    INSIGHT_VECTOR_FILTER_DAYS: int = Field(
        365, description="Milvus 检索的时间窗口天数限制；小于等于0则禁用时间过滤"
    )

    INSIGHT_SEMANTIC_ROUTING_ENABLED: bool = Field(
        True, description="是否为 InsightAgent 启用章节语义路由"
    )
    INSIGHT_SEMANTIC_ROUTING_MODEL: Optional[str] = Field(
        None,
        description="用于章节语义路由的 SentenceTransformer 模型路径/名称；为None回退INSIGHT_EMBEDDING_MODEL；仅用于章节路由，不影响Milvus"
    )

    # ############################################################################
    # 7. 语义聚类配置 (Semantic Clustering Config)
    # ############################################################################
    INSIGHT_CLUSTERING_ENABLED: bool = Field(True, description="是否为 InsightAgent 启用语义聚类")
    INSIGHT_CLUSTER_MODEL: Optional[str] = Field(
        None, description="用于语义聚类的 SentenceTransformer 模型路径或名称"
    )
    INSIGHT_CLUSTER_MAX_RECORDS: int = Field(50, description="用于语义聚类的最大证据记录条数限制")
    INSIGHT_CLUSTER_MAX_CLUSTERS: int = Field(
        5, description="最大允许划分的语义聚类簇数，桶的数量"
    )
    INSIGHT_CLUSTER_MIN_CLUSTER_SIZE: int = Field(
        10, description="期望的最小语义聚类簇大小，桶的记录数量"
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, # 根据env_file=ENV_FILE读取磁盘项目根目录.env文本；
        env_prefix="",     # 环境变量前缀 环境变量前缀。例如设置env_prefix="APP_"，那么模型字段DB_HOST会去读环境变量APP_DB_HOST。
        case_sensitive=False, # 是否区分大小写
        extra="allow", #  运行配置文件比参数类多,多的key也会加入到类的属性中 .获取
        # extra="ignore"  # 允许配置文件比参数类多,多的key不会自动加到类的属性中 .取不到
        # extra="forbid" # 不运行配置文件比参数类多,多了就启动报错! 强行校验  .env == 配置类
    )



# 获取对象的!
# @lru_cache(): 缓存 缓存一次 下载获取就触发了!
# 变向的实现了单例模式
# @cache(maxsize=None) -> lru_cache(maxsize=128, typed=False)  lru 最近最少使用算法!!  缓存缓存 -> 对象 -> 存储 -> 容器 dict -> 一个函数缓存很多份,因为有不同的参数!
# maxsize=128 最多缓存 128份   参数不同会产生不同的缓存,缓存有大小限制! 所有才有淘汰算法! lru
# typed=False 缓存的时候不识别类型  2 "2" 走缓存!  True 识别类型  2 "2" 不触发缓存!
#  @lru_cache() 函数(number:int)     函数(1) 函数(2) 函数(1) 函数(2) 函数(3)  -> 3  -> 缓存考虑参数问题 不同的参数会独立缓存!
# _settings: Optional[Settings] = None

@lru_cache()
def get_settings() -> Settings:
    """获取带缓存的全局配置单例
    默认只会读取一次磁盘.env；后续全部复用内存对象
    """
    return Settings() # type: ignore


def reload_settings() -> Settings:
    """清理缓存以触发配置热更新
    只清空内存缓存，**不会修改磁盘.env文件**；
    调用之后再次get_settings()会重新从磁盘加载.env
    """
    get_settings.cache_clear()
    return get_settings()