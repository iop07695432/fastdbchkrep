"""
SQL Server 健康检查 TXT 文件解析器

负责解析 SQL Server 巡检 TXT 文件，提取结构化数据
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


def parse_table(block: str) -> List[Dict[str, str]]:
    """
    解析通用表格：首行列名 + 横线分隔 + 数据行 + 受影响行终止

    Args:
        block: 表格文本块

    Returns:
        list[dict]: 解析后的数据行列表

    Examples:
        >>> text = '''name,value
        ... ----,-----
        ... user connections,0
        ... max degree of parallelism,0
        ...
        ... (2 rows affected)'''
        >>> parse_table(text)
        [{'name': 'user connections', 'value': '0'},
         {'name': 'max degree of parallelism', 'value': '0'}]
    """
    lines = block.strip().split('\n')
    if len(lines) < 3:
        return []

    # 查找表格开始位置（第一行包含逗号的行）
    header_idx = -1
    for i, line in enumerate(lines):
        if ',' in line and not re.match(r'^[-,\s]+$', line):
            header_idx = i
            break

    if header_idx == -1 or header_idx + 2 >= len(lines):
        return []

    # 列名行
    header_line = lines[header_idx].strip()
    columns = [col.strip() for col in header_line.split(',')]

    # 横线分隔符行（header_idx + 1，跳过）
    # 数据行从 header_idx + 2 开始

    result = []
    for line in lines[header_idx + 2:]:
        line = line.strip()

        # 终止条件：受影响行标记
        if re.match(r'\(\d+ (?:rows affected|行受影响)\)', line):
            break

        # 空行跳过
        if not line:
            continue

        # 跳过横线分隔符行（全是横线和逗号）
        if re.match(r'^[-,\s]+$', line):
            continue

        # 解析数据行（逗号分隔）
        values = [v.strip() for v in line.split(',')]

        # 容错：列数不齐时跳过
        if len(values) != len(columns):
            logger.debug(f"列数不匹配（期望{len(columns)}，实际{len(values)}），跳过行: {line[:80]}")
            continue

        # 构建字典
        row = {}
        for col, val in zip(columns, values):
            # NULL 或空值记为空字符串
            if val.upper() == 'NULL' or not val:
                row[col] = ''
            else:
                row[col] = val

        result.append(row)

    return result


def parse_all_tables(block: str) -> List[List[Dict[str, str]]]:
    """
    解析块中的所有表格

    Args:
        block: 文本块

    Returns:
        list[list[dict]]: 所有表格的列表
    """
    tables = []
    lines = block.strip().split('\n')

    i = 0
    while i < len(lines):
        # 查找表格开始（包含逗号的行）
        if ',' in lines[i] and not re.match(r'^[-,\s]+$', lines[i]):
            # 找到表格，提取到下一个 "rows affected" 或文件结束
            table_lines = [lines[i]]
            i += 1

            while i < len(lines):
                line = lines[i].strip()
                table_lines.append(lines[i])

                # 遇到 "rows affected" 终止
                if re.match(r'\(\d+ (?:rows affected|行受影响)\)', line):
                    i += 1
                    break

                i += 1

            # 解析这个表格
            table_text = '\n'.join(table_lines)
            table_data = parse_table(table_text)
            if table_data:
                tables.append(table_data)
        else:
            i += 1

    return tables


def parse_sql_texts(block: str) -> Dict[str, str]:
    """
    解析 SQL 文本块，提取 handle → statement_text 映射

    规则：以 0x 开头的句柄行起新块，直至下一个句柄或段尾；中间多行拼接为空格

    Args:
        block: SQL 文本块

    Returns:
        dict: {handle: statement_text}

    Examples:
        >>> text = '''sql_handle,statement_text
        ... ----------,--------------
        ... 0x02000000EE256B0D,select @in=sum(insum)
        ... from table
        ... where id=1
        ... 0x02000000F224802F,INSERT INTO table values(@1,@2)
        ... (2 rows affected)'''
        >>> parse_sql_texts(text)
        {'0x02000000EE256B0D': 'select @in=sum(insum) from table where id=1',
         '0x02000000F224802F': 'INSERT INTO table values(@1,@2)'}
    """
    lines = block.strip().split('\n')
    sql_map = {}
    current_handle = None
    current_text_lines = []

    for line in lines:
        line = line.strip()

        # 跳过空行、表头、分隔符、受影响行标记
        if not line or line.startswith('sql_handle') or line.startswith('---') or \
           re.match(r'^\(\d+\s+(rows affected|行受影响)\)', line):
            continue

        # 检查是否是新的 handle 行（以 0x 开头）
        if line.startswith('0x'):
            # 保存上一个 handle 的文本
            if current_handle and current_text_lines:
                sql_map[current_handle] = ' '.join(current_text_lines).strip()

            # 解析新的 handle 行
            parts = line.split(',', 1)
            if len(parts) == 2:
                current_handle = parts[0].strip()
                current_text_lines = [parts[1].strip()] if parts[1].strip() else []
            else:
                current_handle = parts[0].strip()
                current_text_lines = []
        else:
            # 继续拼接当前 handle 的 SQL 文本
            if current_handle:
                current_text_lines.append(line)

    # 保存最后一个 handle 的文本
    if current_handle and current_text_lines:
        sql_map[current_handle] = ' '.join(current_text_lines).strip()

    return sql_map


def normalize_backup_type(backup_type: str) -> str:
    """
    规范化备份类型名称

    将不同脚本版本产生的备份类型名称统一映射到标准名称：
    - FULL: 完全备份
    - INCR: 增量/差异备份（DIFF/差异/增量）
    - LOG: 日志备份

    Args:
        backup_type: 原始备份类型字符串

    Returns:
        str: 规范化后的备份类型（FULL/INCR/LOG）

    Examples:
        >>> normalize_backup_type('FULL')
        'FULL'
        >>> normalize_backup_type('DIFF')
        'INCR'
        >>> normalize_backup_type('差异')
        'INCR'
        >>> normalize_backup_type('增量')
        'INCR'
    """
    backup_type = backup_type.strip().upper()

    # 增量/差异备份的各种变体
    if backup_type in ('DIFF', 'INCR', 'DIFFERENTIAL', 'INCREMENTAL'):
        return 'INCR'

    # 中文变体
    if '差异' in backup_type or '增量' in backup_type:
        return 'INCR'

    # 完全备份
    if backup_type in ('FULL', 'DATABASE') or '完全' in backup_type or '完整' in backup_type:
        return 'FULL'

    # 日志备份
    if backup_type in ('LOG', 'TRANSACTION') or '日志' in backup_type:
        return 'LOG'

    # 未知类型，返回原值
    return backup_type


def aggregate_backup_history(backup_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    按库聚合备份历史，提取最近一次 FULL/INCR/LOG 备份

    Args:
        backup_rows: 备份记录列表（从 parse_table 解析）

    Returns:
        dict: {
            'summary': {db_name: {'FULL': {...}, 'INCR': {...}, 'LOG': {...}}},
            'no_backup_dbs': [db_name, ...],
            'total_dbs': int,
            'backed_up_dbs': int
        }

    Examples:
        >>> rows = [
        ...     {'名称': 'Acs', '类型': 'FULL', '备份启动时间': '2025-10-21 22:58', '备份大小(MB)': '1661.51'},
        ...     {'名称': 'Acs', '类型': 'INCR', '备份启动时间': '2025-10-23 02:57', '备份大小(MB)': '4.38'},
        ... ]
        >>> result = aggregate_backup_history(rows)
        >>> result['summary']['Acs']['FULL']['备份启动时间']
        '2025-10-21 22:58'
    """
    from datetime import datetime
    from collections import defaultdict

    # 按数据库分组
    db_backups = defaultdict(lambda: {'FULL': None, 'INCR': None, 'LOG': None})

    for row in backup_rows:
        db_name = row.get('名称', '')
        backup_type_raw = row.get('类型', '')
        backup_time_str = row.get('备份启动时间', '')

        if not db_name or not backup_type_raw:
            continue

        # 规范化备份类型
        backup_type = normalize_backup_type(backup_type_raw)

        # 解析备份时间
        try:
            backup_time = datetime.strptime(backup_time_str, '%Y-%m-%d %H:%M')
        except (ValueError, TypeError):
            # 如果解析失败，使用字符串比较
            backup_time = backup_time_str

        # 更新最近备份（FULL/INCR/LOG）
        current = db_backups[db_name].get(backup_type)
        if current is None:
            db_backups[db_name][backup_type] = row
        else:
            # 比较时间，保留最新的
            try:
                current_time = datetime.strptime(current.get('备份启动时间', ''), '%Y-%m-%d %H:%M')
                if backup_time > current_time:
                    db_backups[db_name][backup_type] = row
            except (ValueError, TypeError):
                # 字符串比较
                if backup_time_str > current.get('备份启动时间', ''):
                    db_backups[db_name][backup_type] = row

    # 统计无备份的数据库（没有任何类型的备份）
    no_backup_dbs = []
    for db_name, backups in db_backups.items():
        if not any(backups.values()):
            no_backup_dbs.append(db_name)

    return {
        'summary': dict(db_backups),
        'no_backup_dbs': no_backup_dbs,
        'total_dbs': len(db_backups),
        'backed_up_dbs': len(db_backups) - len(no_backup_dbs)
    }


