#!/bin/bash
#================================================================
# MySQL db_check 巡检脚本
# 版本: v2.0
# 作者: yzj（须佐）
# 说明: 需要以root用户执行，自动收集MySQL数据库和系统相关信息
# 支持单机模式（MySQL主从复制和集群模式待后续实现）
#
# 使用示例:
# TCP连接:  ./mysql_inspection.sh -outdir "/tmp" -db_model "one" -mysql_user "root" -mysql_pass "123456" -mysql_tcp_conn -host "192.168.1.100" -port "3306"
# Socket连接: ./mysql_inspection.sh -outdir "/tmp" -db_model "one" -mysql_user "root" -mysql_pass "123456" -mysql_sock_conn -sock "/mysql/data/3306/mysql.sock"
#================================================================

set -e

# 设置字符编码环境变量，确保中文输出正确
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

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
outdir=""
db_model=""
# MySQL连接参数
MYSQL_USER=""
MYSQL_PASS=""
MYSQL_HOST=""
MYSQL_PORT=""
MYSQL_SOCK=""
# 连接类型标志
USE_TCP=0
USE_SOCK=0

while [[ $# -gt 0 ]]; do
    case $1 in
        -mysql_user)
            MYSQL_USER="$2"
            shift 2
            ;;
        -mysql_pass)
            MYSQL_PASS="$2"
            shift 2
            ;;
        -mysql_tcp_conn)
            USE_TCP=1
            shift
            ;;
        -mysql_sock_conn)
            USE_SOCK=1
            shift
            ;;
        -host)
            MYSQL_HOST="$2"
            shift 2
            ;;
        -port)
            MYSQL_PORT="$2"
            shift 2
            ;;
        -sock)
            MYSQL_SOCK="$2"
            shift 2
            ;;
        -outdir)
            outdir="$2"
            shift 2
            ;;
        -db_model)
            db_model="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 -outdir <OUTPUT_DIR> -db_model <one> [MySQL连接参数]"
            echo ""
            echo "必需参数:"
            echo "  -outdir              输出目录的基础路径"
            echo "  -db_model            数据库模式: one(单机)"
            echo ""
            echo "MySQL连接参数（健康检查需要）:"
            echo "  -mysql_user          MySQL数据库用户名"
            echo "  -mysql_pass          MySQL数据库密码"
            echo ""
            echo "连接方式（二选一）:"
            echo "  TCP连接:"
            echo "    -mysql_tcp_conn    使用TCP连接"
            echo "    -host              MySQL主机地址"
            echo "    -port              MySQL端口号"
            echo ""
            echo "  Socket连接:"
            echo "    -mysql_sock_conn   使用Socket连接"
            echo "    -sock              Socket文件路径"
            echo ""
            echo "示例:"
            echo "  仅收集系统信息:"
            echo "    $0 -outdir /tmp -db_model one"
            echo ""
            echo "  TCP连接:"
            echo "    $0 -outdir /tmp -db_model one -mysql_user root -mysql_pass 123456 \\"
            echo "       -mysql_tcp_conn -host 192.168.1.100 -port 3306"
            echo ""
            echo "  Socket连接:"
            echo "    $0 -outdir /tmp -db_model one -mysql_user root -mysql_pass 123456 \\"
            echo "       -mysql_sock_conn -sock /mysql/data/3306/mysql.sock"
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
if [ -z "$outdir" ] || [ -z "$db_model" ]; then
    print_error "缺少必需参数"
    echo ""
    echo "用法: $0 -outdir <OUTPUT_DIR> -db_model <one> [MySQL连接参数]"
    echo ""
    echo "必需参数:"
    echo "  -outdir      输出目录的基础路径"
    echo "  -db_model    数据库模式: one(单机)"
    echo ""
    echo "可选MySQL连接参数（用于健康检查）:"
    echo "  -mysql_user  MySQL用户名"
    echo "  -mysql_pass  MySQL密码"
    echo ""
    echo "  TCP连接方式:"
    echo "    -mysql_tcp_conn  使用TCP连接"
    echo "    -host           主机地址"
    echo "    -port           端口号"
    echo ""
    echo "  Socket连接方式:"
    echo "    -mysql_sock_conn 使用Socket连接"
    echo "    -sock           Socket文件路径"
    echo ""
    echo "示例:"
    echo "  1. 仅收集系统信息:"
    echo "     $0 -outdir /tmp -db_model one"
    echo ""
    echo "  2. TCP连接并执行健康检查:"
    echo "     $0 -outdir /tmp -db_model one -mysql_user root -mysql_pass 123456 \\"
    echo "        -mysql_tcp_conn -host 192.168.1.100 -port 3306"
    echo ""
    echo "  3. Socket连接并执行健康检查:"
    echo "     $0 -outdir /tmp -db_model one -mysql_user root -mysql_pass 123456 \\"
    echo "        -mysql_sock_conn -sock /mysql/data/3306/mysql.sock"
    echo ""
    echo "使用 -h 或 --help 查看完整帮助"
    exit 1
fi

# 验证db_model参数（使用 "one" 而不是 "single"）
if [[ "$db_model" != "one" ]]; then
    print_error "无效的 db_model 参数: $db_model"
    print_error "db_model 必须是 'one' (单机模式)"
    exit 1
fi

# 验证MySQL连接参数逻辑
if [ -n "$MYSQL_USER" ] || [ -n "$MYSQL_PASS" ]; then
    # 如果提供了用户名或密码，必须两个都提供
    if [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_PASS" ]; then
        print_error "MySQL用户名和密码必须同时提供"
        exit 1
    fi

    # 检查连接方式互斥
    if [ $USE_TCP -eq 1 ] && [ $USE_SOCK -eq 1 ]; then
        print_error "不能同时使用TCP和Socket连接方式，请选择其一"
        exit 1
    fi

    # 如果选择了连接方式，检查相应参数
    if [ $USE_TCP -eq 1 ]; then
        if [ -z "$MYSQL_HOST" ] || [ -z "$MYSQL_PORT" ]; then
            print_error "使用TCP连接时，必须提供 -host 和 -port 参数"
            exit 1
        fi
    elif [ $USE_SOCK -eq 1 ]; then
        if [ -z "$MYSQL_SOCK" ]; then
            print_error "使用Socket连接时，必须提供 -sock 参数"
            exit 1
        fi
        # 检查socket文件是否存在
        if [ ! -S "$MYSQL_SOCK" ]; then
            print_error "Socket文件不存在或不是有效的socket: $MYSQL_SOCK"
            exit 1
        fi
    else
        print_error "必须指定连接方式: -mysql_tcp_conn 或 -mysql_sock_conn"
        exit 1
    fi
fi

# 构建MySQL连接命令
MYSQL_CMD=""
if [ -n "$MYSQL_USER" ] && [ -n "$MYSQL_PASS" ]; then
    MYSQL_CMD="mysql --default-character-set=utf8mb4 --table -r --unbuffered --skip-pager"
    MYSQL_CMD="$MYSQL_CMD -u$MYSQL_USER"

    # 使用环境变量传递密码，避免引号问题
    export MYSQL_PWD="$MYSQL_PASS"

    if [ $USE_TCP -eq 1 ]; then
        MYSQL_CMD="$MYSQL_CMD -h$MYSQL_HOST -P$MYSQL_PORT"
        print_info "使用TCP连接: $MYSQL_HOST:$MYSQL_PORT"
    else
        MYSQL_CMD="$MYSQL_CMD -S$MYSQL_SOCK"
        print_info "使用Socket连接: $MYSQL_SOCK"
    fi
fi

# 处理路径，避免双斜杠
if [[ "$outdir" == */ ]]; then
    export report_dir="${outdir}$(hostname)_mysql_$(date +'%Y%m%d')"
else
    export report_dir="$outdir/$(hostname)_mysql_$(date +'%Y%m%d')"
fi

# 检查是否为root用户
if [[ $EUID -ne 0 ]]; then
   print_error "此脚本必须以root用户执行"
   exit 1
fi

# MySQL连接测试
if [ -n "$MYSQL_CMD" ]; then
    print_info "测试MySQL连接..."
    if ! $MYSQL_CMD -e "SELECT 1" &>/dev/null; then
        print_error "无法连接到MySQL数据库，请检查连接参数"
        exit 1
    else
        print_info "MySQL连接成功"
    fi
else
    print_info "未提供MySQL连接参数，仅收集系统信息"
fi

# 创建报告目录
print_info "创建巡检报告目录: $report_dir"
mkdir -p "$report_dir"
chmod 755 "$report_dir"

# 初始化文件状态跟踪
export file_status_log="$report_dir/.file_generation_status"
cat > "$file_status_log" << EOF
# 文件生成状态跟踪 (格式: filename:status:description)
# status: SUCCESS/FAILED/SKIPPED
01_system_info.txt:PENDING:系统信息
02_hardware_info.json:PENDING:硬件信息(JSON格式)
03_xtrabackup_backup.txt:PENDING:XtraBackup备份目录清单
10_sar_report.txt:PENDING:系统资源监控
00_inspection_summary.txt:PENDING:巡检汇总
04_health_check.txt:PENDING:MySQL健康检查
EOF

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

# 收集函数定义
collect_system_info() {
    local output_file="$report_dir/01_system_info.txt"
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
        echo "--- MySQL用户限制 ---"
        if id mysql &>/dev/null; then
            su - mysql -c "ulimit -a" 2>/dev/null || echo "无法获取mysql用户的资源限制"
        else
            echo "未找到mysql用户"
        fi
        echo ""
        echo "--- /etc/security/limits.conf 中mysql相关配置 ---"
        grep -i mysql /etc/security/limits.conf 2>/dev/null || echo "未找到mysql相关配置"
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
    } > "$output_file"

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        update_file_status "01_system_info.txt" "SUCCESS" "系统信息"
        print_info "系统信息已保存到: $output_file"
    else
        update_file_status "01_system_info.txt" "FAILED" "系统信息"
        print_error "系统信息收集失败"
    fi
}

