#!/bin/bash
################################################################################
# Script Name: OracleFastBackupForRman.sh
# Description: Oracle RMAN fast backup script / Oracle RMAN快速备份脚本
# Author: FastDBCheckRep
# Version: 2.0.0
# Features / 功能特性:
#   - Full backup (Level 0) / 全量备份（0级）
#   - Incremental backup (Level 1) / 增量备份（1级）
#   - Archive log backup / 归档日志备份
#   - Auto cleanup based on retention / 基于保留策略的自动清理
#   - Simple configuration / 简单配置
################################################################################

set -euo pipefail

# ============================== Configuration / 配置 ==============================
# Oracle environment (adjust these for your environment) / Oracle环境
ORACLE_HOME="${ORACLE_HOME:-/oracle/app/oracle/product/11.2.0/db_1}"
ORACLE_SID="${ORACLE_SID:-orcl}"

# Backup directories / 备份目录
BACKUP_BASE="${BACKUP_BASE:-/data/oracle_data/rmanBackup}"
# Normalize trailing slashes / 规范化去尾斜杠
ORACLE_HOME="${ORACLE_HOME%/}"
BACKUP_BASE="${BACKUP_BASE%/}"
BACKUP_DIR="${BACKUP_BASE}/${ORACLE_SID}"
LOG_DIR="${BACKUP_BASE}/logs"

# Retention settings (days) / 保留设置（天）
RETENTION_FULL=30        # Keep full backups for 30 days / 保留全量备份30天
RETENTION_INCR=7         # Keep incremental backups for 7 days / 保留增量备份7天
RETENTION_ARCH=3         # Keep archive log backups for 3 days / 保留归档日志备份3天
RETENTION_OBSOLETE=7     # RMAN recovery window / RMAN恢复窗口

# Backup settings / 备份设置
CHANNELS_FULL=8          # Parallel channels for full backup / 全量备份并行通道数（固定为8）
CHANNELS_INCR=4          # Parallel channels for incremental backup / 增量备份并行通道数（固定为4）
CHANNELS_ARCH=2          # Parallel channels for archive backup / 归档备份并行通道数（固定为2）
MAXPIECESIZE="16G"       # Maximum backup piece size / 最大备份片大小（磁盘建议16G，NFS建议8G）
# ============================== Functions / 函数 ==================================

# Allow multiple SIDs via --sids or ORACLE_SID as CSV / 允许通过 --sids 或 ORACLE_SID 逗号分隔传入多个SID
SID_CSV=""
# SID list and per-SID size map / SID列表与每SID片大小映射
SID_LIST=()
declare -A SID_SIZE_MAP

# Logging function / 日志记录函数
log() {
    local _ts _msg
    _ts="$(date '+%Y-%m-%d %H:%M:%S')"
    _msg="[${_ts}] $*"
    # If a log file is defined, prefer writing to it. Avoid /dev/stdout to prevent permission issues.
    if [[ -n "${LOG_FILE:-}" ]]; then
        # In interactive terminals, also echo to screen; in non‑TTY (cron), append to file only.
        if [ -t 1 ]; then
            echo "${_msg}" | tee -a "${LOG_FILE}" >/dev/null
            echo "${_msg}"
        else
            echo "${_msg}" >>"${LOG_FILE}"
        fi
    else
        # No log file defined yet (e.g., 'cron' setup path) — just print to stdout.
        echo "${_msg}"
    fi
}

# Initialize environment / 初始化环境
init_env() {
    export ORACLE_HOME
    export ORACLE_SID
    export PATH="${ORACLE_HOME}/bin:${PATH}"
    export NLS_DATE_FORMAT='YYYY-MM-DD HH24:MI:SS'
    
    # Create directories / 创建目录
    mkdir -p "${BACKUP_DIR}/full" "${BACKUP_DIR}/incr" "${BACKUP_DIR}/arch" "${LOG_DIR}"
    
    # Set log file / 设置日志文件
    LOG_FILE="${LOG_DIR}/${ORACLE_SID}_$(date +%Y%m%d_%H%M%S).log"
    
    log "=========================================="
    log "Oracle RMAN Backup Script Started / Oracle RMAN备份脚本启动"
    log "ORACLE_HOME: ${ORACLE_HOME}"
    log "ORACLE_SID: ${ORACLE_SID}"
    log "Backup Directory / 备份目录: ${BACKUP_DIR}"
    log "=========================================="
}

