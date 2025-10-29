"""
RAC 报告合并器

目的：
- 将 RAC 模式下每个节点生成的输出目录合并到以 identifier 命名的单一目录下。
- 规范图片目录命名：{hostname_sid}_server_picture、{hostname_sid}_awr_picture。
- 重写 MD 与可编辑 HTML 中的图片引用路径，仅在 RAC 模式生效。

注意：不修改 meta/rac_parser.py 逻辑，仅作为 report 阶段的后处理。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from loguru import logger

from .rac_parsers import load_rac_meta
from ..common.template_config import TemplateConfig
from ..common.config import MarkdownConfig
from ..pdf import MarkdownToPdfConverter
from .parsers import InspectionSummaryParser
from datetime import datetime


class RacReportMerger:
    """RAC 输出合并工具"""

    @staticmethod
    def merge_reports(json_file: str, output_dir: str, quiet: bool = False) -> bool:
        """执行 RAC 合并。

        Args:
            json_file: 导入的 RAC JSON 路径
            output_dir: -mdout 目录
            quiet: 是否静默
        Returns:
            True/False
        """
        try:
            json_path = Path(json_file)
            db_type, identifier, metainfo = load_rac_meta(json_path)

            # 输出根目录: {mdout}/{dbtype}
            mdout_root = Path(output_dir)
            oracle_root = mdout_root / db_type

            # 目标目录: {mdout}/{dbtype}/{identifier}
            target_dir = oracle_root / identifier
            if target_dir.exists():
                # 清空旧目录
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            if not quiet:
                logger.info(f"RAC合并目标目录: {target_dir}")

            # 逐节点处理
            for node in metainfo:
                hostname = node.get('hostname', 'unknown')
                sid = node.get('sid', 'unknown')
                collect_date = node.get('collect_date', '')

                # 源节点目录名：生成器按 source_dir 的 basename 作为输出目录
                node_dir_name = None
                if node.get('source_dir'):
                    node_dir_name = Path(node['source_dir']).name
                elif node.get('dirname'):
                    node_dir_name = node['dirname']
                else:
                    # 兜底推断
                    node_dir_name = f"{hostname}_{sid}_{collect_date}".rstrip('_')

                src_node_dir = oracle_root / node_dir_name
                if not src_node_dir.exists():
                    logger.warning(f"节点输出目录不存在，跳过: {src_node_dir}")
                    continue

                hostname_sid = f"{hostname}_{sid}"

                # 1) 移动图片目录 -> {identifier}/{hostname_sid}_...
                RacReportMerger._move_dir_if_exists(
                    src_node_dir / 'server_picture',
                    target_dir / f"{hostname_sid}_server_picture"
                )

                RacReportMerger._move_dir_if_exists(
                    src_node_dir / 'awr_picture',
                    target_dir / f"{hostname_sid}_awr_picture"
                )

                # 2) 移动 MD 和可编辑 HTML 到 {identifier}
                moved_files: List[Path] = []
                # 优先按约定命名寻找
                md_expected = src_node_dir / f"{hostname_sid}.md"
                html_expected = src_node_dir / f"{hostname_sid}.editable.html"

                candidates: List[Path] = []
                if md_expected.exists():
                    candidates.append(md_expected)
                if html_expected.exists():
                    candidates.append(html_expected)
                if not candidates:
                    # 兜底：枚举 *.md 与 *.editable.html
                    candidates = list(src_node_dir.glob("*.md")) + list(src_node_dir.glob("*.editable.html"))

                for f in candidates:
                    dest_path = target_dir / f.name
                    try:
                        shutil.move(str(f), str(dest_path))
                        moved_files.append(dest_path)
                    except Exception as e:
                        logger.error(f"移动文件失败 {f} -> {dest_path}: {e}")

                # 3) 重写文件中的图片引用路径（仅针对此节点的文件）
                for moved in moved_files:
                    try:
                        content = moved.read_text(encoding='utf-8', errors='ignore')
                        updated = RacReportMerger._rewrite_image_refs(content, hostname_sid)
                        if updated != content:
                            moved.write_text(updated, encoding='utf-8')
                    except Exception as e:
                        logger.error(f"重写图片路径失败: {moved}: {e}")

                # 4) 删除原节点目录
                try:
                    shutil.rmtree(src_node_dir)
                except Exception as e:
                    logger.warning(f"删除原目录失败 {src_node_dir}: {e}")

            # 合并目录整理完成后，生成初始 RAC Markdown（<identifier>.rac.md）
            try:
                company_name = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("company_names", "")
                user_company = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_unit", "")
                application_name = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_system", "")

                supname, suptime = _guess_support_fields_from_md(target_dir)

                create_rac_md(
                    json_file=str(json_path),
                    output_dir=str(mdout_root),
                    company_name=company_name,
                    user_company=user_company,
                    application_name=application_name,
                    suptime=suptime,
                    supname=supname,
                    quiet=quiet,
                )
            except Exception as e:
                logger.warning(f"创建RAC初始Markdown失败: {e}")

            return True

        except Exception as e:
            logger.error(f"RAC合并失败: {e}")
            return False

    @staticmethod
    def _move_dir_if_exists(src: Path, dst: Path) -> None:
        if src.exists() and src.is_dir():
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dst))
                logger.info(f"目录已移动: {src} -> {dst}")
            except Exception as e:
                logger.error(f"移动目录失败 {src} -> {dst}: {e}")

    @staticmethod
    def _rewrite_image_refs(content: str, hostname_sid: str) -> str:
        """将 server_picture/ 与 awr_picture/ 引用改写为带前缀的目录名。

        适配场景：
        - Markdown: ![](<./server_picture/...>) 或 ![](<server_picture/...>)
        - HTML: <img src="./server_picture/..."> / <img src='server_picture/...'>
        - CSS/HTML内联: url(./server_picture/...) / url(server_picture/...)
        """
        server_dst = f"{hostname_sid}_server_picture/"
        awr_dst = f"{hostname_sid}_awr_picture/"

        # 仅替换常见的上下文前缀，避免误伤普通文字
        patterns = [
            # Markdown 链接
            (re.compile(r"(\()(?:\./)?server_picture/"), r"\1" + server_dst),
            (re.compile(r"(\()(?:\./)?awr_picture/"), r"\1" + awr_dst),
            # HTML src="..." / src='...'
            (re.compile(r"(src=\")(?:\./)?server_picture/"), r"\1" + server_dst),
            (re.compile(r"(src=')(?:\./)?server_picture/"), r"\1" + server_dst),
            (re.compile(r"(src=\")(?:\./)?awr_picture/"), r"\1" + awr_dst),
            (re.compile(r"(src=')(?:\./)?awr_picture/"), r"\1" + awr_dst),
            # CSS url(...)
            (re.compile(r"(url\()(?:\./)?server_picture/"), r"\1" + server_dst),
            (re.compile(r"(url\()(?:\./)?awr_picture/"), r"\1" + awr_dst),
        ]

        updated = content
        for pat, repl in patterns:
            updated = pat.sub(repl, updated)
        return updated


__all__ = [
    'RacReportMerger',
]


# ===============
# RAC 专用格式化
# ===============


def _parse_scheduler_lines(raw: str) -> List[Dict[str, str]]:
    """解析磁盘调度算法文本为条目列表。

    返回条目: {dev, sched, active}
    - dev: 设备名，如 sda、sdaa、nvme0n1、dm-0
    - sched: 原始调度器字符串，如 "noop [deadline] cfq" 或 "[mq-deadline] kyber bfq"
    - active: 括号中的调度器名（若存在）
    """
    entries: List[Dict[str, str]] = []
    if not raw:
        return entries
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        dev = None
        sched = None
        # /sys 路径形式
        m = re.search(r"/sys/block/([^/\s]+)/queue/scheduler\s*:\s*(.+)$", line)
        if m:
            dev, sched = m.group(1), m.group(2).strip()
        else:
            # 简单 dev: sched 形式
            m2 = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.+)$", line)
            if m2:
                dev, sched = m2.group(1), m2.group(2).strip()
        if not dev or not sched:
            continue
        active = None
        am = re.search(r"\[([^\]]+)\]", sched)
        if am:
            active = am.group(1).strip()
        entries.append({"dev": dev, "sched": sched, "active": active or ""})
    return entries


def format_disk_scheduler_rac(raw: str) -> str:
    """RAC 模式下的 DISK_SCHEDULER 展示优化。

    - 始终生效，仅在 RAC 模式调用：
      * sd* 且活跃调度器包含 "deadline"/"mq-deadline" 的分组：
        以区间标签方式汇总：sd[a]-sd[z]、sd[aa]-sd[az]、sd[ba]-sd[bz] 等，仅输出存在的组。
      * 非默认 active 的 sd 设备：逐条显示（如 sdj: noop deadline [cfq]）。
      * 非 sd 设备：逐条显示（nvme*/dm-* 等）。

    返回按行分隔的文本（调用方会将换行转为 <br>）。
    """
    try:
        entries = _parse_scheduler_lines(raw)

        # 分类
        sd_default: Dict[str, List[str]] = {}  # sched_text -> [sd_dev,...]
        sd_others: List[Tuple[str, str]] = []  # (dev, sched)
        non_sd: List[Tuple[str, str]] = []     # (dev, sched)

        for e in entries:
            dev, sched, active = e['dev'], e['sched'], e['active']
            if dev.startswith('sd') and re.match(r'^sd[a-z]+$', dev):
                if 'deadline' in (active or '').lower():  # 包含 deadline 或 mq-deadline
                    sd_default.setdefault(sched, []).append(dev)
                else:
                    sd_others.append((dev, sched))
            else:
                non_sd.append((dev, sched))

        lines: List[str] = []

        # 1) sd 默认组：按后缀长度和前缀分组，生成区间标签
        for sched_text, devs in sorted(sd_default.items(), key=lambda x: x[0]):
            for label in _build_sd_group_bins(devs):
                lines.append(f"{label}: {sched_text}")

        # 2) 非默认的 sd 设备逐条
        for dev, sched in sorted(sd_others, key=lambda x: x[0]):
            lines.append(f"{dev}: {sched}")

        # 3) 非 sd 设备逐条
        for dev, sched in sorted(non_sd, key=lambda x: x[0]):
            lines.append(f"{dev}: {sched}")

        return "\n".join(lines) if lines else raw
    except Exception as e:
        logger.warning(f"RAC磁盘调度汇总失败，回退原文: {e}")
        return raw


__all__.append('format_disk_scheduler_rac')


def _build_sd_group_bins(devs: List[str]) -> List[str]:
    """根据 sd 设备集合构建分组区间标签（按实际首尾字母）。

    规则：
    - 一位后缀（sda..sdz）：输出 "sd[<min>]-sd[<max>]"。
    - 多位后缀（如 sdaa、sdef）：按前缀 suffix[:-1] 分组，
      对每组输出 "sd[<prefix><min>]-sd[<prefix><max>]"。
    - 仅输出实际存在的分组；标签按字典序排序。
    """
    one_letter_last: List[str] = []
    groups: Dict[str, List[str]] = {}

    for d in devs:
        m = re.match(r"^sd([a-z]+)$", d)
        if not m:
            continue
        suf = m.group(1)
        if len(suf) == 1:
            one_letter_last.append(suf)
        else:
            prefix, last = suf[:-1], suf[-1]
            groups.setdefault(prefix, []).append(last)

    labels: List[str] = []

    if one_letter_last:
        min_l = min(one_letter_last)
        max_l = max(one_letter_last)
        labels.append(f"sd[{min_l}]-sd[{max_l}]")

    for prefix in sorted(groups.keys()):
        lasts = groups[prefix]
        if not lasts:
            continue
        min_l = min(lasts)
        max_l = max(lasts)
        labels.append(f"sd[{prefix}{min_l}]-sd[{prefix}{max_l}]")

    return labels


# =====================
# RAC 合并 MD 初始文件
# =====================

def _build_problems_table() -> str:
    """问题表格（表头+3空行），与单节点生成器保持一致。"""
    return (
        "| NO | 问题描述 | 参考章节 | 建议解决时间 |\n"
        "|---|---|---|---|\n"
        "|  |  |  |  |\n"
        "|  |  |  |  |\n"
        "|  |  |  |  |"
    )


def _format_file_status_content(file_status_content: str) -> str:
    """将文件状态内容格式化为表格，复用单节点逻辑。"""
    lines = (file_status_content or "").split('\n')
    table = "| 状态 | 文件名 | 文件描述 |\n|---|---|---|\n"
    for line in lines:
        s = line.strip()
        if s and any(symbol in s for symbol in ['[✓]', '[✗]', '[○]', '[?]']):
            m = re.match(r"\[(.)\]\s+(\S+)\s+(.+)", s)
            if m:
                table += f"| {m.group(1)} | {m.group(2)} | {m.group(3)} |\n"
    return table


def _format_inspection_time_cn(raw_time: Optional[str]) -> str:
    """将各种可能的时间字符串规范化为中文日期：YYYY年MM月DD日星期X。

    与单节点生成器的实现保持一致，包含星期计算与多格式兼容。
    """
    try:
        if not raw_time:
            return "未知时间"

        text = str(raw_time).strip()

        # 1) 已有中文格式（可带空格，可不带星期后细节）
        m = re.match(r"\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(星期[一二三四五六日]))?", text)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            try:
                weekday_idx = datetime(year, month, day).weekday()
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][weekday_idx]
            except Exception:
                weekday_cn = m.group(4) or ""
            return f"{year}年{month:02d}月{day:02d}日{weekday_cn}"

        # 2) ISO/常见数字格式
        patterns = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d",
        ]

        for p in patterns:
            try:
                dt = datetime.strptime(text, p)
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
            except Exception:
                pass

        # 3) 英文 date/日志风格（尽量兼容）
        en_patterns = [
            "%a %b %d %H:%M:%S %Z %Y",   # Fri Sep  5 18:12:42 CST 2025
            "%a, %b %d %H:%M:%S %Z %Y",
            "%a %b %d %H:%M:%S %Y",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
            "%d %b %Y %H:%M:%S %Z",
            "%b %d %Y %H:%M:%S",
        ]
        for p in en_patterns:
            try:
                dt = datetime.strptime(text, p)
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
                return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日{weekday_cn}"
            except Exception:
                pass

        # 4) 英文行手动提取年月日（回退方案）
        mon_map = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        m2 = re.search(r"\b([A-Z][a-z]{2})\b\s+(\d{1,2})\b.*?(\d{4})", text)
        if m2 and m2.group(1) in mon_map:
            year = int(m2.group(3))
            month = mon_map[m2.group(1)]
            day = int(m2.group(2))
            try:
                dt = datetime(year, month, day)
                weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
            except Exception:
                weekday_cn = ""
            return f"{year}年{month:02d}月{day:02d}日{weekday_cn}"

        # 5) 未识别，原样返回
        return text
    except Exception:
        return str(raw_time) if raw_time else "未知时间"


def _parse_file_status_entries(file_status_content: str) -> List[Dict[str, str]]:
    """解析 00_inspection_summary.txt 中“文件生成状态报告”列表为条目数组。

    返回: [{status, filename, desc, code}]
    - status: 单字符，如 ✓/✗/○/?
    - filename: 文件名
    - desc: 文件描述
    - code: 排序/对齐用编号（来自文件名前两位数字），无则置为 '99'
    """
    entries: List[Dict[str, str]] = []
    if not file_status_content:
        return entries
    for line in file_status_content.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"\[(.)\]\s+(\S+)\s+(.+)", s)
        if not m:
            continue
        status = m.group(1)
        filename = m.group(2)
        desc = m.group(3)
        cm = re.match(r"^(\d{2})_", filename)
        code = cm.group(1) if cm else "99"
        entries.append({"status": status, "filename": filename, "desc": desc, "code": code})
    return entries


def _build_dual_node_file_status_table(
    sid1: str,
    entries1: List[Dict[str, str]],
    sid2: str,
    entries2: List[Dict[str, str]],
) -> str:
    """根据两个节点的条目，生成5列表格：
    | {sid1}_file_status | {sid1}_file | {sid2}_file_status | {sid2}_file | 文件描述 |
    行按编号对齐，编号取自文件名的两位前缀。
    """
    # 构建 code -> entry 映射
    map1: Dict[str, Dict[str, str]] = {e['code']: e for e in entries1}
    map2: Dict[str, Dict[str, str]] = {e['code']: e for e in entries2}
    all_codes: List[str] = sorted(set(map1.keys()) | set(map2.keys()), key=lambda x: (int(x) if x.isdigit() else 99, x))

    # header = f"| {sid1}_file_status | {sid1}_file | {sid2}_file_status | {sid2}_file | 文件描述 |\n|---|---|---|---|---|\n"
    header = f"| 巡检文件状态 | 巡检文件名(节点一) | 巡检文件状态 | 巡检文件名(节点二) | 文件描述 |\n|---|---|---|---|---|\n"

    rows: List[str] = []
    for code in all_codes:
        e1 = map1.get(code)
        e2 = map2.get(code)
        c1 = e1['status'] if e1 else ''
        f1 = e1['filename'] if e1 else ''
        c2 = e2['status'] if e2 else ''
        f2 = e2['filename'] if e2 else ''
        desc = (e1['desc'] if e1 else (e2['desc'] if e2 else ''))
        rows.append(f"| {c1} | {f1} | {c2} | {f2} | {desc} |")
    return header + "\n".join(rows)


def _resolve_support_date_range(metainfo: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """提取RAC节点的现场支持起止日期（按最小/最大collect_date）。"""
    def _extract(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        text = str(raw).strip()
        if not text:
            return None
        if "/" in text or "\\" in text:
            text = Path(text).name
        match = re.search(r"(20\d{2})(\d{2})(\d{2})", text)
        if not match:
            return None
        digits = "".join(match.groups())
        try:
            datetime.strptime(digits, "%Y%m%d")
            return digits
        except ValueError:
            return None

    dates: List[str] = []
    for node in metainfo:
        candidate = _extract(node.get("collect_date"))
        if not candidate:
            candidate = _extract(node.get("source_dir"))
        if candidate:
            dates.append(candidate)

    if not dates:
        return None, None

    start = min(dates)
    end = max(dates)
    return start, end


def create_rac_md(
    json_file: str,
    output_dir: str,
    company_name: str,
    user_company: str,
    application_name: str,
    suptime: Optional[str] = None,
    supname: Optional[str] = None,
    quiet: bool = False,
) -> Path:
    """创建 RAC 合并报告的初始 Markdown 文件：<identifier>.rac.md。

    - 使用与单节点报告相同的封面、目录、文档控制生成逻辑。
    - 生成章节：1. 健康检查总结（概要/建议）与 2. 健康检查介绍（目标/方法）。
    - 后续章节的节点内容合并将在后续步骤中补充。

    Returns:
        生成的Markdown文件路径
    """
    json_path = Path(json_file)
    db_type, identifier, metainfo = load_rac_meta(json_path)

    # 目标目录: {mdout}/{dbtype}/{identifier}
    mdout_root = Path(output_dir)
    oracle_root = mdout_root / db_type
    target_dir = oracle_root / identifier
    target_dir.mkdir(parents=True, exist_ok=True)

    # 生成封面/目录/文档控制（与单节点一致）
    support_start, support_end = _resolve_support_date_range(metainfo)
    cover_page = TemplateConfig.generate_cover_page(
        company_name=company_name,
        user_company=user_company,
        application_name=application_name,
        db_type="Oracle",
        support_start_date=support_start,
        support_end_date=support_end,
        suptime=suptime,
        supname=supname,
        base_dir=target_dir,
    )
    toc_page = _generate_rac_toc()
    document_control = TemplateConfig.generate_document_control(company_name, user_company)

    # 规范化巡检时间：取任意一个节点的 00_inspection_summary.txt
    inspection_time_raw: Optional[str] = None
    # 为构建双节点文件状态表准备
    node1_sid: Optional[str] = None
    node2_sid: Optional[str] = None
    node1_entries: Optional[List[Dict[str, str]]] = None
    node2_entries: Optional[List[Dict[str, str]]] = None

    # 先定位 node_number=1 与 node_number=2；若缺失则取前两个
    node_by_number: Dict[int, Dict[str, Any]] = {}
    for n in metainfo:
        nn = n.get('node_number')
        if isinstance(nn, int):
            node_by_number[nn] = n

    ordered_nodes: List[Dict[str, Any]] = []
    for idx in (1, 2):
        if idx in node_by_number:
            ordered_nodes.append(node_by_number[idx])
    if len(ordered_nodes) < 2:
        # 回退取前两个
        for n in metainfo:
            if n not in ordered_nodes:
                ordered_nodes.append(n)
            if len(ordered_nodes) >= 2:
                break

    # 解析两个节点的 summary 数据
    for i, node in enumerate(ordered_nodes[:2], start=1):
        try:
            files = node.get('files') or {}
            summary = files.get('00_inspection_summary')
            if summary and isinstance(summary, dict) and summary.get('path'):
                summ = InspectionSummaryParser.parse_inspection_summary(Path(summary['path']))
                if summ:
                    if inspection_time_raw is None:
                        inspection_time_raw = summ.inspection_time
                    entries = _parse_file_status_entries(summ.file_status_content)
                    sid_val = node.get('sid') or (summ.sid if hasattr(summ, 'sid') else None)
                    if i == 1:
                        node1_sid = sid_val
                        node1_entries = entries
                    else:
                        node2_sid = sid_val
                        node2_entries = entries
        except Exception as e:
            logger.warning(f"读取节点{i}巡检摘要失败: {e}")

    formatted_time = _format_inspection_time_cn(inspection_time_raw)

    # 数据库模式显示
    db_model_display = "RAC"

    # 使用与单节点一致的占位变量
    company = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("company_names", company_name)
    customer_unit = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_unit", user_company)
    customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_system", application_name)

    problems_table = _build_problems_table()

    section_1_and_2 = f"""# 1. 健康检查总结

