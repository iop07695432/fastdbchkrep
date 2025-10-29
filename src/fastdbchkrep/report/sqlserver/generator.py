"""
SQL Server Markdown 报告生成器

负责从解析后的数据生成 Markdown 和 HTML 报告
"""

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from ..common.config import MarkdownConfig
from ..pdf import MarkdownToPdfConverter
from .parser import SQLServerHealthCheckParser
from .formatters import (
    format_bytes,
    format_bytes_to_mb,
    format_bytes_to_gb,
    format_number_with_comma as format_number,
    format_percentage,
    format_duration_seconds,
)
from . import templates


class MarkdownGenerator:
    """SQL Server Markdown 报告生成器"""

    def __init__(
        self,
        db_type: str = "sqlserver",
        output_dir: Optional[Path] = None,
        company_name: Optional[str] = None,
        user_company: Optional[str] = None,
        application_name: Optional[str] = None,
        suptime: Optional[str] = None,
        supname: Optional[str] = None,
        advice_section_title: Optional[str] = None,
    ):
        """
        初始化生成器

        Args:
            db_type: 数据库类型，默认为 sqlserver
            output_dir: 输出目录路径（来自 -mdout 参数）
            company_name: 公司名称
            user_company: 客户单位名称
            application_name: 应用系统名称
            suptime: 现场支持总时间（小时）
            supname: 支持工程师姓名
            advice_section_title: 建议章节标题，默认为"健康检查建议"
        """
        self.db_type = db_type.lower() if db_type else "sqlserver"
        self.output_dir = output_dir or MarkdownConfig.OUTDIR_PATH
        self.company_name = company_name or "鼎诚科技"
        self.user_company = user_company or "客户单位"
        self.application_name = application_name or "应用系统"
        self.suptime = suptime
        self.supname = supname
        self.advice_section_title = advice_section_title or "健康检查建议"

        logger.debug(
            f"初始化 SQL Server MarkdownGenerator: type={self.db_type}, output_dir={self.output_dir}"
        )

        # 更新模板占位符
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

    def generate_from_txt(self, txt_file: Path, quiet: bool = False) -> bool:
        """
        从 TXT 文件生成 Markdown 报告
        
        这是 SQL Server 的主入口，直接从 TXT 生成报告，跳过 JSON 中间层

        Args:
            txt_file: SQL Server 巡检 TXT 文件路径
            quiet: 是否静默模式

        Returns:
            bool: 是否成功生成
        """
        try:
            txt_path = Path(txt_file)
            if not txt_path.exists():
                logger.error(f"TXT 文件不存在: {txt_file}")
                return False

            if not quiet:
                print(f"  开始解析 SQL Server 巡检文件: {txt_path.name}")

            # 解析 TXT 文件
            parser = SQLServerHealthCheckParser(txt_path)
            parsed_data = parser.parse()

            if not quiet:
                print(f"  检测到版本: {parsed_data['metadata']['version']}")
                print(f"  IP: {parsed_data['metadata']['ip']}")
                print(f"  检查日期: {parsed_data['metadata']['check_date']}")

            # 生成报告
            success = self._generate_report(parsed_data, quiet=quiet)

            if success and not quiet:
                print(f"  ✅ SQL Server 报告生成成功")

            return success

        except Exception as e:
            logger.exception(f"SQL Server 报告生成失败: {e}")
            return False

    def _generate_report(self, parsed_data: Dict[str, Any], quiet: bool = False) -> bool:
        """
        生成 Markdown 和 HTML 报告

        Args:
            parsed_data: 解析后的数据
            quiet: 是否静默模式

        Returns:
            bool: 是否成功生成
        """
        try:
            # 计算输出路径
            ip = parsed_data["metadata"]["ip"]
            output_path = self._calculate_output_path(ip)

            if not quiet:
                print(f"  输出目录: {output_path}")

            # 创建输出目录
            output_path.mkdir(parents=True, exist_ok=True)

            # 生成 Markdown
            md_file = output_path / "HealthCheck.md"
            self._generate_markdown(parsed_data, md_file)

            if not quiet:
                print(f"  生成 Markdown: {md_file}")

            # 生成可编辑 HTML
            self._generate_editable_html(md_file, output_path)

            if not quiet:
                html_file = output_path / f"{md_file.stem}.editable.html"
                print(f"  生成可编辑 HTML: {html_file}")

            return True

        except Exception as e:
            logger.exception(f"生成报告失败: {e}")
            return False

    def _calculate_output_path(self, ip: str) -> Path:
        """
        计算输出路径
        
        路径格式: {mdout}/sqlserver/{ip}/

        Args:
            ip: IP 地址

        Returns:
            Path: 输出路径
        """
        return self.output_dir / "sqlserver" / ip

    def _generate_markdown(self, parsed_data: Dict[str, Any], output_file: Path) -> None:
        """
        生成 Markdown 文件

        Args:
            parsed_data: 解析后的数据
            output_file: 输出文件路径
        """
        # TODO: 阶段 4 实现
        # 生成封面、目录、正文
        md_content = self._build_markdown_content(parsed_data)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Markdown 文件已生成: {output_file}")

    def _build_markdown_content(self, parsed_data: Dict[str, Any]) -> str:
        """
        构建 Markdown 内容

        Args:
            parsed_data: 解析后的数据

        Returns:
            str: Markdown 内容
        """
        sections = []

        # 1. 封面页
        sections.append(self._build_cover_page(parsed_data))

        # 2. 目录页
        sections.append(self._build_toc_page())

        # 3. 正文章节（调整顺序：建议章节移到第一位）
        sections.append(self._build_section_1_advice(parsed_data))
        sections.append(self._build_section_2_basic_info(parsed_data))
        sections.append(self._build_section_3_system_config(parsed_data))
        sections.append(self._build_section_4_database_status(parsed_data))
        sections.append(self._build_section_5_backup(parsed_data))
        sections.append(self._build_section_6_performance(parsed_data))
        sections.append(self._build_section_7_security(parsed_data))

        return "\n\n".join(sections)

    def _generate_editable_html(self, md_file: Path, output_path: Path) -> None:
        """
        生成可编辑 HTML（与 MySQL 一致的行为）

        Args:
            md_file: Markdown 文件路径
            output_path: 输出目录路径
        """
        # TODO: 阶段 4 实现
        # 使用 MarkdownToPdfConverter 生成可编辑 HTML
        converter = MarkdownToPdfConverter()
        success, editable_path = converter.generate_editable_html(
            md_file=str(md_file),
            output_dir=str(output_path),
            output_name=md_file.stem,  # "HealthCheck" 不带后缀
        )

        if success:
            logger.info(f"可编辑 HTML 已生成: {editable_path}")
        else:
            logger.error(f"可编辑 HTML 生成失败")

    def _build_cover_page(self, parsed_data: Dict[str, Any]) -> str:
        """构建封面页"""
        metadata = parsed_data["metadata"]

        # 格式化日期（check_date 格式为 YYYYMMDD）
        check_date = metadata.get("check_date", "")
        if check_date:
            try:
                # 尝试解析 YYYYMMDD 格式并转换为中文格式
                dt = datetime.strptime(check_date, "%Y%m%d")
                check_date_cn = dt.strftime("%Y年%m月%d日")
            except:
                # 如果解析失败，尝试其他格式
                try:
                    dt = datetime.strptime(check_date, "%Y-%m-%d")
                    check_date_cn = dt.strftime("%Y年%m月%d日")
                except:
                    check_date_cn = check_date
        else:
            check_date_cn = "未知"

        report_date_cn = datetime.now().strftime("%Y年%m月%d日")

        # 构建版本信息（包含版本类型和架构）
        version_info = metadata.get("version_full", metadata.get("version", "未知"))
        if metadata.get("edition"):
            version_info += f" {metadata['edition']}"
        if metadata.get("arch"):
            version_info += f" ({metadata['arch']})"

        # 转义元信息以防止 HTML 注入
        ip_escaped = html.escape(str(metadata.get('ip', '未知')))
        version_info_escaped = html.escape(str(version_info))
        os_escaped = html.escape(str(metadata.get('os', '未知')))
        check_date_cn_escaped = html.escape(str(check_date_cn))
        report_date_cn_escaped = html.escape(str(report_date_cn))

        return f"""<div class="cover-page">
    <div>
        <h1>SQL SERVER 数据库巡检报告</h1>
        <h2>Database Health Check Report</h2>
    </div>

    <div class="cover-info">
        <table>
            <thead>
                <tr>
                    <th colspan="2">巡检信息</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>服务器地址：</td>
                    <td>{ip_escaped}</td>
                </tr>
                <tr>
                    <td>数据库版本：</td>
                    <td>{version_info_escaped}</td>
                </tr>
                <tr>
                    <td>操作系统：</td>
                    <td>{os_escaped}</td>
                </tr>
                <tr>
                    <td>巡检日期：</td>
                    <td>{check_date_cn_escaped}</td>
                </tr>
                <tr>
                    <td>报告生成：</td>
                    <td>{report_date_cn_escaped}</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>"""

    def _build_toc_page(self) -> str:
        """构建目录页"""
        return """<div class="toc-page">
    <div class="toc-card">
        <h1>目 录</h1>
        <div class="toc-list">
            <a href="#sec-1" class="toc-link level-1">
                <span class="toc-number">1</span>
                <span class="toc-title">隐患与优化建议</span>
            </a>
            <a href="#sec-2" class="toc-link level-1">
                <span class="toc-number">2</span>
                <span class="toc-title">实例基本信息</span>
            </a>
            <a href="#sec-3" class="toc-link level-1">
                <span class="toc-number">3</span>
                <span class="toc-title">系统配置检查</span>
            </a>
            <a href="#sec-4" class="toc-link level-1">
                <span class="toc-number">4</span>
                <span class="toc-title">数据库状态检查</span>
            </a>
            <a href="#sec-5" class="toc-link level-1">
                <span class="toc-number">5</span>
                <span class="toc-title">备份情况检查</span>
            </a>
            <a href="#sec-6" class="toc-link level-1">
                <span class="toc-number">6</span>
                <span class="toc-title">性能分析</span>
            </a>
            <a href="#sec-7" class="toc-link level-1">
                <span class="toc-number">7</span>
                <span class="toc-title">安全检查</span>
            </a>
        </div>
    </div>
</div>"""

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        渲染 Markdown 表格

        Args:
            headers: 表头列表
            rows: 数据行列表

        Returns:
            str: Markdown 表格字符串
        """
        if not headers or not rows:
            return ""

        # 构建表头
        table = "| " + " | ".join(headers) + " |\n"
        table += "| " + " | ".join(["---"] * len(headers)) + " |\n"

        # 构建数据行
        for row in rows:
            table += "| " + " | ".join(str(cell) for cell in row) + " |\n"

        return table

    def _build_section_2_basic_info(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 2 节：实例基本信息"""
        metadata = parsed_data.get("metadata", {})
        hardware = parsed_data.get("hardware", {})

        content = ['<div class="content">', '', '<h1 id="sec-2">2. 实例基本信息</h1>', '']

        # 2.1 实例版本信息
        content.append('<h2>2.1 实例版本信息</h2>')
        content.append('')

        version_rows = [
            ["实例名称", metadata.get("instance_name", "MSSQLSERVER")],
            ["数据库版本", metadata.get("version_full", metadata.get("version", "未知"))],
            ["版本类型", metadata.get("edition", "未知")],
            ["操作系统", metadata.get("os", "未知")],
            ["平台架构", metadata.get("arch", "未知")],
        ]

        # 添加启动时间（仅 2008+）
        if metadata.get("start_time"):
            version_rows.append(["实例启动时间", metadata["start_time"]])

        content.append(self._render_html_table(["配置项", "配置值"], version_rows))
        content.append('')

        # 版本警告（2005 已停止支持）
        version = metadata.get("version", "")
        if "2005" in version:
            content.append(templates.get_alert_box_html(
                'danger',
                '<strong>严重隐患：</strong>SQL Server 2005 已于2016年4月12日停止官方支持，无法获得安全补丁和技术支持，存在已知安全漏洞。建议尽快升级到SQL Server 2019或2022。'
            ))
            content.append('')

        # 2.2 硬件配置信息
        content.append('<h2>2.2 硬件配置信息</h2>')
        content.append('')

        hardware_rows = [
            ["CPU 数量", hardware.get("cpu_count", "未知")],
            ["CPU 类型", hardware.get("cpu_type", "未知")],
            ["物理内存", format_bytes(int(hardware.get("memory_mb", 0)) * 1024 * 1024) if hardware.get("memory_mb") else "未知"],
        ]

        if hardware.get("active_mask"):
            hardware_rows.append(["CPU 活动掩码", hardware["active_mask"]])

        content.append(self._render_html_table(["配置项", "配置值"], hardware_rows))
        content.append('')

        return "\n".join(content)

    def _build_section_3_system_config(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 3 节：系统配置检查"""
        config = parsed_data.get("config", {})

        content = ['<h1 id="sec-3">3. 系统配置检查</h1>', '']

        # 3.1 内存配置
        content.append('<h2>3.1 内存配置</h2>')
        content.append('')

        min_mem = config.get("min_server_memory_mb", "未知")
        max_mem = config.get("max_server_memory_mb", "未知")

        memory_rows = [
            ["最小服务器内存 (MB)", format_number(min_mem) if isinstance(min_mem, (int, float)) else min_mem],
            ["最大服务器内存 (MB)", format_number(max_mem) if isinstance(max_mem, (int, float)) else max_mem],
        ]

        content.append(self._render_html_table(["配置项", "配置值"], memory_rows))
        content.append('')

        # 3.2 并行度配置
        content.append('<h2>3.2 并行度配置 (MAXDOP)</h2>')
        content.append('')

        maxdop = config.get("maxdop", "未知")
        maxdop_rows = [
            ["最大并行度 (MAXDOP)", str(maxdop)],
        ]

        content.append(self._render_html_table(["配置项", "配置值"], maxdop_rows))
        content.append('')

        # MAXDOP 建议（安全转换并检查）
        try:
            maxdop_int = int(maxdop) if maxdop not in ("未知", None, "") else None
            if maxdop_int is not None and maxdop_int == 0:
                content.append(templates.get_alert_box_html(
                    'warning',
                    '<strong>警告：</strong>MAXDOP 设置为 0（无限制），可能导致并行查询过度消耗资源。建议根据 CPU 核心数设置合理值（通常为 CPU 核心数的 50%-75%）。'
                ))
                content.append('')
        except (ValueError, TypeError):
            pass  # 无法转换为整数，跳过检查

        # 3.3 其他配置
        content.append('<h2>3.3 其他配置</h2>')
        content.append('')

        other_rows = []

        if config.get("user_connections"):
            other_rows.append(["用户连接数", str(config["user_connections"])])

        if config.get("collation"):
            other_rows.append(["排序规则", config["collation"]])

        if other_rows:
            content.append(self._render_html_table(["配置项", "配置值"], other_rows))
            content.append('')

        # 3.4 服务账户
        mssql_account = config.get("mssqlserver_account")
        agent_account = config.get("sqlagent_account")

        if mssql_account or agent_account:
            content.append('<h2>3.4 服务账户</h2>')
            content.append('')

            account_rows = []
            if mssql_account:
                account_rows.append(["MSSQLSERVER", mssql_account])
            if agent_account:
                account_rows.append(["SQLAGENT", agent_account])

            if account_rows:
                content.append(self._render_html_table(["服务名", "启动账户"], account_rows))
                content.append('')

        return "\n".join(content)

    def _build_section_4_database_status(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 4 节：数据库状态检查"""
        db_state = parsed_data.get("db_state", {})

        content = ['<h1 id="sec-4">4. 数据库状态检查</h1>', '']

        # 4.1 数据库概览
        content.append('<h2>4.1 数据库概览</h2>')
        content.append('')

        system_dbs = db_state.get("system_databases", [])
        user_dbs = db_state.get("user_databases", [])

        overview_rows = [
            ["系统数据库数量", str(len(system_dbs))],
            ["用户数据库数量", str(len(user_dbs))],
            ["数据库总数", str(db_state.get("db_count", len(system_dbs) + len(user_dbs)))],
        ]

        content.append(self._render_html_table(["统计项", "数量"], overview_rows))
        content.append('')

        # 4.2 用户数据库列表
        if user_dbs:
            content.append('<h2>4.2 用户数据库列表</h2>')
            content.append('')

            # 只显示前 20 个数据库
            display_dbs = user_dbs[:20]
            db_rows = [[db.get("名称", ""), db.get("状态", ""), db.get("恢复模式", "")] for db in display_dbs]

            content.append(self._render_html_table(["数据库名", "状态", "恢复模式"], db_rows))

            if len(user_dbs) > 20:
                content.append('')
                content.append(f'<p><em>（共 {len(user_dbs)} 个用户数据库，仅显示前 20 个）</em></p>')

            content.append('')

        # 4.3 作业信息
        jobs = db_state.get("jobs", [])
        if jobs:
            content.append('<h2>4.3 SQL Server 代理作业</h2>')
            content.append('')

            # 使用实际列名：name, enabled, 步骤计数
            job_rows = [[job.get("name", ""), job.get("enabled", ""), job.get("步骤计数", "")] for job in jobs[:10]]

            content.append(self._render_html_table(["作业名称", "是否启用", "步骤计数"], job_rows))

            if len(jobs) > 10:
                content.append('')
                content.append(f'<p><em>（共 {len(jobs)} 个作业，仅显示前 10 个）</em></p>')

            content.append('')

        # 4.4 链接服务器
        linked_servers = db_state.get("linked_servers", [])
        if linked_servers:
            content.append('<h2>4.4 链接服务器</h2>')
            content.append('')

            # 使用实际列名：Linked Server, Local Login, Is Self Mapping, Remote Login
            ls_rows = [[ls.get("Linked Server", ""), ls.get("Local Login", ""),
                       ls.get("Is Self Mapping", ""), ls.get("Remote Login", "")] for ls in linked_servers]

            content.append(self._render_html_table(["链接服务器", "本地登录", "自映射", "远程登录"], ls_rows))
            content.append('')

        # 4.5 日志使用情况
        log_usage = db_state.get("log_usage", [])
        if log_usage:
            content.append('<h2>4.5 日志使用情况</h2>')
            content.append('')

            # 使用实际列名：Database Name, Log Size (MB), Log Space Used (%), Status
            log_rows = [[log.get("Database Name", ""), log.get("Log Size (MB)", ""),
                        log.get("Log Space Used (%)", ""), log.get("Status", "")] for log in log_usage[:20]]

            content.append(self._render_html_table(["数据库名", "日志大小 (MB)", "日志使用率 (%)", "状态"], log_rows))

            if len(log_usage) > 20:
                content.append('')
                content.append(f'<p><em>（共 {len(log_usage)} 个数据库，仅显示前 20 个）</em></p>')

            content.append('')

        return "\n".join(content)

    def _build_section_5_backup(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 5 节：备份情况检查"""
        backup = parsed_data.get("backup", {})

        content = ['<h1 id="sec-5">5. 备份情况检查</h1>', '']

        # 5.1 备份概览
        content.append('<h2>5.1 备份概览</h2>')
        content.append('')

        total_dbs = backup.get("total_dbs", 0)
        backed_up_dbs = backup.get("backed_up_dbs", 0)
        no_backup_dbs = backup.get("no_backup_dbs", [])

        overview_rows = [
            ["数据库总数", str(total_dbs)],
            ["有备份的数据库", str(backed_up_dbs)],
            ["无备份的数据库", str(len(no_backup_dbs))],
        ]

        content.append(self._render_html_table(["统计项", "数量"], overview_rows))
        content.append('')

        # 无备份数据库警告
        if no_backup_dbs:
            # 转义数据库名以防止 HTML 注入
            escaped_db_names = [html.escape(str(db)) for db in no_backup_dbs]
            content.append(templates.get_alert_box_html(
                'warning',
                f'<strong>警告：</strong>以下 {len(no_backup_dbs)} 个数据库没有备份记录：{", ".join(escaped_db_names)}'
            ))
            content.append('')

        # 5.2 备份摘要（每个数据库的最近备份）
        summary = backup.get("summary", {})
        if summary:
            content.append('<h2>5.2 备份摘要（最近一次备份）</h2>')
            content.append('')

            backup_rows = []
            for db_name, backups in sorted(summary.items())[:15]:  # 只显示前 15 个
                full_info = backups.get("FULL", {})
                incr_info = backups.get("INCR", {})
                log_info = backups.get("LOG", {})

                # 使用实际字段名：备份大小(MB)
                full_str = f"{full_info.get('备份启动时间', '-')} ({full_info.get('备份大小(MB)', '-')} MB)" if full_info else "-"
                incr_str = f"{incr_info.get('备份启动时间', '-')} ({incr_info.get('备份大小(MB)', '-')} MB)" if incr_info else "-"
                log_str = f"{log_info.get('备份启动时间', '-')}" if log_info else "-"

                backup_rows.append([db_name, full_str, incr_str, log_str])

            content.append(self._render_html_table(
                ["数据库名", "最近完全备份", "最近增量备份", "最近日志备份"],
                backup_rows
            ))

            if len(summary) > 15:
                content.append('')
                content.append(f'<p><em>（共 {len(summary)} 个数据库有备份，仅显示前 15 个）</em></p>')

            content.append('')

        return "\n".join(content)

    def _build_section_6_performance(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 6 节：性能分析"""
        performance = parsed_data.get("performance", {})

        content = ['<h1 id="sec-6">6. 性能分析</h1>', '']

        # 6.1 缓存使用情况
        cache_usage = performance.get("cache_usage", [])
        if cache_usage:
            content.append('<h2>6.1 缓存使用情况</h2>')
            content.append('')

            cache_rows = []
            for cache in cache_usage[:10]:  # 只显示前 10 个
                # 使用实际列名：Cached Size (MB), Database
                cache_rows.append([
                    cache.get("Database", ""),
                    cache.get("Cached Size (MB)", ""),
                ])

            content.append(self._render_html_table(["数据库名", "缓存大小 (MB)"], cache_rows))

            if len(cache_usage) > 10:
                content.append('')
                content.append(f'<p><em>（共 {len(cache_usage)} 条记录，仅显示前 10 条）</em></p>')

            content.append('')

        # 6.2 等待事件
        wait_events = performance.get("wait_events", [])
        if wait_events:
            content.append('<h2>6.2 等待事件 TOP 10</h2>')
            content.append('')

            wait_rows = []
            for wait in wait_events[:10]:
                # 使用实际列名：wait_type, waiting_tasks_COUNT, resource_wait_time, max_wait_time_ms, avg_wait_time
                wait_rows.append([
                    wait.get("wait_type", ""),
                    format_number(wait.get("waiting_tasks_COUNT", 0)),
                    format_number(wait.get("resource_wait_time", 0)),
                    format_number(wait.get("avg_wait_time", 0)),
                ])

            content.append(self._render_html_table(["等待类型", "等待任务数", "资源等待时间", "平均等待时间"], wait_rows))
            content.append('')

        # 6.3 TOP SQL 摘要
        # 直接从 performance 顶层读取 top_cpu 等键
        top_cpu = performance.get("top_cpu", [])
        if top_cpu:
            content.append('<h2>6.3 TOP SQL 摘要</h2>')
            content.append('')

            content.append('<h3>6.3.1 TOP CPU 消耗</h3>')
            content.append('')

            cpu_rows = []
            for sql in top_cpu[:5]:  # 只显示前 5 个
                # 使用实际字段名：statement_text, total_worker_time_ms
                sql_text = sql.get("statement_text", "")
                if len(sql_text) > 100:
                    sql_text = sql_text[:100] + "..."

                cpu_rows.append([
                    sql.get("sql_handle", "")[:16] + "..." if sql.get("sql_handle") else "-",
                    format_number(sql.get("total_worker_time_ms", 0)),
                    sql_text,
                ])

            content.append(self._render_html_table(["SQL Handle", "总CPU时间(ms)", "SQL 文本"], cpu_rows))
            content.append('')

        return "\n".join(content)

    def _build_section_7_security(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 7 节：安全检查"""
        security = parsed_data.get("security", {})

        content = ['<h1 id="sec-7">7. 安全检查</h1>', '']

        # 7.1 sysadmin 角色成员
        sysadmin_users = security.get("sysadmin_users", [])
        if sysadmin_users:
            content.append('<h2>7.1 sysadmin 角色成员</h2>')
            content.append('')

            # 使用实际列名：loginname, type_desc, is_disabled, created, update
            user_rows = [[user.get("loginname", ""), user.get("type_desc", ""),
                         user.get("is_disabled", ""), user.get("created", "")] for user in sysadmin_users]

            content.append(self._render_html_table(["登录名", "类型", "是否禁用", "创建时间"], user_rows))
            content.append('')

            # 安全建议
            if len(sysadmin_users) > 5:
                content.append(templates.get_alert_box_html(
                    'warning',
                    f'<strong>警告：</strong>发现 {len(sysadmin_users)} 个 sysadmin 角色成员，建议遵循最小权限原则，减少高权限账户数量。'
                ))
                content.append('')
        else:
            content.append('<p>未采集到 sysadmin 角色成员信息。</p>')
            content.append('')

        return "\n".join(content)

    def _build_section_1_advice(self, parsed_data: Dict[str, Any]) -> str:
        """构建第 1 节：建议章节（空白占位表格）"""
        content = [f'<h1 id="sec-1">1. {self.advice_section_title}</h1>', '']

        content.append('<p>以下为数据库巡检发现的隐患与优化建议，请根据实际情况填写：</p>')
        content.append('')

        # 空白建议表格（供人工填写）
        content.append('<table data-suggest-id="advice_table">')
        content.append('    <thead>')
        content.append('        <tr>')
        content.append('            <th style="width: 5%;">NO</th>')
        content.append('            <th style="width: 40%;">问题描述</th>')
        content.append('            <th style="width: 15%;">参考章节</th>')
        content.append('            <th style="width: 40%;">建议解决时间</th>')
        content.append('        </tr>')
        content.append('    </thead>')
        content.append('    <tbody>')

        # 默认 3 行空白
        for i in range(1, 4):
            content.append('        <tr>')
            content.append(f'            <td contenteditable="true">{i}</td>')
            content.append('            <td contenteditable="true"></td>')
            content.append('            <td contenteditable="true"></td>')
            content.append('            <td contenteditable="true"></td>')
            content.append('        </tr>')

        content.append('    </tbody>')
        content.append('</table>')
        content.append('')

        # 编辑控件（由 PDF converter 注入）
        content.append('<div class="edit-controls" data-target="advice_table" aria-hidden="false">')
        content.append('    <button type="button" onclick="window.__editor.addRow(\'advice_table\')">新增一行</button>')
        content.append('    <button type="button" onclick="window.__editor.removeLastRow(\'advice_table\')">删除末行</button>')
        content.append('</div>')
        content.append('')

        content.append('</div>')  # 关闭 content div

        return "\n".join(content)

    def _render_html_table(self, headers: List[str], rows: List[List[str]], escape_html: bool = True) -> str:
        """
        渲染 HTML 表格

        Args:
            headers: 表头列表
            rows: 数据行列表
            escape_html: 是否转义 HTML 特殊字符（默认 True）

        Returns:
            str: HTML 表格字符串
        """
        if not headers or not rows:
            return ""

        lines = ['<table>']

        # 表头
        lines.append('    <thead>')
        lines.append('        <tr>')
        for header in headers:
            escaped_header = html.escape(str(header)) if escape_html else str(header)
            lines.append(f'            <th>{escaped_header}</th>')
        lines.append('        </tr>')
        lines.append('    </thead>')

        # 表体
        lines.append('    <tbody>')
        for row in rows:
            lines.append('        <tr>')
            for cell in row:
                # 转义 HTML 特殊字符以防止 XSS 和页面破坏
                escaped_cell = html.escape(str(cell)) if escape_html else str(cell)
                lines.append(f'            <td>{escaped_cell}</td>')
            lines.append('        </tr>')
        lines.append('    </tbody>')

        lines.append('</table>')

        return "\n".join(lines)

