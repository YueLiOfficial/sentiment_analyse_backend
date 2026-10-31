"""
engines/report_engine/renderer.py
Markdown → HTML 渲染 + HTML 页面模板
职责：提供基础工具函数，完成markdown文本转html，以及html页面外壳模板组装；
仅文本转换，不参与报告业务内容生成。
依赖第三方库：mistune
"""
import html as html_lib

import mistune

# HTML页面内置CSS样式，控制报告网页预览样式
_HTML_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 2em; line-height: 1.8; color: #333; }
h1 { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 0.3em; }
h2 { color: #16213e; border-bottom: 1px solid #ddd; padding-bottom: 0.2em; margin-top: 1.5em; }
h3 { color: #0f3460; }
h4 { color: #0f3460; background: #f3f6fa; border-left: 4px solid #e94560; padding: 0.45em 0.75em; margin: 1.4em 0 0.7em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 0.6em 1em; text-align: left; }
th { background: #16213e; color: #fff; }
blockquote { border-left: 4px solid #e94560; padding-left: 1em; color: #555; margin-left: 0; }
code { background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; }
pre { background: #1a1a2e; color: #eee; padding: 1em; border-radius: 6px; overflow-x: auto; }
"""
# HTML文档头部固定模板
_HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>"""
# HTML中间片段：插入title + css + body开标签
_HTML_MID = """</title>
<style>
""" + _HTML_CSS + """
</style>
</head>
<body>
"""
# HTML文档尾部闭合标签
_HTML_TAIL = """
</body>
</html>"""


def render_markdown(text: str) -> str:
    """Markdown → HTML(mistune 硬依赖)
    将原始markdown文本转换为html片段（不含完整html外壳）
    """
    return mistune.html(text) # type: ignore


def render_html(body_html: str, title: str = "研究报告") -> str:
    """包裹 HTML body 为完整样式页面
    输入已经转换完成的html片段，拼接头部css、title、尾部闭合标签，返回完整可直接浏览器打开的html文档
    """
    return _HTML_HEAD + html_lib.escape(title) + _HTML_MID + body_html + _HTML_TAIL