## 1.1. 健康检查概要

  如果{company}工程师在检查中发现Oracle数据库的问题，我们将对有问题的情况进行记录，并通知客户改正；对于比较复杂的问题,我们将在报告中指出，并建议和协助客户进一步进行相关的详细检查，同时将问题提交到{company}技术支持部，以便问题得到更快更好的解决。

  此次检查所需的资料来源主要是{formatted_time}使用 oracle_inspection.sh 脚本对{customer_unit}{customer_system}Oracle数据库收集运行环境文件的结果。此次我们主要检查该数据库的性能和配置，在下面的报告中，我们将做出分析，然后提出相关的改进建议。

  此次检查的数据库范围是：{customer_unit}{customer_system}Oracle{db_model_display}数据库。

## 1.2. 健康检查建议

以下是本次检查发现的一些主要问题和建议的总结。

{customer_system}Oracle{db_model_display}数据库

{problems_table}

# 2. 健康检查介绍

## 2.1. 健康检查目标

数据库性能检查是用来：

- 评价数据库当前的性能情况
- 分析数据库应用瓶颈和资源竞争情况
- 指出存在的问题，提出解决建议

## 2.2. 健康检查方法

本次数据库性能检查的工具是：
- Oracle 数据库巡检工具为 oracle_inspection.sh
- MySQL 数据库巡检工具为 mysql_inspection.sh
- PostgreSQL 数据库巡检工具为 postgresql_inspection.sh
- SQLServer 数据库巡检工具为 sqlserver_inspection.sh