def split_sections(text: str) -> Dict[str, str]:
    """
    切分主要章节

    Args:
        text: 完整文本

    Returns:
        dict: 章节名称 -> 章节内容
    """
    sections = {}

    # 定义章节标记（按出现顺序）
    section_markers = [
        ('instance_info', r'1\.查看实例名称和启动时间'),
        ('version_info', r'查看版本情况'),
        ('os_params', r'3\.查看数据库所在服务器的操作系统参数'),
        ('startup_params', r'4\.查看实例启动参数配置'),
        ('collation', r'5\.查看服务器默认排序规则查询'),
        ('maxdop_connections', r'6\.查看服务器实例配置的最大并行度和允许的最大连接数'),
        ('service_accounts', r'7\.查看SQL Server服务启动用户'),
        ('db_count', r'8\.查看用户数据库数量'),
        ('job_info', r'8\.查看job数量'),
        ('linked_servers', r'8\.查看链接服务器信息'),
        ('system_databases', r'10\.查看系统数据库信息'),
        ('system_db_files', r'11\.系统数据库文件信息'),
        ('user_databases', r'12\.查看用户数据库信息'),
        ('user_db_files', r'12\.用户数据库文件信息'),
        ('log_usage', r'13\.查看所有数据库日志文件大小及使用情况'),
        ('backup_info', r'14\.查看(数据库备份信息|所有数据库备份情况)'),
        ('sysadmin_users', r'15\.sysadmin下的用户'),
        ('cache_usage', r'16\.查看(数据库使用缓存情况|缓存使用情况)'),
        ('wait_events', r'17\.查看等待事件'),
        # TOP SQL 相关章节
        ('top_cpu', r'18\.查看最消耗CPU资源的SQL HANDLE'),
        ('top_cpu_text', r'18\.查看最消耗CPU资源的SQL HANDLE.*对应的语句'),
        ('top_elapsed', r'19\.查看执行时间最长的SQL HANDLE'),
        ('top_elapsed_text', r'19\.查看执行时间最长的SQL HANDLE.*对应的语句'),
        ('top_logical', r'20\.查看最多逻辑读的SQL HANDLE'),
        ('top_logical_text', r'20\.查看最多逻辑读的SQL HANDLE.*对应的语句'),
        ('top_physical', r'21\.查看最多物理读的SQL HANDLE'),
        ('top_physical_text', r'21\.查看最多物理读的SQL HANDLE.*对应的语句'),
    ]

    # 切分章节
    for i, (section_name, pattern) in enumerate(section_markers):
        # 查找当前章节的起始位置
        match = re.search(pattern, text)
        if not match:
            continue

        start_pos = match.start()

        # 查找下一个章节的起始位置
        end_pos = len(text)
        for next_section_name, next_pattern in section_markers[i + 1:]:
            next_match = re.search(next_pattern, text[start_pos:])
            if next_match:
                end_pos = start_pos + next_match.start()
                break

        # 提取章节内容
        sections[section_name] = text[start_pos:end_pos].strip()

    return sections


