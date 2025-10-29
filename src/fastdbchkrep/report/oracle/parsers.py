"""
Oracle数据库解析器类 - 从markdown_generator.py迁移而来
包含所有用于解析Oracle数据库巡检文件的Parser类
"""
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger

from .models import *


class SystemInfoParser:
    """01_system_info.txt文件解析器"""

    @staticmethod
    def parse_system_info(file_path: Path) -> Optional[SystemInfoData]:
        """
        解析01_system_info.txt文件

        Args:
            file_path: 文件路径

        Returns:
            SystemInfoData: 解析后的数据，解析失败返回None
        """
        try:
            content = DataGuardInfoParser._read_text_best_effort(file_path)

            # 提取系统版本信息
            system_version_match = re.search(r'========== 系统版本信息 ==========\n(.+)', content)
            system_version = system_version_match.group(1).strip() if system_version_match else "-"

            # 提取内核版本
            kernel_version_match = re.search(r'========== 内核版本 ==========\n(.+)', content)
            kernel_version = kernel_version_match.group(1).strip() if kernel_version_match else "-"

            # 提取内核参数
            kernel_params_section = re.search(
                r'========== 生效的内核参数 ==========\n(.*?)(?=\n========== [^=]+==========|\Z)',
                content,
                re.DOTALL
            )
            if kernel_params_section:
                kernel_params_raw = kernel_params_section.group(1).strip()
                # 过滤掉备注行（以 --- 开头和结尾的行），保留所有有效的参数配置
                kernel_params_lines = []
                for line in kernel_params_raw.split('\n'):
                    line = line.strip()
                    # 只保留包含等号(=)的参数行，过滤掉备注行和空行
                    if line and '=' in line and not (line.startswith('---') and line.endswith('---')):
                        kernel_params_lines.append(line)
                kernel_params = '\n'.join(kernel_params_lines)
            else:
                kernel_params = "-"

            # 提取资源限制参数
            resource_limits_section = re.search(
                r'========== 资源限制参数 ==========\n(.*?)(?=\n==========|\n\n|\Z)',
                content,
                re.DOTALL
            )
            resource_limits = resource_limits_section.group(1).strip() if resource_limits_section else "-"

            # 提取磁盘调度算法
            disk_scheduler_match = re.search(r'========== 磁盘调度算法 ==========\n(.*?)(?=\n==========|\n\n|\Z)', content, re.DOTALL)
            disk_scheduler = disk_scheduler_match.group(1).strip() if disk_scheduler_match else "-"

            # 提取系统启动时间和负载
            uptime_match = re.search(r'========== 系统启动时间和负载 ==========\n(.+)', content)
            system_uptime = uptime_match.group(1).strip() if uptime_match else "-"

            return SystemInfoData(
                system_version=system_version,
                kernel_version=kernel_version,
                kernel_params=kernel_params,
                resource_limits=resource_limits,
                disk_scheduler=disk_scheduler,
                system_uptime=system_uptime
            )

        except Exception as e:
            logger.error(f"解析01_system_info.txt失败: {e}")
            return None


