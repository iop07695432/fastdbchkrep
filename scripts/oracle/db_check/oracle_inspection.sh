#!/bin/bash
#================================================================
# Oracle db_check/12c/19c/单机/RAC 巡检脚本
# 作者: 自动化巡检脚本
# 版本: v2.0
# 作者：yzj（须佐）
# 说明: 需要以root用户执行，自动收集Oracle数据库和系统相关信息
# 支持单机和RAC模式
# 用法: ./oracle_inspection.sh -sid <ORACLE_SID> -outdir <OUTPUT_DIR> -db_model <single|rac>
#================================================================

set -e

# 颜色输出函数
print_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

print_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

print_warning() {
    echo -e "\033[33m[WARNING]\033[0m $1"
}

# 参数解析
ORACLE_SID=""
outdir=""
db_model=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -sid)
            ORACLE_SID="${2,,}"  # 将参数转换为小写
            shift 2
            ;;
        -outdir)
            outdir="$2"
            shift 2
            ;;
        -db_model)
            db_model="${2,,}"  # 将参数转换为小写
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 -sid <ORACLE_SID> -outdir <OUTPUT_DIR> -db_model <single|rac>"
            echo "  -sid       Oracle数据库SID"
            echo "  -outdir    输出目录的基础路径"
            echo "  -db_model  数据库模式: single(单机) 或 rac(RAC集群)"
            echo ""
            echo "注意: -sid 和 -db_model 参数会自动转为小写"
            echo ""
            echo "示例: $0 -sid ORCL -outdir /tmp -db_model single"
            echo "      $0 -sid ORCL -outdir /tmp -db_model RAC"
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            print_info "使用 -h 或 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 检查必需参数
if [ -z "$ORACLE_SID" ] || [ -z "$outdir" ] || [ -z "$db_model" ]; then
    print_error "缺少必需参数"
    print_info "用法: $0 -sid <ORACLE_SID> -outdir <OUTPUT_DIR> -db_model <single|rac>"
    print_info "注意: -sid 和 -db_model 参数会自动转为小写"
    print_info "示例: $0 -sid ORCL -outdir /tmp -db_model RAC"
    exit 1
fi

# 验证db_model参数
if [[ "$db_model" != "single" && "$db_model" != "rac" ]]; then
    print_error "无效的 db_model 参数: $db_model"
    print_error "db_model 必须是 'single' 或 'rac'"
    exit 1
fi

export ORACLE_SID
# 处理路径，避免双斜杠
if [[ "$outdir" == */ ]]; then
    export report_dir="$outdir$(hostname)_${ORACLE_SID}_$(date +'%Y%m%d')"
else
    export report_dir="$outdir/$(hostname)_${ORACLE_SID}_$(date +'%Y%m%d')"
fi

# 检查是否为root用户
if [[ $EUID -ne 0 ]]; then
   print_error "此脚本必须以root用户执行"
   exit 1
fi

# 创建报告目录
print_info "创建巡检报告目录: $report_dir"
mkdir -p "$report_dir"
chmod 777 "$report_dir"

# 初始化文件状态跟踪
export file_status_log="$report_dir/.file_generation_status"
cat > "$file_status_log" << EOF
# 文件生成状态跟踪 (格式: filename:status:description)
# status: SUCCESS/FAILED/SKIPPED
01_system_info.txt:PENDING:系统信息
02_hardware_info.json:PENDING:硬件信息(JSON格式)
03_alert_${ORACLE_SID}.log:PENDING:Oracle告警日志
04_health_check.txt:PENDING:数据库健康检查
05_adrci_ora.txt:PENDING:ADRCI诊断信息
09_rman_info.txt:PENDING:RMAN备份信息
10_sar_report.txt:PENDING:系统资源监控
11_awrrpt_${ORACLE_SID}.html:PENDING:AWR性能报告
00_inspection_summary.txt:PENDING:巡检汇总
EOF

# 为RAC模式添加额外的文件状态
if [[ "$db_model" == "rac" ]]; then
    cat >> "$file_status_log" << EOF
06_asm_udev.txt:PENDING:ASM磁盘UDEV配置 (RAC专用)
07_multipath.txt:PENDING:多路径磁盘状态 (RAC专用)
08_crs_info.txt:PENDING:CRS和OCR信息 (RAC专用)
EOF
fi

# 状态更新函数
update_file_status() {
    local filename="$1"
    local status="$2"
    local description="$3"

    # 使用临时文件来原子性更新
    local temp_file="$file_status_log.tmp"

    if grep -q "^${filename}:" "$file_status_log" 2>/dev/null; then
        # 更新existing entry
        sed "s/^${filename}:.*/${filename}:${status}:${description}/" "$file_status_log" > "$temp_file"
        mv "$temp_file" "$file_status_log"
    else
        # 添加new entry
        echo "${filename}:${status}:${description}" >> "$file_status_log"
    fi
}

# 检查Oracle用户和环境
if ! id oracle &>/dev/null; then
    print_error "Oracle用户不存在"
    exit 1
fi

print_info "开始Oracle数据库巡检 (SID: $ORACLE_SID)..."

#---------------------------------------------------------
# 1、系统信息收集
#---------------------------------------------------------
print_info "收集系统信息..."
{
    echo "========== 系统版本信息 =========="
    cat /etc/redhat-release 2>/dev/null || cat /etc/os-release 2>/dev/null || uname -a
    echo ""

    echo "========== 内核版本 =========="
    uname -r
    echo ""

    echo "========== 生效的内核参数 =========="
    echo "--- 共享内存参数 ---"
    sysctl kernel.shmmax kernel.shmall kernel.shmmni 2>/dev/null
    echo ""
    echo "--- 信号量参数 ---"
    sysctl kernel.sem 2>/dev/null
    echo ""
    echo "--- 文件句柄参数 ---"
    sysctl fs.file-max 2>/dev/null
    echo ""
    echo "--- 网络参数 ---"
    sysctl net.ipv4.ip_local_port_range 2>/dev/null
    sysctl net.core.rmem_default net.core.rmem_max 2>/dev/null
    sysctl net.core.wmem_default net.core.wmem_max 2>/dev/null
    echo ""

    echo "========== 资源限制参数 =========="
    echo "--- Oracle用户限制 ---"
    su - oracle -c "ulimit -a" 2>/dev/null
    echo ""
    echo "--- /etc/security/limits.conf 中oracle相关配置 ---"
    grep -i oracle /etc/security/limits.conf 2>/dev/null || echo "未找到Oracle相关配置"
    echo ""

    echo "========== 磁盘调度算法 =========="
    for disk in $(lsblk -nd -o NAME 2>/dev/null | grep -E '^(sd|nvme|vd)' || true); do
        if [ -f "/sys/block/$disk/queue/scheduler" ]; then
            echo "$disk: $(cat /sys/block/$disk/queue/scheduler)"
        fi
    done
    echo ""

    echo "========== 系统启动时间和负载 =========="
    uptime
    echo ""

} > "$report_dir/01_system_info.txt"