class SQLServerHealthCheckParser:
    """SQL Server 健康检查 TXT 文件解析器"""

    def __init__(self, txt_file: Path):
        """
        初始化解析器

        Args:
            txt_file: SQL Server 巡检 TXT 文件路径
        """
        self.txt_file = Path(txt_file)
        self.content: str = ""
        self.version: str = ""  # 2005 或 2008
        self.version_full: str = ""  # 完整版本字符串
        self.parsed_data: Dict[str, Any] = {}

        # 从文件名提取元数据
        self.ip: str = ""
        self.check_date: str = ""
        self._extract_metadata_from_filename()

        logger.debug(f"初始化 SQL Server 解析器: {self.txt_file}")

    def _extract_metadata_from_filename(self) -> None:
        """
        从文件名提取 IP 和检查日期
        
        文件名格式: {ip}-HealthCheck-{YYYYMMDD}.txt
        例如: 172.18.0.2-HealthCheck-20251023.txt
        """
        filename = self.txt_file.stem  # 不含扩展名的文件名
        
        # 使用正则提取 IP 和日期
        pattern = r'^(.+?)-HealthCheck-(\d{8})$'
        match = re.match(pattern, filename)
        
        if match:
            self.ip = match.group(1)
            self.check_date = match.group(2)
            logger.debug(f"从文件名提取: IP={self.ip}, 日期={self.check_date}")
        else:
            logger.warning(f"无法从文件名提取元数据: {filename}")
            self.ip = "unknown"
            self.check_date = "unknown"

    def detect_version(self) -> str:
        """
        检测 SQL Server 版本（2005 或 2008）
        
        识别特征:
        - 2005: "Microsoft SQL Server 2005" 或 "9.00." 或 "(N rows affected)"
        - 2008: "Microsoft SQL Server 2008" 或 "10.0." 或 "(N 行受影响)"
        
        Returns:
            str: "2005" 或 "2008" 或 "unknown"
        """
        if not self.content:
            self._load_content()

        # 检查版本字符串
        if "Microsoft SQL Server 2005" in self.content or "9.00." in self.content:
            self.version = "2005"
        elif "Microsoft SQL Server 2008" in self.content or "10.0." in self.content:
            self.version = "2008"
        elif "Microsoft SQL Server 2012" in self.content or "11.0." in self.content:
            self.version = "2012"
        elif "Microsoft SQL Server 2014" in self.content or "12.0." in self.content:
            self.version = "2014"
        elif "Microsoft SQL Server 2016" in self.content or "13.0." in self.content:
            self.version = "2016"
        elif "Microsoft SQL Server 2017" in self.content or "14.0." in self.content:
            self.version = "2017"
        elif "Microsoft SQL Server 2019" in self.content or "15.0." in self.content:
            self.version = "2019"
        else:
            # 通过提示语判断
            if "(N rows affected)" in self.content or "rows affected" in self.content:
                self.version = "2005"
            elif "(N 行受影响)" in self.content or "行受影响" in self.content:
                self.version = "2008"
            else:
                self.version = "unknown"

        # 提取完整版本字符串（使用 \d+ 匹配任意行数）
        version_pattern = r'Microsoft SQL Server \d{4}.*?(?=\n\n|\(\d+ (?:rows affected|行受影响)\))'
        version_match = re.search(version_pattern, self.content, re.DOTALL)
        if version_match:
            self.version_full = version_match.group(0).strip()

        logger.info(f"检测到 SQL Server 版本: {self.version}")
        return self.version

    def _load_content(self) -> None:
        """加载 TXT 文件内容"""
        if not self.txt_file.exists():
            raise FileNotFoundError(f"文件不存在: {self.txt_file}")

        try:
            with open(self.txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                self.content = f.read()
            logger.debug(f"成功加载文件: {self.txt_file}, 大小: {len(self.content)} 字符")
        except Exception as e:
            logger.error(f"加载文件失败: {self.txt_file}, 错误: {e}")
            raise

    def parse(self) -> Dict[str, Any]:
        """
        解析 TXT 文件，提取结构化数据

        Returns:
            Dict[str, Any]: 解析后的结构化数据
        """
        if not self.content:
            self._load_content()

        # 检测版本
        self.detect_version()

        # 切分章节
        sections = split_sections(self.content)
        logger.debug(f"切分章节数: {len(sections)}")

        # 初始化解析结果
        self.parsed_data = {
            "metadata": {
                "ip": self.ip,
                "check_date": self.check_date,
                "version": self.version,
                "version_full": self.version_full,
                "os": "unknown",
                "arch": "unknown",
                "edition": "unknown",
                "start_time": "unknown",
            },
            "hardware": {},
            "config": {},
            "db_state": {},
            "backup": {},
            "performance": {},
            "security": {},
        }

        # 解析各个章节
        self._parse_instance_info(sections.get('instance_info', ''))
        self._parse_os_params(sections.get('os_params', ''))
        self._parse_config(sections.get('startup_params', ''),
                          sections.get('maxdop_connections', ''),
                          sections.get('collation', ''))
        self._parse_service_accounts(sections.get('service_accounts', ''))
        self._parse_databases(sections.get('system_databases', ''),
                             sections.get('user_databases', ''))
        self._parse_jobs(sections.get('job_info', ''))
        self._parse_linked_servers(sections.get('linked_servers', ''))
        self._parse_log_usage(sections.get('log_usage', ''))
        self._parse_backup(sections.get('backup_info', ''))
        self._parse_performance(sections.get('cache_usage', ''),
                               sections.get('wait_events', ''))
        # 解析 TOP SQL（阶段 3 新增）
        self._parse_top_sql(sections)
        # 解析安全信息（阶段 4 补充）
        self._parse_security(sections.get('sysadmin_users', ''))

        logger.info(f"解析完成: {self.txt_file}")
        return self.parsed_data

    def _parse_instance_info(self, block: str) -> None:
        """
        解析实例名称和启动时间

        示例格式:
        1.查看实例名称和启动时间

        -
        MSSQLSERVER

        (1 rows affected)
        查看版本情况

        -
        Microsoft SQL Server 2005 - 9.00.4053.00 (Intel X86)
            May 26 2009 14:24:20
            Copyright (c) 1988-2005 Microsoft Corporation
            Standard Edition on Windows NT 6.0 (Build 6003: Service Pack 2)

        启动时间通常在版本信息的第二行（编译日期）
        """
        if not block:
            return

        lines = block.strip().split('\n')

        # 提取启动时间（从版本信息的第二行）
        # 格式: "May 26 2009 14:24:20"
        for i, line in enumerate(lines):
            # 匹配日期时间格式 (Month Day Year HH:MM:SS)
            date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2})', line)
            if date_match:
                self.parsed_data['metadata']['start_time'] = date_match.group(1)
                break

        # 提取版本信息中的 Edition 和 OS
        for i, line in enumerate(lines):
            # 提取 Edition (Standard/Enterprise/Developer/Express)
            if 'Edition' in line:
                if 'Standard Edition' in line:
                    self.parsed_data['metadata']['edition'] = 'Standard'
                elif 'Enterprise Edition' in line:
                    self.parsed_data['metadata']['edition'] = 'Enterprise'
                elif 'Developer Edition' in line:
                    self.parsed_data['metadata']['edition'] = 'Developer'
                elif 'Express Edition' in line:
                    self.parsed_data['metadata']['edition'] = 'Express'

                # 提取 OS 信息 (Windows NT x.x)
                if 'Windows NT' in line:
                    # 格式: "Standard Edition on Windows NT 6.0 (Build 6003: Service Pack 2)"
                    os_match = re.search(r'Windows NT ([\d.]+) \(Build (\d+)(?:: (.+?))?\)', line)
                    if os_match:
                        nt_version = os_match.group(1)
                        build = os_match.group(2)
                        sp = os_match.group(3) or ''

                        # 映射 NT 版本到 Windows 版本
                        os_map = {
                            '5.0': 'Windows 2000',
                            '5.1': 'Windows XP',
                            '5.2': 'Windows Server 2003',
                            '6.0': 'Windows Server 2008',
                            '6.1': 'Windows Server 2008 R2',
                            '6.2': 'Windows Server 2012',
                            '6.3': 'Windows Server 2012 R2',
                            '10.0': 'Windows Server 2016/2019',
                        }
                        os_name = os_map.get(nt_version, f'Windows NT {nt_version}')
                        self.parsed_data['metadata']['os'] = f"{os_name} ({sp})" if sp else os_name

            # 提取架构 (Intel X86 / X64)
            if 'Intel X86' in line or 'Intel X64' in line or 'X64' in line:
                if 'X64' in line or 'Intel X64' in line:
                    self.parsed_data['metadata']['arch'] = 'X64'
                else:
                    self.parsed_data['metadata']['arch'] = 'X86'

        logger.debug(f"解析实例信息: edition={self.parsed_data['metadata']['edition']}, "
                    f"os={self.parsed_data['metadata']['os']}, "
                    f"arch={self.parsed_data['metadata']['arch']}")

    def _parse_os_params(self, block: str) -> None:
        """解析操作系统参数"""
        if not block:
            return

        # 解析表格
        rows = parse_table(block)

        # 提取关键信息
        for row in rows:
            name = row.get('Name', '')
            value = row.get('Character_Value', '')

            if name == 'ProcessorCount':
                self.parsed_data['hardware']['cpu_count'] = value
            elif name == 'Platform':
                self.parsed_data['hardware']['platform'] = value
                # 从 Platform 也可以提取架构信息（作为备份）
                if 'X64' in value.upper():
                    if self.parsed_data['metadata']['arch'] == 'unknown':
                        self.parsed_data['metadata']['arch'] = 'X64'
                elif 'X86' in value.upper():
                    if self.parsed_data['metadata']['arch'] == 'unknown':
                        self.parsed_data['metadata']['arch'] = 'X86'
            elif name == 'PhysicalMemory':
                # 格式: "4095 (4293492736)"
                self.parsed_data['hardware']['memory_mb'] = value.split()[0] if value else ''

        logger.debug(f"解析 OS 参数: {self.parsed_data['hardware']}")

    def _parse_config(self, startup_block: str, maxdop_block: str, collation_block: str) -> None:
        """解析配置项"""
        # 解析内存配置（启动参数块包含多个表格）
        if startup_block:
            tables = parse_all_tables(startup_block)
            # 查找包含 'name' 和 'value_in_use' 列的表格
            for table in tables:
                if table and 'name' in table[0] and 'value_in_use' in table[0]:
                    for row in table:
                        name = row.get('name', '')
                        value_in_use = row.get('value_in_use', '')

                        if 'min server memory' in name:
                            self.parsed_data['config']['min_server_memory_mb'] = value_in_use
                        elif 'max server memory' in name:
                            self.parsed_data['config']['max_server_memory_mb'] = value_in_use
                    break

        # 解析 MAXDOP 和连接数
        if maxdop_block:
            rows = parse_table(maxdop_block)
            for row in rows:
                name = row.get('name', '')
                value = row.get('value', '')

                if 'user connections' in name:
                    self.parsed_data['config']['user_connections'] = value
                elif 'max degree of parallelism' in name:
                    # 转换为整数以便后续检查
                    try:
                        self.parsed_data['config']['maxdop'] = int(value) if value else value
                    except (ValueError, TypeError):
                        self.parsed_data['config']['maxdop'] = value

        # 解析排序规则
        if collation_block:
            # 提取排序规则（在 "Server default collation" 后面）
            lines = collation_block.split('\n')
            for i, line in enumerate(lines):
                if 'Server default collation' in line and i + 2 < len(lines):
                    self.parsed_data['config']['collation'] = lines[i + 2].strip()
                    break

        logger.debug(f"解析配置项: {self.parsed_data['config']}")

    def _parse_service_accounts(self, block: str) -> None:
        """解析服务启动账户"""
        if not block:
            return

        lines = block.split('\n')
        current_service = None

        for line in lines:
            # 检测服务类型
            if 'MSSQLSERVER服务启动用户' in line:
                current_service = 'mssqlserver'
            elif 'SQL Agent服务启动用户' in line or 'SQLAgent服务启动用户' in line:
                current_service = 'sqlagent'

            # 提取账户名
            if 'SERVICE_START_NAME' in line and current_service:
                # 格式: "        SERVICE_START_NAME : LocalSystem"
                parts = line.split(':')
                if len(parts) >= 2:
                    account = parts[1].strip()

                    if current_service == 'mssqlserver':
                        self.parsed_data['config']['mssqlserver_account'] = account
                    elif current_service == 'sqlagent':
                        self.parsed_data['config']['sqlagent_account'] = account

        logger.debug(f"解析服务账户: MSSQLSERVER={self.parsed_data['config'].get('mssqlserver_account')}, "
                    f"SQLAgent={self.parsed_data['config'].get('sqlagent_account')}")

    def _parse_databases(self, system_block: str, user_block: str) -> None:
        """解析数据库信息"""
        self.parsed_data['db_state']['system_databases'] = []
        self.parsed_data['db_state']['user_databases'] = []

        # 解析系统库
        if system_block:
            rows = parse_table(system_block)
            self.parsed_data['db_state']['system_databases'] = rows
            logger.debug(f"解析系统库: {len(rows)} 个")

        # 解析用户库
        if user_block:
            rows = parse_table(user_block)
            self.parsed_data['db_state']['user_databases'] = rows
            logger.debug(f"解析用户库: {len(rows)} 个")

    def _parse_jobs(self, block: str) -> None:
        """解析作业信息"""
        if not block:
            return

        rows = parse_table(block)
        self.parsed_data['db_state']['jobs'] = rows
        logger.debug(f"解析作业: {len(rows)} 个")

    def _parse_linked_servers(self, block: str) -> None:
        """解析链接服务器"""
        if not block:
            return

        rows = parse_table(block)
        self.parsed_data['db_state']['linked_servers'] = rows
        logger.debug(f"解析链接服务器: {len(rows)} 个")

    def _parse_log_usage(self, block: str) -> None:
        """解析日志使用情况"""
        if not block:
            return

        rows = parse_table(block)
        self.parsed_data['db_state']['log_usage'] = rows
        logger.debug(f"解析日志使用: {len(rows)} 个数据库")

    def _parse_backup(self, block: str) -> None:
        """解析备份信息并聚合"""
        if not block:
            return

        rows = parse_table(block)
        self.parsed_data['backup']['backup_history'] = rows
        logger.debug(f"解析备份记录: {len(rows)} 条")

        # 聚合备份历史
        if rows:
            aggregated = aggregate_backup_history(rows)
            self.parsed_data['backup']['summary'] = aggregated['summary']
            self.parsed_data['backup']['total_dbs'] = aggregated['total_dbs']
            self.parsed_data['backup']['backed_up_dbs'] = aggregated['backed_up_dbs']

            # 从用户数据库列表中找出无备份的库
            user_dbs = self.parsed_data['db_state'].get('user_databases', [])
            backed_up_db_names = set(aggregated['summary'].keys())
            no_backup_dbs = []

            for db in user_dbs:
                # 兼容多种列名：数据库名称、名称、name
                db_name = db.get('数据库名称') or db.get('名称') or db.get('name', '')
                if db_name and db_name not in backed_up_db_names:
                    no_backup_dbs.append(db_name)

            self.parsed_data['backup']['no_backup_dbs'] = no_backup_dbs
            logger.debug(f"备份聚合: {aggregated['backed_up_dbs']}/{aggregated['total_dbs']} 个库有备份记录，{len(no_backup_dbs)} 个用户库无备份")
        else:
            # 如果没有备份记录，所有用户库都算无备份
            user_dbs = self.parsed_data['db_state'].get('user_databases', [])
            # 兼容多种列名：数据库名称、名称、name
            no_backup_dbs = [
                db.get('数据库名称') or db.get('名称') or db.get('name', '')
                for db in user_dbs
                if db.get('数据库名称') or db.get('名称') or db.get('name', '')
            ]
            self.parsed_data['backup']['no_backup_dbs'] = no_backup_dbs
            logger.warning(f"未找到备份记录，{len(no_backup_dbs)} 个用户库无备份")

    def _parse_top_sql(self, sections: Dict[str, str]) -> None:
        """
        解析 TOP SQL 相关章节

        Args:
            sections: 章节字典
        """
        # 解析 SQL 文本映射
        sql_texts = {}
        for text_key in ['top_cpu_text', 'top_elapsed_text', 'top_logical_text', 'top_physical_text']:
            if text_key in sections:
                sql_texts.update(parse_sql_texts(sections[text_key]))

        logger.debug(f"解析 SQL 文本: {len(sql_texts)} 个 handle")

        # 解析 TOP CPU
        if 'top_cpu' in sections:
            rows = parse_table(sections['top_cpu'])
            # 关联 SQL 文本
            for row in rows:
                handle = row.get('sql_handle', '')
                if handle in sql_texts:
                    row['statement_text'] = sql_texts[handle]
            self.parsed_data['performance']['top_cpu'] = rows[:10]  # 截断到 TOP 10
            logger.debug(f"解析 TOP CPU: {len(rows)} 条")

        # 解析 TOP ELAPSED
        if 'top_elapsed' in sections:
            rows = parse_table(sections['top_elapsed'])
            # 关联 SQL 文本
            for row in rows:
                handle = row.get('sql_handle', '')
                if handle in sql_texts:
                    row['statement_text'] = sql_texts[handle]
            self.parsed_data['performance']['top_elapsed'] = rows[:10]  # 截断到 TOP 10
            logger.debug(f"解析 TOP ELAPSED: {len(rows)} 条")

        # 解析 TOP LOGICAL
        if 'top_logical' in sections:
            rows = parse_table(sections['top_logical'])
            # 关联 SQL 文本
            for row in rows:
                handle = row.get('sql_handle', '')
                if handle in sql_texts:
                    row['statement_text'] = sql_texts[handle]
            self.parsed_data['performance']['top_logical'] = rows[:10]  # 截断到 TOP 10
            logger.debug(f"解析 TOP LOGICAL: {len(rows)} 条")

        # 解析 TOP PHYSICAL
        if 'top_physical' in sections:
            rows = parse_table(sections['top_physical'])
            # 关联 SQL 文本
            for row in rows:
                handle = row.get('sql_handle', '')
                if handle in sql_texts:
                    row['statement_text'] = sql_texts[handle]
            self.parsed_data['performance']['top_physical'] = rows[:10]  # 截断到 TOP 10
            logger.debug(f"解析 TOP PHYSICAL: {len(rows)} 条")

    def _parse_performance(self, cache_block: str, wait_block: str) -> None:
        """解析性能指标"""
        # 解析缓存使用
        if cache_block:
            rows = parse_table(cache_block)
            self.parsed_data['performance']['cache_usage'] = rows
            logger.debug(f"解析缓存使用: {len(rows)} 条")

        # 解析等待事件
        if wait_block:
            rows = parse_table(wait_block)
            self.parsed_data['performance']['wait_events'] = rows
            logger.debug(f"解析等待事件: {len(rows)} 条")

    def _parse_security(self, sysadmin_block: str) -> None:
        """解析安全信息"""
        if not sysadmin_block:
            return

        rows = parse_table(sysadmin_block)
        self.parsed_data['security']['sysadmin_users'] = rows
        logger.debug(f"解析 sysadmin 用户: {len(rows)} 个")

