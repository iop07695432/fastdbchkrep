#!/usr/bin/env python3
"""
MySQL数据库元数据解析器
基于通用的DatabaseMetaParser，处理MySQL特定的逻辑
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from loguru import logger

# 导入通用的组件
from ..parser import Config, JsonSchemaValidator


class MySQLMetaParser:
    """MySQL数据库元数据解析器"""
    
    def __init__(self, 
                 import_dirs: Optional[List[str]] = None,
                 json_out_dir: Optional[str] = None,
                 identifier: Optional[str] = None,
                 log_dir: Optional[str] = None):
        """
        初始化MySQL解析器
        
        Args:
            import_dirs: 输入目录列表
            json_out_dir: JSON输出目录
            identifier: 自定义标识符
            log_dir: 日志目录
        """
        self.db_type = 'mysql'
        self.db_model = 'one'  # MySQL目前只支持单机模式
        self.import_dirs = [Path(d) for d in (import_dirs or [])]
        self.json_out_dir = Path(json_out_dir) if json_out_dir else Config.DEFAULT_JSON_DIR
        self.identifier = identifier
        self.log_dir = Path(log_dir) if log_dir else None
        
        # 初始化元数据结构
        self.meta_data = JsonSchemaValidator.create_empty_json(
            dbtype=self.db_type,
            dbmodel=self.db_model,
            identifier=self.identifier or "unknown"
        )
        
        # 设置日志
        self._setup_logging()
        
    def _setup_logging(self):
        """设置日志配置"""
        try:
            log_file = Config.get_log_file(self.log_dir)
            if log_file.parent.exists():
                logger.add(
                    log_file,
                    format=Config.LOG_FORMAT,
                    level=Config.LOG_LEVEL,
                    rotation="100 MB",
                    retention="30 days",
                    encoding="utf-8"
                )
        except Exception as e:
            print(f"设置日志失败: {e}")
            
    def _extract_identifier_from_dir(self, dir_path: Path) -> Tuple[str, str, str]:
        """
        从目录名中提取标识信息
        
        Args:
            dir_path: 目录路径
            
        Returns:
            (hostname, dbname, collect_date) 元组
        """
        dir_name = dir_path.name
        
        # 尝试解析格式: hostname_mysql_date
        parts = dir_name.split('_')
        
        if len(parts) >= 3:
            # 提取日期部分 (最后一部分应该是8位数字)
            date_part = parts[-1]
            if re.match(r'^\d{8}$', date_part):
                hostname = parts[0]
                # 中间部分作为dbname，对MySQL通常是'mysql'
                dbname = '_'.join(parts[1:-1]) if len(parts) > 3 else parts[1]
                return hostname, dbname, date_part
        
        # 如果无法解析，返回默认值
        logger.warning(f"无法从目录名解析标识信息: {dir_name}")
        return "unknown", "mysql", datetime.now().strftime("%Y%m%d")
        
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
        hostname, dbname, collect_date = self._extract_identifier_from_dir(first_dir)
        
        # MySQL单机模式: hostname_dbname_date
        identifier = f"{hostname}_{dbname}_{collect_date}"
        
        # 清理非法字符
        identifier = re.sub(r'[^a-zA-Z0-9_-]', '_', identifier)
        
        return identifier
        
    def parse_file_status(self, directory: Path) -> Optional[Dict[str, Any]]:
        """
        解析MySQL的file_status.json文件
        
        Args:
            directory: 包含file_status.json的目录
            
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
                
            # 验证MySQL必需字段
            if 'hostname' not in data:
                logger.error(f"缺少必需字段 'hostname' 在 {status_file}")
                return None
                
            # MySQL不需要sid字段，但需要检查日期
            if 'collect_date' not in data and 'inspection_time' not in data:
                logger.error(f"缺少必需字段 'collect_date' 或 'inspection_time' 在 {status_file}")
                return None
                
            if 'files' not in data:
                logger.error(f"缺少必需字段 'files' 在 {status_file}")
                return None
                
            # 提取标识信息
            hostname, dbname, collect_date = self._extract_identifier_from_dir(directory)
            
            # MySQL使用固定的sid值
            actual_sid = 'mysql'
            
            # 处理日期字段
            actual_date = data.get('collect_date')
            if not actual_date and 'inspection_time' in data:
                inspection_time = data['inspection_time']
                if inspection_time and len(inspection_time) >= 10:
                    actual_date = inspection_time[:10].replace('-', '')
            actual_date = actual_date or collect_date
            
            # 构建元数据项
            meta_item = {
                "hostname": data.get('hostname', hostname),
                "sid": actual_sid,
                "dbname": dbname,
                "collect_date": actual_date,
                "source_dir": str(directory),
                "files": {}
            }
            
            # 添加MySQL特定字段
            if 'mysql_connection' in data:
                meta_item['mysql_connection'] = data['mysql_connection']
                
            # 转换文件信息（MySQL使用数组格式）
            files_data = data.get('files', [])
            if isinstance(files_data, list):
                for file_info in files_data:
                    if isinstance(file_info, dict):
                        filename = file_info.get('filename', '')
                        if filename:
                            file_key = Path(filename).stem
                            meta_item["files"][file_key] = {
                                "path": str(directory / filename),
                                "exists": file_info.get('exists', False),
                                "size": file_info.get('size', 0)
                            }
                            
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
        
        # MySQL必需的文件
        required_files = [
            'file_status.json',
            '01_system_info.txt',
            '02_hardware_info.json'
        ]
        
        for required_file in required_files:
            file_path = directory / required_file
            if not file_path.exists():
                logger.warning(f"缺少必需文件: {file_path}")
                is_valid = False
                
        return is_valid
        
    def generate_meta_json(self) -> bool:
        """
        生成元数据JSON文件
        
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 确保输出目录存在
            self.json_out_dir.mkdir(parents=True, exist_ok=True)
            
            # 更新identifier
            if not self.identifier:
                self.identifier = self._generate_identifier()
                self.meta_data['identifier'] = self.identifier
                
            # 生成文件名
            filename = JsonSchemaValidator.generate_filename(
                self.db_type, self.db_model, self.identifier
            )
            output_file = self.json_out_dir / filename
            
            # 校验JSON
            is_valid, error_msg = JsonSchemaValidator.validate_json(self.meta_data)
            if not is_valid:
                logger.error(f"JSON校验失败: {error_msg}")
                
            # 写入文件
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
                
        # MySQL单机模式处理
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


def parse_mysql_metadata(import_dirs: List[str],
                         json_out_dir: str,
                         identifier: Optional[str] = None,
                         log_dir: Optional[str] = None) -> bool:
    """
    解析MySQL数据库元数据的公共接口
    
    Args:
        import_dirs: 输入目录列表
        json_out_dir: JSON输出目录
        identifier: 自定义标识符
        log_dir: 日志目录
        
    Returns:
        成功返回True，失败返回False
    """
    try:
        parser = MySQLMetaParser(
            import_dirs=import_dirs,
            json_out_dir=json_out_dir,
            identifier=identifier,
            log_dir=log_dir
        )
        return parser.parse()
    except Exception as e:
        logger.error(f"解析MySQL元数据失败: {e}")
        return False