# 更新系统信息文件状态
if [ -f "$report_dir/01_system_info.txt" ] && [ -s "$report_dir/01_system_info.txt" ]; then
    update_file_status "01_system_info.txt" "SUCCESS" "系统信息"
else
    update_file_status "01_system_info.txt" "FAILED" "系统信息"
fi

#---------------------------------------------------------
# 2、硬件信息收集 (JSON格式)
#---------------------------------------------------------
print_info "收集硬件信息..."
{
    echo "{"

    # CPU信息
    echo '  "cpu": {'
    echo '    "model": "'$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | sed 's/^ *//' | sed 's/"/\\"/g')'",'
    echo '    "cores": '$(nproc)','
    echo '    "physical_cores": '$(grep "physical id" /proc/cpuinfo | sort | uniq | wc -l)','
    echo '    "logical_cores": '$(grep "processor" /proc/cpuinfo | wc -l)','

    # NUMA信息
    if command -v numactl &> /dev/null; then
        numa_nodes=$(numactl --hardware 2>/dev/null | grep "available:" | awk '{print $2}' || echo "0")
        echo '    "numa_nodes": '$numa_nodes
    else
        echo '    "numa_nodes": 0'
    fi
    echo '  },'

    # 内存信息
    total_mem_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    total_mem_gb=$((total_mem_kb / 1024 / 1024))
    echo '  "memory": {'
    echo '    "total_kb": '$total_mem_kb','
    echo '    "total_gb": '$total_mem_gb
    echo '  },'

    # 磁盘空间信息
    echo '  "disk_space": ['
    df -h | grep -v "Filesystem" | while IFS= read -r line; do
        filesystem=$(echo "$line" | awk '{print $1}')
        size=$(echo "$line" | awk '{print $2}')
        used=$(echo "$line" | awk '{print $3}')
        avail=$(echo "$line" | awk '{print $4}')
        use_percent=$(echo "$line" | awk '{print $5}')
        mount_point=$(echo "$line" | awk '{print $6}')

        echo '    {'
        echo '      "filesystem": "'$filesystem'",'
        echo '      "size": "'$size'",'
        echo '      "used": "'$used'",'
        echo '      "available": "'$avail'",'
        echo '      "use_percent": "'$use_percent'",'
        echo '      "mount_point": "'$mount_point'"'
        echo '    },'
    done | sed '$ s/,$//'
    echo '  ]'
    echo "}"
} > "$report_dir/02_hardware_info.json"

# 更新硬件信息文件状态
if [ -f "$report_dir/02_hardware_info.json" ] && [ -s "$report_dir/02_hardware_info.json" ]; then
    update_file_status "02_hardware_info.json" "SUCCESS" "硬件信息(JSON格式)"
else
    update_file_status "02_hardware_info.json" "FAILED" "硬件信息(JSON格式)"
fi

#---------------------------------------------------------
# 3、获取 alert.log 文件
#---------------------------------------------------------
print_info "收集Oracle alert.log文件..."
su - oracle bash -c 'cp $(find $ORACLE_BASE/diag/rdbms -name "alert_'"$ORACLE_SID"'.log") '"$report_dir"'/03_alert_'"$ORACLE_SID"'.log &>/dev/null' || print_warning "alert.log文件收集失败"

# 更新alert.log文件状态
if [ -f "$report_dir/03_alert_${ORACLE_SID}.log" ] && [ -s "$report_dir/03_alert_${ORACLE_SID}.log" ]; then
    update_file_status "03_alert_${ORACLE_SID}.log" "SUCCESS" "Oracle告警日志"
else
    update_file_status "03_alert_${ORACLE_SID}.log" "FAILED" "Oracle告警日志"
fi

#---------------------------------------------------------
# 4、执行health_check.sql (内嵌SQL内容)
#---------------------------------------------------------
print_info "执行health_check.sql健康检查..."

# 创建临时SQL文件，避免heredoc复杂引用问题
cat > /tmp/health_check_temp.sql << 'EOSQL_TEMP'
spool &1
set lines 200;
set pagesize 20000;
break on report
compute sum label total of mbytes on report
col mbytes format 9999999999.999
col tablespace_name format a15

prompt ..........................................................
prompt . 脚  本 名 称：health_check.sql (Enhanced Version)
prompt . 版        本：V2.0
prompt . 创   建   者：鼎城科技(yzj)
prompt . 最后修改日期：2025-08-23
prompt . 增强功能：DG状态、性能参数、日志路径、格式统一
prompt ..........................................................

-- ==============================================================================
-- 第一部分：数据库基础参数信息 (Database Basic Parameters)
-- ==============================================================================

prompt
prompt ==================== DATABASE BASIC PARAMETERS ====================
prompt

prompt [DB_BASIC_INFO_START]
prompt A1. 数据库实例基本信息
col instance_name format a15
col db_name format a15
col db_unique_name format a20
col database_role format a16
col open_mode format a20
col version format a17
col host_name format a30
col startup_time format a20

col inst_id format 99
SELECT
    i.inst_id "INST_ID",
    i.instance_name "INSTANCE_NAME",
    d.name "DB_NAME",
    d.db_unique_name "DB_UNIQUE_NAME",
    d.database_role "DATABASE_ROLE",
    d.open_mode "OPEN_MODE",
    i.version "VERSION",
    i.host_name "HOST_NAME",
    to_char(i.startup_time,'YYYY-MM-DD HH24:MI:SS') "STARTUP_TIME"
FROM gv$instance i, v$database d
ORDER BY i.inst_id;

prompt A2. 数据库服务名和全局名
col global_name format a50
col service_name format a30
SELECT global_name FROM global_name;
SELECT name service_name FROM v$services WHERE name != 'SYS$BACKGROUND' ORDER BY name;

prompt A3. 数据库字符集信息
col parameter format a35
col value format a30
SELECT parameter, value FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET', 'NLS_TERRITORY', 'NLS_LANGUAGE');

prompt A4. 归档模式信息
col log_mode format a20
col archive_mode format a15
col archive_dest format a80
SELECT
    log_mode "LOG_MODE",
    CASE
        WHEN log_mode = 'ARCHIVELOG' THEN 'ENABLED'
        ELSE 'DISABLED'
    END "ARCHIVE_MODE"
FROM v$database;

prompt A4.1 归档目录配置
col name format a35
col value format a80
SELECT inst_id, name, value
FROM gv$parameter
WHERE name LIKE 'log_archive_dest%'
  AND value IS NOT NULL
ORDER BY inst_id, name;

prompt A4.2 归档日志当前信息
col inst_id format 99
col dest_name format a20
col status format a10
col destination format a60
col archiver format a10
SELECT
    inst_id,
    dest_name,
    status,
    destination,
    archiver
FROM gv$archive_dest
WHERE status != 'INACTIVE'
ORDER BY inst_id, dest_id;