"""

    # 构建文件状态表（优先双节点对齐，若不全则降级为单节点表）
    file_status_section = None
    if node1_sid and node2_sid and node1_entries and node2_entries:
        file_status_section = _build_dual_node_file_status_table(node1_sid, node1_entries, node2_sid, node2_entries)
    elif node1_entries:
        # 单节点降级
        file_status_section = _format_file_status_content("\n".join(
            [f"[{e['status']}] {e['filename']} {e['desc']}" for e in node1_entries]
        ))

    if file_status_section:
        section_1_and_2 += f"\n本次提供数据库巡检建议依据文件是：\n\n{file_status_section}\n"

    # 2.3 健康检查范围（沿用单节点模板逻辑/措辞）
    section_2_3 = f"""
## 2.3. 健康检查范围

本次检查仅限 {customer_system} Oracle {db_model_display}数据库，本报告提供的检查和建议主要针对以下方面：

- 主机配置
- 操作系统性能
- 数据库配置
- 数据库性能

本报告的提供的检查和建议不涉及：

- 具体的性能调整
- 应用程序的具体细节

**注意**：本次检查仅历时一天，其中还包括了提交分析报告的时间。所以在具体的性能方面仅做相应的建议。如需在数据库性能方面进行进一步的调整，请继续选择数据库性能调整。
"""

    # 3.1 系统硬件配置（从两个节点的单机MD中抽取并并列展示）
    section_3 = "\n# 3. 系统背景\n\n"
    section_3_1_header = "## 3.1. 系统硬件配置\n\n"
    hw_table = ""
    try:
        if node1_sid and node2_sid:
            md1 = _find_node_md_by_sid(target_dir, node1_sid)
            md2 = _find_node_md_by_sid(target_dir, node2_sid)
            if md1 and md2:
                host1 = ordered_nodes[0].get('hostname', '') if ordered_nodes else ''
                host2 = ordered_nodes[1].get('hostname', '') if len(ordered_nodes) > 1 else ''
                hw_table = _build_dual_node_system_hardware_table(md1, md2, node1_sid, node2_sid, hostname1=host1, hostname2=host2)
            else:
                if not quiet:
                    logger.warning(f"未找到节点MD：{node1_sid} -> {md1}, {node2_sid} -> {md2}")
        else:
            if not quiet:
                logger.warning("缺少节点SID，无法生成3.1并列硬件配置表")
    except Exception as e:
        logger.warning(f"生成3.1硬件配置表失败: {e}")

    # 3.2 数据库配置（提取两节点并合并展示）
    section_3_2_header = "## 3.2. 数据库配置\n\n"
    db_config_block = ""
    try:
        if node1_sid and node2_sid:
            md1 = _find_node_md_by_sid(target_dir, node1_sid)
            md2 = _find_node_md_by_sid(target_dir, node2_sid)
            if md1 and md2:
                db_basic_1 = _parse_named_table_from_md(md1, "数据库基本信息")
                db_basic_2 = _parse_named_table_from_md(md2, "数据库基本信息")

                # 在渲染前，从 04_health_check.txt 注入派生值（控制文件数量/在线日志大小一致性）
                hc_path = _find_health_check_path(ordered_nodes[:2])
                if hc_path and hc_path.exists():
                    try:
                        ctrl_count = _parse_control_file_count(hc_path)
                        if ctrl_count is not None:
                            db_basic_1['CONTROL_FILE_COUNT'] = (str(ctrl_count), '控制文件数量')
                    except Exception as e:
                        logger.warning(f"解析控制文件数量失败: {e}")
                    try:
                        same_size_flag = _parse_online_logs_same_size(hc_path)
                        if same_size_flag:
                            db_basic_1['ONLINE_LOGS_SAME_SIZE'] = (same_size_flag, '在线日志文件大小一致性')
                    except Exception as e:
                        logger.warning(f"解析在线日志大小一致性失败: {e}")

                # 基本信息（多行值合并：CURRENT_SESSION/DB_SID/HOST_NAME/STARTUP_TIME/LOG_MODE/ARCHIVE_MODE）
                # 从节点信息中获取hostname，覆盖HOST_NAME显示
                node1_hostname = ordered_nodes[0].get('hostname', '') if ordered_nodes else ''
                node2_hostname = ordered_nodes[1].get('hostname', '') if len(ordered_nodes) > 1 else ''
                db_basic_rows = _build_db_basic_info_combined_table(
                    node1_sid, db_basic_1,
                    node2_sid, db_basic_2,
                    hostname1=node1_hostname,
                    hostname2=node2_hostname,
                )

                # 数据库使用空间（与基本信息相同呈现逻辑）
                db_space_1 = _parse_named_table_from_md(md1, "数据库使用空间")
                db_space_2 = _parse_named_table_from_md(md2, "数据库使用空间")
                db_space_rows = _build_db_space_info_combined_table(
                    node1_sid, db_space_1,
                    node2_sid, db_space_2,
                )

                # 备份和容灾配置（四列表，一节点一行）
                backup_1 = _parse_named_table_from_md(md1, "备份和容灾配置")
                backup_2 = _parse_named_table_from_md(md2, "备份和容灾配置")
                backup_table = _build_node_key_table(
                    node1_sid, backup_1,
                    node2_sid, backup_2,
                    keys=["DISASTER_RECOVERY_MODE", "RMAN_BACKUP_STATUS"],
                    header_prefix="",
                )

                # 日志配置（优先从 04_health_check.txt 的 C1. 重要日志文件路径 提取）
                log_1 = {}
                log_2 = {}
                # hc_path 已在前面求得
                if hc_path and hc_path.exists():
                    log_1, log_2 = _parse_log_config_from_health_check(hc_path, node1_sid, node2_sid)
                else:
                    # 回退：从各自MD的“日志配置”表获取
                    log_1 = _parse_named_table_from_md(md1, "日志配置")
                    log_2 = _parse_named_table_from_md(md2, "日志配置")
                log_table = _build_node_key_table(
                    node1_sid, log_1,
                    node2_sid, log_2,
                    keys=[
                        "ALERT_LOG_PATH",
                        "AUDIT_FILE_DEST_PATH",
                        "CORE_DUMP_DEST_PATH",
                        "DIAGNOSTIC_DEST_PATH",
                        "USER_DUMP_DEST_PATH",
                    ],
                    header_prefix="",
                )

                db_config_block = "".join([
                    db_basic_rows, "\n\n",
                    "**数据库使用空间：**\n\n",
                    db_space_rows, "\n\n",
                    "**备份和容灾配置：**\n\n",
                    backup_table, "\n\n",
                    "**日志配置：**\n\n",
                    log_table, "\n",
                ])
            else:
                if not quiet:
                    logger.warning(f"未找到节点MD：{node1_sid} -> {md1}, {node2_sid} -> {md2}")
        else:
            if not quiet:
                logger.warning("缺少节点SID，无法生成3.2数据库配置")
    except Exception as e:
        logger.warning(f"生成3.2数据库配置失败: {e}")

    # 4. 操作系统检查（合并两节点 CPU/内存/IO 图与磁盘空间表）
    section_4_block = ""
    try:
        if node1_sid and node2_sid:
            n1 = ordered_nodes[0]
            n2 = ordered_nodes[1] if len(ordered_nodes) > 1 else None
            if n2:
                section_4_block = _build_section_4_content(
                    target_dir=target_dir,
                    hostname1=n1.get('hostname', ''), sid1=n1.get('sid', ''),
                    hostname2=n2.get('hostname', ''), sid2=n2.get('sid', ''),
                )
    except Exception as e:
        logger.warning(f"生成第4章操作系统检查失败: {e}")

    # 5. 数据库配置检查（加载两节点 5.1 RMAN 备份信息 与 5.2 Data Guard 与 5.3 ADRCI/ALERT）
    section_5_block = ""
    try:
        if node1_sid and node2_sid:
            n1 = ordered_nodes[0]
            n2 = ordered_nodes[1] if len(ordered_nodes) > 1 else None
            if n2:
                md1 = _find_node_md_by_sid(target_dir, n1.get('sid', ''))
                md2 = _find_node_md_by_sid(target_dir, n2.get('sid', ''))
                # 5.1 RMAN
                body1 = _extract_rman_5_1_body_from_md(md1, n1.get('hostname',''), n1.get('sid','')) if md1 else None
                body2 = _extract_rman_5_1_body_from_md(md2, n2.get('hostname',''), n2.get('sid','')) if md2 else None
                parts: List[str] = ["## 5.1.RMAN 备份信息\n\n"]
                any_51 = False
                if body1:
                    parts.append(body1.strip() + "\n\n")
                    any_51 = True
                if body2:
                    parts.append(body2.strip() + "\n\n")
                    any_51 = True
                if any_51:
                    parts.append("---\n\n")

                # 5.2 Data Guard 容灾：仅展示节点1；若节点1缺失则回退节点2
                dg1 = _extract_dg_5_2_body_from_md(md1) if md1 else None
                dg2 = _extract_dg_5_2_body_from_md(md2) if md2 else None
                dg_body = dg1 if dg1 else dg2
                if dg_body:
                    parts.append("## 5.2. 数据库 Data Guard 容灾\n\n")
                    parts.append(dg_body.strip() + "\n\n")
                    parts.append("---\n\n")

                # 5.3 ADRCI、ALERT 日志检查：两节点内容都装载
                sec53_1 = _extract_5_3_body_from_md(md1, n1.get('hostname',''), n1.get('sid','')) if md1 else None
                sec53_2 = _extract_5_3_body_from_md(md2, n2.get('hostname',''), n2.get('sid','')) if md2 else None
                if sec53_1 or sec53_2:
                    parts.append("## 5.3. ADRCI、ALERT 日志检查\n\n")
                    if sec53_1:
                        parts.append(sec53_1.strip() + "\n\n")
                    if sec53_2:
                        parts.append(sec53_2.strip() + "\n\n")
                    # RAC 5.3 结尾加综合结论（加粗）
                    parts.append("**综合结论：【请填写结论】**\n\n")
                    parts.append("---\n\n")

                # 5.4 控制文件和在线日志文件（仅节点1，缺则节点2）
                b54_1 = _extract_5_4_body_from_md(md1) if md1 else None
                b54_2 = _extract_5_4_body_from_md(md2) if md2 else None
                b54 = b54_1 if b54_1 else b54_2
                if b54:
                    parts.append("## 5.4. 控制文件和在线日志文件\n\n")
                    parts.append(b54.strip() + "\n\n")
                    parts.append("---\n\n")

                # 5.5 表空间数据文件、归档文件明细（仅节点1，缺则节点2）
                b55_1 = _extract_5_5_body_from_md(md1) if md1 else None
                b55_2 = _extract_5_5_body_from_md(md2) if md2 else None
                b55 = b55_1 if b55_1 else b55_2
                if b55:
                    parts.append("## 5.5. 表空间数据文件、归档文件明细\n\n")
                    parts.append(b55.strip() + "\n\n")
                    parts.append("---\n\n")

                # 5.6 ASM 磁盘信息（仅节点1，缺则节点2；兼容标题两种形式）
                b56_1 = _extract_5_6_body_from_md(md1) if md1 else None
                b56_2 = _extract_5_6_body_from_md(md2) if md2 else None
                b56 = b56_1 if b56_1 else b56_2
                if b56:
                    parts.append("## 5.6. ASM 磁盘信息\n\n")
                    parts.append(b56.strip() + "\n\n")
                    parts.append("---\n\n")

                # 5.7 病毒检查（仅节点1，缺则节点2）
                b57_1 = _extract_5_7_body_from_md(md1) if md1 else None
                b57_2 = _extract_5_7_body_from_md(md2) if md2 else None
                b57 = b57_1 if b57_1 else b57_2
                if b57:
                    parts.append("## 5.7. PL/SQLDeveloper破解版勒索病毒检查\n\n")
                    parts.append(b57.strip() + "\n\n")
                    parts.append("---\n\n")
                # 5.8 磁盘多路径、ASM_UDEV 配置（RAC专属）
                mp1 = _extract_multipath_section_from_node(n1)
                mp2 = _extract_multipath_section_from_node(n2)
                udev1 = _read_node_file_all(n1, '06_asm_udev')
                udev2 = _read_node_file_all(n2, '06_asm_udev')

                if any([mp1, mp2, udev1, udev2]):
                    parts.append("## 5.8. 磁盘多路径、ASM_UDEV 配置\n\n")
                    # multipath
                    parts.append(f"### 【{n1.get('hostname','')}】  磁盘多路径文件\n\n")
                    parts.append("```\n" + (mp1 or "未找到多路径信息") + "\n```\n\n")
                    parts.append(f"### 【{n2.get('hostname','')}】  磁盘多路径文件\n\n")
                    parts.append("```\n" + (mp2 or "未找到多路径信息") + "\n```\n\n")
                    # asm udev
                    parts.append(f"### 【{n1.get('hostname','')}】  ASM_UDEV 配置\n\n")
                    parts.append("```\n" + (udev1 or "未找到ASM UDEV配置") + "\n```\n\n")
                    parts.append(f"### 【{n2.get('hostname','')}】ASM_UDEV 配置\n\n")
                    parts.append("```\n" + (udev2 or "未找到ASM UDEV配置") + "\n```\n\n")
                    parts.append("综合结论：【请填写结论】\n\n")
                    parts.append("---\n\n")

                # 5.9 Oracle Rac 集群信息检查（优先节点1，节点1缺失才回退节点2）
                crs1, vote1, ocr1 = _extract_crs_info_sections(n1)
                if not any([crs1, vote1, ocr1]):
                    crs1, vote1, ocr1 = _extract_crs_info_sections(n2)
                if any([crs1, vote1, ocr1]):
                    parts.append("## 5.9. Oracle Rac 集群信息检查\n\n")
                    # CRS资源状态
                    parts.append("### Rac CRS资源状态 \n\n")
                    parts.append("```\n" + (crs1 or "未找到CRS资源状态信息") + "\n```\n\n")
                    # Voting Disk 信息
                    parts.append("### Voting Disk Information 仲裁磁盘信息\n\n")
                    parts.append("```\n" + (vote1 or "未找到Voting Disk信息") + "\n```\n\n")
                    # OCR 检查
                    parts.append("### OCR检查 仲裁磁盘信息\n\n")
                    parts.append("```\n" + (ocr1 or "未找到OCR检查信息") + "\n```\n\n")
                    parts.append("---\n\n")
                    parts.append("综合结论：【请填写结论】\n\n")
                section_5_block = "".join(parts)
    except Exception as e:
        logger.warning(f"生成第5章RMAN信息失败: {e}")

    # 写入文件：<identifier>.rac.md
    rac_md_name = f"{identifier}.rac.md"
    rac_md_path = target_dir / rac_md_name
    content = cover_page + toc_page + document_control + section_1_and_2 + section_2_3
    # 章节分割线
    content += "\n---\n\n"
    if hw_table or db_config_block:
        content += section_3
        if hw_table:
            content += section_3_1_header + hw_table + "\n"
        # 二级分割线：3.1 与 3.2 之间
        if hw_table and db_config_block:
            content += "---\n\n"
        if db_config_block:
            content += section_3_2_header + db_config_block
        # 章节分割线
        content += "\n---\n\n"
    if section_4_block:
        content += "\n# 4. 操作系统检查\n\n" + section_4_block
        content += "\n---\n\n"
    if section_5_block:
        content += "\n# 5. 数据库配置检查\n\n" + section_5_block
        content += "\n---\n\n"
    # 6. 数据库性能检查（前置引言+两节点AWR基础信息；随后装载 6.1~6.4 并加分割线；6.5 统一结论）
    try:
        if node1_sid and node2_sid:
            n1 = ordered_nodes[0]
            n2 = ordered_nodes[1] if len(ordered_nodes) > 1 else None
            if n2:
                md1 = _find_node_md_by_sid(target_dir, n1.get('sid', ''))
                md2 = _find_node_md_by_sid(target_dir, n2.get('sid', ''))
                # 6. 引言与基础AWR三图
                prelude = _build_ch6_prelude(
                    hostname1=n1.get('hostname',''), sid1=n1.get('sid',''),
                    hostname2=n2.get('hostname',''), sid2=n2.get('sid',''),
                    customer_unit=customer_unit, customer_system=customer_system,
                    db_model_display=db_model_display,
                )
                sec61_1 = _extract_6_1_body_from_md(md1) if md1 else None
                sec61_2 = _extract_6_1_body_from_md(md2) if md2 else None
                sec62_1 = _extract_6_2_body_from_md(md1) if md1 else None
                sec62_2 = _extract_6_2_body_from_md(md2) if md2 else None
                sec63_1 = _extract_6_3_body_from_md(md1) if md1 else None
                sec63_2 = _extract_6_3_body_from_md(md2) if md2 else None
                sec64_1 = _extract_6_4_body_from_md(md1) if md1 else None
                sec64_2 = _extract_6_4_body_from_md(md2) if md2 else None

                parts6: List[str] = []
                if any([sec61_1, sec61_2, sec62_1, sec62_2, sec63_1, sec63_2, sec64_1, sec64_2]):
                    parts6.append(prelude)
                    if sec61_1 or sec61_2:
                        parts6.append("## 6.1. 数据库实例命中率\n\n")
                        if sec61_1:
                            parts6.append(f"### {n1.get('hostname','')} ({n1.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec61_1.strip(), n1.get('hostname',''), n1.get('sid','')) + "\n\n")
                        if sec61_2:
                            parts6.append(f"### {n2.get('hostname','')} ({n2.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec61_2.strip(), n2.get('hostname',''), n2.get('sid','')) + "\n\n")
                        parts6.append("综合结论：【请填写结论】\n\n")
                        parts6.append("---\n\n")
                    if sec62_1 or sec62_2:
                        parts6.append("## 6.2. 数据库资源消耗时间模型\n\n")
                        if sec62_1:
                            parts6.append(f"### {n1.get('hostname','')} ({n1.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec62_1.strip(), n1.get('hostname',''), n1.get('sid','')) + "\n\n")
                        if sec62_2:
                            parts6.append(f"### {n2.get('hostname','')} ({n2.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec62_2.strip(), n2.get('hostname',''), n2.get('sid','')) + "\n\n")
                        parts6.append("综合结论：【请填写结论】\n\n")
                        parts6.append("---\n\n")
                    if sec63_1 or sec63_2:
                        parts6.append("## 6.3. 数据库等待事件\n\n")
                        if sec63_1:
                            parts6.append(f"### {n1.get('hostname','')} ({n1.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec63_1.strip(), n1.get('hostname',''), n1.get('sid','')) + "\n\n")
                        if sec63_2:
                            parts6.append(f"### {n2.get('hostname','')} ({n2.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec63_2.strip(), n2.get('hostname',''), n2.get('sid','')) + "\n\n")
                        parts6.append("综合结论：【请填写结论】\n\n")
                        parts6.append("---\n\n")
                    if sec64_1 or sec64_2:
                        parts6.append("## 6.4. TOP SQL\n\n")
                        if sec64_1:
                            parts6.append(f"### {n1.get('hostname','')} ({n1.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec64_1.strip(), n1.get('hostname',''), n1.get('sid','')) + "\n\n")
                        if sec64_2:
                            parts6.append(f"### {n2.get('hostname','')} ({n2.get('sid','')})\n\n")
                            parts6.append(_rewrite_awrpicture_links_for_node(sec64_2.strip(), n2.get('hostname',''), n2.get('sid','')) + "\n\n")
                        parts6.append("综合结论：【请填写结论】\n\n")
                        parts6.append("---\n\n")
                    # 6.5 - 统一评估标题 + 结论占位
                    parts6.append("## 6.5. 数据库实例负载整体评估\n\n")
                    parts6.append("综合结论：【请填写结论】\n\n")
                content += "".join(parts6)
    except Exception as e:
        logger.warning(f"生成第6章数据库性能检查失败: {e}")
    # 在所有代码块（```...```）结束后自动插入一条分割线，增强可读性
    content = _add_hr_after_code_blocks(content)
    rac_md_path.write_text(content, encoding='utf-8')

    if not quiet:
        logger.info(f"RAC 初始Markdown已生成: {rac_md_path}")

    # 生成 RAC 可编辑HTML，并清理节点级 MD/HTML
    try:
        conv = MarkdownToPdfConverter()
        ok, editable_path = conv.generate_editable_html(
            md_file=str(rac_md_path),
            output_dir=str(target_dir),
            output_name=rac_md_path.stem,
        )
        if not ok:
            logger.warning("RAC 可编辑HTML生成失败")
        else:
            logger.info(f"RAC 可编辑HTML已生成: {editable_path}")
            _cleanup_node_md_html(target_dir, rac_md_path, Path(editable_path))
    except Exception as e:
        logger.warning(f"生成RAC可编辑HTML或清理节点文件时异常: {e}")

    return rac_md_path


__all__.append('create_rac_md')


def _add_hr_after_code_blocks(text: str) -> str:
    """在每个 Markdown 代码块关闭标记后追加分割线（---）。"""
    try:
        pattern = re.compile(r"(^```[^\n]*\n[\s\S]*?\n```[ \t]*\n?)(?!\n?---)", re.MULTILINE)
        new_text = pattern.sub(lambda m: m.group(1) + "\n---\n\n", text)
        # 折叠相邻或被空行分隔的重复分割线
        def collapse_hr(s: str) -> str:
            prev = None
            cur = s
            hr_dup = re.compile(r"(?m)^(?:\s*\n)*---\s*\n(?:\s*\n)*---\s*\n")
            for _ in range(5):
                prev = cur
                cur = hr_dup.sub("\n---\n\n", cur)
                if cur == prev:
                    break
            return cur
        return collapse_hr(new_text)
    except Exception:
        return text

def _guess_support_fields_from_md(dir_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """从已生成的单节点MD中提取 支持工程师/支持时长 字段。

    Returns: (supname, suptime)
    """
    try:
        for md in sorted(dir_path.glob("*.md")):
            try:
                text = md.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            # | 支持工程师 | 王力 |
            m_name = re.search(r"\|\s*支持工程师\s*\|\s*([^|\n]+?)\s*\|", text)
            m_time = re.search(r"\|\s*现场支持总时间（小时）\s*\|\s*([^|\n]+?)\s*\|", text)
            supname = m_name.group(1).strip() if m_name else None
            suptime = m_time.group(1).strip() if m_time else None
            if supname or suptime:
                return supname, suptime
    except Exception:
        pass
    return None, None


def _find_node_md_by_sid(dir_path: Path, sid: str) -> Optional[Path]:
    """在目标目录下根据 SID 推断该节点的单机 MD 文件路径。"""
    # 优先模式：*_{sid}.md
    cands = sorted(dir_path.glob(f"*_{sid}.md"))
    for c in cands:
        # 排除最终 rac.md
        if c.name.endswith('.rac.md'):
            continue
        return c
    # 次选：包含 sid 的 md
    for c in sorted(dir_path.glob("*.md")):
        if c.name.endswith('.rac.md'):
            continue
        if sid in c.stem:
            return c
    return None


def _parse_system_hardware_table_from_md(md_path: Path) -> Tuple[List[str], Dict[str, Tuple[str, str]]]:
    """从单节点 MD 中提取“3.1. 系统硬件配置”表格。

    返回 (keys_order, mapping)
    mapping: key -> (value, desc)
    """
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    # 定位章节
    start = text.find("## 3.1. 系统硬件配置")
    if start == -1:
        return [], {}
    # 获取从该位置开始的子串
    sub = text[start:]
    lines = sub.splitlines()
    # 跳过标题行，找到以 '|' 开始的表格
    table_lines: List[str] = []
    in_table = False
    for ln in lines[1:]:
        if ln.strip().startswith('|'):
            in_table = True
            table_lines.append(ln)
        else:
            if in_table:
                break
    if not table_lines:
        return [], {}
    # 解析表格（忽略表头与分隔线）
    rows = [r for r in table_lines if re.search(r"\|\s*-+\s*\|", r) is None]
    # 第一行为表头，跳过
    if rows:
        rows = rows[1:]
    order: List[str] = []
    mapping: Dict[str, Tuple[str, str]] = {}
    for r in rows:
        seg = [s.strip() for s in r.strip().strip('|').split('|')]
        if len(seg) < 3:
            continue
        key = seg[0]
        val = seg[1]
        desc = seg[2]
        if key and key not in mapping:
            order.append(key)
            mapping[key] = (val, desc)
    return order, mapping


def _build_dual_node_system_hardware_table(
    md1: Path,
    md2: Path,
    sid1: str,
    sid2: str,
    hostname1: Optional[str] = None,
    hostname2: Optional[str] = None,
) -> str:
    """并列合并两个节点的系统硬件配置表格。

    Header: | SR | SRVVal({sid1}) | SRVVal({sid2}) | 说明 |
    顺序：以节点1的键顺序为主，追加节点2中缺失键。
    """
    order1, map1 = _parse_system_hardware_table_from_md(md1)
    order2, map2 = _parse_system_hardware_table_from_md(md2)

    # 构造顺序
    keys: List[str] = list(order1)
    for k in order2:
        if k not in keys:
            keys.append(k)

    col1 = hostname1 or 'sid1'
    col2 = hostname2 or 'sid2'
    # header = f"| SR | {col1} | {col2} | 说明 |\n|---|---|---|---|\n"
    header = f"| 计算节点参数名 | 计算节点一 | 计算节点二 | 说明 |\n|---|---|---|---|\n"
    lines: List[str] = []
    for k in keys:
        v1, d1 = map1.get(k, ("", ""))
        v2, d2 = map2.get(k, ("", d1))
        desc = d1 or d2
        lines.append(f"| {k} | {v1} | {v2} | {desc} |")
    return header + "\n".join(lines)


def _parse_named_table_from_md(md_path: Path, title_zh: str) -> Dict[str, Tuple[str, str]]:
    """解析以加粗标题（如 **数据库基本信息：**）开头的第一个表格为映射。

    返回: key -> (value, desc)
    """
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    # 定位加粗段落，允许有全角/半角 冒号
    # 允许粗体内包含中文或英文冒号：**数据库基本信息：** 或 **数据库基本信息**
    pattern = rf"\*\*\s*{re.escape(title_zh)}\s*[：:]?\s*\*\*"
    m = re.search(pattern, text)
    if not m:
        return {}
    start = m.end()
    sub = text[start:]
    table_lines: List[str] = []
    in_table = False
    for ln in sub.splitlines():
        if ln.strip().startswith('|'):
            in_table = True
            table_lines.append(ln)
        else:
            if in_table:
                break
    if not table_lines:
        return {}
    # 跳过分隔线
    rows = [r for r in table_lines if re.search(r"\|\s*-+\s*\|", r) is None]
    # 第1行为表头
    if rows:
        rows = rows[1:]
    mapping: Dict[str, Tuple[str, str]] = {}
    for r in rows:
        seg = [s.strip() for s in r.strip().strip('|').split('|')]
        if len(seg) < 3:
            continue
        key, val, desc = seg[0], seg[1], seg[2]
        mapping[key] = (val, desc)
    return mapping


def _build_db_basic_info_combined_table(
    sid1: str,
    map1: Dict[str, Tuple[str, str]],
    sid2: str,
    map2: Dict[str, Tuple[str, str]],
    hostname1: Optional[str] = None,
    hostname2: Optional[str] = None,
) -> str:
    """构造“数据库基本信息”展示：

    - 六个关键字段以四列表展示：| 配置项 | {sid1} | {sid2} | 说明 |
      (DB_SID、CURRENT_SESSION、HOST_NAME、STARTUP_TIME、LOG_MODE、ARCHIVE_MODE)
      其中 HOST_NAME 强制使用 JSON 中的 hostname（避免单机MD误差）。

    - 其他字段以原三列表展示：| 配置项 | 配置值 | 说明 |，值优先节点1，缺则节点2。

    - 行顺序：按模板常见顺序，未知键追加末尾（字典序）。
    """
    # 模板常见顺序与默认说明
    default_desc = {
        "DB_OF_APP": "数据库用途",
        "CURRENT_SESSION": "当前活动连接数",
        "DB_SID": "Oracle实例标识",
        "DB_NAME": "数据库名称标识",
        "DB_UNIQUE_NAME": "数据库唯一名称",
        "DATABASE_VERSION": "Oracle数据库版本",
        "DATABASE_ROLE": "数据库角色",
        "OPEN_MODE": "数据库打开模式",
        "HOST_NAME": "主机名称",
        "STARTUP_TIME": "启动时间",
        "NLS_LANGUAGE": "国际化语言",
        "NLS_TERRITORY": "国际化地区",
        "DATABASE_CHARSET": "数据库字符编码",
        "DATABASE_NCHARSET": "国家字符编码",
        "LOG_MODE": "日志模式",
        "ARCHIVE_MODE": "归档模式",
        "CONTROL_FILE_COUNT": "控制文件数量",
        "LOG_MEMBERS_PER_GROUP": "日志组成员数",
        "ONLINE_LOGS_SAME_SIZE": "在线日志文件大小一致性",
    }
    canonical_order = [
        "DB_OF_APP",
        "CURRENT_SESSION",
        "DB_SID",
        "DB_NAME",
        "DB_UNIQUE_NAME",
        "DATABASE_VERSION",
        "DATABASE_ROLE",
        "OPEN_MODE",
        "HOST_NAME",
        "STARTUP_TIME",
        "NLS_LANGUAGE",
        "NLS_TERRITORY",
        "DATABASE_CHARSET",
        "DATABASE_NCHARSET",
        "LOG_MODE",
        "ARCHIVE_MODE",
        "CONTROL_FILE_COUNT",
        "LOG_MEMBERS_PER_GROUP",
        "ONLINE_LOGS_SAME_SIZE",
    ]
    multiline_keys: List[str] = [
        "DB_SID", "CURRENT_SESSION", "HOST_NAME", "STARTUP_TIME", "LOG_MODE", "ARCHIVE_MODE"
    ]

    # 合并键集合
    all_keys: List[str] = []
    for k in canonical_order:
        if (k in map1) or (k in map2) or (k in default_desc):
            all_keys.append(k)
    # 追加未知键
    for k in sorted(set(list(map1.keys()) + list(map2.keys()))):
        if k not in all_keys:
            all_keys.append(k)

    # 先构建四列表（六个关键字段）
    header_4 = f"| 配置项 | 计算节点一 | 计算节点二 | 说明 |\n|---|---|---|---|\n"
    rows_4: List[str] = []
    for key in multiline_keys:
        desc_name = map1.get(key, (None, None))[1] or map2.get(key, (None, None))[1] or default_desc.get(key, "")
        if key == "DB_SID":
            v1 = sid1
            v2 = sid2
        elif key == "HOST_NAME":
            v1 = hostname1 or map1.get(key, ("", ""))[0]
            v2 = hostname2 or map2.get(key, ("", ""))[0]
        else:
            v1 = map1.get(key, ("", ""))[0]
            v2 = map2.get(key, ("", ""))[0]
        # 若两个值均为空，跳过该行
        if not (str(v1).strip() or str(v2).strip()):
            continue
        rows_4.append(f"| {key} | {v1} | {v2} | {desc_name} |")

    table_4 = header_4 + "\n".join(rows_4) if rows_4 else ""

    # 再构建三列表（其余字段）
    header_3 = "| 配置项 | 配置值 | 说明 |\n|---|---|---|\n"
    rows_3: List[str] = []
    for key in all_keys:
        if key in multiline_keys:
            continue
        desc_name = map1.get(key, (None, None))[1] or map2.get(key, (None, None))[1] or default_desc.get(key, "")
        v = map1.get(key, ("", ""))[0] or map2.get(key, ("", ""))[0]
        rows_3.append(f"| {key} | {v} | {desc_name} |")

    table_3 = header_3 + "\n".join(rows_3) if rows_3 else ""

    parts: List[str] = []
    if table_4:
        parts.append("**rac实例基本信息：**\n\n" + table_4)
    if table_3:
        parts.append("**数据库基本信息：**\n\n" + table_3)
    return "\n\n".join(parts)


def _build_db_space_info_combined_table(
    sid1: str,
    map1: Dict[str, Tuple[str, str]],
    sid2: str,
    map2: Dict[str, Tuple[str, str]],
) -> str:
    """构造“数据库使用空间”三列表，配置值一列按节点分行显示。

    支持键名差异（如 DB_BLOCK SIZE 与 DB_BLOCK_SIZE）。
    仅当任一节点存在该键时输出对应行。
    """
    key_variants: List[Tuple[List[str], str]] = [
        (["TOTAL_DATAFILE_SIZE_MB"], "数据文件总大小"),
        (["TOTAL_SEGMENT_SIZE_MB"], "已使用的段空间"),
        (["DB_BLOCK SIZE", "DB_BLOCK_SIZE"], "数据块大小(字节)"),
        (["TABLESPACE_COUNT"], "表空间总数"),
        (["DATAFILE_COUNT"], "数据文件总数"),
        (["TEMP_TABLESPACE_SIZE"], "临时表空间大小"),
        (["UNDO_TABLESPACE_SIZE"], "撤销表空间大小"),
        (["UNDOTBS2"], "撤销表空间2大小"),
    ]

    header = "| 配置项 | 配置值 | 说明 |\n|---|---|---|\n"
    lines: List[str] = []
    for keys, desc_name in key_variants:
        # 选择显示名（优先节点1的键名，否则节点2）
        display_key = None
        for k in keys:
            if k in map1:
                display_key = k
                break
        if not display_key:
            for k in keys:
                if k in map2:
                    display_key = k
                    break
        if not display_key:
            # 两节点均无该键，跳过
            continue
        v1 = ""
        v2 = ""
        for k in keys:
            if k in map1:
                v1 = map1[k][0]
                break
        for k in keys:
            if k in map2:
                v2 = map2[k][0]
                break
        # RAC 两节点通常共享存储，空间统计相同；保持单机展示逻辑，单值展示（优先节点1，缺则节点2）
        value_cell = v1 or v2
        lines.append(f"| {display_key} | {value_cell} | {desc_name} |")
    return header + "\n".join(lines)


def _build_node_key_table(
    sid1: str,
    map1: Dict[str, Tuple[str, str]],
    sid2: str,
    map2: Dict[str, Tuple[str, str]],
    keys: List[str],
    header_prefix: str = "SRVVal",
) -> str:
    """构造四列表：节点 | 配置项 | 配置值 | 说明，两个节点各占一行/项。"""
    header = "| 节点 | 配置项 | 配置值 | 说明 |\n|--|---|---|---|\n"
    lines: List[str] = []
    for key in keys:
        # 节点1
        v1, d1 = map1.get(key, ("", ""))
        label1 = f"{header_prefix}({sid1})" if header_prefix else f"{sid1}"
        lines.append(f"| {label1} | {key} | {v1} | {d1} |")
        # 节点2
        v2, d2 = map2.get(key, ("", d1))
        label2 = f"{header_prefix}({sid2})" if header_prefix else f"{sid2}"
        lines.append(f"| {label2} | {key} | {v2} | {d2} |")
    return header + "\n".join(lines)


def _find_health_check_path(nodes: List[Dict[str, Any]]) -> Optional[Path]:
    """在给定节点列表中按顺序查找 04_health_check.txt 路径。
    优先 node1，其次 node2。"""
    for node in nodes:
        files = node.get('files') or {}
        hc = files.get('04_health_check')
        if hc and isinstance(hc, dict) and hc.get('path'):
            return Path(hc['path'])
    return None


def _parse_log_config_from_health_check(hc_path: Path, sid1: str, sid2: str) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]]]:
    """从 04_health_check.txt 中解析 C1. 重要日志文件路径，返回两个节点的映射。

    返回 map: key -> (value, desc)，key 为：
    - ALERT_LOG_PATH, AUDIT_FILE_DEST_PATH, CORE_DUMP_DEST_PATH, DIAGNOSTIC_DEST_PATH, USER_DUMP_DEST_PATH
    """
    text = hc_path.read_text(encoding='utf-8', errors='ignore')
    # 在全文件范围内通过关键字提取（不依赖行号）
    # 允许 AUDIT_FIL_DEST 的拼写变体
    pat = re.compile(r"^\s*(\d+)\s+(ALERT_LOG|AUDIT_FILE_DEST|AUDIT_FIL_DEST|CORE_DUMP_DEST|DIAGNOSTIC_DEST|USER_DUMP_DEST)\s+(.+?)\s*$",
                     re.MULTILINE)

    # 描述映射
    desc_map = {
        'ALERT_LOG_PATH': '警告日志文件路径',
        'AUDIT_FILE_DEST_PATH': '审计文件存储路径',
        'CORE_DUMP_DEST_PATH': '核心转储文件路径',
        'DIAGNOSTIC_DEST_PATH': '诊断文件根路径',
        'USER_DUMP_DEST_PATH': '用户转储文件路径',
    }
    key_map = {
        'ALERT_LOG': 'ALERT_LOG_PATH',
        'AUDIT_FILE_DEST': 'AUDIT_FILE_DEST_PATH',
        'AUDIT_FIL_DEST': 'AUDIT_FILE_DEST_PATH',
        'CORE_DUMP_DEST': 'CORE_DUMP_DEST_PATH',
        'DIAGNOSTIC_DEST': 'DIAGNOSTIC_DEST_PATH',
        'USER_DUMP_DEST': 'USER_DUMP_DEST_PATH',
    }

    map1: Dict[str, Tuple[str, str]] = {}
    map2: Dict[str, Tuple[str, str]] = {}

    for m in pat.finditer(text):
        inst = m.group(1)
        param = m.group(2)
        val = m.group(3).strip()
        key = key_map.get(param)
        if not key:
            continue
        desc = desc_map[key]
        if inst == '1':
            map1[key] = (val, desc)
        elif inst == '2':
            map2[key] = (val, desc)

    # 确保所有键存在（若缺失则置空）
    for k in desc_map.keys():
        map1.setdefault(k, ("", desc_map[k]))
        map2.setdefault(k, ("", desc_map[k]))

    return map1, map2


def _parse_control_file_count(hc_path: Path) -> Optional[int]:
    """从 04_health_check.txt 的 'C2. 控制文件路径' 段落中统计控制文件数量。

    仅使用关键字定位：先定位标题，再截取到下一小节标题，最后按行匹配路径。
    """
    text = hc_path.read_text(encoding='utf-8', errors='ignore')
    # 1) 标题定位（允许任意空白/标点差异）
    m = re.search(r"(?im)^\s*C2\.\s*.*?控制文件路径\s*$", text)
    if not m:
        return None
    start = m.end()
    # 2) 找到下一节标题的开始位置（如 C3. 或 8. 开头的标题）
    m_next = re.search(r"(?im)^\s*(?:C\d+\.|\d+\.)\s*", text[start:])
    end = start + m_next.start() if m_next else len(text)
    block = text[start:end]

    # 3) 在 block 中匹配路径行：以 + 或 / 开头的非空白字符串
    #    同时忽略表头和分隔线
    paths: List[str] = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        if 'CONTROL_FILE_PATH' in s:
            continue
        if re.match(r"^[\-\s]+$", s):
            continue
        m_path = re.match(r"^([+/][^\s]+)$", s)
        if m_path:
            paths.append(m_path.group(1))
        else:
            # 宽松回退：捕捉包含 controlfile 的路径片段
            m2 = re.search(r"([+/]\S*controlfile\S*)", s, re.IGNORECASE)
            if m2:
                paths.append(m2.group(1))
    return len(paths) if paths else None


def _parse_online_logs_same_size(hc_path: Path) -> Optional[str]:
    """从 04_health_check.txt 的 '8.日志文件信息' 表格判断在线日志大小是否一致。

    返回：'是' | '否' | None（无法判断）
    """
    text = hc_path.read_text(encoding='utf-8', errors='ignore')
    # 找到段落
    m = re.search(r"\b8\.\s*日志文件信息", text)
    if not m:
        return None
    sub = text[m.end():]

    lines = sub.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if 'INST_ID' in line and 'MBYTES' in line:
            header_idx = idx
            break
    if header_idx is None:
        return None
    # 提取表头列名，计算 MBYTES 列索引
    header_cols = re.split(r"\s+", lines[header_idx].strip())
    try:
        mbytes_idx = header_cols.index('MBYTES')
    except ValueError:
        return None

    sizes: Set[str] = set()
    for line in lines[header_idx+1:]:
        s = line.strip()
        if not s:
            continue
        if s.lower().startswith('total'):
            break
        if re.match(r"^[\-\s]+$", s):
            continue
        # 数据行一般以数字开头
        if not re.match(r"^\d+\s+", s):
            # 可能到了下一段
            # 若遇到像 "C" 或 数字. 标题，终止
            if re.match(r"^[A-Z]?\d+\.", s):
                break
            continue
        cols = re.split(r"\s+", s)
        if len(cols) <= mbytes_idx:
            continue
        sizes.add(cols[mbytes_idx])

    if not sizes:
        return None
    return '是' if len(sizes) == 1 else '否'


def _extract_disk_space_table_from_md(md_path: Path) -> Optional[str]:
    """从单节点MD提取 4.4 磁盘空间使用率 表格（首个表格）。"""
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    # 兼容 "## 4.4.磁盘空间使用率" 或 "## 4.4. 磁盘空间使用率"
    m = re.search(r"(?m)^##\s*4\.4\.?\s*.*磁盘空间使用率\s*$", text)
    if not m:
        return None
    sub = text[m.end():]
    table_lines: List[str] = []
    in_table = False
    for ln in sub.splitlines():
        if ln.startswith('#'):
            break
        if ln.strip().startswith('|'):
            in_table = True
            table_lines.append(ln)
        else:
            if in_table:
                break
    return "\n".join(table_lines) if table_lines else None


def _build_section_4_content(target_dir: Path, hostname1: str, sid1: str, hostname2: str, sid2: str) -> str:
    """构建第4章：操作系统检查内容（两节点）。"""
    hn1_sid = f"{hostname1}_{sid1}"
    hn2_sid = f"{hostname2}_{sid2}"

    intro = (
        "以下的部分是对操作系统的检查，可以从中确定一些性能方面的问题。这个分析主要使用的是操作系统自带的命令和工具。\n\n"
        "主要从以下方面来检查操作系统的性能：\n\n"
        "- CPU 利用率\n"
        "- 内存利用率\n"
        "- 磁盘IO使用率\n"
        "- 磁盘空间使用率\n\n"
        " (这部分的检查并不是针对操作系统或硬件的全面深入的检查，如有上述要求请与操作系统厂商联系)\n\n"
    )

    sec_41 = (
        "## 4.1.CPU使用率\n\n"
        f"**以下是**计算节点 {hostname1} **的CPU使用情况：**\n\n"
        f"![CPU使用率趋势图]({hn1_sid}_server_picture/cpu_usage_chart.png)\n\n"
        f"**以下是**计算节点 {hostname2} **的CPU使用情况：**\n\n"
        f"![CPU使用率趋势图]({hn2_sid}_server_picture/cpu_usage_chart.png)\n\n"
    )

    sec_42 = (
        "## 4.2.内存使用率\n\n"
        f"**以下是**计算节点 {hostname1} **的内存使用情况：**\n\n"
        f"![内存使用率趋势图]({hn1_sid}_server_picture/memory_usage_chart.png)\n\n"
        f"**以下是**计算节点 {hostname2} **的内存使用情况：**\n\n"
        f"![内存使用率趋势图]({hn2_sid}_server_picture/memory_usage_chart.png)\n\n"
    )

    sec_43 = (
        "## 4.3.磁盘IO使用率\n\n"
        f"**以下是**计算节点 {hostname1} **的磁盘IO使用率：**\n\n"
        f"![磁盘IO使用率趋势图]({hn1_sid}_server_picture/disk_io_chart.png)\n\n"
        f"**以下是**计算节点 {hostname2} **的磁盘IO使用率：：**\n\n"
        f"![磁盘IO使用率趋势图]({hn2_sid}_server_picture/disk_io_chart.png)\n\n"
    )

    # 磁盘空间表格从各自MD提取
    md1 = _find_node_md_by_sid(target_dir, sid1)
    md2 = _find_node_md_by_sid(target_dir, sid2)
    table1 = _extract_disk_space_table_from_md(md1) if md1 else None
    table2 = _extract_disk_space_table_from_md(md2) if md2 else None

    sec_44 = (
        "## 4.4.磁盘空间使用率\n\n"
        f"**以下是**计算节点 {hostname1} **的磁盘空间使用率：**\n\n"
        f"{(table1 or '')}\n\n"
        f"**以下是**计算节点 {hostname2} **的磁盘空间使用率：**\n\n"
        f"{(table2 or '')}\n\n\n"
        "综合结论：【请填写结论】\n"
    )

    # 在4.x各小节之间增加分割线
    return intro + sec_41 + "---\n\n" + sec_42 + "---\n\n" + sec_43 + "---\n\n" + sec_44


def _extract_rman_5_1_body_from_md(md_path: Path, hostname: str, sid: str) -> Optional[str]:
    """提取节点MD中的“## 5.1.RMAN 备份信息”正文（不含标题）。

    - 截止到下一个以“## ”开头的同级标题或章节结束。
    - 去除末尾的“综合结论：…”行（若存在）。
    """
    if not md_path or not md_path.exists():
        return None
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    # 找起始标题
    m = re.search(r"(?m)^##\s*5\.1\.?\s*RMAN\s*备份信息\s*$", text)
    if not m:
        return None
    start = m.end()
    # 找到下一个二级标题或章节标题
    m_next = re.search(r"(?m)^##\s+\d+\.", text[start:])
    end = start + m_next.start() if m_next else len(text)
    body = text[start:end].strip()
    # 去掉标题行残留及多余空白
    # 删除“综合结论：”行
    body = re.sub(r"(?m)^\s*综合结论：.*$", "", body).strip()
    if not body:
        return None

    # 重写三段小标题，加入“节点 {hostname} ({sid}) {customer_system} …”
    customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_system", "")
    def repl(line_suffix: str) -> str:
        node_prefix = f"【{sid}】 " if hostname or sid else ""
        return f"**{node_prefix}{customer_system} Oracle 数据库 {line_suffix}**"

    # 备份策略
    body = re.sub(
        r"(?m)^\*\*.*?Oracle\s*数据库\s*RMAN\s*备份策略如下：\*\*$",
        repl("RMAN 备份策略如下："),
        body,
    )
    # 备份集路径
    body = re.sub(
        r"(?m)^\*\*.*?Oracle\s*数据库\s*RMAN\s*备份集路径如下：\*\*$",
        repl("RMAN 备份集路径如下："),
        body,
    )
    # 备份集合明细
    body = re.sub(
        r"(?m)^\*\*.*?Oracle\s*数据库\s*RMAN\s*备份集合明细如下：\*\*$",
        repl("RMAN 备份集合明细如下："),
        body,
    )

    return body


def _extract_dg_5_2_body_from_md(md_path: Path) -> Optional[str]:
    """提取节点MD中的“## 5.2. 数据库 Data Guard 容灾”正文（不含标题）。

    截止到下一个以“## ”开头的同级标题或章节结束。保持原样，不改动内部逻辑。"""
    if not md_path or not md_path.exists():
        return None
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    m = re.search(r"(?m)^##\s*5\.2\.?\s*数据库\s*Data\s*Guard\s*容灾\s*$", text)
    if not m:
        return None
    start = m.end()
    m_next = re.search(r"(?m)^##\s+\d+\.", text[start:])
    end = start + m_next.start() if m_next else len(text)
    body = text[start:end].strip()
    return body if body else None