# Check Oracle environment / 检查Oracle环境
check_oracle() {
    if [[ ! -x "${ORACLE_HOME}/bin/rman" ]]; then
        log "ERROR: RMAN not found at / 错误：未找到RMAN ${ORACLE_HOME}/bin/rman"
        exit 1
    fi
    if ! command -v sqlplus >/dev/null 2>&1; then
        log "ERROR: sqlplus not found in PATH / 错误：在PATH中未找到sqlplus (ORACLE_HOME=${ORACLE_HOME})"
        exit 1
    fi
    
    if ! sqlplus -s / as sysdba <<< "select status from v\$instance;" &>/dev/null; then
        log "ERROR: Cannot connect to Oracle database / 错误：无法连接到Oracle数据库 ${ORACLE_SID}"
        exit 1
    fi
    
    log "Oracle environment check passed / Oracle环境检查通过"
}

# Auto-detect database configuration / 自动检测数据库配置
get_db_info() {
    local db_info
    local rc=0
    set +e
    db_info=$(sqlplus -s / as sysdba <<EOF
set heading off feedback off pagesize 0 verify off echo off
select 'DB_NAME='||name from v\$database;
select 'LOG_MODE='||log_mode from v\$database;
select 'DB_ROLE='||database_role from v\$database;
exit;
EOF
)
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
        log "WARNING: Failed to query DB info via sqlplus / 警告：通过sqlplus查询数据库信息失败"
        return 0
    fi
    # Safe parse without eval
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local key="${line%%=*}"
        local value="${line#*=}"
        case "$key" in
            DB_NAME) DB_NAME="$value" ;;
            LOG_MODE) LOG_MODE="$value" ;;
            DB_ROLE) DB_ROLE="$value" ;;
        esac
    done <<< "$db_info"
    
    log "Database / 数据库: ${DB_NAME:-unknown}, Mode / 模式: ${LOG_MODE:-unknown}, Role / 角色: ${DB_ROLE:-unknown}"
}

# Full backup (Level 0) / 全量备份（0级）
backup_full() {
    log "Starting FULL backup (Level 0) / 开始全量备份（0级）..."
    
    local backup_tag="FULL_$(date +%Y%m%d_%H%M%S)"
    local backup_path="${BACKUP_DIR}/full"
    local rc=0

    set +e
    rman target / log="${LOG_FILE}" append <<EOF
run {
    configure retention policy to recovery window of ${RETENTION_OBSOLETE} days;
    configure controlfile autobackup on;
    configure device type disk parallelism ${CHANNELS_FULL};
    
    allocate channel ch1 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch2 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch3 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch4 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch5 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch6 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch7 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch8 type disk maxpiecesize ${MAXPIECESIZE};
    
    backup as compressed backupset 
        incremental level 0 
        database 
        tag '${backup_tag}'
        format '${backup_path}/%d_%T_%s_%p.bkp';
    
    backup current controlfile 
        tag '${backup_tag}_CTL'
        format '${backup_path}/ctl_%d_%T_%s.bkp';
    
    backup spfile 
        tag '${backup_tag}_SPF'
        format '${backup_path}/spf_%d_%T_%s.bkp';
    
    release channel ch1;
    release channel ch2;
    release channel ch3;
    release channel ch4;
    release channel ch5;
    release channel ch6;
    release channel ch7;
    release channel ch8;
}
exit;
EOF
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log "Full backup completed successfully / 全量备份成功完成"
        echo "${backup_tag}" > "${BACKUP_DIR}/.last_full_backup"
    else
        log "ERROR: Full backup failed / 错误：全量备份失败"
        exit 1
    fi
}