prompt [DB_BASIC_INFO_END]

prompt
prompt ==================== DATABASE PERFORMANCE PARAMETERS ====================
prompt

prompt [DB_PERF_PARAMS_START]
prompt B1. 内存相关参数 (Memory Parameters)
col name format a35
col value format a20
col description format a100

col inst_id format 99
SELECT inst_id, name, value, description
FROM gv$parameter
WHERE name IN (
               'sga_target', 'sga_max_size', 'pga_aggregate_target',
               'memory_target', 'memory_max_target', 'shared_pool_size',
               'buffer_cache_advice', 'db_cache_size', 'java_pool_size',
               'large_pool_size', 'streams_pool_size'
    ) ORDER BY inst_id, name;

prompt B2. CPU相关参数 (CPU Parameters)
SELECT inst_id, name, value, description
FROM gv$parameter
WHERE name IN (
               'cpu_count', 'parallel_max_servers', 'parallel_min_servers',
               'processes', 'sessions', 'transactions'
    ) ORDER BY inst_id, name;

prompt B3. 游标相关参数 (Cursor Parameters)
SELECT inst_id, name, value, description
FROM gv$parameter
WHERE name IN (
               'open_cursors', 'session_cached_cursors', 'cursor_space_for_time'
    ) ORDER BY inst_id, name;

prompt B4. 数据库关键参数 (Key Database Parameters)
col name format a30
col value format a100
col description format a60
SELECT inst_id, name, value, description
FROM gv$parameter
WHERE name IN (
               'db_block_size', 'db_files', 'control_files', 'log_buffer',
               'undo_management', 'undo_tablespace', 'undo_retention',
               'archive_lag_target', 'fast_start_mttr_target'
    ) ORDER BY inst_id, name;
prompt [DB_PERF_PARAMS_END]

prompt
prompt ==================== DATABASE LOG PATHS ====================
prompt

prompt [DB_LOG_PATHS_START]
prompt C1. 重要日志文件路径
col parameter_name format a35
col file_path format a80

-- Alert Log路径
col inst_id format 99
SELECT inst_id, 'ALERT_LOG' parameter_name, value file_path
FROM gv$parameter WHERE name = 'background_dump_dest'
UNION ALL
-- 诊断目录
SELECT inst_id, 'DIAGNOSTIC_DEST' parameter_name, value file_path
FROM gv$parameter WHERE name = 'diagnostic_dest'
UNION ALL
-- Core Dump路径
SELECT inst_id, 'CORE_DUMP_DEST' parameter_name, value file_path
FROM gv$parameter WHERE name = 'core_dump_dest'
UNION ALL
-- User Dump路径
SELECT inst_id, 'USER_DUMP_DEST' parameter_name, value file_path
FROM gv$parameter WHERE name = 'user_dump_dest'
UNION ALL
-- Audit文件路径
SELECT inst_id, 'AUDIT_FILE_DEST' parameter_name, value file_path
FROM gv$parameter WHERE name = 'audit_file_dest'
ORDER BY inst_id, parameter_name;

prompt C2. 控制文件路径
col control_file_path format a80
SELECT name control_file_path FROM v$controlfile ORDER BY name;

prompt C3. 归档日志路径
col inst_id format 99
col dest_name format a20
col destination format a60
col status format a10
SELECT inst_id, dest_name, destination, status
FROM gv$archive_dest
WHERE status = 'VALID' AND destination IS NOT NULL
ORDER BY inst_id, dest_name;
prompt [DB_LOG_PATHS_END]

-- ==============================================================================
-- 第二部分：数据库状态检查 (保持原有逻辑)
-- ==============================================================================

prompt
prompt ==================== DATABASE STATUS CHECKS ====================
prompt

prompt [DB_STATUS_START]
prompt 1.数据库版本号和实例名

col version format a80
select banner Version from v$version;
col inst_id format 99
col instance_name format a20
select inst_id, instance_name from gv$instance order by inst_id;

prompt 2.当前用户数


select inst_id,count(*) from gv$session where type='USER' group by inst_id;

prompt 3.SGA大小

show sga
prompt
prompt PGA使用

col inst_id format 99
col name format a45
col value format 999999999999999
select inst_id, name, value from gv$pgastat order by inst_id, name;

prompt 4.控制文件的信息

col STATUS format a7
col NAME format a80
select * from v$controlfile ORDER BY name;

prompt 5.数据库初始化参数

col inst_id format 99
col name format a40
col value format a60
select inst_id,name,value,isdefault,ismodified from gv$parameter order by inst_id,name;

prompt 6.数据库系统信息

col inst_id format 99
col POOL format a12
col NAME format a26
select inst_id,pool,name,bytes/1024/1024 mbytes from gv$sgastat order by inst_id,name;

prompt 7.表空间和数据文件信息

prompt 所有数据文件大小

select sum(bytes)/1024/1024 MB from dba_data_files;

prompt 纯数据大小

col mbytes format 9999999999
select segment_type,sum(bytes)/1024/1024 mbytes from dba_segments group by segment_type ORDER BY sum(bytes) DESC;

prompt 表空间数目

select count(*) from dba_tablespaces;

prompt 数据文件数目

select count(*) from dba_data_files;

prompt 临时文件使用情况

col status format a15
select tablespace_name,bytes/1024/1024 mbytes,status,autoextensible aut,maxbytes/1024/1024 max from dba_temp_files ORDER BY tablespace_name;

prompt 表空间基本信息

col name format a20
col status format a7
col em format a5
col init format 99999999
select TABLESPACE_NAME name,initial_extent init,next_extent next,max_extents max,contents,status,EXTENT_MANAGEMENT em,SEGMENT_SPACE_MANAGEMENT sm from dba_tablespaces ORDER BY TABLESPACE_NAME;

prompt 表空间使用情况

col tablespace format a28
SELECT D.TABLESPACE_NAME tablespace,
    SPACE "SUM_SPACE(M)",
    BLOCKS SUM_BLOCKS,
    SPACE - NVL(FREE_SPACE, 0) "USED_SPACE(M)",
    ROUND((1 - NVL(FREE_SPACE, 0) / SPACE) * 100, 2) "USED_RATE(%)",
    FREE_SPACE "FREE_SPACE(M)"
FROM (SELECT TABLESPACE_NAME,
    ROUND(SUM(BYTES) / (1024 * 1024), 2) SPACE,
    SUM(BLOCKS) BLOCKS
    FROM DBA_DATA_FILES
    GROUP BY TABLESPACE_NAME) D,
    (SELECT TABLESPACE_NAME,
    ROUND(SUM(BYTES) / (1024 * 1024), 2) FREE_SPACE
    FROM DBA_FREE_SPACE
    GROUP BY TABLESPACE_NAME) F WHERE D.TABLESPACE_NAME = F.TABLESPACE_NAME(+)
