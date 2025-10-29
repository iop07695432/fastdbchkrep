"""
配置类 - 从原markdown_generator.py迁移而来
"""
from pathlib import Path


class MarkdownConfig:
    """Markdown生成器配置类"""
    
    # 输出目录基础路径 - 更新为新的目录结构
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
    OUTDIR_PATH = PROJECT_ROOT / "data" / "outdir"
    JSON_PATH = PROJECT_ROOT / "data" / "json"
    
    # 模板常量配置
    TEMPLATE_PLACEHOLDERS = {
        "company_names": "鼎城科技/伟宏智能",
        "customer_unit": "客户单位",
        "customer_system": "客户应用系统名称"
    }
    
    # RMAN内容显示配置
    RMAN_DISPLAY_CONFIG = {
        "max_display_lines": 200,  # RMAN备份详情和备份集显示的最大行数
        "default_backup_details_message": "未找到 RMAN 备份明细信息",
        "default_backup_sets_message": "未找到RMAN备份集信息"
    }

    # 可编辑HTML相关配置（默认值仅作降级使用，可从外部覆写）
    EDITABLE_HTML_SUFFIX = ".editable.html"  # 可编辑HTML后缀
    SUGGESTIONS_JSON_SUFFIX = ".suggestions.json"  # 建议内容JSON后缀

    # 章节锚点（用于HTML注入可编辑控件时定位上下文）
    # 注意：这里使用的是标题片段，避免写死完整标题
    HTML_SECTION_ANCHORS = {
        "advice_table": "1.2.",  # 健康检查建议表格
        "conclusion_rman": "5.1.",  # RMAN章节
        "conclusion_dg": "5.2.",    # Data Guard章节
        "conclusion_adrci_alert": "5.3."  # ADRCI、ALERT章节
    }

    # 结论占位模式（用于识别“综合结论：【…】”文本，避免中文符号写死）
    CONCLUSION_TEXT_PREFIX = "综合结论："
    CONCLUSION_PLACEHOLDER_PATTERN = r"综合结论：\s*【[^】]*】"