def _extract_5_3_body_from_md(md_path: Path, hostname: str, sid: str) -> Optional[str]:
    """提取节点MD中的“## 5.3. ADRCI、ALERT 日志检查”正文（不含标题）。

    - 截止到下一个以“## ”开头的同级标题或章节结束。
    - 去除“综合结论：”行，其他内容保持原样。
    """
    if not md_path or not md_path.exists():
        return None
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    m = re.search(r"(?m)^##\s*5\.3\.?\s*ADRCI、ALERT\s*日志检查\s*$", text)
    if not m:
        return None
    start = m.end()
    m_next = re.search(r"(?m)^##\s+\d+\.", text[start:])
    end = start + m_next.start() if m_next else len(text)
    body = text[start:end].strip()
    body = re.sub(r"(?m)^\s*综合结论：.*$", "", body).strip()
    if not body:
        return None

    # 重写两段小标题，加入“{hostname} ({sid}) {customer_system} …”
    customer_system = MarkdownConfig.TEMPLATE_PLACEHOLDERS.get("customer_system", "")
    # node_prefix = f"{hostname} ({sid}) " if (hostname or sid) else ""
    node_prefix = f"【{sid}】 " if (hostname or sid) else ""
    # ADRCI 诊断工具日志检查
    body = re.sub(
        r"(?m)^\*\*\s*.*?ADRCI\s*诊断工具日志检查：\s*\*\*\s*$",
        f"**{node_prefix}{customer_system} ADRCI 诊断工具日志检查：**",
        body,
    )
    # ALERT日志检查（两种形式：带冒号与不带冒号）
    body = re.sub(
        r"(?m)^\*\*\s*.*?ALERT日志检查\s*\*\*：\s*$",
        f"**{node_prefix}{customer_system} ALERT日志检查**：",
        body,
    )
    body = re.sub(
        r"(?m)^\*\*\s*.*?ALERT日志检查\s*\*\*\s*$",
        f"**{node_prefix}{customer_system} ALERT日志检查**：",
        body,
    )

    return body