UNION ALL
SELECT D.TABLESPACE_NAME,
    SPACE "SUM_SPACE(M)",
    BLOCKS SUM_BLOCKS,
    USED_SPACE "USED_SPACE(M)",
    ROUND(NVL(USED_SPACE, 0) / SPACE * 100, 2) "USED_RATE(%)",
    NVL(FREE_SPACE, 0) "FREE_SPACE(M)"
FROM (SELECT TABLESPACE_NAME,
    ROUND(SUM(BYTES) / (1024 * 1024), 2) SPACE,
    SUM(BLOCKS) BLOCKS
    FROM DBA_TEMP_FILES
    GROUP BY TABLESPACE_NAME) D,
    (SELECT TABLESPACE_NAME,
    ROUND(SUM(BYTES_USED) / (1024 * 1024), 2) USED_SPACE,
    ROUND(SUM(BYTES_FREE) / (1024 * 1024), 2) FREE_SPACE
    FROM V$TEMP_SPACE_HEADER
    GROUP BY TABLESPACE_NAME) F WHERE D.TABLESPACE_NAME = F.TABLESPACE_NAME(+)
ORDER BY tablespace;

prompt 数据文件大小与自动扩展

col tablespace_name format a28
select file_id,tablespace_name,autoextensible,bytes/1024/1024 mbytes,ROUND(MAXBYTES/1024/1024/1024,0) maxgbytes
from dba_data_files
order by autoextensible,tablespace_name;


prompt 数据文件列表

select file_name
from dba_data_files;
select file_name tempfile from dba_temp_files;


prompt 8.日志文件信息

col group# format 99
col mbytes format 9999999
col thread# format 9
col status format a8
col inst_id format 99
select inst_id,GROUP#,THREAD#,SEQUENCE#,BYTES/1024/1024 mbytes,MEMBERS,archived,STATUS,FIRST_CHANGE#,FIRST_TIME from gv$log order by inst_id,group#;
col member format a50
select * from v$logfile ORDER BY group#, member;

prompt 归档统计

SELECT
  TO_CHAR(TRUNC(COMPLETION_TIME, 'DD'), 'YYYY-MM-DD') AS ArchiveDate,
  COUNT(*) AS Archives_Per_Day,
  ROUND(SUM(BLOCKS * BLOCK_SIZE) / 1024 / 1024 / 1024, 2) AS Size_GB
FROM gv$archived_log
WHERE dest_id = 1
GROUP BY TRUNC(COMPLETION_TIME, 'DD')
ORDER BY TRUNC(COMPLETION_TIME, 'DD');

prompt 9.命中率统计

select distinct 1-(select sum(value) from gv$sysstat where name='physical reads')/((select sum(value) from gv$sysstat where name='db block gets')
    +(select sum(value) from gv$sysstat where name='consistent gets')) as buffer_cache_rate
from gv$sysstat where rownum = 1;
select 1-sum(buffer_busy_wait)/sum(buf_got) as Buffer_Nowait from gv$buffer_pool_statistics;
select 1-sum(reloads)/sum(pins) as librarycach_rate from gv$librarycache;
select 1-sum(waits)/sum(gets) as Redo_NoWait from gv$rollstat;
select 1-sum(waits_holding_latch)/sum(gets)*100 as Latch_rate from gv$latch;

prompt 10.回滚段统计

col owner format a10
col status format a10
col segment_name format a25
col tablespace_name format a15
col file_id format 0
col mbytes format 9999999999.999



SELECT SEGMENT_NAME,OWNER,
       TABLESPACE_NAME,SEGMENT_ID,FILE_ID,STATUS
FROM DBA_ROLLBACK_SEGS;


prompt 11.用户使用系统表空间情况

 col username format a10
 col DEFAULT_TABLESPACE format a20
 col TEMPORARY_TABLESPACE format a20
select username,DEFAULT_TABLESPACE,TEMPORARY_TABLESPACE from dba_users
where DEFAULT_TABLESPACE='SYSTEM' or temporary_tablespace='SYSTEM'
ORDER BY username;

prompt 系统表空间中的用户segment统计

select distinct segment_type,
       sum(bytes)/1024/1024 mbytes,
       count(*)
    from dba_segments where owner not in ('SYS','SYSTEM','DBSNMP','OUTLN','WMSYS')
    and tablespace_name='SYSTEM'
group by segment_type
ORDER BY 2 DESC;

select distinct
       owner,
       sum(bytes)/1024/1024 mbytes,
       count(*)
  from dba_segments
where owner not in ('SYS','SYSTEM','DBSNMP','OUTLN','WMSYS') and tablespace_name='SYSTEM'
group by owner
ORDER BY 2 DESC;

prompt 非系统表空间中的用户segment统计
col owner format a30
select distinct owner,sum(bytes)/1024/1024 mbytes,count(*) from dba_segments
where owner not in ('SYS','SYSTEM','DBSNMP','OUTLN','WMSYS')
group by owner
ORDER BY 2 DESC;


prompt 12.数据库对象检查

 col index_type format a10
 col object_name format a30
 prompt 行链接和行迁移

select owner,table_name,chain_cnt from dba_tables where chain_cnt>0;

prompt 无效索引

select owner,index_name,index_type,status  from dba_indexes where status='UNUSABLE';

prompt 无效对象

select owner,object_type,object_name,status from dba_objects where status='INVALID' order by owner,object_type;

prompt 禁用的约束

 col constraint_name format a35
 col table_name format a35
Select constraint_type,constraint_name,table_name,status From dba_constraints Where status<>'ENABLED'
ORDER BY constraint_type, table_name, constraint_name;

prompt 禁用的触发器

 col trigger_name format a35
 col table_name format a35
select trigger_name,table_name,status From dba_triggers Where status!='ENABLED'
ORDER BY table_name, trigger_name;


prompt 13.组件状态情况

 col comp_name format a40
 col version format a15
select comp_name,version,status from dba_registry ORDER BY comp_name;

prompt 14.空块占用较高的百兆表

select table_name,BLOCKS,EMPTY_BLOCKS,ROUND(EMPTY_BLOCKS/BLOCKS*100) from dba_tables where BLOCKS>=12800 and ROUND(EMPTY_BLOCKS/BLOCKS*100)>=30
ORDER BY ROUND(EMPTY_BLOCKS/BLOCKS*100) DESC, table_name;

prompt 15.PL/SQLDeveloper破解版勒索病毒检查

select 'DROP TRIGGER '||owner||'."'||TRIGGER_NAME||'";' from dba_triggers where TRIGGER_NAME like  'DBMS_%_INTERNAL%' union all select 'DROP PROCEDURE '||owner||'."'||a.object_name||'";' from dba_procedures a where a.object_name in ('DBMS_SUPPORT_INTERNAL','DBMS_SYSTEM_INTERNAL','DBMS_CORE_INTERNAL','DBMS_STANDARD_FUN9');


prompt 16.1 ASM磁盘组概览

