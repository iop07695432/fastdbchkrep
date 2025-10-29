"""
工具函数 - 从原markdown_generator.py迁移而来
"""
import re
from typing import Dict, List, Optional


def find_file_by_name(file_list: List[Dict[str, str]], filename: str) -> Optional[Dict[str, str]]:
    """在文件列表中查找指定文件名的文件"""
    for file_info in file_list:
        if file_info["filename"] == filename:
            return file_info
    return None


def find_file_by_pattern(file_list: List[Dict[str, str]], pattern: str) -> Optional[Dict[str, str]]:
    """在文件列表中查找匹配正则表达式模式的文件"""
    for file_info in file_list:
        if re.match(pattern, file_info["filename"]):
            return file_info
    return None