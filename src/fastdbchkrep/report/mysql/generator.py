"""MySQL 数据库 Markdown 报告生成器"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import os
from loguru import logger
import matplotlib.pyplot as plt
 

from ..common.config import MarkdownConfig
from ..common.template_config import TemplateConfig
from ..pdf import MarkdownToPdfConverter
from ..common.chart_utils import normalize_time_label, apply_time_axis, align_twinx_xlim


class MarkdownGenerator:
    """为 MySQL 数据库生成 Markdown 报告的最小实现。"""

    def __init__(
        self,
        db_type: str = "mysql",
        output_dir: Optional[Path] = None,
        company_name: Optional[str] = None,
        user_company: Optional[str] = None,
        application_name: Optional[str] = None,
        suptime: Optional[str] = None,
        supname: Optional[str] = None,
    ) -> None:
        self.db_type = db_type.lower() if db_type else "mysql"
        self.output_dir = output_dir or MarkdownConfig.OUTDIR_PATH
        self.company_name = company_name or "鼎诚科技"
        self.user_company = user_company or "客户单位"
        self.application_name = application_name or "应用系统"
        self.suptime = suptime
        self.supname = supname
        self.db_model: str = "one"

        # 记录基础信息，便于调试
        logger.debug(
            "初始化 MySQL MarkdownGenerator: type=%s, output_dir=%s",
            self.db_type,
            self.output_dir,
        )

        # 更新模板占位符，保持与 Oracle 生成器一致的入口参数效果
        if company_name:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"] = company_name
        if user_company:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"] = user_company
        if application_name:
            MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"] = application_name

        # 初始化日志文件目录
        log_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "log"
        log_dir.mkdir(exist_ok=True)
        logger.add(
            log_dir / "fastdbchkrep.log",
            rotation="10 MB",
            level="INFO",
            format="{time} | {level} | {message}",
        )

    def generate_from_json(self, json_data: Dict[str, Any], quiet: bool = False) -> bool:
        """根据解析后的 JSON 数据生成 Markdown 报告。"""
        try:
            metainfo = json_data.get("metainfo", []) or []
            if not metainfo:
                logger.error("MySQL JSON 数据缺少 metainfo，无法生成报告")
                return False

            self.db_model = str(json_data.get("dbmodel", "one")).lower()

            success_count = 0
            for idx, meta in enumerate(metainfo, start=1):
                if not quiet:
                    hostname = meta.get("hostname", "unknown")
                    sid = meta.get("sid", "unknown")
                    print(f"  处理 MySQL 节点 {idx}/{len(metainfo)}: {hostname} (SID: {sid})")

                if self._generate_single_instance_from_meta(meta):
                    success_count += 1

            if success_count == 0:
                logger.error("MySQL 报告生成失败：未成功处理任何节点")
                return False

            if not quiet:
                print(f"  成功生成 {success_count}/{len(metainfo)} 个 MySQL 节点的报告")
            return True

        except Exception as exc:  # pragma: no cover - 容错输出
            logger.exception(f"MySQL 报告生成时出现异常: {exc}")
            return False

    def _generate_single_instance_from_meta(self, meta_info: Dict[str, Any]) -> bool:
        """为单个 MySQL 节点生成 Markdown 文件。"""
        try:
            output_path = self._get_markdown_output_path(meta_info)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            markdown_content = self._build_markdown_content(meta_info)
            output_path.write_text(markdown_content, encoding="utf-8")

            logger.info("MySQL Markdown 报告已生成: %s", output_path)

            # 生成可编辑HTML（与Oracle一致的行为），文件与MD同目录
            try:
                conv = MarkdownToPdfConverter()
                ok, editable_path = conv.generate_editable_html(
                    md_file=str(output_path),
                    output_dir=str(output_path.parent),
                    output_name=output_path.stem,
                )
                if ok:
                    logger.info("MySQL 可编辑HTML已生成: %s", editable_path)
                else:
                    logger.warning("MySQL 可编辑HTML生成失败: %s", output_path)
            except Exception as e:
                logger.warning(f"生成可编辑HTML时发生异常: {e}")

            return True
        except Exception as exc:  # pragma: no cover - 容错输出
            logger.exception(f"生成 MySQL Markdown 报告失败: {exc}")
            return False

    # --- Markdown 构建 -------------------------------------------------

    def _build_markdown_content(self, meta_info: Dict[str, Any]) -> str:
        """构建要求的基础章节（首页、目录、文档控制、章节 1/2）。"""
        output_path = self._get_markdown_output_path(meta_info)
        output_dir = output_path.parent

        support_start_raw, support_end_raw = self._resolve_support_dates(meta_info)
        cover_page = TemplateConfig.generate_cover_page(
            company_name=self.company_name,
            user_company=self.user_company,
            application_name=self.application_name,
            db_type="MySQL",
            support_start_date=support_start_raw,
            support_end_date=support_end_raw,
            suptime=self.suptime,
            supname=self.supname,
            base_dir=output_dir,
        )
        toc_page = self._generate_mysql_toc()
        document_control = TemplateConfig.generate_document_control(
            company_name=self.company_name,
            user_company=self.user_company,
        )

        formatted_time = self._format_inspection_time_cn(meta_info.get("collect_date"))
        db_model_display = self._get_db_model_display()
        file_status_display = self._build_file_status_display(meta_info)
        problems_table = self._build_placeholder_problems_table()

        system_background = self._build_system_background_section(meta_info)
        database_config_section = self._build_database_config_section(meta_info)
        resource_config_section = self._build_resource_config_section(meta_info)
        os_check_section = self._build_os_check_section(meta_info)
        database_main_info_section = self._build_database_main_info_section(meta_info)
        user_privileges_section = self._build_user_privileges_section(meta_info)
        db_perf_params_section = self._build_db_performance_params_section(meta_info)
        db_log_paths_section = self._build_db_log_paths_section(meta_info)
        db_status_checks_section = self._build_db_status_checks_section(meta_info)
        innodb_status_section = self._build_innodb_status_section(meta_info)
        backup_check_section = self._build_backup_check_section(meta_info)

        sections = f"""# 1. 健康检查总结

