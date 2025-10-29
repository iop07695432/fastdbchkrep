"""
Oracle数据库Markdown报告生成器 - 从markdown_generator.py迁移而来
"""
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
import matplotlib.pyplot as plt
 

from ..common.config import MarkdownConfig
from ..pdf import MarkdownToPdfConverter
from ..common.chart_utils import normalize_time_label, apply_time_axis, align_twinx_xlim
from ..common.utils import find_file_by_name, find_file_by_pattern
from ..common.html_capture import HTMLCapture
from ..common.template_config import TemplateConfig
from .models import *
from .parsers import *
from .rac_generator import format_disk_scheduler_rac


class MarkdownGenerator:
    """Markdown报告生成器"""

    def __init__(self, db_type: str = "oracle",
                 output_dir: Optional[Path] = None,
                 company_name: Optional[str] = None,
                 user_company: Optional[str] = None,
                 application_name: Optional[str] = None,
                 suptime: Optional[str] = None,
                 supname: Optional[str] = None):
        """
        初始化Markdown生成器

        Args:
            db_type: 数据库类型，默认为oracle
            output_dir: 输出目录路径（来自-mdout参数）
            company_name: 公司名称
            user_company: 客户单位名称
            application_name: 应用系统名称
            suptime: 现场支持总时间（小时）
            supname: 支持工程师姓名
        """
        self.db_type = db_type
        self.output_dir = output_dir or MarkdownConfig.OUTDIR_PATH  # 使用传入的路径或默认路径
        self.company_name = company_name or "鼎诚科技"
        self.user_company = user_company or "客户单位"
        self.application_name = application_name or "应用系统"
        self.suptime = suptime
        self.supname = supname
        
        # 更新模板占位符的值，用于报告生成
        if company_name:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"] = f"{company_name}"
        if user_company:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"] = user_company
        if application_name:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"] = application_name

        # 初始化日志 - 统一放到data/log目录
        log_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "log"
        log_dir.mkdir(exist_ok=True)
        logger.add(log_dir / "fastdbchkrep.log",
                  rotation="10 MB",
                  level="INFO",
                  format="{time} | {level} | {message}")
    
    def generate_from_json(self, json_data: Dict[str, Any], quiet: bool = False) -> bool:
        """
        从JSON数据生成markdown报告
        
        Args:
            json_data: 解析后的JSON数据
            quiet: 是否静默模式
            
        Returns:
            bool: 是否成功生成
        """
        try:
            # 从JSON数据中提取metainfo
            metainfo = json_data.get('metainfo', [])
            if not metainfo:
                logger.error("JSON数据中没有metainfo")
                return False
            
            success_count = 0
            # 为每个节点生成报告
            for idx, meta_info in enumerate(metainfo, 1):
                if not quiet:
                    hostname = meta_info.get('hostname', 'unknown')
                    sid = meta_info.get('sid', 'unknown') 
                    print(f"  处理节点 {idx}/{len(metainfo)}: {hostname} (SID: {sid})")
                
                # 生成单个实例的报告
                if self._generate_single_instance_from_meta(meta_info):
                    success_count += 1
                    
            if success_count > 0:
                if not quiet:
                    print(f"  成功生成 {success_count}/{len(metainfo)} 个节点的报告")
                return True
            else:
                logger.error("未能生成任何报告")
                return False
                
        except Exception as e:
            logger.error(f"从JSON生成报告失败: {e}")
            return False
    
    def _generate_single_instance_from_meta(self, meta_info: Dict[str, Any]) -> bool:
        """
        从元信息生成单个实例的报告
        
        Args:
            meta_info: 节点元信息
            
        Returns:
            bool: 是否成功生成
        """
        try:
            # 获取输出路径
            output_path = self._get_markdown_output_path(meta_info)
            output_dir = output_path.parent
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建图片目录
            server_picture_dir = output_dir / "server_picture"
            awr_picture_dir = output_dir / "awr_picture"
            server_picture_dir.mkdir(exist_ok=True)
            awr_picture_dir.mkdir(exist_ok=True)
            
            # 构建一个兼容旧格式的db_info和meta_info
            db_info = {
                "dbname": meta_info.get("dbname", ""),
                "dbtype": self.db_type,
                "dbmodel": "one" if not meta_info.get("node_info") else "rac",
                "metainfo": [meta_info]  # 添加metainfo数组以支持hostname显示
            }
            
            # 将新格式的files转换为旧格式的incfilelist
            incfilelist = []
            files = meta_info.get("files", {})
            for file_key, file_info in files.items():
                if isinstance(file_info, dict):
                    # 根据file_key生成正确的文件名
                    if file_key == "00_inspection_summary":
                        filename = "00_inspection_summary.txt"
                    elif file_key == "01_system_info":
                        filename = "01_system_info.txt"
                    elif file_key == "02_hardware_info":
                        filename = "02_hardware_info.json"
                    elif file_key.startswith("03_alert_"):
                        filename = f"{file_key}.log"
                    elif file_key == "04_health_check":
                        filename = "04_health_check.txt"
                    elif file_key == "05_adrci_ora":
                        filename = "05_adrci_ora.txt"
                    elif file_key == "09_rman_info":
                        filename = "09_rman_info.txt"
                    elif file_key == "10_sar_report":
                        filename = "10_sar_report.txt"
                    elif file_key.startswith("11_awrrpt"):
                        filename = f"{file_key}.html"
                    else:
                        # 对于RAC特有文件
                        filename = f"{file_key}.txt"
                    
                    incfilelist.append({
                        "filename": filename,
                        "fileurl": file_info.get("path", "")
                    })
            old_format_meta = {
                "sid": meta_info.get("sid"),
                "hostname": meta_info.get("hostname"),
                "dirname": meta_info.get("source_dir", "").split("/")[-1] if meta_info.get("source_dir") else "",
                "incfilelist": incfilelist,
                "files": meta_info.get("files", {}),  # 保留原始的files字段以支持AWR查找
                "collect_date": meta_info.get("collect_date"),
                "source_dir": meta_info.get("source_dir"),
            }

            # 调用原有的报告生成方法
            result = self._generate_single_instance_markdown(db_info, old_format_meta)

            if result:
                logger.info(f"成功生成报告: {output_path}")
                logger.info(f"图片目录: {server_picture_dir}, {awr_picture_dir}")

            return result
            
        except Exception as e:
            logger.error(f"生成单个实例报告失败: {e}")
            return False



    def _generate_single_instance_markdown(self, db_info: Dict[str, Any], meta_info: Dict[str, Any]) -> bool:
        """
        为单个实例生成markdown报告

        Args:
            db_info: 数据库信息
            meta_info: 实例元信息

        Returns:
            bool: 是否成功生成
        """
        try:
            # 查找00_inspection_summary.txt文件
            summary_file_info = self._find_inspection_summary_file(meta_info["incfilelist"])
            if not summary_file_info:
                logger.error(f"未找到实例{meta_info['sid']}的00_inspection_summary.txt文件")
                return False

            # 解析00_inspection_summary.txt内容
            summary_file_path = Path(summary_file_info["fileurl"])
            summary_data = InspectionSummaryParser.parse_inspection_summary(summary_file_path)
            if not summary_data:
                logger.error(f"解析{summary_file_path}失败")
                return False

            # 查找并解析01_system_info.txt文件
            system_info_file = find_file_by_name(meta_info["incfilelist"], "01_system_info.txt")
            system_data = None
            if system_info_file:
                system_file_path = Path(system_info_file["fileurl"])
                system_data = SystemInfoParser.parse_system_info(system_file_path)

            # 查找并解析02_hardware_info.json文件
            hardware_info_file = find_file_by_name(meta_info["incfilelist"], "02_hardware_info.json")
            hardware_data = None
            if hardware_info_file:
                hardware_file_path = Path(hardware_info_file["fileurl"])
                hardware_data = HardwareInfoParser.parse_hardware_info(hardware_file_path)

            # 查找09_rman_info.txt文件（需要在解析health_check之前找到）
            rman_info_file = find_file_by_name(meta_info["incfilelist"], "09_rman_info.txt")
            rman_file_path = None
            rman_data = None
            if rman_info_file:
                rman_file_path = Path(rman_info_file["fileurl"])
                rman_data = RmanInfoParser.parse_rman_info(rman_file_path)

            # 查找并解析04_health_check.txt文件
            health_check_file = find_file_by_name(meta_info["incfilelist"], "04_health_check.txt")
            database_config_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                # 构建实例名称字符串（单机显示一个，集群显示多个）
                instance_names = self._build_instance_names_string(db_info)
                database_config_data = HealthCheckParser.parse_health_check(health_check_path, instance_names.upper(), rman_file_path)

            # 查找并解析Data Guard信息（从04_health_check.txt中）
            dg_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                dg_data = DataGuardInfoParser.parse_data_guard_info(health_check_path)

            # 查找并解析05_adrci_ora.txt文件
            adrci_info_file = find_file_by_name(meta_info["incfilelist"], "05_adrci_ora.txt")
            adrci_data = None
            if adrci_info_file:
                adrci_file_path = Path(adrci_info_file["fileurl"])
                adrci_data = AdrciInfoParser.parse_adrci_info(adrci_file_path)

            # 查找并解析03_alert_{SID}.log文件
            alert_log_file = find_file_by_pattern(meta_info["incfilelist"], r"03_alert_.*\.log")
            alert_data = None
            if alert_log_file:
                alert_log_path = Path(alert_log_file["fileurl"])
                # 传递health_check_path用于提取ALERT_LOG路径
                health_check_path = None
                if health_check_file:
                    health_check_path = Path(health_check_file["fileurl"])
                alert_data = AlertLogParser.parse_alert_log(alert_log_path, health_check_path)

            # 解析资源配置数据（需要硬件信息和健康检查信息）
            resource_config_data = None
            if hardware_data and database_config_data and hardware_info_file and health_check_file:
                hardware_file_path = Path(hardware_info_file["fileurl"])
                health_check_path = Path(health_check_file["fileurl"])
                instance_names = self._build_instance_names_string(db_info)
                resource_config_data = ResourceConfigParser.parse_resource_config(hardware_file_path, health_check_path, instance_names.upper(), rman_file_path)

            # 解析控制文件和在线日志数据
            control_file_log_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                control_file_log_data = ControlFileLogParser.parse_control_file_log(health_check_path)

            # 解析表空间和数据文件数据
            tablespace_file_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                tablespace_file_data = TablespaceFileParser.parse_tablespace_file(health_check_path)

            # 解析归档统计数据
            archive_stat_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                archive_stat_data = ArchiveStatParser.parse_archive_stat(health_check_path)

            # 解析ASM磁盘数据
            asm_disk_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                asm_disk_data = AsmDiskParser.parse_asm_disk(health_check_path)

            # 解析PL/SQL病毒检查数据
            plsql_virus_data = None
            if health_check_file:
                health_check_path = Path(health_check_file["fileurl"])
                plsql_virus_data = PlsqlVirusParser.parse_plsql_virus(health_check_path)

            # 解析操作系统性能数据（10_sar_report.txt）
            os_performance_data = None
            sar_report_file = find_file_by_name(meta_info["incfilelist"], "10_sar_report.txt")
            if sar_report_file:
                sar_report_path = Path(sar_report_file["fileurl"])
                logger.info(f"解析SAR报告文件: {sar_report_path}")
                os_performance_data = SarReportParser.parse_sar_report(sar_report_path)
                if os_performance_data:
                    logger.info(f"成功解析SAR数据，主机名: {os_performance_data.hostname}")
                    logger.info(f"CPU数据长度: {len(os_performance_data.cpu_data)}")
                    logger.info(f"内存数据长度: {len(os_performance_data.memory_data)}")
                    logger.info(f"磁盘IO数据长度: {len(os_performance_data.disk_io_data)}")
                else:
                    logger.warning("SAR数据解析失败")

            # 解析磁盘空间数据（从02_hardware_info.json获取）
            disk_space_data = None
            if hardware_info_file:
                hardware_file_path = Path(hardware_info_file["fileurl"])
                disk_space_data = DiskSpaceParser.parse_disk_space(hardware_file_path)

            # 解析AWR报告数据（11_awrrpt_*.html）
            awr_data = None
            awr_file = find_file_by_pattern(meta_info["incfilelist"], r"11_awrrpt_.*\.html")
            if awr_file:
                awr_file_path = Path(awr_file["fileurl"])
                logger.info(f"解析AWR报告文件: {awr_file_path}")
                awr_data = AwrReportParser.parse_awr_report(awr_file_path)
                if awr_data:
                    logger.info(f"成功解析AWR数据，数据库: {awr_data.db_name}，实例: {awr_data.instance}")
                else:
                    logger.warning("AWR数据解析失败")

            # 生成markdown内容
            markdown_content = self._build_markdown_content(
                db_info, summary_data, system_data, hardware_data, database_config_data, meta_info,
                rman_data, dg_data, adrci_data, alert_data, resource_config_data, 
                control_file_log_data, tablespace_file_data, archive_stat_data, 
                asm_disk_data, plsql_virus_data, os_performance_data, disk_space_data, awr_data
            )

            # 保存markdown文件
            output_path = self._get_markdown_output_path(meta_info)
            saved = self._save_markdown_file(output_path, markdown_content)

            # 生成可编辑HTML（与MD同目录），供工程师填写建议
            try:
                base_name = output_path.stem
                conv = MarkdownToPdfConverter()
                ok, editable_path = conv.generate_editable_html(
                    md_file=str(output_path),
                    output_dir=str(output_path.parent),
                    output_name=base_name
                )
                if not ok:
                    logger.warning(f"可编辑HTML生成失败: {output_path}")
                else:
                    logger.info(f"可编辑HTML已生成: {editable_path}")
            except Exception as e:
                logger.warning(f"生成可编辑HTML时发生异常: {e}")

            return saved

        except Exception as e:
            logger.error(f"生成实例{meta_info.get('sid', 'unknown')}的markdown失败: {e}")
            return False

    def _build_instance_names_string(self, db_info: Dict[str, Any]) -> str:
        """构建实例名称字符串（单机显示一个，集群显示多个逗号分割）"""
        all_meta_info = db_info.get("metainfo", [])
        instance_names = [info.get("sid", "-") for info in all_meta_info]
        return ", ".join(set(instance_names))  # 去重并用逗号分隔

    def _find_inspection_summary_file(self, file_list: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """在文件列表中查找00_inspection_summary.txt"""
        return find_file_by_name(file_list, "00_inspection_summary.txt")

    def _get_markdown_output_path(self, meta_info: Dict[str, Any]) -> Path:
        """
        获取markdown输出路径
        格式: outdir/{dbtype}/{identifier或dirname}/{hostname_sid.md}
        """
        # 优先使用source_dir中的目录名，如果没有则使用hostname_sid_date格式
        if 'source_dir' in meta_info:
            dirname = Path(meta_info['source_dir']).name
        elif 'dirname' in meta_info:
            dirname = meta_info["dirname"]
        else:
            # 生成默认目录名
            hostname = meta_info.get("hostname", "unknown")
            sid = meta_info.get("sid", "unknown")
            collect_date = meta_info.get("collect_date", "00000000")
            dirname = f"{hostname}_{sid}_{collect_date}"
        
        hostname = meta_info.get("hostname", "unknown")
        sid = meta_info.get("sid", "unknown")

        output_dir = self.output_dir / self.db_type / dirname
        markdown_filename = f"{hostname}_{sid}.md"

        return output_dir / markdown_filename

    def _build_markdown_content(self, db_info: Dict[str, Any], summary_data: InspectionSummaryData,
                               system_data: Optional[SystemInfoData] = None,
                               hardware_data: Optional[HardwareInfoData] = None,
                               database_config_data: Optional[DatabaseConfigData] = None,
                               meta_info: Dict[str, Any] = None,
                               rman_data: Optional[RmanInfoData] = None,
                               dg_data: Optional[DataGuardInfoData] = None,
                               adrci_data: Optional[AdrciInfoData] = None,
                               alert_data: Optional[AlertLogData] = None,
                               resource_config_data: Optional[ResourceConfigData] = None,
                               control_file_log_data: Optional[ControlFileLogData] = None,
                               tablespace_file_data: Optional[TablespaceFileData] = None,
                               archive_stat_data: Optional[ArchiveStatData] = None,
                               asm_disk_data: Optional[AsmDiskData] = None,
                               plsql_virus_data: Optional[PlsqlVirusData] = None,
                               os_performance_data: Optional[OsPerformanceData] = None,
                               disk_space_data: Optional[DiskSpaceData] = None,
                               awr_data: Optional[AwrReportData] = None) -> str:
        """构建markdown内容"""

        meta_info = meta_info or {}

        # 格式化数据库模式显示
        db_model_display = db_info["dbmodel"].upper()
        if db_model_display == "ONE":
            db_model_display = "单机"
        
        # 生成模板内容（封面页、目录、文档控制）
        template_content = ""

        # 计算Markdown输出目录，供资源相对路径解析
        output_path = self._get_markdown_output_path(meta_info)
        output_dir = output_path.parent

        # 1. 生成封面页
        support_start_raw, support_end_raw = self._resolve_support_dates(meta_info)
        cover_page = TemplateConfig.generate_cover_page(
            company_name=self.company_name,
            user_company=self.user_company,
            application_name=self.application_name,
            db_type="Oracle",
            support_start_date=support_start_raw,
            support_end_date=support_end_raw,
            suptime=self.suptime,
            supname=self.supname,
            base_dir=output_dir
        )
        
        # 2. 生成目录页
        toc_page = TemplateConfig.generate_toc()
        
        # 3. 生成文档控制页
        document_control = TemplateConfig.generate_document_control(
            company_name=self.company_name,
            user_company=self.user_company
        )
        
        # 组合模板内容
        template_content = cover_page + toc_page + document_control

        # 构建问题表格（4行，第一行是表头，后三行为空）
        problems_table = self._build_problems_table()

        # 构建文件状态显示内容
        file_status_display = self._format_file_status_content(summary_data.file_status_content)

        # 构建系统背景部分（如果有系统和硬件信息）
        system_background = ""
        if system_data or hardware_data or database_config_data:
            system_background = self._build_system_background_section(db_info, system_data, hardware_data, database_config_data, meta_info)

        # 构建3.3数据库资源相关配置表格
        resource_config_section = ""
        if resource_config_data:
            resource_config_section = self._build_resource_config_section(resource_config_data)

        # 构建第4章操作系统检查部分
        os_check_section = ""
        if os_performance_data or disk_space_data:
            # 获取输出目录
            output_path = self._get_markdown_output_path(meta_info)
            output_dir = output_path.parent
            sid = meta_info.get('sid', 'unknown')
            os_check_section = self._build_os_check_section(os_performance_data, disk_space_data, output_dir, sid)

        # 构建第5章数据库配置检查部分（原第4章）
        database_config_check = ""
        if rman_data or dg_data or adrci_data or alert_data:
            database_config_check = self._build_database_config_check_section(rman_data, dg_data, adrci_data, alert_data)

        # 构建4.7-4.11新增章节
        control_file_log_section = ""
        if control_file_log_data:
            control_file_log_section = self._build_control_file_log_section(control_file_log_data)

        # 4.6章节现在合并了表空间数据文件和归档统计信息
        tablespace_file_section = self._build_tablespace_file_section(tablespace_file_data, archive_stat_data)

        asm_disk_section = ""
        if asm_disk_data:
            asm_disk_section = self._build_asm_disk_section(asm_disk_data)

        plsql_virus_section = ""
        if plsql_virus_data:
            plsql_virus_section = self._build_plsql_virus_section(plsql_virus_data)

        # 构建第6章数据库性能检查部分（AWR报告）
        # 现在基于AWR HTML文件直接生成，不依赖解析的AWR数据
        awr_performance_section = self._build_awr_performance_section(awr_data, meta_info, db_info)

        # 规范化巡检时间：无论输入格式，统一输出为中文格式：YYYY年MM月DD日星期X
        formatted_inspection_time = self._format_inspection_time_cn(summary_data.inspection_time)

        # 组合最终的markdown内容：模板内容 + 原有内容
        markdown_content = template_content + f"""# 1. 健康检查总结

## 1.1. 健康检查概要

  如果{MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"]}工程师在检查中发现Oracle数据库的问题，我们将对有问题的情况进行记录，并通知客户改正；对于比较复杂的问题，我们将在报告中指出，并建议和协助客户进一步进行相关的详细检查，同时将问题提交到{MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"]}技术支持部，以便问题得到更快更好的解决。

  此次检查所需的资料来源主要是{formatted_inspection_time}使用 oracle_inspection.sh 脚本对{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"]}{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}Oracle数据库收集运行环境文件的结果。此次我们主要检查该数据库的性能和配置，在下面的报告中，我们将做出分析，然后提出相关的改进建议。

  此次检查的数据库范围是：{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"]}{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}Oracle{db_model_display}数据库。

## 1.2. 健康检查建议

以下是本次检查发现的一些主要问题和建议的总结。

{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}Oracle{db_model_display}数据库

{problems_table}

# 2. 健康检查介绍

## 2.1. 健康检查目标

数据库性能检查是用来：

- 评价数据库当前的性能情况
- 分析数据库应用瓶颈和资源竞争情况
- 指出存在的问题，提出解决建议

## 2.2. 健康检查方法

本次数据库性能检查的工具是：
- Oracle 数据库巡检工具为 oracle_inspection.sh
- MySQL 数据库巡检工具为 mysql_inspection.sh
- PostgreSQL 数据库巡检工具为 postgresql_inspection.sh
- SQLServer 数据库巡检工具为 sqlserver_inspection.sh


本次提供数据库巡检建议依据文件是：

{file_status_display}

## 2.3. 健康检查范围

本次检查仅限 {MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} Oracle {db_model_display}数据库，本报告提供的检查和建议主要针对以下方面：

- 主机配置
- 操作系统性能
- 数据库配置
- 数据库性能

本报告的提供的检查和建议不涉及：

- 具体的性能调整
- 应用程序的具体细节

**注意**：本次检查仅历时一天，其中还包括了提交分析报告的时间。所以在具体的性能方面仅做相应的建议。如需在数据库性能方面进行进一步的调整，请继续选择数据库性能调整。

{system_background}
{resource_config_section}

{os_check_section}
{database_config_check}
{control_file_log_section}
{tablespace_file_section}
{asm_disk_section}
{plsql_virus_section}
{awr_performance_section}
"""

        # 在所有代码块（```...```）结束后自动插入一条分割线，增强可读性
        markdown_content = self._add_hr_after_code_blocks(markdown_content)

        return markdown_content

    def _resolve_support_dates(self, meta_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """解析现场支持起止日期（优先取 collect_date，其次取目录名中的日期）。"""
        collect_date = meta_info.get("collect_date")
        if collect_date:
            return str(collect_date), str(collect_date)

        source_dir = meta_info.get("source_dir")
        if source_dir:
            match = re.search(r"(20\d{2})(\d{2})(\d{2})", Path(source_dir).name)
            if match:
                digits = "".join(match.groups())
                return digits, digits

        return None, None

    @staticmethod
    def _add_hr_after_code_blocks(text: str) -> str:
        """在每个 Markdown 代码块关闭标记后追加分割线（---）。

        规则：匹配形如
            ```[lang]\n...\n```
        的块，若其后未紧跟分割线，则插入一个空行+分割线+空行。
        """
        try:
            pattern = re.compile(r"(^```[^\n]*\n[\s\S]*?\n```[ \t]*\n?)(?!\n?---)", re.MULTILINE)
            new_text = pattern.sub(lambda m: m.group(1) + "\n---\n\n", text)

            # 折叠相邻或被空行分隔的重复分割线（避免出现两条或多条横线）
            def collapse_hr(s: str) -> str:
                prev = None
                cur = s
                hr_dup = re.compile(r"(?m)^(?:\s*\n)*---\s*\n(?:\s*\n)*---\s*\n")
                # 最多收敛几次，直到不再变化
                for _ in range(5):
                    prev = cur
                    cur = hr_dup.sub("\n---\n\n", cur)
                    if cur == prev:
                        break
                return cur

            return collapse_hr(new_text)
        except Exception:
            return text

    def _format_inspection_time_cn(self, raw_time: Optional[str]) -> str:
        """将各种可能的时间字符串规范化为中文日期：YYYY年MM月DD日星期X。

        处理示例：
        - "2025年 08月 26日 星期二 10:45:29 CST" -> "2025年08月26日星期二"
        - "Fri Sep  5 18:12:42 CST 2025" -> "2025年09月05日星期五"
        - "2025-08-26T10:45:29+0800" -> "2025年08月26日星期二"
        - "2025-09-02" / "20250902" -> "YYYY年MM月DD日星期X"
        """
        try:
            if not raw_time:
                return "未知时间"

            text = str(raw_time).strip()

            # 1) 已有中文格式（可带空格，可不带星期后细节）
            m = re.match(r"\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(星期[一二三四五六日]))?", text)
            if m:
                year = int(m.group(1))
                month = int(m.group(2))
                day = int(m.group(3))
                try:
                    weekday_idx = datetime(year, month, day).weekday()  # 0=周一
                    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][weekday_idx]
                except Exception:
                    weekday_cn = m.group(4) or ""
                return f"{year}年{month:02d}月{day:02d}日{weekday_cn}"

            # 2) ISO/常见数字格式
            patterns = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y%m%d",
            ]

            for p in patterns:
                try:
                    dt = datetime.strptime(text, p)
                    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                    return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
                except Exception:
                    pass

            # 3) 英文 date/日志风格（尽量兼容）
            en_patterns = [
                "%a %b %d %H:%M:%S %Z %Y",   # Fri Sep  5 18:12:42 CST 2025
                "%a, %b %d %H:%M:%S %Z %Y",
                "%a %b %d %H:%M:%S %Y",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S",
                "%d %b %Y %H:%M:%S %Z",
                "%b %d %Y %H:%M:%S",
            ]
            for p in en_patterns:
                try:
                    dt = datetime.strptime(text, p)
                    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                    return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
                except Exception:
                    pass

            # 4) 英文行手动提取年月日（回退方案），如：Fri Sep  5 18:12:42 CST 2025
            mon_map = {
                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
            }
            m2 = re.search(r"\b([A-Z][a-z]{2})\b\s+(\d{1,2})\b.*?(\d{4})", text)
            if m2 and m2.group(1) in mon_map:
                year = int(m2.group(3))
                month = mon_map[m2.group(1)]
                day = int(m2.group(2))
                try:
                    dt = datetime(year, month, day)
                    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                except Exception:
                    weekday_cn = ""
                return f"{year}年{month:02d}月{day:02d}日{weekday_cn}"

            # 5) 未识别，原样返回（保持兼容）
            return text
        except Exception:
            return str(raw_time) if raw_time else "未知时间"

    def _build_problems_table(self) -> str:
        """构建问题表格（表头+3个空行）"""
        table_content = """| NO | 问题描述 | 参考章节 | 建议解决时间 |
|---|---|---|---|
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |"""

        return table_content

    def _format_file_status_content(self, file_status_content: str) -> str:
        """格式化文件状态内容为markdown表格"""
        # 将文件状态内容按行分割并解析
        lines = file_status_content.split('\n')
        table_rows = []

        # 表头
        table_content = "| 状态 | 文件名 | 文件描述 |\n|---|---|---|\n"

        for line in lines:
            line = line.strip()
            if line and any(symbol in line for symbol in ['[✓]', '[✗]', '[○]', '[?]']):
                # 解析状态行格式：[✓] 文件名 文件描述
                match = re.match(r'\[(.)\]\s+(\S+)\s+(.+)', line)
                if match:
                    status_symbol = match.group(1)
                    filename = match.group(2)
                    description = match.group(3)
                    table_content += f"| {status_symbol} | {filename} | {description} |\n"

        return table_content

    def _build_system_background_section(self, db_info: Dict[str, Any],
                                       system_data: Optional[SystemInfoData],
                                       hardware_data: Optional[HardwareInfoData],
                                       database_config_data: Optional[DatabaseConfigData],
                                       meta_info: Dict[str, Any]) -> str:
        """构建系统背景部分"""

        # 格式化数据库模式显示
        db_model_display = db_info["dbmodel"].upper()
        if db_model_display == "ONE":
            db_model_display = "单机"

        # 获取所有hostname（用于集群显示）
        all_meta_info = db_info.get("metainfo", [])
        hostnames = [info.get("hostname", "-") for info in all_meta_info]
        hostname_display = ", ".join(set(hostnames))  # 去重并用逗号分隔

        # 构建系统硬件配置表格
        system_config_table = f"""| 选项参数名 | 选项参数值 | 说明 |
|---|---|---|
| SERVER_TYPE | X86数据库服务器 / Oracle ExaData 一体机 (二选一) | 服务器类型 |
| SERVER_NAME | {hostname_display} | 服务器主机名 |
| SERVER_ENVIRONMENT | Prod | 服务器环境类型 |
| SERVER_LOCATION | - | 服务器所在地 |
| SERVER_VENDOR | - | 服务器供应商 |
| SERVER_MODEL | - | 服务器型号 |"""

        if hardware_data:
            system_config_table += f"""
| CPU_MODEL | {hardware_data.cpu_model} | 处理器型号 |
| CPU_LOGICAL_CORES | {hardware_data.cpu_logical_cores} | 逻辑CPU核心数 |
| CPU_CORES_PER_CPU | {hardware_data.cpu_cores} | 每颗CPU核心数 |
| MEMORY_SIZE_GB | {hardware_data.memory_total_gb} | 物理内存大小 |
| DISK_CONFIGURATION | {hardware_data.disk_info} | 本地磁盘配置信息 |"""
        else:
            system_config_table += """
| CPU_MODEL | - | 处理器型号 |
| CPU_LOGICAL_CORES | - | 逻辑CPU核心数 |
| CPU_CORES_PER_CPU | - | 每颗CPU核心数 |
| MEMORY_SIZE_GB | - | 物理内存大小 |
| DISK_CONFIGURATION | - | 本地磁盘配置信息 |"""

        system_config_table += f"""
| DISK_REDUNDANCY_TYPE | - | 磁盘冗余类型 |
| SERVER_AVAILABILITY | 7x24 | 服务器可用性需求 |
| MAX_DOWNTIME | - | 最大可接受停机时间 |
| PARALLEL_SERVER_TYPE | {db_model_display} | 并行服务器类型 |"""

        if system_data:
            # RAC 模式下，若磁盘设备超过10个，则对 sd* 的 [deadline]/[mq-deadline] 分组进行区间压缩
            disk_scheduler_text = system_data.disk_scheduler
            if db_info.get("dbmodel", "").lower() == "rac":
                disk_scheduler_text = format_disk_scheduler_rac(disk_scheduler_text)
            system_config_table += f"""
| SYSTEM_VERSION | {system_data.system_version} | 操作系统版本信息 |
| KERNEL_VERSION | {system_data.kernel_version} | 操作系统内核版本 |
| KERNEL_PARAMETERS | {system_data.kernel_params.replace(chr(10), '<br>')} | 生效的内核参数 |
| RESOURCE_LIMITS | {system_data.resource_limits.replace(chr(10), '<br>')} | 资源限制参数 |
| DISK_SCHEDULER | {disk_scheduler_text.replace(chr(10), '<br>')} | 磁盘调度算法 |
| SYSTEM_UPTIME | {system_data.system_uptime.replace(',', ',<br>', 0)} | 系统启动时间和负载 |"""
        else:
            system_config_table += """
| SYSTEM_VERSION | - | 操作系统版本信息 |
| KERNEL_VERSION | - | 操作系统内核版本 |
| KERNEL_PARAMETERS | - | 生效的内核参数 |
| RESOURCE_LIMITS | - | 资源限制参数 |
| DISK_SCHEDULER | - | 磁盘调度算法 |
| SYSTEM_UPTIME | - | 系统启动时间和负载 |"""

        # 构建数据库配置表格
        db_config_section = self._build_database_config_section(database_config_data, db_info)

        return f"""
# 3. 系统背景

## 3.1. 系统硬件配置

{system_config_table}

{db_config_section}
"""

    def _build_database_config_section(self, database_config_data: Optional[DatabaseConfigData],
                                     db_info: Dict[str, Any]) -> str:
        """构建数据库配置部分"""

        # 客户信息模板
        customer_unit = MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"]
        customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]

        if database_config_data:
            # 判断是否是RAC环境（用于UNDOTBS2显示）
            is_rac = db_info.get("dbmodel", "").lower() == "rac"
            undotbs2_row = f"| UNDOTBS2 | {database_config_data.undotbs2_size} | 撤销表空间2大小 |" if is_rac else ""

            db_config_table = f"""**数据库基本信息：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| DB_OF_APP | {customer_unit}{customer_system} Oracle 数据库 | 数据库用途 |
| CURRENT_SESSION | {database_config_data.current_connections} | 当前活动连接数 |
| DB_SID | {database_config_data.instance_names.upper()} | Oracle实例标识 |
| DB_NAME | {database_config_data.db_name} | 数据库名称标识 |
| DB_UNIQUE_NAME | {database_config_data.db_unique_name.upper()} | 数据库唯一名称 |
| DATABASE_VERSION | {database_config_data.database_version} | Oracle数据库版本 |
| DATABASE_ROLE | {database_config_data.database_role} | 数据库角色 |
| OPEN_MODE | {database_config_data.open_mode} | 数据库打开模式 |
| HOST_NAME | {database_config_data.host_name} | 主机名称 |
| STARTUP_TIME | {database_config_data.startup_time} | 启动时间 |
| NLS_LANGUAGE | {database_config_data.nls_language} | 国际化语言 |
| NLS_TERRITORY | {database_config_data.nls_territory} | 国际化地区 |
| DATABASE_CHARSET | {database_config_data.database_charset} | 数据库字符编码 |
| DATABASE_NCHARSET | {database_config_data.database_nchar_charset} | 国家字符编码 |
| LOG_MODE | {database_config_data.log_mode} | 日志模式 |
| ARCHIVE_MODE | {database_config_data.archive_mode} | 归档模式 |
| CONTROL_FILE_COUNT | {database_config_data.control_file_count} | 控制文件数量 |
| LOG_MEMBERS_PER_GROUP | {database_config_data.log_members_per_group} | 日志组成员数 |
| ONLINE_LOGS_SAME_SIZE | {database_config_data.online_logs_same_size} | 在线日志文件大小一致性 |

**数据库使用空间：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| TOTAL_DATAFILE_SIZE_MB | {database_config_data.total_datafile_size_mb} | 数据文件总大小 |
| TOTAL_SEGMENT_SIZE_MB | {database_config_data.total_segment_size_mb} | 已使用的段空间 |
| DB_BLOCK SIZE | {database_config_data.db_block_size} | 数据块大小(字节) |
| TABLESPACE_COUNT | {database_config_data.tablespace_count} | 表空间总数 |
| DATAFILE_COUNT | {database_config_data.datafile_count} | 数据文件总数 |
| TEMP_TABLESPACE_SIZE | {database_config_data.temp_tablespace_size} | 临时表空间大小 |
| UNDO_TABLESPACE_SIZE | {database_config_data.undo_tablespace_size} | 撤销表空间大小 |{undotbs2_row}

**备份和容灾配置：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| DISASTER_RECOVERY_MODE | {database_config_data.disaster_recovery_mode} | Data Guard容灾状态 |
| RMAN_BACKUP_STATUS | {database_config_data.rman_backup_status} | RMAN备份配置状态 |

**日志配置：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| ALERT_LOG_PATH | {database_config_data.c1_alert_log_path} | 警告日志文件路径 |
| AUDIT_FILE_DEST_PATH | {database_config_data.audit_file_dest} | 审计文件存储路径 |
| CORE_DUMP_DEST_PATH | {database_config_data.core_dump_dest} | 核心转储文件路径 |
| DIAGNOSTIC_DEST_PATH | {database_config_data.diagnostic_dest} | 诊断文件根路径 |
| USER_DUMP_DEST_PATH | {database_config_data.user_dump_dest} | 用户转储文件路径 |

"""


        else:
            db_config_table = f"""**数据库基本信息：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| 数据库名称 | {customer_unit}{customer_system} Oracle 数据库 | 数据库用途 |
| 实例名称 | - | Oracle实例标识 |
| 数据库版本 | - | Oracle数据库版本 |
| DB_NAME | - | 数据库名称标识 |
| DB_UNIQUE_NAME | - | 数据库唯一名称 |
| DATABASE_ROLE | - | 数据库角色 |
| OPEN_MODE | - | 数据库打开模式 |
| HOST_NAME | - | 主机名称 |
| STARTUP_TIME | - | 启动时间 |
| NLS_LANGUAGE | - | 国际化语言 |
| NLS_TERRITORY | - | 国际化地区 |
| 数据库字符集 | - | 数据库字符编码 |
| 数据库国家字符集 | - | 国家字符编码 |
| LOG_MODE | - | 日志模式 |
| ARCHIVE_MODE | - | 归档模式 |
| 当前数据库连接数 | - | 当前活动连接数 |

**数据库使用空间：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| 所有数据文件大小(MB) | - | 数据文件总大小 |
| 所有 SEGMENT 大小(MB) | - | 已使用的段空间 |
| DB_BLOCK SIZE | - | 数据块大小(字节) |
| 表空间数目 | - | 表空间总数 |
| 数据文件数目 | - | 数据文件总数 |
| 临时表空间大小 | - | 临时表空间大小 |
| Undo表空间大小 | - | 撤销表空间大小 |

**日志配置：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| 控制文件数目 | - | 控制文件数量 |
| 是否所有的在线日志都是同样大小 | - | 在线日志文件大小一致性 |
| 每组在线日志的成员数 | - | 日志组成员数 |
| ALERT_LOG路径 | - | 警告日志文件路径 |
| AUDIT_FILE_DEST路径 | - | 审计文件存储路径 |
| CORE_DUMP_DEST路径 | - | 核心转储文件路径 |
| DIAGNOSTIC_DEST路径 | - | 诊断文件根路径 |
| USER_DUMP_DEST路径 | - | 用户转储文件路径 |

**备份和容灾配置：**

| 配置项 | 配置值 | 说明 |
|---|---|---|
| 现有灾备方式 | - | Data Guard容灾状态 |
| 是否配置 RMAN 备份 | - | RMAN备份配置状态 |"""

        return f"""## 3.2. 数据库配置

{db_config_table}"""

    def _build_resource_config_section(self, resource_config_data: Optional[ResourceConfigData]) -> str:
        """构建3.3数据库资源相关配置表格"""
        if resource_config_data:
            resource_config_table = f"""**服务器硬件资源：**

| 资源类型 | 配置值 | 说明 |
|---|---|---|
| SERVER_LOGICAL_CORES | {resource_config_data.server_logical_cores} | 服务器逻辑CPU核心数 |
| SERVER_MEM_SIZE_GB | {resource_config_data.server_mem_size_gb} | 服务器物理内存大小 |

**数据库实例配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| CPU_COUNT | {resource_config_data.db_cpu_count} | 数据库可使用的CPU核心数 |
| PROCESSES | {resource_config_data.db_processes} | 数据库实例最大进程数 |
| SESSIONS | {resource_config_data.db_sessions} | 数据库实例最大会话数 |
| TRANSACTIONS | {resource_config_data.db_transactions} | 数据库实例最大事务数 |

**并行执行配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| PARALLEL_MAX_SERVERS | {resource_config_data.db_parallel_max_servers} | 并行执行的最大服务器进程数 |
| PARALLEL_MIN_SERVERS | {resource_config_data.db_parallel_min_servers} | 并行执行的最小服务器进程数 |

**内存配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| SGA_SIZE(GB) | {resource_config_data.db_sga_size_gb} | 系统全局区域内存大小 |
| PGA_SIZE(GB) | {resource_config_data.db_pga_size_gb} | 程序全局区域内存目标大小 |
| LOG_BUFFER(MB) | {resource_config_data.db_log_buffer_mb} | 重做日志缓冲区大小 |

**游标配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| OPEN_CURSORS | {resource_config_data.db_open_cursors} | 每个会话最大打开游标数 |
| SESSION_CACHED_CURSORS | {resource_config_data.db_session_cached_cursors} | 每个会话缓存游标数 |"""
        else:
            resource_config_table = f"""**服务器硬件资源：**

| 资源类型 | 配置值 | 说明 |
|---|---|---|
| 逻辑CPU核心数 | - | 服务器逻辑CPU核心数 |
| 物理内存大小(GB) | - | 服务器物理内存大小 |

**数据库实例配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| CPU_COUNT | - | 数据库可使用的CPU核心数 |
| PROCESSES | - | 数据库实例最大进程数 |
| SESSIONS | - | 数据库实例最大会话数 |
| TRANSACTIONS | - | 数据库实例最大事务数 |

**并行执行配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| PARALLEL_MAX_SERVERS | - | 并行执行的最大服务器进程数 |
| PARALLEL_MIN_SERVERS | - | 并行执行的最小服务器进程数 |

**内存配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| SGA_SIZE(GB) | - | 系统全局区域内存大小 |
| PGA_SIZE(GB) | - | 程序全局区域内存目标大小 |
| LOG_BUFFER(MB) | - | 重做日志缓冲区大小 |

**游标配置：**

| 参数名称 | 配置值 | 参数说明 |
|---|---|---|
| OPEN_CURSORS | - | 每个会话最大打开游标数 |
| SESSION_CACHED_CURSORS | - | 每个会话缓存游标数 |"""

        return f"""## 3.3. 数据库资源相关配置

{resource_config_table}"""

    def _build_database_config_check_section(self, rman_data: Optional[RmanInfoData],
                                           dg_data: Optional[DataGuardInfoData],
                                           adrci_data: Optional[AdrciInfoData],
                                           alert_data: Optional[AlertLogData]) -> str:
        """构建第4章数据库配置检查部分"""

        customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]

        # 4.1 RMAN备份信息（合并4.1、4.2、4.3的内容）
        rman_strategy_section = f"""## 5.1.RMAN 备份信息

 **{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} Oracle 数据库 RMAN 备份策略如下：**

```
{rman_data.backup_strategy if rman_data and rman_data.backup_strategy else "未找到 RMAN 备份策略信息"}
```

**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} Oracle 数据库 RMAN 备份集路径如下：**

```
{MarkdownGenerator._limit_rman_content_lines(rman_data.backup_details) if rman_data and rman_data.backup_details else MarkdownConfig.RMAN_DISPLAY_CONFIG["default_backup_details_message"]}
```

**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} Oracle 数据库 RMAN 备份集合明细如下：**

```
{MarkdownGenerator._limit_rman_content_lines(rman_data.backup_sets) if rman_data and rman_data.backup_sets else MarkdownConfig.RMAN_DISPLAY_CONFIG["default_backup_sets_message"]}
```

目前存在 {rman_data.backup_count if rman_data and rman_data.backup_count else 0} 份 RMAN 备份集（可用：{rman_data.available_count if rman_data else 0}、过期：{rman_data.expired_count if rman_data else 0}、FULL：{rman_data.full_count if rman_data else 0}、INC1：{rman_data.incremental_count if rman_data else 0}）。

综合结论：【请填写结论】

"""

        # 4.2和4.3章节内容已合并到4.1，这里设为空字符串（删除标题）
        rman_details_section = ""
        rman_sets_section = ""

        # 4.2 Data Guard容灾
        dg_section = ""
        if dg_data:
            dg_section = f"""## 5.2. 数据库 Data Guard 容灾

**Data Guard 基本配置检查：** 

{self._format_as_table(dg_data.basic_config_check) if dg_data.basic_config_check else "未找到Data Guard基本配置检查信息"}

**归档传输目的地配置 (Archive Destination Configuration)：**

{self._format_as_table(dg_data.archive_dest_config) if dg_data.archive_dest_config else "未找到归档传输目的地配置信息"}

**Data Guard 相关参数：**

{self._format_as_table(dg_data.dg_related_params) if dg_data.dg_related_params else "未找到Data Guard相关参数信息"}

**Data Guard 状态消息 (最近50条)：**

{self._format_as_table(dg_data.dg_status_messages) if dg_data.dg_status_messages else "未找到Data Guard状态消息信息"}

**传输/应用延迟统计：**

{self._format_as_table(dg_data.transport_apply_lag) if dg_data.transport_apply_lag else "未找到传输/应用延迟统计信息"}

**归档日志应用状态 (仅Standby数据库)：**

{self._format_as_table(dg_data.archive_log_apply) if dg_data.archive_log_apply else "未找到归档日志应用状态信息"}

**MRP进程状态 (仅Standby数据库)：**

{self._format_as_table(dg_data.mrp_process_status) if dg_data.mrp_process_status else "未找到MRP进程状态信息"}

**综合结论：【请填写结论】**

"""
        else:
            dg_section = f"""## 5.2. 数据库 Data Guard 容灾

未找到Data Guard相关信息

综合结论：【请填写结论】

"""

        # 4.3 ADRCI、ALERT 日志检查（合并原4.3和4.4）
        adrci_alert_section = ""
        
        # ADRCI内容
        adrci_content = ""
        if adrci_data and adrci_data.adrci_content:
            adrci_content = f"""**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} ADRCI 诊断工具日志检查：**

```
{adrci_data.adrci_content}
```

"""
        else:
            adrci_content = f"""**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} ADRCI 诊断工具日志检查：**

```
未找到ADRCI诊断信息
```

"""

        # ALERT内容
        alert_content = ""
        if alert_data and alert_data.alert_summary:
            # 构建详细错误列表
            error_details = self._build_alert_error_details(alert_data) if alert_data.grouped_errors else ""
            alert_content = f"""**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} ALERT日志检查**：


```
{alert_data.alert_summary}
```

{error_details}

"""
        else:
            alert_content = f"""**{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} ALERT日志检查**

ALERT_LOG 路径：-

```
未找到ALERT日志信息
```

"""

        adrci_alert_section = f"""## 5.3. ADRCI、ALERT 日志检查

{adrci_content}

{alert_content}

综合结论：【请填写结论】

"""

        return f"""
# 5. 数据库配置检查

{rman_strategy_section}{rman_details_section}{rman_sets_section}{dg_section}{adrci_alert_section}"""

    def _build_control_file_log_section(self, control_file_log_data: Optional[ControlFileLogData]) -> str:
        """构建4.4控制文件和在线日志文件章节"""
        if control_file_log_data:
            return f"""## 5.4. 控制文件和在线日志文件

**数据库控制文件信息如下：**

{control_file_log_data.control_file_info}



{control_file_log_data.online_log_info}

综合结论：【留空给工程师写结论】

"""
        else:
            return f"""## 5.4. 控制文件和在线日志文件

**数据库控制文件信息如下：**

未找到控制文件信息

**数据库控在线日志信息如下：**

未找到在线日志信息

综合结论：【留空给工程师写结论】

"""

    def _build_tablespace_file_section(self, tablespace_file_data: Optional[TablespaceFileData], archive_stat_data: Optional[ArchiveStatData]) -> str:
        """构建4.5表空间数据文件、归档文件明细章节（合并了原4.7归档统计）"""
        if tablespace_file_data:
            tablespace_section = f"""**数据文件列表信息：**

{tablespace_file_data.datafile_list}

**表空间基本信息：**

{tablespace_file_data.tablespace_basic_info}

**数据库使用率超过85％的表空间如下：**

{tablespace_file_data.high_usage_tablespaces}

**未开启文件自动扩展的表空间文件：**

{tablespace_file_data.no_autoextend_files}

"""
        else:
            tablespace_section = f"""**数据文件列表信息：**

**未找到数据文件列表信息**

**表空间基本信息：**

**未找到表空间基本信息**

**数据库使用率超过85％的表空间如下：**

**未找到使用率超过85%的表空间**

**未开启文件自动扩展的表空间文件：**

**未找到未开启自动扩展的文件**

"""

        # 构建归档统计部分
        if archive_stat_data:
            archive_section = f"""**归档统计信息：**

{archive_stat_data.archive_statistics}

"""
        else:
            archive_section = f"""**归档统计信息：**

未找到归档统计信息

"""

        # 合并两个部分
        return f"""## 5.5. 表空间数据文件、归档文件明细

{tablespace_section}{archive_section}综合结论：【留空给工程师写结论】

"""


    def _build_asm_disk_section(self, asm_disk_data: Optional[AsmDiskData]) -> str:
        """构建4.6 ASM磁盘详细信息章节"""
        if asm_disk_data:
            return f"""## 5.6. ASM 磁盘信息

{asm_disk_data.asm_disk_detail}

综合结论：【留空给工程师写结论】

"""
        else:
            return f"""## 5.6. ASM磁盘详细信息

未找到ASM磁盘详细信息

综合结论：【留空给工程师写结论】
"""

    def _build_plsql_virus_section(self, plsql_virus_data: Optional[PlsqlVirusData]) -> str:
        """构建4.7 PL/SQLDeveloper破解版勒索病毒检查章节"""
        if plsql_virus_data:
            return f"""## 5.7. PL/SQLDeveloper破解版勒索病毒检查

```
{plsql_virus_data.virus_check_info}
```
综合结论：【留空给工程师写结论】
"""
        else:
            return f"""## 5.7. PL/SQLDeveloper破解版勒索病毒检查

```
未找到PL/SQLDeveloper病毒检查信息
```
综合结论：【留空给工程师写结论】

"""

    def _build_alert_error_details(self, alert_data: AlertLogData) -> str:
        """构建Alert日志错误详情表格 - 按时间戳分组显示"""
        if not alert_data or not alert_data.grouped_errors:
            return ""

        details_parts = []
        total_errors = sum(len(errors) for errors in alert_data.grouped_errors.values())
        
        if total_errors == 0:
            return ""

        # 详细错误列表
       # details_parts.append("\n**详细 ORA 错误信息**\n")
        
        # 收集所有错误并按时间排序（最新的在前）
        all_errors_with_time = []
        for timestamp, errors in alert_data.grouped_errors.items():
            for error in errors:
                all_errors_with_time.append((timestamp, error))
        
        # 按时间戳排序（日期解析排序，最新的在前）
        def parse_timestamp(timestamp_str):
            """解析时间戳字符串为可排序的对象"""
            import datetime
            try:
                # Oracle时间戳格式：Wed Dec 25 13:16:03 2024
                return datetime.datetime.strptime(timestamp_str, '%a %b %d %H:%M:%S %Y')
            except:
                try:
                    # 其他格式的尝试
                    return datetime.datetime.strptime(timestamp_str, '%a %b  %d %H:%M:%S %Y')
                except:
                    # 如果解析失败，返回一个很早的时间
                    return datetime.datetime(1900, 1, 1)
        
        all_errors_with_time.sort(key=lambda x: parse_timestamp(x[0]), reverse=True)
        
        details_parts.append("| 时间戳 | ORA代码 | 错误消息 |")
        details_parts.append("|--------|---------|----------|")
        
        # 只显示前30个错误，避免表格过长
        for timestamp, error in all_errors_with_time[:30]:
            ora_code = error.get('error_code', 'ORA-未知')
            message = error.get('error_message', '').replace('|', '\\|')
            message = self._clean_garbled_text(message)
            # 截断过长的错误消息
            if len(message) > 80:
                message = message[:80] + "..."
                
            details_parts.append(f"| {timestamp} | {ora_code} | {message} |")

        if len(all_errors_with_time) > 30:
            details_parts.append(f"\n*注: 仅显示最近30个错误，总共发现{len(all_errors_with_time)}个错误*\n")

        return '\n'.join(details_parts)

    def _clean_garbled_text(self, text: str) -> str:
        """简单清理常见乱码片段；若仍包含大量不可识别字符，返回精简后的文本"""
        if not text:
            return text
        tokens = ['�', '��', 'δѡ', 'С�']
        for t in tokens:
            text = text.replace(t, '')
        # 收敛多空格
        text = ' '.join(text.split())
        return text.strip()

    def _build_alert_error_summary(self, alert_data: AlertLogData) -> str:
        """构建Alert日志错误总结"""
        if not alert_data:
            return ""

        summary_parts = []

        # 统计各级别错误数量
        critical_count = len(alert_data.critical_errors)
        high_count = len(alert_data.high_errors)
        medium_count = len(alert_data.medium_errors)

        if critical_count > 0:
            summary_parts.append(f"🔴 **严重级别错误**: {critical_count} 个")
            # 显示前3个严重错误的简要信息
            for i, error in enumerate(alert_data.critical_errors[:3]):
                summary_parts.append(f"  - {error.get('ora_code', 'ORA-XXXXX')}: {error.get('rule_name', '未知错误')} ({error.get('timestamp', '未知时间')})")

        if high_count > 0:
            summary_parts.append(f"🟡 **高级别错误**: {high_count} 个")
            # 显示前2个高级别错误的简要信息
            for i, error in enumerate(alert_data.high_errors[:2]):
                summary_parts.append(f"  - {error.get('ora_code', 'ORA-XXXXX')}: {error.get('rule_name', '未知错误')} ({error.get('timestamp', '未知时间')})")

        if medium_count > 0:
            summary_parts.append(f"🔵 **中级别错误**: {medium_count} 个")

        if not summary_parts:
            return "**日志分析结果**: 未发现严重系统错误。"

        return "\n".join(summary_parts)

    def _format_as_table(self, content: str) -> str:
        """
        将Oracle查询结果文本格式化为Markdown表格
        处理跨行数据和多列格式
        
        Args:
            content: 原始文本内容
            
        Returns:
            str: Markdown表格格式的字符串
        """
        if not content or not content.strip():
            return ""
            
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return content  # 如果内容不够构成表格，直接返回原内容
            
        # 找到表头行和分隔线行
        header_line = None
        separator_line = None
        data_start_index = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # 检查是否是分隔线（主要由-组成）
            if line.replace('-', '').replace(' ', '') == '':
                if header_line is not None:
                    separator_line = line
                    data_start_index = i + 1
                    break
            else:
                if header_line is None:
                    header_line = line
        
        if not header_line or not separator_line:
            return content  # 无法识别表格结构
            
        # 基于分隔线检测列位置（更精确的方法）
        columns = self._detect_columns_from_separator(separator_line)
        
        
        if len(columns) < 2:
            return content  # 至少需要2列才能构成表格
            
        # 构建Markdown表格
        table_lines = []
        
        # 处理表头
        header_cells = self._extract_table_cells(header_line, columns)
        table_lines.append("| " + " | ".join(header_cells) + " |")
        
        # 添加表格分隔符
        separator = "|" + "|".join([" --- " for _ in header_cells]) + "|"
        table_lines.append(separator)
        
        # 处理数据行（合并跨行数据）
        current_row_data = None
        
        for i in range(data_start_index, len(lines)):
            line = lines[i].rstrip()  # 只去掉右侧空格，保留左侧对齐空格
            if not line.strip():  # 检查是否为空行时才strip
                continue
                
            # 提取当前行的单元格数据
            cells = self._extract_table_cells(line, columns)
            
            
            # 检查是否是新行的开始（第一列有数据）
            if cells[0].strip():
                # 如果有未完成的行，先输出它
                if current_row_data is not None:
                    if any(cell.strip() for cell in current_row_data):
                        table_lines.append("| " + " | ".join(current_row_data) + " |")
                
                # 开始新行
                current_row_data = cells[:]
            else:
                # 这是跨行数据，合并到当前行
                if current_row_data is not None:
                    for j in range(len(cells)):
                        if cells[j].strip():
                            if current_row_data[j].strip():
                                current_row_data[j] += " " + cells[j].strip()
                            else:
                                current_row_data[j] = cells[j].strip()
        
        # 输出最后一行数据
        if current_row_data is not None:
            if any(cell.strip() for cell in current_row_data):
                table_lines.append("| " + " | ".join(current_row_data) + " |")
        
        return "\n".join(table_lines)
    
    def _detect_table_columns(self, header_line: str) -> list:
        """
        检测表格列的位置
        
        Args:
            header_line: 表头行
            
        Returns:
            list: 列的起始位置列表
        """
        columns = [0]  # 第一列总是从位置0开始
        
        # 找到每个单词的结束位置，作为潜在的列分隔点
        words = []
        current_word = ""
        start_pos = 0
        
        i = 0
        while i < len(header_line):
            if header_line[i] != ' ':
                if not current_word:  # 新单词开始
                    start_pos = i
                current_word += header_line[i]
            else:
                if current_word:  # 单词结束
                    words.append((start_pos, i, current_word))
                    current_word = ""
            i += 1
        
        # 最后一个单词
        if current_word:
            words.append((start_pos, len(header_line), current_word))
        
        # 基于单词间距检测列分隔
        for i in range(1, len(words)):
            prev_end = words[i-1][1]
            curr_start = words[i][0]
            
            # 如果间距大于2个空格，认为是新列
            if curr_start - prev_end >= 2:
                columns.append(curr_start)
        
        return columns
    
    def _detect_columns_from_separator(self, separator_line: str) -> list:
        """
        基于分隔线检测表格列的位置（更精确的方法）
        
        Args:
            separator_line: 分隔线（主要由-和空格组成）
            
        Returns:
            list: 列的起始位置列表
        """
        columns = [0]  # 第一列总是从位置0开始
        
        # 找到每个-段落，段落之间的空格分隔标识新列开始
        i = 0
        while i < len(separator_line):
            if separator_line[i] == '-':
                # 跳过当前-段落
                while i < len(separator_line) and separator_line[i] == '-':
                    i += 1
                # 跳过段落后的空格
                while i < len(separator_line) and separator_line[i] == ' ':
                    i += 1
                # 如果还有内容（下一个-段落），记录新列位置
                if i < len(separator_line):
                    columns.append(i)
            else:
                i += 1
        
        return columns
    
    def _extract_table_cells(self, line: str, columns: list) -> list:
        """
        根据列位置提取表格单元格内容
        
        Args:
            line: 数据行
            columns: 列位置列表
            
        Returns:
            list: 单元格内容列表
        """
        cells = []
        
        for i in range(len(columns)):
            start = columns[i]
            end = columns[i + 1] if i + 1 < len(columns) else len(line)
            
            cell_content = line[start:end].strip() if start < len(line) else ""
            # 清理单元格内容中的多余空格
            cell_content = " ".join(cell_content.split())
            cells.append(cell_content)
        
        return cells

    def _save_markdown_file(self, output_path: Path, content: str) -> bool:
        """保存markdown文件"""
        try:
            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Markdown文件已保存到: {output_path}")
            return True

        except Exception as e:
            logger.error(f"保存markdown文件失败 {output_path}: {e}")
            return False

    def _build_os_check_section(self, os_performance_data: Optional[OsPerformanceData],
                               disk_space_data: Optional[DiskSpaceData], output_dir: Path, sid: str) -> str:
        """构建第4章操作系统检查部分"""
        
        # 获取主机名，优先从性能数据获取
        hostname = ""
        if os_performance_data and os_performance_data.hostname:
            hostname = os_performance_data.hostname
        elif disk_space_data:
            hostname = "系统主机"  # 从硬件信息获取的备用
        
        # 构建4.1 CPU使用率章节
        cpu_section = self._build_cpu_usage_section(os_performance_data, hostname, output_dir, sid)
        
        # 构建4.2 内存使用率章节
        memory_section = self._build_memory_usage_section(os_performance_data, hostname, output_dir, sid)
        
        # 构建4.3 磁盘IO使用率章节
        disk_io_section = self._build_disk_io_usage_section(os_performance_data, hostname, output_dir, sid)
        
        # 构建4.4 磁盘空间使用率章节
        disk_space_section = self._build_disk_space_usage_section(disk_space_data, hostname)
        
        os_check_content = f"""# 4. 操作系统检查

以下的部分是对操作系统的检查，可以从中确定一些性能方面的问题。这个分析主要使用的是操作系统自带的命令和工具。\n
主要从以下方面来检查操作系统的性能：\n
- CPU 利用率
- 内存利用率
- 磁盘IO使用率
- 磁盘空间使用率\n
 (这部分的检查并不是针对操作系统或硬件的全面深入的检查，如有上述要求请与操作系统厂商联系)

{cpu_section}

{memory_section}

{disk_io_section}

{disk_space_section}

综合结论：【请填写结论】
"""
        
        return os_check_content

    def _build_cpu_usage_section(self, os_performance_data: Optional[OsPerformanceData], hostname: str, output_dir: Path, sid: str) -> str:
        """构建4.1 CPU使用率章节"""
        if not os_performance_data or not os_performance_data.cpu_data:
            return """## 4.1.CPU使用率

未找到CPU使用率数据"""
            
        # 将CPU数据转换为图表格式
        cpu_chart = self._generate_cpu_chart(os_performance_data.cpu_data, output_dir, hostname, sid)
        
        return f"""## 4.1.CPU使用率

**以下是**计算节点 {hostname} **的CPU使用情况：**

{cpu_chart}"""

    def _build_memory_usage_section(self, os_performance_data: Optional[OsPerformanceData], hostname: str, output_dir: Path, sid: str) -> str:
        """构建4.2 内存使用率章节"""
        if not os_performance_data or not os_performance_data.memory_data:
            return """## 4.2.内存使用率

未找到内存使用率数据"""
            
        # 将内存数据转换为图表格式
        memory_chart = self._generate_memory_chart(os_performance_data.memory_data, output_dir, hostname, sid)
        
        return f"""## 4.2.内存使用率

**以下是**计算节点 {hostname} **的内存使用情况：**

{memory_chart}"""

    def _build_disk_io_usage_section(self, os_performance_data: Optional[OsPerformanceData], hostname: str, output_dir: Path, sid: str) -> str:
        """构建4.3 磁盘IO使用率章节"""
        if not os_performance_data or not os_performance_data.disk_io_data:
            return """## 4.3.磁盘IO使用率

未找到磁盘IO使用率数据"""
            
        # 将磁盘IO数据转换为图表格式
        disk_io_chart = self._generate_disk_io_chart(os_performance_data.disk_io_data, output_dir, hostname, sid)
        
        return f"""## 4.3.磁盘IO使用率

**以下是**计算节点 {hostname} **的磁盘IO使用率：**

{disk_io_chart}"""

    def _build_disk_space_usage_section(self, disk_space_data: Optional[DiskSpaceData], hostname: str) -> str:
        """构建4.4 磁盘空间使用率章节"""
        if not disk_space_data or not disk_space_data.disk_space_info:
            return """## 4.4.磁盘空间使用率

未找到磁盘空间使用率数据"""
            
        # 将磁盘空间数据转换为表格格式
        disk_space_table = self._generate_disk_space_table(disk_space_data.disk_space_info)
        
        return f"""## 4.4.磁盘空间使用率

**以下是**计算节点 {hostname} **的磁盘空间使用率：**

{disk_space_table}"""

    def _prepare_matplotlib(self, base_dir: Path) -> None:
        try:
            mpl_config_dir = base_dir / "mplconfig"
            mpl_config_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))
        except Exception as exc:
            logger.warning(f"设置Matplotlib配置目录失败: {exc}")
        try:
            plt.switch_backend("Agg")
        except Exception:
            pass

    def _generate_cpu_chart(self, cpu_data: str, output_dir: Path, hostname: str, sid: str) -> str:
        lines = cpu_data.strip().split('\n')
        chart_data = []

        for line in lines:
            is_chinese_format = '时' in line and 'all' in line and 'CPU' not in line and '平均时间' not in line
            is_english_format = ('AM' in line or 'PM' in line) and 'all' in line and 'CPU' not in line and 'Average' not in line

            if is_chinese_format or is_english_format:
                parts = line.split()
                try:
                    if is_english_format and len(parts) >= 9:
                        time_str = parts[0]
                        user = float(parts[3])
                        nice = float(parts[4])
                        system = float(parts[5])
                        iowait = float(parts[6])
                        steal = float(parts[7])
                        idle = float(parts[8])
                    elif is_chinese_format and len(parts) >= 8:
                        time_str = parts[0]
                        user = float(parts[2])
                        nice = float(parts[3])
                        system = float(parts[4])
                        iowait = float(parts[5])
                        steal = float(parts[6])
                        idle = float(parts[7])
                    else:
                        continue

                    if is_chinese_format:
                        time_display = normalize_time_label(time_str)
                    else:
                        time_display = normalize_time_label(time_str)

                    chart_data.append((time_display, user, nice, system, iowait, steal, idle))
                except (ValueError, IndexError):
                    continue

        if not chart_data:
            return f"```text\n{cpu_data}\n```"

        self._prepare_matplotlib(output_dir)
        server_picture_dir = output_dir / "server_picture"
        server_picture_dir.mkdir(exist_ok=True)

        chart_filename = "cpu_usage_chart.png"
        chart_path = server_picture_dir / chart_filename

        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=(12, 6))

        times = [data[0] for data in chart_data]
        user_data = [data[1] for data in chart_data]
        nice_data = [data[2] for data in chart_data]
        system_data = [data[3] for data in chart_data]
        iowait_data = [data[4] for data in chart_data]
        steal_data = [data[5] for data in chart_data]
        idle_data = [data[6] for data in chart_data]

        ax.plot(times, user_data, 'r-', linewidth=2, label='%user (用户CPU使用率)', marker='o', markersize=4)
        ax.plot(times, system_data, 'orange', linestyle='-', linewidth=2, label='%system (系统CPU使用率)', marker='s', markersize=4)
        ax.plot(times, iowait_data, 'b-', linewidth=2, label='%iowait (IO等待时间)', marker='^', markersize=4)
        ax.plot(times, nice_data, 'purple', linestyle='--', linewidth=1.5, label='%nice', alpha=0.7)
        ax.plot(times, steal_data, 'brown', linestyle='--', linewidth=1.5, label='%steal', alpha=0.7)
        ax.plot(times, idle_data, 'g--', linewidth=1.5, label='%idle (空闲时间)', alpha=0.7)

        ax.set_title(f'CPU使用率趋势图 (8:00-12:00) - {hostname}', fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('时间', fontsize=12)
        ax.set_ylabel('使用率 (%)', fontsize=12)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

        # CPU 图保留默认行为（已较清晰）；无 twinx 对齐需求
        plt.xticks(rotation=45)
        plt.tight_layout()

        try:
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(f"CPU图表已保存到: {chart_path}")
            return f"![CPU使用率趋势图](./server_picture/{chart_filename})"
        except Exception as exc:
            logger.error(f"保存CPU图表失败: {exc}")
            plt.close()
            return f"```text\n{cpu_data}\n```"

    def _generate_memory_chart(self, memory_data: str, output_dir: Path, hostname: str, sid: str) -> str:
        lines = memory_data.strip().split('\n')
        chart_data = []

        for line in lines:
            is_chinese_format = '时' in line and 'kbmemfree' not in line and '平均时间' not in line
            is_english_format = ('AM' in line or 'PM' in line) and 'kbmemfree' not in line and 'Average' not in line

            if is_chinese_format or is_english_format:
                parts = line.split()
                try:
                    # 自适应字段解析：支持不同版本的SAR输出格式
                    # Linux 6.x 通常有8个字段，Linux 7.x/8.x 有11个或更多字段
                    min_fields_chinese = 8  # 最小字段数（中文格式）
                    min_fields_english = 9  # 最小字段数（英文格式）

                    if is_english_format and len(parts) >= min_fields_english:
                        time_str = parts[0]
                        values = parts[2:]
                    elif is_chinese_format and len(parts) >= min_fields_chinese:
                        time_str = parts[0]
                        values = parts[1:]
                    else:
                        continue

                    # 记录字段数用于调试
                    field_count = len(values)
                    if field_count < 10:
                        logger.debug(f"内存数据字段数较少({field_count}个)，可能是旧版本Linux系统")

                    def safe_int(idx: int) -> Optional[int]:
                        try:
                            return int(values[idx])
                        except (ValueError, IndexError):
                            return None

                    def safe_float(idx: int) -> Optional[float]:
                        try:
                            return float(values[idx])
                        except (ValueError, IndexError):
                            return None

                    # 基础字段（所有版本都有）
                    kbmemfree = safe_int(0)
                    kbmemused = safe_int(1)
                    memused_pct = safe_float(2)
                    kbbuffers = safe_int(3)
                    kbcached = safe_int(4)
                    kbcommit = safe_int(5)
                    commit_pct = safe_float(6)

                    # 扩展字段（新版本才有，旧版本返回None）
                    kbactive = safe_int(7)  # 可能不存在
                    kbinact = safe_int(8)   # 可能不存在
                    kbdirty = safe_int(9)   # 可能不存在

                    if is_chinese_format:
                        time_display = normalize_time_label(time_str)
                    else:
                        time_display = normalize_time_label(time_str)

                    chart_data.append((time_display, kbmemfree, kbmemused, memused_pct, kbbuffers, kbcached, kbcommit, commit_pct, kbactive, kbinact, kbdirty))
                except (ValueError, IndexError):
                    continue

        if not chart_data:
            return f"```text\n{memory_data}\n```"

        self._prepare_matplotlib(output_dir)
        server_picture_dir = output_dir / 'server_picture'
        server_picture_dir.mkdir(exist_ok=True)

        chart_filename = 'memory_usage_chart.png'
        chart_path = server_picture_dir / chart_filename

        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax1 = plt.subplots(figsize=(12, 6))

        times = [data[0] for data in chart_data]
        memused_pct_data = [data[3] if data[3] is not None else math.nan for data in chart_data]
        commit_pct_data = [data[7] if data[7] is not None else math.nan for data in chart_data]

        def kb_to_gb(value: Optional[int]) -> float:
            return math.nan if value is None else value / (1024 ** 2)

        kbmemfree_data = [kb_to_gb(data[1]) for data in chart_data]
        kbmemused_data = [kb_to_gb(data[2]) for data in chart_data]
        kbbuffers_data = [kb_to_gb(data[4]) for data in chart_data]
        kbcached_data = [kb_to_gb(data[5]) for data in chart_data]
        kbcommit_data = [kb_to_gb(data[6]) for data in chart_data]
        kbactive_data = [kb_to_gb(data[8]) for data in chart_data]
        kbinact_data = [kb_to_gb(data[9]) for data in chart_data]
        kbdirty_data = [kb_to_gb(data[10]) for data in chart_data]

        # 基于索引绘图，统一横轴抽稀与旋转
        # 展示全部时间标签（不再抽稀）
        x, _ = apply_time_axis(ax1, [normalize_time_label(t) for t in times], max_labels=None, rotation=45, fontsize=10)
        ax1.plot(x, memused_pct_data, 'r-', linewidth=2, label='内存使用率 (%)', marker='o', markersize=4)
        ax1.plot(x, commit_pct_data, 'orange', linestyle='-', linewidth=2, label='Commit 使用率 (%)', marker='s', markersize=4)
        ax1.set_ylabel('使用率 (%)', fontsize=12)
        ax1.set_ylim(0, 100)
        ax1.tick_params(axis='y')

        ax2 = ax1.twinx()
        ax2.plot(x, kbmemused_data, 'b-', linewidth=1.5, label='已用内存 (GB)', marker='^', markersize=4)
        ax2.plot(x, kbmemfree_data, 'g-', linewidth=1.5, label='可用内存 (GB)', marker='v', markersize=4)
        ax2.plot(x, kbcached_data, color='#9467bd', linestyle='--', linewidth=1.2, label='缓存 (GB)', alpha=0.7)
        ax2.plot(x, kbbuffers_data, color='#8c564b', linestyle='--', linewidth=1.2, label='缓冲 (GB)', alpha=0.7)
        ax2.plot(x, kbcommit_data, color='#ff9896', linestyle='-.', linewidth=1.2, label='Commit 内存 (GB)', alpha=0.7)

        # 只有数据存在时才绘制扩展字段
        # 检查是否有有效的扩展数据（非None且非全NaN）
        has_active = any(data[8] is not None for data in chart_data)
        has_inact = any(data[9] is not None for data in chart_data)
        has_dirty = any(data[10] is not None for data in chart_data)

        if has_active:
            ax2.plot(times, kbactive_data, color='#17becf', linestyle='-.', linewidth=1.2, label='活跃内存 (GB)', alpha=0.7)
        if has_inact:
            ax2.plot(times, kbinact_data, color='#bcbd22', linestyle='-.', linewidth=1.2, label='非活跃内存 (GB)', alpha=0.7)
        if has_dirty:
            ax2.plot(times, kbdirty_data, color='#7f7f7f', linestyle=':', linewidth=1.2, label='脏页 (GB)', alpha=0.7)

        ax2.set_ylabel('内存 (GB)', fontsize=12)
        ax2.tick_params(axis='y')

        ax1.set_title(f'内存使用率趋势图 (8:00-12:00) - {hostname}', fontsize=14, fontweight='bold', pad=20)
        ax1.set_xlabel('时间', fontsize=12)
        ax1.grid(True, alpha=0.3)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, bbox_to_anchor=(1.05, 1), loc='upper left')
        align_twinx_xlim(ax1, ax2)
        plt.tight_layout()

        try:
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(f'内存图表已保存到: {chart_path}')
            return f"![内存使用率趋势图](./server_picture/{chart_filename})"
        except Exception as exc:
            logger.error(f'保存内存图表失败: {exc}')
            plt.close()
            return f"```text\n{memory_data}\n```"

    def _generate_disk_io_chart(self, disk_io_data: str, output_dir: Path, hostname: str, sid: str) -> str:
        lines = disk_io_data.strip().split('\n')
        chart_data = []

        for line in lines:
            is_chinese_format = '时' in line and 'tps' not in line and '平均时间' not in line
            is_english_format = ('AM' in line or 'PM' in line) and 'tps' not in line and 'Average' not in line

            if is_chinese_format or is_english_format:
                parts = line.split()
                try:
                    if is_english_format and len(parts) >= 7:
                        time_str = parts[0]
                        tps = float(parts[2])
                        rtps = float(parts[3])
                        wtps = float(parts[4])
                        bread_s = float(parts[5])
                        bwrtn_s = float(parts[6])
                    elif is_chinese_format and len(parts) >= 6:
                        time_str = parts[0]
                        tps = float(parts[1])
                        rtps = float(parts[2])
                        wtps = float(parts[3])
                        bread_s = float(parts[4])
                        bwrtn_s = float(parts[5])
                    else:
                        continue

                    if is_chinese_format:
                        time_display = normalize_time_label(time_str)
                    else:
                        time_display = normalize_time_label(time_str)

                    chart_data.append((time_display, tps, rtps, wtps, bread_s, bwrtn_s))
                except (ValueError, IndexError):
                    continue

        if not chart_data:
            return f"```text\n{disk_io_data}\n```"

        self._prepare_matplotlib(output_dir)
        server_picture_dir = output_dir / 'server_picture'
        server_picture_dir.mkdir(exist_ok=True)

        chart_filename = 'disk_io_chart.png'
        chart_path = server_picture_dir / chart_filename

        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax1 = plt.subplots(figsize=(12, 6))

        times = [data[0] for data in chart_data]
        tps_data = [data[1] for data in chart_data]
        rtps_data = [data[2] for data in chart_data]
        wtps_data = [data[3] for data in chart_data]

        # 展示全部时间标签（不再抽稀）
        x, _ = apply_time_axis(ax1, [normalize_time_label(t) for t in times], max_labels=None, rotation=45, fontsize=10)
        ax1.plot(x, tps_data, 'r-', linewidth=2, label='总TPS', marker='o', markersize=4)
        ax1.plot(x, rtps_data, 'orange', linestyle='-', linewidth=2, label='读TPS', marker='s', markersize=4)
        ax1.plot(x, wtps_data, 'b-', linewidth=2, label='写TPS', marker='^', markersize=4)
        ax1.set_ylabel('事务数 (次/秒)', fontsize=12)
        ax1.grid(True, alpha=0.3)

        ax2 = ax1.twinx()
        bread_data = [data[4] for data in chart_data]
        bwrtn_data = [data[5] for data in chart_data]
        ax2.plot(x, bread_data, 'g--', linewidth=1.5, label='读速率(KB/s)', marker='>', markersize=4, alpha=0.7)
        ax2.plot(x, bwrtn_data, 'purple', linestyle='--', linewidth=1.5, label='写速率(KB/s)', marker='<', markersize=4, alpha=0.7)
        ax2.set_ylabel('吞吐量 (KB/s)', fontsize=12)

        ax1.set_title(f'磁盘IO使用率趋势图 (8:00-12:00) - {hostname}', fontsize=14, fontweight='bold', pad=20)
        ax1.set_xlabel('时间', fontsize=12)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, bbox_to_anchor=(1.05, 1), loc='upper left')

        align_twinx_xlim(ax1, ax2)
        plt.tight_layout()

        try:
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(f'磁盘IO图表已保存到: {chart_path}')
            return f"![磁盘IO使用率趋势图](./server_picture/{chart_filename})"
        except Exception as exc:
            logger.error(f'保存磁盘IO图表失败: {exc}')
            plt.close()
            return f"```text\n{disk_io_data}\n```"

    def _generate_disk_space_table(self, disk_space_info: List[Dict[str, str]]) -> str:
        """生成磁盘空间使用率表格"""
        if not disk_space_info:
            return "未找到磁盘空间数据"
        
        # 构建Markdown表格
        table = "| 文件系统 | 容量 | 已用 | 可用 | 已用% | 挂载点 |\n"
        table += "|---|---|---|---|---|---|\n"
        
        # 跳过表头行（如果存在）
        for disk in disk_space_info:
            if disk.get('filesystem') == '文件系统':
                continue
            
            filesystem = disk.get('filesystem', '-')
            size = disk.get('size', '-')
            used = disk.get('used', '-')
            available = disk.get('available', '-')
            use_percent = disk.get('use_percent', '-')
            mount_point = disk.get('mount_point', '-')
            
            table += f"| {filesystem} | {size} | {used} | {available} | {use_percent} | {mount_point} |\n"
        
        return table

    def _build_awr_performance_section(self, awr_data: AwrReportData, meta_info: Dict[str, Any], db_info: Dict[str, Any]) -> str:
        """构建第6章数据库性能检查部分 - 基于AWR HTML文件截图"""
        # 获取基本信息
        hostname = meta_info.get('hostname', '未知主机') if meta_info else '未知主机'
        sid = meta_info.get('sid', 'unknown') if meta_info else 'unknown'
        
        # 获取客户信息和数据库模式显示
        customer_unit = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_unit", "")
        customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_system", "")
        
        # 格式化数据库模式显示
        db_model_display = db_info["dbmodel"].upper()
        if db_model_display == "ONE":
            db_model_display = "单机"
        
        # 从meta_info获取AWR HTML文件路径
        awr_html_path = self._get_awr_html_file_path(meta_info)
        if not awr_html_path:
            return f"""# 6. 数据库性能检查

数据库的性能情况通过 AWR 的报告来体现。\n
本报告中选取了{customer_unit}{customer_system} Oracle{db_model_display}数据库系统工作峰值时间段进行分析。\n


未找到 AWR 报告文件"""
        
        # 获取输出目录
        output_path = self._get_markdown_output_path(meta_info)
        output_dir = output_path.parent
        
        # 生成原有的3张基础AWR HTML截图
        db_info_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays database instance information", "awr_database_info", output_dir)
        host_info_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays host information", "awr_host_info", output_dir) 
        snapshot_info_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays snapshot information", "awr_snapshot_info", output_dir)
        
        # 构建各个详细子章节
        section_6_1 = self._build_awr_instance_efficiency_section(awr_html_path, customer_unit, customer_system, db_model_display, output_dir)
        section_6_2 = self._build_awr_time_model_section(awr_html_path, customer_unit, customer_system, db_model_display, output_dir)
        section_6_3 = self._build_awr_wait_events_section(awr_html_path, customer_unit, customer_system, db_model_display, output_dir)
        section_6_4 = self._build_awr_top_sql_section(awr_html_path, customer_unit, customer_system, db_model_display, output_dir)
        section_6_5 = self._build_awr_overall_assessment_section(customer_unit, customer_system, db_model_display)
        
        return f"""# 6. 数据库性能检查

数据库的性能情况通过 AWR 的报告来体现。\n
本报告中选取了{customer_unit}{customer_system} Oracle{db_model_display}数据库系统工作峰值时间段进行分析。\n

{db_info_image}
{host_info_image}
{snapshot_info_image}

{section_6_1}

{section_6_2}

{section_6_3}

{section_6_4}

{section_6_5}
"""
    
    def _get_awr_html_file_path(self, meta_info: Dict[str, Any]) -> Optional[Path]:
        """从meta_info中获取AWR HTML文件路径"""
        if not meta_info:
            logger.warning("meta_info为空")
            return None
        
        # 直接从meta_info的files字段中查找AWR HTML文件
        files = meta_info.get('files', {})
        
        # 查找 AWR HTML 文件 (11_awrrpt_*.html)
        for file_key, file_info in files.items():
            if file_key.startswith('11_awrrpt') and file_info.get('exists', False):
                file_path = file_info.get('path')
                if file_path:
                    path_obj = Path(file_path)
                    if path_obj.suffix.lower() == '.html' and path_obj.exists():
                        logger.info(f"找到AWR HTML文件: {file_path}")
                        return path_obj
                    else:
                        logger.warning(f"AWR文件路径无效或不存在: {file_path}")
                        
        # 如果没找到，尝试从incfilelist中查找（兼容旧格式）
        incfilelist = meta_info.get('incfilelist', [])
        for file_item in incfilelist:
            if isinstance(file_item, dict):
                filename = file_item.get('filename', '')
                fileurl = file_item.get('fileurl', '')
                if filename.startswith('11_awrrpt') and filename.endswith('.html'):
                    path_obj = Path(fileurl)
                    if path_obj.exists():
                        logger.info(f"从incfilelist找到AWR HTML文件: {fileurl}")
                        return path_obj
                    
        logger.warning(f"未找到AWR HTML文件，meta_info结构: {list(meta_info.keys())}")
        return None
    
    def _generate_awr_html_screenshot(self, html_file_path: Path, summary_text: str, output_file_name: str, output_dir: Path) -> str:
        """生成AWR HTML截图"""
        try:
            # 创建awr_picture目录
            awr_picture_dir = output_dir / "awr_picture"
            awr_picture_dir.mkdir(exist_ok=True)
            
            # 检查HTML文件是否存在
            if not html_file_path.exists():
                logger.error(f"AWR HTML文件不存在: {html_file_path}")
                return "AWR HTML文件不存在，无法生成截图"
            
            # 使用HTMLCapture进行截图
            with HTMLCapture(compress_images=True) as capture:
                result = capture.capture_by_summary(
                    html_file_path=html_file_path,
                    summary_text=summary_text,
                    output_file_name=output_file_name,
                    output_dir=awr_picture_dir
                )
                
                # 检查截图是否成功
                if result and not result.startswith("获取 AWR 报告图片失败"):
                    # 返回markdown图片引用
                    return f"![AWR截图](./awr_picture/{output_file_name}.png)"
                else:
                    logger.error(f"AWR HTML截图失败: {result}")
                    return f"AWR HTML截图失败: {result}"
                    
        except Exception as e:
            logger.error(f"生成AWR HTML截图异常: {e}")
            return f"生成AWR HTML截图异常: {str(e)}"

    def _generate_awr_database_info_chart(self, awr_data: AwrReportData, output_dir: Path, hostname: str, sid: str) -> str:
        """生成AWR数据库实例信息表格图片"""
        # 创建awr_picture目录
        awr_picture_dir = output_dir / "awr_picture"
        awr_picture_dir.mkdir(exist_ok=True)
        
        chart_filename = "awr_database_info_table.png"
        chart_path = awr_picture_dir / chart_filename
        
        try:
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.axis('tight')
            ax.axis('off')
            
            # 准备表格数据
            table_data = [
                ['数据库名称', awr_data.db_name],
                ['数据库ID', awr_data.db_id],
                ['实例名称', awr_data.instance],
                ['实例编号', awr_data.inst_num],
                ['启动时间', awr_data.startup_time],
                ['Oracle版本', awr_data.release],
                ['RAC模式', awr_data.rac]
            ]
            
            # 创建表格
            table = ax.table(cellText=table_data,
                           colLabels=['项目', '值'],
                           cellLoc='left',
                           loc='center',
                           bbox=[0, 0, 1, 1])
            
            # 设置表格样式
            table.auto_set_font_size(False)
            table.set_fontsize(12)
            table.scale(1, 2)
            
            # 设置表头样式
            for i in range(2):  # 2列
                table[(0, i)].set_facecolor('#4472C4')
                table[(0, i)].set_text_props(weight='bold', color='white')
                table[(0, i)].set_height(0.15)
            
            # 设置数据行样式
            for i in range(1, len(table_data) + 1):
                for j in range(2):
                    if i % 2 == 0:
                        table[(i, j)].set_facecolor('#F2F2F2')
                    table[(i, j)].set_height(0.12)
            
            plt.title(f'AWR数据库实例信息 - {hostname}', fontsize=14, fontweight='bold', pad=20)
            plt.tight_layout()
            
            # 保存图表
            plt.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()
            
            logger.info(f"AWR数据库信息表格已保存到: {chart_path}")
            return f"![AWR数据库实例信息](./awr_picture/{chart_filename})"
            
        except Exception as e:
            logger.error(f"生成AWR数据库信息表格失败: {e}")
            return "生成AWR数据库信息表格失败"

    def _generate_awr_host_info_chart(self, awr_data: AwrReportData, output_dir: Path, hostname: str, sid: str) -> str:
        """生成AWR主机信息表格图片"""
        # 创建awr_picture目录
        awr_picture_dir = output_dir / "awr_picture"
        awr_picture_dir.mkdir(exist_ok=True)
        
        chart_filename = "awr_host_info_table.png"
        chart_path = awr_picture_dir / chart_filename
        
        try:
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.axis('tight')
            ax.axis('off')
            
            # 准备表格数据
            table_data = [
                ['主机名称', awr_data.host_name],
                ['操作系统平台', awr_data.platform],
                ['CPU数量', awr_data.cpus],
                ['CPU核心数', awr_data.cores],
                ['CPU插槽数', awr_data.sockets],
                ['内存容量(GB)', awr_data.memory_gb]
            ]
            
            # 创建表格
            table = ax.table(cellText=table_data,
                           colLabels=['项目', '值'],
                           cellLoc='left',
                           loc='center',
                           bbox=[0, 0, 1, 1])
            
            # 设置表格样式
            table.auto_set_font_size(False)
            table.set_fontsize(12)
            table.scale(1, 2)
            
            # 设置表头样式
            for i in range(2):  # 2列
                table[(0, i)].set_facecolor('#4472C4')
                table[(0, i)].set_text_props(weight='bold', color='white')
                table[(0, i)].set_height(0.15)
            
            # 设置数据行样式
            for i in range(1, len(table_data) + 1):
                for j in range(2):
                    if i % 2 == 0:
                        table[(i, j)].set_facecolor('#F2F2F2')
                    table[(i, j)].set_height(0.12)
            
            plt.title(f'AWR主机信息 - {hostname}', fontsize=14, fontweight='bold', pad=20)
            plt.tight_layout()
            
            # 保存图表
            plt.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()
            
            logger.info(f"AWR主机信息表格已保存到: {chart_path}")
            return f"![AWR主机信息](./awr_picture/{chart_filename})"
            
        except Exception as e:
            logger.error(f"生成AWR主机信息表格失败: {e}")
            return "生成AWR主机信息表格失败"

    def _generate_awr_snapshot_info_chart(self, awr_data: AwrReportData, output_dir: Path, hostname: str, sid: str) -> str:
        """生成AWR快照信息表格图片"""
        # 创建awr_picture目录
        awr_picture_dir = output_dir / "awr_picture"
        awr_picture_dir.mkdir(exist_ok=True)
        
        chart_filename = "awr_snapshot_info_table.png"
        chart_path = awr_picture_dir / chart_filename
        
        try:
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 3))
            ax.axis('tight')
            ax.axis('off')
            
            # 准备表格数据
            table_data = [
                ['开始快照', awr_data.begin_snap_id, awr_data.begin_snap_time, awr_data.begin_sessions, awr_data.begin_cursors_per_session, awr_data.instances],
                ['结束快照', awr_data.end_snap_id, awr_data.end_snap_time, awr_data.end_sessions, awr_data.end_cursors_per_session, awr_data.instances]
            ]
            
            # 创建表格
            table = ax.table(cellText=table_data,
                           colLabels=['快照类型', '快照ID', '快照时间', '会话数', '每会话游标数', '实例数'],
                           cellLoc='center',
                           loc='center',
                           bbox=[0, 0, 1, 1])
            
            # 设置表格样式
            table.auto_set_font_size(False)
            table.set_fontsize(11)
            table.scale(1, 2.5)
            
            # 设置表头样式
            for i in range(6):  # 6列
                table[(0, i)].set_facecolor('#4472C4')
                table[(0, i)].set_text_props(weight='bold', color='white')
                table[(0, i)].set_height(0.2)
            
            # 设置数据行样式
            for i in range(1, len(table_data) + 1):
                for j in range(6):
                    if i % 2 == 0:
                        table[(i, j)].set_facecolor('#F2F2F2')
                    table[(i, j)].set_height(0.15)
            
            plt.title(f'AWR快照信息 - {hostname}', fontsize=14, fontweight='bold', pad=20)
            plt.tight_layout()
            
            # 保存图表
            plt.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()
            
            logger.info(f"AWR快照信息表格已保存到: {chart_path}")
            return f"![AWR快照信息](./awr_picture/{chart_filename})"
            
        except Exception as e:
            logger.error(f"生成AWR快照信息表格失败: {e}")
            return "生成AWR快照信息表格失败"

    def _build_awr_instance_efficiency_section(self, awr_html_path: Path, customer_unit: str, customer_system: str, db_model_display: str, output_dir: Path) -> str:
        """构建6.1数据库实例命中率章节"""
        efficiency_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays instance efficiency percentages", "awr_instance_efficiency", output_dir)
        
        return f"""## 6.1. 数据库实例命中率


以下列出的是{customer_unit}{customer_system} Oracle{db_model_display}实例性能的各项命中率 \n
**Instance Efficiency Percentages (Target 100%)**\n
{efficiency_image}

综合结论：【请填写结论】"""

    def _build_awr_time_model_section(self, awr_html_path: Path, customer_unit: str, customer_system: str, db_model_display: str, output_dir: Path) -> str:
        """构建6.2数据库资源消耗时间模型章节"""
        time_model_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays different time model statistics. For each statistic, time and % of DB time are displayed", "awr_time_model", output_dir)
        
        return f"""## 6.2. 数据库资源消耗时间模型


以下列出的是{customer_unit}{customer_system} Oracle{db_model_display}数据库实例资源消耗时间模型，该模型能表现出当前实例消耗最长时间的事件是那些。 \n
**Time Model Statistics**\n
- Total time in database user-calls (DB Time): 0s\n
- Statistics including the word "background" measure background process time, and so do not contribute to the DB time statistic\n
- Ordered by % or DB time desc, Statistic name\n
{time_model_image}

综合结论：【请填写结论】"""

    def _build_awr_wait_events_section(self, awr_html_path: Path, customer_unit: str, customer_system: str, db_model_display: str, output_dir: Path) -> str:
        """构建6.3数据库等待事件章节"""
        efficiency_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays top 10 wait events by total wait time", "awr_wait_efficiency", output_dir)
        wait_class_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays wait class statistics ordered by total wait time", "awr_wait_class", output_dir)
        
        return f"""## 6.3. 数据库等待事件

在观察期内，{customer_unit}{customer_system} Oracle{db_model_display}数据库的等待事件(可能的瓶颈所在)如下： \n
**Top 10 Foreground Events by Total Wait Time**\n
{efficiency_image} \n
**Wait Classes by Total Wait Time**\n
{wait_class_image}

综合结论：【请填写结论】"""

    def _build_awr_top_sql_section(self, awr_html_path: Path, customer_unit: str, customer_system: str, db_model_display: str, output_dir: Path) -> str:
        """构建6.4 TOP SQL章节"""
        elapsed_time_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays top SQL by elapsed time", "awr_top_sql_elapsed", output_dir)
        cpu_time_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays top SQL by CPU time", "awr_top_sql_cpu", output_dir)
        io_time_image = self._generate_awr_html_screenshot(awr_html_path, "This table displays top SQL by user I/O time", "awr_top_sql_io", output_dir)
        
        return f"""## 6.4. TOP SQL

观察期内，{customer_unit}{customer_system} Oracle{db_model_display}数据库逻辑读的TOP SQL如下： \n
**SQL ordered by Elapsed Time** \n
- Resources reported for PL/SQL code includes the resources used by all SQL statements called by the code.\n
- % Total DB Time is the Elapsed Time of the SQL statement divided into the Total Database Time multiplied by 100\n
- %Total - Elapsed Time as a percentage of Total DB time\n
- %CPU - CPU Time as a percentage of Elapsed Time\n
- %IO - User I/O Time as a percentage of Elapsed Time\n
- Captured SQL account for 5.6E+04% of Total DB Time (s): 0\n
- Captured PL/SQL account for 1.6E+03% of Total DB Time (s): 0\n
{elapsed_time_image}

**SQL ordered by CPU Time** \n
- Resources reported for PL/SQL code includes the resources used by all SQL statements called by the code.\n
- %Total - CPU Time as a percentage of Total DB CPU\n
- %CPU - CPU Time as a percentage of Elapsed Time\n
- %IO - User I/O Time as a percentage of Elapsed Time\n
- Captured SQL account for 5.1E+04% of Total CPU Time (s): 0\n
- Captured PL/SQL account for 1.6E+03% of Total CPU Time (s): 0\n
{cpu_time_image}

**SQL ordered by User I/O Wait Time**\n
- Resources reported for PL/SQL code includes the resources used by all SQL statements called by the code.\n
- %Total - User I/O Time as a percentage of Total User I/O Wait time\n
- %CPU - CPU Time as a percentage of Elapsed Time\n
- %IO - User I/O Time as a percentage of Elapsed Time\n
- Captured SQL account for 99.0% of Total User I/O Wait Time (s): 0\n
- Captured PL/SQL account for 0.1% of Total User I/O Wait Time (s): 0\n
{io_time_image}

综合结论：【请填写结论】"""

    def _build_awr_overall_assessment_section(self, customer_unit: str, customer_system: str, db_model_display: str) -> str:
        """构建6.5数据库实例负载整体评估章节"""
        return f"""## 6.5. 数据库实例负载整体评估

综合结论：【请填写结论】"""

    @staticmethod
    def _limit_rman_content_lines(content: str, max_lines: Optional[int] = None) -> str:
        """
        限制RMAN内容显示行数
        
        Args:
            content: 要限制的内容字符串
            max_lines: 最大显示行数，如果为None则使用配置中的默认值
            
        Returns:
            限制行数后的内容字符串
        """
        if not content:
            return content
            
        # 检查是否为默认错误信息，如果是则直接返回
        default_messages = [
            MarkdownConfig.RMAN_DISPLAY_CONFIG["default_backup_details_message"],
            MarkdownConfig.RMAN_DISPLAY_CONFIG["default_backup_sets_message"]
        ]
        if content in default_messages:
            return content
        
        # 获取最大行数配置
        if max_lines is None:
            max_lines = MarkdownConfig.RMAN_DISPLAY_CONFIG["max_display_lines"]
        
        # 分割内容为行
        lines = content.splitlines()
        
        # 如果行数不超过限制，返回原内容
        if len(lines) <= max_lines:
            return content
            
        # 截取前max_lines行并重新组合
        limited_lines = lines[:max_lines]
        return '\n'.join(limited_lines)