class HealthCheckParser:
    """04_health_check.txt文件解析器"""

    @staticmethod
    def parse_health_check(file_path: Path, instance_names: str, rman_file_path: Optional[Path] = None) -> Optional[DatabaseConfigData]:
        """
        解析04_health_check.txt文件

        Args:
            file_path: 文件路径
            instance_names: 实例名称（从meta文件获取）
            rman_file_path: RMAN信息文件路径（可选）

        Returns:
            DatabaseConfigData: 解析后的数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取SGA相关信息
            sga_size_mb = HealthCheckParser._extract_sga_size(content)
            shared_pool_size_mb = HealthCheckParser._extract_shared_pool_size(content)
            buffer_cache_size_mb = HealthCheckParser._extract_buffer_cache_size(content)

            # 提取存储信息
            total_datafile_size_mb = HealthCheckParser._extract_datafile_size(content)
            total_segment_size_mb = HealthCheckParser._extract_segment_size(content)
            db_block_size = HealthCheckParser._extract_db_block_size(content)

            # 提取表空间和文件信息
            tablespace_count = HealthCheckParser._extract_tablespace_count(content)
            datafile_count = HealthCheckParser._extract_datafile_count(content)
            temp_tablespace_size = HealthCheckParser._extract_temp_tablespace_size(content)
            undo_tablespace_size = HealthCheckParser._extract_undo_tablespace_size(content)
            undotbs2_size = HealthCheckParser._extract_undotbs2_size(content)
            control_file_count = HealthCheckParser._extract_control_file_count(content)

            # 提取在线日志信息
            online_logs_same_size = HealthCheckParser._extract_online_logs_same_size(content)
            log_members_per_group = HealthCheckParser._extract_log_members_per_group(content)

            # 提取连接数信息
            current_connections = HealthCheckParser._extract_current_connections(content)

            # 提取灾备信息
            disaster_recovery_mode = HealthCheckParser._extract_disaster_recovery_mode(content)

            # 提取A1部分 - 数据库实例基本信息
            a1_data = HealthCheckParser._extract_a1_database_instance_info(content)
            
            # 提取A3部分 - 字符集信息
            a3_data = HealthCheckParser._extract_a3_charset_info(content)
            
            # 提取A4部分 - 归档模式信息
            a4_data = HealthCheckParser._extract_a4_archive_info(content)
            
            # 提取C1部分 - 重要日志文件路径
            c1_data = HealthCheckParser._extract_c1_log_paths(content)
            
            # 检查RMAN备份状态
            rman_backup_status = "无"
            if rman_file_path and rman_file_path.exists():
                rman_backup_status = RmanInfoParser.check_rman_backup_status(rman_file_path)
            
            # 提取ALERT_LOG路径
            alert_log_path = HealthCheckParser._extract_alert_log_path_from_health_check(content)

            return DatabaseConfigData(
                # 使用A1部分提取的版本和实例名
                database_version=a1_data.get('version', '-'),
                instance_names=a1_data.get('instance_name', '-'),
                # A1部分其他数据
                db_name=a1_data.get('db_name', '-'),
                db_unique_name=a1_data.get('db_unique_name', '-'),
                database_role=a1_data.get('database_role', '-'),
                open_mode=a1_data.get('open_mode', '-'),
                host_name=a1_data.get('host_name', '-'),
                startup_time=a1_data.get('startup_time', '-'),
                # A3部分数据
                database_charset=a3_data.get('nls_characterset', '-'),
                database_nchar_charset=a3_data.get('nls_nchar_characterset', '-'),
                nls_language=a3_data.get('nls_language', '-'),
                nls_territory=a3_data.get('nls_territory', '-'),
                # A4部分数据
                log_mode=a4_data.get('log_mode', '-'),
                archive_mode=a4_data.get('archive_mode', '-'),
                # C1部分数据
                c1_alert_log_path=c1_data.get('alert_log_path', '-'),
                audit_file_dest=c1_data.get('audit_file_dest', '-'),
                core_dump_dest=c1_data.get('core_dump_dest', '-'),
                diagnostic_dest=c1_data.get('diagnostic_dest', '-'),
                user_dump_dest=c1_data.get('user_dump_dest', '-'),
                total_datafile_size_mb=total_datafile_size_mb,
                total_segment_size_mb=total_segment_size_mb,
                sga_size_mb=sga_size_mb,
                shared_pool_size_mb=shared_pool_size_mb,
                buffer_cache_size_mb=buffer_cache_size_mb,
                db_block_size=db_block_size,
                tablespace_count=tablespace_count,
                datafile_count=datafile_count,
                temp_tablespace_size=temp_tablespace_size,
                undo_tablespace_size=undo_tablespace_size,
                undotbs2_size=undotbs2_size,
                control_file_count=control_file_count,
                online_logs_same_size=online_logs_same_size,
                log_members_per_group=log_members_per_group,
                archive_frequency_minutes="-",
                daily_archive_size_mb="-",
                current_connections=current_connections,
                disaster_recovery_mode=disaster_recovery_mode,
                rman_backup_status=rman_backup_status,
                alert_log_path=alert_log_path
            )

        except Exception as e:
            logger.error(f"解析04_health_check.txt失败: {e}")
            return None

    @staticmethod
    def _extract_database_version(content: str) -> str:
        """提取数据库版本信息"""
        # 查找 "1.数据库版本号和实例" 章节
        version_section_match = re.search(r'1\.数据库版本号和实例.*?VERSION.*?-+', content, re.DOTALL)
        if version_section_match:
            version_section = version_section_match.group(0)
            
            # 尝试不同的Oracle版本格式匹配
            patterns = [
                # Oracle db_check/12c/18c/19c/21c等标准格式
                r'Oracle Database.*?Enterprise Edition Release ([\d\.]+(?:\.\d+)*) - (\d+bit)',
                r'Oracle Database.*?Standard Edition Release ([\d\.]+(?:\.\d+)*) - (\d+bit)',
                r'Oracle Database.*?Express Edition Release ([\d\.]+(?:\.\d+)*) - (\d+bit)',
                # 只匹配版本号，不区分版本类型
                r'Oracle Database.*?Release ([\d\.]+(?:\.\d+)*) - (\d+bit)',
                # 更宽泛的版本号匹配
                r'Oracle Database.*?([\d\.]+(?:\.\d+)*)',
            ]
            
            for pattern in patterns:
                version_match = re.search(pattern, version_section)
                if version_match:
                    if len(version_match.groups()) >= 2:
                        # 有版本号和位数信息
                        version_number = version_match.group(1)
                        bit_info = version_match.group(2)
                        # 判断版本类型
                        if 'Enterprise Edition' in version_match.group(0):
                            return f"Enterprise Edition Release {version_number} - {bit_info}"
                        elif 'Standard Edition' in version_match.group(0):
                            return f"Standard Edition Release {version_number} - {bit_info}"
                        elif 'Express Edition' in version_match.group(0):
                            return f"Express Edition Release {version_number} - {bit_info}"
                        else:
                            return f"Release {version_number} - {bit_info}"
                    else:
                        # 只有版本号信息
                        version_number = version_match.group(1)
                        return f"Release {version_number}"
        
        # 如果上面的方法失败，尝试在整个文件中查找版本号
        fallback_patterns = [
            r'Oracle Database \d+[gc].*?Enterprise Edition Release ([\d\.]+(?:\.\d+)*) - (\d+bit)',
            r'Oracle Database.*?Release ([\d\.]+(?:\.\d+)*)',
            r'VERSION\s*[\r\n]+.*?Release ([\d\.]+(?:\.\d+)*)',
        ]
        
        for pattern in fallback_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    return f"Release {match.group(1)} - {match.group(2)}"
                else:
                    return f"Release {match.group(1)}"
        
        return "-"

    @staticmethod
    def _extract_sga_size(content: str) -> str:
        """提取SGA大小（MB）"""
        # 查找"3.SGA大小"部分的Total System Global Area
        pattern = r'3\.SGA大小.*?Total System Global Area\s+([\d\.E\+]+)\s+bytes'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            bytes_value = float(match.group(1))
            mb_value = int(bytes_value / (1024 * 1024))
            return str(mb_value)
        return "-"

    @staticmethod
    def _extract_shared_pool_size(content: str) -> str:
        """提取共享池大小（MB）"""
        # 从sga_target参数推算，或查找具体的shared pool信息
        pattern = r'sga_target\s+(\d+)'
        match = re.search(pattern, content)
        if match:
            # SGA target通常包含共享池，这里简化处理，返回总SGA的一部分
            sga_bytes = int(match.group(1))
            # 通常共享池约占SGA的15-20%，这里取18%作为估算
            shared_pool_mb = int(sga_bytes * 0.18 / (1024 * 1024))
            return str(shared_pool_mb)
        return "-"

    @staticmethod
    def _extract_buffer_cache_size(content: str) -> str:
        """提取数据高速缓冲区大小（MB）"""
        # 查找Database Buffers信息
        pattern = r'Database Buffers\s+([\d\.E\+]+)\s+bytes'
        match = re.search(pattern, content)
        if match:
            bytes_value = float(match.group(1))
            mb_value = int(bytes_value / (1024 * 1024))
            return str(mb_value)
        return "-"

    @staticmethod
    def _extract_datafile_size(content: str) -> str:
        """提取所有数据文件大小（MB）"""
        # 查找"所有数据文件大小"部分
        pattern = r'所有数据文件大小.*?(\d+)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_segment_size(content: str) -> str:
        """提取所有segment大小（MB）"""
        # 查找"纯数据大小"部分的total值
        pattern = r'纯数据大小.*?total\s+(\d+)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_db_block_size(content: str) -> str:
        """提取DB_BLOCK_SIZE"""
        pattern = r'db_block_size\s+(\d+)'
        match = re.search(pattern, content)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_tablespace_count(content: str) -> str:
        """提取表空间数目"""
        pattern = r'表空间数目.*?(\d+)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_datafile_count(content: str) -> str:
        """提取数据文件数目"""
        # 优先匹配显式“数据文件数目”小节（COUNT(*) 表格输出）
        try:
            sec_start = content.find('数据文件数目')
            if sec_start != -1:
                # 扩大窗口，逐行扫描，寻找第一个“纯数字”的行（跳过表头/分隔线）
                tail = content[sec_start:sec_start + 5000]
                for line in tail.splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith('-') or 'COUNT' in s.upper():
                        continue
                    if s.isdigit():
                        return s
        except Exception:
            pass

        # 兼容 SQL*Plus 英文尾注："n rows selected"
        m2 = re.search(r'数据文件列表[\s\S]*?(\d+)\s+rows selected', content, re.IGNORECASE)
        if m2:
            return m2.group(1)

        # 兼容 SQL*Plus 中文尾注："选定了 n 行" 或 "n 行已选择"（常见翻译）
        m3 = re.search(r'数据文件列表[\s\S]*?(?:选定了|已选择|行已选择)\s*(\d+)\s*行', content)
        if m3:
            return m3.group(1)

        return "-"

    @staticmethod
    def _extract_temp_tablespace_size(content: str) -> str:
        """提取临时表空间大小"""
        pattern = r'TEMP\s+(\d+)'
        match = re.search(pattern, content)
        return f"{match.group(1)}MB" if match else "-"

    @staticmethod
    def _extract_undo_tablespace_size(content: str) -> str:
        """提取Undo表空间大小"""
        # 在表空间使用情况中查找UNDOTBS1
        pattern = r'UNDOTBS1\s+([\d\.]+)\s+\d+\s+([\d\.]+)'
        match = re.search(pattern, content)
        if match:
            total_size = float(match.group(1))
            return f"{int(total_size)}MB"
        return "-"

    @staticmethod
    def _extract_undotbs2_size(content: str) -> str:
        """提取UNDOTBS2大小（RAC专用）"""
        pattern = r'UNDOTBS2\s+([\d\.]+)'
        match = re.search(pattern, content)
        if match:
            size_mb = float(match.group(1))
            return f"{int(size_mb)}MB"
        return "-"

    @staticmethod
    def _extract_control_file_count(content: str) -> str:
        """提取控制文件数目"""
        # 查找控制文件路径部分，统计.ctl文件数量
        pattern = r'C2\. 控制文件路径.*?(?=C3\.|==================== [^=]+===================|\Z)'
        section_match = re.search(pattern, content, re.DOTALL)
        if section_match:
            ctl_files = re.findall(r'\.ctl', section_match.group(0))
            return str(len(ctl_files))
        return "-"

    @staticmethod
    def _extract_online_logs_same_size(content: str) -> str:
        """检查是否所有在线日志都是同样大小"""
        # 查找日志文件信息部分
        log_section = re.search(
            r'8\.日志文件信息.*?(?=\d+\..*?信息|==================|$)', 
            content, 
            re.DOTALL
        )
        
        if not log_section:
            return "-"
            
        log_content = log_section.group(0)
        
        # 提取所有MBYTES值，查找类似 "     1       1       1081      500          1" 这样的行
        # 其中第4个数字字段是MBYTES
        mbytes_pattern = r'\s+\d+\s+\d+\s+\d+\s+(\d+)\s+\d+\s+(?:YES|NO)'
        mbytes_matches = re.findall(mbytes_pattern, log_content)
        
        if not mbytes_matches:
            return "-"
            
        # 检查所有MBYTES值是否相同
        unique_sizes = set(mbytes_matches)
        if len(unique_sizes) == 1:
            return "是"
        else:
            return "否"

    @staticmethod
    def _extract_log_members_per_group(content: str) -> str:
        """提取每组在线日志的成员数"""
        # 查找日志文件信息中的MEMBERS列
        pattern = r'GROUP#.*?MEMBERS.*?(\d+)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_current_connections(content: str) -> str:
        """提取当前数据库连接数"""
        # 查找"2.当前用户数"部分的COUNT(*)值（跳过INST_ID列的数字，取第二个数字）
        pattern = r'2\.当前用户数.*?COUNT\(\*\).*?\d+\s+(\d+)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else "-"

    @staticmethod
    def _extract_disaster_recovery_mode(content: str) -> str:
        """提取现有灾备方式"""
        # 查找DATA GUARD信息段落
        dg_section = re.search(
            r'==================== DATA GUARD INFORMATION ====================.*?(?===================== [^=]+===================|\Z)',
            content,
            re.DOTALL
        )

        if not dg_section:
            return "未找到DG容灾库相关信息"

        dg_content = dg_section.group(0)

        # Step 0: 确定角色（主库/备库）
        is_primary = re.search(r'DG_ROLE.*?PRIMARY DATABASE|database_role.*?PRIMARY', dg_content, re.IGNORECASE)
        is_standby = re.search(r'DG_ROLE.*(PHYSICAL STANDBY|LOGICAL STANDBY)|database_role.*(STANDBY)', dg_content, re.IGNORECASE)

        # Step 1: 检查是否配置了DG远端目的地
        has_remote_dest = False
        remote_dest_valid = False

        # 查找TARGET=STANDBY且STATUS=VALID的配置
        if re.search(r'TARGET.*?STANDBY.*?STATUS.*?VALID', dg_content, re.IGNORECASE):
            has_remote_dest = True
            remote_dest_valid = True

        # 查找SERVICE=远端服务名的配置（而非本地路径）
        if re.search(r'SERVICE\s*=\s*[^\s/]+', dg_content):
            has_remote_dest = True
            # 检查该SERVICE配置是否有效
            if re.search(r'SERVICE.*?STATUS.*?VALID', dg_content, re.IGNORECASE):
                remote_dest_valid = True

        # 检查是否只有本地路径（无远端配置）
        local_only = re.search(r'DESTINATION.*?/[^/\s]+/[^/\s]+', dg_content) and not has_remote_dest

        # Step 1判断：如果只有本地路径，没有远端目的地
        if local_only or not has_remote_dest:
            return "未找到DG容灾库相关信息"

        # Step 2: 在备用端检查MRP进程
        has_mrp = re.search(r'MRP0|MR\(fg\)', dg_content, re.IGNORECASE)

        # Step 3: 检查应用状态
        any_applied_yes = re.search(r'APPLIED.*?(YES|IN-MEMORY)', dg_content, re.IGNORECASE)
        applied_all_no = re.search(r'APPLIED.*?NO', dg_content) and not any_applied_yes

        # Step 4: 根据决策树返回结果
        if has_remote_dest and remote_dest_valid:
            # 有有效的远端配置
            if is_standby and not has_mrp:
                # 备库端但无MRP进程
                return "有dg容灾库配置但未启用应用"
            elif applied_all_no and not has_mrp:
                # 日志未应用且无MRP进程
                return "有dg容灾库配置但未启用应用"
            elif any_applied_yes or has_mrp:
                # 有应用进程或日志在应用
                return "有dg容灾库"
            else:
                # 有配置但状态不明
                return "有dg容灾库"
        elif has_remote_dest and not remote_dest_valid:
            # 有远端配置但无效
            return "有dg容灾库配置但传输异常"

        return "未找到DG容灾库相关信息"

    @staticmethod
    def _extract_database_charset(content: str) -> str:
        """提取数据库字符集信息"""
        # 查找A3. 数据库字符集信息部分
        charset_section = re.search(
            r'A3\. 数据库字符集信息.*?(?=\[DB_BASIC_INFO_END\]|A4\.|==================)',
            content,
            re.DOTALL
        )
        
        if not charset_section:
            return "-"
            
        charset_content = charset_section.group(0)
        
        # 提取NLS_CHARACTERSET值
        charset_match = re.search(r'NLS_CHARACTERSET\s+(\S+)', charset_content)
        if charset_match:
            return charset_match.group(1)
        
        return "-"

    @staticmethod
    def _extract_database_nchar_charset(content: str) -> str:
        """提取数据库国家字符集信息"""
        # 查找A3. 数据库字符集信息部分
        charset_section = re.search(
            r'A3\. 数据库字符集信息.*?(?=\[DB_BASIC_INFO_END\]|A4\.|==================)',
            content,
            re.DOTALL
        )
        
        if not charset_section:
            return "-"
            
        charset_content = charset_section.group(0)
        
        # 提取NLS_NCHAR_CHARACTERSET值
        nchar_charset_match = re.search(r'NLS_NCHAR_CHARACTERSET\s+(\S+)', charset_content)
        if nchar_charset_match:
            return nchar_charset_match.group(1)
        
        return "-"

    @staticmethod
    def _extract_alert_log_path_from_health_check(content: str) -> str:
        """从04_health_check.txt中提取ALERT_LOG路径"""
        # 查找DATABASE LOG PATHS章节
        log_paths_section = re.search(r'\[DB_LOG_PATHS_START\](.*?)\[DB_LOG_PATHS_END\]', content, re.DOTALL)
        if log_paths_section:
            section_content = log_paths_section.group(1)
            
            # 查找ALERT_LOG行
            alert_log_match = re.search(r'ALERT_LOG\s+(.+)', section_content)
            if alert_log_match:
                # 提取路径，去除多余空格
                alert_log_path = alert_log_match.group(1).strip()
                return alert_log_path
        
        return "-"

    @staticmethod
    def _extract_a1_database_instance_info(content: str) -> Dict[str, str]:
        """从A1部分提取数据库实例基本信息"""
        result = {
            'instance_name': '-',     # INSTANCE_NAME
            'db_name': '-',           # DB_NAME
            'db_unique_name': '-',    # DB_UNIQUE_NAME 
            'database_role': '-',     # DATABASE_ROLE
            'open_mode': '-',         # OPEN_MODE
            'version': '-',           # VERSION
            'host_name': '-',         # HOST_NAME
            'startup_time': '-'       # STARTUP_TIME
        }
        
        try:
            # 查找A1.数据库实例基本信息部分
            a1_section = re.search(
                r'A1\.\s*数据库实例基本信息.*?(?=A[2-9]\.|$)', 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            if a1_section:
                section_content = a1_section.group(0)
                
                # 查找数据行（非标题行和分隔线）
                lines = section_content.split('\n')
                for line in lines:
                    # 跳过标题行和分隔线
                    if ('INST_ID' in line or 'INSTANCE_NAME' in line or 
                        line.strip().startswith('-') or not line.strip()):
                        continue
                    
                    # 数据行格式：INST_ID INSTANCE_NAME DB_NAME DB_UNIQUE_NAME DATABASE_ROLE OPEN_MODE VERSION HOST_NAME STARTUP_TIME
                    # 按空格分割，但要考虑时间戳中的空格和OPEN_MODE的"READ WRITE"
                    parts = line.split()
                    if len(parts) >= 9:  # 至少应该有9列
                        try:
                            # 根据已知格式解析各字段
                            # parts[0] = INST_ID, parts[1] = INSTANCE_NAME
                            # parts[2] = DB_NAME, parts[3] = DB_UNIQUE_NAME  
                            # parts[4] = DATABASE_ROLE, parts[5-6] = OPEN_MODE ("READ WRITE")
                            # parts[7] = VERSION, parts[8] = HOST_NAME, parts[9:] = STARTUP_TIME
                            
                            # STARTUP_TIME是最后的字段，可能包含空格（日期时间）
                            startup_time_parts = parts[9:]  # 从第9个元素开始是时间戳
                            startup_time = ' '.join(startup_time_parts) if startup_time_parts else '-'
                            
                            result.update({
                                'instance_name': parts[1].strip(),  # INSTANCE_NAME
                                'db_name': parts[2].strip(),  # DB_NAME
                                'db_unique_name': parts[3].strip(),  # DB_UNIQUE_NAME
                                'database_role': parts[4].strip(),  # DATABASE_ROLE  
                                'open_mode': f'{parts[5]} {parts[6]}'.strip(),  # OPEN_MODE是"READ WRITE"
                                'version': parts[7].strip(),  # VERSION
                                'host_name': parts[8].strip(),  # HOST_NAME 
                                'startup_time': startup_time.strip()  # STARTUP_TIME
                            })
                            break  # 找到第一行数据就够了
                        except (IndexError, ValueError) as e:
                            logger.warning(f"解析A1数据行失败: {line}, 错误: {e}")
                            continue
                            
        except Exception as e:
            logger.error(f"提取A1数据库实例基本信息失败: {e}")
        
        return result

    @staticmethod
    def _extract_a3_charset_info(content: str) -> Dict[str, str]:
        """从A3部分提取数据库字符集信息"""
        result = {
            'nls_language': '-',
            'nls_territory': '-',
            'nls_characterset': '-',
            'nls_nchar_characterset': '-'
        }
        
        try:
            # 查找A3.数据库字符集信息部分
            a3_section = re.search(
                r'A3\.\s*数据库字符集信息.*?(?=A[4-9]\.|$)', 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            if a3_section:
                section_content = a3_section.group(0)
                
                # 查找参数值对
                param_patterns = {
                    'nls_language': r'NLS_LANGUAGE\s+(\S+)',
                    'nls_territory': r'NLS_TERRITORY\s+(\S+)', 
                    'nls_characterset': r'NLS_CHARACTERSET\s+(\S+)',
                    'nls_nchar_characterset': r'NLS_NCHAR_CHARACTERSET\s+(\S+)'
                }
                
                for key, pattern in param_patterns.items():
                    match = re.search(pattern, section_content, re.IGNORECASE)
                    if match:
                        result[key] = match.group(1).strip()
                        
        except Exception as e:
            logger.error(f"提取A3数据库字符集信息失败: {e}")
        
        return result

    @staticmethod
    def _extract_a4_archive_info(content: str) -> Dict[str, str]:
        """从A4部分提取归档模式信息"""
        result = {
            'log_mode': '-',         # LOG_MODE
            'archive_mode': '-'      # ARCHIVE_MODE
        }
        
        try:
            # 查找A4.归档模式信息部分
            a4_section = re.search(
                r'A4\.\s*归档模式信息.*?(?=A[5-9]\.|A4\.1|$)', 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            if a4_section:
                section_content = a4_section.group(0)
                
                # 查找数据行（非标题行和分隔线）
                lines = section_content.split('\n')
                for line in lines:
                    # 跳过标题行、分隔线和A4标题行
                    if ('LOG_MODE' in line or 'ARCHIVE_MODE' in line or 
                        line.strip().startswith('-') or not line.strip() or
                        'A4.' in line or '归档模式信息' in line):
                        continue
                    
                    # 数据行格式：LOG_MODE ARCHIVE_MODE
                    # 例如：ARCHIVELOG ENABLED
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            result.update({
                                'log_mode': parts[0].strip(),      # LOG_MODE
                                'archive_mode': parts[1].strip()   # ARCHIVE_MODE
                            })
                            break  # 找到第一行数据就够了
                        except (IndexError, ValueError) as e:
                            logger.warning(f"解析A4数据行失败: {line}, 错误: {e}")
                            continue
                            
        except Exception as e:
            logger.error(f"提取A4归档模式信息失败: {e}")
        
        return result

    @staticmethod
    def _extract_c1_log_paths(content: str) -> Dict[str, str]:
        """从C1部分提取重要日志文件路径信息"""
        result = {
            'alert_log_path': '-',          # ALERT_LOG
            'audit_file_dest': '-',         # AUDIT_FILE_DEST
            'core_dump_dest': '-',          # CORE_DUMP_DEST
            'diagnostic_dest': '-',         # DIAGNOSTIC_DEST
            'user_dump_dest': '-'           # USER_DUMP_DEST
        }
        
        try:
            # 查找C1.重要日志文件路径部分
            c1_section = re.search(
                r'C1\.\s*重要日志文件路径.*?(?=C[2-9]\.|$)', 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            if c1_section:
                section_content = c1_section.group(0)
                
                # 查找数据行（非标题行和分隔线）
                lines = section_content.split('\n')
                for line in lines:
                    # 跳过标题行、分隔线和C1标题行
                    if ('INST_ID' in line or 'PARAMETER_NAME' in line or 'FILE_PATH' in line or
                        line.strip().startswith('-') or not line.strip() or
                        'C1.' in line or '重要日志文件路径' in line):
                        continue
                    
                    # 数据行格式：INST_ID PARAMETER_NAME FILE_PATH
                    # 例如：1 ALERT_LOG /oracle_db_file/app/oracle_db_file/diag/rdbms/orcl/orcl/trace
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            # FILE_PATH可能包含空格或很长，从第2个元素开始重新组合
                            parameter_name = parts[1].strip()  # PARAMETER_NAME
                            file_path_parts = parts[2:]  # FILE_PATH可能被空格分割
                            file_path = ' '.join(file_path_parts).strip()
                            
                            # 根据参数名映射到result字典
                            if parameter_name == 'ALERT_LOG':
                                result['alert_log_path'] = file_path
                            elif parameter_name == 'AUDIT_FILE_DEST':
                                result['audit_file_dest'] = file_path
                            elif parameter_name == 'CORE_DUMP_DEST':
                                result['core_dump_dest'] = file_path
                            elif parameter_name == 'DIAGNOSTIC_DEST':
                                result['diagnostic_dest'] = file_path
                            elif parameter_name == 'USER_DUMP_DEST':
                                result['user_dump_dest'] = file_path
                                
                        except (IndexError, ValueError) as e:
                            logger.warning(f"解析C1数据行失败: {line}, 错误: {e}")
                            continue
                            
        except Exception as e:
            logger.error(f"提取C1重要日志文件路径失败: {e}")
        
        return result


class HardwareInfoParser:
    """02_hardware_info.json文件解析器"""

    @staticmethod
    def parse_hardware_info(file_path: Path) -> Optional[HardwareInfoData]:
        """
        解析02_hardware_info.json文件

        Args:
            file_path: 文件路径

        Returns:
            HardwareInfoData: 解析后的数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 提取CPU信息
            cpu_info = data.get("cpu", {})
            cpu_model = cpu_info.get("model", "-")
            cpu_cores = cpu_info.get("cores", 0)
            cpu_logical_cores = cpu_info.get("logical_cores", 0)
            cpu_physical_cores = cpu_info.get("physical_cores", 0)

            # 提取内存信息
            memory_info = data.get("memory", {})
            memory_total_gb = memory_info.get("total_gb", 0)

            # 提取磁盘信息，格式化为描述
            disk_info_list = data.get("disk_space", [])
            disk_descriptions = []

            for disk in disk_info_list:
                if disk.get("filesystem") not in ["devtmpfs", "tmpfs", "overlay", "shm", "文件系统"]:
                    filesystem = disk.get("filesystem", "-")
                    size = disk.get("size", "-")
                    mount_point = disk.get("mount_point", "-")
                    disk_descriptions.append(f"{filesystem}: {size} ({mount_point})")

            disk_info = "<br>".join(disk_descriptions) if disk_descriptions else "-"

            return HardwareInfoData(
                cpu_model=cpu_model,
                cpu_cores=cpu_cores,
                cpu_logical_cores=cpu_logical_cores,
                cpu_physical_cores=cpu_physical_cores,
                memory_total_gb=memory_total_gb,
                disk_info=disk_info
            )

        except Exception as e:
            logger.error(f"解析02_hardware_info.json失败: {e}")
            return None


