# 1. 使用说明（请务必阅读）
本 SQL Server 实例巡检方案适用于使用 SSMS 工具配合 `xp_cmdshell` 功能执行数据库日常健康检查，并生成结构化的巡检报告。

##  巡检适用范围
+ 适用于 SQL Server 2008 及以上版本
+ 适用于具有 `sysadmin` 权限的用户
+ 可用于定期生成巡检报告文件（.txt）并归档

##  权限要求
+ 建议使用 `sa` 账户执行，如无法使用，请使用具备 `sysadmin` 权限的 SQL 登录账户
+ 巡检过程中需启用 `xp_cmdshell`，建议执行后立即关闭以保证安全性

##  巡检脚本组成
+ **mssql_healthcheck.sql**：主巡检脚本，执行各项系统视图查询并输出信息
+ **主控脚本（SSMS内执行）**：负责调用 `sqlcmd` 执行主巡检脚本，并将输出内容保存为文件

##  输出结果
+ 输出文件将保存为 `HealthCheck_yyyyMMdd_HHmm.txt`，包含以下内容：
    - 实例信息、数据库信息、内存配置、用户与权限、备份状态、性能视图、等待事件等

## ⚠️ 使用注意事项
1. 请确认 `mssql_healthcheck.sql` 文件路径正确，并上传至服务器本地磁盘（如 `D:\YZJ\`）
2. 请根据实际路径修改主控脚本中输入文件（`-i`）与输出文件（`-o`）参数
3. 巡检结束后请执行关闭 `xp_cmdshell` 的语句，避免潜在安全风险
4. 巡检脚本默认会连接当前数据库实例的默认数据库（如无特殊情况不需指定）

# 2、开启 xp_cmdshell 功能
### 一、启用 xp_cmdshell
```sql
-- 第一步：SSMS 开启高级选项
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;

-- 第二步：SSMS 启用 xp_cmdshell
EXEC sp_configure 'xp_cmdshell', 1;
RECONFIGURE;
```

### 二、测试 xp_cmdshell 是否正常可用
```sql
EXEC xp_cmdshell 'dir C:\';
```

# 3、将巡检脚本上传服务器目录
将 mssql_healthcheck.sql 上传到需要巡检服务器特定目录，命名好。

[mssql_healthcheck.sql](https://www.yuque.com/attachments/yuque/0/2025/sql/12594962/1749546646738-0ad5e0c2-4b1a-4b58-8cdd-d9cbe3c67545.sql)

```sql

--1.查看实例名称和启动时间
PRINT '1.查看实例名称和启动时间';
SELECT @@SERVICENAME
GO
SELECT sqlserver_start_time FROM sys.dm_os_sys_info
GO

--2.查看数据库版本和情况
PRINT '查看版本情况'
SELECT @@VERSION
GO

--3.查看数据库所在服务器的操作系统参数
PRINT '3.查看数据库所在服务器的操作系统参数'
exec master..xp_msver
GO

--4.查看实例启动参数配置
PRINT '4.查看实例启动参数配置'
EXEC sp_readerrorlog 0, 1, 'Registry startup parameters'
GO


--4.查看实例最小和最大内存配置
SELECT c.name,c.value, c.value_in_use
FROM sys.configurations c WHERE c.[name] = 'max server memory (MB)' or c.[name] = 'min server memory (MB)'
GO

--5.查看服务器默认排序规则查询
PRINT '5.查看服务器默认排序规则查询'
EXECUTE sp_helpsort;

--6.查看服务器实例配置的最大并行度和允许的最大连接数
PRINT '6.查看服务器实例配置的最大并行度和允许的最大连接数'
SELECT name,value FROM sys.configurations WHERE name = 'max degree of parallelism' or name = 'user connections'
GO
SELECT name,value FROM sys.configurations WHERE name like 'user connections'

--7.查看SQL Server服务启动用户 *如果allow updates配置为1，则无法调用cmd命令，那么该查询会返回错误
PRINT '7.查看SQL Server服务启动用户'
EXEC sp_configure 'show advanced options', '1'
GO
RECONFIGURE
EXEC sp_configure 'xp_cmdshell', '1' 
GO
RECONFIGURE
PRINT '7.1 查看MSSQLSERVER服务启动用户'

EXEC xp_cmdshell 'sc qc MSSQLSERVER | findstr START_NAME'
GO
PRINT '7.2 查看SQL Agent服务启动用户'

EXEC xp_cmdshell 'sc qc SQLSERVERAGENT | findstr START_NAME'
GO
EXEC sp_configure 'xp_cmdshell', '0' 
GO
RECONFIGURE

