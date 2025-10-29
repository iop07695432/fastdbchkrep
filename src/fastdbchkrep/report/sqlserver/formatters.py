"""
SQL Server 报告格式化工具

提供数值、文本、时间等格式化功能
"""

import re
from typing import Any, Optional, Union


def format_number_with_comma(value: Union[int, float, str]) -> str:
    """
    格式化数字，添加千分位逗号
    
    Args:
        value: 数值
        
    Returns:
        str: 格式化后的字符串
        
    Examples:
        >>> format_number_with_comma(1234567)
        '1,234,567'
        >>> format_number_with_comma(1234.56)
        '1,234.56'
    """
    if value is None or value == "":
        return ""
    
    try:
        # 转换为浮点数
        num = float(value)
        
        # 判断是否为整数
        if num.is_integer():
            return f"{int(num):,}"
        else:
            return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def format_bytes_to_mb(bytes_value: Union[int, float, str]) -> str:
    """
    将字节转换为 MB
    
    Args:
        bytes_value: 字节数
        
    Returns:
        str: MB 格式字符串
        
    Examples:
        >>> format_bytes_to_mb(1048576)
        '1.00 MB'
    """
    if bytes_value is None or bytes_value == "":
        return ""
    
    try:
        bytes_num = float(bytes_value)
        mb = bytes_num / (1024 * 1024)
        return f"{mb:.2f} MB"
    except (ValueError, TypeError):
        return str(bytes_value)


def format_bytes_to_gb(bytes_value: Union[int, float, str]) -> str:
    """
    将字节转换为 GB

    Args:
        bytes_value: 字节数

    Returns:
        str: GB 格式字符串

    Examples:
        >>> format_bytes_to_gb(1073741824)
        '1.00 GB'
    """
    if bytes_value is None or bytes_value == "":
        return ""

    try:
        bytes_num = float(bytes_value)
        gb = bytes_num / (1024 * 1024 * 1024)
        return f"{gb:.2f} GB"
    except (ValueError, TypeError):
        return str(bytes_value)


def format_bytes(bytes_value: Union[int, float, str]) -> str:
    """
    智能格式化字节数，自动选择合适的单位（KB/MB/GB/TB）

    Args:
        bytes_value: 字节数

    Returns:
        str: 格式化后的字符串

    Examples:
        >>> format_bytes(1024)
        '1.00 KB'
        >>> format_bytes(1048576)
        '1.00 MB'
        >>> format_bytes(1073741824)
        '1.00 GB'
    """
    if bytes_value is None or bytes_value == "":
        return ""

    try:
        bytes_num = float(bytes_value)

        # 自动选择合适的单位
        if bytes_num < 1024:
            return f"{bytes_num:.2f} B"
        elif bytes_num < 1024 * 1024:
            return f"{bytes_num / 1024:.2f} KB"
        elif bytes_num < 1024 * 1024 * 1024:
            return f"{bytes_num / (1024 * 1024):.2f} MB"
        elif bytes_num < 1024 * 1024 * 1024 * 1024:
            return f"{bytes_num / (1024 * 1024 * 1024):.2f} GB"
        else:
            return f"{bytes_num / (1024 * 1024 * 1024 * 1024):.2f} TB"
    except (ValueError, TypeError):
        return str(bytes_value)


def format_percentage(value: Union[int, float, str], decimals: int = 2) -> str:
    """
    格式化百分比

    Args:
        value: 数值（0-100 或 0-1，自动检测）
        decimals: 小数位数

    Returns:
        str: 百分比字符串

    Examples:
        >>> format_percentage(75.5)
        '75.50%'
        >>> format_percentage(0.755)
        '75.50%'
    """
    if value is None or value == "":
        return ""

    try:
        num = float(value)
        # 如果值在 0-1 之间（不含 0 和 1），自动乘以 100
        if 0 < num < 1:
            num = num * 100
        return f"{num:.{decimals}f}%"
    except (ValueError, TypeError):
        return str(value)


def format_duration_seconds(seconds: Union[int, float, str]) -> str:
    """
    将秒数格式化为 h/m/s 格式
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化后的时长字符串
        
    Examples:
        >>> format_duration_seconds(3661)
        '1h 1m 1s'
        >>> format_duration_seconds(90)
        '1m 30s'
    """
    if seconds is None or seconds == "":
        return ""
    
    try:
        total_seconds = int(float(seconds))
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)
    except (ValueError, TypeError):
        return str(seconds)


def clean_sql_text(sql_text: str) -> str:
    """
    清理 SQL 文本，移除多余空白和换行
    
    Args:
        sql_text: SQL 文本
        
    Returns:
        str: 清理后的 SQL 文本
    """
    if not sql_text:
        return ""
    
    # 移除多余的空白字符
    cleaned = re.sub(r'\s+', ' ', sql_text)
    
    # 去除首尾空白
    cleaned = cleaned.strip()
    
    return cleaned


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
        
    Returns:
        str: 截断后的文本
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_null_value(value: Any, default: str = "N/A") -> str:
    """
    格式化空值
    
    Args:
        value: 原始值
        default: 默认值
        
    Returns:
        str: 格式化后的值
    """
    if value is None or value == "" or str(value).upper() == "NULL":
        return default
    
    return str(value)


def normalize_affected_rows_marker(text: str) -> str:
    """
    标准化"受影响行数"标记
    
    将 "(N rows affected)" 和 "(N 行受影响)" 统一处理
    
    Args:
        text: 原始文本
        
    Returns:
        str: 标准化后的文本
    """
    # 移除英文版本
    text = re.sub(r'\(\d+\s+rows?\s+affected\)', '', text, flags=re.IGNORECASE)
    
    # 移除中文版本
    text = re.sub(r'\(\d+\s+行受影响\)', '', text)
    
    return text.strip()


def format_boolean(value: Any) -> str:
    """
    格式化布尔值为中文
    
    Args:
        value: 布尔值或字符串
        
    Returns:
        str: "是" 或 "否"
    """
    if isinstance(value, bool):
        return "是" if value else "否"
    
    if isinstance(value, str):
        value_lower = value.lower()
        if value_lower in ("true", "1", "yes", "enabled", "on"):
            return "是"
        elif value_lower in ("false", "0", "no", "disabled", "off"):
            return "否"
    
    if isinstance(value, (int, float)):
        return "是" if value != 0 else "否"
    
    return str(value)