class RmanInfoParser:
    """09_rman_info.txt文件解析器"""

    @staticmethod
    def parse_rman_info(file_path: Path) -> Optional[RmanInfoData]:
        """
        解析09_rman_info.txt文件

        Args:
            file_path: 文件路径

        Returns:
            RmanInfoData: 解析后的数据，解析失败返回None
        """
        try:
            content = RmanInfoParser._read_text_best_effort(file_path)

            # 查找所有RMAN>位置
            rman_positions = []
            for match in re.finditer(r'^RMAN>\s*$', content, re.MULTILINE):
                rman_positions.append(match.end())

            if len(rman_positions) < 3:
                logger.warning(f"RMAN文件中RMAN>标识不足3个，只找到{len(rman_positions)}个")
                return RmanInfoData(
                    backup_strategy="未找到RMAN备份策略信息",
                    backup_details="未找到RMAN备份明细信息",
                    backup_sets="未找到RMAN备份集信息",
                    backup_count=0,
                    available_count=0,
                    expired_count=0,
                    full_count=0,
                    incremental_count=0
                )

            # 提取第1个RMAN>到第2个RMAN>之间的内容（备份策略）
            backup_strategy = content[rman_positions[0]:rman_positions[1]].strip()
            backup_strategy = RmanInfoParser._clean_rman_content(backup_strategy)

            # 提取第2个RMAN>到第3个RMAN>之间的内容（备份明细）
            backup_details = content[rman_positions[1]:rman_positions[2]].strip()
            backup_details = RmanInfoParser._clean_rman_content(backup_details)

            # 提取第3个RMAN>之后的内容（备份集）
            backup_sets = ""
            backup_count = 0
            if len(rman_positions) > 2:
                if len(rman_positions) > 3:
                    # 有第4个RMAN>，提取第3个到第4个之间的内容
                    backup_sets = content[rman_positions[2]:rman_positions[3]].strip()
                else:
                    # 只有3个RMAN>，提取第3个之后的全部内容
                    backup_sets = content[rman_positions[2]:].strip()

                backup_sets = RmanInfoParser._clean_rman_content(backup_sets)

                # 分析备份集详细统计信息
                total_count, available_count, expired_count, full_count, incremental_count = RmanInfoParser._analyze_backup_sets(backup_sets)

            return RmanInfoData(
                backup_strategy=backup_strategy or "未找到RMAN备份策略信息",
                backup_details=backup_details or "未找到RMAN备份明细信息",
                backup_sets=backup_sets or "未找到RMAN备份集信息",
                backup_count=total_count,
                available_count=available_count,
                expired_count=expired_count,
                full_count=full_count,
                incremental_count=incremental_count
            )

        except Exception as e:
            logger.error(f"解析09_rman_info.txt失败: {e}")
            return None

    @staticmethod
    def _clean_rman_content(content: str) -> str:
        """清理RMAN内容，移除多余的空白行和特殊字符"""
        if not content:
            return ""

        # 移除前后空白
        content = content.strip()

        # 将连续的多个空白行替换为两个换行符
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)

        # 移除行尾的空格
        content = '\n'.join(line.rstrip() for line in content.split('\n'))

        return content

    @staticmethod
    def _analyze_backup_sets(backup_sets_content: str) -> tuple:
        """
        分析备份集内容，返回详细统计信息
        
        Args:
            backup_sets_content: 备份集内容（List of Backups表格）
            
        Returns:
            tuple: (总数量, 可用数量, 过期数量, 全量数量, 增量数量)
        """
        if not backup_sets_content:
            return (0, 0, 0, 0, 0)

        # 定位List of Backups表格区域
        list_start_pattern = r'(?:List of Backups|备份列表)'
        list_start_match = re.search(list_start_pattern, backup_sets_content, re.IGNORECASE)
        
        if not list_start_match:
            return (0, 0, 0, 0, 0)

        # 从List of Backups开始往后查找
        content_from_list = backup_sets_content[list_start_match.end():]
        
        # 匹配备份集行：以数字开头，TY列为B的行
        # 格式：Key TY LV S Device_Type Completion_Time #Pieces #Copies Compressed Tag
        backup_set_pattern = r'^\s*(\d+)\s+B\s+([01F])\s+([AXU])\s+\w+'
        
        # 初始化计数器
        total_count = 0
        available_count = 0  # S='A'
        expired_count = 0    # S='X'
        full_count = 0       # LV='0'
        incremental_count = 0  # LV='1'
        
        # 逐行分析
        for line in content_from_list.split('\n'):
            match = re.match(backup_set_pattern, line)
            if match:
                total_count += 1
                key_num, level, status = match.groups()
                
                # 按状态分类
                if status == 'A':
                    available_count += 1
                elif status == 'X':
                    expired_count += 1
                
                # 按备份级别分类
                if level in ('0','F'):
                    full_count += 1
                elif level == '1':
                    incremental_count += 1
        
        return (total_count, available_count, expired_count, full_count, incremental_count)

    @staticmethod
    def check_rman_backup_status(file_path: Path) -> str:
        """
        检查RMAN备份配置状态
        
        Args:
            file_path: RMAN信息文件路径
            
        Returns:
            str: RMAN备份配置状态："有" 或 "无"
        """
        try:
            content = RmanInfoParser._read_text_best_effort(file_path)
            
            # 检查是否包含"specification does not match any backup in the repository"关键字
            if "specification does not match any backup in the repository" in content:
                return "无"
            else:
                return "有"
                
        except Exception as e:
            logger.error(f"检查RMAN备份状态失败: {e}")
            return "无"

    @staticmethod
    def _read_text_best_effort(file_path: Path) -> str:
        """尽力读取文本文件，尝试多种常见编码以避免乱码。

        优先使用 utf-8/utf-8-sig，若失败再回退到 gb18030/gbk/cp936/utf-16 等。
        读取失败返回空字符串。
        """
        encodings = [
            'utf-8', 'utf-8-sig',
            'gb18030', 'gbk', 'cp936',
            'utf-16', 'utf-16le', 'utf-16be',
        ]
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        # 最后兜底用二进制读取 + latin1 解码，避免完全空白
        try:
            data = file_path.read_bytes()
            return data.decode('latin-1', errors='ignore')
        except Exception:
            return ""