--8.查看用户数据库数量
PRINT '8.查看用户数据库数量'
SELECT COUNT (*) FROM sys.databases WHERE database_id>4
GO

--9.查看job数量和链接服务器信息
PRINT '8.查看job数量'
SELECT COUNT(*) FROM msdb.dbo.sysjobs_view
GO
SELECT jv.name,jv.enabled, COUNT(*)'步骤计数' FROM msdb..sysjobsteps  sj,msdb..sysjobs_view jv WHERE sj.job_id = jv.job_id group by jv.name,jv.enabled
GO
PRINT '8.查看链接服务器信息'
exec sp_helplinkedsrvlogin
GO


--10.查看系统数据库信息
PRINT '10.查看系统数据库信息';
SELECT 
    db.name "名称",
    sl.name "所属用户",
    db.compatibility_level "兼容性", db.collation_name "排序规则", db.user_access_desc "用户访问", db.state_desc "状态",db.recovery_model_desc "恢复",
    case db.is_read_only
    when 1 then '只读'
    when 0 then '可读写'
    else '未知'
    END "读写状态"
FROM sys.databases db, sys.syslogins sl
WHERE db.database_id<=4
AND db.owner_sid = sl.sid
GO

--11.查看系统数据库文件信息
PRINT '11.系统数据库文件信息';
SELECT DB_NAME(database_id) "数据库名称",
	case type_desc 
	when 'ROWS' then '数据'
	when 'LOG' then '日志' 
	END "文件类型",
	name "逻辑名称",
	--physical_name "物理文件",
	size*8/1024 "大小(MB)",
	growth "增长大小",
	case is_percent_growth
	when 1 then 'percent'
	when 0 then 'page'
	end "增长类型", 
	case max_size
	when -1 then 'unlimited'
	when 268435456 then '2TB'
	END "最大值"
FROM sys.master_files
WHERE database_id<=4
ORDER BY database_id,"文件类型"
GO

--12.查看用户数据库信息
PRINT '12.用户数据库信息';
SELECT 
    db.name "名称",
    sl.name "所属用户",
    db.compatibility_level "兼容性", db.collation_name "排序规则", db.user_access_desc "用户访问", db.state_desc "状态",db.recovery_model_desc "恢复",
    case db.is_read_only
    when 1 then '只读'
    when 0 then '可读写'
    else '未知'
    END "读写状态"
FROM sys.databases db, sys.syslogins sl
WHERE db.database_id>4
AND db.owner_sid = sl.sid
GO

--12.查看用户数据库文件信息
PRINT '12.用户数据库文件信息'
SELECT DB_NAME(database_id) "数据库名称",
	case type_desc 
	when 'ROWS' then '数据'
	when 'LOG' then '日志' 
	END "文件类型",
	name "逻辑名称",
	--physical_name "物理文件",
	size*8/1024 "大小(MB)",
	growth "增长大小",
	case is_percent_growth
	when 1 then 'percent'
	when 0 then 'page'
	end "增长类型", 
	case max_size
	when -1 then 'unlimited'
	when 268435456 then '2TB'
	END "最大值"
FROM sys.master_files
WHERE database_id>4
ORDER BY database_id,"文件类型"
GO

--13.查看所有数据库日志文件大小及使用情况
PRINT '13.查看所有数据库日志文件大小及使用情况'
dbcc sqlperf(logspace)
GO

--14.查看所有数据库备份情况
PRINT '14.查看所有数据库备份情况'
SELECT bs.database_name "名称",
case bs.type when 'D' then 'FULL' when 'L' then 'LOG' when 'I' then 'INCR' END "类型",
CONVERT(VARCHAR(16),bs.backup_start_date,120) "备份启动时间",
CONVERT(VARCHAR(16),bs.backup_finish_date,120) "备份完成时间",
DATEDIFF(SS,backup_start_date,backup_finish_date) "耗时(秒)",
CAST (bs.backup_size/1024/1024 AS DECIMAL(38,2)) "备份大小(MB)",
bmf.physical_device_name "备份文件"
FROM msdb.dbo.backupset AS bs INNER JOIN msdb.dbo.backupmediafamily AS bmf ON bs.media_set_id=bmf.media_set_id
WHERE bs.backup_start_date>CURRENT_TIMESTAMP-7
ORDER BY bs.database_name,bs.backup_start_date

