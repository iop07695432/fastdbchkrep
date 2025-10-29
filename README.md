# FastDBCheckRep

**数据库巡检报告生成工具** - 让 DBA 专注于数据库分析而非报告格式化

[![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 📖 项目概述

### 核心定位

FastDBCheckRep 是一个现代化的数据库巡检和报告生成工具包，旨在为数据库管理员（DBA）提供自动化、专业化的数据库健康检查和报告生成服务。

### 解决的问题

在企业级数据库管理领域，传统的数据库巡检工作面临以下挑战：

- **数据收集复杂性**：需要从多个系统层面（操作系统、数据库实例、存储等）收集大量指标数据
- **报告格式化耗时**：DBA 需要花费大量时间将技术数据转换为业务可读的专业报告
- **一致性难以保证**：手工报告容易出现格式不统一、遗漏关键信息等问题
- **可视化要求提升**：现代企业对数据可视化和图表展示的要求越来越高

### 核心理念

**让 DBA 专注于数据库分析而非报告格式化**

- 自动化数据收集 → 解析 → 报告生成 → PDF 导出全流程
- 标准化、专业化的报告输出，便于项目交付验收
- 高质量的图表和可视化输出

### 目标用户

- 数据库管理员（DBA）
- 运维工程师
- 技术咨询公司
- 需要定期生成数据库巡检报告的企业

---

## ✨ 功能特性

### 已完整实现的功能

#### Oracle 数据库支持（✅ 完整实现）

- **单机模式（ONE）**：支持 Oracle 11g、12c、19c 非多租户版本
- **RAC 模式**：支持 2-4 节点 Oracle RAC 集群
  - 自动合并多节点报告
  - 图片路径自动重写
  - 节点一致性验证
- **AWR 报告处理**：高保真 HTML 截图（支持按 summary 文本灵活匹配截取 AWR 各章节）
- **性能监控图表**：CPU、内存、磁盘 I/O 趋势图（Matplotlib 生成）

#### MySQL 数据库支持（✅ 完整实现）

- **单机模式（ONE）**：完整的 MySQL 巡检数据解析
- **独立解析器**：专用的 MySQL 元数据解析器

#### SQL Server 数据库支持（🚧 部分实现）

- **版本支持**：2005、2008、2012、2014、2016、2017、2019
- **直接 TXT 解析**：跳过 JSON 中间层，简化流程
- **智能版本检测**：通过版本字符串和提示语双重判断
- **当前状态**：解析器和报告生成器已实现，持续优化中

### 技术亮点

#### 🎨 AWR HTML 截图解决方案（里程碑级创新）

- **高保真截图**：使用 Playwright 实现 AWR 报告的高质量截图
- **自动化处理**：无需手工截图和裁剪
- **图片压缩优化**：Pillow 压缩至 <200KB
- **技术价值**：将 AWR 报告处理时间从小时级降低到分钟级

#### 📊 性能监控图表生成

- **CPU 使用率趋势图**：user/system/iowait/idle 多维度展示
- **内存使用率图表**：双 Y 轴（百分比 + GB）
- **磁盘 I/O 趋势图**：读写性能可视化
- **高质量输出**：300 DPI，适合打印和展示

#### 🔄 RAC 多节点支持

- 支持 2-4 节点（不仅限于 2 节点）
- 自动合并节点报告
- 图片路径自动重写
- 节点一致性验证

#### 📦 二进制分发支持

- PyInstaller 打包，无需 Python 环境即可运行
- Playwright 浏览器可打包到二进制中
- 适合客户现场部署

---

## 🏗️ 技术架构

### 技术栈

- **Python 3.6+**：现代化特性（类型注解、dataclass、pathlib）
- **Playwright**：高质量 HTML 截图和 PDF 生成
- **Matplotlib**：性能监控图表生成
- **Markdown**：中间格式，易于编辑和版本控制
- **Pillow**：图片压缩优化
- **Loguru**：结构化日志记录

### 分层架构

```
┌─────────────────────────────────────┐
│  CLI 层: fastdbchkrep.sh + main.py │
├─────────────────────────────────────┤
│  数据收集层: Shell/PowerShell 脚本  │
├─────────────────────────────────────┤
│  数据解析层: meta/ (Parser)         │
├─────────────────────────────────────┤
│  报告生成层: report/ (Generator)    │
├─────────────────────────────────────┤
│  可视化层: common/ (Charts+HTML)    │
├─────────────────────────────────────┤
│  导出层: pdf/ (HTML→PDF)            │
└─────────────────────────────────────┘
```

### 数据流程

#### Oracle/MySQL 流程（JSON 中间层）

```
原始文件(多个) → parse → JSON 元数据 → report → MD + HTML → htmltopdf → PDF
```

#### SQL Server 流程（直接解析）

```
单个 TXT 文件 → report → MD + HTML → htmltopdf → PDF
```

---

## 📊 数据库支持矩阵

| 数据库 | 模式 | Parse | Report | PDF | 状态 | 备注 |
|--------|------|-------|--------|-----|------|------|
| **Oracle** | ONE | ✅ | ✅ | ✅ | 完整实现 | 11g/12c/19c 非多租户 |
| **Oracle** | RAC | ✅ | ✅ | ✅ | 完整实现 | 2-4 节点支持 |
| **MySQL** | ONE | ✅ | ✅ | ✅ | 完整实现 | 独立解析器 |
| **SQL Server** | ONE | N/A | ✅ | ✅ | 部分实现 | 2005-2019 支持 |
| **PostgreSQL** | - | 🚧 | ❌ | ❌ | 规划中 | CLI 占位，暂无报告生成器 |

**图例**：
- ✅ 完整实现
- 🚧 部分实现/开发中
- ❌ 未实现
- N/A 不适用

**说明**：
- PostgreSQL 目前仅在 CLI 中预留了 `-dbtype postgresql` 参数，解析器已定义必需文件列表，但报告生成器尚未实现

---

## 🚀 安装与依赖

### Python 版本要求

- Python 3.6 或更高版本

### 依赖安装

1. **安装 Python 依赖包**

```bash
pip install -r requirements.txt
```

2. **安装 Playwright 浏览器**

```bash
# 安装 Chromium 浏览器（用于 HTML 截图和 PDF 生成）
playwright install chromium
```

### 依赖包说明

```
loguru>=0.5.0          # 日志框架
matplotlib>=3.0.0      # 图表生成
numpy>=1.20.0          # 数值计算
playwright>=1.40.0     # HTML 渲染和截图
Pillow>=8.0.0          # 图片处理
markdown>=3.4.0        # Markdown 转换
```

---

## 📖 使用方法

FastDBCheckRep 提供三大核心命令：

1. **parse** - 解析原始数据生成 JSON 元数据
2. **report** - 生成 Markdown 和 HTML 报告
3. **htmltopdf** - 转换 HTML 为 PDF

### 命令 1: parse - 解析原始数据

#### 用途

将数据库巡检脚本收集的原始文件解析为结构化的 JSON 元数据。

#### 语法

```bash
./fastdbchkrep.sh parse [选项]
```

#### 参数说明

**单机模式参数：**
- `-import_dir <路径>` - 输入目录路径（必需）

**RAC 模式参数：**
- `-import_dir_1 <路径>` - 节点 1 输入目录（必需）
- `-import_dir_2 <路径>` - 节点 2 输入目录（必需）
- `-import_dir_3 <路径>` - 节点 3 输入目录（可选）
- `-import_dir_4 <路径>` - 节点 4 输入目录（可选）

**通用参数：**
- `-dbtype <类型>` - 数据库类型：`oracle`、`mysql`、`postgresql`、`sqlserver`（必需）
- `-dbmodel <模型>` - 数据库模型：`one`（单机）、`rac`（集群）（必需）
- `-jsonout <路径>` - JSON 输出目录（必需）
- `--identifier <标识>` - 自定义标识符（可选，默认自动生成）
- `--quiet` - 静默模式（可选）

#### 使用示例

**示例 1：解析 Oracle 单机数据**

```bash
./fastdbchkrep.sh parse \
  -import_dir "data/file/oracle/hnkafka_oms_20250902" \
  -dbtype oracle \
  -dbmodel one \
  -jsonout "data/json"

# 输出文件：data/json/(oracle-one)-hnkafka_oms_20250902.json
```

**示例 2：解析 Oracle RAC 数据（2 节点）**

```bash
./fastdbchkrep.sh parse \
  -import_dir_1 "data/file/oracle/rac_node1_20250902" \
  -import_dir_2 "data/file/oracle/rac_node2_20250902" \
  -dbtype oracle \
  -dbmodel rac \
  -jsonout "data/json"

# 输出文件：data/json/(oracle-rac)-rac_cluster_20250902.json
```

**示例 3：解析 MySQL 数据**

```bash
./fastdbchkrep.sh parse \
  -import_dir "data/file/mysql/mysql_server_20250902" \
  -dbtype mysql \
  -dbmodel one \
  -jsonout "data/json"

# 输出文件：data/json/(mysql-one)-mysql_server_20250902.json
```

**输出文件命名规则**：

生成的 JSON 文件名格式为：`({dbtype}-{dbmodel})-{identifier}.json`

- `{dbtype}`：数据库类型（oracle、mysql 等）
- `{dbmodel}`：数据库模型（one、rac）
- `{identifier}`：唯一标识符（自动生成或通过 `--identifier` 参数指定）

---

### 命令 2: report - 生成巡检报告

#### 用途

从 JSON 元数据文件（Oracle/MySQL）或 TXT 文件（SQL Server）生成 Markdown 和 HTML 格式的巡检报告。

#### 语法

```bash
./fastdbchkrep.sh report [选项]
```

#### 参数说明

**输入参数（互斥，必须选择一个）：**
- `-import_json <路径>` - 输入 JSON 文件路径（Oracle/MySQL）
- `-import_txt <路径>` - 输入 TXT 文件路径（SQL Server）

**必需参数：**
- `-mdout <路径>` - Markdown 输出目录
- `-company_name <名称>` - 公司名称（`鼎诚科技` 或 `伟宏智能`）
- `-user_company <名称>` - 客户单位名称
- `-application_name <名称>` - 应用系统名称

**可选参数：**
- `-suptime <小时>` - 现场支持总时间（小时）
- `-supname <姓名>` - 支持工程师姓名
- `--quiet` - 静默模式

#### 使用示例

**示例 1：生成 Oracle 报告（从 JSON）**

```bash
./fastdbchkrep.sh report \
  -import_json "data/json/(oracle-one)-hnkafka_oms_20250902.json" \
  -mdout "data/md" \
  -company_name "鼎诚科技" \
  -user_company "海南电网" \
  -application_name "OMS调度系统" \
  -suptime "4" \
  -supname "张工"
```

**示例 2：生成 MySQL 报告（从 JSON）**

```bash
./fastdbchkrep.sh report \
  -import_json "data/json/(mysql-one)-mysql_server_20250902.json" \
  -mdout "data/md" \
  -company_name "伟宏智能" \
  -user_company "广州银行" \
  -application_name "核心业务系统"
```

**示例 3：生成 SQL Server 报告（从 TXT）**

```bash
./fastdbchkrep.sh report \
  -import_txt "data/file/sqlserver/172.18.0.2-HealthCheck-20251023.txt" \
  -mdout "data/md" \
  -company_name "鼎诚科技" \
  -user_company "海南电网" \
  -application_name "OMS调度系统" \
  -suptime "4" \
  -supname "王工"
```

#### 输出说明

报告生成后，会在 `-mdout` 指定的目录下创建以下文件：

**Oracle 单机（ONE）输出结构：**
```
data/md/
└── oracle/
    └── {hostname}_{sid}_{date}/
        ├── {hostname}_{sid}.md              # Markdown 源文件
        ├── {hostname}_{sid}.editable.html  # 可编辑 HTML（用于 PDF 转换）
        ├── server_picture/                  # 性能监控图表
        │   ├── cpu_usage_chart.png
        │   ├── memory_usage_chart.png
        │   └── disk_io_chart.png
        └── awr_picture/                     # AWR 报告截图
            ├── awr_database_info.png
            ├── awr_load_profile.png
            └── ...
```

**Oracle RAC 输出结构：**
```
data/md/
└── oracle/
    └── {identifier}/
        ├── {identifier}.rac.md              # RAC 合并 Markdown 源文件
        ├── {identifier}.rac.editable.html  # RAC 可编辑 HTML（用于 PDF 转换）
        ├── server_picture/                  # 性能监控图表（合并后）
        │   ├── cpu_usage_chart.png
        │   ├── memory_usage_chart.png
        │   └── disk_io_chart.png
        └── awr_picture/                     # AWR 报告截图（合并后）
            ├── awr_database_info.png
            ├── awr_load_profile.png
            └── ...
```

**说明**：
- Oracle RAC 报告使用 `.rac.md` 和 `.rac.editable.html` 后缀，以区分单机报告
- `{identifier}` 为解析时自动生成或通过 `--identifier` 参数指定的唯一标识符

**MySQL 输出结构：**
```
data/md/
└── mysql/
    └── {dirname}/
        ├── {hostname}_{sid}.md              # Markdown 源文件
        ├── {hostname}_{sid}.editable.html  # 可编辑 HTML（用于 PDF 转换）
        └── server_picture/                  # 性能监控图表
            ├── cpu_usage_chart.png
            ├── memory_usage_chart.png
            └── disk_io_chart.png
```

**SQL Server 输出结构：**
```
data/md/
└── sqlserver/
    └── {ip}/
        ├── HealthCheck.md              # Markdown 源文件
        └── HealthCheck.editable.html   # 可编辑 HTML（用于 PDF 转换）
```

---

### 命令 3: htmltopdf - 转换 HTML 为 PDF

#### 用途

将可编辑的 HTML 文件转换为 PDF 格式，同时支持建议章节的编辑内容保存。

#### 语法

```bash
./fastdbchkrep.sh htmltopdf [选项]
```

#### 参数说明

- `-import_html <路径>` - 输入 HTML 文件路径（建议使用 `*.editable.html`）（必需）
- `-pdfout <路径>` - 输出目录路径（PDF 文件保存位置）（必需）
- `-pdfname <名称>` - 输出文件名（不含扩展名）（必需）

#### 使用示例

**示例 1：转换 Oracle 报告为 PDF**

```bash
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/oracle/hnkafka_oms_20250902/hnkafka_oms.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_海南电网_OMS系统_ORACLE数据库巡检报告_20250902"
```

**示例 2：转换 SQL Server 报告为 PDF**

```bash
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/sqlserver/172.18.0.2/HealthCheck.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_海南电网_OMS系统_SQLSERVER数据库巡检报告_20251023"
```

#### 输出说明

转换完成后，会在 `-pdfout` 指定的目录下生成以下文件：

```
data/pdf/
└── {pdfname}.pdf                    # 最终 PDF 文件
```

同时，在原 HTML 文件所在目录会生成：

```
{basename}.final.html                # 最终版 HTML（包含编辑内容）
```

---

## 📁 目录结构

```
fastdbchkrep/
├── data/                           # 数据文件目录
│   ├── file/                       # 原始数据文件
│   │   ├── oracle/                 # Oracle 巡检数据
│   │   ├── mysql/                  # MySQL 巡检数据
│   │   └── sqlserver/              # SQL Server 巡检数据
│   ├── json/                       # JSON 元数据文件
│   ├── md/                         # Markdown 和 HTML 报告
│   │   ├── oracle/
│   │   ├── mysql/
│   │   └── sqlserver/
│   ├── pdf/                        # PDF 报告
│   └── log/                        # 日志文件
├── src/                            # 源代码目录
│   └── fastdbchkrep/
│       ├── meta/                   # 数据解析层
│       │   ├── parser.py           # Oracle 解析器
│       │   ├── rac_parser.py       # RAC 解析器
│       │   ├── mysql/              # MySQL 解析器
│       │   └── json_schema.py      # JSON Schema 验证
│       ├── report/                 # 报告生成层
│       │   ├── api.py              # 统一 API 接口
│       │   ├── oracle/             # Oracle 报告生成器
│       │   ├── mysql/              # MySQL 报告生成器
│       │   ├── sqlserver/          # SQL Server 报告生成器
│       │   ├── common/             # 共享工具
│       │   │   ├── chart_utils.py  # 图表生成
│       │   │   ├── html_capture.py # HTML 截图
│       │   │   └── template_config.py # 模板配置
│       │   └── pdf/                # PDF 转换
│       │       └── converter.py
│       └── resource/               # 资源文件
│           └── icob/               # 公司 Logo
├── scripts/                        # 数据收集脚本
│   ├── oracle/                     # Oracle 巡检脚本
│   └── mysql/                      # MySQL 巡检脚本
├── tests/                          # 测试文件
├── main.py                         # Python 入口脚本
├── fastdbchkrep.sh                 # Shell 入口脚本
├── requirements.txt                # Python 依赖
├── fastdbchkrep.spec               # PyInstaller 打包配置
└── README.md                       # 项目文档
```

---

## 🔧 完整使用流程示例

### Oracle 单机完整流程

```bash
# 步骤 1：解析原始数据
./fastdbchkrep.sh parse \
  -import_dir "data/file/oracle/hnkafka_oms_20250902" \
  -dbtype oracle \
  -dbmodel one \
  -jsonout "data/json"

# 步骤 2：生成报告
./fastdbchkrep.sh report \
  -import_json "data/json/(oracle-one)-hnkafka_oms_20250902.json" \
  -mdout "data/md" \
  -company_name "鼎诚科技" \
  -user_company "海南电网" \
  -application_name "OMS调度系统"

# 步骤 3：转换为 PDF
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/oracle/hnkafka_oms_20250902/hnkafka_oms.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_海南电网_OMS系统_ORACLE数据库巡检报告_20250902"
```

### Oracle RAC 完整流程

```bash
# 步骤 1：解析 RAC 多节点数据
./fastdbchkrep.sh parse \
  -import_dir_1 "data/file/oracle/rac_node1_20250902" \
  -import_dir_2 "data/file/oracle/rac_node2_20250902" \
  -dbtype oracle \
  -dbmodel rac \
  -jsonout "data/json"

# 步骤 2：生成报告（自动合并节点）
./fastdbchkrep.sh report \
  -import_json "data/json/(oracle-rac)-rac_cluster_20250902.json" \
  -mdout "data/md" \
  -company_name "鼎诚科技" \
  -user_company "海南电网" \
  -application_name "OMS调度系统"

# 步骤 3：转换为 PDF
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/oracle/rac_cluster_20250902/rac_cluster_20250902.rac.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_海南电网_OMS系统_ORACLE_RAC数据库巡检报告_20250902"
```

### MySQL 完整流程

```bash
# 步骤 1：解析原始数据
./fastdbchkrep.sh parse \
  -import_dir "data/file/mysql/mysql_server_20250902" \
  -dbtype mysql \
  -dbmodel one \
  -jsonout "data/json"

# 步骤 2：生成报告
./fastdbchkrep.sh report \
  -import_json "data/json/(mysql-one)-mysql_server_20250902.json" \
  -mdout "data/md" \
  -company_name "伟宏智能" \
  -user_company "广州银行" \
  -application_name "核心业务系统"

# 步骤 3：转换为 PDF
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/mysql/mysql_server_20250902/mysql_server.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_广州银行_核心业务系统_MYSQL数据库巡检报告_20250902"
```

### SQL Server 完整流程

```bash
# 步骤 1：生成报告（SQL Server 跳过 parse 步骤，直接从 TXT 生成）
./fastdbchkrep.sh report \
  -import_txt "data/file/sqlserver/172.18.0.2-HealthCheck-20251023.txt" \
  -mdout "data/md" \
  -company_name "鼎诚科技" \
  -user_company "海南电网" \
  -application_name "OMS调度系统"

# 步骤 2：转换为 PDF
./fastdbchkrep.sh htmltopdf \
  -import_html "data/md/sqlserver/172.18.0.2/HealthCheck.editable.html" \
  -pdfout "data/pdf" \
  -pdfname "2025年第三季度_海南电网_OMS系统_SQLSERVER数据库巡检报告_20251023"
```

---

## 🛠️ 开发指南

### 代码规范和命名约定

- **Python 代码**：遵循 PEP 8 规范，使用 4 空格缩进
- **命名规范**：
  - 模块/函数：`snake_case`
  - 类：`PascalCase`
  - 常量：`UPPER_CASE`
- **类型注解**：公共 API 使用类型注解
- **文档字符串**：使用简洁的 docstring

### 如何扩展新的数据库类型

假设要添加 PostgreSQL 支持，需要以下步骤：

#### 1. 创建解析器模块

在 `src/fastdbchkrep/meta/postgresql/` 目录下创建 `parser.py`：

```python
from pathlib import Path
from typing import List, Optional

def parse_postgresql_metadata(import_dirs: List[str],
                              json_out_dir: str,
                              identifier: Optional[str] = None,
                              log_dir: Optional[str] = None) -> bool:
    """
    解析 PostgreSQL 数据库元数据

    Args:
        import_dirs: 输入目录列表
        json_out_dir: JSON 输出目录
        identifier: 自定义标识符
        log_dir: 日志目录

    Returns:
        成功返回 True，失败返回 False
    """
    # 实现解析逻辑
    pass
```

#### 2. 创建报告生成器模块

在 `src/fastdbchkrep/report/postgresql/` 目录下创建 `generator.py`：

```python
from pathlib import Path
from typing import Dict, Any

class MarkdownGenerator:
    """PostgreSQL 报告生成器"""

    def __init__(self, db_type: str, output_dir: Path,
                 company_name: str, user_company: str,
                 application_name: str, **kwargs):
        self.db_type = db_type
        self.output_dir = output_dir
        self.company_name = company_name
        self.user_company = user_company
        self.application_name = application_name

    def generate_from_json(self, json_data: Dict[str, Any],
                          quiet: bool = False) -> bool:
        """从 JSON 数据生成报告"""
        # 实现报告生成逻辑
        pass
```

#### 3. 更新 CLI 参数验证

在 `main.py` 中，`-dbtype` 参数已经包含 `postgresql`，无需修改。

#### 4. 更新 API 路由

在 `src/fastdbchkrep/report/api.py` 中添加 PostgreSQL 支持：

```python
from .postgresql.generator import MarkdownGenerator as PostgreSQLMarkdownGenerator

# 在 generate_report_from_json 函数中添加路由逻辑
if db_type.lower() == "postgresql":
    generator_cls = PostgreSQLMarkdownGenerator
```

### 如何添加新的报告章节

以 SQL Server 为例，在 `src/fastdbchkrep/report/sqlserver/generator.py` 中：

1. 在 `_build_markdown_content()` 方法中添加新章节调用
2. 实现新的章节构建方法（如 `_build_section_8_new_feature()`）
3. 在 `templates.py` 中添加章节定义（如果需要）

---

## ❓ 常见问题

### Q1: 如何解决依赖安装问题？

**问题**：`pip install -r requirements.txt` 失败

**解决方案**：

```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### Q2: Playwright 浏览器安装失败怎么办？

**问题**：`playwright install chromium` 失败或超时

**解决方案**：

```bash
# 设置环境变量使用国内镜像
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/

# 然后重新安装
playwright install chromium
```

### Q3: 如何处理文件编码问题？

**问题**：解析 TXT 文件时出现编码错误

**解决方案**：

所有文件读取已使用 `encoding='utf-8', errors='ignore'` 参数，会自动忽略编码错误。如果仍有问题，可以手动转换文件编码：

```bash
# 将 GBK 编码转换为 UTF-8
iconv -f GBK -t UTF-8 input.txt > output.txt
```

### Q4: 如何使用二进制分发版本？

**问题**：客户现场没有 Python 环境

**解决方案**：

```bash
# 1. 在开发环境构建二进制
pyinstaller fastdbchkrep.spec

# 2. 设置环境变量
export FASTDBCHKREP_BINARY="$PWD/binary/fastdbchkrep/fastdbchkrep"

# 3. 正常使用 fastdbchkrep.sh（会自动使用二进制）
./fastdbchkrep.sh parse -import_dir /data -dbtype oracle -dbmodel one -jsonout /json
```

### Q5: Oracle RAC 报告合并失败怎么办？

**问题**：RAC 多节点报告合并时出错

**解决方案**：

1. 检查节点数据一致性（hostname、dbname 应一致）
2. 确保所有节点数据都已成功解析
3. 查看日志文件 `data/log/` 获取详细错误信息

### Q6: AWR 截图失败怎么办？

**问题**：AWR 报告截图显示"获取 AWR 报告图片失败"

**解决方案**：

1. 确认 Playwright 浏览器已正确安装：`playwright install chromium`
2. 检查 AWR HTML 文件是否存在且格式正确
3. 查看日志文件获取详细错误信息

### Q7: PDF 生成失败怎么办？

**问题**：`htmltopdf` 命令执行失败

**解决方案**：

1. 确认输入的 HTML 文件存在
2. 确认 Playwright 浏览器已安装
3. 检查输出目录是否有写入权限
4. 查看日志文件获取详细错误信息

### Q8: 如何自定义公司 Logo？

**问题**：需要使用自己公司的 Logo

**解决方案**：

1. 将 Logo 图片（JPG 格式）放到 `src/fastdbchkrep/resource/icob/` 目录
2. 在 `src/fastdbchkrep/report/common/template_config.py` 中添加映射：

```python
COMPANY_LOGO_MAPPING: Dict[str, str] = {
    "鼎诚科技": "dckj.jpg",
    "伟宏智能": "whzn.jpg",
    "你的公司名": "your_logo.jpg",  # 添加这一行
}
```

3. 在 `main.py` 中更新 `-company_name` 参数的 `choices` 列表

---

## 📝 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出改进建议！

### 贡献方式

1. Fork 本仓库：[https://github.com/iop07695432/fastdbchkrep](https://github.com/iop07695432/fastdbchkrep)
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码审查标准

- 遵循项目代码规范（详见 `README.md`）
- 添加必要的测试用例
- 更新相关文档
- 确保所有测试通过

---

## 📧 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 Issue：[GitHub Issues](https://github.com/iop07695432/fastdbchkrep/issues)
- 项目主页：[https://github.com/iop07695432/fastdbchkrep](https://github.com/iop07695432/fastdbchkrep)
- 邮件：xzjj0420@gmail.com
- 博客：https://www.cnblogs.com/yuzhijian

---

## 🙏 致谢

感谢所有为本项目做出贡献的开发者和用户！

特别感谢以下开源项目：

- [Playwright](https://playwright.dev/) - 强大的浏览器自动化工具
- [Matplotlib](https://matplotlib.org/) - 优秀的 Python 绘图库
- [Loguru](https://github.com/Delgan/loguru) - 简洁易用的日志库

---

**FastDBCheckRep** - 让数据库巡检报告生成更简单、更专业！


