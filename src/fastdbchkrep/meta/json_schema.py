#!/usr/bin/env python3
"""
JSON Schema定义和验证模块
定义新版本JSON格式的Schema结构
"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime


class JsonSchemaValidator:
    """JSON Schema验证器"""
    
    # JSON格式版本号
    CURRENT_VERSION = "2.0"
    
    @staticmethod
    def get_json_schema() -> Dict[str, Any]:
        """
        获取新版本JSON Schema定义
        支持单机和RAC模式的统一格式
        """
        return {
            "type": "object",
            "required": ["version", "dbtype", "dbmodel", "identifier", "timestamp", "metainfo"],
            "properties": {
                "version": {
                    "type": "string",
                    "pattern": "^\\d+\\.\\d+$",
                    "description": "JSON格式版本号"
                },
                "dbtype": {
                    "type": "string",
                    "enum": ["oracle", "mysql", "postgresql", "sqlserver", "oracle_db_file"],
                    "description": "数据库类型"
                },
                "dbmodel": {
                    "type": "string", 
                    "enum": ["one", "rac"],
                    "description": "数据库模型(单机/RAC)"
                },
                "identifier": {
                    "type": "string",
                    "pattern": "^[a-zA-Z0-9_-]+$",
                    "description": "唯一标识符"
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "生成时间戳"
                },
                "metainfo": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["hostname", "sid", "dbname", "collect_date", "source_dir", "files"],
                        "properties": {
                            "hostname": {
                                "type": "string",
                                "description": "主机名"
                            },
                            "sid": {
                                "type": "string",
                                "description": "数据库实例ID"
                            },
                            "dbname": {
                                "type": "string",
                                "description": "数据库名称"
                            },
                            "collect_date": {
                                "type": "string",
                                "pattern": "^\\d{8}$",
                                "description": "采集日期(YYYYMMDD)"
                            },
                            "source_dir": {
                                "type": "string",
                                "description": "源数据目录路径"
                            },
                            "node_info": {
                                "type": "object",
                                "description": "RAC节点信息(可选)",
                                "properties": {
                                    "node_number": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 4
                                    },
                                    "node_name": {
                                        "type": "string"
                                    }
                                }
                            },
                            "files": {
                                "type": "object",
                                "description": "文件列表",
                                "additionalProperties": {
                                    "type": "object",
                                    "required": ["path", "exists", "size"],
                                    "properties": {
                                        "path": {
                                            "type": "string",
                                            "description": "文件完整路径"
                                        },
                                        "exists": {
                                            "type": "boolean",
                                            "description": "文件是否存在"
                                        },
                                        "size": {
                                            "type": "integer",
                                            "minimum": 0,
                                            "description": "文件大小(字节)"
                                        },
                                        "modified": {
                                            "type": "string",
                                            "format": "date-time",
                                            "description": "最后修改时间"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    @staticmethod
    def validate_json(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证JSON数据是否符合Schema
        
        Args:
            data: 待验证的JSON数据
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 检查必需字段
            required_fields = ["version", "dbtype", "dbmodel", "identifier", "timestamp", "metainfo"]
            for field in required_fields:
                if field not in data:
                    return False, f"缺少必需字段: {field}"
            
            # 验证版本号
            if not isinstance(data["version"], str) or not data["version"]:
                return False, "version必须是非空字符串"
            
            # 验证数据库类型
            # 接受新值 oracle，同时兼容历史值 oracle_db_file
            valid_dbtypes = ["oracle", "mysql", "postgresql", "sqlserver", "oracle_db_file"]
            if data["dbtype"] not in valid_dbtypes:
                return False, f"dbtype必须是{valid_dbtypes}之一"
            
            # 验证数据库模型
            valid_dbmodels = ["one", "rac"]
            if data["dbmodel"] not in valid_dbmodels:
                return False, f"dbmodel必须是{valid_dbmodels}之一"
            
            # 验证identifier格式
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', data["identifier"]):
                return False, "identifier只能包含字母、数字、下划线和连字符"
            
            # 验证metainfo数组
            if not isinstance(data["metainfo"], list) or len(data["metainfo"]) == 0:
                return False, "metainfo必须是非空数组"
            
            # 验证单机模式只有一个节点
            if data["dbmodel"] == "one" and len(data["metainfo"]) != 1:
                return False, "单机模式(one)的metainfo数组只能有一个元素"
            
            # 验证RAC模式有多个节点
            if data["dbmodel"] == "rac" and len(data["metainfo"]) < 2:
                return False, "RAC模式的metainfo数组至少需要2个节点"
            
            # 验证每个metainfo项
            for idx, meta in enumerate(data["metainfo"]):
                # 检查必需字段
                meta_required = ["hostname", "sid", "dbname", "collect_date", "source_dir", "files"]
                for field in meta_required:
                    if field not in meta:
                        return False, f"metainfo[{idx}]缺少必需字段: {field}"
                
                # 验证collect_date格式
                if not re.match(r'^\d{8}$', meta["collect_date"]):
                    return False, f"metainfo[{idx}].collect_date必须是YYYYMMDD格式"
                
                # 验证files对象
                if not isinstance(meta["files"], dict):
                    return False, f"metainfo[{idx}].files必须是对象类型"
                
                # RAC模式验证node_info
                if data["dbmodel"] == "rac":
                    if "node_info" not in meta:
                        return False, f"RAC模式下metainfo[{idx}]缺少node_info"
                    
                    node_info = meta["node_info"]
                    if "node_number" not in node_info or "node_name" not in node_info:
                        return False, f"metainfo[{idx}].node_info缺少必需字段"
                    
                    if not (1 <= node_info["node_number"] <= 4):
                        return False, f"metainfo[{idx}].node_info.node_number必须在1-4之间"
            
            return True, None
            
        except Exception as e:
            return False, f"验证过程出错: {str(e)}"
    
    @staticmethod
    def generate_filename(dbtype: str, dbmodel: str, identifier: str) -> str:
        """
        生成符合命名规范的JSON文件名
        
        Args:
            dbtype: 数据库类型
            dbmodel: 数据库模型
            identifier: 唯一标识符
            
        Returns:
            JSON文件名
        """
        return f"({dbtype}-{dbmodel})-{identifier}.json"
    
    @staticmethod
    def parse_filename(filename: str) -> Optional[Dict[str, str]]:
        """
        解析JSON文件名，提取参数信息
        
        Args:
            filename: JSON文件名
            
        Returns:
            包含dbtype、dbmodel、identifier的字典，解析失败返回None
        """
        import re
        # 匹配格式: (dbtype-dbmodel)-identifier.json
        pattern = r'^\(([a-z]+)-([a-z]+)\)-([a-zA-Z0-9_-]+)\.json$'
        match = re.match(pattern, filename)
        
        if match:
            return {
                "dbtype": match.group(1),
                "dbmodel": match.group(2),
                "identifier": match.group(3)
            }
        return None
    
    @staticmethod
    def create_empty_json(dbtype: str, dbmodel: str, identifier: str) -> Dict[str, Any]:
        """
        创建一个空的符合Schema的JSON结构
        
        Args:
            dbtype: 数据库类型
            dbmodel: 数据库模型
            identifier: 唯一标识符
            
        Returns:
            JSON数据结构
        """
        return {
            "version": JsonSchemaValidator.CURRENT_VERSION,
            "dbtype": dbtype,
            "dbmodel": dbmodel,
            "identifier": identifier,
            "timestamp": datetime.now().isoformat(),
            "metainfo": []
        }