--15.查看sysadmin下的用户
PRINT '15.sysadmin下的用户'
SELECT p.name AS [loginname] ,
p.type_desc ,
p.is_disabled,
CONVERT(VARCHAR(10),p.create_date ,101) AS [created],
CONVERT(VARCHAR(10),p.modify_date , 101) AS [update]
FROM sys.server_principals p
JOIN sys.syslogins s ON p.sid = s.sid
WHERE p.type_desc IN ('SQL_LOGIN', 'WINDOWS_LOGIN', 'WINDOWS_GROUP')
-- Logins that are not process logins
AND p.name NOT LIKE '##%'
-- Logins that are sysadmins
AND s.sysadmin = 1
GO


--16.查看数据库使用缓存情况
PRINT '16.查看数据库使用缓存情况'
SELECT  COUNT(*) * 8 / 1024 AS 'Cached Size (MB)' ,
        CASE database_id
          WHEN 32767 THEN 'ResourceDb'
          ELSE DB_NAME(database_id)
        END AS 'Database'
FROM    sys.dm_os_buffer_descriptors
GROUP BY DB_NAME(database_id) ,
        database_id
ORDER BY 'Cached Size (MB)' DESC
GO

--17.查看等待事件
PRINT '17.查看等待事件'
SELECT TOP (10)
        wait_type ,
        waiting_tasks_COUNT ,
        ( wait_time_ms - signal_wait_time_ms ) AS resource_wait_time ,
        max_wait_time_ms ,
        CASE waiting_tasks_COUNT
          WHEN 0 THEN 0
          ELSE wait_time_ms / waiting_tasks_COUNT
        END AS avg_wait_time
FROM    sys.dm_os_wait_stats
WHERE   wait_type NOT LIKE '%SLEEP%'   -- 去除不相关的等待类型
        AND wait_type NOT LIKE 'XE%'
        AND wait_type NOT IN -- 去除系统类型   
( 'KSOURCE_WAKEUP', 'BROKER_TASK_STOP', 'FT_IFTS_SCHEDULER_IDLE_WAIT',
  'SQLTRACE_BUFFER_FLUSH', 'CLR_AUTO_EVENT', 'BROKER_EVENTHANDLER',
  'BAD_PAGE_PROCESS', 'BROKER_TRANSMITTER', 'CHECKPOINT_QUEUE',
  'DBMIRROR_EVENTS_QUEUE', 'SQLTRACE_BUFFER_FLUSH', 'CLR_MANUAL_EVENT',
  'ONDEMAND_TASK_QUEUE', 'REQUEST_FOR_DEADLOCK_SEARCH', 'LOGMGR_QUEUE',
  'BROKER_RECEIVE_WAITFOR', 'PREEMPTIVE_OS_GETPROCADDRESS',
  'PREEMPTIVE_OS_AUTHENTICATIONOPS', 'BROKER_TO_FLUSH' )
ORDER BY wait_time_ms DESC
GO


--18.查看最消耗CPU资源的SQL HANDLE（TOP 10）
PRINT '18.查看最消耗CPU资源的SQL HANDLE（TOP 10）'
SELECT TOP (10)
        qs.sql_handle ,
        execution_count ,
        total_worker_time / 1000 AS total_worker_time_ms ,
        ( total_worker_time / 1000 ) / execution_count AS avg_worker_time_ms , 
        total_elapsed_time / 1000 AS total_elapsed_time_ms ,
        ( total_elapsed_time / 1000 ) / execution_count AS avg_elapsed_time_ms,
		total_logical_reads,last_logical_reads,total_physical_reads,last_physical_reads,creation_time
FROM    sys.dm_exec_query_stats qs
ORDER BY total_worker_time DESC
GO
PRINT '18.查看最消耗CPU资源的SQL HANDLE（TOP 10）对应的语句'
SELECT TOP (10)
         qs.sql_handle ,SUBSTRING(ST.text, ( QS.statement_start_offset / 2 ) + 1,
                  ( ( CASE statement_end_offset
                        WHEN -1 THEN DATALENGTH(st.text)
                        ELSE QS.statement_end_offset
                      END - QS.statement_start_offset ) / 2 ) + 1) AS statement_text 
FROM    sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY total_worker_time DESC
GO

