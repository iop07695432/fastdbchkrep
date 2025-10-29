"""
FastDBCheckRep 报告生成API
统一对外接口 - 从原markdown_generator.py迁移而来
"""
import json
from pathlib import Path
from typing import Optional
from loguru import logger

from .oracle.generator import MarkdownGenerator as OracleMarkdownGenerator
try:
    from .mysql.generator import MarkdownGenerator as MySQLMarkdownGenerator
except ImportError:  # MySQL报告实现尚未存在时保持兼容
    MySQLMarkdownGenerator = None
from .oracle.rac_generator import RacReportMerger

MarkdownGenerator = OracleMarkdownGenerator


def generate_report_from_json(json_file: str, 
                             output_dir: str,
                             company_name: str,
                             user_company: str, 
                             application_name: str,
                             suptime: Optional[str] = None,
                             supname: Optional[str] = None,
                             quiet: bool = False) -> bool:
    """
    从JSON文件生成Markdown报告
    
    Args:
        json_file: 输入的JSON文件路径
        output_dir: 输出目录路径（-mdout参数）
        company_name: 公司名称
        user_company: 客户单位名称
        application_name: 应用系统名称
        suptime: 现场支持总时间（小时）
        supname: 支持工程师姓名
        quiet: 是否静默模式
        
    Returns:
        bool: 生成成功返回True，失败返回False
    """
    try:
        # 读取JSON文件
        json_path = Path(json_file)
        if not json_path.exists():
            logger.error(f"JSON文件不存在: {json_file}")
            return False
        
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # 提取数据库类型和模型
        # 默认采用 oracle，兼容历史 JSON 中的 oracle_db_file
        db_type = json_data.get('dbtype', 'oracle')
        db_model = json_data.get('dbmodel', 'one')
        identifier = json_data.get('identifier', 'unknown')
        
        if not quiet:
            print(f"  数据库类型: {db_type}")
            print(f"  数据库模型: {db_model}")
            print(f"  标识符: {identifier}")
        
        # 创建生成器实例，传入输出目录
        generator_cls = OracleMarkdownGenerator
        if db_type.lower() == "mysql":
            if MySQLMarkdownGenerator is None:
                logger.error("MySQL 报告模块不可用，请确认已实现 report.mysql.generator")
                return False
            generator_cls = MySQLMarkdownGenerator

        generator = generator_cls(
            db_type=db_type,
            output_dir=Path(output_dir),  # 传入-mdout参数指定的目录
            company_name=company_name,
            user_company=user_company,
            application_name=application_name,
            suptime=suptime,
            supname=supname
        )
        
        # 生成报告
        success = generator.generate_from_json(json_data, quiet=quiet)

        # RAC 模式下执行合并与图片路径改写
        if success and db_model == 'rac':
            try:
                merge_ok = RacReportMerger.merge_reports(
                    json_file=str(json_path),
                    output_dir=output_dir,
                    quiet=quiet,
                )
                if not merge_ok:
                    logger.warning("RAC 合并过程出现问题，请检查日志")
                return merge_ok
            except Exception as e:
                logger.error(f"RAC 合并失败: {e}")
                return False

        return success
        
    except Exception as e:
        logger.error(f"生成报告失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# 导出主要类和函数
__all__ = ["MarkdownGenerator", "generate_report_from_json"]