# Incremental backup (Level 1) / 增量备份（1级）
backup_incremental() {
    log "Starting INCREMENTAL backup (Level 1) / 开始增量备份（1级）..."
    
    # Check if full backup exists / 检查是否存在全量备份
    if [[ ! -f "${BACKUP_DIR}/.last_full_backup" ]]; then
        log "No full backup found, performing full backup first / 未找到全量备份，先执行全量备份"
        backup_full
        return
    fi
    
    local backup_tag="INCR_$(date +%Y%m%d_%H%M%S)"
    local backup_path="${BACKUP_DIR}/incr"
    
    local rc=0

    set +e
    rman target / log="${LOG_FILE}" append <<EOF
run {
    configure device type disk parallelism ${CHANNELS_INCR};
    
    allocate channel ch1 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch2 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch3 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch4 type disk maxpiecesize ${MAXPIECESIZE};
    
    backup as compressed backupset 
        incremental level 1 
        database 
        tag '${backup_tag}'
        format '${backup_path}/%d_%T_%s_%p.bkp';
    
    backup current controlfile 
        tag '${backup_tag}_CTL'
        format '${backup_path}/ctl_%d_%T_%s.bkp';
    
    release channel ch1;
    release channel ch2;
    release channel ch3;
    release channel ch4;
}
exit;
EOF
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log "Incremental backup completed successfully / 增量备份成功完成"
    else
        log "ERROR: Incremental backup failed / 错误：增量备份失败"
        exit 1
    fi
}

# Archive log backup / 归档日志备份
backup_archivelog() {
    log "Starting ARCHIVE LOG backup / 开始归档日志备份..."
    
    local backup_tag="ARCH_$(date +%Y%m%d_%H%M%S)"
    local backup_path="${BACKUP_DIR}/arch"
    # If not in ARCHIVELOG mode, skip gracefully
    if [[ "${LOG_MODE:-}" != "ARCHIVELOG" ]]; then
        log "INFO: Database not in ARCHIVELOG mode, skip archivelog backup / 信息：数据库非归档模式，跳过归档日志备份"
        return 0
    fi
    
    local rc=0

    set +e
    rman target / log="${LOG_FILE}" append <<EOF
run {
    configure device type disk parallelism ${CHANNELS_ARCH};
    
    allocate channel ch1 type disk maxpiecesize ${MAXPIECESIZE};
    allocate channel ch2 type disk maxpiecesize ${MAXPIECESIZE};

    sql 'alter system archive log current';
    crosscheck archivelog all;

    backup as compressed backupset 
        archivelog all 
        not backed up 1 times
        delete input 
        tag '${backup_tag}'
        format '${backup_path}/%d_%T_%s_%p.arc';

    delete noprompt expired archivelog all;
    
    release channel ch1;
    release channel ch2;
}
exit;
EOF
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log "Archive log backup completed successfully / 归档日志备份成功完成"
    else
        log "ERROR: Archive log backup failed / 错误：归档日志备份失败"
        # Print recent RMAN errors to help diagnosis / 打印最近的RMAN错误以便定位
        if [[ -f "${LOG_FILE}" ]]; then
            log "Recent RMAN errors:"
            tail -n 120 "${LOG_FILE}" | grep -E "RMAN-|ORA-" || tail -n 60 "${LOG_FILE}" || true
        fi
        return 1
    fi
}

# Clean old backups / 清理旧备份
cleanup_old_backups() {
    log "Starting cleanup of old backups / 开始清理旧备份..."
    
    # Clean old full backups / 清理旧的全量备份
    if [[ -d "${BACKUP_DIR}/full" ]]; then
        find "${BACKUP_DIR}/full" -name "*.bkp" -type f -mtime +${RETENTION_FULL} -delete 2>/dev/null || true
        log "Cleaned full backups older than ${RETENTION_FULL} days / 已清理${RETENTION_FULL}天前的全量备份"
    fi
    
    # Clean old incremental backups / 清理旧的增量备份
    if [[ -d "${BACKUP_DIR}/incr" ]]; then
        find "${BACKUP_DIR}/incr" -name "*.bkp" -type f -mtime +${RETENTION_INCR} -delete 2>/dev/null || true
        log "Cleaned incremental backups older than ${RETENTION_INCR} days / 已清理${RETENTION_INCR}天前的增量备份"
    fi
    
    # Clean old archive backups / 清理旧的归档备份
    if [[ -d "${BACKUP_DIR}/arch" ]]; then
        find "${BACKUP_DIR}/arch" -name "*.arc" -type f -mtime +${RETENTION_ARCH} -delete 2>/dev/null || true
        log "Cleaned archive backups older than ${RETENTION_ARCH} days / 已清理${RETENTION_ARCH}天前的归档备份"
    fi
    
    # Clean old logs / 清理旧日志
    find "${LOG_DIR}" -name "*.log" -type f -mtime +30 -delete 2>/dev/null || true
    
    # RMAN cleanup obsolete / RMAN清理过期备份
    local rc=0
    set +e
    rman target / log="${LOG_FILE}" append <<EOF
configure retention policy to recovery window of ${RETENTION_OBSOLETE} days;
crosscheck backup;
delete noprompt obsolete;
delete noprompt expired backup;
exit;
EOF
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
        log "WARNING: RMAN cleanup encountered issues / 警告：RMAN清理出现问题"
    fi
    
    log "Cleanup completed / 清理完成"
}