COLUMN NAME FORMAT A15 HEADING 'DISKGROUP NAME'
COLUMN TOTAL_GB FORMAT 99999.99 HEADING 'TOTAL(GB)'
COLUMN FREE_GB FORMAT 99999.99 HEADING 'FREE(GB)'
COLUMN USED_PCT FORMAT A10 HEADING 'USED %'

SELECT
    NAME,
    ROUND(TOTAL_MB/1024, 2) AS TOTAL_GB,
    ROUND(FREE_MB/1024, 2) AS FREE_GB,
    ROUND((TOTAL_MB-FREE_MB)/TOTAL_MB*100, 2) || '%' AS USED_PCT
FROM v$asm_diskgroup;

prompt 16.2 ASM磁盘详细信息

SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TRIMOUT ON
SET TAB OFF
COLUMN GROUP_NUMBER         FORMAT 999           HEADING 'GROUP|NO'
COLUMN DISKGROUP_NAME       FORMAT A15           HEADING 'DISKGROUP'
COLUMN DISK_NAME            FORMAT A10           HEADING 'DISK|NAME'
COLUMN DISK_PATH            FORMAT A25           HEADING 'DISK PATH'
COLUMN MOUNT_STATUS         FORMAT A10
COLUMN HEADER_STATUS        FORMAT A10
COLUMN MODE_STATUS          FORMAT A10
COLUMN STATE                FORMAT A10
COLUMN TOTAL_GB             FORMAT 999999.99     HEADING 'DISK|TOTAL(GB)'
COLUMN FREE_GB              FORMAT 999999.99     HEADING 'DISK|FREE(GB)'
COLUMN GROUP_TOTAL_GB       FORMAT 999999.99     HEADING 'GROUP|TOTAL(GB)'
COLUMN GROUP_FREE_GB        FORMAT 999999.99     HEADING 'GROUP|FREE(GB)'
COLUMN REQ_MIRROR_FREE_GB   FORMAT 999999.99     HEADING 'REQUIRED|MIRROR|FREE(GB)'
COLUMN USABLE_FILE_GB       FORMAT 999999.99     HEADING 'USABLE|FILE(GB)'

SELECT
    d.GROUP_NUMBER,
    dg.NAME AS DISKGROUP_NAME,
    d.NAME  AS DISK_NAME,
    d.PATH  AS DISK_PATH,
    d.MOUNT_STATUS,
    d.HEADER_STATUS,
    d.MODE_STATUS,
    d.STATE,
    d.TOTAL_MB / 1024        AS TOTAL_GB,
    d.FREE_MB / 1024         AS FREE_GB,
    dg.TOTAL_MB / 1024       AS GROUP_TOTAL_GB,
    dg.FREE_MB / 1024        AS GROUP_FREE_GB,
    dg.REQUIRED_MIRROR_FREE_MB / 1024 AS REQ_MIRROR_FREE_GB,
    dg.USABLE_FILE_MB / 1024           AS USABLE_FILE_GB
FROM
    gv$asm_disk_stat d
        LEFT JOIN  gv$asm_diskgroup dg ON d.GROUP_NUMBER = dg.GROUP_NUMBER AND d.inst_id = dg.inst_id
ORDER BY d.inst_id, dg.NAME, d.NAME;

prompt 16.3 ASM磁盘基本信息 (原有信息)

col inst_id format 99
select inst_id,name,state,type,total_mb,total_mb-free_mb USED_MB,free_mb from gv$asm_diskgroup order by inst_id,name;

prompt [DB_STATUS_END]

-- ==============================================================================
-- 第三部分：Data Guard 相关检查
-- ==============================================================================

prompt
prompt ==================== DATA GUARD INFORMATION ====================
prompt

prompt [DG_INFO_START]
prompt D1. Data Guard 基本配置检查
col dg_role format a20
col dg_status format a20

SELECT
    CASE
        WHEN database_role = 'PRIMARY' THEN 'PRIMARY DATABASE'
        WHEN database_role = 'PHYSICAL STANDBY' THEN 'PHYSICAL STANDBY'
        WHEN database_role = 'LOGICAL STANDBY' THEN 'LOGICAL STANDBY'
        ELSE 'STANDALONE DATABASE'
        END as dg_role,
    open_mode as dg_status,
    switchover_status
FROM v$database;

prompt D2. 归档传输目的地配置 (Archive Destination Configuration)
col inst_id format 99
col dest_id format 99
col dest_name format a20
col destination format a60
col status format a10
col binding format a10
col target format a10

SELECT inst_id, dest_id, dest_name, destination, status, binding, target
FROM gv$archive_dest
WHERE status IN ('VALID', 'ERROR', 'DEFERRED')
  AND destination IS NOT NULL
ORDER BY inst_id, dest_id;

prompt D3. Data Guard 相关参数
col inst_id format 99
col parameter format a35
col value format a80

SELECT inst_id, name parameter, value
FROM gv$parameter
WHERE name IN (
               'log_archive_config',
               'log_archive_dest_1', 'log_archive_dest_2', 'log_archive_dest_3',
               'log_archive_dest_state_1', 'log_archive_dest_state_2', 'log_archive_dest_state_3',
               'log_archive_format',
               'log_archive_max_processes',
               'fal_server', 'fal_client',
               'standby_file_management',
               'db_file_name_convert',
               'log_file_name_convert',
               'remote_login_passwordfile'
    ) AND value IS NOT NULL
ORDER BY inst_id, name;

prompt D4. Data Guard 状态消息 (最近50条)
-- 检查v$dataguard_status视图是否存在
set line 2000 pagesize 3000 long 9999999
col inst_id format 99
col facility format a30
col severity format a25
col error_code format 9999999
col message format a120
col timestamp format a20

SELECT * FROM (
                  SELECT
                      inst_id,
                      facility,
                      severity,
                      error_code,
                      message,
                      to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') timestamp
                  FROM gv$dataguard_status
                  WHERE timestamp >= SYSDATE - 7  -- 最近7天
                  ORDER BY timestamp DESC
              ) WHERE rownum <= 50;

prompt D5. 传输/应用延迟统计
-- 检查v$dataguard_stats视图
col inst_id format 99
col name format a30
col value format a20
col unit format a10
col time_computed format a20

SELECT
    inst_id,
    name,
    value,
    unit,
    to_char(time_computed, 'YYYY-MM-DD HH24:MI:SS') time_computed
FROM gv$dataguard_stats
WHERE name IN (
               'transport lag',
               'apply lag',
               'apply finish time',
               'estimated startup time'
    )
ORDER BY name;

prompt D6. 归档日志应用状态 (仅Standby数据库)
col inst_id format 99
col sequence# format 9999999
col applied format a10
col completion_time format a20

SELECT * FROM (
                  SELECT
                      inst_id,
                      thread#,
                      sequence#,
                      applied,
                      to_char(completion_time, 'YYYY-MM-DD HH24:MI:SS') completion_time
                  FROM gv$archived_log
                  WHERE applied IN ('YES', 'NO', 'IN-MEMORY')
                  ORDER BY sequence# DESC
              ) WHERE rownum <= 20;

