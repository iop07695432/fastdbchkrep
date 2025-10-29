"""
SQL Server 报告生成模块

提供 SQL Server 数据库巡检报告的解析和生成功能
"""

from .parser import SQLServerHealthCheckParser
from .generator import MarkdownGenerator

__all__ = [
    "SQLServerHealthCheckParser",
    "MarkdownGenerator",
]