# List backups / 列出备份
list_backups() {
    log "Listing current backups / 列出当前备份..."
    local rc=0
    set +e
    rman target / log="${LOG_FILE}" append <<EOF
list backup summary;
exit;
EOF
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
        log "WARNING: Failed to list backups via RMAN / 警告：RMAN列出备份失败"
        return 1
    fi
}

# Setup cron jobs / 设置定时任务
setup_cron() {
    log "Setting up cron jobs for automatic backups / 设置自动备份的定时任务..."
    # Pre-check: crontab command
    if ! command -v crontab >/dev/null 2>&1; then
        log "ERROR: 'crontab' command not found. Please install cronie package. / 错误：未找到 crontab 命令，请安装 cronie 包"
        return 1
    fi
    # Warn if crond service inactive
    if command -v systemctl >/dev/null 2>&1; then
        if ! systemctl is-active --quiet crond 2>/dev/null; then
            log "WARNING: 'crond' service is not active. Enable with: systemctl enable --now crond / 警告：'crond' 未运行，可执行 systemctl enable --now crond"
        fi
    fi

    # Get script absolute path / 获取脚本绝对路径
    local script_path=$(readlink -f "$0")
    # Create temp cron files / 创建临时cron文件
    local temp_cron_orig
    local temp_cron_new
    temp_cron_orig=$(mktemp /tmp/rman_cron_orig.XXXXXX)
    temp_cron_new=$(mktemp /tmp/rman_cron_new.XXXXXX)
    crontab -l 2>/dev/null > "$temp_cron_orig" || true

    # Base new cron from original with old entries removed / 从原crontab去除旧条目作为基底
    grep -v "OracleFastBackupForRman.sh" "$temp_cron_orig" | \
    grep -v "Oracle RMAN Backup Schedule" > "$temp_cron_new" || true

    # Add cron jobs with Oracle environment for each SID / 为每个SID添加定时任务
    local sids=("$@")
    if [[ ${#sids[@]} -eq 0 ]]; then
        sids=("${ORACLE_SID}")
    fi
    {
        echo ""
        echo "# Oracle RMAN Backup Schedule - Added by OracleFastBackupForRman.sh"
        echo "# Oracle RMAN备份计划 - 由OracleFastBackupForRman.sh添加"
        local entry sid size use_size
        for entry in "${sids[@]}"; do
            sid="${entry%%:*}"
            size="${entry#*:}"
            if [[ "$sid" == "$size" ]]; then
                size=""
            fi
            # Determine size: per-SID > global -m > default 32G for cron
            if [[ -n "$size" ]]; then
                use_size="${size^^}"
            elif [[ -n "${MAXPIECESIZE:-}" ]]; then
                use_size="${MAXPIECESIZE^^}"
            else
                use_size="32G"
            fi
            echo "# Instance: ${sid}"
            echo "# Full backup every Sunday at 2:00 AM / 每周日凌晨2:00全量备份"
            echo "0 2 * * 0 ORACLE_HOME=${ORACLE_HOME} ORACLE_SID=${sid} ${script_path} --backup-dir ${BACKUP_BASE} -m ${use_size} full >/dev/null 2>&1"
            echo "# Incremental backup daily (Mon-Sat) at 2:00 AM / 每天（周一至周六）凌晨2:00增量备份"
            echo "0 2 * * 1-6 ORACLE_HOME=${ORACLE_HOME} ORACLE_SID=${sid} ${script_path} --backup-dir ${BACKUP_BASE} -m ${use_size} incr >/dev/null 2>&1"
            echo "# Archive log backup every 2 hours / 每2小时归档日志备份"
            echo "0 */2 * * * ORACLE_HOME=${ORACLE_HOME} ORACLE_SID=${sid} ${script_path} --backup-dir ${BACKUP_BASE} -m ${use_size} arch >/dev/null 2>&1"
            echo "# Cleanup old backups every Sunday at 4:00 AM / 每周日凌晨4:00清理旧备份"
            echo "0 4 * * 0 ORACLE_HOME=${ORACLE_HOME} ORACLE_SID=${sid} ${script_path} --backup-dir ${BACKUP_BASE} -m ${use_size} cleanup >/dev/null 2>&1"
            echo ""
        done
    } >> "$temp_cron_new"
    
    # Show diff / 显示变更差异
    if command -v diff >/dev/null 2>&1; then
        echo "Proposed crontab changes / 计划写入的crontab变更:"
        diff -u "$temp_cron_orig" "$temp_cron_new" || true
    fi

    # If no change, skip install
    if cmp -s "$temp_cron_orig" "$temp_cron_new" 2>/dev/null; then
        log "Crontab already up to date / crontab 已是最新，无需变更"
        rm -f "$temp_cron_orig" "$temp_cron_new"
        echo "To view cron jobs / 查看定时任务: crontab -l | grep OracleFastBackupForRman.sh"
        return 0
    fi

    # Install new crontab / 安装新的定时任务
    if crontab "$temp_cron_new"; then
        log "Cron jobs installed successfully / 定时任务安装成功"
        echo ""
        echo "Installed cron schedule / 已安装的定时计划:"
        echo "  - Full backup / 全量备份: Sunday 2:00 AM / 周日凌晨2:00"
        echo "  - Incremental backup / 增量备份: Monday-Saturday 2:00 AM / 周一至周六凌晨2:00"
        echo "  - Archive log backup / 归档日志备份: Every 2 hours / 每2小时"
        echo "  - Cleanup / 清理: Sunday 4:00 AM / 周日凌晨4:00"
        echo ""
        echo "To view cron jobs / 查看定时任务: crontab -l | grep OracleFastBackupForRman.sh"
        echo "To remove cron jobs / 移除定时任务: $0 remove-cron"
    else
        log "ERROR: Failed to install cron jobs / 错误：安装定时任务失败"
        rm -f "$temp_cron_orig" "$temp_cron_new"
        return 1
    fi
    
    # Verify presence / 校验安装
    if ! crontab -l 2>/dev/null | grep -q "OracleFastBackupForRman.sh"; then
        log "WARNING: Cron jobs not found after installation / 警告：安装后未在crontab中找到相关条目"
    fi

    rm -f "$temp_cron_orig" "$temp_cron_new"
}

# Remove cron jobs / 移除定时任务
remove_cron() {
    log "Removing cron jobs / 移除定时任务..."
    # Pre-check: crontab command
    if ! command -v crontab >/dev/null 2>&1; then
        log "ERROR: 'crontab' command not found. Please install cronie package. / 错误：未找到 crontab 命令，请安装 cronie 包"
        return 1
    fi
    
    local temp_cron_orig
    local temp_cron_new
    temp_cron_orig=$(mktemp /tmp/rman_cron_orig.XXXXXX)
    temp_cron_new=$(mktemp /tmp/rman_cron_new.XXXXXX)
    crontab -l 2>/dev/null > "$temp_cron_orig" || true
    
    if ! grep -q "OracleFastBackupForRman.sh" "$temp_cron_orig" 2>/dev/null; then
        log "No cron jobs found for OracleFastBackupForRman.sh / 未找到OracleFastBackupForRman.sh的定时任务"
        rm -f "$temp_cron_orig" "$temp_cron_new"
        return 0
    fi
    
    # Remove entries / 移除条目
    grep -v "OracleFastBackupForRman.sh" "$temp_cron_orig" | \
    grep -v "Oracle RMAN Backup Schedule" > "$temp_cron_new" || true

    # Show diff / 显示变更差异
    if command -v diff >/dev/null 2>&1; then
        echo "Crontab changes to remove entries / 将要移除的crontab差异:"
        diff -u "$temp_cron_orig" "$temp_cron_new" || true
    fi

    if crontab "$temp_cron_new"; then
        log "Cron jobs removed successfully / 定时任务移除成功"
    else
        log "ERROR: Failed to remove cron jobs / 错误：移除定时任务失败"
        rm -f "$temp_cron_orig" "$temp_cron_new"
        return 1
    fi
    
    # Verify removal / 校验移除
    if crontab -l 2>/dev/null | grep -q "OracleFastBackupForRman.sh"; then
        log "WARNING: Some cron entries still remain / 警告：仍有部分定时任务残留"
    fi

    rm -f "$temp_cron_orig" "$temp_cron_new"
}

# Show usage / 显示使用说明
usage() {
    cat <<EOF
Usage / 用法: $0 [OPTIONS] COMMAND

Oracle Fast Backup Script for RMAN / Oracle RMAN快速备份脚本

COMMANDS / 命令:
    full            Perform full backup (Level 0) / 执行全量备份（0级）
    incr            Perform incremental backup (Level 1) / 执行增量备份（1级）
    arch            Backup archive logs / 备份归档日志
    cleanup         Clean old backups based on retention / 基于保留策略清理旧备份
    list            List current backups / 列出当前备份
    cron            Setup automatic backup schedule via cron / 通过cron设置自动备份计划
    remove-cron     Remove cron jobs for automatic backups / 移除自动备份的定时任务
    help            Show this help message / 显示此帮助信息

OPTIONS / 选项:
    -h, --oracle-home PATH    Oracle home directory / Oracle主目录 (default: ${ORACLE_HOME})
    -s, --sid SID            Oracle SID / Oracle实例标识 (default: ${ORACLE_SID})
    -S, --sids "SID1[:SIZE],SID2[:SIZE]"  Multiple SIDs (CSV), optional per-SID max piece size / 多个SID（逗号分隔），可选每SID备份片大小
    -b, --backup-dir PATH    Backup directory / 备份目录 (default: ${BACKUP_BASE})
    -m, --max-piece-size SZ  RMAN maxpiecesize, e.g. 8G/16G/32G (default: ${MAXPIECESIZE})

EXAMPLES / 示例:
    # Full backup / 全量备份
    $0 full
    
    # Incremental backup / 增量备份
    $0 incr
    
    # Archive log backup / 归档日志备份
    $0 arch
    
    # Cleanup old backups / 清理旧备份
    $0 cleanup
    
    # Setup automatic backups / 设置自动备份
    $0 cron
    
    # Remove automatic backups / 移除自动备份
    $0 remove-cron
    
    # Full backup with custom settings / 使用自定义设置的全量备份
    $0 --oracle-home /u01/app/oracle --sid PROD full
    $0 --sid ORCL1 -m 32G full
    $0 --sid ORCL1 -b /oracle/backup incr
    
    # Multiple SIDs / 多实例
    $0 --sids "ORCL1,ORCL2" incr
    # or / 或
    ORACLE_SID="ORCL1,ORCL2" $0 arch
    
    # Multiple SIDs with per-SID size (cron/list/exec supported) / 多实例且指定每SID片大小
    $0 --sids "ORCL1:32G,ORCL2:8G" cron
    $0 --sids "ORCL1:32G ORCL2:8G" list

    # Show help / 显示帮助
    $0 help

AUTOMATIC BACKUP SCHEDULE / 自动备份计划 (when using 'cron' command / 使用'cron'命令时):
    - Full backup / 全量备份: Sunday 2:00 AM / 周日凌晨2:00
    - Incremental backup / 增量备份: Monday-Saturday 2:00 AM / 周一至周六凌晨2:00
    - Archive log backup / 归档日志备份: Every 2 hours / 每2小时
    - Cleanup / 清理: Sunday 4:00 AM / 周日凌晨4:00

NOTES / 注意:
    - MAXPIECESIZE 默认 16G；磁盘场景建议 16G–32G，NFS 建议 8G–16G。
    - 可通过修改脚本顶部变量 MAXPIECESIZE 调整；单位不区分大小写（如 16G/16g）。
    - 通道数固定：全量8、增量4、归档2；TB 级库可结合更大的 MAXPIECESIZE 降低备份片数量。
    - 使用 --sids 生成 cron 时，可用 "SID:SIZE" 指定每实例片大小；未指定的实例默认 32G（磁盘场景）。

EOF
}

# ============================== Helpers / 助手函数 ====================================

# Build SID list from --sids or ORACLE_SID / 从 --sids 或 ORACLE_SID 构建SID列表
build_sid_list() {
    local src
    if [[ -n "${SID_CSV}" ]]; then
        src="${SID_CSV}"
    else
        src="${ORACLE_SID}"
    fi
    # Normalize separators to space and split / 规范化分隔符为空格并拆分
    local norm
    norm=$(echo "$src" | tr ',;' ' ')
    SID_LIST=()
    SID_SIZE_MAP=()
    local token sid size
    for token in $norm; do
        [[ -z "$token" ]] && continue
        sid="${token%%:*}"
        size="${token#*:}"
        # If no colon, size==token; treat as empty
        if [[ "$sid" == "$size" ]]; then
            size=""
        fi
        SID_LIST+=("$sid")
        if [[ -n "$size" ]]; then
            # Uppercase size unify units
            SID_SIZE_MAP["$sid"]="${size^^}"
        fi
    done
}

# Run command for a single SID in subshell to isolate failures / 在子shell中按单个SID执行，隔离失败
run_for_sid() {
    local cmd="$1" sid="$2"
    (
        export ORACLE_SID="$sid"
        local base="${BACKUP_BASE%/}"
        BACKUP_DIR="${base}/${ORACLE_SID}"
        # Apply per-SID piece size if provided in --sids (overrides global) / 若指定了每SID片大小则覆盖
        local sid_size="${SID_SIZE_MAP[$sid]:-}"
        if [[ -n "$sid_size" ]]; then
            MAXPIECESIZE="$sid_size"
        fi
        init_env
        # check_oracle may exit on failure; that's fine in subshell / 失败时子shell退出
        check_oracle
        get_db_info
        case "$cmd" in
            full)
                backup_full
                cleanup_old_backups
                ;;
            incr)
                backup_incremental
                ;;
            arch)
                backup_archivelog
                ;;
            cleanup)
                cleanup_old_backups
                ;;
            list)
                list_backups
                ;;
        esac
    )
}

