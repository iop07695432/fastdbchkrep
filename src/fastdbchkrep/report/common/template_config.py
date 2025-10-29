"""
报告模板配置文件
定义公司Logo映射、模板内容等配置项
"""
from pathlib import Path
import os
import re
import shutil
import sys
from typing import Dict, Optional
from datetime import datetime


class TemplateConfig:
    """报告模板配置类"""
    
    # 资源文件根目录
    RESOURCE_ROOT = Path(__file__).parent.parent.parent / "resource" / "icob"
    
    # 公司与Logo文件映射关系
    COMPANY_LOGO_MAPPING: Dict[str, str] = {
        "鼎诚科技": "dckj.jpg",
        "广州鼎诚科技有限公司": "dckj.jpg",
        "伟宏智能": "whzn.jpg",
        "广州伟宏智能科技有限公司": "whzn.jpg"
    }
    
    # 默认Logo（当公司名称未匹配时使用）
    DEFAULT_LOGO = "dckj.jpg"
    
    @classmethod
    def get_logo_path(cls, company_name: str, use_relative: bool = True, base_dir: Optional[Path] = None) -> str:
        """
        根据公司名称获取Logo文件路径
        
        Args:
            company_name: 公司名称
            use_relative: 是否返回相对路径（用于Markdown文档）
            
        Returns:
            Logo文件路径（相对路径或绝对路径）
        """
        # 查找匹配的Logo文件名
        logo_filename = cls.DEFAULT_LOGO
        
        # 遍历映射关系，支持部分匹配
        for company_key, logo_file in cls.COMPANY_LOGO_MAPPING.items():
            if company_key in company_name or company_name in company_key:
                logo_filename = logo_file
                break
        
        # 解析资源实际路径（兼容打包场景）
        logo_abs_path = cls.RESOURCE_ROOT / logo_filename
        if not logo_abs_path.exists():
            try:
                # PyInstaller 单文件/目录模式支持（需 --add-data "src/fastdbchkrep/resource/icob:fastdbchkrep/resource/icob"）
                if hasattr(sys, '_MEIPASS'):
                    bundle_root = Path(sys._MEIPASS) / 'fastdbchkrep' / 'resource' / 'icob'
                    candidate = bundle_root / logo_filename
                    if candidate.exists():
                        logo_abs_path = candidate
            except Exception:
                pass

        # 如果不需要相对路径，则直接返回绝对路径
        if not use_relative:
            return str(logo_abs_path)

        # 若提供了输出目录，则将 Logo 复制到 <base_dir>/assets/logo/ 并返回相对路径
        if base_dir is not None:
            try:
                assets_logo_dir = Path(base_dir) / 'assets' / 'logo'
                assets_logo_dir.mkdir(parents=True, exist_ok=True)
                dst_path = assets_logo_dir / logo_filename
                # 仅在不存在或源更新时复制
                need_copy = True
                try:
                    if dst_path.exists() and logo_abs_path.exists():
                        need_copy = logo_abs_path.stat().st_mtime_ns > dst_path.stat().st_mtime_ns or logo_abs_path.stat().st_size != dst_path.stat().st_size
                except Exception:
                    # 无法比较时，执行复制
                    need_copy = True
                if need_copy and logo_abs_path.exists():
                    shutil.copy2(str(logo_abs_path), str(dst_path))
                # 返回相对路径（面向同目录下的 MD/HTML）
                return str(Path('assets') / 'logo' / logo_filename)
            except Exception:
                # 复制失败时回退到相对定位
                pass

        # 回退：基于默认输出结构，向上三级到项目根目录（不推荐，仅兜底）
        # Markdown通常在: <outdir>/{dbtype}/{identifier}/
        # Logo在: src/fastdbchkrep/resource/icob/
        return f"../../../src/fastdbchkrep/resource/icob/{logo_filename}"
    
    @staticmethod
    def generate_cover_page(company_name: str, user_company: str, 
                           application_name: str, db_type: str = "Oracle",
                           support_start_date: Optional[str] = None,
                           support_end_date: Optional[str] = None,
                           suptime: Optional[str] = None,
                           supname: Optional[str] = None,
                           base_dir: Optional[Path] = None) -> str:
        """
        生成封面页内容
        
        Args:
            company_name: 公司名称
            user_company: 客户单位名称
            application_name: 应用系统名称
            db_type: 数据库类型
            support_start_date: 现场支持起始日期（原始值，可为采集目录或8位日期）
            support_end_date: 现场支持结束日期（原始值，可为采集目录或8位日期）
            suptime: 现场支持总时间（小时）
            supname: 支持工程师姓名
            
        Returns:
            封面页的Markdown内容
        """
        logo_path = TemplateConfig.get_logo_path(company_name, use_relative=True, base_dir=base_dir)
        fallback_date = datetime.now().strftime("%Y 年 %m 月 %d 日")
        start_date = TemplateConfig._normalize_support_date(support_start_date, fallback_date)
        end_date = TemplateConfig._normalize_support_date(support_end_date or support_start_date, fallback_date)
        current_date = fallback_date
        
        # 使用传入的参数或默认值
        engineer_name = supname if supname else ""
        support_hours = suptime if suptime else ""
        
        content = f"""<div style="text-align: center;">

# {user_company}{application_name}

## {db_type} 数据库检查报告

![公司Logo]({logo_path})

</div>

| 项目 |  信息    |
|------|------|
| 支持工程师 | {engineer_name} |
| 现场支持起始日期 | {start_date} |
| 现场支持结束日期 | {end_date} |
| 现场支持总时间（小时） | {support_hours} |
| 报告生成日期 | {current_date} |

---
        """
        return content

    @staticmethod
    def _normalize_support_date(raw_value: Optional[str], fallback: str) -> str:
        """
        将采集目录或日期字符串格式化为“YYYY 年 MM 月 DD 日”。

        Args:
            raw_value: 原始日期或包含日期的字符串
            fallback: 格式化失败时使用的回退日期

        Returns:
            规范化后的日期字符串
        """
        if not raw_value:
            return fallback

        text = str(raw_value).strip()
        if not text:
            return fallback

        # 如果是路径或包含路径，优先取目录名
        if "/" in text or "\\" in text:
            text = Path(text).name

        # 提取连续8位数字（例如 20251023）
        match = re.search(r"(20\d{2})(\d{2})(\d{2})", text)
        if match:
            digits = "".join(match.groups())
            try:
                dt = datetime.strptime(digits, "%Y%m%d")
                return dt.strftime("%Y 年 %m 月 %d 日")
            except ValueError:
                pass

        normalized = TemplateConfig._try_parse_known_formats(text)
        return normalized if normalized else fallback

    @staticmethod
    def _try_parse_known_formats(text: str) -> Optional[str]:
        """尝试从常见格式中解析日期。"""
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%Y 年 %m 月 %d 日")
            except ValueError:
                continue

        match = re.search(r"(\d{4}).?年.?(\d{1,2}).?月.?(\d{1,2}).?日", text)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y 年 %m 月 %d 日")
            except ValueError:
                return None
        return None
    
    @staticmethod
    def generate_toc() -> str:
        """
        生成目录页内容
        
        Returns:
            目录页的Markdown内容
        """
        return """# 目录

1. [健康检查总结](#1-健康检查总结)
   - 1.1. [健康检查概要](#11-健康检查概要)
   - 1.2. [健康检查建议](#12-健康检查建议)

2. [健康检查介绍](#2-健康检查介绍)
   - 2.1. [健康检查目标](#21-健康检查目标)
   - 2.2. [健康检查方法](#22-健康检查方法)
   - 2.3. [健康检查范围](#23-健康检查范围)

3. [系统背景](#3-系统背景)
   - 3.1. [硬件配置](#31-硬件配置)
   - 3.2. [数据库配置](#32-数据库配置)
   - 3.3. [网络配置](#33-网络配置)

4. [操作系统检查](#4-操作系统检查)
   - 4.1. [CPU 使用率](#41-cpu-使用率)
   - 4.2. [内存使用率](#42-内存使用率)
   - 4.3. [网络使用情况](#43-网络使用情况)
   - 4.4. [磁盘空间使用情况](#44-磁盘空间使用情况)

5. [数据库配置检查](#5-数据库配置检查)
   - 5.1. [RMAN 备份信息](#51rman-备份信息)
   - 5.2. [数据库 Data Guard 容灾](#52-数据库-data-guard-容灾)
   - 5.3. [ADRCI、ALERT 日志检查](#53-adrcialert-日志检查)
   - 5.4. [控制文件和在线日志文件](#54-控制文件和在线日志文件)
   - 5.5. [表空间数据文件、归档文件明细](#55-表空间数据文件归档文件明细)
   - 5.6. [ASM 磁盘信息](#56-asm-磁盘信息)
   - 5.7. [PL/SQLDeveloper破解版勒索病毒检查](#57-plsqldeveloper破解版勒索病毒检查)

6. [数据库性能检查](#6-数据库性能检查)
   - 6.1. [数据库实例命中率](#61-数据库实例命中率)
   - 6.2. [数据库资源消耗时间模型](#62-数据库资源消耗时间模型)
   - 6.3. [数据库等待事件](#63-数据库等待事件)
   - 6.4. [TOP SQL](#64-top-sql)
   - 6.5. [数据库实例负载整体评估](#65-数据库实例负载整体评估)

---
"""
    
    @staticmethod
    def generate_document_control(company_name: str, user_company: str) -> str:
        """
        生成文档控制页内容
        
        Args:
            company_name: 公司名称
            user_company: 客户单位名称
            
        Returns:
            文档控制页的Markdown内容
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        return f"""**公司：{company_name}**

---

# 文档控制

## 修改记录

| 日期 | 作者 | 版本 | 修改记录 |
|------|------|------|----------|
| {current_date} |  | V1.0 | 新建 |
| | | | |
| | | | |

## 分发者

| 姓名 | 单位 | 职位 | 联系电话 | Email |
|------|------|------|----------|--------|
| | | | | |
| | | | | |
| | | | | |

## 审阅记录

| 姓名 | 单位 | 职位 | 联系电话 | Email |
|------|------|------|----------|--------|
| | | | | |
| | | | | |
| | | | | |

## 保密级别

> **注意**
> 此文档只能提供给{company_name}和{user_company}相关人员查看。

---
"""
