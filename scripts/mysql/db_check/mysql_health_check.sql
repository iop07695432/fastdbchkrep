-- ================================================================
-- MySQL Health Check SQL Script
-- 版本: v1.0
-- 作者: yzj (须佐)
-- 说明: MySQL数据库健康检查SQL脚本，用于收集数据库状态和性能信息
-- 使用方法: mysql -u<user> -p<password> < mysql_health_check.sql > health_check_output.txt
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
    @@transaction_isolation AS 'TRANSACTION_ISOLATION',  -- MySQL 8.0使用transaction_isolation替代tx_isolation
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
    CONCAT(
        IF(Select_priv='Y', 'SELECT ', ''),
        IF(Insert_priv='Y', 'INSERT ', ''),
        IF(Update_priv='Y', 'UPDATE ', ''),
        IF(Delete_priv='Y', 'DELETE ', ''),
        IF(Create_priv='Y', 'CREATE ', ''),
        IF(Drop_priv='Y', 'DROP ', ''),
        IF(Grant_priv='Y', 'GRANT ', ''),
        IF(References_priv='Y', 'REFERENCES ', ''),
        IF(Index_priv='Y', 'INDEX ', ''),
        IF(Alter_priv='Y', 'ALTER ', ''),
        IF(Create_tmp_table_priv='Y', 'CREATE_TMP ', ''),
        IF(Lock_tables_priv='Y', 'LOCK_TABLES ', ''),
        IF(Create_view_priv='Y', 'CREATE_VIEW ', ''),
        IF(Show_view_priv='Y', 'SHOW_VIEW ', ''),
        IF(Create_routine_priv='Y', 'CREATE_ROUTINE ', ''),
        IF(Alter_routine_priv='Y', 'ALTER_ROUTINE ', ''),
        IF(Execute_priv='Y', 'EXECUTE ', ''),
        IF(Event_priv='Y', 'EVENT ', ''),
        IF(Trigger_priv='Y', 'TRIGGER ', '')
    ) AS 'PRIVILEGES'
FROM mysql.db
ORDER BY User, Host, Db
LIMIT 50;

-- 4. 密码策略和过期账户
\! echo ""
\! echo "4. 密码策略和账户状态检查"
SELECT 
    User AS 'USER',
    Host AS 'HOST',
    CASE 
        WHEN password_expired = 'Y' THEN '已过期'
        WHEN password_lifetime IS NOT NULL AND 
             DATEDIFF(NOW(), password_last_changed) > password_lifetime THEN '即将过期'
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

-- B1. 内存相关参数 (Memory Parameters)
\! echo "[DB_PERF_PARAMS_START]"
\! echo "B1. 内存相关参数 (Memory Parameters)"
SELECT 
    @@key_buffer_size/1024/1024 AS 'KEY_BUFFER_SIZE_MB',
    -- MySQL 8.0已移除查询缓存
    @@tmp_table_size/1024/1024 AS 'TMP_TABLE_SIZE_MB',
    @@max_heap_table_size/1024/1024 AS 'MAX_HEAP_TABLE_SIZE_MB',
    @@sort_buffer_size/1024/1024 AS 'SORT_BUFFER_SIZE_MB',
    @@join_buffer_size/1024/1024 AS 'JOIN_BUFFER_SIZE_MB',
    @@read_buffer_size/1024/1024 AS 'READ_BUFFER_SIZE_MB',
    @@read_rnd_buffer_size/1024/1024 AS 'READ_RND_BUFFER_SIZE_MB';

-- B2. InnoDB内存参数
\! echo ""
\! echo "B2. InnoDB内存参数"
SELECT 
    @@innodb_buffer_pool_size/1024/1024/1024 AS 'INNODB_BUFFER_POOL_SIZE_GB',
    @@innodb_buffer_pool_instances AS 'BUFFER_POOL_INSTANCES',
    @@innodb_log_buffer_size/1024/1024 AS 'INNODB_LOG_BUFFER_SIZE_MB',
    @@innodb_sort_buffer_size/1024/1024 AS 'INNODB_SORT_BUFFER_SIZE_MB',
    @@innodb_page_size/1024 AS 'INNODB_PAGE_SIZE_KB';

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
    @@thread_stack/1024 AS 'THREAD_STACK_KB';

-- B4. 其他性能参数
\! echo ""
\! echo "B4. 其他性能参数"
SELECT 
    @@table_open_cache AS 'TABLE_OPEN_CACHE',
    @@table_definition_cache AS 'TABLE_DEFINITION_CACHE',
    @@open_files_limit AS 'OPEN_FILES_LIMIT',
    @@max_allowed_packet/1024/1024 AS 'MAX_ALLOWED_PACKET_MB';

\! echo "[DB_PERF_PARAMS_END]"
\! echo ""

-- ==============================================================================
-- 第四部分：数据库日志路径 (Database Log Paths)
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
    @@binlog_expire_logs_seconds/86400 AS 'EXPIRE_LOGS_DAYS',  -- MySQL 8.0使用binlog_expire_logs_seconds
    @@max_binlog_size/1024/1024 AS 'MAX_BINLOG_SIZE_MB',
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
\! echo "11. 完整进程列表（SHOW FULL PROCESSLIST）"
SHOW FULL PROCESSLIST;

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
    'Com_select',
    'Com_insert',
    'Com_update',
    'Com_delete',
    'Com_replace',
    'Slow_queries',
    'Select_full_join',
    'Select_scan',
    'Sort_scan',
    'Sort_merge_passes'
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
    'Innodb_os_log_written',
    'Innodb_log_waits'
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
        WHEN @@innodb_buffer_pool_size < (SELECT SUM(data_length + index_length) FROM information_schema.tables WHERE engine = 'InnoDB') * 0.7
        THEN CONCAT('建议增加 innodb_buffer_pool_size, 当前值: ', ROUND(@@innodb_buffer_pool_size/1024/1024/1024, 2), 'GB')
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
        WHEN @@long_query_time > 2
        THEN CONCAT('建议降低 long_query_time, 当前值: ', @@long_query_time, '秒')
        ELSE '慢查询配置合理'
    END AS 'SLOW_QUERY_RECOMMENDATION';

\! echo ""
\! echo "4. 二进制日志建议:"
SELECT 
    CASE 
        WHEN @@log_bin = 0
        THEN '警告: 二进制日志未开启，无法进行主从复制和时间点恢复'
        WHEN @@sync_binlog != 1
        THEN CONCAT('建议设置 sync_binlog=1 以确保数据安全, 当前值: ', @@sync_binlog)
        ELSE '二进制日志配置合理'
    END AS 'BINLOG_RECOMMENDATION';

\! echo ""
\! echo "==================== HEALTH CHECK COMPLETED ===================="
\! echo "检查时间: " 
SELECT NOW() AS 'COMPLETION_TIME';
\! echo "============================================================="