--19.查看执行时间最长的SQL HANDLE（TOP 10）
PRINT '19.查看执行时间最长的SQL HANDLE（TOP 10）'
SELECT TOP (10)
        qs.sql_handle ,execution_count,
        total_elapsed_time / 1000 AS  total_elapsed_time_ms,
		last_elapsed_time / 1000 AS  last_elapsed_time_ms,
		( total_elapsed_time / 1000 ) / execution_count AS  avg_elapsed_time_ms,
        total_worker_time / 1000 AS total_worker_time_ms ,
        ( total_worker_time / 1000 ) / execution_count AS avg_worker_time_ms , 
        total_elapsed_time / 1000 AS total_elapsed_time_ms ,
        ( total_elapsed_time / 1000 ) / execution_count AS avg_elapsed_time_ms,
		total_logical_reads,last_logical_reads,total_physical_reads,last_physical_reads,creation_time
FROM    sys.dm_exec_query_stats qs
ORDER BY qs.total_elapsed_time DESC
GO
PRINT '19.查看执行时间最长的SQL HANDLE（TOP 10）对应的语句'
SELECT TOP (10)
         qs.sql_handle ,SUBSTRING(ST.text, ( QS.statement_start_offset / 2 ) + 1,
                  ( ( CASE statement_end_offset
                        WHEN -1 THEN DATALENGTH(st.text)
                        ELSE QS.statement_end_offset
                      END - QS.statement_start_offset ) / 2 ) + 1) AS statement_text 
FROM    sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY qs.total_elapsed_time DESC

--20.查看最多逻辑读的SQL HANDLE（TOP 10）
PRINT '20.查看最多逻辑读的SQL HANDLE（TOP 10）'
SELECT TOP (10)
        sql_handle, execution_count,
		total_logical_reads / execution_count AS avg_total_logical_reads,
		last_logical_reads,
		last_elapsed_time / 1000 AS  last_elapsed_time_ms,		
        total_worker_time / 1000 AS total_worker_time_ms ,
        ( total_worker_time / 1000 ) / execution_count AS avg_worker_time_ms , 
        total_elapsed_time / 1000 AS total_elapsed_time_ms ,
        ( total_elapsed_time / 1000 ) / execution_count AS avg_elapsed_time_ms,
		creation_time				
FROM    sys.dm_exec_query_stats
ORDER BY total_logical_reads DESC
GO
PRINT '20.查看最多逻辑读的SQL HANDLE（TOP 10）对应的语句'
SELECT TOP (10)
         qs.sql_handle ,SUBSTRING(ST.text, ( QS.statement_start_offset / 2 ) + 1,
                  ( ( CASE statement_end_offset
                        WHEN -1 THEN DATALENGTH(st.text)
                        ELSE QS.statement_end_offset
                      END - QS.statement_start_offset ) / 2 ) + 1) AS statement_text 
FROM    sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY total_logical_reads DESC
GO

--21.查看最多物理读的SQL HANDLE（TOP 10）
PRINT '21.查看最多物理读的SQL HANDLE（TOP 10）'
SELECT TOP (10)
        qs.sql_handle , execution_count ,
		total_physical_reads / execution_count AS avg_total_physical_reads,
		last_physical_reads,
		last_elapsed_time / 1000 AS  last_elapsed_time_ms,
        total_worker_time / 1000 AS total_worker_time_ms ,
        ( total_worker_time / 1000 ) / execution_count AS avg_worker_time_ms , 
        total_elapsed_time / 1000 AS total_elapsed_time_ms ,
        ( total_elapsed_time / 1000 ) / execution_count AS avg_elapsed_time_ms,
		creation_time				
FROM    sys.dm_exec_query_stats qs
ORDER BY total_physical_reads DESC
GO
PRINT '21.查看最多物理读的SQL HANDLE（TOP 10）对应的语句'
SELECT TOP (10)
         qs.sql_handle ,SUBSTRING(ST.text, ( QS.statement_start_offset / 2 ) + 1,
                  ( ( CASE statement_end_offset
                        WHEN -1 THEN DATALENGTH(st.text)
                        ELSE QS.statement_end_offset
                      END - QS.statement_start_offset ) / 2 ) + 1) AS statement_text 
FROM    sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY total_physical_reads DESC
GO
		
--22.查看消耗CPU最多的存储过程（TOP 10）
PRINT '22.查看消耗CPU最多的存储过程（TOP 10）'
SELECT TOP (10) p.name AS [SP Name] ,qs.execution_count,
		qs.total_worker_time/1000 AS total_worker_time_ms,
        ( qs.total_worker_time / 1000 ) / qs.execution_count AS avg_worker_time_ms , 		
		qs.last_elapsed_time,
        qs.total_physical_reads AS [TotalPhysicalReads] ,
        qs.total_logical_reads AS [TotalLogicalReads] ,
        qs.total_physical_reads / qs.execution_count AS [AvgPhysicalReads] ,
        qs.cached_time
