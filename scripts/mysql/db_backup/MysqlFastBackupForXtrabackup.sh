#!/bin/bash
#================================================================
# MySQL Fast Backup For XtraBackup - 快速自动化备份脚本
# MySQL Fast Backup For XtraBackup - Automated Backup Script
# 
# 功能 Features：
#   - 全量备份（压缩）Full backup (compressed)
#   - 每日增量备份（压缩）Daily incremental backup (compressed)
#   - 每小时归档日志备份 Hourly archive log backup
#   - 自动清理旧备份 Auto cleanup old backups
#   - 自动检测binlog目录 Auto-detect binlog directory
#
# 使用方法 Usage:
#   ./MysqlFastBackupForXtrabackup.sh backup [full|incremental|archive]  # 执行备份
#   ./MysqlFastBackupForXtrabackup.sh cleanup                             # 执行清理
#   ./MysqlFastBackupForXtrabackup.sh cron                               # 安装cron任务
#   ./MysqlFastBackupForXtrabackup.sh help                               # 显示帮助
#
# 版本 Version: 2.0
#================================================================

set -euo pipefail

# ========================================
# 配置部分 CONFIGURATION
# ========================================

# MySQL配置 MySQL Configuration
MYSQL_CNF="/mysql/data/3306/my.cnf"
MYSQL_USER="root"
MYSQL_PASSWORD="123456"
MYSQL_BIN="/mysql/app/mysql-8.0.35/bin/mysql"
# 可选：手动指定Unix Socket路径；若设置则强制通过Socket连接
# Optional: specify Unix socket path; if set, force socket connection
MYSQL_SOCK="/mysql/data/3306/mysql.sock"

# XtraBackup配置 XtraBackup Configuration  
XTRABACKUP_BIN="/mysql/app/xtrabackup-8.0.35/bin/xtrabackup"
BACKUP_DIR="/mysql/backup"
LOG_DIR="/mysql/backup/logs"

# 保留策略（天数）Retention Policy (days)
FULL_RETENTION_DAYS=30        # 全量备份保留30天
INCR_RETENTION_DAYS=7         # 增量备份保留7天
ARCHIVE_RETENTION_DAYS=3      # 归档备份保留3天

# 性能设置 Performance Settings
PARALLEL_THREADS=4             # 并行线程数
COMPRESS_THREADS=4             # 压缩线程数

# ========================================
# 初始化 INITIALIZATION
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${LOG_DIR}/mysql_fast_backup_$(date '+%Y%m%d').log"

# 创建必要目录 Create necessary directories
mkdir -p "$BACKUP_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "${LOG_DIR}/cron"

# 日志函数 Logging functions
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
}