collect_hardware_info() {
    local output_file="$report_dir/02_hardware_info.json"
    print_info "收集硬件信息..."

    {
        echo "{"

        echo '  "cpu": {'
        echo '    "model": "'$(grep "model name" /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | sed 's/^ *//' | sed 's/"/\\"/g')'",'
        echo '    "cores": '$(nproc 2>/dev/null || echo 0)','
        echo '    "physical_cores": '$(grep -i "physical id" /proc/cpuinfo 2>/dev/null | sort -u | wc -l | awk '{print $1}')','
        echo '    "logical_cores": '$(grep -i "^processor" /proc/cpuinfo 2>/dev/null | wc -l | awk '{print $1}')
        if command -v numactl &>/dev/null; then
            numa_nodes=$(numactl --hardware 2>/dev/null | grep "available:" | awk '{print $2}' || echo "0")
        else
            numa_nodes=0
        fi
        echo '    ,"numa_nodes": '$numa_nodes
        echo '  },'

        echo '  "memory": {'
        total_mem_kb=$(grep -i MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
        total_mem_gb=$(( ${total_mem_kb:-0} / 1024 / 1024 ))
        echo '    "total_kb": '${total_mem_kb:-0}','
        echo '    "total_gb": '${total_mem_gb:-0}
        echo '  },'

        echo '  "disk_space": ['
        first=1
        df -h 2>/dev/null | grep -v "Filesystem" | while IFS= read -r line; do
            fs=$(echo "$line" | awk '{print $1}')
            size=$(echo "$line" | awk '{print $2}')
            used=$(echo "$line" | awk '{print $3}')
            avail=$(echo "$line" | awk '{print $4}')
            usep=$(echo "$line" | awk '{print $5}')
            mnt=$(echo "$line" | awk '{print $6}')
            if [ $first -eq 1 ]; then
                first=0
            else
                echo ","
            fi
            echo -n '    {"filesystem": "'$fs'", "size": "'$size'", "used": "'$used'", "available": "'$avail'", "use_percent": "'$usep'", "mount_point": "'$mnt'"}'
        done
        echo ''
        echo '  ]'

        echo "}"
    } > "$output_file"

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        update_file_status "02_hardware_info.json" "SUCCESS" "硬件信息(JSON格式)"
        print_info "硬件信息已保存到: $output_file"
    else
        update_file_status "02_hardware_info.json" "FAILED" "硬件信息(JSON格式)"
        print_error "硬件信息收集失败"
    fi
}

collect_sar_report() {
    local output_file="$report_dir/10_sar_report.txt"
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
    } > "$output_file"

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        update_file_status "10_sar_report.txt" "SUCCESS" "系统资源监控"
    else
        update_file_status "10_sar_report.txt" "FAILED" "系统资源监控"
    fi
}

