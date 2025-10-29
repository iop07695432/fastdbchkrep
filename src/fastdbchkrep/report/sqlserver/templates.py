"""
SQL Server 报告 HTML/CSS 模板

存储 HTML 模板字符串和 CSS 样式常量
"""

# SQL Server 报告章节定义
REPORT_SECTIONS = [
    {"id": "sec-1", "title": "1. 实例基本信息"},
    {"id": "sec-2", "title": "2. 系统配置"},
    {"id": "sec-3", "title": "3. 数据库状态"},
    {"id": "sec-4", "title": "4. 备份检查"},
    {"id": "sec-5", "title": "5. 性能分析"},
    {"id": "sec-6", "title": "6. 安全检查"},
    {"id": "sec-7", "title": "7. 健康检查建议"},
]

# 提示框样式类型
ALERT_TYPES = {
    "danger": "危险",
    "warning": "警告",
    "info": "信息",
    "success": "成功",
}

# A4 页面样式
A4_PAGE_STYLE = """
@page {
    size: A4;
    margin: 2cm;
}

body {
    font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #333;
}
"""

# 表格样式
TABLE_STYLE = """
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 9pt;
}

table thead {
    background-color: #f0f0f0;
    font-weight: bold;
}

table th,
table td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}

table tbody tr:nth-child(even) {
    background-color: #f9f9f9;
}

table tbody tr:hover {
    background-color: #f5f5f5;
}
"""

# 提示框样式
ALERT_BOX_STYLE = """
.alert {
    padding: 12px 16px;
    margin: 1em 0;
    border-left: 4px solid;
    border-radius: 4px;
}

.alert-danger {
    background-color: #f8d7da;
    border-color: #dc3545;
    color: #721c24;
}

.alert-warning {
    background-color: #fff3cd;
    border-color: #ffc107;
    color: #856404;
}

.alert-info {
    background-color: #d1ecf1;
    border-color: #17a2b8;
    color: #0c5460;
}

.alert-success {
    background-color: #d4edda;
    border-color: #28a745;
    color: #155724;
}
"""

# 封面页样式
COVER_PAGE_STYLE = """
.cover-page {
    page-break-after: always;
    text-align: center;
    padding-top: 30%;
}

.cover-page h1 {
    font-size: 28pt;
    margin-bottom: 2em;
}

.cover-page .metadata-table {
    margin: 2em auto;
    width: 60%;
}
"""

# 目录页样式
TOC_PAGE_STYLE = """
.toc-page {
    page-break-after: always;
    padding: 2em;
}

.toc-page h2 {
    font-size: 20pt;
    margin-bottom: 1em;
    border-bottom: 2px solid #333;
    padding-bottom: 0.5em;
}

.toc-page ul {
    list-style: none;
    padding: 0;
}

.toc-page li {
    margin: 0.8em 0;
    font-size: 12pt;
}

.toc-page a {
    text-decoration: none;
    color: #0066cc;
}

.toc-page a:hover {
    text-decoration: underline;
}
"""

# 正文样式
CONTENT_STYLE = """
.content h1 {
    font-size: 18pt;
    margin-top: 2em;
    margin-bottom: 1em;
    border-bottom: 2px solid #333;
    padding-bottom: 0.5em;
    page-break-before: auto;
}

.content h2 {
    font-size: 14pt;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
    color: #0066cc;
}

.content h3 {
    font-size: 12pt;
    margin-top: 1em;
    margin-bottom: 0.5em;
    color: #333;
}

.content p {
    margin: 0.5em 0;
}

.content code {
    background-color: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: "Consolas", "Monaco", monospace;
}

.content pre {
    background-color: #f4f4f4;
    padding: 1em;
    border-radius: 4px;
    overflow-x: auto;
    font-family: "Consolas", "Monaco", monospace;
    font-size: 9pt;
    page-break-inside: avoid;
}
"""

# 建议表格可编辑样式
ADVICE_TABLE_STYLE = """
.advice-table {
    width: 100%;
    border-collapse: collapse;
}

.advice-table th,
.advice-table td {
    border: 1px solid #ddd;
    padding: 8px;
}

.advice-table th {
    background-color: #f0f0f0;
    font-weight: bold;
}

.advice-table td[contenteditable="true"] {
    background-color: #fffef0;
    cursor: text;
}

.advice-table td[contenteditable="true"]:focus {
    background-color: #fff;
    outline: 2px solid #0066cc;
}

.edit-controls {
    margin: 1em 0;
}

.edit-controls button {
    padding: 8px 16px;
    margin-right: 8px;
    background-color: #0066cc;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

.edit-controls button:hover {
    background-color: #0052a3;
}
"""

# 完整 CSS 样式
FULL_CSS_STYLE = (
    A4_PAGE_STYLE
    + TABLE_STYLE
    + ALERT_BOX_STYLE
    + COVER_PAGE_STYLE
    + TOC_PAGE_STYLE
    + CONTENT_STYLE
    + ADVICE_TABLE_STYLE
)


def get_alert_box_html(alert_type: str, content: str) -> str:
    """
    生成提示框 HTML
    
    Args:
        alert_type: 提示框类型 (danger/warning/info/success)
        content: 提示内容
        
    Returns:
        str: HTML 字符串
    """
    return f'<div class="alert alert-{alert_type}">{content}</div>'


def get_table_html(headers: list, rows: list, table_class: str = "") -> str:
    """
    生成表格 HTML
    
    Args:
        headers: 表头列表
        rows: 数据行列表
        table_class: 表格 CSS 类名
        
    Returns:
        str: HTML 字符串
    """
    class_attr = f' class="{table_class}"' if table_class else ""
    
    html = f"<table{class_attr}>\n"
    html += "  <thead>\n    <tr>\n"
    for header in headers:
        html += f"      <th>{header}</th>\n"
    html += "    </tr>\n  </thead>\n"
    
    html += "  <tbody>\n"
    for row in rows:
        html += "    <tr>\n"
        for cell in row:
            html += f"      <td>{cell}</td>\n"
        html += "    </tr>\n"
    html += "  </tbody>\n"
    html += "</table>\n"
    
    return html