prompt D7. MRP进程状态 (仅Standby数据库)
col inst_id format 99
col process format a10
col status format a12
col client_process format a15
col sequence# format 9999999

SELECT
    inst_id,
    process,
    status,
    client_process,
    sequence#
FROM gv$managed_standby
ORDER BY inst_id, process;
prompt [DG_INFO_END]

prompt
prompt ==================== HEALTH CHECK COMPLETED ====================
prompt over!!
spool off
exit;
EOSQL_TEMP

# 执行SQL，使用临时文件
su - oracle -c "bash -c '
source /home/oracle/.bash_profile;
\$ORACLE_HOME/bin/sqlplus \"/ as sysdba\" @/tmp/health_check_temp.sql \"$report_dir/04_health_check.txt\"
'" &>/dev/null || print_warning "health_check.sql执行失败"

# 清理临时文件
rm -f /tmp/health_check_temp.sql

# 更新health_check文件状态
if [ -f "$report_dir/04_health_check.txt" ] && [ -s "$report_dir/04_health_check.txt" ]; then
    update_file_status "04_health_check.txt" "SUCCESS" "数据库健康检查"
else
    update_file_status "04_health_check.txt" "FAILED" "数据库健康检查"
fi

#---------------------------------------------------------
# 5、获取adrci_ora.txt
#---------------------------------------------------------
print_info "收集ADRCI信息..."
su - oracle -c "bash -c '
source /home/oracle/.bash_profile;
\$ORACLE_HOME/bin/adrci <<\"EOADRCI\"
set homepath diag/rdbms/\$ORACLE_SID/\$ORACLE_SID
show homes
show alert -tail 100
show problem
show incident
exit
EOADRCI
'" > "$report_dir/05_adrci_ora.txt" 2>/dev/null || print_warning "ADRCI信息收集失败"

# 更新ADRCI文件状态
if [ -f "$report_dir/05_adrci_ora.txt" ] && [ -s "$report_dir/05_adrci_ora.txt" ]; then
    update_file_status "05_adrci_ora.txt" "SUCCESS" "ADRCI诊断信息"
else
    update_file_status "05_adrci_ora.txt" "FAILED" "ADRCI诊断信息"
fi

#---------------------------------------------------------
# 6、收集AWR报告
#---------------------------------------------------------
print_info "收集AWR报告..."

# 动态获取最近的snap_id，使用临时文件避免引用问题
cat > /tmp/get_snap_id.sql << 'EOSQL'
set pagesize 0 feedback off verify off heading off echo off
SELECT MIN(snap_id) || ',' ||  MAX(snap_id)  FROM dba_hist_snapshot WHERE trunc(begin_interval_time) = trunc(sysdate - 1) AND to_char(begin_interval_time, 'HH24MISS') BETWEEN '080000' AND '120000';
exit;
EOSQL



