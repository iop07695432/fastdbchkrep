"""
RAC 辅助解析模块

职责：
- 读取导入的 JSON，抽取 RAC 相关元信息（identifier、dbtype、各节点基本属性）。
- 提供最小依赖的轻量解析，供 rac_generator 使用。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


def load_rac_meta(json_file: Path) -> Tuple[str, str, List[Dict[str, Any]]]:
    """从 JSON 中加载 RAC 基本信息。

    Returns:
        (dbtype, identifier, metainfo_list)
    Raises:
        ValueError: 当 JSON 不是 RAC 模式或缺少关键字段时。
    """
    if not json_file.exists():
        raise ValueError(f"JSON文件不存在: {json_file}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    db_model = data.get('dbmodel', 'one')
    if db_model != 'rac':
        raise ValueError(f"JSON不是RAC模式 (dbmodel={db_model})")

    db_type = data.get('dbtype', 'oracle')
    identifier = data.get('identifier')
    metainfo = data.get('metainfo', [])

    if not identifier:
        raise ValueError("JSON缺少identifier，无法确定目标目录名")
    if not isinstance(metainfo, list) or not metainfo:
        raise ValueError("JSON缺少metainfo节点列表")

    # 基本字段检查，便于后续构建路径
    for idx, m in enumerate(metainfo, 1):
        if 'hostname' not in m or 'sid' not in m:
            logger.warning(f"metainfo[{idx}] 缺少 hostname/sid: {m.keys()}")

    return db_type, identifier, metainfo


__all__ = [
    'load_rac_meta',
]