def _extract_section_body(md_path: Path, header_patterns: List[str]) -> Optional[str]:
    """通用：按给定标题正则列表尝试提取某节正文（不含标题），到下一 '## <number>.' 标题或文件末尾。
    第一个命中的模式使用。"""
    if not md_path or not md_path.exists():
        return None
    text = md_path.read_text(encoding='utf-8', errors='ignore')
    for pat in header_patterns:
        m = re.search(pat, text, flags=re.MULTILINE)
        if not m:
            continue
        start = m.end()
        # 截至下一章节标题（支持任意级别 #...）
        m_next = re.search(r"(?m)^#{1,6}\s+\d+\.\s*", text[start:])
        end = start + m_next.start() if m_next else len(text)
        body = text[start:end].strip()
        return body if body else None
    return None


def _extract_5_4_body_from_md(md_path: Path) -> Optional[str]:
    return _extract_section_body(md_path, [r"(?m)^##\s*5\.4\.?\s*控制文件和在线日志文件\s*$"])


def _extract_5_5_body_from_md(md_path: Path) -> Optional[str]:
    return _extract_section_body(md_path, [r"(?m)^##\s*5\.5\.?\s*表空间数据文件、归档文件明细\s*$"])


def _extract_5_6_body_from_md(md_path: Path) -> Optional[str]:
    # 兼容“ASM 磁盘信息”与“ASM磁盘详细信息”
    return _extract_section_body(md_path, [
        r"(?m)^##\s*5\.6\.?\s*ASM\s*磁盘信息\s*$",
        r"(?m)^##\s*5\.6\.?\s*ASM\s*磁盘详细信息\s*$",
    ])