class DataGuardInfoParser:
    """04_health_check.txt中Data Guard信息解析器"""

    @staticmethod
    def _read_text_best_effort(file_path: Path) -> str:
        encodings = ['utf-8','utf-8-sig','gb18030','gbk','cp936','utf-16','utf-16le','utf-16be']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        try:
            return file_path.read_bytes().decode('latin-1','ignore')
        except Exception:
            return ''

    @staticmethod
    def _sanitize_sqlplus_controls(section_content: str) -> str:
        """移除 SQL*Plus 的控制语句，避免影响表格识别

        会过滤如下常见指令：
        - col/column <name> format ...
        - set <option> ...
        - ttitle/btitle/break/compute/define/undef/prompt 等
        """
        try:
            lines = section_content.splitlines()
            out = []
            pat = re.compile(r"^\s*(col(umn)?\s+\w+\s+format\s+\w+|set\s+\w+|ttitle\b|btitle\b|break\b|compute\b|define\b|undef\b|prompt\b)", re.IGNORECASE)
            for ln in lines:
                if pat.search(ln):
                    continue
                out.append(ln)
            # 收敛多余空行
            cleaned = []
            blank = 0
            for ln in out:
                if ln.strip():
                    cleaned.append(ln)
                    blank = 0
                else:
                    if blank == 0:
                        cleaned.append(ln)
                    blank = 1
            return "\n".join(cleaned).strip()
        except Exception:
            return section_content

    @staticmethod
    def _remove_garbled_content(section_content: str) -> str:
        """移除疑似乱码的行；若整体为乱码则返回空字符串以触发“未找到”占位。"""
        if not section_content:
            return section_content
        tokens = ['�', '��', 'δѡ', 'С�']
        lines = section_content.splitlines()
        kept = []
        for ln in lines:
            if any(tok in ln for tok in tokens):
                continue
            kept.append(ln)
        # 收敛空行
        out=[]; blank=0
        for ln in kept:
            if ln.strip():
                out.append(ln); blank=0
            else:
                if blank==0:
                    out.append(ln)
                blank=1
        result='\n'.join(out).strip()
        if len([l for l in result.splitlines() if l.strip()]) < 2:
            return ''
        return result

    def parse_data_guard_info(file_path: Path) -> Optional[DataGuardInfoData]:
        """
        解析04_health_check.txt文件中的Data Guard信息
        基于关键字提取各个子章节数据

        Args:
            file_path: 文件路径

        Returns:
            DataGuardInfoData: 解析后的数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 查找[DG_INFO_START]到[DG_INFO_END]之间的内容
            dg_section_match = re.search(
                r'\[DG_INFO_START\]\s*\n(.*?)\n\s*\[DG_INFO_END\]',
                content,
                re.DOTALL
            )

            if not dg_section_match:
                logger.warning("未找到Data Guard信息标记")
                return DataGuardInfoData()

            dg_full_content = dg_section_match.group(1).strip()

            # 基于关键字提取各个子章节数据
            data = DataGuardInfoData()
            
            # D1. Data Guard 基本配置检查 && D2. 归档传输目的地配置之间的内容
            data.basic_config_check = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D1. Data Guard 基本配置检查", 
                "D2. 归档传输目的地配置 (Archive Destination Configuration)"
            ))

            # D2. 归档传输目的地配置 && D3. Data Guard 相关参数之间的内容
            data.archive_dest_config = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D2. 归档传输目的地配置 (Archive Destination Configuration)", 
                "D3. Data Guard 相关参数"
            ))

            # D3. Data Guard 相关参数 && D4. Data Guard 状态消息之间的内容
            data.dg_related_params = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D3. Data Guard 相关参数", 
                "D4. Data Guard 状态消息 (最近50条)"
            ))

            # D4. Data Guard 状态消息 && D5. 传输/应用延迟统计之间的内容
            data.dg_status_messages = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D4. Data Guard 状态消息 (最近50条)", 
                "D5. 传输/应用延迟统计"
            ))

            # D5. 传输/应用延迟统计 && D6. 归档日志应用状态之间的内容
            data.transport_apply_lag = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D5. 传输/应用延迟统计", 
                "D6. 归档日志应用状态 (仅Standby数据库)"
            ))

            # D6. 归档日志应用状态 && D7. MRP进程状态之间的内容
            data.archive_log_apply = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_content(
                dg_full_content, 
                "D6. 归档日志应用状态 (仅Standby数据库)", 
                "D7. MRP进程状态 (仅Standby数据库)"
            ))

            # D7. MRP进程状态到结束的内容
            data.mrp_process_status = DataGuardInfoParser._remove_garbled_content(DataGuardInfoParser._extract_section_to_end(
                dg_full_content, 
                "D7. MRP进程状态 (仅Standby数据库)"
            ))

            return data

        except Exception as e:
            logger.error(f"解析Data Guard信息失败: {e}")
            return None

    @staticmethod
    def _extract_section_content(full_content: str, start_keyword: str, end_keyword: str) -> str:
        """
        提取两个关键字之间的内容
        
        Args:
            full_content: 完整内容
            start_keyword: 开始关键字
            end_keyword: 结束关键字
            
        Returns:
            str: 提取的内容，如果未找到则返回空字符串
        """
        try:
            # 找到开始关键字的位置
            start_match = re.search(re.escape(start_keyword), full_content)
            if not start_match:
                logger.warning(f"未找到开始关键字: {start_keyword}")
                return ""

            # 找到结束关键字的位置  
            end_match = re.search(re.escape(end_keyword), full_content[start_match.end():])
            if not end_match:
                logger.warning(f"未找到结束关键字: {end_keyword}")
                return ""

            # 提取两个关键字之间的内容
            start_pos = start_match.end()
            end_pos = start_match.end() + end_match.start()
            
            section_content = full_content[start_pos:end_pos].strip()
            # 清理SQL*Plus控制语句（如 col/column/set/ttitle 等），避免被当作表头
            section_content = DataGuardInfoParser._sanitize_sqlplus_controls(section_content)
            return section_content

        except Exception as e:
            logger.error(f"提取章节内容失败 ({start_keyword} -> {end_keyword}): {e}")
            return ""

    @staticmethod
    def _extract_section_to_end(full_content: str, start_keyword: str) -> str:
        """
        提取从关键字到内容结束的部分
        
        Args:
            full_content: 完整内容
            start_keyword: 开始关键字
            
        Returns:
            str: 提取的内容，如果未找到则返回空字符串
        """
        try:
            # 找到开始关键字的位置
            start_match = re.search(re.escape(start_keyword), full_content)
            if not start_match:
                logger.warning(f"未找到开始关键字: {start_keyword}")
                return ""

            # 提取从关键字到末尾的内容
            section_content = full_content[start_match.end():].strip()
            section_content = DataGuardInfoParser._sanitize_sqlplus_controls(section_content)
            return section_content

        except Exception as e:
            logger.error(f"提取章节内容失败 ({start_keyword} -> 结束): {e}")
            return ""


class AdrciInfoParser:
    """05_adrci_ora.txt文件解析器"""

    @staticmethod
    def parse_adrci_info(file_path: Path) -> Optional[AdrciInfoData]:
        """
        解析05_adrci_ora.txt文件

        Args:
            file_path: 文件路径

        Returns:
            AdrciInfoData: 解析后的数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()

            return AdrciInfoData(adrci_content=content)

        except Exception as e:
            logger.error(f"解析05_adrci_ora.txt失败: {e}")
            return None