FROM    sys.procedures AS p
        INNER JOIN sys.dm_exec_procedure_stats AS qs ON p.[object_id] = qs.[object_id]
WHERE   qs.database_id = DB_ID()
        AND qs.total_physical_reads > 0
ORDER BY qs.total_worker_time DESC;
GO

--23.最多逻辑读的存储过程（TOP 10）
PRINT '23.最多逻辑读的存储过程（TOP 10）'
SELECT TOP (10) p.name AS [SP Name] ,qs.execution_count ,
		qs.total_worker_time/1000 AS total_worker_time_ms,
        ( qs.total_worker_time / 1000 ) / qs.execution_count AS avg_worker_time_ms , 		
		qs.last_elapsed_time,
        qs.total_logical_reads AS [TotalLogicalReads] ,
        qs.total_logical_reads/ qs.execution_count AS [AvgLogicalReads] ,
        qs.total_physical_reads AS [TotalPhysicalReads] ,
        qs.total_physical_reads / qs.execution_count AS [AvgPhysicalReads] ,
        qs.cached_time
FROM    sys.procedures AS p
        INNER JOIN sys.dm_exec_procedure_stats AS qs ON p.[object_id] = qs.[object_id]
WHERE   qs.database_id = DB_ID()
        AND qs.total_physical_reads > 0
ORDER BY qs.total_logical_reads DESC ,
        qs.total_physical_reads DESC;
GO

--24.最多物理读的存储过程（TOP 10）
PRINT '24.最多物理读的存储过程（TOP 10）'
SELECT TOP (10)  p.name AS [SP Name] ,qs.execution_count ,
		qs.total_worker_time/1000 AS total_worker_time_ms,
        ( qs.total_worker_time / 1000 ) / qs.execution_count AS avg_worker_time_ms ,
        qs.total_physical_reads AS [TotalPhysicalReads] ,
        qs.total_physical_reads / qs.execution_count AS [AvgPhysicalReads] ,
        qs.total_logical_reads AS [TotalLogicalReads] ,
        qs.total_logical_reads/ qs.execution_count AS [AvgLogicalReads] ,
        qs.cached_time
FROM    sys.procedures AS p
        INNER JOIN sys.dm_exec_procedure_stats AS qs ON p.[object_id] = qs.[object_id]
WHERE   qs.database_id = DB_ID()
        AND qs.total_physical_reads > 0
ORDER BY qs.total_physical_reads DESC ,
        qs.total_logical_reads DESC;
GO
```

# 4、执行巡检脚本
**使用 ssms 执行以下脚本**

```sql
-- 0. 生成文件路径（带日期） D:\YZJ\ 这个你要改好路径
DECLARE @out nvarchar(4000);
SELECT @out = N'D:\YZJ\HealthCheck_' + FORMAT(GETDATE(), N'yyyyMMdd_HHmm') + N'.txt';

-- 1. 把本脚本保存到磁盘（或直接嵌入 -Q 参数） D:\YZJ\ 这个你要改好路径
DECLARE @sqlfile nvarchar(4000) = N'D:\YZJ\mssql_healthcheck.sql';

-- 2. 用 sqlcmd 调用并输出
DECLARE @cmd nvarchar(4000) =
N'cmd /c sqlcmd -E -S ' + QUOTENAME(@@SERVERNAME, '"') +
N' -i "' + @sqlfile + N'"' +
N' -o "' + @out + N'" -W -w 1024 -s ","';

EXEC master..xp_cmdshell @cmd, no_output;   
PRINT N'巡检报告已生成：' + @out;

```

# 5、 巡检完成后关闭 xp_cmdshell 功能
⚠️ 建议关闭这个功能。

### 一、关闭xp_cmdshell 功能
```sql
-- 关闭 xp_cmdshell
EXEC sp_configure 'xp_cmdshell', 0;
RECONFIGURE;

-- 可选：关闭高级选项
EXEC sp_configure 'show advanced options', 0;
RECONFIGURE;
```

### 二、检查 xp_cmdshell 是否关闭
```sql
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;
GO

EXEC sp_configure 'xp_cmdshell';
GO
```

# 6、 sqlserver 性能报告功能安装使用（可选）
[SQL sever配置数据收集器.doc](https://www.yuque.com/attachments/yuque/0/2025/doc/12594962/1749608832074-219c5a40-b259-4de8-b618-582e7f4cffc0.doc)

# 




