# Execute for all SIDs / 为所有SID执行
execute_for_sids() {
    local cmd="$1"
    build_sid_list
    local sid
    local failures=0
    for sid in "${SID_LIST[@]}"; do
        log "---- SID: ${sid} | Command: ${cmd} ----"
        if run_for_sid "$cmd" "$sid"; then
            log "SID ${sid}: ${cmd} done"
        else
            log "WARNING: SID ${sid}: ${cmd} failed"
            failures=$((failures+1))
        fi
    done
    if [[ $failures -gt 0 ]]; then
        log "Completed with ${failures} failure(s) across SIDs / 多实例执行完成，其中 ${failures} 个失败"
    fi
}

# ============================== Main / 主程序 =======================================

# Parse command line options / 解析命令行选项
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--oracle-home)
            ORACLE_HOME="${2%/}"
            shift 2
            ;;
        -s|--sid)
            ORACLE_SID="$2"
            shift 2
            ;;
        -S|--sids)
            SID_CSV="$2"
            shift 2
            ;;
        -b|--backup-dir)
            BACKUP_BASE="${2%/}"
            BACKUP_DIR="${BACKUP_BASE}/${ORACLE_SID}"
            LOG_DIR="${BACKUP_BASE}/logs"
            shift 2
            ;;
        -m|--max-piece-size)
            # Uppercase units for consistency
            MAXPIECESIZE="${2^^}"
            shift 2
            ;;
        full|incr|arch|cleanup|list|cron|remove-cron|help)
            COMMAND="$1"
            shift
            break
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Set default command / 设置默认命令
COMMAND="${COMMAND:-help}"

# Execute command / 执行命令
case "${COMMAND}" in
    help)
        usage
        exit 0
        ;;
    
    full)
        execute_for_sids full
        ;;
    
    incr)
        execute_for_sids incr
        ;;
    
    arch)
        execute_for_sids arch
        ;;
    
    cleanup)
        execute_for_sids cleanup
        ;;
    
    list)
        execute_for_sids list
        ;;
    
    cron)
        build_sid_list
        setup_cron "${SID_LIST[@]}"
        ;;
    
    remove-cron)
        remove_cron
        ;;
    
    *)
        echo "Invalid command: ${COMMAND}"
        usage
        exit 1
        ;;
esac

log "=========================================="
log "Backup operation completed / 备份操作完成"
log "=========================================="

exit 0