## 1.1. 健康检查概要

  如果{MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"]}工程师在检查中发现MySQL数据库的问题，我们将对有问题的情况进行记录，并通知客户改正；对于比较复杂的问题，我们将在报告中指出，并建议和协助客户进一步进行相关的详细检查，同时将问题提交到{MarkdownConfig.TEMPLATE_PLACEHOLDERS["company_names"]}技术支持部，以便问题得到更快更好的解决。

  此次检查所需的资料来源主要是{formatted_time}使用 mysql_inspection.sh 脚本对{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"]}{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}MySQL数据库收集运行环境文件的结果。此次我们主要检查该数据库的性能和配置，在下面的报告中，我们将做出分析，然后提出相关的改进建议。

  此次检查的数据库范围是：{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_unit"]}{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}MySQL{db_model_display}数据库。

## 1.2. 健康检查建议

以下是本次检查发现的一些主要问题和建议的总结。

{MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]}MySQL{db_model_display}数据库

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

本次检查仅限 {MarkdownConfig.TEMPLATE_PLACEHOLDERS["customer_system"]} MySQL {db_model_display}数据库，本报告提供的检查和建议主要针对以下方面：

- 主机配置
- 操作系统性能
- 数据库配置
- 数据库性能

本报告的提供的检查和建议不涉及：

- 具体的性能调整
- 应用程序的具体细节

**注意**：本次检查仅历时一天，其中还包括了提交分析报告的时间。所以在具体的性能方面仅做相应的建议。如需在数据库性能方面进行进一步的调整，请继续选择数据库性能调整。

{system_background}
{database_config_section}
{resource_config_section}
{os_check_section}
{database_main_info_section}
{user_privileges_section}
{db_perf_params_section}
{db_log_paths_section}
{db_status_checks_section}
{innodb_status_section}
{backup_check_section}
        """

        return f"{cover_page}{toc_page}{document_control}{sections}"

    def _resolve_support_dates(self, meta_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """解析现场支持日期（collect_date 优先，其次目录名中的日期）。"""
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
    def _generate_mysql_toc() -> str:
        """生成适配MySQL章节结构的目录（包含第11章）。"""
        return """# 目录

1. [健康检查总结](#1-健康检查总结)
   - 1.1. [健康检查概要](#11-健康检查概要)
   - 1.2. [健康检查建议](#12-健康检查建议)

2. [健康检查介绍](#2-健康检查介绍)
   - 2.1. [健康检查目标](#21-健康检查目标)
   - 2.2. [健康检查方法](#22-健康检查方法)
   - 2.3. [健康检查范围](#23-健康检查范围)

3. [系统背景](#3-系统背景)
   - 3.1. [系统硬件配置](#31-系统硬件配置)
   - 3.2. [数据库配置](#32-数据库配置)
   - 3.3. [数据库资源相关配置](#33-数据库资源相关配置)

4. [操作系统检查](#4-操作系统检查)
   - 4.1. [CPU 使用率](#41-cpu-使用率)
   - 4.2. [内存使用率](#42-内存使用率)
   - 4.3. [磁盘IO使用率](#43-磁盘io使用率)
   - 4.4. [磁盘空间使用情况](#44-磁盘空间使用率)

5. [数据库主要信息检查](#5-数据库主要信息检查)
   - 5.1. [数据库实例基本信息](#51-数据库实例基本信息)
   - 5.2. [数据库字符集信息](#52-数据库字符集信息)
   - 5.3. [数据库模式和状态](#53-数据库模式和状态)

6. [数据库用户权限](#6-数据库用户权限)
   - 6.1. [用户账户基本信息](#61-用户账户基本信息)
   - 6.2. [用户系统权限汇总](#62-用户系统权限汇总)
   - 6.3. [数据库级别权限](#63-数据库级别权限)
   - 6.4. [密码策略和账户状态检查](#64-密码策略和账户状态检查)
   - 6.5. [用户权限与维护状态](#65-用户权限与维护状态)

7. [数据库性能参数](#7-数据库性能参数)
   - 7.1. [内存相关参数](#71-内存相关参数-memory-parameters)
   - 7.2. [InnoDB内存参数](#72-innodb内存参数)
   - 7.3. [连接和线程参数](#73-连接和线程参数)
   - 7.4. [其他性能参数](#74-其他性能参数)

8. [数据库日志路径](#8-数据库日志路径)
   - 8.1. [重要日志文件路径](#81-重要日志文件路径)
   - 8.2. [二进制日志配置](#82-二进制日志配置)
   - 8.3. [慢查询日志配置](#83-慢查询日志配置)

9. [数据库状态检查](#9-数据库状态检查)
   - 9.1. [数据库大小统计](#91-数据库大小统计)
   - 9.2. [各数据库大小排名](#92-各数据库大小排名-top-10)
   - 9.3. [表大小排名](#93-表大小排名-top-20)
   - 9.4. [无主键的表](#94-无主键的表-top-20)
   - 9.5. [碎片率高的表](#95-碎片率高的表-碎片率30-top-20)
   - 9.6. [自增ID使用率高的表](#96-自增id使用率高的表-使用率70-top-20)
   - 9.7. [大事务检测](#97-大事务检测-修改行数10000)
   - 9.8. [缓慢SQL列表（前20条）](#98-缓慢sql列表前20条)

10. [InnoDB Status](#10innodb-status)
   - 10.1. [InnoDB Buffer Pool状态](#101innodb-buffer-pool状态)
   - 10.2. [InnoDB引擎详细状态信息](#102innodb引擎详细状态信息)

11. [MySQL备份检查](#11mysql备份检查)
   - 11.1. [MySQL Fast Backup (XtraBackup) 检测](#111mysql-fast-backup-xtrabackup-检测)
   - 11.2. [备份目录容量与时间 (按大小倒序)](#112备份目录容量与时间-按大小倒序)
   - 11.3. [Crontab 自动备份任务配置](#113crontab-自动备份任务配置)

---
"""

    def _build_backup_check_section(self, meta_info: Dict[str, Any]) -> str:
        """构建第11章 MySQL备份检查。

        11.1 从 03_xtrabackup_backup.txt 中抽取 "===== MySQL Fast Backup (XtraBackup) 检测 ====="
        11.2 从 03_xtrabackup_backup.txt 中抽取 "===== 备份目录容量与时间 (按大小倒序) ====="
        11.3 从 03_xtrabackup_backup.txt 中抽取 "===== Crontab 自动备份任务配置 ====="
        三段内容均以代码块展示；末尾添加综合结论占位。
        """
        text = self._load_xtrabackup_text(meta_info)

        def code_block_for(marker: str) -> str:
            content = self._extract_block_by_marker(text, marker) if text else None
            if content:
                return f"```text\n{content}\n```"
            return "```text\n未找到相关内容\n```"

        part_11_1 = code_block_for("MySQL Fast Backup (XtraBackup) 检测")
        part_11_2 = code_block_for("备份目录容量与时间 (按大小倒序)")
        part_11_3 = code_block_for("Crontab 自动备份任务配置")

        section = f"""# 11.MySQL备份检查

## 11.1.MySQL Fast Backup (XtraBackup) 检测 
{part_11_1}

## 11.2.备份目录容量与时间 (按大小倒序)
{part_11_2}

## 11.3.Crontab 自动备份任务配置
{part_11_3}

综合结论：【留空给工程师写结论】
"""
        return section

    def _load_xtrabackup_text(self, meta_info: Dict[str, Any]) -> Optional[str]:
        files = meta_info.get("files", {}) or {}
        entry = files.get("03_xtrabackup_backup")
        if not entry:
            return None
        path = entry.get("path")
        if not path:
            return None
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            logger.warning("无法读取 XtraBackup 文件: %s", path)
            return None

    @staticmethod
    def _extract_block_by_marker(text: Optional[str], marker_title: str) -> Optional[str]:
        """从文本中抽取指定“==== 标题 ==== ”块的内容。

        匹配规则：
        - 标题行形如：===== {marker_title} =====（等号数量不做严格限定）
        - 返回从标题下一行到下一个“===== ... =====”标题行（不含）之间的内容。
        """
        if not text:
            return None
        lines = text.splitlines()
        # 标题匹配：允许可变数量的等号与空格
        import re as _re
        header_re = _re.compile(r"^\s*=+\s*(.*?)\s*=+\s*$")

        # 先找到所有标题的下标，建立索引
        headers: List[Tuple[int, str]] = []
        for idx, line in enumerate(lines):
            m = header_re.match(line)
            if m:
                headers.append((idx, m.group(1).strip()))

        # 根据标题精确或包含匹配找到起始位置
        start_idx: Optional[int] = None
        end_idx: Optional[int] = None

        # 优先精确匹配
        for i, (idx, title) in enumerate(headers):
            if title == marker_title:
                start_idx = idx + 1
                # 找到下一个标题
                if i + 1 < len(headers):
                    end_idx = headers[i + 1][0]
                else:
                    end_idx = len(lines)
                break

        # 若无精确匹配，退化为包含匹配（容错不同空格或细微差异）
        if start_idx is None:
            for i, (idx, title) in enumerate(headers):
                if marker_title in title:
                    start_idx = idx + 1
                    end_idx = headers[i + 1][0] if i + 1 < len(headers) else len(lines)
                    break

        if start_idx is None:
            return None

        block = "\n".join(lines[start_idx:end_idx]).strip()
        return block or None

    # --- 内容辅助 -----------------------------------------------------

    def _build_file_status_display(self, meta_info: Dict[str, Any]) -> str:
        files: Dict[str, Dict[str, Any]] = meta_info.get("files", {}) or {}
        if not files:
            return "| 状态 | 文件名 | 文件描述 |\n|---|---|---|\n| ✗ | - | 暂无文件信息 |"

        description_map = {
            "00_inspection_summary.txt": "巡检汇总",
            "01_system_info.txt": "系统信息",
            "02_hardware_info.json": "硬件信息(JSON格式)",
            "03_xtrabackup_backup.txt": "XtraBackup备份信息",
            "04_health_check.txt": "数据库健康检查",
            "05_adrci_ora.txt": "ADRCI诊断信息",
            "09_rman_info.txt": "RMAN备份信息",
            "10_sar_report.txt": "系统资源监控",
        }

        rows: List[str] = ["| 状态 | 文件名 | 文件描述 |", "|---|---|---|"]
        for key in sorted(files.keys()):
            info = files.get(key, {}) or {}
            path = info.get("path") or key
            exists = bool(info.get("exists"))
            filename = Path(path).name if path else key
            status_symbol = "✓" if exists else "✗"
            description = description_map.get(filename, description_map.get(key, "-"))
            rows.append(f"| {status_symbol} | {filename} | {description} |")

        return "\n".join(rows)

    @staticmethod
    def _build_placeholder_problems_table() -> str:
        rows = ["| NO | 问题描述 | 参考章节 | 建议解决时间 |", "|---|---|---|---|"]
        rows.extend(["|  |  |  |  |"] * 3)
        return "\n".join(rows)

    def _build_system_background_section(self, meta_info: Dict[str, Any]) -> str:
        hardware = self._load_hardware_info(meta_info)
        hostname = meta_info.get("hostname", "-")

        cpu_info = hardware.get("cpu", {}) if hardware else {}
        memory_info = hardware.get("memory", {}) if hardware else {}
        disk_info = hardware.get("disk_space", []) if hardware else []

        cpu_model = cpu_info.get("model") or "-"
        logical_cores_raw = cpu_info.get("logical_cores") or cpu_info.get("cores")
        physical_cores_raw = cpu_info.get("physical_cores")
        cores_per_cpu = None
        try:
            logical_int = int(logical_cores_raw) if logical_cores_raw not in (None, "-") else None
            physical_int = int(physical_cores_raw) if physical_cores_raw not in (None, "-") else None
            if logical_int and physical_int and physical_int > 0:
                cores_per_cpu = logical_int // physical_int or logical_int
        except Exception:
            cores_per_cpu = None
        logical_cores = str(logical_cores_raw) if logical_cores_raw not in (None, "") else "-"
        cores_per_cpu_display = str(cores_per_cpu) if cores_per_cpu else "-"
        memory_total_gb = memory_info.get("total_gb") or self._kb_to_gb(memory_info.get("total_kb")) or "-"
        if memory_total_gb not in ("-", None):
            memory_total_gb = f"{memory_total_gb} GB"
        disk_summary = self._format_disk_summary(disk_info) or "-"

        system_info = self._load_system_info(meta_info)
        system_version = system_info.get("系统版本信息", "-")
        kernel_version = system_info.get("内核版本", "-")
        kernel_params = (system_info.get("生效的内核参数") or "-").replace("\n", "<br>")
        resource_limits = (system_info.get("资源限制参数") or "-").replace("\n", "<br>")
        disk_scheduler = (system_info.get("磁盘调度算法") or "-").replace("\n", "<br>")
        system_uptime = system_info.get("系统启动时间和负载") or "-"

        db_model_display = "集群" if self.db_model == "rac" else "单机"

        table_lines = [
            "| 选项参数名 | 选项参数值 | 说明 |",
            "|---|---|---|",
            "| SERVER_TYPE | X86数据库服务器 / Oracle ExaData 一体机 (二选一) | 服务器类型 |",
            f"| SERVER_NAME | {hostname or '-'} | 服务器主机名 |",
            "| SERVER_ENVIRONMENT | Prod | 服务器环境类型 |",
            "| SERVER_LOCATION | - | 服务器所在地 |",
            "| SERVER_VENDOR | - | 服务器供应商 |",
            "| SERVER_MODEL | - | 服务器型号 |",
            f"| CPU_MODEL | {cpu_model} | 处理器型号 |",
            f"| CPU_LOGICAL_CORES | {logical_cores} | 逻辑CPU核心数 |",
            f"| CPU_CORES_PER_CPU | {cores_per_cpu_display} | 每颗CPU核心数 |",
            f"| MEMORY_SIZE_GB | {memory_total_gb} | 物理内存大小 |",
            f"| DISK_CONFIGURATION | {disk_summary} | 本地磁盘配置信息 |",
            "| DISK_REDUNDANCY_TYPE | - | 磁盘冗余类型 |",
            "| SERVER_AVAILABILITY | 7x24 | 服务器可用性需求 |",
            "| MAX_DOWNTIME | - | 最大可接受停机时间 |",
            f"| PARALLEL_SERVER_TYPE | {db_model_display} | 并行服务器类型 |",
            f"| SYSTEM_VERSION | {system_version or '-'} | 操作系统版本信息 |",
            f"| KERNEL_VERSION | {kernel_version or '-'} | 操作系统内核版本 |",
            f"| KERNEL_PARAMETERS | {kernel_params or '-'} | 生效的内核参数 |",
            f"| RESOURCE_LIMITS | {resource_limits or '-'} | 资源限制参数 |",
            f"| DISK_SCHEDULER | {disk_scheduler or '-'} | 磁盘调度算法 |",
            f"| SYSTEM_UPTIME | {system_uptime or '-'} | 系统启动时间和负载 |",
        ]

        return "# 3. 系统背景\n\n## 3.1. 系统硬件配置\n\n" + "\n".join(table_lines) + "\n"

    def _build_database_config_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        basic = health.get("basic_info")
        charset = health.get("charset_info")
        db_stats = health.get("database_stats")
        binary_log = health.get("binary_log_config")

        sections: List[str] = ["## 3.2. 数据库配置", ""]

        rows: List[tuple] = []
        if db_stats:
            stats_row = db_stats[0]
            rows.extend([
                ("DATABASE_COUNT", stats_row.get("DATABASE_COUNT", "-"), "数据库数量"),
                ("TABLE_COUNT", stats_row.get("TABLE_COUNT", "-"), "表数量"),
                ("TOTAL_SIZE_MB", stats_row.get("TOTAL_SIZE_MB", "-"), "数据库总大小(MB)"),
                ("DATA_SIZE_MB", stats_row.get("DATA_SIZE_MB", "-"), "数据占用(MB)"),
                ("INDEX_SIZE_MB", stats_row.get("INDEX_SIZE_MB", "-"), "索引占用(MB)"),
            ])
        binary_log_entry: Optional[tuple] = None
        if binary_log:
            log_row = binary_log[0]
            binary_log_entry = (
                "BINARY_LOG_ENABLED",
                log_row.get("BINARY_LOG_ENABLED", "-") or "-",
                "是否启用二进制日志",
            )

        if basic:
            basic_row = basic[0]
            base_rows = [
                ("DB_HOST", basic_row.get("HOSTNAME", "-"), "数据库主机名"),
                ("DB_PORT", basic_row.get("PORT", "-"), "数据库端口"),
                ("DB_VERSION", basic_row.get("VERSION", "-"), "数据库版本"),
                ("VERSION_COMMENT", basic_row.get("VERSION_COMMENT", "-"), "版本注释"),
                ("COMPILE_OS", basic_row.get("COMPILE_OS", "-"), "编译操作系统"),
                ("COMPILE_MACHINE", basic_row.get("COMPILE_MACHINE", "-"), "编译架构"),
                ("CHECK_TIME", basic_row.get("CHECK_TIME", "-"), "本次检查时间"),
                ("UPTIME_FORMATTED", basic_row.get("UPTIME_FORMATTED", "-"), "数据库已运行时长"),
            ]
            if binary_log_entry:
                base_rows.append(binary_log_entry)
                binary_log_entry = None
            rows[:0] = base_rows

        if binary_log_entry:
            rows[:0] = [binary_log_entry]

        if charset:
            charset_row = charset[0]
            rows.extend([
                ("SERVER_CHARSET", charset_row.get("SERVER_CHARSET", "-"), "服务器字符集"),
                ("SERVER_COLLATION", charset_row.get("SERVER_COLLATION", "-"), "服务器字符序"),
                ("DATABASE_CHARSET", charset_row.get("DATABASE_CHARSET", "-"), "数据库字符集"),
                ("DATABASE_COLLATION", charset_row.get("DATABASE_COLLATION", "-"), "数据库字符序"),
                ("CLIENT_CHARSET", charset_row.get("CLIENT_CHARSET", "-"), "客户端字符集"),
                ("CONNECTION_CHARSET", charset_row.get("CONNECTION_CHARSET", "-"), "连接字符集"),
            ])

        if not rows:
            return "## 3.2. 数据库配置\n\n暂未获取到数据库配置相关信息。\n"

        sections.append(self._render_table(rows))
        sections.append("")
        return "\n".join(sections)

    def _build_resource_config_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        connections = health.get("connection_info")
        mode = health.get("mode_info")
        innodb = health.get("innodb_buffer")
        connection_stats = health.get("connection_stats")

        sections: List[str] = ["## 3.3. 数据库资源相关配置", ""]

        rows: List[tuple] = []
        if connections:
            row = connections[0]
            rows.extend([
                ("MAX_CONNECTIONS", row.get("MAX_CONNECTIONS", "-"), "允许的最大连接数"),
                ("CURRENT_CONNECTIONS", row.get("CURRENT_CONNECTIONS", "-"), "当前连接数"),
                ("MAX_USER_CONNECTIONS", row.get("MAX_USER_CONNECTIONS", "-"), "用户级最大连接"),
            ])
        if mode:
            row = mode[0]
            rows.extend([
                ("AUTOCOMMIT", self._format_bool(row.get("AUTOCOMMIT")), "自动提交"),
                ("TRANSACTION_ISOLATION", row.get("TRANSACTION_ISOLATION", "-"), "事务隔离级别"),
                ("READ_ONLY", self._format_bool(row.get("READ_ONLY")), "只读模式"),
                ("SUPER_READ_ONLY", self._format_bool(row.get("SUPER_READ_ONLY")), "超级只读模式"),
            ])

        if innodb:
            kv = {row.get("VARIABLE_NAME"): row.get("VARIABLE_VALUE") for row in innodb if row.get("VARIABLE_NAME")}
            rows.extend([
                ("INNODB_BUFFER_POOL_PAGES_TOTAL", kv.get("Innodb_buffer_pool_pages_total", "-"), "Buffer Pool页总数"),
                ("INNODB_BUFFER_POOL_PAGES_FREE", kv.get("Innodb_buffer_pool_pages_free", "-"), "空闲页数"),
                ("INNODB_BUFFER_POOL_READ_REQUESTS", kv.get("Innodb_buffer_pool_read_requests", "-"), "读取请求数"),
            ])

        if connection_stats:
            row = connection_stats[0]
            rows.extend([
                ("TOTAL_CONNECTIONS", row.get("TOTAL_CONNECTIONS", "-"), "总连接数"),
                ("ACTIVE_CONNECTIONS", row.get("ACTIVE", "-"), "活动连接"),
                ("MAX_CONNECTION_TIME", row.get("MAX_CONNECTION_TIME", "-"), "最长连接时间(秒)"),
            ])

        if not rows:
            return "## 3.3. 数据库资源相关配置\n\n暂未获取到数据库资源相关信息。\n"

        sections.append(self._render_table(rows, header="| 配置项 | 配置值 | 说明 |"))
        sections.append("")
        return "\n".join(sections)

    def _build_os_check_section(self, meta_info: Dict[str, Any]) -> str:
        hostname = meta_info.get("hostname", "-")
        disk_info = self._load_hardware_info(meta_info).get("disk_space", [])
        sar_sections, sar_hostname = self._load_sar_sections(meta_info)
        output_dir = self._get_markdown_output_path(meta_info).parent
        sid = meta_info.get("sid", "mysql")

        hostname_display = sar_hostname or hostname

        cpu_section = self._build_cpu_usage_section(hostname_display, output_dir, sid, sar_sections.get("CPU"))
        memory_section = self._build_memory_usage_section(hostname_display, output_dir, sid, sar_sections.get("MEMORY"))
        disk_io_section = self._build_disk_io_section(hostname_display, output_dir, sid, sar_sections.get("DISK_IO"))
        disk_space_section = self._build_disk_space_section(hostname, disk_info)

        return f"""# 4. 操作系统检查

以下的部分是对操作系统的检查，可以从中确定一些性能方面的问题。这个分析主要使用的是操作系统自带的命令和工具。\n主要从以下方面来检查操作系统的性能：

- CPU 利用率
- 内存利用率
- 磁盘IO使用率
- 磁盘空间使用率

(这部分检查并不是针对操作系统或硬件的全面深入的检查，如有上述要求请与操作系统厂商联系)

{cpu_section}

{memory_section}

{disk_io_section}

{disk_space_section}

综合结论：【请填写结论】
"""

    def _build_database_main_info_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        basic_info = health.get("basic_info")
        charset_info = health.get("charset_info")
        mode_info = health.get("mode_info")

        sections: List[str] = ["# 5. 数据库主要信息检查", ""]

        sections.append(self._build_basic_info_subsection(basic_info))
        sections.append("")
        sections.append(self._build_charset_info_subsection(charset_info))
        sections.append("")
        sections.append(self._build_mode_status_subsection(mode_info))
        sections.append("")

        return "\n".join(part for part in sections if part is not None)

    def _build_user_privileges_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        user_accounts = health.get("user_account_basic")
        system_privileges = health.get("user_system_privileges")
        db_privileges = health.get("user_database_privileges")
        password_policy = health.get("user_password_policy")
        user_priv_maint_vertical = health.get("user_priv_maint_vertical")

        sections: List[str] = ["# 6. 数据库用户权限", ""]

        sections.append(self._build_user_basic_accounts_section(user_accounts))
        sections.append("")
        sections.append(self._build_user_system_privileges_section(system_privileges))
        sections.append("")
        sections.append(self._build_user_database_privileges_section(db_privileges))
        sections.append("")
        sections.append(self._build_user_password_policy_section(password_policy))
        sections.append("")
        sections.append(self._build_user_priv_maint_vertical_section(user_priv_maint_vertical))
        sections.append("")
        sections.append("综合结论：【留空给工程师写结论】")

        return "\n".join(part for part in sections if part is not None)

    def _build_db_performance_params_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        mem_params = health.get("perf_memory_params")
        innodb_mem_params = health.get("perf_innodb_memory_params")
        conn_thread_params = health.get("perf_conn_thread_params")
        other_params = health.get("perf_other_params")

        sections: List[str] = ["# 7. 数据库性能参数", ""]

        sections.append(self._build_perf_kv_subsection("## 7.1.内存相关参数 (Memory Parameters)", mem_params))
        sections.append("")
        sections.append(self._build_perf_kv_subsection("## 7.2.InnoDB内存参数", innodb_mem_params))
        sections.append("")
        sections.append(self._build_perf_kv_subsection("## 7.3.连接和线程参数", conn_thread_params))
        sections.append("")
        sections.append(self._build_perf_kv_subsection("## 7.4.其他性能参数", other_params))
        sections.append("")
        sections.append("综合结论：【留空给工程师写结论】")

        return "\n".join(part for part in sections if part is not None)

    def _build_db_log_paths_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        log_paths = health.get("log_paths")
        binary_log = health.get("binary_log_config")
        slow_log = health.get("slow_query_log_config")

        sections: List[str] = ["# 8. 数据库日志路径", ""]

        # 8.1 重要日志文件路径
        if log_paths:
            row = log_paths[0]
            desc = {
                "DATA_DIRECTORY": "数据目录",
                "TEMP_DIRECTORY": "临时目录",
                "GENERAL_LOG_FILE": "通用日志文件",
                "SLOW_QUERY_LOG_FILE": "慢查询日志文件",
                "ERROR_LOG_FILE": "错误日志文件",
            }
            table = self._render_vertical_table_auto(row, description_map=desc)
            sections.append("## 8.1.重要日志文件路径\n\n" + table + "\n")
        else:
            sections.append("## 8.1.重要日志文件路径\n\n暂未获取到重要日志文件路径信息。\n")

        # 8.2 二进制日志配置
        if binary_log:
            row = binary_log[0]
            desc = {
                "BINARY_LOG_ENABLED": "是否启用二进制日志",
                "LOG_BIN_BASENAME": "二进制日志基名",
                "LOG_BIN_INDEX": "二进制日志索引文件",
                "BINLOG_FORMAT": "二进制日志格式",
                "EXPIRE_LOGS_DAYS": "过期清理天数",
                "MAX_BINLOG_SIZE_MB": "单个日志最大(MB)",
                "SYNC_BINLOG": "写入同步级别",
            }
            fmt = {k: self._format_numeric_compact for k in row.keys()}
            table = self._render_vertical_table_auto(row, description_map=desc, formatters=fmt)
            sections.append("## 8.2.二进制日志配置\n\n" + table + "\n")
        else:
            sections.append("## 8.2.二进制日志配置\n\n暂未获取到二进制日志配置。\n")

        # 8.3 慢查询日志配置
        if slow_log:
            row = slow_log[0]
            desc = {
                "SLOW_QUERY_LOG_ENABLED": "是否启用慢日志",
                "LONG_QUERY_TIME": "慢日志阈值(秒)",
                "LOG_QUERIES_NOT_USING_INDEXES": "记录未用索引",
                "LOG_THROTTLE_QUERIES_NOT_USING_INDEXES": "未用索引限速",
                "MIN_EXAMINED_ROW_LIMIT": "最少扫描行数",
            }
            fmt = {k: self._format_numeric_compact for k in row.keys()}
            table = self._render_vertical_table_auto(row, description_map=desc, formatters=fmt)
            sections.append("## 8.3.慢查询日志配置\n\n" + table + "\n")
        else:
            sections.append("## 8.3.慢查询日志配置\n\n暂未获取到慢查询日志配置信息。\n")

        sections.append("综合结论：【留空给工程师写结论】")

        return "\n".join(sections)

    def _build_db_status_checks_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)
        db_stats = health.get("database_stats")
        top_dbs = health.get("top_databases")
        top_tables = health.get("top_tables")
        no_pk_tables = health.get("diag_no_primary_key")
        high_fragment_tables = health.get("diag_high_fragmentation")
        high_auto_inc_tables = health.get("diag_high_auto_inc_usage")
        large_txn_tables = health.get("diag_large_transactions")

        sections: List[str] = ["# 9. 数据库状态检查", ""]

        # 9.1 数据库大小统计 (列转行)
        if db_stats:
            row = db_stats[0]
            desc = {
                "DATABASE_COUNT": "数据库数量",
                "TABLE_COUNT": "表数量",
                "TOTAL_SIZE_MB": "总大小(MB)",
                "DATA_SIZE_MB": "数据大小(MB)",
                "INDEX_SIZE_MB": "索引大小(MB)",
                "FREE_SIZE_MB": "空闲空间(MB)",
            }
            fmt = {k: self._format_numeric_compact for k in row.keys()}
            table = self._render_vertical_table_auto(row, description_map=desc, formatters=fmt)
            sections.append("## 9.1.数据库大小统计\n\n" + table + "\n")
        else:
            sections.append("## 9.1.数据库大小统计\n\n暂未获取到数据库大小统计信息。\n")

        # 9.2 各数据库大小排名 (行展示)
        if top_dbs:
            table = self._render_dict_table(top_dbs)
            sections.append("## 9.2.各数据库大小排名 (TOP 10)\n\n" + table + "\n")
        else:
            sections.append("## 9.2.各数据库大小排名 (TOP 10)\n\n暂未获取到各数据库大小排名。\n")

        # 9.3 表大小排名 (行展示)
        if top_tables:
            table = self._render_dict_table(top_tables)
            sections.append("## 9.3.表大小排名 (TOP 20)\n\n" + table + "\n")
        else:
            sections.append("## 9.3.表大小排名 (TOP 20)\n\n暂未获取到表大小排名信息。\n")

        # 9.4 无主键的表 (行展示)
        if no_pk_tables:
            table = self._render_dict_table(no_pk_tables)
            sections.append("## 9.4.无主键的表 (TOP 20)\n\n" + table + "\n")
        else:
            sections.append("## 9.4.无主键的表 (TOP 20)\n\n暂无无主键的表信息。\n")

        # 9.5 碎片率高的表 (行展示)
        if high_fragment_tables:
            table = self._render_dict_table(high_fragment_tables)
            sections.append("## 9.5.碎片率高的表 (碎片率>30%, TOP 20)\n\n" + table + "\n")
        else:
            sections.append("## 9.5.碎片率高的表 (碎片率>30%, TOP 20)\n\n暂无高碎片率表信息。\n")

        # 9.6 自增ID使用率高的表 (行展示)
        if high_auto_inc_tables:
            table = self._render_dict_table(high_auto_inc_tables)
            sections.append("## 9.6.自增ID使用率高的表 (使用率>70%, TOP 20)\n\n" + table + "\n")
        else:
            sections.append("## 9.6.自增ID使用率高的表 (使用率>70%, TOP 20)\n\n暂无高使用率自增表信息。\n")

        # 9.7 大事务检测 (行展示)
        if large_txn_tables:
            table = self._render_dict_table(large_txn_tables)
            sections.append("## 9.7.大事务检测 (修改行数>10000)\n\n" + table + "\n")
        else:
            sections.append("## 9.7.大事务检测 (修改行数>10000)\n\n暂无大事务信息。\n")

        # 9.8 缓慢SQL列表（前20条）(行展示)
        slow_sql = health.get("slow_sql_top20")
        if slow_sql:
            header_map = {
                "db": "DB",
                "sample_sql": "示例SQL",
                "exec_count": "执行次数",
                "total_s": "总耗时(s)",
                "avg_s": "平均耗时(s)",
            }
            columns = [col for col in ["db", "sample_sql", "exec_count", "total_s", "avg_s"] if col in slow_sql[0]]
            table = self._render_dict_table(slow_sql, columns=columns, header_map=header_map)
            sections.append("## 9.8.缓慢SQL列表（前20条）\n\n" + table + "\n")
        else:
            sections.append("## 9.8.缓慢SQL列表（前20条）\n\n暂无缓慢SQL列表信息。\n")

        sections.append("综合结论：【留空给工程师写结论】")

        return "\n".join(sections)

    def _build_perf_kv_subsection(self, title: str, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return f"{title}\n\n暂未获取到相关参数信息。\n"

        # 这些表通常只有一行，按列转行展示
        row = rows[0]
        desc_map = self._get_perf_param_descriptions()
        fmt = {k: self._format_numeric_compact for k in row.keys()}
        table = self._render_vertical_table_auto(row, description_map=desc_map, formatters=fmt)
        return f"{title}\n\n{table}\n"

    def _build_basic_info_subsection(self, basic_info: Optional[List[Dict[str, Any]]]) -> str:
        if not basic_info:
            return "## 5.1.数据库实例基本信息\n\n暂未获取到数据库实例基本信息。\n"

        row = basic_info[0]
        table = self._render_vertical_table(
            row,
            [
                ("HOSTNAME", "HOSTNAME", "数据库主机名"),
                ("PORT", "PORT", "数据库端口"),
                ("VERSION", "VERSION", "数据库版本"),
                ("VERSION_COMMENT", "VERSION_COMMENT", "版本注释"),
                ("COMPILE_OS", "COMPILE_OS", "编译操作系统"),
                ("COMPILE_MACHINE", "COMPILE_MACHINE", "编译架构"),
                ("CHECK_TIME", "CHECK_TIME", "检查时间"),
                ("UPTIME_SECONDS", "UPTIME_SECONDS", "数据库已运行(秒)"),
                ("UPTIME_FORMATTED", "UPTIME_FORMATTED", "数据库已运行时长"),
            ],
        )

        return f"## 5.1.数据库实例基本信息\n\n{table}\n"

    def _build_charset_info_subsection(self, charset_info: Optional[List[Dict[str, Any]]]) -> str:
        if not charset_info:
            return "## 5.2.数据库字符集信息\n\n暂未获取到数据库字符集信息。\n"

        row = charset_info[0]
        table = self._render_vertical_table(
            row,
            [
                ("SERVER_CHARSET", "SERVER_CHARSET", "服务器字符集"),
                ("SERVER_COLLATION", "SERVER_COLLATION", "服务器字符序"),
                ("DATABASE_CHARSET", "DATABASE_CHARSET", "数据库字符集"),
                ("DATABASE_COLLATION", "DATABASE_COLLATION", "数据库字符序"),
                ("CLIENT_CHARSET", "CLIENT_CHARSET", "客户端字符集"),
                ("CONNECTION_CHARSET", "CONNECTION_CHARSET", "连接字符集"),
            ],
        )

        return f"## 5.2.数据库字符集信息\n\n{table}\n"

    def _build_mode_status_subsection(self, mode_info: Optional[List[Dict[str, Any]]]) -> str:
        if not mode_info:
            return "## 5.3.数据库模式和状态\n\n暂未获取到数据库模式和状态信息。\n"

        row = mode_info[0]
        table = self._render_vertical_table(
            row,
            [
                ("SQL_MODE", "SQL_MODE", "SQL_MODE设置"),
                ("AUTOCOMMIT", "AUTOCOMMIT", "自动提交开关"),
                ("TRANSACTION_ISOLATION", "TRANSACTION_ISOLATION", "事务隔离级别"),
                ("READ_ONLY", "READ_ONLY", "实例只读模式"),
                ("SUPER_READ_ONLY", "SUPER_READ_ONLY", "超级只读模式"),
            ],
            formatters={
                "SQL_MODE": self._wrap_sql_mode,
                "AUTOCOMMIT": self._format_bool,
                "READ_ONLY": self._format_bool,
                "SUPER_READ_ONLY": self._format_bool,
            },
        )

        return f"## 5.3.数据库模式和状态\n\n{table}\n"

    def _build_user_basic_accounts_section(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return "## 6.1.用户账户基本信息\n\n暂未获取到用户账户基本信息。\n"

        columns = [
            "USER",
            "HOST",
            "AUTH_PLUGIN",
            "PWD_LAST_CHANGED",
            "ACCOUNT_LOCKED",
        ]
        available = [col for col in columns if col in rows[0]]
        table = self._render_dict_table(rows, columns=available)

        return f"## 6.1.用户账户基本信息\n\n{table}\n"

    def _build_user_system_privileges_section(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return "## 6.2.用户系统权限汇总\n\n暂未获取到用户系统权限信息。\n"

        table = self._render_dict_table(rows)
        return f"## 6.2.用户系统权限汇总\n\n{table}\n"

    def _build_user_database_privileges_section(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return "## 6.3.数据库级别权限\n\n暂未获取到数据库级别权限信息。\n"

        table = self._render_dict_table(rows)
        return f"## 6.3.数据库级别权限\n\n{table}\n"

    def _build_user_password_policy_section(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return "## 6.4.密码策略和账户状态检查\n\n暂未获取到密码策略和账户状态信息。\n"

        table = self._render_dict_table(rows)
        return f"## 6.4.密码策略和账户状态检查\n\n{table}\n"

    def _build_user_priv_maint_vertical_section(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return "## 6.5.用户权限与维护状态\n\n暂未获取到用户权限与维护状态信息。\n"
        table = self._render_dict_table(rows)
        return f"## 6.5.用户权限与维护状态\n\n{table}\n"

    def _render_vertical_table(
        self,
        row: Dict[str, Any],
        items: List[Tuple[str, str, str]],
        formatters: Optional[Dict[str, Callable[[Any], Any]]] = None,
    ) -> str:
        lines = ["| 配置项 | 配置值 | 说明 |", "|---|---|---|"]
        formatters = formatters or {}

        for key, display_key, description in items:
            raw_value = row.get(key, "-")
            formatter = formatters.get(key)
            value = formatter(raw_value) if formatter else raw_value
            display = self._safe_value(value)
            lines.append(f"| {display_key} | {display} | {description} |")

        return "\n".join(lines)

    def _render_vertical_table_auto(
        self,
        row: Dict[str, Any],
        description_map: Optional[Dict[str, str]] = None,
        formatters: Optional[Dict[str, Callable[[Any], Any]]] = None,
    ) -> str:
        description_map = description_map or {}
        items: List[Tuple[str, str, str]] = [
            (key, key, description_map.get(key, "-")) for key in row.keys()
        ]
        return self._render_vertical_table(row, items, formatters)

    @staticmethod
    def _format_numeric_compact(value: Any) -> str:
        if value in (None, ""):
            return "-"
        s = str(value).strip()
        upper = s.upper()
        if upper in ("NULL", "N/A", "INF", "NAN"):
            return s
        # trim trailing zeros in decimal representations
        try:
            if "." in s:
                # keep only digits, one dot and optional leading sign
                # if it's a pure decimal representation, trim zeros
                # fallback to Decimal for correctness
                from decimal import Decimal, InvalidOperation
                try:
                    d = Decimal(s)
                    s2 = format(d.normalize(), 'f')
                except InvalidOperation:
                    # not a pure decimal string
                    return s
                s2 = s2.rstrip('0').rstrip('.')
                return s2 if s2 else "0"
            else:
                return s
        except Exception:
            return s

    @staticmethod
    def _get_perf_param_descriptions() -> Dict[str, str]:
        return {
            # B1 Memory Parameters
            "KEY_BUFFER_SIZE_MB": "MyISAM键缓存大小(MB)",
            "TMP_TABLE_SIZE_MB": "临时表大小上限(MB)",
            "MAX_HEAP_TABLE_SIZE_MB": "内存表最大大小(MB)",
            "SORT_BUFFER_SIZE_MB": "排序缓冲区(MB)",
            "JOIN_BUFFER_SIZE_MB": "连接缓冲区(MB)",
            "READ_BUFFER_SIZE_MB": "顺序读缓冲(MB)",
            "READ_RND_BUFFER_SIZE_MB": "随机读缓冲(MB)",

            # B2 InnoDB Memory
            "INNODB_BUFFER_POOL_SIZE_GB": "InnoDB缓冲池大小(GB)",
            "BUFFER_POOL_INSTANCES": "缓冲池实例数",
            "INNODB_LOG_BUFFER_SIZE_MB": "InnoDB日志缓冲(MB)",
            "INNODB_SORT_BUFFER_SIZE_MB": "InnoDB排序缓冲(MB)",
            "INNODB_PAGE_SIZE_KB": "InnoDB页大小(KB)",

            # B3 Connections/Threads
            "MAX_CONNECTIONS": "最大连接数",
            "MAX_CONNECT_ERRORS": "最大连接错误数",
            "CONNECT_TIMEOUT": "连接超时(秒)",
            "WAIT_TIMEOUT": "空闲连接超时(秒)",
            "INTERACTIVE_TIMEOUT": "交互式超时(秒)",
            "THREAD_CACHE_SIZE": "线程缓存大小",
            "THREAD_STACK_KB": "线程栈大小(KB)",

            # B4 Other
            "TABLE_OPEN_CACHE": "表缓存大小",
            "TABLE_DEFINITION_CACHE": "表定义缓存",
            "OPEN_FILES_LIMIT": "打开文件上限",
            "MAX_ALLOWED_PACKET_MB": "最大允许包大小(MB)",
        }

    @staticmethod
    def _render_dict_table(
        rows: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        header_map: Optional[Dict[str, str]] = None,
    ) -> str:
        if not rows:
            return ""

        header_map = header_map or {}
        if columns:
            column_order = [col for col in columns if col in rows[0]]
        else:
            column_order = list(rows[0].keys())

        if not column_order:
            return ""

        header = "|" + "|".join(f" {header_map.get(col, col)} " for col in column_order) + "|"
        divider = "|" + "|".join(["---"] * len(column_order)) + "|"

        lines = [header, divider]
        for row in rows:
            cells = [f" {MarkdownGenerator._safe_value(row.get(col, '-'))} " for col in column_order]
            lines.append("|" + "|".join(cells) + "|")

        return "\n".join(lines)

    @staticmethod
    def _render_kv_rows_with_description(
        rows: List[Dict[str, Any]],
        name_key: str,
        value_key: str,
        desc_map: Optional[Dict[str, str]] = None,
        value_formatter: Optional[Callable[[Any], Any]] = None,
    ) -> str:
        if not rows:
            return ""
        desc_map = desc_map or {}
        lines = ["| 配置项 | 配置值 | 说明 |", "|---|---|---|"]
        for row in rows:
            name = row.get(name_key, "-")
            raw_val = row.get(value_key, "-")
            val = value_formatter(raw_val) if value_formatter else raw_val
            display = MarkdownGenerator._safe_value(val)
            desc = desc_map.get(name, "-")
            lines.append(f"| {name} | {display} | {desc} |")
        return "\n".join(lines)

    @staticmethod
    def _render_kv_many_with_description(
        sources: List[Tuple[Optional[List[Dict[str, Any]]], str, str]],
        desc_map: Optional[Dict[str, str]] = None,
        value_formatter: Optional[Callable[[Any], Any]] = None,
    ) -> str:
        desc_map = desc_map or {}
        lines: List[str] = ["| 配置项 | 配置值 | 说明 |", "|---|---|---|"]
        count = 0
        for rows, name_key, value_key in sources:
            if not rows:
                continue
            for row in rows:
                name = row.get(name_key, "-")
                raw_val = row.get(value_key, "-")
                val = value_formatter(raw_val) if value_formatter else raw_val
                display = MarkdownGenerator._safe_value(val)
                desc = desc_map.get(name, "-")
                lines.append(f"| {name} | {display} | {desc} |")
                count += 1
        return "\n".join(lines) if count > 0 else ""

    @staticmethod
    def _get_innodb_status_desc_map() -> Dict[str, str]:
        return {
            # Query stats
            "Questions": "累计查询数",
            "Slow_queries": "慢查询计数",
            "Select_scan": "全表扫描次数",
            "Select_full_join": "全连接次数",
            "Sort_merge_passes": "排序归并次数",
            "Sort_scan": "排序扫描次数",
            # Table lock stats
            "Table_locks_immediate": "立即获取表锁次数",
            "Table_locks_waited": "等待表锁次数",
            "Table_open_cache_hits": "表缓存命中",
            "Table_open_cache_misses": "表缓存未命中",
            "Table_open_cache_overflows": "表缓存溢出",
            # InnoDB metrics
            "Innodb_data_reads": "数据读次数",
            "Innodb_data_writes": "数据写次数",
            "Innodb_log_waits": "日志写等待次数",
            "Innodb_os_log_written": "日志写入字节",
            "Innodb_row_lock_time": "行锁耗时(毫秒)",
            "Innodb_row_lock_time_avg": "平均行锁耗时(毫秒)",
            "Innodb_row_lock_waits": "行锁等待次数",
            "Innodb_rows_deleted": "删除行数",
            "Innodb_rows_inserted": "插入行数",
            "Innodb_rows_read": "读取行数",
            "Innodb_rows_updated": "更新行数",
            # Hit rates
            "InnoDB Buffer Pool Hit Rate": "缓冲池命中率(%)",
            "Thread Cache Hit Rate": "线程缓存命中率(%)",
            "Table Open Cache Hit Rate": "表缓存命中率(%)",
            # Buffer pool status
            "Innodb_buffer_pool_pages_dirty": "脏页数量",
            "Innodb_buffer_pool_pages_flushed": "已刷新页累计",
            "Innodb_buffer_pool_pages_free": "空闲页数",
            "Innodb_buffer_pool_pages_total": "总页数",
            "Innodb_buffer_pool_read_requests": "逻辑读请求次数",
            "Innodb_buffer_pool_reads": "物理读次数",
            "Innodb_buffer_pool_wait_free": "等待空闲页次数",
            "Innodb_buffer_pool_write_requests": "写请求次数",
            # Detail metrics (Chinese headers under 指标)
            "History List Length": "历史列表长度",
            "Queries Inside": "InnoDB内部活动数",
            "Queries In Queue": "等待队列中的请求",
            "总大小": "缓冲池总大小",
            "空闲页": "空闲页数",
            "数据页": "数据页数",
            "脏页": "脏页数",
            "命中率": "缓冲池命中率",
            # InnoDB I/O统计（5.3）
            "OS File Reads": "操作系统层文件读取次数",
            "OS File Writes": "操作系统层文件写入次数",
            "OS Fsyncs": "fsync系统调用次数",
            "读取速率": "当前读取吞吐速率",
            "写入速率": "当前写入吞吐速率",
            "Fsync速率": "当前fsync调用速率",
            # InnoDB 行操作统计（5.4）
            "Rows Inserted": "插入行数",
            "Rows Updated": "更新行数",
            "Rows Deleted": "删除行数",
            "Rows Read": "读取行数",
            # InnoDB 日志状态（5.5）
            "LSN": "当前日志序列号(Log Sequence Number)",
            "Flushed LSN": "已刷新到磁盘的日志序列号",
            "Last Checkpoint": "最近检查点的日志序列号",
        }

    def _build_innodb_status_section(self, meta_info: Dict[str, Any]) -> str:
        health = self._load_health_check_data(meta_info)

        # 10.1 sources
        innodb_bp = health.get("innodb_buffer")
        qs = health.get("perf_query_stats")
        tls = health.get("perf_table_lock_stats")
        im = health.get("perf_innodb_metrics")
        hr = health.get("perf_cache_hit_rates")

        # 10.2 sources
        d_key = health.get("innodb_detail_key_metrics")
        d_bp = health.get("innodb_detail_bp_summary")
        d_io = health.get("innodb_detail_io_stats")
        d_row = health.get("innodb_detail_row_ops")
        d_log = health.get("innodb_detail_log_status")

        desc_map = self._get_innodb_status_desc_map()

        def sec10_table(rows: Optional[List[Dict[str, Any]]], name_key: str, value_key: str) -> str:
            if not rows:
                return ""
            return self._render_kv_rows_with_description(
                rows,
                name_key=name_key,
                value_key=value_key,
                desc_map=desc_map,
                value_formatter=self._format_numeric_compact,
            )

        parts: List[str] = ["# 10.InnoDB Status", ""]

        # 10.1 合并为一个表
        table_10_1 = self._render_kv_many_with_description(
            [
                (innodb_bp, "VARIABLE_NAME", "VARIABLE_VALUE"),
                (qs, "VARIABLE_NAME", "VARIABLE_VALUE"),
                (tls, "VARIABLE_NAME", "VARIABLE_VALUE"),
                (im, "VARIABLE_NAME", "VARIABLE_VALUE"),
                (hr, "METRIC", "VALUE_PERCENT"),
            ],
            desc_map=desc_map,
            value_formatter=self._format_numeric_compact,
        )
        if table_10_1:
            parts.append("## 10.1.InnoDB Buffer Pool状态\n\n" + table_10_1 + "\n")
        else:
            parts.append("## 10.1.InnoDB Buffer Pool状态\n\n暂未获取到InnoDB相关状态。\n")

        # 10.2 合并为一个表
        table_10_2 = self._render_kv_many_with_description(
            [
                (d_key, "指标", "值"),
                (d_bp, "指标", "值"),
                (d_io, "指标", "值"),
                (d_row, "指标", "值"),
                (d_log, "指标", "值"),
            ],
            desc_map=desc_map,
            value_formatter=self._format_numeric_compact,
        )
        if table_10_2:
            parts.append("## 10.2.InnoDB引擎详细状态信息\n\n" + table_10_2 + "\n")
        else:
            parts.append("## 10.2.InnoDB引擎详细状态信息\n\n暂未获取到InnoDB引擎详细状态。\n")

        parts.append("综合结论：【留空给工程师写结论】")
        return "\n".join(parts)

    def _build_cpu_usage_section(self, hostname: str, output_dir: Path, sid: str, cpu_content: Optional[str]) -> str:
        if not cpu_content:
            return """## 4.1.CPU使用率

未找到CPU使用率数据"""

        chart = self._generate_cpu_chart(cpu_content, output_dir, hostname, sid)

        return f"""## 4.1.CPU使用率

**以下是**计算节点 {hostname} **的CPU使用情况：**

{chart}
"""

    def _build_memory_usage_section(self, hostname: str, output_dir: Path, sid: str, memory_content: Optional[str]) -> str:
        if not memory_content:
            return """## 4.2.内存使用率

未找到内存使用率数据"""

        chart = self._generate_memory_chart(memory_content, output_dir, hostname, sid)

        return f"""## 4.2.内存使用率

**以下是**计算节点 {hostname} **的内存使用情况：**

{chart}
"""

    def _build_disk_io_section(self, hostname: str, output_dir: Path, sid: str, disk_io_content: Optional[str]) -> str:
        if not disk_io_content:
            return """## 4.3.磁盘IO使用率

未找到磁盘IO使用率数据"""

        chart = self._generate_disk_io_chart(disk_io_content, output_dir, hostname, sid)

        return f"""## 4.3.磁盘IO使用率

**以下是**计算节点 {hostname} **的磁盘IO使用情况：**

{chart}
"""

    def _build_disk_space_section(self, hostname: str, disk_info: List[Dict[str, Any]]) -> str:
        table = self._generate_disk_space_table(disk_info)
        if not table:
            return """## 4.4.磁盘空间使用率

未找到磁盘空间使用率数据"""

        return f"""## 4.4.磁盘空间使用率

**以下是**计算节点 {hostname} **的磁盘空间使用率：**

{table}
"""

    def _prepare_matplotlib(self, base_dir: Path) -> None:
        try:
            mpl_config_dir = base_dir / "assets" / "mplconfig"
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

                    # 统一时间显示为 HH:MM
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
                    if is_english_format and len(parts) >= 12:
                        time_str = parts[0]
                        kbmemfree = int(parts[2])
                        kbmemused = int(parts[3])
                        memused_pct = float(parts[4])
                        kbbuffers = int(parts[5])
                        kbcached = int(parts[6])
                        kbcommit = int(parts[7])
                        commit_pct = float(parts[8])
                        kbactive = int(parts[9])
                        kbinact = int(parts[10])
                        kbdirty = int(parts[11])
                    elif is_chinese_format and len(parts) >= 11:
                        time_str = parts[0]
                        kbmemfree = int(parts[1])
                        kbmemused = int(parts[2])
                        memused_pct = float(parts[3])
                        kbbuffers = int(parts[4])
                        kbcached = int(parts[5])
                        kbcommit = int(parts[6])
                        commit_pct = float(parts[7])
                        kbactive = int(parts[8])
                        kbinact = int(parts[9])
                        kbdirty = int(parts[10])
                    else:
                        continue

                    # 统一时间显示为 HH:MM
                    time_display = normalize_time_label(time_str)

                    chart_data.append((time_display, kbmemfree, kbmemused, memused_pct, kbbuffers, kbcached, kbcommit, commit_pct, kbactive, kbinact, kbdirty))
                except (ValueError, IndexError):
                    continue

        if not chart_data:
            return f"```text\n{memory_data}\n```"

        self._prepare_matplotlib(output_dir)
        server_picture_dir = output_dir / "server_picture"
        server_picture_dir.mkdir(exist_ok=True)

        chart_filename = "memory_usage_chart.png"
        chart_path = server_picture_dir / chart_filename

        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax1 = plt.subplots(figsize=(12, 6))

        times = [data[0] for data in chart_data]
        memused_pct_data = [data[3] for data in chart_data]
        commit_pct_data = [data[7] for data in chart_data]

        kb_to_gb = lambda value: value / (1024 ** 2)

        kbmemfree_data = [kb_to_gb(data[1]) for data in chart_data]
        kbmemused_data = [kb_to_gb(data[2]) for data in chart_data]
        kbbuffers_data = [kb_to_gb(data[4]) for data in chart_data]
        kbcached_data = [kb_to_gb(data[5]) for data in chart_data]
        kbcommit_data = [kb_to_gb(data[6]) for data in chart_data]
        kbactive_data = [kb_to_gb(data[8]) for data in chart_data]
        kbinact_data = [kb_to_gb(data[9]) for data in chart_data]
        kbdirty_data = [kb_to_gb(data[10]) for data in chart_data]

        # 使用索引绘图，并在最后统一设置抽稀后的刻度与旋转
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
        ax2.plot(x, kbactive_data, color='#17becf', linestyle='-.', linewidth=1.2, label='活跃内存 (GB)', alpha=0.7)
        ax2.plot(x, kbinact_data, color='#bcbd22', linestyle='-.', linewidth=1.2, label='非活跃内存 (GB)', alpha=0.7)
        ax2.plot(x, kbdirty_data, color='#7f7f7f', linestyle=':', linewidth=1.2, label='脏页 (GB)', alpha=0.7)
        ax2.set_ylabel('内存 (GB)', fontsize=12)
        ax2.tick_params(axis='y')

        ax1.set_title(f'内存使用率趋势图 (8:00-12:00) - {hostname}', fontsize=14, fontweight='bold', pad=20)
        ax1.set_xlabel('时间', fontsize=12)
        ax1.grid(True, alpha=0.3)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, bbox_to_anchor=(1.05, 1), loc='upper left')

        # 对齐双轴x范围，避免刻度与数据错位
        align_twinx_xlim(ax1, ax2)
        plt.tight_layout()

        try:
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(f"内存图表已保存到: {chart_path}")
            return f"![内存使用率趋势图](./server_picture/{chart_filename})"
        except Exception as exc:
            logger.error(f"保存内存图表失败: {exc}")
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
                        time_display = time_str.replace('时', ':').replace('分01秒', '').replace('分02秒', '')
                    else:
                        time_display = time_str[:5]

                    chart_data.append((time_display, tps, rtps, wtps, bread_s, bwrtn_s))
                except (ValueError, IndexError):
                    continue

        if not chart_data:
            return f"```text\n{disk_io_data}\n```"

        self._prepare_matplotlib(output_dir)
        server_picture_dir = output_dir / "server_picture"
        server_picture_dir.mkdir(exist_ok=True)

        chart_filename = "disk_io_chart.png"
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
            logger.info(f"磁盘IO图表已保存到: {chart_path}")
            return f"![磁盘IO使用率趋势图](./server_picture/{chart_filename})"
        except Exception as exc:
            logger.error(f"保存磁盘IO图表失败: {exc}")
            plt.close()
            return f"```text\n{disk_io_data}\n```"

    def _load_sar_sections(self, meta_info: Dict[str, Any]) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
        files = meta_info.get("files", {}) or {}
        sar_entry = files.get("10_sar_report")
        if not sar_entry:
            return {"CPU": None, "MEMORY": None, "DISK_IO": None}, None

        path = sar_entry.get("path")
        if not path:
            return {"CPU": None, "MEMORY": None, "DISK_IO": None}, None

        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            logger.warning("无法读取 MySQL SAR 数据: %s", path)
            return {"CPU": None, "MEMORY": None, "DISK_IO": None}, None

        sections: Dict[str, List[str]] = {"CPU": [], "MEMORY": [], "DISK_IO": []}
        current_key: Optional[str] = None
        buffer: List[str] = []
        sar_hostname: Optional[str] = None

        def flush(target: Optional[str]) -> None:
            nonlocal buffer
            if target and buffer:
                sections[target] = buffer.copy()
            buffer = []

        for line in text.splitlines():
            if sar_hostname is None and line.startswith("Linux ") and '(' in line and ')' in line:
                try:
                    sar_hostname = line.split('(')[1].split(')')[0].strip()
                except Exception:
                    sar_hostname = None
            if line.startswith("== CPU"):
                flush(current_key)
                current_key = "CPU"
                continue
            if line.startswith("== 内存"):
                flush(current_key)
                current_key = "MEMORY"
                continue
            if line.startswith("== 磁盘 I/O"):
                flush(current_key)
                current_key = "DISK_IO"
                continue
            if current_key:
                buffer.append(line)

        flush(current_key)

        return ({key: "\n".join(lines).strip() if lines else None for key, lines in sections.items()}, sar_hostname)

    def _load_hardware_info(self, meta_info: Dict[str, Any]) -> Dict[str, Any]:
        files = meta_info.get("files", {}) or {}
        hardware_entry = files.get("02_hardware_info")
        if not hardware_entry:
            return {}

        path = hardware_entry.get("path")
        if not path:
            return {}

        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            return json.loads(text) if text else {}
        except Exception:
            logger.warning("无法读取 MySQL 硬件信息文件: %s", path)
            return {}

    def _load_system_info(self, meta_info: Dict[str, Any]) -> Dict[str, str]:
        files = meta_info.get("files", {}) or {}
        system_entry = files.get("01_system_info")
        if not system_entry:
            return {}

        path = system_entry.get("path")
        if not path:
            return {}

        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            logger.warning("无法读取 MySQL 系统信息文件: %s", path)
            return {}

        sections: Dict[str, str] = {}
        current_key: Optional[str] = None
        buffer: List[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            header = re.match(r"^=+\s*(.+?)\s*=+$", stripped)
            if header:
                if current_key:
                    sections[current_key] = "\n".join(buffer).strip()
                current_key = header.group(1)
                buffer = []
                continue
            if current_key:
                buffer.append(line.rstrip())

        if current_key:
            sections[current_key] = "\n".join(buffer).strip()

        # 提取感兴趣的段落，仅返回需要的键
        wanted_keys = {
            "系统版本信息": "系统版本信息",
            "内核版本": "内核版本",
            "生效的内核参数": "生效的内核参数",
            "资源限制参数": "资源限制参数",
            "磁盘调度算法": "磁盘调度算法",
            "系统启动时间和负载": "系统启动时间和负载",
        }

        result = {}
        for src_key, dst_key in wanted_keys.items():
            value = sections.get(src_key, "").strip()
            # 去除多余空行
            value = "\n".join([ln for ln in value.splitlines() if ln.strip()]) if value else ""
            result[dst_key] = value

        return result

    def _load_health_check_data(self, meta_info: Dict[str, Any]) -> Dict[str, Any]:
        files = meta_info.get("files", {}) or {}
        health_entry = files.get("04_health_check")
        if not health_entry:
            return {}

        path = health_entry.get("path")
        if not path:
            return {}

        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            logger.warning("无法读取 MySQL 健康检查文件: %s", path)
            return {}

        lines = text.splitlines()

        def table(marker: str) -> List[Dict[str, str]]:
            tbl_lines = self._extract_table_lines(lines, marker)
            return self._parse_ascii_table(tbl_lines)

        data = {
            "basic_info": table("A1. 数据库实例基本信息"),
            "connection_info": table("A2. 数据库连接和用户信息"),
            "charset_info": table("A3. 数据库字符集信息"),
            "mode_info": table("A4. 数据库模式和状态"),
            "log_paths": table("C1. 重要日志文件路径"),
            "slow_query_log_config": table("C3. 慢查询日志配置"),
            "binary_log_config": table("C2. 二进制日志配置"),
            "database_stats": table("1. 数据库大小统计"),
            "top_databases": table("2. 各数据库大小排名"),
            "top_tables": table("3. 表大小排名"),
            "storage_engines": table("4. 存储引擎使用情况"),
            "innodb_buffer": table("5. InnoDB Buffer Pool状态"),
            "perf_query_stats": table("1. 查询统计"),
            "perf_table_lock_stats": table("2. 表锁统计"),
            "perf_innodb_metrics": table("3. InnoDB性能指标"),
            "perf_cache_hit_rates": table("4. 缓存命中率"),
            "connection_stats": table("6. 连接状态统计"),
            "user_account_basic": table("1. 用户账户基本信息"),
            "user_system_privileges": table("2. 用户系统权限汇总"),
            "user_database_privileges": table("3. 数据库级别权限"),
            "user_password_policy": table("4. 密码策略和账户状态检查"),
            "user_priv_maint_vertical": table("12V. 用户权限与维护状态（纵向展示，便于阅读）"),
            "perf_memory_params": table("B1. 内存相关参数 (Memory Parameters)"),
            "perf_innodb_memory_params": table("B2. InnoDB内存参数"),
            "perf_conn_thread_params": table("B3. 连接和线程参数"),
            "perf_other_params": table("B4. 其他性能参数"),
            "user_connections_by_user": table("7. 按用户统计连接"),
            "lock_waits": table("8. 当前锁等待信息"),
            "slow_query_stats": table("10. 慢查询统计"),
            "processlist": table("11. 进程列表（SHOW PROCESSLIST）"),
            "diag_no_primary_key": table("1. 无主键的表 (TOP 20)"),
            "diag_high_fragmentation": table("2. 碎片率高的表 (碎片率>30%, TOP 20)"),
            "diag_high_auto_inc_usage": table("3. 自增ID使用率高的表 (使用率>70%, TOP 20)"),
            "diag_large_transactions": table("4. 大事务检测 (修改行数>10000)"),
            "slow_sql_top20": table("4.1 缓慢SQL列表（前20条）"),
            "innodb_detail_key_metrics": table("5.1 InnoDB关键性能指标"),
            "innodb_detail_bp_summary": table("5.2 InnoDB Buffer Pool汇总"),
            "innodb_detail_io_stats": table("5.3 InnoDB I/O统计"),
            "innodb_detail_row_ops": table("5.4 InnoDB行操作统计"),
            "innodb_detail_log_status": table("5.5 InnoDB日志状态"),
        }

        return data

    def _extract_table_lines(self, lines: List[str], marker: str) -> List[str]:
        start_idx = None
        for idx, line in enumerate(lines):
            if marker in line:
                start_idx = idx + 1
                break
        if start_idx is None:
            return []

        table_lines: List[str] = []
        for line in lines[start_idx:]:
            if not line.strip():
                if table_lines:
                    break
                continue
            if line.startswith('+') or line.startswith('|'):
                table_lines.append(line.rstrip())
                continue
            if table_lines:
                break

        return table_lines

    @staticmethod
    def _parse_ascii_table(table_lines: List[str]) -> List[Dict[str, str]]:
        if not table_lines:
            return []

        data_lines = [line for line in table_lines if line.startswith('|')]
        if not data_lines:
            return []

        headers = [cell.strip() for cell in data_lines[0].split('|')[1:-1]]
        rows = []
        for line in data_lines[1:]:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
        return rows

    @staticmethod
    def _kb_to_gb(value: Optional[Any]) -> Optional[int]:
        try:
            if value is None:
                return None
            kb = int(value)
            return round(kb / (1024 * 1024))
        except Exception:
            return None

    @staticmethod
    def _format_disk_summary(disk_info: List[Dict[str, Any]]) -> str:
        if not disk_info:
            return "-"

        entries: List[str] = []
        for item in disk_info:
            filesystem = item.get("filesystem")
            mount_point = item.get("mount_point")
            size = item.get("size")
            used = item.get("use_percent")
            if filesystem in {"文件系统", "Filesystem"}:
                continue
            fs_lower = str(filesystem).lower()
            if fs_lower.startswith("tmpfs") or fs_lower.startswith("devtmpfs") or fs_lower == "overlay" or fs_lower == "shm":
                continue
            if filesystem and mount_point and size:
                entries.append(f"{filesystem}:{mount_point} ({size}, {used})")

        if not entries:
            return "-"

        return "<br>".join(entries)

    @staticmethod
    def _generate_disk_space_table(disk_info: List[Dict[str, Any]]) -> str:
        if not disk_info:
            return ""

        rows: List[List[str]] = []
        for item in disk_info:
            filesystem = item.get("filesystem")
            if filesystem in {"文件系统", "Filesystem"}:
                continue
            fs_lower = str(filesystem).lower()
            if fs_lower.startswith("tmpfs") or fs_lower.startswith("devtmpfs") or fs_lower == "overlay" or fs_lower == "shm":
                continue
            mount_point = item.get("mount_point")
            size = item.get("size")
            used = item.get("used")
            available = item.get("available")
            use_percent = item.get("use_percent")
            if filesystem and size:
                rows.append([
                    filesystem,
                    size or "-",
                    used or "-",
                    available or "-",
                    use_percent or "-",
                    mount_point or "-",
                ])

        if not rows:
            return ""

        table_lines = [
            "| 文件系统 | 容量 | 已用 | 可用 | 已用% | 挂载点 |",
            "|---|---|---|---|---|---|",
        ]
        for row in rows:
            table_lines.append("| " + " | ".join(row) + " |")
        return "\n".join(table_lines)

    @staticmethod
    def _safe_value(value: Any) -> str:
        if value in (None, ""):
            return "-"
        return str(value).replace("\n", "<br>")

    @staticmethod
    def _format_bool(value: Any) -> str:
        if value in ("1", 1, True, "TRUE", "true"):
            return "是"
        if value in ("0", 0, False, "FALSE", "false"):
            return "否"
        return str(value) if value is not None else "-"

    @staticmethod
    def _wrap_sql_mode(value: Optional[str]) -> str:
        if not value:
            return "-"
        parts = [part.strip() for part in str(value).split(',') if part.strip()]
        if not parts:
            return str(value)
        return ",<br>".join(parts)

    @staticmethod
    def _render_table(rows: List[tuple], header: str = "| 配置项 | 配置值 | 说明 |") -> str:
        if not rows:
            return ""
        lines = [header, "|---|---|---|"]
        for key, value, desc in rows:
            lines.append(f"| {key} | {MarkdownGenerator._safe_value(value)} | {desc} |")
        return "\n".join(lines)

    def _get_markdown_output_path(self, meta_info: Dict[str, Any]) -> Path:
        if "source_dir" in meta_info and meta_info["source_dir"]:
            dirname = Path(meta_info["source_dir"]).name
        elif "dirname" in meta_info and meta_info["dirname"]:
            dirname = meta_info["dirname"]
        else:
            hostname = meta_info.get("hostname", "unknown")
            sid = meta_info.get("sid", "unknown")
            collect_date = meta_info.get("collect_date", "00000000")
            dirname = f"{hostname}_{sid}_{collect_date}"

        hostname = meta_info.get("hostname", "unknown")
        sid = meta_info.get("sid", "unknown")

        output_dir = self.output_dir / self.db_type / dirname
        markdown_filename = f"{hostname}_{sid}.md"
        return output_dir / markdown_filename

    def _get_db_model_display(self) -> str:
        if self.db_model == "rac":
            return "集群"
        return "单机"

    def _format_inspection_time_cn(self, raw_time: Optional[str]) -> str:
        if not raw_time:
            return "未知时间"

        text = str(raw_time).strip()

        match = re.match(r"\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                weekday_idx = datetime(year, month, day).weekday()
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][weekday_idx]
            except Exception:
                weekday_cn = ""
            return f"{year}年{month:02d}月{day:02d}日{weekday_cn}"

        patterns = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d",
        ]
        for pattern in patterns:
            try:
                dt = datetime.strptime(text, pattern)
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
            except Exception:
                continue

        en_patterns = [
            "%a %b %d %H:%M:%S %Z %Y",
            "%a, %b %d %H:%M:%S %Z %Y",
            "%a %b %d %H:%M:%S %Y",
        ]
        for pattern in en_patterns:
            try:
                dt = datetime.strptime(text, pattern)
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
            except Exception:
                continue

        return text