# XtraBackup 备份部署与文件清单收集
collect_xtrabackup_backup_info() {
    local output_file="$report_dir/03_xtrabackup_backup.txt"
    print_info "检测并收集XtraBackup备份信息..."

    # 获取crontab配置，查找MysqlFastBackupForXtrabackup.sh的调用
    local cron_content
    cron_content=$(crontab -l 2>/dev/null || true)

    local script_path
    script_path=$(echo "$cron_content" | awk '{for(i=1;i<=NF;i++){ if($i ~ /MysqlFastBackupForXtrabackup\.sh$/){print $i; exit}}}')

    if [ -z "$script_path" ]; then
        # 尝试默认路径
        if [ -f "/mysql/scripts/MysqlFastBackupForXtrabackup.sh" ]; then
            script_path="/mysql/scripts/MysqlFastBackupForXtrabackup.sh"
        fi
    fi

    if [ -z "$script_path" ] || [ ! -f "$script_path" ]; then
        print_warning "未检测到已部署的MysqlFastBackupForXtrabackup.sh或crontab任务"
        update_file_status "03_xtrabackup_backup.txt" "SKIPPED" "未检测到Fast Backup计划任务"
        return
    fi

    # 从脚本中解析BACKUP_DIR
    local backup_dir_line backup_dir
    backup_dir_line=$(grep -E '^[[:space:]]*BACKUP_DIR[[:space:]]*=' "$script_path" 2>/dev/null | tail -1 || true)
    backup_dir=$(echo "$backup_dir_line" | sed -E "s/^[[:space:]]*BACKUP_DIR[[:space:]]*=//" | sed -E "s/^\"(.*)\"$/\1/; s/^'(.*)'$/\1/")

    if [ -z "$backup_dir" ] || [ ! -d "$backup_dir" ]; then
        print_warning "无法确定BACKUP_DIR或目录不存在: ${backup_dir:-<empty>}"
        update_file_status "03_xtrabackup_backup.txt" "SKIPPED" "未找到备份目录"
        return
    fi

    # 生成备份文件清单
    {
        echo "===== MySQL Fast Backup (XtraBackup) 检测 ====="
        echo "检测时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "脚本路径: $script_path"
        echo "BACKUP_DIR: $backup_dir"
        echo ""
        echo "===== 备份目录容量与时间 (按大小倒序) ====="
        # GNU du支持 --time/--time-style；若不支持则降级为ls
        if du --time "$backup_dir" >/dev/null 2>&1; then
            ( cd "$backup_dir" && du -sh --time --time-style=+'%Y-%m-%d %H:%M:%S' ./* 2>/dev/null | sort -hr )
        else
            ( cd "$backup_dir" && ls -lsh --time-style=+'%Y-%m-%d %H:%M:%S' 2>/dev/null || ls -lsh 2>/dev/null )
        fi

        echo ""
        echo "===== Crontab 自动备份任务配置 ====="
        # 筛选出包含 MysqlFastBackupForXtrabackup.sh 的 crontab 任务
        local mysql_backup_cron
        mysql_backup_cron=$(crontab -l 2>/dev/null | grep -E "MysqlFastBackupForXtrabackup\.sh|MySQL Fast Backup" || true)

        if [ -n "$mysql_backup_cron" ]; then
            echo "$mysql_backup_cron"
        else
            echo "未在 crontab 中找到 MySQL 自动备份任务"
        fi
    } > "$output_file"

    if [ -s "$output_file" ]; then
        update_file_status "03_xtrabackup_backup.txt" "SUCCESS" "XtraBackup备份目录清单"
        print_info "XtraBackup备份清单已保存到: $output_file"
    else
        update_file_status "03_xtrabackup_backup.txt" "FAILED" "XtraBackup备份目录清单"
        print_error "生成XtraBackup备份清单失败"
    fi
}

# MySQL健康检查函数
collect_mysql_health_check() {
    local output_file="$report_dir/04_health_check.txt"
    local error_file="$report_dir/04_health_check.err"

    if [ -z "$MYSQL_CMD" ]; then
        print_warning "未提供MySQL连接参数，跳过健康检查"
        update_file_status "04_health_check.txt" "SKIPPED" "未提供MySQL连接参数"
        return
    fi

    print_info "执行MySQL健康检查..."

    # 先清空输出与错误文件（后面统一用 >> 追加）
    : > "$output_file"
    : > "$error_file"

    # 1) 用 --force 让 mysql 遇错继续；2) 放进 if/! 里避免 set -e 直接中断
    if ! $MYSQL_CMD --force --line-numbers >> "$output_file" 2>> "$error_file" << 'EOSQL'
-- ================================================================
-- MySQL Health Check SQL Script
-- 版本: v2.0
-- 作者: yzj (须佐)
-- 说明: MySQL数据库健康检查SQL脚本，用于收集数据库状态和性能信息
-- ================================================================

-- 设置输出格式
\! echo "=========================================="
\! echo "MySQL Database Health Check Report"
\! echo "=========================================="
\! echo ""

-- ==============================================================================
-- 第一部分：数据库基础参数信息 (Database Basic Parameters)
-- ==============================================================================

\! echo "==================== DATABASE BASIC PARAMETERS ===================="
\! echo ""

-- A1. 数据库实例基本信息
\! echo "[DB_BASIC_INFO_START]"
\! echo "A1. 数据库实例基本信息"
SELECT
    @@hostname AS 'HOSTNAME',
    @@port AS 'PORT',
    @@version AS 'VERSION',
    @@version_comment AS 'VERSION_COMMENT',
    @@version_compile_os AS 'COMPILE_OS',
    @@version_compile_machine AS 'COMPILE_MACHINE',
    NOW() AS 'CHECK_TIME',
    VARIABLE_VALUE AS 'UPTIME_SECONDS',
    CONCAT(FLOOR(VARIABLE_VALUE/86400), ' days ',
           FLOOR((VARIABLE_VALUE%86400)/3600), ' hours ',
           FLOOR((VARIABLE_VALUE%3600)/60), ' minutes') AS 'UPTIME_FORMATTED'
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Uptime';

-- A2. 数据库服务信息
\! echo ""
\! echo "A2. 数据库连接和用户信息"
SELECT
    USER() AS 'CURRENT_USER',
    CURRENT_USER() AS 'AUTHENTICATED_USER',
    CONNECTION_ID() AS 'CONNECTION_ID',
    DATABASE() AS 'CURRENT_DATABASE',
    @@max_connections AS 'MAX_CONNECTIONS',
    (SELECT COUNT(*) FROM information_schema.processlist) AS 'CURRENT_CONNECTIONS',
    @@max_user_connections AS 'MAX_USER_CONNECTIONS';

-- A3. 数据库字符集信息
\! echo ""
\! echo "A3. 数据库字符集信息"
SELECT
    @@character_set_server AS 'SERVER_CHARSET',
    @@collation_server AS 'SERVER_COLLATION',
    @@character_set_database AS 'DATABASE_CHARSET',
    @@collation_database AS 'DATABASE_COLLATION',
    @@character_set_client AS 'CLIENT_CHARSET',
    @@character_set_connection AS 'CONNECTION_CHARSET';

-- A4. 数据库模式信息
\! echo ""
\! echo "A4. 数据库模式和状态"
SELECT
    @@sql_mode AS 'SQL_MODE',
    @@autocommit AS 'AUTOCOMMIT',
    @@transaction_isolation AS 'TRANSACTION_ISOLATION',
    @@read_only AS 'READ_ONLY',
    @@super_read_only AS 'SUPER_READ_ONLY';

\! echo "[DB_BASIC_INFO_END]"
\! echo ""

-- ==============================================================================
-- 第二部分：用户权限和账户信息 (User Privileges and Account Information)
-- ==============================================================================

\! echo "==================== USER PRIVILEGES AND ACCOUNTS ===================="
\! echo ""

-- 1. 用户账户基本信息
\! echo "[USER_INFO_START]"
\! echo "1. 用户账户基本信息"
SELECT
    User AS 'USER',
    Host AS 'HOST',
    authentication_string != '' AS 'HAS_PASSWORD',
    plugin AS 'AUTH_PLUGIN',
    password_expired AS 'PWD_EXPIRED',
    password_last_changed AS 'PWD_LAST_CHANGED',
    password_lifetime AS 'PWD_LIFETIME_DAYS',
    account_locked AS 'ACCOUNT_LOCKED',
    Create_priv AS 'CREATE',
    Drop_priv AS 'DROP',
    Grant_priv AS 'GRANT',
    Super_priv AS 'SUPER',
    Create_user_priv AS 'CREATE_USER',
    Repl_slave_priv AS 'REPL_SLAVE',
    Repl_client_priv AS 'REPL_CLIENT'
FROM mysql.user
ORDER BY User, Host;

-- 2. 用户系统权限汇总
\! echo ""
\! echo "2. 用户系统权限汇总"
-- 为避免超宽单行，按每行10个权限分行展示
SET SESSION group_concat_max_len = 8192;
WITH privs AS (
    SELECT u.User, u.Host, 'SELECT' AS p,  10 AS ord FROM mysql.user u WHERE u.Select_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'INSERT',           20 FROM mysql.user u WHERE u.Insert_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'UPDATE',           30 FROM mysql.user u WHERE u.Update_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'DELETE',           40 FROM mysql.user u WHERE u.Delete_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE',           50 FROM mysql.user u WHERE u.Create_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'DROP',             60 FROM mysql.user u WHERE u.Drop_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'RELOAD',           70 FROM mysql.user u WHERE u.Reload_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'SHUTDOWN',         80 FROM mysql.user u WHERE u.Shutdown_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'PROCESS',          90 FROM mysql.user u WHERE u.Process_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'FILE',            100 FROM mysql.user u WHERE u.File_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'GRANT',           110 FROM mysql.user u WHERE u.Grant_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'REFERENCES',      120 FROM mysql.user u WHERE u.References_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'INDEX',           130 FROM mysql.user u WHERE u.Index_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'ALTER',           140 FROM mysql.user u WHERE u.Alter_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'SHOW_DB',         150 FROM mysql.user u WHERE u.Show_db_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'SUPER',           160 FROM mysql.user u WHERE u.Super_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE_TMP',      170 FROM mysql.user u WHERE u.Create_tmp_table_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'LOCK_TABLES',     180 FROM mysql.user u WHERE u.Lock_tables_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'EXECUTE',         190 FROM mysql.user u WHERE u.Execute_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'REPL_SLAVE',      200 FROM mysql.user u WHERE u.Repl_slave_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'REPL_CLIENT',     210 FROM mysql.user u WHERE u.Repl_client_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE_VIEW',     220 FROM mysql.user u WHERE u.Create_view_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'SHOW_VIEW',       230 FROM mysql.user u WHERE u.Show_view_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE_ROUTINE',  240 FROM mysql.user u WHERE u.Create_routine_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'ALTER_ROUTINE',   250 FROM mysql.user u WHERE u.Alter_routine_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE_USER',     260 FROM mysql.user u WHERE u.Create_user_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'EVENT',           270 FROM mysql.user u WHERE u.Event_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'TRIGGER',         280 FROM mysql.user u WHERE u.Trigger_priv='Y'
    UNION ALL SELECT u.User, u.Host, 'CREATE_TABLESPACE',290 FROM mysql.user u WHERE u.Create_tablespace_priv='Y'
), r AS (
    SELECT User, Host, p, ord,
           ROW_NUMBER() OVER (PARTITION BY User, Host ORDER BY ord, p) AS rn
    FROM privs
), chunks AS (
    SELECT User, Host, CEIL(rn/10) AS line_no, p, ord
    FROM r
)
SELECT
    User AS 'USER',
    Host AS 'HOST',
    GROUP_CONCAT(p ORDER BY ord SEPARATOR ' ') AS 'PRIVILEGES'
FROM chunks
GROUP BY User, Host, line_no
HAVING User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
ORDER BY User, Host, line_no;

-- 3. 数据库级别权限
\! echo ""
\! echo "3. 数据库级别权限"
SELECT
    User AS 'USER',
    Host AS 'HOST',
    Db AS 'DATABASE',
    CONCAT_WS(' ',
        IF(Select_priv='Y', 'SELECT', NULL),
        IF(Insert_priv='Y', 'INSERT', NULL),
        IF(Update_priv='Y', 'UPDATE', NULL),
        IF(Delete_priv='Y', 'DELETE', NULL),
        IF(Create_priv='Y', 'CREATE', NULL),
        IF(Drop_priv='Y', 'DROP', NULL),
        IF(Grant_priv='Y', 'GRANT', NULL),
        IF(References_priv='Y', 'REFERENCES', NULL),
        IF(Index_priv='Y', 'INDEX', NULL),
        IF(Alter_priv='Y', 'ALTER', NULL),
        IF(Create_tmp_table_priv='Y', 'CREATE_TMP_TABLE', NULL),
        IF(Lock_tables_priv='Y', 'LOCK_TABLES', NULL),
        IF(Execute_priv='Y', 'EXECUTE', NULL),
        IF(Create_view_priv='Y', 'CREATE_VIEW', NULL),
        IF(Show_view_priv='Y', 'SHOW_VIEW', NULL),
        IF(Create_routine_priv='Y', 'CREATE_ROUTINE', NULL),
        IF(Alter_routine_priv='Y', 'ALTER_ROUTINE', NULL),
        IF(Event_priv='Y', 'EVENT', NULL),
        IF(Trigger_priv='Y', 'TRIGGER', NULL)
    ) AS 'PRIVILEGES'
FROM mysql.db
ORDER BY User, Host, Db;

-- 4. 密码策略和账户状态检查
\! echo ""
\! echo "4. 密码策略和账户状态检查"
SELECT
    User AS 'USER',
    Host AS 'HOST',
    CASE
        WHEN authentication_string = '' THEN '无密码'
        WHEN password_expired = 'Y' THEN '密码已过期'
        ELSE '正常'
    END AS 'PASSWORD_STATUS',
    DATEDIFF(NOW(), password_last_changed) AS 'PWD_AGE_DAYS',
    password_lifetime AS 'PWD_LIFETIME',
    account_locked AS 'LOCKED'
FROM mysql.user
WHERE User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
ORDER BY password_expired DESC, PWD_AGE_DAYS DESC;

\! echo "[USER_INFO_END]"
\! echo ""

-- ==============================================================================
-- 第三部分：数据库性能参数 (Database Performance Parameters)
-- ==============================================================================

\! echo "==================== DATABASE PERFORMANCE PARAMETERS ===================="
\! echo ""

-- B1. 内存相关参数
\! echo "[DB_PERF_PARAMS_START]"
\! echo "B1. 内存相关参数 (Memory Parameters)"
SELECT
    @@key_buffer_size / 1024 / 1024 AS 'KEY_BUFFER_SIZE_MB',
    @@tmp_table_size / 1024 / 1024 AS 'TMP_TABLE_SIZE_MB',
    @@max_heap_table_size / 1024 / 1024 AS 'MAX_HEAP_TABLE_SIZE_MB',
    @@sort_buffer_size / 1024 / 1024 AS 'SORT_BUFFER_SIZE_MB',
    @@join_buffer_size / 1024 / 1024 AS 'JOIN_BUFFER_SIZE_MB',
    @@read_buffer_size / 1024 / 1024 AS 'READ_BUFFER_SIZE_MB',
    @@read_rnd_buffer_size / 1024 / 1024 AS 'READ_RND_BUFFER_SIZE_MB';

-- B2. InnoDB内存参数
\! echo ""
\! echo "B2. InnoDB内存参数"
SELECT
    @@innodb_buffer_pool_size / 1024 / 1024 / 1024 AS 'INNODB_BUFFER_POOL_SIZE_GB',
    @@innodb_buffer_pool_instances AS 'BUFFER_POOL_INSTANCES',
    @@innodb_log_buffer_size / 1024 / 1024 AS 'INNODB_LOG_BUFFER_SIZE_MB',
    @@innodb_sort_buffer_size / 1024 / 1024 AS 'INNODB_SORT_BUFFER_SIZE_MB',
    @@innodb_page_size / 1024 AS 'INNODB_PAGE_SIZE_KB';

-- B3. 连接和线程参数
\! echo ""
\! echo "B3. 连接和线程参数"
SELECT
    @@max_connections AS 'MAX_CONNECTIONS',
    @@max_connect_errors AS 'MAX_CONNECT_ERRORS',
    @@connect_timeout AS 'CONNECT_TIMEOUT',
    @@wait_timeout AS 'WAIT_TIMEOUT',
    @@interactive_timeout AS 'INTERACTIVE_TIMEOUT',
    @@thread_cache_size AS 'THREAD_CACHE_SIZE',
    @@thread_stack / 1024 AS 'THREAD_STACK_KB';

-- B4. 其他性能参数
\! echo ""
\! echo "B4. 其他性能参数"
SELECT
    @@table_open_cache AS 'TABLE_OPEN_CACHE',
    @@table_definition_cache AS 'TABLE_DEFINITION_CACHE',
    @@open_files_limit AS 'OPEN_FILES_LIMIT',
    @@max_allowed_packet / 1024 / 1024 AS 'MAX_ALLOWED_PACKET_MB';

\! echo "[DB_PERF_PARAMS_END]"
\! echo ""

-- ==============================================================================
-- 第三部分：数据库日志路径 (Database Log Paths)
-- ==============================================================================

\! echo "==================== DATABASE LOG PATHS ===================="
\! echo ""

-- C1. 重要日志文件路径
\! echo "[DB_LOG_PATHS_START]"
\! echo "C1. 重要日志文件路径"
SELECT
    @@datadir AS 'DATA_DIRECTORY',
    @@tmpdir AS 'TEMP_DIRECTORY',
    @@general_log_file AS 'GENERAL_LOG_FILE',
    @@slow_query_log_file AS 'SLOW_QUERY_LOG_FILE',
    @@log_error AS 'ERROR_LOG_FILE';

-- C2. 二进制日志配置
\! echo ""
\! echo "C2. 二进制日志配置"
SELECT
    @@log_bin AS 'BINARY_LOG_ENABLED',
    @@log_bin_basename AS 'LOG_BIN_BASENAME',
    @@log_bin_index AS 'LOG_BIN_INDEX',
    @@binlog_format AS 'BINLOG_FORMAT',
    @@binlog_expire_logs_seconds / 86400 AS 'EXPIRE_LOGS_DAYS',
    @@max_binlog_size / 1024 / 1024 AS 'MAX_BINLOG_SIZE_MB',
    @@sync_binlog AS 'SYNC_BINLOG';

-- C3. 慢查询日志配置
\! echo ""
\! echo "C3. 慢查询日志配置"
SELECT
    @@slow_query_log AS 'SLOW_QUERY_LOG_ENABLED',
    @@long_query_time AS 'LONG_QUERY_TIME',
    @@log_queries_not_using_indexes AS 'LOG_QUERIES_NOT_USING_INDEXES',
    @@log_throttle_queries_not_using_indexes AS 'LOG_THROTTLE_QUERIES_NOT_USING_INDEXES',
    @@min_examined_row_limit AS 'MIN_EXAMINED_ROW_LIMIT';

\! echo "[DB_LOG_PATHS_END]"
\! echo ""

-- ==============================================================================
-- 第四部分：数据库状态检查 (Database Status Checks)
-- ==============================================================================

\! echo "==================== DATABASE STATUS CHECKS ===================="
\! echo ""

-- 1. 数据库大小统计
\! echo "[DB_STATUS_START]"
\! echo "1. 数据库大小统计"
SELECT
    IFNULL(COUNT(DISTINCT table_schema), 0) AS 'DATABASE_COUNT',
    IFNULL(COUNT(*), 0) AS 'TABLE_COUNT',
    IFNULL(ROUND(SUM(data_length + index_length) / 1024 / 1024, 2), 0.00) AS 'TOTAL_SIZE_MB',
    IFNULL(ROUND(SUM(data_length) / 1024 / 1024, 2), 0.00) AS 'DATA_SIZE_MB',
    IFNULL(ROUND(SUM(index_length) / 1024 / 1024, 2), 0.00) AS 'INDEX_SIZE_MB',
    IFNULL(ROUND(SUM(data_free) / 1024 / 1024, 2), 0.00) AS 'FREE_SIZE_MB'
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys');

-- 2. 各数据库大小排名 (TOP 10)
\! echo ""
\! echo "2. 各数据库大小排名 (TOP 10)"
SELECT * FROM (
    SELECT
        table_schema AS 'DATABASE_NAME',
        COUNT(*) AS 'TABLE_COUNT',
        ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'TOTAL_SIZE_MB',
        ROUND(SUM(data_length) / 1024 / 1024, 2) AS 'DATA_SIZE_MB',
        ROUND(SUM(index_length) / 1024 / 1024, 2) AS 'INDEX_SIZE_MB'
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
    GROUP BY table_schema
    UNION ALL
    SELECT '(无用户数据库)', 0, 0.00, 0.00, 0.00
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
    )
) AS t
ORDER BY TOTAL_SIZE_MB DESC
LIMIT 10;

-- 3. 表大小排名 (TOP 20)
\! echo ""
\! echo "3. 表大小排名 (TOP 20)"
SELECT * FROM (
    SELECT
        table_schema AS 'DATABASE_NAME',
        table_name AS 'TABLE_NAME',
        table_rows AS 'ROW_COUNT',
        ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'TOTAL_SIZE_MB',
        ROUND(data_length / 1024 / 1024, 2) AS 'DATA_SIZE_MB',
        ROUND(index_length / 1024 / 1024, 2) AS 'INDEX_SIZE_MB',
        ROUND(data_free / 1024 / 1024, 2) AS 'FREE_SIZE_MB'
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
    UNION ALL
    SELECT '(无用户表)', '', 0, 0.00, 0.00, 0.00, 0.00
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
    )
) AS t
ORDER BY TOTAL_SIZE_MB DESC
LIMIT 20;

-- 4. 存储引擎使用情况
\! echo ""
\! echo "4. 存储引擎使用情况"
SELECT * FROM (
    SELECT
        ENGINE AS 'STORAGE_ENGINE',
        COUNT(*) AS 'TABLE_COUNT',
        ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'TOTAL_SIZE_MB'
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        AND ENGINE IS NOT NULL
    GROUP BY ENGINE
    UNION ALL
    SELECT '(无用户表)', 0, 0.00
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            AND ENGINE IS NOT NULL
    )
) AS t
ORDER BY TABLE_COUNT DESC;

-- 5. InnoDB状态概览
\! echo ""
\! echo "5. InnoDB Buffer Pool状态"
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_write_requests',
    'Innodb_buffer_pool_wait_free'
);

-- 6. 连接状态统计
\! echo ""
\! echo "6. 连接状态统计"
SELECT
    COUNT(*) AS 'TOTAL_CONNECTIONS',
    SUM(CASE WHEN command = 'Sleep' THEN 1 ELSE 0 END) AS 'SLEEPING',
    SUM(CASE WHEN command != 'Sleep' THEN 1 ELSE 0 END) AS 'ACTIVE',
    MAX(time) AS 'MAX_CONNECTION_TIME'
FROM information_schema.processlist;

-- 7. 按用户统计连接
\! echo ""
\! echo "7. 按用户统计连接"
SELECT
    user AS 'USER',
    COUNT(*) AS 'CONNECTION_COUNT',
    SUM(CASE WHEN command = 'Sleep' THEN 1 ELSE 0 END) AS 'SLEEPING',
    SUM(CASE WHEN command != 'Sleep' THEN 1 ELSE 0 END) AS 'ACTIVE'
FROM information_schema.processlist
GROUP BY user
ORDER BY CONNECTION_COUNT DESC;

-- 7.1 当前进程详细列表（非Sleep进程）
\! echo ""
\! echo "7.1 当前活跃进程列表（非Sleep进程）"
-- 去除当前会话、清洗换行和制表、截断SQL文本以避免表格换行
SELECT
    id AS 'PROCESS_ID',
    user AS 'USER',
    host AS 'HOST',
    db AS 'DATABASE',
    command AS 'COMMAND',
    time AS 'TIME_SECONDS',
    state AS 'STATE',
    SUBSTRING(
        TRIM(
            REGEXP_REPLACE(
                REPLACE(REPLACE(info, '\n', ' '), '\r', ' '),
                '[\t ]+', ' '
            )
        ), 1, 160
    ) AS 'SQL_TEXT'
FROM information_schema.processlist
WHERE command != 'Sleep' AND id <> CONNECTION_ID()
ORDER BY time DESC;

-- 7.2 完整进程列表（包含Sleep，限制20条）
\! echo ""
\! echo "7.2 所有进程列表（TOP 20 by TIME）"
-- 清洗SQL文本，避免多行内容破坏表格结构
SELECT
    id AS 'PROCESS_ID',
    user AS 'USER',
    host AS 'HOST',
    db AS 'DATABASE',
    command AS 'COMMAND',
    time AS 'TIME_SECONDS',
    state AS 'STATE',
    SUBSTRING(
        TRIM(
            REGEXP_REPLACE(
                REPLACE(REPLACE(info, '\n', ' '), '\r', ' '),
                '[\t ]+', ' '
            )
        ), 1, 160
    ) AS 'SQL_TEXT'
FROM information_schema.processlist
ORDER BY time DESC
LIMIT 20;

-- 8. 锁等待信息（MySQL 8.0使用performance_schema）
\! echo ""
\! echo "8. 当前锁等待信息"
SELECT
    COUNT(*) AS 'LOCK_WAIT_COUNT'
FROM performance_schema.data_lock_waits;

-- 9. 长时间运行的事务
\! echo ""
\! echo "9. 长时间运行的事务 (超过60秒)"
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS 'DURATION_SECONDS',
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
WHERE TIMESTAMPDIFF(SECOND, trx_started, NOW()) > 60
ORDER BY trx_started;

-- 10. 慢查询统计
\! echo ""
\! echo "10. 慢查询统计"
SELECT
    VARIABLE_VALUE AS 'SLOW_QUERIES_COUNT'
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Slow_queries';

-- 11. 原生进程列表输出（SHOW FULL PROCESSLIST）
\! echo ""
\! echo "11. 进程列表（SHOW PROCESSLIST）"
SHOW PROCESSLIST;

-- 12. 用户权限和维护状态详细分析
\! echo ""
\! echo "12. 用户权限和维护状态详细分析"
SELECT
    User AS '用户名',
    Host AS '主机',
    -- 认证和密码信息
    plugin AS '认证插件',
    CASE
        WHEN authentication_string = '' THEN '无密码(危险!)'
        WHEN LENGTH(authentication_string) < 41 THEN '弱密码哈希'
        ELSE '已设置密码'
    END AS '密码状态',
    password_expired AS '密码已过期',
    password_last_changed AS '密码最后修改时间',
    CASE
        WHEN password_lifetime IS NULL THEN '使用全局设置'
        WHEN password_lifetime = 0 THEN '永不过期'
        ELSE CONCAT(password_lifetime, '天')
    END AS '密码有效期',
    DATEDIFF(NOW(), password_last_changed) AS '密码使用天数',

    -- 账户状态
    account_locked AS '账户锁定',

    -- 系统级权限（关键权限）
    CONCAT(
        IF(Super_priv='Y', 'SUPER ', ''),
        IF(Shutdown_priv='Y', 'SHUTDOWN ', ''),
        IF(Process_priv='Y', 'PROCESS ', ''),
        IF(File_priv='Y', 'FILE ', ''),
        IF(Grant_priv='Y', 'GRANT ', ''),
        IF(Create_user_priv='Y', 'CREATE_USER ', ''),
        IF(Reload_priv='Y', 'RELOAD ', ''),
        IF(Repl_slave_priv='Y', 'REPL_SLAVE ', ''),
        IF(Repl_client_priv='Y', 'REPL_CLIENT ', '')
    ) AS '系统权限',

    -- 数据库级权限
    CONCAT(
        IF(Select_priv='Y', 'SELECT ', ''),
        IF(Insert_priv='Y', 'INSERT ', ''),
        IF(Update_priv='Y', 'UPDATE ', ''),
        IF(Delete_priv='Y', 'DELETE ', ''),
        IF(Create_priv='Y', 'CREATE ', ''),
        IF(Drop_priv='Y', 'DROP ', ''),
        IF(Alter_priv='Y', 'ALTER ', ''),
        IF(Index_priv='Y', 'INDEX ', ''),
        IF(References_priv='Y', 'REFERENCES ', '')
    ) AS '数据权限',

    -- 对象级权限
    CONCAT(
        IF(Create_tmp_table_priv='Y', 'CREATE_TMP_TABLE ', ''),
        IF(Lock_tables_priv='Y', 'LOCK_TABLES ', ''),
        IF(Execute_priv='Y', 'EXECUTE ', ''),
        IF(Create_view_priv='Y', 'CREATE_VIEW ', ''),
        IF(Show_view_priv='Y', 'SHOW_VIEW ', ''),
        IF(Create_routine_priv='Y', 'CREATE_ROUTINE ', ''),
        IF(Alter_routine_priv='Y', 'ALTER_ROUTINE ', ''),
        IF(Event_priv='Y', 'EVENT ', ''),
        IF(Trigger_priv='Y', 'TRIGGER ', '')
    ) AS '对象权限',

    -- 资源限制
    max_questions AS '每小时最大查询数',
    max_updates AS '每小时最大更新数',
    max_connections AS '最大连接数',
    max_user_connections AS '最大用户连接数',

    -- 维护建议
    CASE
        WHEN authentication_string = '' THEN '【高危】立即设置密码'
        WHEN password_expired = 'Y' THEN '【重要】密码已过期，需要重置'
        WHEN DATEDIFF(NOW(), password_last_changed) > 90 THEN '【建议】密码超过90天未更改'
        WHEN Super_priv = 'Y' AND User NOT IN ('root', 'admin') THEN '【注意】非管理员用户拥有SUPER权限'
        WHEN Grant_priv = 'Y' AND Super_priv = 'N' THEN '【注意】用户拥有GRANT权限但无SUPER权限'
        WHEN account_locked = 'Y' THEN '【信息】账户已锁定'
        ELSE '正常'
    END AS '维护建议'
FROM mysql.user
WHERE User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
ORDER BY
    CASE
        WHEN authentication_string = '' THEN 1
        WHEN password_expired = 'Y' THEN 2
        WHEN Super_priv = 'Y' THEN 3
        ELSE 4
    END,
    User, Host;

\! echo ""
\! echo "12V. 用户权限与维护状态（纵向展示，便于阅读）"
-- 将同一账户的各项信息转为多行展示：ACCOUNT | ITEM | VALUE
SELECT * FROM (
    SELECT
        CONCAT(u.User, '@', u.Host) AS ACCOUNT,
        '认证插件' AS ITEM,
        u.plugin AS VALUE
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '密码状态',
        CASE
            WHEN u.authentication_string = '' THEN '无密码(危险!)'
            WHEN LENGTH(u.authentication_string) < 41 THEN '弱密码哈希'
            ELSE '已设置密码'
        END
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '密码已过期', u.password_expired FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '密码最后修改时间', IFNULL(CAST(u.password_last_changed AS CHAR), 'NULL') FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '密码有效期',
        CASE
            WHEN u.password_lifetime IS NULL THEN '使用全局设置'
            WHEN u.password_lifetime = 0 THEN '永不过期'
            ELSE CONCAT(u.password_lifetime, '天')
        END
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '密码使用天数', CAST(DATEDIFF(NOW(), u.password_last_changed) AS CHAR)
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '账户锁定', u.account_locked FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '系统权限',
        TRIM(
            CONCAT(
                IF(u.Super_priv='Y', 'SUPER ', ''),
                IF(u.Shutdown_priv='Y', 'SHUTDOWN ', ''),
                IF(u.Process_priv='Y', 'PROCESS ', ''),
                IF(u.File_priv='Y', 'FILE ', ''),
                IF(u.Grant_priv='Y', 'GRANT ', ''),
                IF(u.Create_user_priv='Y', 'CREATE_USER ', ''),
                IF(u.Reload_priv='Y', 'RELOAD ', ''),
                IF(u.Repl_slave_priv='Y', 'REPL_SLAVE ', ''),
                IF(u.Repl_client_priv='Y', 'REPL_CLIENT ', '')
            )
        )
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '数据权限',
        TRIM(
            CONCAT(
                IF(u.Select_priv='Y', 'SELECT ', ''),
                IF(u.Insert_priv='Y', 'INSERT ', ''),
                IF(u.Update_priv='Y', 'UPDATE ', ''),
                IF(u.Delete_priv='Y', 'DELETE ', ''),
                IF(u.Create_priv='Y', 'CREATE ', ''),
                IF(u.Drop_priv='Y', 'DROP ', ''),
                IF(u.Alter_priv='Y', 'ALTER ', ''),
                IF(u.Index_priv='Y', 'INDEX ', ''),
                IF(u.References_priv='Y', 'REFERENCES ', '')
            )
        )
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '对象权限',
        TRIM(
            CONCAT(
                IF(u.Create_tmp_table_priv='Y', 'CREATE_TMP_TABLE ', ''),
                IF(u.Lock_tables_priv='Y', 'LOCK_TABLES ', ''),
                IF(u.Execute_priv='Y', 'EXECUTE ', ''),
                IF(u.Create_view_priv='Y', 'CREATE_VIEW ', ''),
                IF(u.Show_view_priv='Y', 'SHOW_VIEW ', ''),
                IF(u.Create_routine_priv='Y', 'CREATE_ROUTINE ', ''),
                IF(u.Alter_routine_priv='Y', 'ALTER_ROUTINE ', ''),
                IF(u.Event_priv='Y', 'EVENT ', ''),
                IF(u.Trigger_priv='Y', 'TRIGGER ', '')
            )
        )
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '每小时最大查询数', IFNULL(CAST(u.max_questions AS CHAR), '0') FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '每小时最大更新数', IFNULL(CAST(u.max_updates AS CHAR), '0') FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '最大连接数', IFNULL(CAST(u.max_connections AS CHAR), '0') FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '最大用户连接数', IFNULL(CAST(u.max_user_connections AS CHAR), '0') FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
    UNION ALL
    SELECT CONCAT(u.User, '@', u.Host), '维护建议',
        CASE
            WHEN u.authentication_string = '' THEN '【高危】立即设置密码'
            WHEN u.password_expired = 'Y' THEN '【重要】密码已过期，需要重置'
            WHEN DATEDIFF(NOW(), u.password_last_changed) > 90 THEN '【建议】密码超过90天未更改'
            WHEN u.Super_priv = 'Y' AND u.User NOT IN ('root', 'admin') THEN '【注意】非管理员用户拥有SUPER权限'
            WHEN u.Grant_priv = 'Y' AND u.Super_priv = 'N' THEN '【注意】用户拥有GRANT权限但无SUPER权限'
            WHEN u.account_locked = 'Y' THEN '【信息】账户已锁定'
            ELSE '正常'
        END
    FROM mysql.user u
    WHERE u.User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema')
) t
ORDER BY ACCOUNT, ITEM;

\! echo "[DB_STATUS_END]"
\! echo ""

-- ==============================================================================
-- 第五部分：主从复制状态 (Replication Status)
-- ==============================================================================

\! echo "==================== REPLICATION STATUS ===================="
\! echo ""

-- 1. 复制相关参数
\! echo "[REPLICATION_START]"
\! echo "1. 复制相关参数"
SELECT
    @@server_id AS 'SERVER_ID',
    @@server_uuid AS 'SERVER_UUID',
    @@log_bin AS 'BINLOG_ENABLED',
    @@log_slave_updates AS 'LOG_SLAVE_UPDATES',
    @@read_only AS 'READ_ONLY',
    @@super_read_only AS 'SUPER_READ_ONLY',
    @@gtid_mode AS 'GTID_MODE',
    @@enforce_gtid_consistency AS 'ENFORCE_GTID_CONSISTENCY';

-- 2. 主库状态
\! echo ""
\! echo "2. 主库状态"
SHOW MASTER STATUS\G

-- 3. 从库状态
\! echo ""
\! echo "3. 从库状态"
SHOW SLAVE STATUS\G

-- 4. 从库主机列表
\! echo ""
\! echo "4. 连接的从库列表"
SHOW SLAVE HOSTS;

\! echo "[REPLICATION_END]"
\! echo ""

-- ==============================================================================
-- 第六部分：性能指标统计 (Performance Metrics)
-- ==============================================================================

\! echo "==================== PERFORMANCE METRICS ===================="
\! echo ""

-- 1. 查询统计
\! echo "[PERFORMANCE_START]"
\! echo "1. 查询统计"
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Questions',
    'Select_full_join',
    'Select_scan',
    'Slow_queries',
    'Sort_merge_passes',
    'Sort_scan'
)
ORDER BY VARIABLE_NAME;

-- 2. 表锁统计
\! echo ""
\! echo "2. 表锁统计"
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Table_locks_immediate',
    'Table_locks_waited',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows'
)
ORDER BY VARIABLE_NAME;

-- 3. InnoDB性能指标
\! echo ""
\! echo "3. InnoDB性能指标"
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_rows_read',
    'Innodb_rows_inserted',
    'Innodb_rows_updated',
    'Innodb_rows_deleted',
    'Innodb_row_lock_waits',
    'Innodb_row_lock_time',
    'Innodb_row_lock_time_avg',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_log_waits',
    'Innodb_os_log_written'
)
ORDER BY VARIABLE_NAME;

-- 4. 缓存命中率计算
\! echo ""
\! echo "4. 缓存命中率"
SELECT
    'InnoDB Buffer Pool Hit Rate' AS 'METRIC',
    ROUND(
        100 - (
            (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_reads') * 100.0 /
            NULLIF((SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_read_requests'), 0)
        ), 2
    ) AS 'VALUE_PERCENT'
UNION ALL
SELECT
    'Thread Cache Hit Rate' AS 'METRIC',
    ROUND(
        100 - (
            (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Threads_created') * 100.0 /
            NULLIF((SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Connections'), 0)
        ), 2
    ) AS 'VALUE_PERCENT'
UNION ALL
SELECT
    'Table Open Cache Hit Rate' AS 'METRIC',
    ROUND(
        (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Table_open_cache_hits') * 100.0 /
        NULLIF(
            (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Table_open_cache_hits') +
            (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Table_open_cache_misses'), 0
        ), 2
    ) AS 'VALUE_PERCENT';

\! echo "[PERFORMANCE_END]"
\! echo ""

-- ==============================================================================
-- 第七部分：问题诊断 (Problem Diagnosis)
-- ==============================================================================

\! echo "==================== PROBLEM DIAGNOSIS ===================="
\! echo ""

-- 1. 无主键的表
\! echo "[DIAGNOSIS_START]"
\! echo "1. 无主键的表 (TOP 20)"
SELECT * FROM (
    SELECT
        t.table_schema AS 'DATABASE_NAME',
        t.table_name AS 'TABLE_NAME',
        t.table_rows AS 'ROW_COUNT',
        ROUND((t.data_length + t.index_length) / 1024 / 1024, 2) AS 'SIZE_MB'
    FROM information_schema.tables t
    WHERE t.table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        AND t.table_type = 'BASE TABLE'
        AND NOT EXISTS (
            SELECT 1
            FROM information_schema.statistics s
            WHERE s.table_schema = t.table_schema
                AND s.table_name = t.table_name
                AND s.index_name = 'PRIMARY'
        )
    UNION ALL
    SELECT '(无用户表)', '', 0, 0.00
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            AND table_type = 'BASE TABLE'
    )
) AS t
ORDER BY ROW_COUNT DESC
LIMIT 20;

-- 2. 表碎片率高的表
\! echo ""
\! echo "2. 碎片率高的表 (碎片率>30%, TOP 20)"
SELECT * FROM (
    SELECT
        table_schema AS 'DATABASE_NAME',
        table_name AS 'TABLE_NAME',
        ROUND(data_free / 1024 / 1024, 2) AS 'FRAGMENTED_MB',
        ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'TOTAL_SIZE_MB',
        ROUND(data_free * 100 / (data_length + index_length + data_free), 2) AS 'FRAGMENTATION_PERCENT'
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        AND data_free > 0
        AND (data_length + index_length) > 0
        AND data_free * 100 / (data_length + index_length + data_free) > 30
    UNION ALL
    SELECT '(无高碎片表)', '', 0.00, 0.00, 0.00
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            AND data_free > 0
            AND (data_length + index_length) > 0
            AND data_free * 100 / (data_length + index_length + data_free) > 30
    )
) AS t
ORDER BY FRAGMENTED_MB DESC
LIMIT 20;

-- 3. 自增ID使用率高的表
\! echo ""
\! echo "3. 自增ID使用率高的表 (使用率>70%, TOP 20)"
SELECT * FROM (
    SELECT
        t.table_schema AS 'DATABASE_NAME',
        t.table_name AS 'TABLE_NAME',
        t.auto_increment AS 'CURRENT_VALUE',
        ROUND(t.auto_increment /
            CASE
                WHEN c.column_type LIKE 'tinyint%' THEN 127
                WHEN c.column_type LIKE 'smallint%' THEN 32767
                WHEN c.column_type LIKE 'mediumint%' THEN 8388607
                WHEN c.column_type LIKE 'int%' THEN 2147483647
                WHEN c.column_type LIKE 'bigint%' THEN 9223372036854775807
            END * 100, 2) AS 'USAGE_PERCENT',
        c.column_type AS 'COLUMN_TYPE'
    FROM information_schema.tables t
    JOIN information_schema.columns c ON
        t.table_schema = c.table_schema
        AND t.table_name = c.table_name
        AND c.extra = 'auto_increment'
    WHERE t.table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        AND t.auto_increment IS NOT NULL
        AND t.auto_increment /
            CASE
                WHEN c.column_type LIKE 'tinyint%' THEN 127
                WHEN c.column_type LIKE 'smallint%' THEN 32767
                WHEN c.column_type LIKE 'mediumint%' THEN 8388607
                WHEN c.column_type LIKE 'int%' THEN 2147483647
                WHEN c.column_type LIKE 'bigint%' THEN 9223372036854775807
            END > 0.7
    UNION ALL
    SELECT '(无高使用率自增表)', '', NULL, 0.00, ''
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t2
        JOIN information_schema.columns c2 ON
            t2.table_schema = c2.table_schema
            AND t2.table_name = c2.table_name
            AND c2.extra = 'auto_increment'
        WHERE t2.table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            AND t2.auto_increment IS NOT NULL
    )
) AS t
ORDER BY USAGE_PERCENT DESC
LIMIT 20;

-- 4. 大事务检测
\! echo ""
\! echo "4. 大事务检测 (修改行数>10000)"
SELECT * FROM (
    SELECT
        trx_id,
        trx_state,
        trx_started,
        TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS 'DURATION_SECONDS',
        trx_rows_modified AS 'ROWS_MODIFIED',
        trx_mysql_thread_id
    FROM information_schema.innodb_trx
    WHERE trx_rows_modified > 10000
    UNION ALL
    SELECT '(无大事务)', '', NULL, 0, 0, 0
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.innodb_trx
        WHERE trx_rows_modified > 10000
    )
) AS t
ORDER BY ROWS_MODIFIED DESC;

-- 4.1 缓慢SQL列表（前20条）
\! echo ""
\! echo "4.1 缓慢SQL列表（前20条）"
SELECT
    d.SCHEMA_NAME              AS db,
    d.DIGEST_TEXT              AS sample_sql,
    d.COUNT_STAR               AS exec_count,
    ROUND(d.SUM_TIMER_WAIT/1e12, 3)  AS total_s,
    ROUND(d.AVG_TIMER_WAIT/1e12, 6)  AS avg_s
FROM performance_schema.events_statements_summary_by_digest AS d
WHERE d.SCHEMA_NAME IS NOT NULL
ORDER BY d.SUM_TIMER_WAIT DESC
LIMIT 20;

-- 5. InnoDB引擎详细状态信息
\! echo ""
\! echo "5. InnoDB引擎详细状态信息"
\! echo "------------------------------------------------------"

\! echo "[DIAGNOSIS_END]"
\! echo ""

-- ==============================================================================
-- 第八部分：建议与总结 (Recommendations and Summary)
-- ==============================================================================

\! echo "==================== RECOMMENDATIONS ===================="
\! echo ""

\! echo "1. 内存配置建议:"
SELECT
    CASE
        WHEN @@innodb_buffer_pool_size < (SELECT SUM(data_length + index_length) FROM information_schema.tables WHERE ENGINE='InnoDB')
        THEN CONCAT('建议增加 InnoDB Buffer Pool 大小, 当前: ', ROUND(@@innodb_buffer_pool_size/1024/1024/1024, 2), 'GB')
        ELSE 'InnoDB Buffer Pool 配置合理'
    END AS 'MEMORY_RECOMMENDATION';

\! echo ""
\! echo "2. 连接数建议:"
SELECT
    CASE
        WHEN (SELECT COUNT(*) FROM information_schema.processlist) > @@max_connections * 0.8
        THEN CONCAT('警告: 连接数接近上限, 当前连接数: ', (SELECT COUNT(*) FROM information_schema.processlist), ', 最大连接数: ', @@max_connections)
        ELSE '连接数正常'
    END AS 'CONNECTION_RECOMMENDATION';

\! echo ""
\! echo "3. 慢查询建议:"
SELECT
    CASE
        WHEN @@slow_query_log = 0
        THEN '建议开启慢查询日志'
        WHEN @@long_query_time > 5
        THEN CONCAT('建议降低 long_query_time, 当前值: ', @@long_query_time, '秒')
        ELSE '慢查询配置合理'
    END AS 'SLOW_QUERY_RECOMMENDATION';

\! echo ""
\! echo "4. 二进制日志建议:"
SELECT
    CASE
        WHEN @@log_bin = 0
        THEN '建议开启二进制日志以支持备份和复制'
        WHEN @@sync_binlog != 1
        THEN CONCAT('建议设置 sync_binlog=1 以确保数据安全, 当前值: ', @@sync_binlog)
        ELSE '二进制日志配置合理'
    END AS 'BINLOG_RECOMMENDATION';

\! echo ""
\! echo "5. InnoDB引擎优化建议:"
-- 基于InnoDB状态的优化建议
SELECT '根据InnoDB状态分析，建议关注以下优化点：' AS 'INNODB_RECOMMENDATIONS'
UNION ALL
-- Buffer Pool脏页建议
SELECT CONCAT('- 脏页比例: ',
    ROUND((SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_dirty') * 100.0 /
          (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'), 2),
    '%, ',
    CASE
        WHEN (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_dirty') * 100.0 /
             (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total') > 75
        THEN '脏页比例过高，建议调整 innodb_max_dirty_pages_pct 参数'
        ELSE '脏页比例正常'
    END)
UNION ALL
-- 空闲页建议
SELECT CONCAT('- 空闲页比例: ',
    ROUND((SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_free') * 100.0 /
          (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'), 2),
    '%, ',
    CASE
        WHEN (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_free') * 100.0 /
             (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total') > 20
        THEN '空闲页过多，可考虑减小 Buffer Pool 大小'
        WHEN (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_free') * 100.0 /
             (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total') < 1
        THEN '空闲页不足，建议增加 Buffer Pool 大小'
        ELSE '空闲页比例合理'
    END)
UNION ALL
-- 日志等待建议
SELECT CASE
    WHEN (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_log_waits') > 0
    THEN CONCAT('- 检测到日志等待: ',
        (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_log_waits'),
        ' 次，建议增加 innodb_log_buffer_size')
    ELSE '- 日志缓冲区配置合理，无等待发生'
END
UNION ALL
-- 行锁等待建议
SELECT CASE
    WHEN (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_row_lock_waits') > 100
    THEN CONCAT('- 行锁等待次数较多: ',
        (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_row_lock_waits'),
        ' 次，建议优化事务和查询')
    ELSE '- 行锁等待情况正常'
END;

\! echo ""
\! echo "==================== HEALTH CHECK COMPLETED ===================="
\! echo "检查时间: "
SELECT NOW() AS 'COMPLETION_TIME';
\! echo "============================================================="
EOSQL
    then
        # 只提示存在错误，继续后续处理
        print_warning "健康检查 SQL 存在错误，已忽略并继续执行，详情见: $error_file"
    fi

    # InnoDB 状态获取也做容错，避免 set -e 因失败中断
    print_info "正在处理InnoDB引擎状态信息..."
    local innodb_tmp="/tmp/innodb_status_$$.txt"
    local innodb_formatted="/tmp/innodb_formatted_$$.txt"

    # 获取原始InnoDB状态（容错处理）
    if $MYSQL_CMD -e "SHOW ENGINE INNODB STATUS\G" > "$innodb_tmp" 2>> "$error_file"; then

        if [ -f "$innodb_tmp" ] && [ -s "$innodb_tmp" ]; then
            # 格式化InnoDB状态信息
            {
                # 查找5. InnoDB引擎详细状态信息位置并插入格式化内容
                awk '
                /^5\. InnoDB引擎详细状态信息$/ {
                    print
                    print "------------------------------------------------------"
                    print ""

                    # 5.1 事务状态
                    print "5.1 InnoDB关键性能指标"
                    print "+--------------------+----------------------+"
                    print "| 指标               | 值                   |"
                    print "+--------------------+----------------------+"

                    # 从文件中提取信息
                    while ((getline line < "'$innodb_tmp'") > 0) {
                        if (line ~ /History list length/) {
                            if (match(line, /History list length ([0-9]+)/, arr)) {
                                printf "| %-18s | %-20s |\n", "History List Length", arr[1]
                            }
                        }
                        if (line ~ /queries inside InnoDB/) {
                            if (match(line, /([0-9]+) queries inside InnoDB/, arr)) {
                                printf "| %-18s | %-20s |\n", "Queries Inside", arr[1]
                            }
                        }
                        if (line ~ /queries in queue/) {
                            if (match(line, /([0-9]+) queries in queue/, arr)) {
                                printf "| %-18s | %-20s |\n", "Queries In Queue", arr[1]
                            }
                        }
                    }
                    close("'$innodb_tmp'")
                    print "+--------------------+----------------------+"
                    print ""

                    # 5.2 Buffer Pool状态
                    print "5.2 InnoDB Buffer Pool汇总"
                    print "+--------------------+----------------------+"
                    print "| 指标               | 值                   |"
                    print "+--------------------+----------------------+"

                    # 只读取总体Buffer Pool信息，不读取单个Pool信息
                    total_found = 0
                    while ((getline line < "'$innodb_tmp'") > 0) {
                        # 跳过单个Buffer Pool的信息
                        if (line ~ /^---BUFFER POOL/) {
                            break
                        }

                        if (line ~ /^Buffer pool size[ ]+[0-9]+$/ && total_found == 0) {
                            if (match(line, /Buffer pool size[ ]+([0-9]+)/, arr)) {
                                pages = arr[1]
                                mb = int(pages * 16 / 1024)
                                printf "| %-18s | %-20s |\n", "总大小", mb " MB (" pages " pages)"
                                total_found = 1
                            }
                        }
                        if (line ~ /^Free buffers/ && total_found == 1) {
                            if (match(line, /Free buffers[ ]+([0-9]+)/, arr)) {
                                printf "| %-18s | %-20s |\n", "空闲页", arr[1]
                            }
                        }
                        if (line ~ /^Database pages/ && total_found == 1) {
                            if (match(line, /Database pages[ ]+([0-9]+)/, arr)) {
                                printf "| %-18s | %-20s |\n", "数据页", arr[1]
                            }
                        }
                        if (line ~ /^Modified db pages/ && total_found == 1) {
                            if (match(line, /Modified db pages[ ]+([0-9]+)/, arr)) {
                                printf "| %-18s | %-20s |\n", "脏页", arr[1]
                            }
                        }
                        if (line ~ /Buffer pool hit rate/ && total_found == 1) {
                            if (match(line, /Buffer pool hit rate ([0-9]+) \/ 1000/, arr)) {
                                hit_rate = arr[1] / 10
                                printf "| %-18s | %-20s |\n", "命中率", hit_rate "%"
                                break  # 找到命中率后就停止，避免读取单个Pool的信息
                            }
                        }
                    }
                    close("'$innodb_tmp'")
                    print "+--------------------+----------------------+"
                    print ""

                    # 5.3 I/O统计
                    print "5.3 InnoDB I/O统计"
                    print "+--------------------+----------------------+"
                    print "| 指标               | 值                   |"
                    print "+--------------------+----------------------+"

                    while ((getline line < "'$innodb_tmp'") > 0) {
                        if (line ~ /OS file reads,/) {
                            if (match(line, /([0-9]+) OS file reads/, arr)) {
                                printf "| %-18s | %-20s |\n", "OS File Reads", arr[1]
                            }
                            if (match(line, /([0-9]+) OS file writes/, arr)) {
                                printf "| %-18s | %-20s |\n", "OS File Writes", arr[1]
                            }
                            if (match(line, /([0-9]+) OS fsyncs/, arr)) {
                                printf "| %-18s | %-20s |\n", "OS Fsyncs", arr[1]
                            }
                        }
                        if (line ~ /reads\/s.*writes\/s.*fsyncs\/s/) {
                            if (match(line, /([0-9.]+) reads\/s/, arr)) {
                                printf "| %-18s | %-20s |\n", "读取速率", arr[1] " reads/s"
                            }
                            if (match(line, /([0-9.]+) writes\/s/, arr)) {
                                printf "| %-18s | %-20s |\n", "写入速率", arr[1] " writes/s"
                            }
                            if (match(line, /([0-9.]+) fsyncs\/s/, arr)) {
                                printf "| %-18s | %-20s |\n", "Fsync速率", arr[1] " fsyncs/s"
                            }
                        }
                    }
                    close("'$innodb_tmp'")
                    print "+--------------------+----------------------+"
                    print ""

                    # 5.4 行操作统计
                    print "5.4 InnoDB行操作统计"
                    print "+--------------------+----------------------+"
                    print "| 指标               | 值                   |"
                    print "+--------------------+----------------------+"

                    while ((getline line < "'$innodb_tmp'") > 0) {
                        if (line ~ /^Number of rows inserted/) {
                            if (match(line, /inserted ([0-9]+)/, arr)) {
                                printf "| %-18s | %\047-20d |\n", "Rows Inserted", arr[1]
                            }
                            if (match(line, /updated ([0-9]+)/, arr)) {
                                printf "| %-18s | %\047-20d |\n", "Rows Updated", arr[1]
                            }
                            if (match(line, /deleted ([0-9]+)/, arr)) {
                                printf "| %-18s | %\047-20d |\n", "Rows Deleted", arr[1]
                            }
                            if (match(line, /read ([0-9]+)/, arr)) {
                                printf "| %-18s | %\047-20d |\n", "Rows Read", arr[1]
                            }
                        }
                    }
                    close("'$innodb_tmp'")
                    print "+--------------------+----------------------+"
                    print ""

                    # 5.5 日志状态
                    print "5.5 InnoDB日志状态"
                    print "+--------------------+----------------------+"
                    print "| 指标               | 值                   |"
                    print "+--------------------+----------------------+"

                    while ((getline line < "'$innodb_tmp'") > 0) {
                        if (line ~ /^Log sequence number/) {
                            if (match(line, /Log sequence number[ ]+([0-9]+)/, arr)) {
                                lsn_mb = int(arr[1] / 1024 / 1024)
                                printf "| %-18s | %-20s |\n", "LSN", lsn_mb " MB"
                            }
                        }
                        if (line ~ /^Log flushed up to/) {
                            if (match(line, /Log flushed up to[ ]+([0-9]+)/, arr)) {
                                lsn_mb = int(arr[1] / 1024 / 1024)
                                printf "| %-18s | %-20s |\n", "Flushed LSN", lsn_mb " MB"
                            }
                        }
                        if (line ~ /^Last checkpoint at/) {
                            if (match(line, /Last checkpoint at[ ]+([0-9]+)/, arr)) {
                                lsn_mb = int(arr[1] / 1024 / 1024)
                                printf "| %-18s | %-20s |\n", "Last Checkpoint", lsn_mb " MB"
                            }
                        }
                    }
                    close("'$innodb_tmp'")
                    print "+--------------------+----------------------+"

                    # 跳过原始的------分隔线，继续处理后面的内容
                    next
                }
                /^------------------------------------------------------$/ && prevline ~ /^5\. InnoDB引擎详细状态信息$/ {
                    # 跳过原始分隔线
                    next
                }
                {
                    prevline = $0
                    print
                }
                ' "$output_file" > "$innodb_formatted"

                # 替换原文件
                mv "$innodb_formatted" "$output_file"
            }
        fi
    else
        print_warning "无法获取 InnoDB 引擎状态，已记录到: $error_file"
    fi

    # 清理临时文件
    rm -f "$innodb_tmp" "$innodb_formatted"

    # 只要有内容，就按"成功（含非致命错误）"处理
    if [ -s "$output_file" ]; then
        update_file_status "04_health_check.txt" "SUCCESS" "MySQL健康检查完成（可能包含非致命错误，详见 .err）"
        print_info "MySQL健康检查已保存到: $output_file"
    else
        update_file_status "04_health_check.txt" "FAILED" "MySQL健康检查失败（无输出）"
        print_error "MySQL健康检查失败（无输出），错误信息保存在: $error_file"
    fi

    # 统一在结尾提示是否有错误/告警
    if [ -s "$error_file" ]; then
        print_warning "健康检查过程中存在错误/告警，请查看: $error_file"
    fi
}

generate_summary() {
    local summary_file="$report_dir/00_inspection_summary.txt"
    print_info "生成巡检报告汇总..."

    update_file_status "00_inspection_summary.txt" "SUCCESS" "巡检汇总"

    {
        echo "======================================="
        echo "MySQL 数据库巡检报告"
        echo "======================================="
        echo "主机名: $(hostname)"
        echo "数据库模式: $db_model"
        echo "巡检时间: $(date)"
        echo "报告目录: $report_dir"
        echo ""
        echo "文件生成状态报告:"
        echo "======================================="

        grep -vE '^[[:space:]]*#' "$file_status_log" | sed '/^[[:space:]]*$/d' | sort -t':' -k1,1 | \
        while IFS=':' read -r filename status description; do
            case "$status" in
                SUCCESS) status_symbol="✓" ;;
                FAILED)  status_symbol="✗" ;;
                SKIPPED) status_symbol="○" ;;
                PENDING) status_symbol="?" ;;
                *)       status_symbol="-" ;;
            esac
            printf "  [%s] %-30s %s\n" "$status_symbol" "$filename" "$description"
        done

        echo ""
        echo "状态说明: ✓=成功生成  ✗=生成失败  ○=跳过执行  ?=待处理"
        echo ""
        echo "生成的文件列表:"
        ls -la "$report_dir" | grep -v ".file_generation_status"
        echo ""
        echo "======================================="
    } > "$summary_file"

    print_info "巡检汇总报告已保存到: $summary_file"
}

# 生成最终的file_status.json（与 oracle_inspection.sh 结构一致）
generate_file_status_json() {
    local json_file="$report_dir/file_status.json"
    print_info "生成file_status.json..."

    cat > "$json_file" << EOF
{
  "inspection_time": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "db_model": "$db_model",
  "mysql_connection": "$(
    if [ "$USE_TCP" -eq 1 ]; then echo "tcp:${MYSQL_HOST}:${MYSQL_PORT}"; elif [ "$USE_SOCK" -eq 1 ]; then echo "socket:${MYSQL_SOCK}"; else echo "none"; fi
  )",
  "files": [
EOF

    local first_entry=true
    grep -vE '^[[:space:]]*#' "$file_status_log" | sed '/^[[:space:]]*$/d' | \
    while IFS=':' read -r filename status description; do
        file_exists=false
        file_size=0
        if [ -f "$report_dir/$filename" ]; then
            file_exists=true
            file_size=$(stat -c%s "$report_dir/$filename" 2>/dev/null || stat -f%z "$report_dir/$filename" 2>/dev/null || echo 0)
        fi

        if [ "$first_entry" = true ]; then
            first_entry=false
        else
            echo "," >> "$json_file"
        fi

        printf '    {\n      "filename": "%s",\n      "status": "%s",\n      "description": "%s",\n      "exists": %s,\n      "size": %s\n    }' \
            "$filename" "$status" "$description" "$file_exists" "$file_size" >> "$json_file"
    done

    cat >> "$json_file" << EOF
  ]
}
EOF

    print_info "状态文件已生成: $json_file"
}
# 主执行流程
main() {
    print_info "开始MySQL数据库巡检..."
    print_info "数据库模式: $db_model"

    # 执行各项收集任务
    collect_system_info
    collect_hardware_info
    collect_sar_report
    collect_xtrabackup_backup_info  # XtraBackup备份部署与清单
    collect_mysql_health_check  # MySQL健康检查

    # 生成汇总报告
    generate_summary

    # 生成file_status.json
    generate_file_status_json

    print_info "=========================================="
    print_info "巡检完成！"
    print_info "报告目录: $report_dir"
    print_info "请查看 00_inspection_summary.txt 了解详细信息"
    print_info "=========================================="
}

# 执行主流程
main

