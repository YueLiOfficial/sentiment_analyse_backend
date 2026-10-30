"""固定四表检索 SQL。
db_sql_statement：在线业务关键词查询，带WHERE LIKE过滤；
vector_sql_statement：离线同步全量读取，不带WHERE条件；
两张SQL所有SELECT分支字段顺序、字段名必须完全对齐，保证UNION ALL正常执行。
安全规范：使用text()+命名参数params；%通配符放在参数值，禁止f-string拼接用户输入SQL，防止注入。
"""
from sqlalchemy import text

#  mysql -> 关键字 -> 相关的数据 
def db_sql_statement():
    """MySQL关键词检索：带LIKE过滤，用于线上db_repository"""
    return text("""
        SELECT * FROM (
            SELECT 'douyin' AS platform, 'douyin_aweme' AS source_table, id AS mysql_primary_key, title AS title_or_content, create_time AS published_at,
                liked_count AS eng_likes, comment_count AS eng_comments, share_count AS eng_shares, collected_count AS eng_collects, 0 AS eng_replies,
                liked_count + comment_count * 4 + share_count * 5 + collected_count * 2 AS hotness_score
            FROM douyin_aweme WHERE title LIKE :search_term
            UNION ALL
            SELECT 'douyin' AS platform, 'douyin_aweme_comment' AS source_table, id AS mysql_primary_key, content AS title_or_content, create_time AS published_at,
                like_count AS eng_likes, 0 AS eng_comments, 0 AS eng_shares, 0 AS eng_collects, sub_comment_count AS eng_replies,
                like_count + sub_comment_count * 3 AS hotness_score
            FROM douyin_aweme_comment WHERE content LIKE :search_term
            UNION ALL
            SELECT 'weibo' AS platform, 'weibo_note' AS source_table, id AS mysql_primary_key, content AS title_or_content, create_time AS published_at,
                liked_count AS eng_likes, comments_count AS eng_comments, shared_count AS eng_shares, 0 AS eng_collects, 0 AS eng_replies,
                liked_count + comments_count * 4 + shared_count * 5 AS hotness_score
            FROM weibo_note WHERE content LIKE :search_term
            UNION ALL
            SELECT 'weibo' AS platform, 'weibo_note_comment' AS source_table, id AS mysql_primary_key, content AS title_or_content, create_time AS published_at,
                comment_like_count AS eng_likes, 0 AS eng_comments, 0 AS eng_shares, 0 AS eng_collects, sub_comment_count AS eng_replies,
                comment_like_count + sub_comment_count * 3 AS hotness_score
            FROM weibo_note_comment WHERE content LIKE :search_term
        ) AS db_call_candidates
        ORDER BY hotness_score DESC, published_at DESC
        LIMIT :limit
    """)

# mysql -> milvus
def vector_sql_statement():
    """全量同步读取SQL：不带WHERE条件，给sync/reader.py使用
    仅离线同步脚本调用；在线业务绝对禁止调用该SQL，会全表扫描打爆数据库。
    """
    return text("""
        SELECT 'douyin' AS platform, 'douyin_aweme' AS source_table, id AS mysql_primary_key, title AS content, create_time AS published_at,
            liked_count AS eng_likes, comment_count AS eng_comments, share_count AS eng_shares, collected_count AS eng_collects, 0 AS eng_replies,
            liked_count + comment_count * 4 + share_count * 5 + collected_count * 2 AS hotness_score
        FROM douyin_aweme
        UNION ALL
        SELECT 'douyin' AS platform, 'douyin_aweme_comment' AS source_table, id AS mysql_primary_key, content AS content, create_time AS published_at,
            like_count AS eng_likes, 0 AS eng_comments, 0 AS eng_shares, 0 AS eng_collects, sub_comment_count AS eng_replies,
            like_count + sub_comment_count * 3 AS hotness_score
        FROM douyin_aweme_comment
        UNION ALL
        SELECT 'weibo' AS platform, 'weibo_note' AS source_table, id AS mysql_primary_key, content AS content, create_time AS published_at,
            liked_count AS eng_likes, comments_count AS eng_comments, shared_count AS eng_shares, 0 AS eng_collects, 0 AS eng_replies,
            liked_count + comments_count * 4 + shared_count * 5 AS hotness_score
        FROM weibo_note
        UNION ALL
        SELECT 'weibo' AS platform, 'weibo_note_comment' AS source_table, id AS mysql_primary_key, content AS content, create_time AS published_at,
            comment_like_count AS eng_likes, 0 AS eng_comments, 0 AS eng_shares, 0 AS eng_collects, sub_comment_count AS eng_replies,
            comment_like_count + sub_comment_count * 3 AS hotness_score
        FROM weibo_note_comment
    """)