#!/usr/bin/env python3
"""
FastDBCheckRep 数据库元数据解析器
重构版本：支持参数化输入输出路径，新的JSON格式
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# 导入JSON Schema验证器
try:
    from fastdbchkrep.meta.json_schema import JsonSchemaValidator
except ImportError:
    # 如果导入失败，提供回退方案
    class JsonSchemaValidator:
        CURRENT_VERSION = "2.0"
        
        @staticmethod
        def create_empty_json(dbtype, dbmodel, identifier):
            return {
                "version": "2.0",
                "dbtype": dbtype,
                "dbmodel": dbmodel,
                "identifier": identifier,
                "timestamp": datetime.now().isoformat(),
                "metainfo": []
            }
        
        @staticmethod
        def generate_filename(dbtype, dbmodel, identifier):
            return f"({dbtype}-{dbmodel})-{identifier}.json"
        
        @staticmethod
        def validate_json(data):
            return True, None

# 导入RAC解析器
try:
    from fastdbchkrep.meta.rac_parser import RacParser, RacClusterInfo
except ImportError:
    # 如果导入失败，提供占位符
    RacParser = None
    RacClusterInfo = None


class Config:
    """配置类 - 支持动态配置"""
    
    # 基础路径 - 动态配置，不再硬编码
    BASE_PATH = Path(__file__).parent.parent.parent.parent
    DATA_PATH = BASE_PATH / "data"
    
    # 默认路径 - 仅作为降级使用
    DEFAULT_OUTPUT_DIR = DATA_PATH / "outdir"
    DEFAULT_JSON_DIR = DATA_PATH / "json"
    DEFAULT_LOG_DIR = DATA_PATH / "log"
    
    # 文件状态JSON文件名 - 固定命名规范
    FILE_STATUS_JSON = "file_status.json"
    
    # 支持的数据库类型配置
    SUPPORTED_DATABASES = {
        # 新键 oracle；保留 oracle_db_file 兼容历史
        'oracle': {
            'required_files': [
                'file_status.json',
                '01_system_info.txt',  # 系统信息文件
                '02_hardware_info.json'  # 硬件信息文件
            ]
        },
        'oracle_db_file': {
            'required_files': [
                'file_status.json',
                '01_system_info.txt',
                '02_hardware_info.json'
            ]
        },
        'mysql': {
            'required_files': [
                'file_status.json',
                'mysql_status.json'
            ]
        },
        'postgresql': {
            'required_files': [
                'file_status.json',
                'pg_status.json'
            ]
        },
        'sqlserver': {
            'required_files': [
                'file_status.json',
                'sqlserver_status.json'
            ]
        }
    }
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    
    @classmethod
    def get_log_file(cls, log_dir: Optional[Path] = None) -> Path:
        """获取日志文件路径"""
        if log_dir:
            return log_dir / "meta_parser.log"
        return cls.DEFAULT_LOG_DIR / "meta_parser.log"


class DatabaseMetaParser:
    """数据库元数据解析器 - 参数化版本"""
    
    def __init__(self, 
                 db_type: str = 'oracle',
                 db_model: str = 'one',
                 import_dirs: Optional[List[str]] = None,
                 json_out_dir: Optional[str] = None,
                 identifier: Optional[str] = None,
                 log_dir: Optional[str] = None):
        """
        初始化解析器
        
        Args:
            db_type: 数据库类型 ('oracle', 'mysql', 'postgresql', 'sqlserver')
            db_model: 数据库模型 ('one' for single, 'rac' for cluster)
            import_dirs: 输入目录列表 (单机模式1个，RAC模式2-4个)
            json_out_dir: JSON输出目录
            identifier: 自定义标识符 (可选，为空则自动生成)
            log_dir: 日志目录 (可选)
        """
        # 参数验证
        if db_type not in Config.SUPPORTED_DATABASES:
            raise ValueError(f"不支持的数据库类型: {db_type}")
        
        if db_model not in ['one', 'rac']:
            raise ValueError(f"不支持的数据库模型: {db_model}")
        
        # 验证输入目录数量
        if not import_dirs:
            raise ValueError("必须提供至少一个输入目录")
        
        if db_model == 'one' and len(import_dirs) != 1:
            raise ValueError(f"单机模式需要且仅需要1个输入目录，实际提供了{len(import_dirs)}个")
        
        if db_model == 'rac' and not (2 <= len(import_dirs) <= 4):
            raise ValueError(f"RAC模式需要2-4个输入目录，实际提供了{len(import_dirs)}个")
        
        # 初始化属性
        self.db_type = db_type
        self.db_model = db_model
        self.db_config = Config.SUPPORTED_DATABASES[db_type]
        self.import_dirs = [Path(d) for d in import_dirs]
        self.json_out_dir = Path(json_out_dir) if json_out_dir else Config.DEFAULT_JSON_DIR
        self.identifier = identifier
        self.log_dir = Path(log_dir) if log_dir else Config.DEFAULT_LOG_DIR
        
        # JSON Schema验证器
        self.schema_validator = JsonSchemaValidator()
        
        # 元数据存储
        self.meta_data: Dict[str, Any] = self.schema_validator.create_empty_json(
            db_type, db_model, identifier or "temp"
        )
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """设置日志配置"""
        try:
            # 确保日志目录存在
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = Config.get_log_file(self.log_dir)
            
            # 配置logger
            logger.remove()  # 移除默认处理器
            logger.add(
                log_file,
                format=Config.LOG_FORMAT,
                level=Config.LOG_LEVEL,
                rotation="10 MB",
                retention="7 days",
                encoding="utf-8"
            )
            # 同时输出到控制台
            logger.add(
                sys.stdout,
                format=Config.LOG_FORMAT,
                level=Config.LOG_LEVEL,
                colorize=True
            )
        except Exception as e:
            print(f"设置日志失败: {e}", file=sys.stderr)
    
    def _extract_identifier_from_dir(self, dir_path: Path) -> Tuple[str, str, str, str]:
        """
        从目录名中提取标识信息
        
        Args:
            dir_path: 目录路径
            
        Returns:
            (hostname, sid, dbname, collect_date) 元组
        """
        dir_name = dir_path.name
        
        # 尝试解析格式: hostname_sid_date 或 hostname_dbname_date
        parts = dir_name.split('_')
        
        if len(parts) >= 3:
            # 提取日期部分 (最后一部分应该是8位数字)
            date_part = parts[-1]
            if re.match(r'^\d{8}$', date_part):
                hostname = parts[0]
                # 中间部分作为sid/dbname
                sid_or_dbname = '_'.join(parts[1:-1]) if len(parts) > 3 else parts[1]
                return hostname, sid_or_dbname, sid_or_dbname, date_part
        
        # 如果无法解析，返回默认值
        logger.warning(f"无法从目录名解析标识信息: {dir_name}")
        return "unknown", "unknown", "unknown", datetime.now().strftime("%Y%m%d")
    
    def _generate_identifier(self) -> str:
        """
        自动生成identifier
        
        Returns:
            生成的identifier字符串
        """
        if self.identifier:
            return self.identifier
        
        # 从第一个输入目录提取信息
        first_dir = self.import_dirs[0]
        hostname, sid, dbname, collect_date = self._extract_identifier_from_dir(first_dir)
        
        # 根据数据库模型生成不同的identifier
        if self.db_model == 'one':
            # 单机模式: hostname_sid_date
            identifier = f"{hostname}_{sid}_{collect_date}"
        else:
            # RAC模式: 使用dbname而不是sid (因为RAC的多个节点共享dbname)
            identifier = f"{dbname}_{collect_date}"
        
        # 清理非法字符
        identifier = re.sub(r'[^a-zA-Z0-9_-]', '_', identifier)
        
        return identifier
    
    def parse_file_status(self, directory: Path, node_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        解析目录中的file_status.json文件
        
        Args:
            directory: 包含file_status.json的目录
            node_number: RAC节点编号 (可选，1-4)
            
        Returns:
            解析后的元数据，失败返回None
        """
        status_file = directory / Config.FILE_STATUS_JSON
        
        if not status_file.exists():
            logger.error(f"文件不存在: {status_file}")
            return None
        
        try:
            with open(status_file, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
            
            # 验证必需字段 - 兼容不同的字段名称
            # 检查hostname
            if 'hostname' not in data:
                logger.error(f"缺少必需字段 'hostname' 在 {status_file}")
                return None
            
            # 检查sid字段 - 兼容oracle_sid和sid
            if 'sid' not in data and 'oracle_sid' not in data:
                logger.error(f"缺少必需字段 'sid' 或 'oracle_sid' 在 {status_file}")
                return None
            
            # 检查日期字段 - 兼容collect_date和inspection_time
            if 'collect_date' not in data and 'inspection_time' not in data:
                logger.error(f"缺少必需字段 'collect_date' 或 'inspection_time' 在 {status_file}")
                return None
            
            # 检查files字段
            if 'files' not in data:
                logger.error(f"缺少必需字段 'files' 在 {status_file}")
                return None
            
            # 提取标识信息
            hostname, sid, dbname, collect_date = self._extract_identifier_from_dir(directory)
            
            # 处理sid字段 - 兼容oracle_sid
            actual_sid = data.get('sid') or data.get('oracle_sid') or sid
            
            # 处理日期字段 - 兼容inspection_time
            actual_date = data.get('collect_date')
            if not actual_date and 'inspection_time' in data:
                # 从inspection_time提取日期 (格式: 2025-08-26T10:45:29+0800)
                inspection_time = data['inspection_time']
                if inspection_time and len(inspection_time) >= 10:
                    actual_date = inspection_time[:10].replace('-', '')  # 转换为YYYYMMDD
            actual_date = actual_date or collect_date
            
            # 构建新格式的metainfo项
            meta_item = {
                "hostname": data.get('hostname', hostname),
                "sid": actual_sid,
                "dbname": data.get('dbname', dbname),
                "collect_date": actual_date,
                "source_dir": str(directory),
                "files": {}
            }
            
            # 如果是RAC模式，添加节点信息
            if self.db_model == 'rac' and node_number:
                meta_item["node_info"] = {
                    "node_number": node_number,
                    "node_name": f"node{node_number}"
                }
            
            # 转换文件信息格式 - 兼容数组和对象格式
            files_data = data.get('files', {})
            
            # 如果files是数组格式，转换为对象格式
            if isinstance(files_data, list):
                for file_info in files_data:
                    if isinstance(file_info, dict):
                        filename = file_info.get('filename', '')
                        if filename:
                            # 使用文件名（不含扩展名）作为key
                            file_key = Path(filename).stem
                            meta_item["files"][file_key] = {
                                "path": str(directory / filename),
                                "exists": file_info.get('exists', False),
                                "size": file_info.get('size', 0)
                            }
                            
                            # 添加修改时间(如果有)
                            if 'modified' in file_info:
                                meta_item["files"][file_key]["modified"] = file_info['modified']
            else:
                # 原来的对象格式处理
                for file_key, file_info in files_data.items():
                    if isinstance(file_info, dict):
                        filename = file_info.get('filename', '')
                        meta_item["files"][file_key] = {
                            "path": str(directory / filename) if filename else "",
                            "exists": file_info.get('exists', False),
                            "size": file_info.get('size', 0)
                        }
                        
                        # 添加修改时间(如果有)
                        if 'modified' in file_info:
                            meta_item["files"][file_key]["modified"] = file_info['modified']
            
            return meta_item
            
        except json.JSONDecodeError as e:
            logger.error(f"解析JSON文件失败 {status_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"读取文件错误 {status_file}: {e}")
            return None
    
    def validate_directory(self, directory: Path, data: Dict[str, Any]) -> bool:
        """
        验证目录中必需的文件是否存在
        
        Args:
            directory: 要验证的目录
            data: 解析后的元数据
            
        Returns:
            验证通过返回True，否则False
        """
        is_valid = True
        
        # 检查数据库类型所需的文件
        for required_file in self.db_config['required_files']:
            file_path = directory / required_file
            if not file_path.exists():
                logger.warning(f"缺少必需文件: {file_path}")
                is_valid = False
        
        # 验证文件信息
        files_info = data.get('files', {})
        for file_key, file_data in files_info.items():
            if isinstance(file_data, dict):
                file_path = file_data.get('path', '')
                if file_path:
                    file_path = Path(file_path)
                    exists = file_data.get('exists', False)
                    actual_exists = file_path.exists()
                    
                    if exists != actual_exists:
                        logger.warning(
                            f"文件存在状态不匹配 {file_path.name}: "
                            f"记录为 {exists}, 实际为 {actual_exists}"
                        )
                        is_valid = False
        
        return is_valid
    
    def generate_meta_json(self) -> bool:
        """
        生成数据库元数据JSON文件
        
        Returns:
            成功返回True，失败返回False
        """
        # 确保输出目录存在
        self.json_out_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成最终的identifier
        final_identifier = self._generate_identifier()
        self.meta_data["identifier"] = final_identifier
        
        # 生成符合命名规范的文件名
        filename = self.schema_validator.generate_filename(
            self.db_type, self.db_model, final_identifier
        )
        output_file = self.json_out_dir / filename
        
        # 验证JSON数据
        is_valid, error_msg = self.schema_validator.validate_json(self.meta_data)
        if not is_valid:
            logger.error(f"JSON数据验证失败: {error_msg}")
            return False
        
        try:
            # 写入JSON文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.meta_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"成功生成元数据JSON: {output_file}")
            logger.info(f"处理节点数: {len(self.meta_data['metainfo'])}")
            print(f"✅ 成功生成JSON文件: {output_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"写入JSON文件失败: {e}")
            return False
    
    def parse(self) -> bool:
        """
        主解析方法，处理所有输入目录
        
        Returns:
            解析成功返回True，失败返回False
        """
        logger.info(f"开始 {self.db_type} 元数据解析...")
        logger.info(f"数据库模型: {self.db_model}")
        logger.info(f"输入目录数: {len(self.import_dirs)}")
        
        # 验证所有输入目录存在
        for dir_path in self.import_dirs:
            if not dir_path.exists():
                logger.error(f"输入目录不存在: {dir_path}")
                return False
            if not dir_path.is_dir():
                logger.error(f"路径不是目录: {dir_path}")
                return False
        
        # RAC模式特殊处理
        if self.db_model == 'rac' and RacParser:
            return self._parse_rac_mode()
        
        # 单机模式处理 (原逻辑)
        for idx, directory in enumerate(self.import_dirs, 1):
            logger.info(f"处理目录 {idx}/{len(self.import_dirs)}: {directory}")
            
            # 解析file_status.json
            meta_item = self.parse_file_status(directory)
            if not meta_item:
                logger.error(f"解析目录失败: {directory}")
                return False
            
            # 验证目录内容
            if not self.validate_directory(directory, meta_item):
                logger.warning(f"目录验证失败: {directory}")
                # 继续处理，但标记验证状态
                meta_item['validation_status'] = 'failed'
            else:
                meta_item['validation_status'] = 'passed'
            
            # 添加到metainfo数组
            self.meta_data['metainfo'].append(meta_item)
            logger.info(f"成功处理目录: {directory.name}")
        
        if not self.meta_data['metainfo']:
            logger.error("未收集到有效数据")
            return False
        
        # 更新时间戳
        self.meta_data['timestamp'] = datetime.now().isoformat()
        
        # 生成元数据JSON文件
        return self.generate_meta_json()
    
    def _parse_rac_mode(self) -> bool:
        """
        RAC模式的特殊处理逻辑
        
        Returns:
            解析成功返回True，失败返回False
        """
        logger.info("使用RAC模式解析多节点数据...")
        
        try:
            # 使用RacParser解析RAC集群
            directories = [str(d) for d in self.import_dirs]
            cluster = RacParser.parse_rac_directories(directories)
            
            # 验证一致性
            is_consistent, issues = cluster.validate_consistency()
            if not is_consistent:
                logger.warning(f"RAC一致性检查问题: {issues}")
            
            # 合并节点文件信息
            metainfo = RacParser.merge_node_files(cluster)
            
            # 更新meta_data
            self.meta_data['metainfo'] = metainfo
            
            # 使用集群的identifier（如果没有指定）
            if not self.identifier:
                self.identifier = cluster.generate_identifier()
                logger.info(f"自动生成RAC identifier: {self.identifier}")
            
            # 更新dbname（使用集群级别的dbname）
            if cluster.dbname:
                # 可选：在meta_data中添加集群级别的信息
                self.meta_data['cluster_info'] = {
                    'cluster_name': cluster.cluster_name,
                    'dbname': cluster.dbname,
                    'node_count': cluster.node_count,
                    'consistency_check': is_consistent
                }
            
            # 更新时间戳
            self.meta_data['timestamp'] = datetime.now().isoformat()
            
            # 生成元数据JSON文件
            return self.generate_meta_json()
            
        except Exception as e:
            logger.error(f"RAC模式解析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


# 用于从main.py调用的函数
def parse_metadata(db_type: str,
                  db_model: str,
                  import_dirs: List[str],
                  json_out_dir: str,
                  identifier: Optional[str] = None,
                  log_dir: Optional[str] = None) -> bool:
    """
    解析数据库元数据的公共接口
    
    Args:
        db_type: 数据库类型
        db_model: 数据库模型
        import_dirs: 输入目录列表
        json_out_dir: JSON输出目录
        identifier: 自定义标识符
        log_dir: 日志目录
        
    Returns:
        成功返回True，失败返回False
    """
    try:
        parser = DatabaseMetaParser(
            db_type=db_type,
            db_model=db_model,
            import_dirs=import_dirs,
            json_out_dir=json_out_dir,
            identifier=identifier,
            log_dir=log_dir
        )
        return parser.parse()
    except Exception as e:
        logger.error(f"解析元数据失败: {e}")
        return False


def main():
    """
    独立运行的入口函数（用于测试）
    实际使用应通过main.py调用
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Database Metadata Parser (测试模式)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--db-type',
        choices=['oracle', 'mysql', 'postgresql', 'sqlserver'],
        default='oracle',
        help='数据库类型 (默认: oracle)'
    )
    
    parser.add_argument(
        '--db-model',
        choices=['one', 'rac'],
        default='one',
        help='数据库模型 (默认: one)'
    )
    
    parser.add_argument(
        '--import-dir',
        action='append',
        dest='import_dirs',
        help='输入目录 (可多次指定用于RAC模式)'
    )
    
    parser.add_argument(
        '--json-out',
        required=True,
        help='JSON输出目录'
    )
    
    parser.add_argument(
        '--identifier',
        help='自定义标识符 (可选)'
    )
    
    parser.add_argument(
        '--log-dir',
        help='日志目录 (可选)'
    )
    
    args = parser.parse_args()
    
    # 检查必需参数
    if not args.import_dirs:
        print("错误: 必须指定至少一个 --import-dir")
        return 1
    
    # 调用解析函数
    success = parse_metadata(
        db_type=args.db_type,
        db_model=args.db_model,
        import_dirs=args.import_dirs,
        json_out_dir=args.json_out,
        identifier=args.identifier,
        log_dir=args.log_dir
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