class AlertLogParser:
    """03_alert_orcl.log文件解析器 - 新实现：从文件尾部读取10万行，按时间戳分组ORA错误"""

    @staticmethod
    def _read_last_n_lines(file_path: Path, n: int = 100000) -> List[str]:
        """
        从文件尾部高效读取N行
        Args:
            file_path: 文件路径
            n: 读取的行数
        Returns:
            List[str]: 文件最后n行的内容
        """
        try:
            with open(file_path, 'rb') as f:
                # 移动到文件末尾
                f.seek(0, 2)
                file_size = f.tell()

                if file_size == 0:
                    return []

                # 分块向前读取，直到找到足够的行数（按字节处理，避免提前假设编码）
                chunk_size = 8192
                lines: List[bytes] = []
                position = file_size

                while len(lines) < n and position > 0:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    chunk_lines = chunk.split(b'\n')

                    # 如果不是第一次读取，需要与前面的部分行（bytes）合并
                    if lines:
                        chunk_lines[-1] += lines[0]
                        lines = chunk_lines + lines[1:]
                    else:
                        lines = chunk_lines

                # 移除第一个可能不完整的行（除非已经读到文件开头）
                if position > 0 and lines:
                    lines = lines[1:]

                # 截取尾部 n 行并进行多编码解码
                tail = lines[-n:] if len(lines) > n else lines
                return [AlertLogParser._decode_bytes_best_effort(bline) for bline in tail]

        except Exception as e:
            logger.error(f"读取文件最后{n}行失败: {e}")
            return []

    @staticmethod
    def _decode_bytes_best_effort(data: bytes) -> str:
        """尽力将字节解码为字符串，按常见编码顺序尝试，避免出现乱码。

        优先 utf-8/utf-8-sig，随后 gb18030/gbk/cp936，再到 utf-16 族；最后兜底 latin-1。
        """
        for enc in ('utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'cp936', 'utf-16', 'utf-16le', 'utf-16be'):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        try:
            return data.decode('latin-1', errors='ignore')
        except Exception:
            return ''

    @staticmethod
    def _parse_alert_log_reverse(lines: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """
        从后往前解析Alert日志，按时间戳分组ORA错误
        Args:
            lines: 日志文件行列表
        Returns:
            Dict[str, List[Dict[str, str]]]: 按时间戳分组的错误字典
        """
        import re
        
        # Oracle Alert日志时间戳格式模式
        timestamp_patterns = [
            r'[A-Za-z]{3} [A-Za-z]{3} \s*\d{1,2} \d{2}:\d{2}:\d{2} \d{4}',  # Sun Aug 24 08:21:09 2025
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+',  # 2025-08-24T08:21:09.123
            r'[A-Za-z]{3} \s*\d{1,2} \d{2}:\d{2}:\d{2} \d{4}',  # Aug 24 08:21:09 2025
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',  # 2025-08-24 08:21:09
        ]
        
        ora_pattern = r'ORA-\d{1,5}'
        current_timestamp = "未知时间"
        grouped_errors = {}
        current_errors = []
        
        # 从最后一行开始向前遍历
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
                
            # 检查是否为时间戳
            is_timestamp = False
            for pattern in timestamp_patterns:
                if re.search(pattern, line):
                    # 保存当前时间段的错误
                    if current_errors:
                        if current_timestamp not in grouped_errors:
                            grouped_errors[current_timestamp] = []
                        grouped_errors[current_timestamp].extend(current_errors)
                        current_errors = []
                    current_timestamp = line
                    is_timestamp = True
                    break
            
            # 如果不是时间戳，检查是否为ORA错误
            if not is_timestamp and re.search(ora_pattern, line):
                # 提取ORA错误号 - 支持1-5位数字
                ora_match = re.search(r'ORA-(\d{1,5})', line)
                error_code = ora_match.group(0) if ora_match else "ORA-未知"
                
                error_info = {
                    'error_code': error_code,
                    'error_message': line,
                    'timestamp': current_timestamp
                }
                current_errors.append(error_info)
        
        # 处理最后一个时间段的错误
        if current_errors:
            if current_timestamp not in grouped_errors:
                grouped_errors[current_timestamp] = []
            grouped_errors[current_timestamp].extend(current_errors)
        
        return grouped_errors

    @staticmethod
    def _generate_alert_summary(grouped_errors: Dict[str, List[Dict[str, str]]]) -> str:
        """
        生成Alert日志统计报表
        Args:
            grouped_errors: 按时间戳分组的错误字典
        Returns:
            str: 格式化的统计报表
        """
        total_errors = sum(len(errors) for errors in grouped_errors.values())
        
        if total_errors == 0:
            return """【ALERT日志分析结果】
- 分析范围: 最近200,000行日志
- 总错误数: 0 个ORA错误
- 状态: 未发现ORA错误，系统运行正常"""
        
        summary = f"""【ALERT日志分析结果】
- 分析范围: 最近200,000行日志
- 总错误数: {total_errors} 个ORA错误
- 时间段数: {len(grouped_errors)} 个"""
        
        return summary

    @staticmethod
    def parse_alert_log(file_path: Path, health_check_path: Optional[Path] = None) -> Optional[AlertLogData]:
        """
        新的Alert日志解析方法：从文件尾部读取10万行，按时间戳分组ORA错误
        
        Args:
            file_path: Alert日志文件路径
            health_check_path: 04_health_check.txt文件路径（可选，用于获取ALERT_LOG路径）
        
        Returns:
            AlertLogData: 解析后的数据，解析失败返回None
        """
        try:
            # 1. 从文件尾部读取5万行（优化性能，聚焦近期问题）
            lines = AlertLogParser._read_last_n_lines(file_path, 200000)
            
            if not lines:
                return AlertLogData(
                    alert_summary="【ALERT日志分析结果】\n- 文件为空或无法读取",
                    alert_log_path="-",
                    grouped_errors={}
                )
            
            # 2. 从后往前解析，按时间分组ORA错误
            grouped_errors = AlertLogParser._parse_alert_log_reverse(lines)
            
            # 3. 生成统计报表
            alert_summary = AlertLogParser._generate_alert_summary(grouped_errors)
            
            # 4. 提取ALERT_LOG路径
            alert_log_path = "-"
            if health_check_path and health_check_path.exists():
                alert_log_path = AlertLogParser._extract_alert_log_path(health_check_path)
            
            return AlertLogData(
                alert_summary=alert_summary,
                alert_log_path=alert_log_path,
                grouped_errors=grouped_errors
            )
            
        except Exception as e:
            logger.error(f"解析Alert日志失败: {e}")
            return AlertLogData(
                alert_summary=f"【ALERT日志分析结果】\n- ⚠️ 分析失败: {e}",
                alert_log_path="-",
                grouped_errors={}
            )

    @staticmethod
    def _extract_alert_log_path(health_check_path: Path) -> str:
        """从04_health_check.txt文件中提取ALERT_LOG路径"""
        try:
            with open(health_check_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # 查找C1. 重要日志文件路径部分
            log_path_section = re.search(
                r'C1\. 重要日志文件路径.*?(?=C2\.|==================|$)',
                content,
                re.DOTALL
            )
            if not log_path_section:
                return "-"
            log_content = log_path_section.group(0)
            # 提取ALERT_LOG对应的路径
            alert_log_match = re.search(r'ALERT_LOG\s+(\S+)', log_content)
            if alert_log_match:
                return alert_log_match.group(1)
            return "-"
        except Exception as e:
            logger.error(f"提取ALERT_LOG路径失败: {e}")
            return "-"


class ResourceConfigParser:
    """数据库资源相关配置解析器"""

    @staticmethod
    def parse_resource_config(hardware_file_path: Path, health_check_file_path: Path, instance_names: str = "", rman_file_path: Optional[Path] = None) -> Optional[ResourceConfigData]:
        """
        解析数据库资源相关配置信息
        
        Args:
            hardware_file_path: 02_hardware_info.json文件路径
            health_check_file_path: 04_health_check.txt文件路径
            instance_names: 实例名称字符串
            rman_file_path: RMAN信息文件路径（可选）
            
        Returns:
            ResourceConfigData: 解析后的资源配置数据
        """
        try:
            # 解析硬件信息
            hardware_data = HardwareInfoParser.parse_hardware_info(hardware_file_path)
            if not hardware_data:
                logger.error("无法解析硬件信息文件")
                return None
                
            # 直接从04_health_check.txt文件中解析所需的数据库参数
            with open(health_check_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                health_check_content = f.read()
            
            # 提取数据库CPU和进程相关参数
            db_cpu_count = ResourceConfigParser._extract_param_value(health_check_content, "cpu_count")
            db_parallel_max_servers = ResourceConfigParser._extract_param_value(health_check_content, "parallel_max_servers")
            db_parallel_min_servers = ResourceConfigParser._extract_param_value(health_check_content, "parallel_min_servers")
            db_processes = ResourceConfigParser._extract_param_value(health_check_content, "processes")
            db_sessions = ResourceConfigParser._extract_param_value(health_check_content, "sessions")
            db_transactions = ResourceConfigParser._extract_param_value(health_check_content, "transactions")
            db_sga_max_size = ResourceConfigParser._extract_param_value(health_check_content, "sga_max_size")
            db_pga_aggregate_target = ResourceConfigParser._extract_param_value(health_check_content, "pga_aggregate_target")
            db_log_buffer = ResourceConfigParser._extract_param_value(health_check_content, "log_buffer")
            db_open_cursors = ResourceConfigParser._extract_param_value(health_check_content, "open_cursors")
            db_session_cached_cursors = ResourceConfigParser._extract_param_value(health_check_content, "session_cached_cursors")
            
            # 单位转换函数
            def bytes_to_gb(bytes_str: str) -> str:
                """将字节转换为GB"""
                try:
                    if not bytes_str or bytes_str == "-":
                        return "-"
                    bytes_val = int(bytes_str)
                    gb_val = bytes_val / (1024**3)
                    return f"{gb_val:.2f}"
                except:
                    return "-"
                    
            def bytes_to_mb(bytes_str: str) -> str:
                """将字节转换为MB"""
                try:
                    if not bytes_str or bytes_str == "-":
                        return "-"
                    bytes_val = int(bytes_str)
                    mb_val = bytes_val / (1024**2)
                    return f"{mb_val:.2f}"
                except:
                    return "-"
            
            return ResourceConfigData(
                # 服务器资源
                server_logical_cores=str(hardware_data.cpu_logical_cores),
                server_mem_size_gb=str(hardware_data.memory_total_gb),
                
                # 数据库CPU配置
                db_cpu_count=db_cpu_count,
                db_parallel_max_servers=db_parallel_max_servers,
                db_parallel_min_servers=db_parallel_min_servers,
                db_processes=db_processes,
                db_sessions=db_sessions,
                db_transactions=db_transactions,
                
                # 数据库内存配置
                db_sga_size_gb=bytes_to_gb(db_sga_max_size),
                db_pga_size_gb=bytes_to_gb(db_pga_aggregate_target),
                db_log_buffer_mb=bytes_to_mb(db_log_buffer),
                db_open_cursors=db_open_cursors,
                db_session_cached_cursors=db_session_cached_cursors
            )
            
        except Exception as e:
            logger.error(f"解析资源配置信息失败: {e}")
            return None

    @staticmethod
    def _extract_param_value(content: str, param_name: str) -> str:
        """从健康检查文件内容中提取指定参数的值"""
        try:
            # 查找参数名后面跟着数值的模式
            pattern = rf'{param_name}\s+(\d+)'
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
            return "-"
        except Exception as e:
            logger.error(f"提取参数{param_name}失败: {e}")
            return "-"


class ControlFileLogParser:
    """控制文件和在线日志解析器"""

    @staticmethod
    def parse_control_file_log(file_path: Path) -> Optional[ControlFileLogData]:
        """
        解析04_health_check.txt文件中的控制文件和在线日志信息
        
        Args:
            file_path: 04_health_check.txt文件路径
            
        Returns:
            ControlFileLogData: 解析后的控制文件和日志数据
        """
        try:
            content = ControlFileLogParser._read_text_best_effort(file_path)
            
            # 提取并转换控制文件信息为表格
            control_file_info = ControlFileLogParser._parse_control_file_table(content)
            
            # 提取并转换在线日志信息为表格
            online_log_info = ControlFileLogParser._parse_online_log_table(content)
            
            return ControlFileLogData(
                control_file_info=control_file_info or "未找到控制文件信息",
                online_log_info=online_log_info or "未找到在线日志信息"
            )
            
        except Exception as e:
            logger.error(f"解析控制文件和日志信息失败: {e}")
            return None
    
    @staticmethod
    def _parse_control_file_table(content: str) -> str:
        """解析控制文件路径为表格格式"""
        try:
            # 提取控制文件路径段内容
            section_content = ControlFileLogParser._extract_section(content, "C2. 控制文件路径", "C3. 归档日志路径")
            if not section_content:
                return "未找到控制文件信息"
            
            lines = section_content.split('\n')
            control_files = []
            
            # 提取控制文件路径
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 跳过表头和分隔线
                if line.startswith('CONTROL_FILE_PATH') or re.match(r'^-+$', line):
                    continue
                # 兼容不同输出：
                # - 传统文件: /path/to/control01.ctl
                # - ASM: +DATA/dbname/controlfile/current.260.1130798727 （无 .ctl 后缀）
                # - Windows: C:\...\control01.ctl
                if (
                    line.endswith('.ctl') or
                    line.startswith('+') or
                    '/' in line or '\\' in line
                ):
                    control_files.append(line)
            
            if not control_files:
                return "未找到控制文件路径"
            
            # 构建表格
            table_lines = ["| 序号 | 控制文件路径 |"]
            table_lines.append("| :--- | :--- |")
            
            for i, file_path in enumerate(control_files, 1):
                table_lines.append(f"| {i} | {file_path} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析控制文件表格失败: {e}")
            return "解析控制文件信息失败"

    @staticmethod
    def _read_text_best_effort(file_path: Path) -> str:
        # 读取原始字节，按顺序尝试多种编码；优先UTF-8(ignore)并校验关键标记，
        # 若未命中关键标记再尝试其它编码；最终兜底回退到UTF-8(ignore)。
        try:
            raw = file_path.read_bytes()
        except Exception:
            return ''

        def decode_with(enc: str) -> str:
            try:
                return raw.decode(enc, errors='ignore')
            except Exception:
                return ''

        def has_key_markers(text: str) -> bool:
            # 关键标记：日志路径范围与控制文件/在线日志段标题
            markers = [
                '[DB_LOG_PATHS_START]',
                'C2.',           # C2. 控制文件路径
                '8.',            # 8.日志文件信息
                '控制文件路径',
                '日志文件信息',
                '归档统计',
            ]
            return any(m in text for m in markers)

        # 1) 优先UTF-8(ignore)并校验标记
        text_utf8 = decode_with('utf-8')
        if has_key_markers(text_utf8):
            return text_utf8

        # 2) 尝试可能的UTF-16变体（某些环境下会导出为UTF-16）
        for enc in ['utf-16', 'utf-16le', 'utf-16be']:
            t = decode_with(enc)
            if has_key_markers(t):
                return t

        # 3) 再尝试中文本地编码（仅当包含关键标记才接受）
        for enc in ['gb18030', 'gbk', 'cp936']:
            t = decode_with(enc)
            if has_key_markers(t):
                return t

        # 4) 兜底：返回UTF-8(ignore)，尽量保持可读
        return text_utf8 or decode_with('latin-1') or ''
    
    @staticmethod
    def _parse_online_log_table(content: str) -> str:
        """解析在线日志信息为表格格式"""
        try:
            # 提取在线日志段内容
            section_content = ControlFileLogParser._extract_section(content, "8.日志文件信息", "归档统计")
            if not section_content:
                return "未找到在线日志信息"
            
            lines = section_content.split('\n')
            log_groups = []
            log_members = []
            
            # 解析日志组信息（第一个表格）
            in_group_section = False
            group_header_found = False
            
            for line in lines:
                line = line.strip()
                if 'GROUP#' in line and 'THREAD#' in line and 'SEQUENCE#' in line:
                    in_group_section = True
                    group_header_found = True
                    continue
                
                if in_group_section and line.startswith('--'):
                    continue
                
                if in_group_section and group_header_found and line and not line.startswith('total'):
                    # 解析日志组行
                    parts = line.split()
                    if len(parts) >= 8:
                        try:
                            group_id = parts[0]
                            thread_id = parts[1]
                            sequence = parts[2]
                            mbytes = parts[3]
                            members = parts[4]
                            arc = parts[5]
                            status = parts[6]
                            first_change = parts[7]
                            first_time = parts[8] if len(parts) > 8 else ""
                            
                            log_groups.append({
                                'group_id': group_id,
                                'thread_id': thread_id,
                                'sequence': sequence,
                                'mbytes': mbytes,
                                'members': members,
                                'arc': arc,
                                'status': status,
                                'first_change': first_change,
                                'first_time': first_time
                            })
                        except:
                            continue
                
                # 检查是否到达成员信息部分
                if 'GROUP#' in line and 'STATUS' in line and 'TYPE' in line and 'MEMBER' in line:
                    in_group_section = False
                    break
            
            # 解析日志成员信息（第二个表格）
            in_member_section = False
            member_header_found = False
            
            for line in lines:
                line = line.strip()
                if 'GROUP#' in line and 'STATUS' in line and 'TYPE' in line and 'MEMBER' in line:
                    in_member_section = True
                    member_header_found = True
                    continue
                
                if in_member_section and line.startswith('--'):
                    continue
                
                if in_member_section and member_header_found and line:
                    # 解析日志成员行
                    # 原始数据: "     3          ONLINE  /u01/app/oradata/HNHKCZP/redo03.log                NO"
                    # 表头: GROUP# STATUS   TYPE    MEMBER                                             IS_
                    # split()结果: ['3', 'ONLINE', '/u01/app/oradata/HNHKCZP/redo03.log', 'NO']
                    # 实际上STATUS列为空，所以split()跳过了它，导致字段顺序偏移
                    
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            group_id = parts[0]  # 组号
                            
                            # 由于STATUS列为空（被split跳过），实际结构是：
                            # parts[0]: 组号
                            # parts[1]: TYPE (ONLINE)
                            # parts[2]: MEMBER (文件路径)
                            # parts[3]: IS_ (NO)
                            
                            status = "-"  # STATUS列为空
                            type_val = parts[1]  # TYPE是ONLINE
                            member_path = parts[2]  # MEMBER是文件路径
                            
                            log_members.append({
                                'group_id': group_id,
                                'status': status,
                                'type': type_val,
                                'member_path': member_path
                            })
                        except:
                            continue
            
            # 构建表格输出
            table_content = []
            
            # 日志组信息表格
            if log_groups:
                table_content.append("**日志组信息：**")
                table_content.append("")
                table_content.append("| 组号 | 线程# | 序列# | 大小(MB) | 成员数 | 归档 | 状态 | 首次变更# | 首次时间 |")
                table_content.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                
                for group in log_groups:
                    table_content.append(f"| {group['group_id']} | {group['thread_id']} | {group['sequence']} | {group['mbytes']} | {group['members']} | {group['arc']} | {group['status']} | {group['first_change']} | {group['first_time']} |")
            
            # 日志成员信息表格
            if log_members:
                table_content.append("")
                table_content.append("**日志成员信息：**")
                table_content.append("")
                table_content.append("| 组号 | 状态 | 类型 | 成员路径 |")
                table_content.append("| :--- | :--- | :--- | :--- |")
                
                for member in log_members:
                    table_content.append(f"| {member['group_id']} | {member['status']} | {member['type']} | {member['member_path']} |")
            
            return '\n'.join(table_content) if table_content else "未找到在线日志详细信息"
            
        except Exception as e:
            logger.error(f"解析在线日志表格失败: {e}")
            return "解析在线日志信息失败"
    
    @staticmethod
    def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
        """提取两个标记之间的内容"""
        try:
            start_match = re.search(rf"{re.escape(start_marker)}", content)
            if not start_match:
                return ""
            
            end_match = re.search(rf"{re.escape(end_marker)}", content[start_match.end():])
            if not end_match:
                # 如果没有结束标记，取到文件末尾
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            # 清理内容
            section_content = section_content.strip()
            # 移除多余的空白行
            section_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', section_content)
            # 优化过长的分隔横线，限制最大长度为80个字符
            section_content = ControlFileLogParser._format_separator_lines(section_content)
            
            return section_content
            
        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")
            return ""

    @staticmethod
    def _format_separator_lines(content: str) -> str:
        """优化过长的分隔横线格式"""
        try:
            lines = content.split('\n')
            formatted_lines = []
            
            for line in lines:
                # 如果是纯分隔线（只包含'-'和空格），且长度过长，则缩短
                if re.match(r'^[-\s]+$', line) and len(line.strip()) > 80:
                    # 缩短为合适长度（50个字符）
                    formatted_lines.append('-' * 50)
                else:
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
            
        except Exception as e:
            logger.error(f"格式化分隔线失败: {e}")
            return content


class TablespaceFileParser:
    """表空间和数据文件解析器"""

    @staticmethod
    def parse_tablespace_file(file_path: Path) -> Optional[TablespaceFileData]:
        """
        解析04_health_check.txt文件中的表空间和数据文件信息
        
        Args:
            file_path: 04_health_check.txt文件路径
            
        Returns:
            TablespaceFileData: 解析后的表空间文件数据
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 提取并转换数据文件列表信息为表格
            datafile_list = TablespaceFileParser._parse_datafile_list_table(content)
            
            # 提取并转换表空间基本信息为表格
            tablespace_basic_info = TablespaceFileParser._parse_tablespace_basic_info_table(content)
            
            # 提取并转换表空间使用情况为表格（过滤USED_RATE(%) > 85的数据）
            high_usage_tablespaces = TablespaceFileParser._parse_high_usage_tablespaces_table(content)
            
            # 提取并转换未开启自动扩展的表空间文件为表格（AUT = NO）
            no_autoextend_files = TablespaceFileParser._parse_no_autoextend_files_table(content)
            
            return TablespaceFileData(
                datafile_list=datafile_list or "未找到数据文件列表信息",
                tablespace_basic_info=tablespace_basic_info or "未找到表空间基本信息",
                high_usage_tablespaces=high_usage_tablespaces or "无使用率超过85%的表空间",
                no_autoextend_files=no_autoextend_files or "无未开启自动扩展的文件"
            )
            
        except Exception as e:
            logger.error(f"解析表空间和数据文件信息失败: {e}")
            return None
    
    @staticmethod
    def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
        """提取两个标记之间的内容"""
        try:
            start_match = re.search(rf"{re.escape(start_marker)}", content)
            if not start_match:
                return ""
            
            end_match = re.search(rf"{re.escape(end_marker)}", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            section_content = section_content.strip()
            section_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', section_content)
            # 优化过长的分隔横线，限制最大长度为80个字符
            section_content = TablespaceFileParser._format_separator_lines(section_content)
            
            return section_content
            
        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")
            return ""

    @staticmethod
    def _format_separator_lines(content: str) -> str:
        """优化过长的分隔横线格式"""
        try:
            lines = content.split('\n')
            formatted_lines = []
            
            for line in lines:
                # 如果是纯分隔线（只包含'-'和空格），且长度过长，则缩短
                if re.match(r'^[-\s]+$', line) and len(line.strip()) > 80:
                    # 缩短为合适长度（50个字符）
                    formatted_lines.append('-' * 50)
                else:
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
            
        except Exception as e:
            logger.error(f"格式化分隔线失败: {e}")
            return content
    
    @staticmethod
    def _parse_datafile_list_table(content: str) -> str:
        """解析数据文件列表为表格格式"""
        try:
            # 提取数据文件列表段内容
            section_content = TablespaceFileParser._extract_section(content, "数据文件列表", "8.日志文件信息")
            if not section_content:
                return "未找到数据文件列表信息"
            
            lines = section_content.split('\n')
            datafiles = []
            
            # 提取数据文件路径
            for line in lines:
                line = line.strip()
                if line and not line.startswith('FILE_NAME') and not line.startswith('-'):
                    if line.endswith('.dbf') or line.endswith('.DBF'):  # 确保是数据文件路径
                        datafiles.append(line)
            
            if not datafiles:
                return "未找到数据文件路径"
            
            # 构建表格
            table_lines = ["| 序号 | 数据文件路径 |"]
            table_lines.append("| :--- | :--- |")
            
            for i, file_path in enumerate(datafiles, 1):
                table_lines.append(f"| {i} | {file_path} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析数据文件列表表格失败: {e}")
            return "解析数据文件列表信息失败"
    
    @staticmethod
    def _parse_tablespace_basic_info_table(content: str) -> str:
        """解析表空间基本信息为表格格式"""
        try:
            # 提取表空间基本信息段内容
            section_content = TablespaceFileParser._extract_section(content, "表空间基本信息", "表空间使用情况")
            if not section_content:
                return "未找到表空间基本信息"
            
            lines = section_content.split('\n')
            tablespaces = []
            
            # 解析表空间信息
            header_found = False
            
            for line in lines:
                line = line.strip()
                if 'NAME' in line and 'INIT' in line and 'STATUS' in line:
                    header_found = True
                    continue
                
                if line.startswith('--'):
                    continue
                
                if header_found and line and not 'rows selected' in line:
                    # 解析表空间行: NAME INIT NEXT MAX CONTENTS STATUS EM SM
                    parts = line.split()
                    if len(parts) >= 7:
                        try:
                            name = parts[0]
                            init_val = parts[1]
                            next_val = parts[2] if parts[2] != '2147483645' else '自动'
                            max_val = parts[3] if parts[3] != '2147483645' else '无限制'
                            contents = parts[4]
                            status = parts[5]
                            em = parts[6] if len(parts) > 6 else ""
                            sm = parts[7] if len(parts) > 7 else ""
                            
                            tablespaces.append({
                                'name': name,
                                'init': init_val,
                                'next': next_val,
                                'max': max_val,
                                'contents': contents,
                                'status': status,
                                'em': em,
                                'sm': sm
                            })
                        except:
                            continue
            
            if not tablespaces:
                return "未找到表空间基本信息数据"
            
            # 构建表格（删除空间管理列）
            table_lines = ["| 表空间名 | 初始大小 | 扩展大小 | 最大大小 | 内容类型 | 状态 | 扩展管理 |"]
            table_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            
            for ts in tablespaces:
                table_lines.append(f"| {ts['name']} | {ts['init']} | {ts['next']} | {ts['max']} | {ts['contents']} | {ts['status']} | {ts['em']} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析表空间基本信息表格失败: {e}")
            return "解析表空间基本信息失败"
    
    @staticmethod
    def _parse_high_usage_tablespaces_table(content: str) -> str:
        """解析使用率超过85%的表空间为表格格式"""
        try:
            # 先获取整个表空间使用情况段
            usage_section = TablespaceFileParser._extract_section(content, "表空间使用情况", "数据文件大小与自动扩展")
            if not usage_section:
                return ""
            
            lines = usage_section.split('\n')
            high_usage_tablespaces = []
            
            # 解析表空间使用情况
            header_found = False
            
            for line in lines:
                line = line.strip()
                if 'TABLESPACE' in line and 'USED_RATE' in line:
                    header_found = True
                    continue
                
                if line.startswith('--'):
                    continue
                
                if header_found and line and 'rows selected' not in line:
                    # 解析使用率行: TABLESPACE SUM_SPACE(M) SUM_BLOCKS USED_SPACE(M) USED_RATE(%) FREE_SPACE(M)
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            tablespace = parts[0]
                            sum_space = parts[1]
                            sum_blocks = parts[2]
                            used_space = parts[3]
                            used_rate_str = parts[4]
                            free_space = parts[5]
                            
                            # 检查使用率是否超过85%
                            used_rate = float(used_rate_str)
                            if used_rate > 85:
                                high_usage_tablespaces.append({
                                    'tablespace': tablespace,
                                    'sum_space': sum_space,
                                    'sum_blocks': sum_blocks,
                                    'used_space': used_space,
                                    'used_rate': used_rate_str,
                                    'free_space': free_space
                                })
                        except (ValueError, IndexError):
                            continue
            
            if not high_usage_tablespaces:
                return "无使用率超过85%的表空间"
            
            # 构建表格
            table_lines = ["| 表空间名 | 总空间(M) | 总块数 | 已用空间(M) | 使用率(%) | 剩余空间(M) |"]
            table_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            
            for ts in high_usage_tablespaces:
                table_lines.append(f"| {ts['tablespace']} | {ts['sum_space']} | {ts['sum_blocks']} | {ts['used_space']} | {ts['used_rate']} | {ts['free_space']} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析高使用率表空间表格失败: {e}")
            return ""
    
    @staticmethod
    def _parse_no_autoextend_files_table(content: str) -> str:
        """解析未开启自动扩展的表空间文件为表格格式（AUT = NO）"""
        try:
            # 获取数据文件大小与自动扩展段
            autoextend_section = TablespaceFileParser._extract_section(content, "数据文件大小与自动扩展", "数据文件列表")
            if not autoextend_section:
                return ""
            
            lines = autoextend_section.split('\n')
            no_autoextend_files = []
            
            # 解析数据文件自动扩展信息
            header_found = False
            
            for line in lines:
                line = line.strip()
                if 'FILE_ID' in line and 'AUT' in line:
                    header_found = True
                    continue
                
                if line.startswith('--'):
                    continue
                
                if header_found and line and 'total' not in line.lower() and 'rows selected' not in line:
                    # 解析文件行: FILE_ID TABLESPACE_NAME AUT MBYTES MAXGBYTES
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            file_id = parts[0]
                            tablespace_name = parts[1]
                            aut = parts[2]
                            mbytes = parts[3]
                            maxgbytes = parts[4]
                            
                            # 只收集AUT = NO的文件
                            if aut == "NO":
                                no_autoextend_files.append({
                                    'file_id': file_id,
                                    'tablespace_name': tablespace_name,
                                    'aut': aut,
                                    'mbytes': mbytes,
                                    'maxgbytes': maxgbytes
                                })
                        except:
                            continue
            
            if not no_autoextend_files:
                return "无未开启自动扩展的文件"
            
            # 构建表格
            table_lines = ["| 文件ID | 表空间名 | 自动扩展 | 大小(MB) | 最大大小(GB) |"]
            table_lines.append("| :--- | :--- | :--- | :--- | :--- |")
            
            for file_info in no_autoextend_files:
                table_lines.append(f"| {file_info['file_id']} | {file_info['tablespace_name']} | {file_info['aut']} | {file_info['mbytes']} | {file_info['maxgbytes']} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析未开启自动扩展文件表格失败: {e}")
            return ""


class ArchiveStatParser:
    """归档统计解析器"""

    @staticmethod
    def parse_archive_stat(file_path: Path) -> Optional[ArchiveStatData]:
        """
        解析04_health_check.txt文件中的归档统计信息
        
        Args:
            file_path: 04_health_check.txt文件路径
            
        Returns:
            ArchiveStatData: 解析后的归档统计数据
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 解析归档统计表格
            archive_statistics = ArchiveStatParser._parse_archive_table(content)
            
            return ArchiveStatData(
                archive_statistics=archive_statistics or "未找到归档统计信息"
            )
            
        except Exception as e:
            logger.error(f"解析归档统计信息失败: {e}")
            return None
    
    @staticmethod
    def _parse_archive_table(content: str) -> str:
        """解析归档统计信息为表格格式"""
        try:
            # 提取归档统计信息（归档统计 和 9.命中率统计 中间这段内容）
            start_match = re.search(r"归档统计", content)
            if not start_match:
                return "未找到归档统计信息"
            
            end_match = re.search(r"9\.命中率统计", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            # 解析表格数据
            lines = section_content.strip().split('\n')
            table_lines = ["| 归档日期 | 每日归档数量 | 归档大小(GB) |"]
            table_lines.append("| :--- | :--- | :--- |")
            
            data_found = False
            for line in lines:
                line = line.strip()
                
                # 跳过空行、标题行和分隔行
                if not line:
                    continue
                if line.startswith('ARCHIVEDA') or line.startswith('ARCHIVEDATE'):
                    continue
                if line.startswith('---') or line.startswith('='):
                    continue
                if 'rows selected' in line.lower():
                    continue
                    
                # 解析数据行 - 现在统一为YYYY-MM-DD格式
                parts = line.split()
                if len(parts) >= 3:
                    archive_date = parts[0]
                    archives_per_day = parts[1]
                    size_gb = parts[2]
                    
                    # 验证数据有效性
                    try:
                        int(archives_per_day)
                        float(size_gb.replace(',', ''))
                        table_lines.append(f"| {archive_date} | {archives_per_day} | {size_gb} |")
                        data_found = True
                    except ValueError:
                        # 跳过无法解析为数字的行
                        continue
            
            if not data_found:
                return "未找到有效的归档统计数据"
                
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析归档统计表格失败: {e}")
            return "解析归档统计信息失败"
    
    @staticmethod
    def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
        """提取两个标记之间的内容"""
        try:
            start_match = re.search(rf"{re.escape(start_marker)}", content)
            if not start_match:
                return ""
            
            end_match = re.search(rf"{re.escape(end_marker)}", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            section_content = section_content.strip()
            section_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', section_content)
            
            return section_content
            
        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")
            return ""


class AsmDiskParser:
    """ASM磁盘详细信息解析器"""

    @staticmethod
    def parse_asm_disk(file_path: Path) -> Optional[AsmDiskData]:
        """
        解析04_health_check.txt文件中的ASM磁盘详细信息
        
        Args:
            file_path: 04_health_check.txt文件路径
            
        Returns:
            AsmDiskData: 解析后的ASM磁盘数据
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 解析ASM磁盘信息为表格格式
            asm_disk_overview_table = AsmDiskParser._parse_asm_overview_table(content)
            asm_disk_detail_table = AsmDiskParser._parse_asm_detail_table(content)
            
            # 组合ASM磁盘信息
            combined_info = ""
            if asm_disk_overview_table:
                combined_info += "**ASM磁盘组概览**\n\n" + asm_disk_overview_table + "\n\n"
            if asm_disk_detail_table:
                combined_info += "**ASM磁盘详细信息**\n\n" + asm_disk_detail_table
            
            return AsmDiskData(
                asm_disk_detail=combined_info or "未找到ASM磁盘详细信息"
            )
            
        except Exception as e:
            logger.error(f"解析ASM磁盘信息失败: {e}")
            return None
    
    @staticmethod
    def _parse_asm_overview_table(content: str) -> str:
        """解析16.1 ASM磁盘组概览为表格格式"""
        try:
            # 提取16.1 ASM磁盘组概览内容
            start_match = re.search(r"16\.1 ASM磁盘组概览", content)
            if not start_match:
                return "未找到ASM磁盘组概览信息"
            
            end_match = re.search(r"16\.2 ASM磁盘详细信息", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            # 解析表格数据
            lines = section_content.strip().split('\n')
            table_lines = ["| 磁盘组名称 | 总容量(GB) | 剩余空间(GB) | 使用率 |"]
            table_lines.append("| :--- | :--- | :--- | :--- |")
            
            for line in lines:
                line = line.strip()
                # 跳过标题行和分隔行
                if not line or line.startswith('DISKGROUP') or line.startswith('---'):
                    continue
                
                # 解析数据行
                parts = line.split()
                if len(parts) >= 4:
                    diskgroup_name = parts[0]
                    total_gb = parts[1]
                    free_gb = parts[2]
                    used_percent = parts[3]
                    table_lines.append(f"| {diskgroup_name} | {total_gb} | {free_gb} | {used_percent} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析ASM磁盘组概览表格失败: {e}")
            return "解析ASM磁盘组概览信息失败"
    
    @staticmethod
    def _parse_asm_detail_table(content: str) -> str:
        """解析16.2 ASM磁盘详细信息为表格格式"""
        try:
            # 提取16.2 ASM磁盘详细信息内容
            start_match = re.search(r"16\.2 ASM磁盘详细信息", content)
            if not start_match:
                return "未找到ASM磁盘详细信息"
            
            end_match = re.search(r"16\.3 ASM磁盘基本信息", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            # 解析表格数据
            lines = section_content.strip().split('\n')
            
            # 创建简化的表格头
            table_lines = ["| 组号 | 磁盘组 | 磁盘名称 | 磁盘路径 | 状态 | 磁盘容量(GB) | 剩余空间(GB) |"]
            table_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            
            # 解析数据行
            for line in lines:
                line = line.strip()
                # 跳过标题行、分隔行和空行
                if (not line or line.startswith('REQUIRED') or line.startswith('GROUP') or 
                    line.startswith('---') or line.startswith('NO DISKGROUP')):
                    continue
                
                # 解析数据行 - 使用固定宽度格式解析
                parts = line.split()
                if len(parts) >= 10:
                    group_no = parts[0]
                    diskgroup = parts[1]
                    disk_name = parts[2]
                    disk_path = parts[3]
                    state = parts[7]
                    disk_total = parts[8]
                    disk_free = parts[9]
                    table_lines.append(f"| {group_no} | {diskgroup} | {disk_name} | {disk_path} | {state} | {disk_total} | {disk_free} |")
            
            return '\n'.join(table_lines)
            
        except Exception as e:
            logger.error(f"解析ASM磁盘详细信息表格失败: {e}")
            return "解析ASM磁盘详细信息失败"
    
    @staticmethod
    def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
        """提取两个标记之间的内容"""
        try:
            start_match = re.search(rf"{re.escape(start_marker)}", content)
            if not start_match:
                return ""
            
            end_match = re.search(rf"{re.escape(end_marker)}", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            section_content = section_content.strip()
            section_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', section_content)
            
            return section_content
            
        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")
            return ""


class PlsqlVirusParser:
    """PL/SQLDeveloper破解版勒索病毒检查解析器"""

    @staticmethod
    def parse_plsql_virus(file_path: Path) -> Optional[PlsqlVirusData]:
        """
        解析04_health_check.txt文件中的PL/SQLDeveloper破解版勒索病毒检查信息
        
        Args:
            file_path: 04_health_check.txt文件路径
            
        Returns:
            PlsqlVirusData: 解析后的病毒检查数据
        """
        try:
            content = PlsqlVirusParser._read_text_best_effort(file_path)
            
            # 提取PL/SQLDeveloper破解版勒索病毒检查信息（15.PL/SQLDeveloper破解版勒索病毒检查 和 16.1 ASM磁盘组概览 中间这段内容）
            virus_check_info = PlsqlVirusParser._extract_section(content, "15.PL/SQLDeveloper破解版勒索病毒检查", "16.1 ASM磁盘组概览")
            virus_check_info = PlsqlVirusParser._remove_garbled_content(virus_check_info)
            
            return PlsqlVirusData(
                virus_check_info=virus_check_info or "未找到PL/SQLDeveloper病毒检查信息"
            )
            
        except Exception as e:
            logger.error(f"解析PL/SQLDeveloper病毒检查信息失败: {e}")
            return None
    
    @staticmethod
    def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
        """提取两个标记之间的内容"""
        try:
            start_match = re.search(rf"{re.escape(start_marker)}", content)
            if not start_match:
                return ""
            
            end_match = re.search(rf"{re.escape(end_marker)}", content[start_match.end():])
            if not end_match:
                section_content = content[start_match.end():]
            else:
                section_content = content[start_match.end():start_match.end() + end_match.start()]
            
            section_content = section_content.strip()
            section_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', section_content)
            
            return section_content
            
        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")
            return ""

    @staticmethod
    def _read_text_best_effort(file_path: Path) -> str:
        encodings = ['utf-8','utf-8-sig','gb18030','gbk','cp936','utf-16','utf-16le','utf-16be']
        for enc in encodings:
            try:
                with open(file_path,'r',encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        try:
            return file_path.read_bytes().decode('latin-1','ignore')
        except Exception:
            return ''

    @staticmethod
    def _remove_garbled_content(section_content: str) -> str:
        if not section_content:
            return section_content
        tokens = ['�','��','δѡ','С�']
        lines = section_content.splitlines()
        kept = [ln for ln in lines if not any(tok in ln for tok in tokens)]
        result = '\n'.join(kept).strip()
        # 如果几乎全是乱码（有效行过少），返回空字符串走占位
        non_empty = [l for l in result.splitlines() if l.strip()]
        if len(non_empty) == 0:
            return ''
        return result


class InspectionSummaryParser:
    """00_inspection_summary.txt文件解析器"""

    @staticmethod
    def parse_inspection_summary(file_path: Path) -> Optional[InspectionSummaryData]:
        """
        解析00_inspection_summary.txt文件

        Args:
            file_path: 文件路径

        Returns:
            InspectionSummaryData: 解析后的数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取主机名
            hostname_match = re.search(r'主机名:\s*(\S+)', content)
            hostname = hostname_match.group(1) if hostname_match else "unknown"

            # 提取SID
            sid_match = re.search(r'SID:\s*(\S+)', content)
            sid = sid_match.group(1) if sid_match else "unknown"

            # 提取数据库模式
            db_model_match = re.search(r'数据库模式:\s*(\S+)', content)
            db_model = db_model_match.group(1) if db_model_match else "unknown"

            # 提取巡检时间
            time_match = re.search(r'巡检时间:\s*(.+)', content)
            inspection_time = time_match.group(1).strip() if time_match else "未知时间"

            # 提取文件状态部分（从"文件生成状态报告"到"状态说明"）
            status_section_match = re.search(
                r'文件生成状态报告:\s*\n=+\s*\n(.*?)\n状态说明:',
                content,
                re.DOTALL
            )

            if status_section_match:
                file_status_content = status_section_match.group(1).strip()
            else:
                # 如果没有找到标准格式，尝试提取整个文件状态区域
                file_status_content = "文件状态信息提取失败"

            return InspectionSummaryData(
                hostname=hostname,
                sid=sid,
                db_model=db_model,
                inspection_time=inspection_time,
                file_status_content=file_status_content
            )

        except Exception as e:
            logger.error(f"解析00_inspection_summary.txt失败: {e}")
            return None


class SarReportParser:
    """10_sar_report.txt文件解析器"""

    @staticmethod
    def parse_sar_report(file_path: Path) -> Optional[OsPerformanceData]:
        """
        解析10_sar_report.txt文件，提取操作系统性能数据
        
        Args:
            file_path: SAR报告文件路径
            
        Returns:
            OsPerformanceData: 解析后的操作系统性能数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取主机名
            hostname_match = re.search(r'Linux.*?\((.*?)\)', content)
            hostname = hostname_match.group(1) if hostname_match else "未知主机"

            # 提取CPU使用率数据（通过关键字定位）
            cpu_data = SarReportParser._extract_section_data(
                content, 
                "== CPU 使用率（昨天 08:00~12:00）==", 
                "== 内存使用率（昨天 08:00~12:00）=="
            )

            # 提取内存使用率数据
            memory_data = SarReportParser._extract_section_data(
                content,
                "== 内存使用率（昨天 08:00~12:00）==",
                "== 磁盘 I/O 情况（昨天 08:00~12:00）=="
            )

            # 提取磁盘IO数据（从磁盘IO标识到文件结尾）
            disk_io_match = re.search(
                r'== 磁盘 I/O 情况（昨天 08:00~12:00）==(.*?)$',
                content,
                re.DOTALL
            )
            disk_io_data = disk_io_match.group(1).strip() if disk_io_match else ""

            return OsPerformanceData(
                hostname=hostname,
                cpu_data=cpu_data,
                memory_data=memory_data,
                disk_io_data=disk_io_data
            )

        except Exception as e:
            logger.error(f"解析10_sar_report.txt失败: {e}")
            return None

    @staticmethod
    def _extract_section_data(content: str, start_marker: str, end_marker: str) -> str:
        """
        提取两个标记之间的内容
        
        Args:
            content: 文件全部内容
            start_marker: 开始标记
            end_marker: 结束标记
            
        Returns:
            str: 提取的内容，失败返回空字符串
        """
        try:
            start_pos = content.find(start_marker)
            if start_pos == -1:
                return ""
            
            end_pos = content.find(end_marker, start_pos)
            if end_pos == -1:
                # 如果没有找到结束标记，提取到文件结尾
                section_content = content[start_pos + len(start_marker):]
            else:
                section_content = content[start_pos + len(start_marker):end_pos]
            
            return section_content.strip()
            
        except Exception as e:
            logger.error(f"提取章节数据失败: {e}")
            return ""


class DiskSpaceParser:
    """02_hardware_info.json文件中磁盘空间信息解析器"""

    @staticmethod
    def parse_disk_space(file_path: Path) -> Optional[DiskSpaceData]:
        """
        解析02_hardware_info.json文件中的磁盘空间信息
        
        Args:
            file_path: 硬件信息JSON文件路径
            
        Returns:
            DiskSpaceData: 解析后的磁盘空间数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                hardware_data = json.load(f)

            # 获取disk_space数组
            disk_space_list = hardware_data.get('disk_space', [])
            
            if not disk_space_list:
                logger.warning("hardware_info.json中未找到disk_space数据")
                return DiskSpaceData()

            return DiskSpaceData(disk_space_info=disk_space_list)

        except Exception as e:
            logger.error(f"解析02_hardware_info.json磁盘空间信息失败: {e}")
            return None


class AwrReportParser:
    """11_awrrpt_*.html文件解析器"""
    
    @staticmethod
    def parse_awr_report(file_path: Path) -> Optional[AwrReportData]:
        """
        解析AWR报告HTML文件
        
        Args:
            file_path: AWR HTML文件路径
            
        Returns:
            AwrReportData: 解析后的AWR数据，解析失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            awr_data = AwrReportData()
            
            # 解析数据库实例信息表
            awr_data = AwrReportParser._parse_database_instance_info(html_content, awr_data)
            
            # 解析主机信息表
            awr_data = AwrReportParser._parse_host_info(html_content, awr_data)
            
            # 解析快照信息表
            awr_data = AwrReportParser._parse_snapshot_info(html_content, awr_data)
            
            return awr_data
            
        except Exception as e:
            logger.error(f"解析AWR报告文件失败: {e}")
            return None
    
    @staticmethod
    def _parse_database_instance_info(html_content: str, awr_data: AwrReportData) -> AwrReportData:
        """
        解析数据库实例信息表
        """
        try:
            # 查找数据库实例信息表
            db_table_pattern = r'<table[^>]*summary="This table displays database instance information"[^>]*>(.*?)</table>'
            db_table_match = re.search(db_table_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            if db_table_match:
                table_content = db_table_match.group(1)
                
                # 提取数据行（跳过表头）
                data_row_pattern = r'<tr><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td></tr>'
                data_match = re.search(data_row_pattern, table_content, re.IGNORECASE)
                
                if data_match:
                    awr_data.db_name = data_match.group(1).strip()
                    awr_data.db_id = data_match.group(2).strip()
                    awr_data.instance = data_match.group(3).strip()
                    awr_data.inst_num = data_match.group(4).strip()
                    awr_data.startup_time = data_match.group(5).strip()
                    awr_data.release = data_match.group(6).strip()
                    awr_data.rac = data_match.group(7).strip()
                    
        except Exception as e:
            logger.error(f"解析数据库实例信息失败: {e}")
            
        return awr_data
    
    @staticmethod
    def _parse_host_info(html_content: str, awr_data: AwrReportData) -> AwrReportData:
        """
        解析主机信息表
        """
        try:
            # 查找主机信息表
            host_table_pattern = r'<table[^>]*summary="This table displays host information"[^>]*>(.*?)</table>'
            host_table_match = re.search(host_table_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            if host_table_match:
                table_content = host_table_match.group(1)
                
                # 提取数据行（跳过表头）
                data_row_pattern = r'<tr><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td></tr>'
                data_match = re.search(data_row_pattern, table_content, re.IGNORECASE)
                
                if data_match:
                    awr_data.host_name = data_match.group(1).strip()
                    awr_data.platform = data_match.group(2).strip()
                    awr_data.cpus = data_match.group(3).strip()
                    awr_data.cores = data_match.group(4).strip()
                    awr_data.sockets = data_match.group(5).strip()
                    awr_data.memory_gb = data_match.group(6).strip()
                    
        except Exception as e:
            logger.error(f"解析主机信息失败: {e}")
            
        return awr_data
    
    @staticmethod
    def _parse_snapshot_info(html_content: str, awr_data: AwrReportData) -> AwrReportData:
        """
        解析快照信息表
        """
        try:
            # 查找快照信息表
            snapshot_table_pattern = r'<table[^>]*summary="This table displays snapshot information"[^>]*>(.*?)</table>'
            snapshot_table_match = re.search(snapshot_table_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            if snapshot_table_match:
                table_content = snapshot_table_match.group(1)
                
                # 提取Begin Snap行
                begin_snap_pattern = r'<tr><td[^>]*>Begin Snap:</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td></tr>'
                begin_match = re.search(begin_snap_pattern, table_content, re.IGNORECASE)
                
                if begin_match:
                    awr_data.begin_snap_id = begin_match.group(1).strip()
                    awr_data.begin_snap_time = begin_match.group(2).strip()
                    awr_data.begin_sessions = begin_match.group(3).strip()
                    awr_data.begin_cursors_per_session = begin_match.group(4).strip()
                    awr_data.instances = begin_match.group(5).strip()
                
                # 提取End Snap行
                end_snap_pattern = r'<tr><td[^>]*>End Snap:</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td></tr>'
                end_match = re.search(end_snap_pattern, table_content, re.IGNORECASE)
                
                if end_match:
                    awr_data.end_snap_id = end_match.group(1).strip()
                    awr_data.end_snap_time = end_match.group(2).strip()
                    awr_data.end_sessions = end_match.group(3).strip()
                    awr_data.end_cursors_per_session = end_match.group(4).strip()
                
                # 提取Elapsed时间
                elapsed_pattern = r'<tr><td[^>]*>Elapsed:</td><td[^>]*>[^<]*</td><td[^>]*[^>]*>([^<]+)</td>'
                elapsed_match = re.search(elapsed_pattern, table_content, re.IGNORECASE)
                if elapsed_match:
                    awr_data.elapsed_minutes = elapsed_match.group(1).strip()
                
                # 提取DB Time
                db_time_pattern = r'<tr><td[^>]*>DB Time:</td><td[^>]*>[^<]*</td><td[^>]*[^>]*>([^<]+)</td>'
                db_time_match = re.search(db_time_pattern, table_content, re.IGNORECASE)
                if db_time_match:
                    awr_data.db_time_minutes = db_time_match.group(1).strip()
                    
        except Exception as e:
            logger.error(f"解析快照信息失败: {e}")
            
        return awr_data