SNAP_INFO=$(su - oracle -c "bash -c '
source /home/oracle/.bash_profile;
\$ORACLE_HOME/bin/sqlplus -s / as sysdba @/tmp/get_snap_id.sql
'" 2>/dev/null | grep -E '^[0-9]+,[0-9]+$' || true)

# 清理临时文件
rm -f /tmp/get_snap_id.sql

if [ -n "$SNAP_INFO" ] && [ "$SNAP_INFO" != "," ]; then
    SNAP_BEGIN=$(echo "$SNAP_INFO" | cut -d',' -f1)
    SNAP_END=$(echo "$SNAP_INFO" | cut -d',' -f2)

    print_info "使用快照ID: $SNAP_BEGIN 到 $SNAP_END"

    # 生成AWR报告，使用自动化输入
    su - oracle -c "bash -c '
    source /home/oracle/.bash_profile;
    cd \"$report_dir\"
    \$ORACLE_HOME/bin/sqlplus / as sysdba <<\"EOAWR\"
set echo off feedback off verify off pagesize 0 linesize 1000
@?/rdbms/admin/awrrpt.sql
html
1
$SNAP_BEGIN
$SNAP_END
11_awrrpt_${ORACLE_SID}.html
exit
EOAWR
    '" &>/dev/null || print_warning "AWR报告生成过程出现问题"

    # 检查AWR报告是否成功生成
    if [ -f "$report_dir/11_awrrpt_${ORACLE_SID}.html" ] && [ -s "$report_dir/11_awrrpt_${ORACLE_SID}.html" ]; then
        print_info "AWR报告生成成功"
        update_file_status "11_awrrpt_${ORACLE_SID}.html" "SUCCESS" "AWR性能报告"
    else
        print_warning "AWR报告生成失败"
        update_file_status "11_awrrpt_${ORACLE_SID}.html" "FAILED" "AWR性能报告"
    fi
else
    print_warning "无法获取有效的AWR快照ID，跳过AWR报告生成"
    update_file_status "11_awrrpt_${ORACLE_SID}.html" "SKIPPED" "AWR性能报告"
fi

#---------------------------------------------------------
# 7、收集系统资源监控信息 (sar)
#---------------------------------------------------------
print_info "收集系统资源监控信息..."
YDAY=$(date --date="yesterday" +%d 2>/dev/null || date -d "1 day ago" +%d 2>/dev/null || date -v-1d +%d 2>/dev/null || echo "01")
{
    echo "== CPU 使用率（昨天 08:00~12:00）=="
    sar -u -f /var/log/sa/sa$YDAY -s 08:00:00 -e 12:00:00 2>/dev/null || echo "无法获取CPU使用率数据"
    echo ""
    echo "== 内存使用率（昨天 08:00~12:00）=="
    sar -r -f /var/log/sa/sa$YDAY -s 08:00:00 -e 12:00:00 2>/dev/null || echo "无法获取内存使用率数据"
    echo ""
    echo "== 磁盘 I/O 情况（昨天 08:00~12:00）=="
    sar -b -f /var/log/sa/sa$YDAY -s 08:00:00 -e 12:00:00 2>/dev/null || echo "无法获取磁盘I/O数据"
} > "$report_dir/10_sar_report.txt"

# 更新sar报告文件状态
if [ -f "$report_dir/10_sar_report.txt" ] && [ -s "$report_dir/10_sar_report.txt" ]; then
    update_file_status "10_sar_report.txt" "SUCCESS" "系统资源监控"
else
    update_file_status "10_sar_report.txt" "FAILED" "系统资源监控"
fi

#---------------------------------------------------------
# 8、收集RMAN备份信息
#---------------------------------------------------------
print_info "收集RMAN备份信息..."
su - oracle -c "bash -c '
source /home/oracle/.bash_profile;
\$ORACLE_HOME/bin/rman target / <<\"EORMAN\"
show all;
crosscheck backup;
list backup of database summary;
list backup of archivelog all summary;
exit;
EORMAN
'" > "$report_dir/09_rman_info.txt" 2>/dev/null || print_warning "RMAN信息收集失败"

# 更新RMAN信息文件状态
if [ -f "$report_dir/09_rman_info.txt" ] && [ -s "$report_dir/09_rman_info.txt" ]; then
    update_file_status "09_rman_info.txt" "SUCCESS" "RMAN备份信息"
else
    update_file_status "09_rman_info.txt" "FAILED" "RMAN备份信息"
fi

#---------------------------------------------------------
# 9、RAC专用功能 (仅当db_model为rac时执行)
#---------------------------------------------------------
if [[ "$db_model" == "rac" ]]; then
    print_info "执行RAC集群专用检查..."

    # 9.1、root 用户获取ASM 磁盘相关 UDEV 配置
    print_info "收集ASM磁盘UDEV配置..."
    echo "== ASM Disk UDEV 配置 ==" > "$report_dir/06_asm_udev.txt"
    echo "收集时间: $(date)" >> "$report_dir/06_asm_udev.txt"
    echo "" >> "$report_dir/06_asm_udev.txt"

    # 检查/etc/udev/rules.d/目录是否存在
    if [ -d "/etc/udev/rules.d" ]; then
        # 查找所有包含99的规则文件
        found_udev_files=0
        for file in /etc/udev/rules.d/*99*; do
            if [ -f "$file" ]; then
                echo -e "\n==== $file ====" >> "$report_dir/06_asm_udev.txt"
                if [ -r "$file" ]; then
                    cat "$file" >> "$report_dir/06_asm_udev.txt" 2>/dev/null
                    found_udev_files=1
                else
                    echo "文件不可读或权限不足" >> "$report_dir/06_asm_udev.txt"
                fi
            fi
        done

        if [ $found_udev_files -eq 0 ]; then
            echo "未找到包含'99'的UDEV规则文件" >> "$report_dir/06_asm_udev.txt"
        fi
    else
        echo "/etc/udev/rules.d/ 目录不存在" >> "$report_dir/06_asm_udev.txt"
    fi

    # 9.2、root 用户多路径状态信息，先刷新后收集
    print_info "收集多路径磁盘状态..."
    echo "== 多路径磁盘状态 ==" > "$report_dir/07_multipath.txt"
    echo "收集时间: $(date)" >> "$report_dir/07_multipath.txt"
    echo "" >> "$report_dir/07_multipath.txt"

    # 检查multipath命令是否存在
    if command -v multipath >/dev/null 2>&1; then
        echo "== 刷新多路径配置 ==" >> "$report_dir/07_multipath.txt"
        if multipath -r >> "$report_dir/07_multipath.txt" 2>&1; then
            print_info "多路径刷新成功"
        else
            print_warning "多路径刷新失败，但继续收集信息"
        fi

        echo -e "\n== 多路径磁盘详细状态 ==" >> "$report_dir/07_multipath.txt"
        multipath -ll >> "$report_dir/07_multipath.txt" 2>&1 || echo "multipath -ll 执行失败" >> "$report_dir/07_multipath.txt"
    else
        echo "multipath 命令不存在，可能未安装多路径软件" >> "$report_dir/07_multipath.txt"
        print_warning "multipath命令不存在"
    fi

    # 9.3、root获取crs和ocrcheck信息
    print_info "收集CRS和OCR信息..."
    echo "== CRS和OCR检查信息 ==" > "$report_dir/08_crs_info.txt"
    echo "收集时间: $(date)" >> "$report_dir/08_crs_info.txt"
    echo "" >> "$report_dir/08_crs_info.txt"

    # 优雅的查找crsctl和ocrcheck命令
    # 首先尝试在常见路径中查找
    crs_cmd=""
    ocrcheck_cmd=""

    # 常见的Oracle Grid Infrastructure路径
    common_paths=(
        "/u01/app/11.2.0/grid/bin"
        "/opt/app/11.2.0/grid/bin"
        "/oracle/app/11.2.0/grid/bin"
        "/u01/app/oracle/product/11.2.0/grid/bin"
        "/opt/oracle/product/11.2.0/grid/bin"
    )

    # 首先在常见路径中查找
    for path in "${common_paths[@]}"; do
        if [ -x "$path/crsctl" ]; then
            crs_cmd="$path/crsctl"
            break
        fi
    done

    for path in "${common_paths[@]}"; do
        if [ -x "$path/ocrcheck" ]; then
            ocrcheck_cmd="$path/ocrcheck"
            break
        fi
    done

    # 如果在常见路径中没找到，再使用find命令搜索
    if [ -z "$crs_cmd" ]; then
        print_info "在常见路径中未找到crsctl，正在全局搜索..."
        crs_cmd=$(find /u01 /opt /oracle -type f -name 'crsctl' -executable 2>/dev/null | head -1)
        if [ -z "$crs_cmd" ]; then
            # 最后的尝试，搜索整个根目录（但限制搜索深度和排除一些目录）
            crs_cmd=$(find / -maxdepth 6 -type f -name 'crsctl' -executable \
                      -not -path "/proc/*" -not -path "/sys/*" -not -path "/dev/*" \
                      -not -path "/tmp/*" -not -path "/var/tmp/*" 2>/dev/null | head -1)
        fi
    fi

    if [ -z "$ocrcheck_cmd" ]; then
        print_info "在常见路径中未找到ocrcheck，正在全局搜索..."
        ocrcheck_cmd=$(find /u01 /opt /oracle -type f -name 'ocrcheck' -executable 2>/dev/null | head -1)
        if [ -z "$ocrcheck_cmd" ]; then
            # 最后的尝试，搜索整个根目录（但限制搜索深度和排除一些目录）
            ocrcheck_cmd=$(find / -maxdepth 6 -type f -name 'ocrcheck' -executable \
                           -not -path "/proc/*" -not -path "/sys/*" -not -path "/dev/*" \
                           -not -path "/tmp/*" -not -path "/var/tmp/*" 2>/dev/null | head -1)
        fi
    fi

    # 执行CRS状态检查
    if [ -n "$crs_cmd" ] && [ -x "$crs_cmd" ]; then
        echo "== CRS资源状态 (使用: $crs_cmd) ==" >> "$report_dir/08_crs_info.txt"
        if ! timeout 30 "$crs_cmd" status res -t >> "$report_dir/08_crs_info.txt" 2>&1; then
            echo "crsctl status res -t 执行失败或超时" >> "$report_dir/08_crs_info.txt"
            print_warning "CRS状态检查失败或超时"
        fi

        echo "" >> "$report_dir/08_crs_info.txt"
        echo "==========================================================================" >> "$report_dir/08_crs_info.txt"
        echo "== Voting Disk Information ==" >> "$report_dir/08_crs_info.txt"
        if ! timeout 30 "$crs_cmd" query css votedisk >> "$report_dir/08_crs_info.txt" 2>&1; then
            echo "crsctl query css votedisk 执行失败或超时" >> "$report_dir/08_crs_info.txt"
            print_warning "Voting Disk查询失败或超时"
        fi
    else
        echo "未找到可执行的crsctl命令" >> "$report_dir/08_crs_info.txt"
        print_warning "未找到crsctl命令，可能未安装Grid Infrastructure或路径不正确"
    fi

    # 执行OCR检查
    if [ -n "$ocrcheck_cmd" ] && [ -x "$ocrcheck_cmd" ]; then
        echo "" >> "$report_dir/08_crs_info.txt"
        echo "==========================================================================" >> "$report_dir/08_crs_info.txt"
        echo "== OCR检查 (使用: $ocrcheck_cmd) ==" >> "$report_dir/08_crs_info.txt"
        if ! timeout 60 "$ocrcheck_cmd" >> "$report_dir/08_crs_info.txt" 2>&1; then
            echo "ocrcheck 执行失败或超时" >> "$report_dir/08_crs_info.txt"
            print_warning "OCR检查失败或超时"
        fi
    else
        echo -e "\n未找到可执行的ocrcheck命令" >> "$report_dir/08_crs_info.txt"
        print_warning "未找到ocrcheck命令，可能未安装Grid Infrastructure或路径不正确"
    fi

    print_info "RAC集群专用检查完成"

    # 更新RAC专用文件状态
    if [ -f "$report_dir/06_asm_udev.txt" ] && [ -s "$report_dir/06_asm_udev.txt" ]; then
        update_file_status "06_asm_udev.txt" "SUCCESS" "ASM磁盘UDEV配置 (RAC专用)"
    else
        update_file_status "06_asm_udev.txt" "FAILED" "ASM磁盘UDEV配置 (RAC专用)"
    fi

    if [ -f "$report_dir/07_multipath.txt" ] && [ -s "$report_dir/07_multipath.txt" ]; then
        update_file_status "07_multipath.txt" "SUCCESS" "多路径磁盘状态 (RAC专用)"
    else
        update_file_status "07_multipath.txt" "FAILED" "多路径磁盘状态 (RAC专用)"
    fi

    if [ -f "$report_dir/08_crs_info.txt" ] && [ -s "$report_dir/08_crs_info.txt" ]; then
        update_file_status "08_crs_info.txt" "SUCCESS" "CRS和OCR信息 (RAC专用)"
    else
        update_file_status "08_crs_info.txt" "FAILED" "CRS和OCR信息 (RAC专用)"
    fi
else
    print_info "单机模式，跳过RAC集群专用检查"
fi

#---------------------------------------------------------
# 生成巡检报告汇总
#---------------------------------------------------------
print_info "生成巡检报告汇总..."

# 首先标记汇总报告为成功状态
update_file_status "00_inspection_summary.txt" "SUCCESS" "巡检汇总"

{
    echo "======================================="
    echo "Oracle 数据库巡检报告"
    echo "======================================="
    echo "主机名: $(hostname)"
    echo "SID: $ORACLE_SID"
    echo "数据库模式: $db_model"
    echo "巡检时间: $(date)"
    echo "报告目录: $report_dir"
    echo ""
    echo "文件生成状态报告:"
    echo "======================================="

    # 读取并格式化输出文件状态
    while IFS=':' read -r filename status description || [ -n "$filename" ]; do
        # 跳过注释行和空行
        if [[ "$filename" =~ ^#.*$ ]] || [[ -z "$filename" ]]; then
            continue
        fi

        # 格式化状态显示
        case "$status" in
            "SUCCESS")
                status_symbol="✓"
                ;;
            "FAILED")
                status_symbol="✗"
                ;;
            "SKIPPED")
                status_symbol="○"
                ;;
            "PENDING")
                status_symbol="?"
                ;;
            *)
                status_symbol="-"
                ;;
        esac

        printf "  [%s] %-30s %s\n" "$status_symbol" "$filename" "$description"
    done < "$file_status_log"

    echo ""
    echo "状态说明: ✓=成功生成  ✗=生成失败  ○=跳过执行  ?=待处理"
    echo ""
    echo "生成的文件列表:"
    ls -la "$report_dir" | grep -v ".file_generation_status"
    echo ""
    echo "======================================="
} > "$report_dir/00_inspection_summary.txt"

print_info "巡检完成！报告文件保存在: $report_dir"
print_info ""
print_info "文件生成状态报告:"
print_info "======================================"

# 在终端也显示文件状态
while IFS=':' read -r filename status description || [ -n "$filename" ]; do
    # 跳过注释行和空行
    if [[ "$filename" =~ ^#.*$ ]] || [[ -z "$filename" ]]; then
        continue
    fi

    # 格式化状态显示
    case "$status" in
        "SUCCESS")
            status_symbol="✓"
            color="\033[32m"  # 绿色
            ;;
        "FAILED")
            status_symbol="✗"
            color="\033[31m"  # 红色
            ;;
        "SKIPPED")
            status_symbol="○"
            color="\033[33m"  # 黄色
            ;;
        "PENDING")
            status_symbol="?"
            color="\033[37m"  # 白色
            ;;
        *)
            status_symbol="-"
            color="\033[37m"  # 白色
            ;;
    esac

    printf "${color}  [%s] %-30s %s\033[0m\n" "$status_symbol" "$filename" "$description"
done < "$file_status_log"

print_info ""
print_info "状态说明: ✓=成功生成  ✗=生成失败  ○=跳过执行  ?=待处理"
print_info "详细信息请查看: $report_dir/00_inspection_summary.txt"

# 生成Python可读的状态文件
cat > "$report_dir/file_status.json" << EOF
{
  "inspection_time": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "oracle_sid": "$ORACLE_SID",
  "db_model": "$db_model",
  "files": [
EOF

# 添加文件状态信息到JSON
first_entry=true
while IFS=':' read -r filename status description || [ -n "$filename" ]; do
    # 跳过注释行和空行
    if [[ "$filename" =~ ^#.*$ ]] || [[ -z "$filename" ]]; then
        continue
    fi

    # 检查文件是否实际存在
    file_exists="false"
    file_size="0"
    if [ -f "$report_dir/$filename" ]; then
        file_exists="true"
        file_size=$(stat -f%z "$report_dir/$filename" 2>/dev/null || stat -c%s "$report_dir/$filename" 2>/dev/null || echo "0")
    fi

    # 添加逗号分隔符（除了第一个条目）
    if [ "$first_entry" = "true" ]; then
        first_entry=false
    else
        echo "," >> "$report_dir/file_status.json"
    fi

    # 输出JSON格式的文件状态
    printf '    {\n      "filename": "%s",\n      "status": "%s",\n      "description": "%s",\n      "exists": %s,\n      "size": %s\n    }' \
        "$filename" "$status" "$description" "$file_exists" "$file_size" >> "$report_dir/file_status.json"
done < "$file_status_log"

# 结束JSON
cat >> "$report_dir/file_status.json" << EOF
  ]
}
EOF

print_info "状态文件已生成: $report_dir/file_status.json"