def _extract_5_7_body_from_md(md_path: Path) -> Optional[str]:
    return _extract_section_body(md_path, [r"(?m)^##\s*5\.7\.?\s*PL/SQLDeveloper破解版勒索病毒检查\s*$"])


def _strip_conclusion_lines(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return re.sub(r"(?m)^\s*综合结论：.*$", "", text).strip()


def _extract_6_1_body_from_md(md_path: Path) -> Optional[str]:
    return _strip_conclusion_lines(_extract_section_body(md_path, [r"(?m)^##\s*6\.1\.?\s*数据库实例命中率\s*$"]))


def _extract_6_2_body_from_md(md_path: Path) -> Optional[str]:
    return _strip_conclusion_lines(_extract_section_body(md_path, [r"(?m)^##\s*6\.2\.?\s*数据库资源消耗时间模型\s*$"]))


def _extract_6_3_body_from_md(md_path: Path) -> Optional[str]:
    return _strip_conclusion_lines(_extract_section_body(md_path, [r"(?m)^##\s*6\.3\.?\s*数据库等待事件\s*$"]))


def _extract_6_4_body_from_md(md_path: Path) -> Optional[str]:
    return _strip_conclusion_lines(_extract_section_body(md_path, [r"(?m)^##\s*6\.4\.?\s*TOP\s*SQL\s*$"]))


def _get_node_file_path_by_key(node: Dict[str, Any], key: str) -> Optional[Path]:
    files = node.get('files') or {}
    info = files.get(key)
    if isinstance(info, dict) and info.get('path'):
        p = Path(info['path'])
        return p if p.exists() else None
    return None


def _read_node_file_all(node: Dict[str, Any], key: str) -> Optional[str]:
    p = _get_node_file_path_by_key(node, key)
    if not p:
        return None
    try:
        return p.read_text(encoding='utf-8', errors='ignore').strip()
    except Exception:
        return None


def _extract_multipath_section_from_node(node: Dict[str, Any]) -> Optional[str]:
    """读取节点 07_multipath.txt，从关键字“== 多路径磁盘详细状态 ==”开始到文件结尾。"""
    p = _get_node_file_path_by_key(node, '07_multipath')
    if not p:
        return None
    try:
        txt = p.read_text(encoding='utf-8', errors='ignore')
        idx = txt.find('== 多路径磁盘详细状态 ==')
        if idx == -1:
            # 若未找到关键字，返回全文（或None皆可）。这里返回全文以便人工判读
            return txt.strip()
        return txt[idx:].strip()
    except Exception:
        return None


def _extract_crs_info_sections(node: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """从 08_crs_info.txt 提取三个片段：
    - CRS资源状态：从 "== CRS资源状态" 开始，到 "== Voting Disk Information ==" 之前
    - Voting Disk 信息：从 Voting heading 上一行的分隔线开始，到 OCR heading 上一行的分隔线结束
    - OCR检查：从 "== OCR检查" 开始到文件末尾
    若节点无文件，三者均返回 None。
    """
    p = _get_node_file_path_by_key(node, '08_crs_info')
    if not p:
        return None, None, None
    try:
        lines = p.read_text(encoding='utf-8', errors='ignore').splitlines()
        n = len(lines)
        # 索引工具
        def find_line_idx(pattern: str) -> Optional[int]:
            rx = re.compile(pattern)
            for i, ln in enumerate(lines):
                if rx.search(ln):
                    return i
            return None

        # 1) CRS资源状态
        crs_start = find_line_idx(r"^\s*==\s*CRS资源状态")
        vote_heading = find_line_idx(r"^\s*==\s*Voting\s+Disk\s+Information\s*==")
        crs_block = None
        if crs_start is not None:
            end = vote_heading if (vote_heading is not None and vote_heading > crs_start) else n
            crs_block = "\n".join(lines[crs_start:end]).strip()

        # 2) Voting Disk 信息
        # 起点：Voting heading 上一行的全等号分隔线；终点：OCR heading 上一行的全等号分隔线
        sep_re = re.compile(r"^\s*=+\s*$")
        ocr_heading = find_line_idx(r"^\s*==\s*OCR检查")
        vote_block = None
        if vote_heading is not None:
            # 向上寻找分隔线
            start_idx = None
            for i in range(vote_heading - 1, -1, -1):
                if sep_re.match(lines[i]):
                    start_idx = i
                    break
            # 结束分隔线
            end_idx = n
            if ocr_heading is not None:
                for i in range(ocr_heading - 1, -1, -1):
                    if sep_re.match(lines[i]):
                        end_idx = i
                        break
            if start_idx is None:
                # 回退到Voting heading本身
                start_idx = vote_heading
            if start_idx < end_idx:
                vote_block = "\n".join(lines[start_idx:end_idx]).strip()

        # 3) OCR检查
        ocr_block = None
        if ocr_heading is not None:
            ocr_block = "\n".join(lines[ocr_heading:]).strip()

        return crs_block, vote_block, ocr_block
    except Exception:
        return None, None, None


def _rewrite_awrpicture_links_for_node(text: str, hostname: str, sid: str) -> str:
    """将提取到的6.x小节中的 ./awr_picture/ 路径改写到 {hostname}_{sid}_awr_picture/。"""
    if not text:
        return text
    prefix = f"{hostname}_{sid}_awr_picture/" if hostname or sid else "awr_picture/"
    # Markdown image or link patterns: (./awr_picture/...) or (awr_picture/...)
    text = re.sub(r"(\()\./?awr_picture/", r"\1" + prefix, text)
    # HTML src attributes
    text = re.sub(r"(src=\")[.]/?awr_picture/", r"\1" + prefix, text)
    text = re.sub(r"(src=')\./?awr_picture/", r"\1" + prefix, text)
    return text


def _build_ch6_prelude(hostname1: str, sid1: str, hostname2: str, sid2: str,
                       customer_unit: str, customer_system: str, db_model_display: str) -> str:
    """构建第6章引言与两节点AWR基础三图。"""
    hs1 = f"{hostname1}_{sid1}_awr_picture"
    hs2 = f"{hostname2}_{sid2}_awr_picture"
    intro = (
        "\n# 6. 数据库性能检查\n\n"
        "数据库的性能情况通过 AWR 的报告来体现。\n\n"
        f"本报告中选取了{customer_unit}{customer_system} Oracle{db_model_display}数据库系统工作峰值时间段进行分析。\n\n"
        f"### {hostname1} ({sid1})\n"
        f"![AWR截图]({hs1}/awr_database_info.png)\n"
        f"![AWR截图]({hs1}/awr_host_info.png)\n"
        f"![AWR截图]({hs1}/awr_snapshot_info.png)\n\n"
        f"### {hostname2} ({sid2})\n"
        f"![AWR截图]({hs2}/awr_database_info.png)\n"
        f"![AWR截图]({hs2}/awr_host_info.png)\n"
        f"![AWR截图]({hs2}/awr_snapshot_info.png)\n\n"
        "---\n\n"
    )
    return intro


def _cleanup_node_md_html(target_dir: Path, rac_md: Path, rac_editable: Path) -> None:
    """删除节点级的 .md 与 .editable.html，保留合并后的 rac.md 与 rac.editable.html。

    - 仅作用于 {identifier} 目标目录，不跨目录删除。
    - 安全过滤：忽略非 .md/.editable.html 文件。
    """
    try:
        for f in target_dir.iterdir():
            if f.is_dir():
                continue
            if f == rac_md or f == rac_editable:
                continue
            name = f.name
            if name.endswith('.rac.md') or name.endswith('.rac.editable.html'):
                # 再保险：保留任何 rac 合并命名
                continue
            if name.endswith('.editable.html') or name.endswith('.md'):
                try:
                    f.unlink()
                    logger.info(f"已删除节点文件: {f}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {f}: {e}")
    except Exception as e:
        logger.warning(f"清理节点MD/HTML失败: {e}")


def _generate_rac_toc() -> str:
    """生成RAC专用目录，包含 5.8/5.9 与 6.5。"""
    return """# 目录

1. [健康检查总结](#1-健康检查总结)
   - 1.1. [健康检查概要](#11-健康检查概要)
   - 1.2. [健康检查建议](#12-健康检查建议)

2. [健康检查介绍](#2-健康检查介绍)
   - 2.1. [健康检查目标](#21-健康检查目标)
   - 2.2. [健康检查方法](#22-健康检查方法)
   - 2.3. [健康检查范围](#23-健康检查范围)

3. [系统背景](#3-系统背景)
   - 3.1. [系统硬件配置](#31-系统硬件配置)
   - 3.2. [数据库配置](#32-数据库配置)

4. [操作系统检查](#4-操作系统检查)
   - 4.1. [CPU 使用率](#41cpu使用率)
   - 4.2. [内存使用率](#42内存使用率)
   - 4.3. [磁盘IO使用率](#43磁盘io使用率)
   - 4.4. [磁盘空间使用情况](#44磁盘空间使用情况)

5. [数据库配置检查](#5-数据库配置检查)
   - 5.1. [RMAN 备份信息](#51rman-备份信息)
   - 5.2. [数据库 Data Guard 容灾](#52-数据库-data-guard-容灾)
   - 5.3. [ADRCI、ALERT 日志检查](#53-adrcialert-日志检查)
   - 5.4. [控制文件和在线日志文件](#54-控制文件和在线日志文件)
   - 5.5. [表空间数据文件、归档文件明细](#55-表空间数据文件归档文件明细)
   - 5.6. [ASM 磁盘信息](#56-asm-磁盘信息)
   - 5.7. [PL/SQLDeveloper破解版勒索病毒检查](#57-plsqldeveloper破解版勒索病毒检查)
   - 5.8. [磁盘多路径、ASM_UDEV 配置](#58-磁盘多路径asm_udev-配置)
   - 5.9. [Oracle Rac 集群信息检查](#59-oracle-rac-集群信息检查)

6. [数据库性能检查](#6-数据库性能检查)
   - 6.1. [数据库实例命中率](#61-数据库实例命中率)
   - 6.2. [数据库资源消耗时间模型](#62-数据库资源消耗时间模型)
   - 6.3. [数据库等待事件](#63-数据库等待事件)
   - 6.4. [TOP SQL](#64-top-sql)
   - 6.5. [数据库实例负载整体评估](#65-数据库实例负载整体评估)

---
"""
