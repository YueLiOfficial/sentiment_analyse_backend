SECTION_SUMMARY_USER_PROMPT = """
【写作任务】
请按照当前章节职责,基于下方实际可见的证据材料撰写本章正文。

[章节职责]
{section_context}

[实际检索请求]
{retrieval_text}

[证据材料]
以下材料仅是本次提供的检索样本,不代表事实已经核实,也不代表全部信息范围。
只能引用下方实际可见的证据材料。

{evidence_text}
"""