# 自动获取MySQL binlog目录 Auto-detect MySQL binlog directory
get_mysql_binlog_dir() {
    local binlog_dir=""
    
    # 尝试从MySQL获取log_bin_basename路径 Try to get log_bin_basename from MySQL
    if [[ -n "$MYSQL_PASSWORD" && "$MYSQL_PASSWORD" != "your_password_here" ]]; then
        # 组装mysql连接参数 Build mysql connection args
        local MYSQL_CONN_ARGS=()
        if [[ -n "${MYSQL_SOCK}" ]]; then
            MYSQL_CONN_ARGS=(-S "${MYSQL_SOCK}")
        else
            MYSQL_CONN_ARGS=(-h "${MYSQL_HOST:-localhost}" -P "${MYSQL_PORT:-3306}")
        fi
        # 获取log_bin_basename并提取目录路径
        binlog_dir=$($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" \
            -se "SELECT SUBSTRING_INDEX(@@log_bin_basename, '/', -1 + LENGTH(@@log_bin_basename) - LENGTH(REPLACE(@@log_bin_basename, '/', '')));" 2>/dev/null || true)
        
        # 如果上面的方法失败，尝试获取datadir
        if [[ -z "$binlog_dir" ]]; then
            binlog_dir=$($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" \
                -se "SELECT @@datadir;" 2>/dev/null || true)
        fi
    fi
    
    # 如果从MySQL获取失败，尝试从my.cnf解析
    if [[ -z "$binlog_dir" && -f "$MYSQL_CNF" ]]; then
        # 尝试从my.cnf获取log-bin路径
        local log_bin=$(grep -E "^[[:space:]]*log[-_]bin[[:space:]]*=" "$MYSQL_CNF" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' ')
        if [[ -n "$log_bin" ]]; then
            # 如果是绝对路径，提取目录部分
            if [[ "$log_bin" == /* ]]; then
                binlog_dir=$(dirname "$log_bin")
            else
                # 如果是相对路径，尝试获取datadir
                local datadir=$(grep -E "^[[:space:]]*datadir[[:space:]]*=" "$MYSQL_CNF" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' ')
                if [[ -n "$datadir" ]]; then
                    binlog_dir="$datadir"
                fi
            fi
        fi
        
        # 如果还是没有，直接获取datadir
        if [[ -z "$binlog_dir" ]]; then
            binlog_dir=$(grep -E "^[[:space:]]*datadir[[:space:]]*=" "$MYSQL_CNF" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' ')
        fi
    fi
    
    # 返回结果，如果为空则返回默认值
    echo "${binlog_dir:-/mysql/data/3306/data}"
}

# ========================================
# 备份功能 BACKUP FUNCTIONS
# ========================================

# 查找最新的全量备份 Find latest full backup
find_latest_full_backup() {
    find "$BACKUP_DIR" -maxdepth 1 -type d -name "full_*" 2>/dev/null | sort -r | head -1
}

# 执行全量备份 Perform full backup
perform_full_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="full_${timestamp}"
    local backup_path="${BACKUP_DIR}/${backup_name}"
    
    log_info "开始全量备份 Starting full backup: $backup_name"
    
    mkdir -p "$backup_path"
    
    # 执行备份 Execute backup
    # xtrabackup连接参数（若指定Socket则追加） XtraBackup connection args (append socket if provided)
    local XTRA_SOCKET_ARGS=()
    if [[ -n "${MYSQL_SOCK}" ]]; then
        XTRA_SOCKET_ARGS=(--socket="${MYSQL_SOCK}")
    fi

    if $XTRABACKUP_BIN \
        --defaults-file=$MYSQL_CNF \
        --user=$MYSQL_USER \
        --password=$MYSQL_PASSWORD \
        "${XTRA_SOCKET_ARGS[@]}" \
        --backup \
        --target-dir=$backup_path \
        --compress \
        --compress-threads=$COMPRESS_THREADS \
        --parallel=$PARALLEL_THREADS 2>&1 | tee -a "$LOG_FILE"; then
        
        log_info "全量备份成功 Full backup completed: $backup_name"
        echo "备份大小 Backup size: $(du -sh $backup_path | cut -f1)"
        return 0
    else
        log_error "全量备份失败 Full backup failed: $backup_name"
        rm -rf "$backup_path"
        return 1
    fi
}

# 执行增量备份 Perform incremental backup
perform_incremental_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="incr_${timestamp}"
    local backup_path="${BACKUP_DIR}/${backup_name}"
    
    # 查找基础备份 Find base backup
    local base_backup=$(find_latest_full_backup)
    
    if [[ -z "$base_backup" ]]; then
        log_info "没有找到基础备份，执行全量备份 No base backup found, performing full backup"
        perform_full_backup
        return $?
    fi
    
    log_info "开始增量备份 Starting incremental backup: $backup_name"
    log_info "基础备份 Base backup: $(basename $base_backup)"
    
    mkdir -p "$backup_path"
    
    # 执行备份 Execute backup
    # xtrabackup连接参数（若指定Socket则追加） XtraBackup connection args (append socket if provided)
    local XTRA_SOCKET_ARGS=()
    if [[ -n "${MYSQL_SOCK}" ]]; then
        XTRA_SOCKET_ARGS=(--socket="${MYSQL_SOCK}")
    fi

    if $XTRABACKUP_BIN \
        --defaults-file=$MYSQL_CNF \
        --user=$MYSQL_USER \
        --password=$MYSQL_PASSWORD \
        "${XTRA_SOCKET_ARGS[@]}" \
        --backup \
        --target-dir=$backup_path \
        --incremental-basedir=$base_backup \
        --compress \
        --compress-threads=$COMPRESS_THREADS \
        --parallel=$PARALLEL_THREADS 2>&1 | tee -a "$LOG_FILE"; then
        
        log_info "增量备份成功 Incremental backup completed: $backup_name"
        echo "备份大小 Backup size: $(du -sh $backup_path | cut -f1)"
        return 0
    else
        log_error "增量备份失败 Incremental backup failed: $backup_name"
        rm -rf "$backup_path"
        return 1
    fi
}

# 执行归档日志备份 Perform archive log backup
perform_archive_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local today=$(date '+%Y%m%d')
    local archive_dir="${BACKUP_DIR}/archive_${today}"
    
    log_info "==================== 开始binlog归档和清理任务 ===================="
    log_info "归档目录 Archive directory: $archive_dir"
    
    # 创建归档目录
    mkdir -p "$archive_dir"
    
    # MySQL连接参数
    local MYSQL_CONN_ARGS=()
    if [[ -n "${MYSQL_SOCK}" ]]; then
        MYSQL_CONN_ARGS=(-S "${MYSQL_SOCK}")
    else
        MYSQL_CONN_ARGS=(-h "${MYSQL_HOST:-localhost}" -P "${MYSQL_PORT:-3306}")
    fi
    
    # ========================================
    # 步骤1: SHOW BINARY LOGS 获取文件列表与大小
    # ========================================
    log_info "步骤1: SHOW BINARY LOGS - 获取文件列表与大小"
    
    local -a all_binlogs=()
    local -A binlog_sizes=()
    local total_size=0
    
    # 使用SHOW BINARY LOGS获取完整信息
    while IFS=$'\t' read -r log_name log_size encrypted; do
        [[ -z "$log_name" ]] && continue
        all_binlogs+=("$log_name")
        binlog_sizes["$log_name"]=$log_size
        ((total_size += log_size))
        log_info "  - $log_name ($(numfmt --to=iec $log_size 2>/dev/null || echo "${log_size} bytes"))"
    done < <($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SHOW BINARY LOGS;" 2>/dev/null)
    
    if [[ ${#all_binlogs[@]} -eq 0 ]]; then
        log_info "未开启binlog或无法读取binlog列表"
        return 0
    fi
    
    log_info "找到 ${#all_binlogs[@]} 个binlog文件，总大小: $(numfmt --to=iec $total_size 2>/dev/null || echo "${total_size} bytes")"
    
    # 获取当前正在写入的binlog
    local current_binlog current_pos
    read current_binlog current_pos < <($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SHOW MASTER STATUS;" 2>/dev/null | awk '{print $1" "$2}')
    
    if [[ -z "$current_binlog" ]]; then
        log_error "无法获取当前binlog状态"
        return 1
    fi
    
    log_info "当前正在写入: $current_binlog (位置: $current_pos)"
    
    # 获取datadir路径
    local datadir
    datadir=$($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SELECT @@datadir;" 2>/dev/null)
    datadir="${datadir%/}"
    log_info "数据目录: $datadir"
    
    # ========================================
    # 步骤2: SHOW REPLICA STATUS 检查从库状态
    # ========================================
    log_info "步骤2: SHOW REPLICA STATUS - 检查从库状态"
    
    local oldest_replica_binlog=""
    local has_replica=0
    
    # 尝试获取所有从库的binlog使用情况
    local replica_binlogs=()
    
    # 检查SHOW REPLICA STATUS (MySQL 8.0+)
    while IFS= read -r master_log_file; do
        [[ -n "$master_log_file" ]] && replica_binlogs+=("$master_log_file")
    done < <($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SHOW REPLICA STATUS\G" 2>/dev/null | grep "Master_Log_File:" | awk '{print $2}')
    
    # 兼容旧版本，检查SHOW SLAVE STATUS
    if [[ ${#replica_binlogs[@]} -eq 0 ]]; then
        while IFS= read -r master_log_file; do
            [[ -n "$master_log_file" ]] && replica_binlogs+=("$master_log_file")
        done < <($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SHOW SLAVE STATUS\G" 2>/dev/null | grep "Master_Log_File:" | awk '{print $2}')
    fi
    
    if [[ ${#replica_binlogs[@]} -gt 0 ]]; then
        has_replica=1
        # 找出最早的binlog（序号最小的）
        oldest_replica_binlog=$(printf '%s\n' "${replica_binlogs[@]}" | sort | head -1)
        log_info "检测到从库，最早使用的binlog: $oldest_replica_binlog"
        
        # 显示所有从库的状态
        for replica_binlog in "${replica_binlogs[@]}"; do
            log_info "  从库正在使用: $replica_binlog"
        done
    else
        log_info "未检测到从库配置"
    fi
    
    # ========================================
    # 步骤3: 备份要删除的binlog文件
    # ========================================
    log_info "步骤3: 备份binlog文件（除当前活跃文件外）"
    
    local -a binlogs_to_backup=()
    local last_backup_binlog=""
    
    # 提取binlog序号的函数
    get_binlog_number() {
        local binlog_name="$1"
        echo "${binlog_name##*.}"
    }
    
    # 确定要备份的binlog（所有非活跃的）
    for binlog in "${all_binlogs[@]}"; do
        # 跳过当前正在写入的binlog
        if [[ "$binlog" == "$current_binlog" ]]; then
            log_info "  跳过当前活跃文件: $binlog"
            continue
        fi
        
        # 如果有从库，检查是否仍在被从库使用
        local skip_for_replica=0
        if [[ -n "$oldest_replica_binlog" ]]; then
            local binlog_num=$(get_binlog_number "$binlog")
            local replica_num=$(get_binlog_number "$oldest_replica_binlog")
            
            if [[ $binlog_num -ge $replica_num ]]; then
                skip_for_replica=1
                log_info "  保留 $binlog (从库需要，序号: $binlog_num >= $replica_num)"
            fi
        fi
        
        # 如果不被从库使用，则加入备份列表
        if [[ $skip_for_replica -eq 0 ]]; then
            binlogs_to_backup+=("$binlog")
            last_backup_binlog="$binlog"
            log_info "  待备份: $binlog"
        fi
    done
    
    log_info "总计需要备份 ${#binlogs_to_backup[@]} 个binlog文件"
    
    # 执行备份
    local backed_up_count=0
    local backed_up_size=0
    local -a successfully_backed_binlogs=()
    
    if [[ ${#binlogs_to_backup[@]} -gt 0 ]]; then
        for binlog in "${binlogs_to_backup[@]}"; do
            local src="${datadir}/${binlog}"
            local dst="${archive_dir}/${binlog}"
            
            # 检查是否已经备份过
            if [[ -f "$dst" || -f "${dst}.gz" || -f "${dst}.zst" ]]; then
                log_info "  已存在，跳过: $binlog"
                successfully_backed_binlogs+=("$binlog")
                continue
            fi
            
            # 使用cp备份文件
            if [[ -f "$src" ]]; then
                local file_size_mb=$(( ${binlog_sizes[$binlog]:-0} / 1024 / 1024 ))
                log_info "  正在备份: $binlog (大小: $(numfmt --to=iec ${binlog_sizes[$binlog]:-0} 2>/dev/null || echo "${file_size_mb}MB"))"
                
                # 执行备份
                if cp -p "$src" "$dst"; then
                    log_info "    复制成功"
                    ((++backed_up_count))
                    backed_up_size=$((backed_up_size + ${binlog_sizes[$binlog]:-0}))
                    successfully_backed_binlogs+=("$binlog")
                    
                    # 可选：压缩备份文件
                    local DISABLE_COMPRESS="${DISABLE_COMPRESS:-0}"
                    if [[ "$DISABLE_COMPRESS" == "1" ]]; then
                        log_info "    跳过压缩 (DISABLE_COMPRESS=1)"
                    elif command -v zstd >/dev/null 2>&1; then
                        log_info "    开始压缩 (zstd)..."
                        if zstd -T0 "$dst" 2>&1 | tee -a "$LOG_FILE"; then
                            rm -f "$dst"
                            log_info "    已压缩为: ${binlog}.zst"
                        else
                            log_error "    压缩失败: $binlog (退出码: $?)"
                            log_info "    保留未压缩文件: $dst"
                        fi
                    elif command -v gzip >/dev/null 2>&1; then
                        log_info "    开始压缩 (gzip)..."
                        if gzip "$dst" 2>&1 | tee -a "$LOG_FILE"; then
                            log_info "    已压缩为: ${binlog}.gz"
                        else
                            log_error "    压缩失败: $binlog (退出码: $?)"
                            log_info "    保留未压缩文件: $dst"
                        fi
                    else
                        log_info "    未压缩 (无压缩工具)"
                    fi
                else
                    log_error "  备份失败: $binlog (cp命令失败)"
                    log_error "  请检查:"
                    log_error "    - 磁盘空间: $(df -h "$BACKUP_DIR" | tail -1)"
                    log_error "    - 源文件权限: $(ls -lh "$src")"
                    log_error "    - 目标目录权限: $(ls -ld "$archive_dir")"
                fi
            else
                log_error "  文件不存在: $src"
            fi
        done
        
        log_info "备份完成: 新增 $backed_up_count 个文件，大小: $(numfmt --to=iec $backed_up_size 2>/dev/null || echo "${backed_up_size} bytes")"
        log_info "成功备份总数: ${#successfully_backed_binlogs[@]} 个文件"
    else
        log_info "没有需要备份的binlog文件"
    fi
    
    # 记录备份状态（用于交叉验证）
    local state_file="${LOG_DIR}/last_archived_binlog.state"
    if [[ -n "$last_backup_binlog" ]]; then
        echo "$last_backup_binlog" > "$state_file"
        log_info "更新状态文件: $last_backup_binlog"
    fi
    
    # ========================================
    # 步骤4: PURGE清理已备份的binlog
    # ========================================
    if [[ ${#successfully_backed_binlogs[@]} -gt 0 ]]; then
        log_info "步骤4: PURGE BINARY LOGS - 清理已备份的binlog"
        
        # 找出可以清理到的最后一个binlog
        local purge_to_binlog=""
        for binlog in "${successfully_backed_binlogs[@]}"; do
            purge_to_binlog="$binlog"
        done
        
        if [[ -n "$purge_to_binlog" ]]; then
            # 找到下一个binlog作为PURGE TO的目标
            local purge_to_next=""
            local found=0
            
            for binlog in "${all_binlogs[@]}"; do
                if [[ $found -eq 1 ]]; then
                    purge_to_next="$binlog"
                    break
                fi
                if [[ "$binlog" == "$purge_to_binlog" ]]; then
                    found=1
                fi
            done
            
            if [[ -n "$purge_to_next" ]]; then
                log_info "执行清理命令: PURGE BINARY LOGS TO '$purge_to_next'"
                
                if $MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" \
                    -e "PURGE BINARY LOGS TO '$purge_to_next';" 2>&1; then
                    log_info "清理成功！"
                    
                    # 记录清理信息
                    {
                        echo "timestamp=$timestamp"
                        echo "purged_to=$purge_to_next"
                        echo "purged_count=${#successfully_backed_binlogs[@]}"
                        echo "backed_up_count=$backed_up_count"
                        echo "backed_up_size=$backed_up_size"
                        echo "purged_binlogs:"
                        printf '%s\n' "${successfully_backed_binlogs[@]}"
                    } > "${archive_dir}/.purge_${timestamp}.info"
                    
                    log_info "清理记录已保存到: ${archive_dir}/.purge_${timestamp}.info"
                else
                    log_error "清理失败，请检查权限或手动执行"
                fi
            else
                log_info "无法确定清理边界，跳过PURGE"
            fi
        fi
    else
        log_info "步骤4: 没有已备份的binlog需要清理"
    fi
    
    # ========================================
    # 汇总信息
    # ========================================
    log_info "==================== binlog归档和清理任务完成 ===================="
    
    # 显示当前状态
    local current_binlog_count
    current_binlog_count=$($MYSQL_BIN -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "${MYSQL_CONN_ARGS[@]}" -Nse "SHOW BINARY LOGS;" 2>/dev/null | wc -l)
    
    log_info "当前系统保留binlog数量: $current_binlog_count"
    log_info "归档目录: $archive_dir"
    
    return 0
}

# ========================================
# 清理功能 CLEANUP FUNCTION
# ========================================

perform_cleanup() {
    log_info "开始清理旧备份 Starting cleanup of old backups"
    
    local cleaned_count=0

    # 优先：仅保留按日集中目录，删除同一天内的按小时快照
    # Keep only daily-centralized archive dirs; prune hourly snapshots for days that have centralized binlogs
    local pruned_count=0
    shopt -s nullglob
    for hourly_dir in "${BACKUP_DIR}"/archive_????????_??????; do
        # 提取日期部分 Extract YYYYMMDD
        local base day
        base="$(basename "$hourly_dir")"
        day="${base:8:8}"
        # 当天已存在集中目录且包含binlogs时，删除该小时快照
        if [[ -d "${BACKUP_DIR}/archive_${day}/binlogs" ]]; then
            log_info "删除同日小时归档快照 Removing hourly archive snapshot: ${base}"
            rm -rf -- "$hourly_dir"
            ((cleaned_count++))
            ((pruned_count++))
        fi
    done
    shopt -u nullglob
    if [[ ${pruned_count} -gt 0 ]]; then
        log_info "已按日集中策略裁剪 ${pruned_count} 个小时级归档快照 Pruned ${pruned_count} hourly snapshots (daily-centralized policy)"
    fi
    
    # 清理旧的全量备份 Clean old full backups
    while IFS= read -r backup_dir; do
        log_info "删除旧全量备份 Removing old full backup: $(basename $backup_dir)"
        rm -rf "$backup_dir"
        ((cleaned_count++))
    done < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name "full_*" -mtime +$FULL_RETENTION_DAYS 2>/dev/null)
    
    # 清理旧的增量备份 Clean old incremental backups
    while IFS= read -r backup_dir; do
        log_info "删除旧增量备份 Removing old incremental backup: $(basename $backup_dir)"
        rm -rf "$backup_dir"
        ((cleaned_count++))
    done < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name "incr_*" -mtime +$INCR_RETENTION_DAYS 2>/dev/null)
    
    # 清理旧的归档备份 Clean old archive backups
    while IFS= read -r backup_dir; do
        log_info "删除旧归档备份 Removing old archive backup: $(basename $backup_dir)"
        rm -rf "$backup_dir"
        ((cleaned_count++))
    done < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name "archive_*" -mtime +$ARCHIVE_RETENTION_DAYS 2>/dev/null)
    
    log_info "清理完成，删除了 $cleaned_count 个备份 Cleanup completed, removed $cleaned_count backups"
    
    # 显示磁盘使用情况 Show disk usage
    local disk_usage=$(df -h "$BACKUP_DIR" | awk 'NR==2 {print $5}')
    log_info "备份目录磁盘使用率 Backup directory disk usage: $disk_usage"
}

# ========================================
# 恢复功能 RESTORE FROM ARCHIVE
# ========================================

restore_from_archive() {
    # 默认参数 Defaults
    local DAY=""
    local AUTO_YES=0
    local MYSQL_SOCK_DEFAULT="/mysql/data/3306/mysql.sock"
    local MYSQL_SOCK_INPUT=""
    local MYSQL_HOST_INPUT="localhost"
    local MYSQL_PORT_INPUT="3306"
    local MYSQL_USER_INPUT="${MYSQL_USER:-root}"

    # 解析参数 Parse options
    local OPTIND opt
    while getopts ":d:yS:h:P:u:" opt; do
        case "$opt" in
            d) DAY="$OPTARG" ;;
            y) AUTO_YES=1 ;;
            S) MYSQL_SOCK_INPUT="$OPTARG" ;;
            h) MYSQL_HOST_INPUT="$OPTARG" ;;
            P) MYSQL_PORT_INPUT="$OPTARG" ;;
            u) MYSQL_USER_INPUT="$OPTARG" ;;
            *)
               echo "Usage: $0 restore -d YYYYMMDD [-y] [-S sock|-h host -P port] [-u user]"
               return 1
               ;;
        esac
    done

    if [[ -z "$DAY" ]]; then
        echo "restore: -d YYYYMMDD is required"
        return 1
    fi

    local ARCHIVE_DAY_DIR="${BACKUP_DIR}/archive_${DAY}"
    local BINLOGS_DIR="${ARCHIVE_DAY_DIR}/binlogs"
    if [[ ! -d "$BINLOGS_DIR" ]]; then
        echo "Not found: $BINLOGS_DIR"
        return 1
    fi

    # 选择最新的清单目录 Pick latest manifest
    local latest_manifest_dir
    latest_manifest_dir=$(ls -1d "${ARCHIVE_DAY_DIR}"/[0-9][0-9][0-9][0-9][0-9][0-9] 2>/dev/null | sort | tail -n1 || true)
    if [[ -z "$latest_manifest_dir" ]]; then
        echo "No manifest dirs found under $ARCHIVE_DAY_DIR"
        return 1
    fi

    if [[ ! -f "${latest_manifest_dir}/master_status.env" ]]; then
        echo "Missing master_status.env in $latest_manifest_dir"
        return 1
    fi

    # 读取位点 Read master status
    # shellcheck disable=SC1090
    source "${latest_manifest_dir}/master_status.env"
    if [[ -z "${master_file:-}" || -z "${master_pos:-}" ]]; then
        echo "master_file/master_pos not found in manifest"
        return 1
    fi

    # 构建完整文件列表（排除 .part.） Build binlog list
    local FILES=()
    while IFS= read -r f; do FILES+=("$f"); done < <(ls -1 "${BINLOGS_DIR}"/binlog.* 2>/dev/null | grep -v ".part\." | sort)
    if [[ ${#FILES[@]} -eq 0 ]]; then
        echo "No binlogs found in $BINLOGS_DIR"
        return 1
    fi

    num_from_name(){ awk -F. '{print $NF+0}' <<<"$(basename "$1")"; }
    local start_num
    start_num=$(num_from_name "$master_file")
    local SELECTED=()
    local f bn fnum
    for f in "${FILES[@]}"; do
        bn=$(basename "$f")
        fnum=$(num_from_name "$bn")
        if (( fnum >= start_num )); then
            SELECTED+=("$f")
        fi
    done
    if [[ ${#SELECTED[@]} -eq 0 ]]; then
        echo "No binlogs >= $master_file in $BINLOGS_DIR"
        return 1
    fi

    echo "Restore plan (from ${master_file}:${master_pos}) using ${#SELECTED[@]} file(s):"
    printf '  %s\n' "${SELECTED[@]}"

    # 连接参数 Build mysql flags
    local MYSQL_FLAGS=()
    local sock="${MYSQL_SOCK_INPUT:-${MYSQL_SOCK:-$MYSQL_SOCK_DEFAULT}}"
    if [[ -S "$sock" ]]; then
        MYSQL_FLAGS=(-S "$sock" -u "$MYSQL_USER_INPUT")
        # 密码：推荐用 MYSQL_PWD 环境变量；如需也可改为 -p"$MYSQL_PASSWORD"
    else
        MYSQL_FLAGS=(-h "$MYSQL_HOST_INPUT" -P "$MYSQL_PORT_INPUT" -u "$MYSQL_USER_INPUT")
    fi

    run_mysqlbinlog(){
      local file="$1" start_pos="${2:-}"
      local decmd="" ext="${file##*.}"
      case "$ext" in
        zst) decmd="zstd -dc -- \"$file\"" ;;
        gz)  decmd="zcat -- \"$file\"" ;;
        *)   decmd="cat -- \"$file\"" ;;
      esac
      if [[ -n "$start_pos" ]]; then
        echo "$decmd | mysqlbinlog --start-position=$start_pos - | mysql ${MYSQL_FLAGS[*]}"
        (( AUTO_YES )) && bash -c "$decmd | mysqlbinlog --start-position=$start_pos - | mysql ${MYSQL_FLAGS[*]}"
      else
        echo "$decmd | mysqlbinlog - | mysql ${MYSQL_FLAGS[*]}"
        (( AUTO_YES )) && bash -c "$decmd | mysqlbinlog - | mysql ${MYSQL_FLAGS[*]}"
      fi
    }

    echo ""
    if (( AUTO_YES )); then
      echo "Executing restore..."
    else
      echo "Dry-run only. Add -y to execute."
    fi

    local first=1
    for f in "${SELECTED[@]}"; do
      if (( first )); then
        run_mysqlbinlog "$f" "$master_pos"
        first=0
      else
        run_mysqlbinlog "$f"
      fi
    done

    echo "Done."
}

# ========================================
# CRON设置 CRON SETUP
# ========================================

setup_cron() {
    log_info "设置cron任务 Setting up cron jobs"
    
    # 创建临时cron文件 Create temp cron file
    local temp_cron="/tmp/mysql_fast_backup_cron_$(date +%s)"
    crontab -l 2>/dev/null > "$temp_cron" || true
    
    # 检查是否已存在 Check if already exists
    if grep -q "MysqlFastBackupForXtrabackup.sh" "$temp_cron" 2>/dev/null; then
        log_info "Cron任务已存在 Cron jobs already exist"
        return 0
    fi
    
    # 添加cron任务 Add cron jobs
    cat >> "$temp_cron" <<EOF

# ===== MySQL Fast Backup 自动备份任务 Automated Backup Jobs =====
# 全量备份：每周日凌晨2点 Full backup: Sunday 2 AM
0 2 * * 0 $SCRIPT_DIR/MysqlFastBackupForXtrabackup.sh backup full >> ${LOG_DIR}/cron/full.log 2>&1

# 增量备份：周一至周六凌晨2点 Incremental: Mon-Sat 2 AM  
0 2 * * 1-6 $SCRIPT_DIR/MysqlFastBackupForXtrabackup.sh backup incremental >> ${LOG_DIR}/cron/incremental.log 2>&1

# 归档备份：每小时（除凌晨2点）Archive: Every hour except 2 AM
# 注意：禁用压缩以避免大文件压缩超时 Note: Disable compression to avoid timeout on large files
0 0,1,3-23 * * * DISABLE_COMPRESS=1 $SCRIPT_DIR/MysqlFastBackupForXtrabackup.sh backup archive >> ${LOG_DIR}/cron/archive.log 2>&1

# 清理任务：每天凌晨4点 Cleanup: Daily 4 AM
0 4 * * * $SCRIPT_DIR/MysqlFastBackupForXtrabackup.sh cleanup >> ${LOG_DIR}/cron/cleanup.log 2>&1
# ===== End of MySQL Fast Backup Jobs =====
EOF
    
    # 安装cron Install cron
    crontab "$temp_cron"
    rm -f "$temp_cron"
    
    log_info "Cron任务设置成功 Cron jobs setup completed"
    
    # 显示当前任务 Show current jobs
    echo ""
    echo "当前MySQL Fast Backup cron任务 Current MySQL Fast Backup cron jobs:"
    echo "============================================="
    crontab -l | grep -A 10 "MySQL Fast Backup"
    echo "============================================="
}

# ========================================
# 主程序 MAIN PROGRAM
# ========================================

show_help() {
    cat <<EOF
MySQL Fast Backup For XtraBackup - 快速自动化备份脚本
MySQL Fast Backup For XtraBackup - Automated Backup Script

用法 Usage: $0 <command> [options]

命令 Commands:
  backup [type]   执行备份 Execute backup
    full          - 全量备份 Full backup
    incremental   - 增量备份 Incremental backup
    archive       - 归档日志备份 Archive log backup
    
  cleanup         执行清理 Execute cleanup
  cron            安装cron任务 Install cron jobs
  restore         从归档回放二进制日志 Restore from archived binlogs
  help            显示帮助 Show help

示例 Examples:
  $0 backup full        # 执行全量备份 Execute full backup
  $0 backup incremental # 执行增量备份 Execute incremental backup
  $0 backup archive     # 执行归档备份 Execute archive backup
  DISABLE_COMPRESS=1 $0 backup archive  # 归档备份（不压缩）Archive without compression
  $0 cleanup           # 清理旧备份 Clean old backups
  $0 cron              # 设置自动任务 Setup auto jobs
  $0 restore -d 20250910 -S /mysql/data/3306/mysql.sock -u root   # 预演回放
  MYSQL_PWD=*** $0 restore -d 20250910 -S /mysql/data/3306/mysql.sock -u root -y  # 执行回放

配置信息 Configuration:
  备份目录 Backup Dir: $BACKUP_DIR
  日志目录 Log Dir: $LOG_DIR
  Binlog目录 Binlog Dir: 自动检测 Auto-detect
  保留策略 Retention: 
    - 全量 Full: $FULL_RETENTION_DAYS 天 days
    - 增量 Incr: $INCR_RETENTION_DAYS 天 days
    - 归档 Archive: $ARCHIVE_RETENTION_DAYS 天 days

备份计划 Backup Schedule (cron):
  - 全量备份 Full: 每周日凌晨2点 Sunday 2 AM
  - 增量备份 Incr: 周一至周六凌晨2点 Mon-Sat 2 AM
  - 归档备份 Archive: 每小时执行 Every hour
  - 清理任务 Cleanup: 每天凌晨4点 Daily 4 AM

归档与恢复说明 Archive & Restore:
  - 归档功能说明:
      1) SHOW BINARY LOGS 获取所有binlog列表和大小
      2) SHOW REPLICA STATUS 检查从库状态（如果有）
      3) 备份所有非活跃binlog到 archive_YYYYMMDD/ 目录（跳过当前活跃的和从库需要的）
      4) PURGE BINARY LOGS TO 清理已备份的binlog
  - 归档输出:
      $BACKUP_DIR/archive_YYYYMMDD/            # 按日归档目录
        ├── binlog.000001.zst                  # 压缩的binlog文件
        ├── binlog.000002.gz                   
        ├── .purge_YYYYMMDD_HHMMSS.info        # 清理记录
        └── last_archived_binlog.state          # 状态文件（交叉验证）
  - 快速恢复:
      1) 用最近全量/增量恢复数据目录（xtrabackup --prepare ...）
      2) 使用归档的binlog进行时间点恢复
      3) 使用：$0 restore -d YYYYMMDD [-y] [-S sock|-h host -P port] [-u user]
EOF
}

# 主入口 Main entry
case "${1:-help}" in
    backup)
        case "${2:-}" in
            full)
                perform_full_backup
                ;;
            incremental|incr)
                perform_incremental_backup
                ;;
            archive|arch)
                perform_archive_backup
                ;;
            *)
                echo "错误：请指定备份类型 Error: Please specify backup type"
                echo "用法 Usage: $0 backup [full|incremental|archive]"
                exit 1
                ;;
        esac
        ;;
    restore)
        shift
        restore_from_archive "$@"
        ;;
    cleanup|clean)
        perform_cleanup
        ;;
    cron)
        setup_cron
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "未知命令 Unknown command: $1"
        echo "运行 Run '$0 help' 查看帮助 for help"
        exit 1
        ;;
esac
