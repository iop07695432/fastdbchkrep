"""
数据模型类 - 从原markdown_generator.py迁移而来
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class InspectionSummaryData:
    """巡检摘要数据类"""
    hostname: str
    sid: str
    db_model: str
    inspection_time: str
    file_status_content: str


@dataclass
class SystemInfoData:
    """系统信息数据类"""
    system_version: str
    kernel_version: str
    kernel_params: str
    resource_limits: str
    disk_scheduler: str
    system_uptime: str


@dataclass
class HardwareInfoData:
    """硬件信息数据类"""
    cpu_model: str
    cpu_cores: int
    cpu_logical_cores: int
    cpu_physical_cores: int
    memory_total_gb: int
    disk_info: str


@dataclass
class DatabaseConfigData:
    """数据库配置信息数据类"""
    # 基本信息（必需字段）
    database_version: str
    instance_names: str  # 单机显示一个，集群显示多个逗号分割

    # 存储信息（必需字段）
    total_datafile_size_mb: str
    total_segment_size_mb: str
    sga_size_mb: str
    shared_pool_size_mb: str
    buffer_cache_size_mb: str
    db_block_size: str

    # 表空间和文件信息（必需字段）
    tablespace_count: str
    datafile_count: str
    temp_tablespace_size: str
    undo_tablespace_size: str
    undotbs2_size: str  # RAC专用
    control_file_count: str

    # 在线日志信息（必需字段）
    online_logs_same_size: str
    log_members_per_group: str

    # 归档和连接信息（必需字段）
    archive_frequency_minutes: str  # 默认为"-"
    daily_archive_size_mb: str     # 默认为"-"
    current_connections: str

    # 灾备信息（必需字段）
    disaster_recovery_mode: str
    
    # RMAN备份配置状态（必需字段）
    rman_backup_status: str  # RMAN备份配置状态：有 或 无
    
    # A1部分 - 数据库实例基本信息（可选字段）
    db_name: str = "-"  # DB_NAME
    db_unique_name: str = "-"  # DB_UNIQUE_NAME  
    database_role: str = "-"  # DATABASE_ROLE
    open_mode: str = "-"  # OPEN_MODE
    host_name: str = "-"  # HOST_NAME
    startup_time: str = "-"  # STARTUP_TIME
    
    # A3部分 - 数据库字符集信息（可选字段）
    database_charset: str = "-"  # NLS_CHARACTERSET
    database_nchar_charset: str = "-"  # NLS_NCHAR_CHARACTERSET
    nls_language: str = "-"  # NLS_LANGUAGE
    nls_territory: str = "-"  # NLS_TERRITORY
    
    # A4部分 - 归档模式信息（可选字段）
    log_mode: str = "-"  # LOG_MODE
    archive_mode: str = "-"  # ARCHIVE_MODE
    
    # C1部分 - 重要日志文件路径（可选字段）
    c1_alert_log_path: str = "-"  # ALERT_LOG路径
    audit_file_dest: str = "-"  # AUDIT_FILE_DEST路径
    core_dump_dest: str = "-"  # CORE_DUMP_DEST路径
    diagnostic_dest: str = "-"  # DIAGNOSTIC_DEST路径
    user_dump_dest: str = "-"  # USER_DUMP_DEST路径
    
    # 其他日志路径信息（可选字段）
    alert_log_path: str = "-"  # 原有ALERT_LOG路径（保持兼容性）


@dataclass
class ResourceConfigData:
    """数据库资源相关配置数据类"""
    # 服务器资源
    server_logical_cores: str
    server_mem_size_gb: str
    
    # 数据库CPU配置
    db_cpu_count: str
    db_parallel_max_servers: str
    db_parallel_min_servers: str
    db_processes: str
    db_sessions: str
    db_transactions: str
    
    # 数据库内存配置
    db_sga_size_gb: str
    db_pga_size_gb: str
    db_log_buffer_mb: str
    db_open_cursors: str
    db_session_cached_cursors: str


@dataclass
class ControlFileLogData:
    """控制文件和在线日志数据类"""
    control_file_info: str
    online_log_info: str


@dataclass
class TablespaceFileData:
    """表空间和数据文件数据类"""
    datafile_list: str
    tablespace_basic_info: str
    high_usage_tablespaces: str
    no_autoextend_files: str


@dataclass
class ArchiveStatData:
    """归档统计数据类"""
    archive_statistics: str


@dataclass
class AsmDiskData:
    """ASM磁盘详细信息数据类"""
    asm_disk_detail: str


@dataclass
class PlsqlVirusData:
    """PL/SQLDeveloper破解版勒索病毒检查数据类"""
    virus_check_info: str


@dataclass
class RmanInfoData:
    """RMAN备份信息数据类"""
    backup_strategy: str  # RMAN备份策略（第1个RMAN>到第2个RMAN>之间内容）
    backup_details: str   # RMAN备份明细（第2个RMAN>到第3个RMAN>之间内容）
    backup_sets: str      # RMAN备份集（第3个RMAN>到第4个RMAN>之间内容）
    backup_count: int     # 备份集总数量（统计List of Backups表格中TY='B'的行数）
    available_count: int  # 可用备份集数量（S='A'的行数）
    expired_count: int    # 过期备份集数量（S='X'的行数）
    full_count: int       # 全量备份数量（LV='0'的行数）
    incremental_count: int  # 增量备份数量（LV='1'的行数）


@dataclass
class DataGuardInfoData:
    """Data Guard信息数据类"""
    basic_config_check: str = ""         # D1. Data Guard 基本配置检查
    archive_dest_config: str = ""        # D2. 归档传输目的地配置
    dg_related_params: str = ""          # D3. Data Guard 相关参数
    dg_status_messages: str = ""         # D4. Data Guard 状态消息 (最近50条)
    transport_apply_lag: str = ""        # D5. 传输/应用延迟统计
    archive_log_apply: str = ""          # D6. 归档日志应用状态 (仅Standby数据库)
    mrp_process_status: str = ""         # D7. MRP进程状态 (仅Standby数据库)


@dataclass
class AdrciInfoData:
    """ADRCI诊断信息数据类"""
    adrci_content: str    # 05_adrci_ora.txt全部内容


@dataclass
class AlertLogData:
    """Alert日志分析数据类"""
    alert_summary: str    # Alert日志分析结果总结
    alert_log_path: str   # ALERT_LOG路径
    grouped_errors: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)  # 按时间戳分组的错误


@dataclass
class OsPerformanceData:
    """操作系统性能监控数据类"""
    hostname: str = ""
    cpu_data: str = ""        # CPU使用率数据（08:00~12:00）
    memory_data: str = ""     # 内存使用率数据（08:00~12:00）
    disk_io_data: str = ""    # 磁盘IO数据（08:00~12:00）
    
    
@dataclass
class DiskSpaceData:
    """磁盘空间使用数据类"""
    disk_space_info: List[Dict[str, str]] = field(default_factory=list)  # 从02_hardware_info.json获取的磁盘空间信息


@dataclass
class AwrReportData:
    """AWR报告数据类"""
    # 数据库实例信息
    db_name: str = ""
    db_id: str = ""
    instance: str = ""
    inst_num: str = ""
    startup_time: str = ""
    release: str = ""
    rac: str = ""
    
    # 主机信息
    host_name: str = ""
    platform: str = ""
    cpus: str = ""
    cores: str = ""
    sockets: str = ""
    memory_gb: str = ""
    
    # 快照信息
    begin_snap_id: str = ""
    begin_snap_time: str = ""
    begin_sessions: str = ""
    begin_cursors_per_session: str = ""
    end_snap_id: str = ""
    end_snap_time: str = ""
    end_sessions: str = ""
    end_cursors_per_session: str = ""
    elapsed_minutes: str = ""
    db_time_minutes: str = ""
    instances: str = ""