"""
Markdown到PDF转换器与可编辑HTML生成器
说明：在保持既有 Markdown→HTML→PDF 能力的基础上，新增可编辑HTML生成功能，
以便工程师在HTML阶段填写“建议/综合结论”等内容。
"""
import re
import os
try:
    import markdown as _markdown
except ImportError:
    _markdown = None
from pathlib import Path
from typing import Tuple, List
from loguru import logger
from ..common.config import MarkdownConfig


class MarkdownToPdfConverter:
    """Markdown转PDF转换器最终版"""
    
    def __init__(self):
        """初始化转换器"""
        self.css_style = self._load_default_css()
        self.md_content = ""
        self.html_content = ""
        self.md_file_path = None
        self.output_dir = None
        self.output_name = None
        
    def convert(self, md_file: str, output_dir: str, output_name: str) -> Tuple[bool, str, str]:
        """
        执行完整的转换流程
        
        Args:
            md_file: Markdown文件路径
            output_dir: 输出目录路径  
            output_name: 输出文件名（不含扩展名）
            
        Returns:
            (成功标志, HTML文件路径, PDF文件路径)
        """
        try:
            # 参数验证
            md_path = Path(md_file)
            if not md_path.exists():
                logger.error(f"Markdown文件不存在: {md_file}")
                return False, "", ""
                
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            
            # 设置实例变量
            self.md_file_path = md_path
            self.output_dir = out_path
            self.output_name = output_name
            
            # 读取Markdown内容
            logger.info(f"读取Markdown文件: {md_file}")
            with open(md_path, 'r', encoding='utf-8') as f:
                self.md_content = f.read()
            
            # 转换为HTML（需要markdown包）
            if _markdown is None:
                logger.error("缺少依赖包: markdown。请安装后重试: pip install markdown")
                return False, "", ""
            logger.info("开始转换Markdown到HTML")
            self.html_content = self._convert_md_to_html()
            
            # 保存HTML文件
            html_file = out_path / f"{output_name}.html"
            logger.info(f"保存HTML文件: {html_file}")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(self.html_content)
            
            # 转换为PDF
            pdf_file = out_path / f"{output_name}.pdf"
            logger.info(f"生成PDF文件: {pdf_file}")
            success = self._convert_html_to_pdf(str(html_file), str(pdf_file))
            
            if success:
                logger.success(f"转换完成 - HTML: {html_file}, PDF: {pdf_file}")
                return True, str(html_file), str(pdf_file)
            else:
                logger.error("PDF生成失败")
                return False, str(html_file), ""
                
        except Exception as e:
            logger.error(f"转换过程出错: {e}")
            return False, "", ""

    def generate_editable_html(self, md_file: str, output_dir: str, output_name: str) -> Tuple[bool, str]:
        """生成可编辑版HTML文件

        Args:
            md_file: Markdown文件路径
            output_dir: 输出目录
            output_name: 输出文件名（不含扩展名）

        Returns:
            (成功标志, 可编辑HTML路径)
        """
        try:
            md_path = Path(md_file)
            if not md_path.exists():
                logger.error(f"Markdown文件不存在: {md_file}")
                return False, ""

            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            # 读取Markdown并转基础HTML
            self.md_file_path = md_path
            self.output_dir = out_path
            self.output_name = output_name

            with open(md_path, 'r', encoding='utf-8') as f:
                self.md_content = f.read()

            if _markdown is None:
                logger.error("缺少依赖包: markdown。请安装后重试: pip install markdown")
                return False, ""
            base_html = self._convert_md_to_html()

            # 注入可编辑控件、工具条、打印样式
            editable_html = self._make_html_editable(base_html)

            # 写入可编辑HTML
            editable_name = f"{output_name}{MarkdownConfig.EDITABLE_HTML_SUFFIX}"
            editable_file = out_path / editable_name
            with open(editable_file, 'w', encoding='utf-8') as f:
                f.write(editable_html)

            logger.info(f"可编辑HTML文件已生成: {editable_file}")
            return True, str(editable_file)
        except Exception as e:
            logger.error(f"生成可编辑HTML失败: {e}")
            return False, ""

    def html_to_pdf(self, html_file: str, output_dir: str, output_name: str) -> Tuple[bool, str]:
        """将现有HTML转换为PDF（用于htmltopdf子命令）

        注意：HTML自身应包含打印样式（隐藏编辑UI、保留版式）。

        Returns:
            (成功标志, PDF路径)
        """
        try:
            html_path = Path(html_file)
            if not html_path.exists():
                logger.error(f"HTML文件不存在: {html_file}")
                return False, ""

            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            pdf_file = out_path / f"{output_name}.pdf"

            # 自动查找与HTML同目录的建议JSON（<base>.suggestions.json 或 <base>.editable.suggestions.json）
            suggestions = None
            base = html_path.name
            base_no_ext = base[:-len(html_path.suffix)] if html_path.suffix else base
            # 规范化基名：去除 .editable；保留 .final（如已为最终版）
            if base_no_ext.endswith('.editable'):
                base_core = base_no_ext[:-len('.editable')]
            else:
                base_core = base_no_ext

            # 读取建议JSON：优先 <core>.suggestions.json；若输入是final且未找到，回退到去掉.final的建议文件
            sug_candidates = [f"{base_core}{MarkdownConfig.SUGGESTIONS_JSON_SUFFIX}"]
            if base_core.endswith('.final'):
                sug_candidates.append(f"{base_core[:-len('.final')]}{MarkdownConfig.SUGGESTIONS_JSON_SUFFIX}")
            for sug_name in sug_candidates:
                sug_path = html_path.parent / sug_name
                if sug_path.exists():
                    try:
                        import json as _json
                        with open(sug_path, 'r', encoding='utf-8') as sf:
                            suggestions = _json.load(sf)
                        logger.info(f"检测到建议JSON，已加载: {sug_path}")
                    except Exception as e:
                        logger.warning(f"加载建议JSON失败，将忽略: {sug_path}，错误: {e}")
                    break

            # 在相同目录输出final HTML（若输入已是final，避免生成 .final.final.html）
            if base_core.endswith('.final'):
                final_html_path = None  # 已是最终版，跳过另存final HTML
            else:
                final_html_name = f"{base_core}.final.html"
                final_html_path = str(html_path.parent / final_html_name)

            ok = self._convert_html_to_pdf(str(html_path), str(pdf_file), suggestions=suggestions, final_html_path=final_html_path)
            if ok:
                logger.success(f"PDF生成成功: {pdf_file}")
                return True, str(pdf_file)
            return False, ""
        except Exception as e:
            logger.error(f"HTML转PDF失败: {e}")
            return False, ""
    
    def _load_default_css(self) -> str:
        """加载默认CSS样式（基于test_document_style.html）"""
        return """
        /* A4纸张规范样式 - 适合打印和PDF转换 */
        @page {
            size: A4;
            margin: 2.5cm 2cm 2.5cm 2cm;
        }
        
        body {
            font-family: "Times New Roman", "SimSun", "宋体", serif;
            font-size: 12pt;
            line-height: 1.5;
            color: #000;
            background: white;
            max-width: 210mm; /* A4宽度 */
            margin: 0 auto;
            padding: 20px;
        }
        
        /* 平滑滚动用于目录跳转 */
        html { scroll-behavior: smooth; }
        
        /* 封面页 - 正式文档风格（home page） */
        .cover-page {
            page-break-after: always;
            text-align: center;
            padding: 60px 40px;
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: calc(100vh - 120px);
        }

        /* 顶部/底部装饰线 */
        .cover-page::before,
        .cover-page::after {
            content: "";
            position: absolute;
            left: 10%;
            right: 10%;
            height: 2px;
            background: #000;
        }
        .cover-page::before { top: 30px; }
        .cover-page::after { bottom: 30px; }
        
        .cover-page h1 {
            font-size: 26pt;
            font-weight: bold;
            margin: 80px 0 30px 0;
            color: #000;
            border: none;
            letter-spacing: 2pt;
            text-transform: uppercase;
        }
        
        .cover-page h2 {
            font-size: 20pt;
            font-weight: normal;
            margin-bottom: 50px;
            color: #000;
            border: none;
            position: relative;
            padding: 20px 0;
        }
        .cover-page h2::before,
        .cover-page h2::after {
            content: "";
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            height: 1px;
            background: #666;
            width: 200px;
        }
        .cover-page h2::before { top: 0; }
        .cover-page h2::after { bottom: 0; }
        
        .cover-page img {
            max-width: 220px;
            margin: 30px auto;
            display: block;
            opacity: 0.9;
        }
        
        .cover-info {
            margin-top: auto;
            margin-bottom: 60px;
            display: inline-block;
            text-align: left;
        }
        
        /* 封面信息表格采用三线表风格（覆盖全局表格样式） */
        .cover-page table {
            border-collapse: collapse;
            margin: 0 auto;
            border: none;
            min-width: 450px;
            width: auto;
        }
        .cover-page thead { border-top: 2px solid #000; border-bottom: 1px solid #000; }
        .cover-page tbody { border-bottom: 2px solid #000; }
        .cover-page th {
            padding: 12px 24px;
            font-size: 12pt;
            font-weight: bold;
            text-align: center;
            background: none;
            border: none;
        }
        .cover-page td {
            padding: 10px 24px;
            font-size: 11pt;
            text-align: left;
            border: none;
            border-bottom: 0.5pt solid #eee;
        }
        .cover-page tbody tr:last-child td { border-bottom: none; }
        .cover-page td:first-child {
            text-align: right;
            font-weight: bold;
            background: none;
            width: 45%;
            padding-right: 30px;
        }
        .cover-page td:last-child { padding-left: 30px; }
        
        /* 目录页 - 正式文档风格 */
        .toc-page {
            page-break-after: always;
            padding: 40px;
            min-height: auto;
            background: white;
        }
        
        .toc-page h1 {
            font-size: 18pt;
            text-align: center;
            margin-bottom: 40px;
            font-weight: bold;
            border: none;
            color: #000;
            letter-spacing: 0.5pt;
        }
        
        .toc-content {
            font-family: "Times New Roman", "SimSun", "宋体", serif;
            font-size: 11pt;
            line-height: 2.5;
            padding: 0;
            margin: 0;
        }

        /* 目录卡片样式 - 正式排版 */
        .toc-card { background: white; border: none; padding: 20px 0; margin: 0 auto; max-width: 100%; }
        .toc-card h1 { margin: 0 0 30px; font-size: 18pt; text-align: center; border: none; padding: 0; position: relative; }
        .toc-card h1:before, .toc-card h1:after { content: ""; position: absolute; top: 50%; width: 80px; height: 1px; background: #000; }
        .toc-card h1:before { left: 50%; margin-left: -140px; }
        .toc-card h1:after { right: 50%; margin-right: -140px; }
        .toc-list { margin: 0; padding: 0; border-top: 2px solid #000; border-bottom: 2px solid #000; padding: 20px 0; }
        .toc-link { display: flex; align-items: baseline; padding: 3px 0; margin: 0; color: #000; text-decoration: none; transition: none; position: relative; }
        .toc-link:hover { background: transparent; text-decoration: underline; }
        .toc-link::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0.3em; border-bottom: 1px dotted #999; z-index: -1; }
        .toc-number { background: white; padding-right: 8px; min-width: 3em; text-align: left; color: #000; font-weight: normal; z-index: 1; }
        .toc-title { background: white; padding: 0 8px; color: #000; z-index: 1; }
        .toc-link::before { content: attr(data-page); position: absolute; right: 0; background: white; padding-left: 8px; z-index: 1; font-style: italic; color: #666; }
        .toc-link.level-1 { font-weight: bold; font-size: 12pt; margin-top: 8px; margin-bottom: 4px; padding: 5px 0; }
        .toc-link.level-1:first-child { margin-top: 0; }
        .toc-link.level-1 .toc-number { font-weight: bold; }
        .toc-link.level-1 .toc-title { font-weight: bold; text-transform: uppercase; letter-spacing: 0.5pt; }
        .toc-link.level-1:not(:first-child) { border-top: 1px solid #ddd; padding-top: 12px; margin-top: 12px; }
        .toc-link.level-2 { padding-left: 2em; font-size: 11pt; color: #333; }
        .toc-link.level-2 .toc-number { padding-left: 2em; }
        .toc-link.level-3 { padding-left: 4em; font-size: 10pt; color: #666; }
        .toc-link.level-3 .toc-number { padding-left: 4em; }
        @media print { .toc-link:hover { text-decoration: none; } }
        
        /* 标题样式 - 简洁正式 */
        h1, h2, h3, h4, h5, h6 {
            font-weight: bold;
            margin-top: 24pt;
            margin-bottom: 12pt;
            page-break-after: avoid;
            color: #000;
        }
        
        h1 {
            font-size: 16pt;
            border-bottom: 2px solid #000;
            padding-bottom: 6pt;
        }

        /* 默认不强制章节换页，保持版面紧凑；如需章节换页，可后续再启用 */
        .content h1[id^="sec-"] {
            page-break-before: auto;
            break-before: auto;
        }
        
        /* 第一个标题不分页 */
        .content h1:first-of-type {
            page-break-before: auto;
        }
        
        h2 {
            font-size: 14pt;
            border-bottom: 1px solid #666;
            padding-bottom: 4pt;
        }
        
        h3 {
            font-size: 13pt;
        }
        
        h4 {
            font-size: 12pt;
        }
        
        /* 段落样式 */
        p {
            margin: 0 0 12pt 0;
            text-align: justify;
            text-indent: 2em; /* 首行缩进 */
        }
        
        /* 表格样式 - 标准三线表 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 12pt 0;
            font-size: 10.5pt;
            page-break-inside: auto;
        }
        
        thead {
            border-top: 1.5pt solid #000;
            border-bottom: 1pt solid #000;
        }
        
        th {
            padding: 6pt 8pt;
            text-align: left;
            font-weight: bold;
            background: #f5f5f5;
        }
        
        tbody {
            border-bottom: 1.5pt solid #000;
        }
        
        td {
            padding: 6pt 8pt;
            border-bottom: 0.5pt solid #ddd;
        }
        
        tbody tr:last-child td {
            border-bottom: none;
        }
        
        tbody tr:nth-child(even) {
            background-color: #fafafa;
        }
        
        /* 列表样式 */
        ul, ol {
            margin: 12pt 0;
            padding-left: 2em;
        }
        
        li {
            margin: 4pt 0;
        }
        
        /* 代码块样式 */
        pre {
            background: #f5f5f5;
            border: 1px solid #ddd;
            padding: 12pt;
            margin: 12pt 0;
            font-family: "Courier New", monospace;
            font-size: 10pt;
            overflow-x: auto;
            /* 允许在长代码块中分页，避免与章节强制换页叠加出现整页空白 */
            page-break-inside: auto;
            break-inside: auto;
        }
        
        code {
            background: #f5f5f5;
            padding: 2pt 4pt;
            font-family: "Courier New", monospace;
            font-size: 10pt;
        }
        
        pre code {
            background: none;
            padding: 0;
        }
        
        /* 高亮代码块样式（四边统一边框，更协调；兼容 div.highlight > pre 与 pre.highlight 两种结构） */
        pre.highlight, .highlight pre {
            background: #fafafa;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 10pt 12pt;
            margin: 12pt 0;
            overflow-x: auto;
            white-space: pre;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            /* 同理，允许分页以减少空白 */
            page-break-inside: auto;
            break-inside: auto;
        }

        pre.highlight code, .highlight pre code {
            background: transparent;
            padding: 0;
            font-family: "Courier New", monospace;
            font-size: 10pt;
            color: #111;
            line-height: 1.5;
        }
        
        /* 图片样式 */
        img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 12pt auto;
            page-break-inside: avoid;
        }
        
        /* 引用块样式 */
        blockquote {
            margin: 12pt 0;
            padding-left: 12pt;
            border-left: 3pt solid #666;
            font-style: italic;
            color: #333;
        }
        
        /* 强调文本 */
        strong {
            font-weight: bold;
        }
        
        em {
            font-style: italic;
        }
        
        /* 水平线 */
        hr {
            border: none;
            border-top: 1px solid #999;
            margin: 20pt 0;
        }
        
        /* 分页控制 */
        .page-break {
            page-break-after: always;
        }
        
        .keep-together {
            page-break-inside: avoid;
        }
        
        /* 打印时的特殊处理 */
        @media print {
            body {
                margin: 0;
                padding: 0;
            }
            
            table {
                page-break-inside: auto;
            }
            
            tr {
                page-break-inside: avoid;
                page-break-after: auto;
            }
            
            h1, h2, h3, h4 {
                page-break-after: avoid;
            }
            
            p {
                orphans: 3;
                widows: 3;
            }
        }
        """
    
    def _convert_md_to_html(self) -> str:
        """将Markdown转换为HTML"""
        if _markdown is None:
            raise ImportError("缺少markdown包，无法将Markdown转换为HTML")
        # 分割文档为三个部分：封面、目录、正文
        cover_html = self._process_cover_section()
        toc_html = self._process_toc_section()
        content_html = self._process_content_section()
        
        # 提取标题
        title = self._extract_title()
        
        # 生成完整HTML
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        {self.css_style}
    </style>
</head>
<body>
{cover_html}
{toc_html}
{content_html}
</body>
</html>"""
        
        return html

    def _make_html_editable(self, html: str) -> str:
        """对HTML注入可编辑控件：建议表格、综合结论、工具条与打印样式"""
        try:
            # 注入工具条与样式（插入到</head>前与<body>开始处）
            style_block = self._editor_style_block()
            script_block = self._editor_script_block()

            # 注入报告元数据（用于文件命名）
            meta_base = f'<meta name="x-report-base" content="{self.output_name}">'

            if '</head>' in html:
                html = html.replace('</head>', f"{meta_base}\n{style_block}\n{script_block}\n</head>")
            else:
                html = f"<head>{meta_base}{style_block}{script_block}</head>\n{html}"

            if '<body>' in html:
                html = html.replace('<body>', '<body>\n' + self._editor_toolbar_block())
            else:
                html = '<body>' + self._editor_toolbar_block() + html

            # 标记 1.2 建议表格（找到1.2标题后的第一张表）
            html = self._mark_advice_table_editable(html)

            # 标记 综合结论 占位（按章节锚点依次处理）
            html = self._mark_conclusions_editable(html)
            # 捕获页面上其余“综合结论：[…]”占位并统一为空的可编辑区域
            html = self._mark_all_conclusion_placeholders(html)
            # 规范结论区结构，避免 <p> 内嵌 <div>
            html = self._normalize_conclusion_blocks(html)
            # 标记“服务器类型二选一”单元格可编辑（下拉选择）
            html = self._mark_server_type_editable(html)

            # 3.1 系统硬件配置表：保持默认样式（RAC不再做特殊列宽处理）

            return html
        except Exception as e:
            logger.error(f"注入可编辑控件失败: {e}")
            return html

    def _mark_advice_table_editable(self, html: str) -> str:
        """将1.2节后的第一张表格设为可编辑，并添加行管理按钮"""
        try:
            # 寻找1.2节标题
            h2_pattern = re.compile(r"<h2[^>]*>\s*1\.2\.[\s\S]*?</h2>")
            m = h2_pattern.search(html)
            if not m:
                return html
            start = m.end()

            # 找到其后的第一个<table>
            table_start = html.find('<table', start)
            if table_start == -1:
                return html
            table_end = html.find('</table>', table_start)
            if table_end == -1:
                return html
            table_end += len('</table>')

            table_html = html[table_start:table_end]

            # 给<table>打标记 data-suggest-id，避免重复添加
            if 'data-suggest-id="advice_table"' not in table_html:
                table_html = re.sub(r'<table', '<table data-suggest-id="advice_table"', table_html, count=1)

            # 为所有<td>增加contenteditable
            def add_editable_td(match):
                td_tag = match.group(0)
                if 'contenteditable' in td_tag:
                    return td_tag
                return td_tag.replace('<td', '<td contenteditable="true"')

            table_html = re.sub(r'<td(?![^>]*contenteditable)[^>]*>', add_editable_td, table_html)

            # 在表格后添加行编辑按钮（编辑阶段显示，打印隐藏）
            controls = (
                '<div class="edit-controls" data-target="advice_table" aria-hidden="false">'
                '<button type="button" onclick="window.__editor.addRow(\'advice_table\')">新增一行</button>'
                '<button type="button" onclick="window.__editor.removeLastRow(\'advice_table\')">删除末行</button>'
                '</div>'
            )

            html = html[:table_start] + table_html + controls + html[table_end:]
            return html
        except Exception as e:
            logger.error(f"标记1.2建议表格失败: {e}")
            return html

    def _mark_conclusions_editable(self, html: str) -> str:
        """将指定章节内的"综合结论：【…】"替换为可编辑表格"""
        anchors = MarkdownConfig.HTML_SECTION_ANCHORS
        for key, anchor in anchors.items():
            if key == 'advice_table':
                continue
            try:
                # 找到章节<h2>（例如 5.2. …）
                h2_pattern = re.compile(rf"<h2[^>]*>\s*{re.escape(anchor)}[\s\S]*?</h2>")
                m = h2_pattern.search(html)
                if not m:
                    continue
                sec_start = m.end()
                # 章节结束位置（下一个<h2>或文档结束）
                next_h2 = html.find('<h2', sec_start)
                sec_end = next_h2 if next_h2 != -1 else len(html)
                segment = html[sec_start:sec_end]

                # 查找"综合结论：【…】"
                concl_re = re.compile(MarkdownConfig.CONCLUSION_PLACEHOLDER_PATTERN)
                if not concl_re.search(segment):
                    continue

                def _repl(match):
                    # 使用表格形式替换
                    table_id = f"conclusion_table_{key}"
                    return (
                        f'<p><strong>综合结论：</strong></p>\n'
                        f'<table data-suggest-id="{table_id}" class="conclusion-table">\n'
                        f'<thead>\n'
                        f'<tr><th style="width: 60px;">序号</th><th>结论内容</th></tr>\n'
                        f'</thead>\n'
                        f'<tbody>\n'
                        f'<tr><td>1</td><td contenteditable="true"></td></tr>\n'
                        f'</tbody>\n'
                        f'</table>\n'
                        f'<div class="edit-controls" data-target="{table_id}" aria-hidden="false">\n'
                        f'<button type="button" onclick="window.__editor.addConclusionRow(\'{table_id}\')">新增结论</button>\n'
                        f'<button type="button" onclick="window.__editor.removeConclusionRow(\'{table_id}\')">删除末行</button>\n'
                        f'</div>'
                    )

                new_segment = concl_re.sub(_repl, segment, count=1)
                html = html[:sec_start] + new_segment + html[sec_end:]
            except Exception as e:
                logger.error(f"标记章节{key}结论失败: {e}")
                continue
        return html

    def _mark_all_conclusion_placeholders(self, html: str) -> str:
        """将页面上所有剩余的"综合结论：【…】"替换为可编辑表格，自动编号ID。"""
        try:
            pattern = re.compile(MarkdownConfig.CONCLUSION_PLACEHOLDER_PATTERN)
            auto_idx = 1

            def repl(m: re.Match) -> str:
                nonlocal auto_idx
                table_id = f"conclusion_table_auto_{auto_idx}"
                replacement = (
                    f'<p><strong>综合结论：</strong></p>\n'
                    f'<table data-suggest-id="{table_id}" class="conclusion-table">\n'
                    f'<thead>\n'
                    f'<tr><th style="width: 60px;">序号</th><th>结论内容</th></tr>\n'
                    f'</thead>\n'
                    f'<tbody>\n'
                    f'<tr><td>1</td><td contenteditable="true"></td></tr>\n'
                    f'</tbody>\n'
                    f'</table>\n'
                    f'<div class="edit-controls" data-target="{table_id}" aria-hidden="false">\n'
                    f'<button type="button" onclick="window.__editor.addConclusionRow(\'{table_id}\')">新增结论</button>\n'
                    f'<button type="button" onclick="window.__editor.removeConclusionRow(\'{table_id}\')">删除末行</button>\n'
                    f'</div>'
                )
                auto_idx += 1
                return replacement

            # 为避免替换已经处理过的段落，这里先跳过包含 contenteditable 的片段
            # 简单做法：全局替换，随后移除重复：若在已含contenteditable的上下文内，不会出现原始占位文本
            return pattern.sub(repl, html)
        except Exception as e:
            logger.warning(f"替换通用结论占位失败: {e}")
            return html

    def _normalize_conclusion_blocks(self, html: str) -> str:
        """修复 <p> 内嵌 <div class="editable-conclusion"> 的结构为分离的块级元素

        转换：
          <p>综合结论：<div class="editable-conclusion" ...></div></p>
        为：
          <p><strong>综合结论：</strong></p><div class="editable-conclusion" ...></div>
        """
        try:
            # 基础情形：<p>综合结论：<div class="editable-conclusion">...</div></p>
            html = re.sub(
                r"<p>\s*综合结论：\s*(<div class=\"editable-conclusion\"[\s\S]*?</div>)\s*</p>",
                r"<p><strong>综合结论：</strong></p>\1",
                html
            )
            # 可选情形：<p><strong>综合结论：</strong><div ...></div></p>
            html = re.sub(
                r"<p>\s*<strong>综合结论：</strong>\s*(<div class=\"editable-conclusion\"[\s\S]*?</div>)\s*</p>",
                r"<p><strong>综合结论：</strong></p>\1",
                html
            )
            # 清理多余的空段落
            html = re.sub(r"<p>\s*</p>", "", html)
            return html
        except Exception as e:
            logger.debug(f"规范结论块结构失败: {e}")
            return html

    def _editor_style_block(self) -> str:
        """返回编辑模式所需样式，打印时隐藏编辑UI"""
        return """
<style>
/* 编辑标识与工具条样式 */
[contenteditable="true"] { outline: 1px dashed #999; padding: 2px; font-size: 12pt; line-height: inherit; }

/* 结论编辑区域特殊样式 */
.editable-conclusion {
    display: block;
    width: 100%;
    min-height: 1.2em;
    margin-top: 0.3em;
    padding: 6px 10px;
    border: 1px dashed #4a90e2;
    border-radius: 4px;
    background: #f0f8ff;
    font-size: 12pt;
    line-height: 1.4;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
    box-sizing: border-box;
}

.editable-conclusion:empty:before {
    content: attr(placeholder);
    color: #9aa0a6;
    font-style: italic;
}

.editable-conclusion:focus {
    outline: none;
    border-color: #4a90e2;
    background: #ffffff;
    box-shadow: 0 0 4px rgba(74, 144, 226, 0.3);
}

/* 最终态渲染（预览/导出） */
.conclusion-output{
    margin: .3em 0 .8em;
    white-space: pre-wrap; /* 保留空格和换行 */
    border: none; background: transparent; padding: 0;
}
.conclusion-output p{ margin: 0 0 .6em; text-indent: 2em; }
.conclusion-output ul, .conclusion-output ol{ margin: .4em 0 .8em 2em; }

#edit-toolbar { 
    position: sticky; 
    top: 0; 
    background: #fff8dc; 
    border-bottom: 1px solid #ddd; 
    padding: 8px; 
    z-index: 9999; 
    font-size: 12px; 
}
#edit-toolbar button { margin-right: 8px; }

/* 表格编辑样式保持不变 */
table[data-suggest-id="advice_table"] [contenteditable="true"] {
    outline: 1px dashed #999;
    padding: 2px;
}

/* 结论表格样式 */
.conclusion-table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
}

.conclusion-table th {
    background-color: #f0f0f0;
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
    font-weight: bold;
}

.conclusion-table td {
    border: 1px solid #ddd;
    padding: 8px;
    vertical-align: top;
}

.conclusion-table td:first-child {
    text-align: center;
    font-weight: bold;
    background-color: #f9f9f9;
}

.conclusion-table [contenteditable="true"] {
    outline: 1px dashed #999;
    padding: 4px;
    min-height: 60px;
    white-space: pre-wrap;
}

.edit-controls { margin: 6px 0 12px 0; }
.edit-controls button { margin-right: 6px; }

/* 行内选择字段（如服务器类型二选一） */
.field-inline select { font-size: 12pt; padding: 2px 6px; }

/* 预览覆盖层 */
#preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  z-index: 10000;
  display: none;
}
#preview-panel {
  position: absolute;
  left: 5%;
  top: 5%;
  width: 90%;
  height: 90%;
  background: #fff;
  border: 1px solid #ccc;
  box-shadow: 0 6px 18px rgba(0,0,0,0.2);
  overflow: auto;
  border-radius: 6px;
}
#preview-close {
  position: sticky;
  top: 0;
  float: right;
  margin: 8px;
}
#preview-content { padding: 16px 20px; max-width: 210mm; margin: 0 auto; font-size: 12pt; line-height: 1.5; }

/* 打印隐藏编辑UI */
@media print {
  #edit-toolbar, .edit-controls { display: none !important; }
  [contenteditable="true"] { outline: none !important; border: none !important; background: transparent !important; }
  .editable-conclusion { border: none !important; background: transparent !important; padding: 0 !important; }
  #preview-overlay { display: none !important; }
}

/* 编辑态压缩封面与目录留白（仅优化浏览器视图，不影响打印） */
body[data-editing="true"] .cover-page {
  min-height: auto !important;
  justify-content: flex-start !important;
  padding: 16px 20px !important;
}
body[data-editing="true"] .cover-page::before,
body[data-editing="true"] .cover-page::after {
  display: none !important;
}
body[data-editing="true"] .cover-page h1 {
  margin: 12px 0 !important;
}
body[data-editing="true"] .cover-page h2 {
  margin: 6px 0 16px !important;
}
body[data-editing="true"] .cover-info {
  margin-top: 8px !important;
  margin-bottom: 16px !important;
}
body[data-editing="true"] .toc-page {
  padding: 16px !important;
}

/* 保持默认表格列宽，不对3.1章节做特殊样式 */
</style>
        """

    def _editor_toolbar_block(self) -> str:
        """顶部工具条（仅保留导出功能）"""
        return """
<div id="edit-toolbar" role="region" aria-label="编辑工具">
  <strong>编辑模式：</strong>
  <button type="button" onclick="window.__editor.previewFormatted()">预览格式化</button>
  <button type="button" onclick="window.__editor.exportFinalHTML()">导出最终HTML</button>
  <span style="margin-left: 16px; color: #666; font-size: 11px;">
    提示：编辑完成后，请导出最终HTML，然后使用 htmltopdf 命令转换为PDF
  </span>
</div>
        """

    def _editor_script_block(self) -> str:
        """注入编辑脚本：序列化/反序列化与导出纯净HTML（ES5兼容）"""
        suffix = MarkdownConfig.SUGGESTIONS_JSON_SUFFIX
        script = r"""
<script>
(function(){
  function download(filename, text){
    var a = document.createElement('a');
    try {
      var blob = new Blob([text], {type: 'text/plain'});
      var url = (window.URL || window.webkitURL).createObjectURL(blob);
      a.href = url; a.download = filename; a.click();
      (window.URL || window.webkitURL).revokeObjectURL(url);
    } catch(e){
      a.setAttribute('href','data:text/plain;charset=utf-8,' + encodeURIComponent(text));
      a.setAttribute('download', filename); a.click();
    }
  }
  // 通用文本->HTML 格式化（段落/列表/换行），供预览与导出共享
  function _escapeHtml(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function _formatUserTextToHtml(text){
    if(!text) return '';
    // 统一换行与空白
    text = text.replace(/\r\n?/g,'\n').replace(/\t/g,' ');
    // 标点规范（温和）
    text = text.replace(/[，，]/g,'，').replace(/[。．]/g,'。').replace(/[；;]/g,'；').replace(/[：:]/g,'：');
    // 若没有换行且文本较长，按句号/分号断行
    if(text.indexOf('\n')===-1 && text.length>120){ text = text.replace(/([。；])\s*/g,'$1\n'); }

    var lines = text.split('\n');
    var html = [];
    var listMode = null; // 'ul' | 'ol'
    var bulletRe = /^\s*[-*•·]\s+/;
    var numRe    = /^\s*\d+[\.)、]\s+/;
    function flushList(items){ if(!items||!items.length) return; var tag=(listMode==='ol')?'ol':'ul'; html.push('<'+tag+'>'); for(var i=0;i<items.length;i++){ html.push('<li>'+_escapeHtml(items[i])+'</li>'); } html.push('</'+tag+'>'); }
    var items=[];
    for(var i=0;i<lines.length;i++){
      var line = lines[i].replace(/\s+$/,'');
      if(!line){ if(listMode){ flushList(items); items=[]; listMode=null; } continue; }
      if(bulletRe.test(line)){ if(listMode && listMode!=='ul'){ flushList(items); items=[]; } listMode='ul'; items.push(line.replace(bulletRe,'')); continue; }
      if(numRe.test(line)){ if(listMode && listMode!=='ol'){ flushList(items); items=[]; } listMode='ol'; items.push(line.replace(numRe,'')); continue; }
      if(listMode){ flushList(items); items=[]; listMode=null; }
      // 将每一行视为一个段落，保证每次回车都形成独立段落
      // 保留连续空格，使用 &nbsp; 替换普通空格
      var escapedLine = _escapeHtml(line).replace(/ {2,}/g, function(spaces) {
        return spaces.replace(/ /g, '&nbsp;');
      });
      html.push('<p>'+ escapedLine +'</p>');
    }
    if(listMode){ flushList(items); }
    return html.join('');
  }
  // 将编辑态的结论块转为最终态（预览/导出共用）
  function finalizeConclusions(root){
    // 处理旧版结论块（兼容）
    var nodes = root.querySelectorAll('.editable-conclusion');
    for(var i=0;i<nodes.length;i++){
      var el=nodes[i];
      var text = el.innerText || el.textContent || '';
      if(text && text.length>4000){ text = text.substring(0,3997)+'...'; }
      el.innerHTML = text && text.trim()!=='' ? _formatUserTextToHtml(text) : '';
      el.removeAttribute('contenteditable');
      el.removeAttribute('data-suggest-id');
      el.removeAttribute('placeholder');
      el.className = 'conclusion-output';
    }
    // 处理结论表格
    var conclusionTables = root.querySelectorAll('table.conclusion-table');
    for(var t=0;t<conclusionTables.length;t++){
      var ctable = conclusionTables[t];
      // 移除所有 contenteditable 属性
      var editableCells = ctable.querySelectorAll('[contenteditable]');
      for(var c=0;c<editableCells.length;c++){
        editableCells[c].removeAttribute('contenteditable');
      }
      // 移除编辑控制按钮
      var controls = root.querySelector('.edit-controls[data-target="'+ctable.getAttribute('data-suggest-id')+'"]');
      if(controls && controls.parentNode){
        controls.parentNode.removeChild(controls);
      }
    }
  }
  function collectData(){
    var data = {};
    // 收集所有可编辑结论（旧版兼容）
    var conclusions = document.querySelectorAll('.editable-conclusion[data-suggest-id]');
    for(var k=0;k<conclusions.length;k++){
      var el = conclusions[k]; 
      var id = el.getAttribute('data-suggest-id');
      if(id){ data[id] = el.innerText || ''; }
    }
    // 服务器类型选择
    var st = document.querySelector('[data-suggest-id="server_type"] select');
    if(st){ data['server_type'] = st.value || ''; }
    // 收集建议表格数据
    var table = document.querySelector('table[data-suggest-id="advice_table"]');
    if(table){
      var rows = []; var tbody = table.querySelector('tbody') || table;
      var trList = tbody.querySelectorAll('tr');
      for(var r=0;r<trList.length;r++){
        var tr = trList[r];
        if(tr.querySelectorAll('th').length>0) continue;
        var cells = []; var tds = tr.querySelectorAll('td');
        for(var c=0;c<tds.length;c++){ cells.push(tds[c].innerText || ''); }
        if(cells.length) rows.push(cells);
      }
      data['advice_table'] = rows;
    }
    // 收集所有结论表格数据
    var conclusionTables = document.querySelectorAll('table.conclusion-table[data-suggest-id]');
    for(var t=0;t<conclusionTables.length;t++){
      var ctable = conclusionTables[t];
      var tid = ctable.getAttribute('data-suggest-id');
      if(!tid) continue;
      var crows = []; var ctbody = ctable.querySelector('tbody') || ctable;
      var ctrList = ctbody.querySelectorAll('tr');
      for(var cr=0;cr<ctrList.length;cr++){
        var ctr = ctrList[cr];
        var ctds = ctr.querySelectorAll('td');
        if(ctds.length>=2){ crows.push(ctds[1].innerText || ''); }
      }
      data[tid] = crows;
    }
    return data;
  }
  function applyData(data){
    // 应用结论数据（旧版兼容）
    for(var key in data){ 
      if(!data.hasOwnProperty(key)) continue; 
      if(key==='advice_table' || key.indexOf('conclusion_table_')===0) continue;
      var conclusion = document.querySelector('.editable-conclusion[data-suggest-id="'+key+'"]'); 
      if(conclusion){ conclusion.innerText = data[key] || ''; }
    }
    // 应用服务器类型选择
    if(data && data.hasOwnProperty('server_type')){
      var st = document.querySelector('[data-suggest-id="server_type"] select');
      if(st){ st.value = data['server_type'] || ''; }
    }
    // 应用建议表格数据
    if(Object.prototype.toString.call(data['advice_table'])==='[object Array]'){
      var table = document.querySelector('table[data-suggest-id="advice_table"]');
      if(table){ var tbody = table.querySelector('tbody') || table;
        var trs = tbody.querySelectorAll('tr');
        for(var i=trs.length-1;i>=0;i--){ if(trs[i].querySelectorAll('th').length===0){ tbody.removeChild(trs[i]); } }
        var rows = data['advice_table'] || [];
        for(var r=0;r<rows.length;r++){ var tr = document.createElement('tr'); var cols = rows[r];
          for(var c=0;c<cols.length;c++){ var td = document.createElement('td'); td.setAttribute('contenteditable','true'); td.innerText = cols[c]; tr.appendChild(td);}
          tbody.appendChild(tr);
        }
      }
    }
    // 应用结论表格数据
    for(var tkey in data){
      if(!data.hasOwnProperty(tkey) || tkey.indexOf('conclusion_table_')!==0) continue;
      var ctable = document.querySelector('table[data-suggest-id="'+tkey+'"]');
      if(!ctable) continue;
      var ctbody = ctable.querySelector('tbody') || ctable;
      // 清空现有行
      while(ctbody.firstChild){ ctbody.removeChild(ctbody.firstChild); }
      // 添加新行
      var crows = data[tkey] || [];
      for(var cr=0;cr<crows.length;cr++){
        var ctr = document.createElement('tr');
        var ctd1 = document.createElement('td');
        ctd1.textContent = (cr+1);
        ctr.appendChild(ctd1);
        var ctd2 = document.createElement('td');
        ctd2.setAttribute('contenteditable','true');
        ctd2.innerText = crows[cr] || '';
        ctr.appendChild(ctd2);
        ctbody.appendChild(ctr);
      }
    }
  }
  function saveJSON(){ var data = collectData(); var meta=document.querySelector('meta[name="x-report-base"]'); var base=(meta&&meta.content)||'report'; var name = base + '__SUG_SUFFIX__'; download(name, JSON.stringify(data,null,2)); }
  function loadJSON(){ var input=document.createElement('input'); input.type='file'; input.accept='application/json';
    input.onchange=function(e){ var file=e.target.files[0]; if(!file) return; var reader=new FileReader();
      reader.onload=function(){ try{ var data=JSON.parse(reader.result); applyData(data); }catch(err){ alert('JSON 解析失败: '+err); } }; reader.readAsText(file,'utf-8'); };
    input.click(); }
  function exportFinalHTML(){ 
    var meta=document.querySelector('meta[name="x-report-base"]'); 
    var base=(meta&&meta.content)||'report'; 
    // 在克隆前捕获服务器类型选择，写入data-selected-value，确保clone后可读取
    (function(){
      var wraps = document.querySelectorAll('[data-suggest-id="server_type"]');
      for(var i=0;i<wraps.length;i++){
        var sel = wraps[i].querySelector('select');
        if(sel){ var v = sel.value || ((sel.options[sel.selectedIndex]||{}).text)||''; wraps[i].setAttribute('data-selected-value', v); }
      }
    })();
    var doc=document.cloneNode(true);
    // 统一将结论区从编辑态转为最终态
    finalizeConclusions(doc);
    // 将“服务器类型二选一”转为纯文本
    (function(){
      var wraps = doc.querySelectorAll('[data-suggest-id="server_type"]');
      for(var i=0;i<wraps.length;i++){
        var wrap = wraps[i];
        var val = wrap.getAttribute('data-selected-value') || '';
        if(!val){ var sel = wrap.querySelector('select'); if(sel){ val = ((sel.options[sel.selectedIndex]||{}).text)|| sel.value || ''; } }
        var td = wrap.closest('td') || wrap;
        td.innerHTML = val || '';
      }
    })();
    var rm = doc.querySelectorAll('#edit-toolbar, .edit-controls'); for(var i=0;i<rm.length;i++){ rm[i].parentNode.removeChild(rm[i]); }
    var ed1 = doc.querySelectorAll('[contenteditable]'); for(var j=0;j< ed1.length;j++){ ed1[j].removeAttribute('contenteditable'); }
    var ed2 = doc.querySelectorAll('[data-suggest-id]'); for(var k=0;k< ed2.length;k++){ ed2[k].removeAttribute('data-suggest-id'); }
    // 清理编辑相关类
    var cls = doc.querySelectorAll('.editable-conclusion, .editable-output, .field-inline, .field-input');
    for(var m=0;m<cls.length;m++){ if(cls[m].classList.contains('editable-conclusion')){ cls[m].className='conclusion-output'; } else { cls[m].removeAttribute('class'); } }
    // 移除编辑标记
    if(doc.body){ doc.body.removeAttribute('data-editing'); }
    var html='<!DOCTYPE html>\n' + doc.documentElement.outerHTML; download(base + '.final.html', html); }
  function ensurePreviewOverlay(){
    var ov = document.getElementById('preview-overlay');
    if(!ov){
      ov = document.createElement('div');
      ov.id = 'preview-overlay';
      ov.innerHTML = '<div id="preview-panel">\n' +
                     '  <button id="preview-close" type="button">关闭预览</button>\n' +
                     '  <div id="preview-content"></div>\n' +
                     '</div>';
      document.body.appendChild(ov);
      ov.querySelector('#preview-close').onclick = function(){ ov.style.display='none'; };
      ov.addEventListener('click', function(e){ if(e.target===ov){ ov.style.display='none'; } });
    }
    return ov;
  }
  function previewFormatted(){
    // 克隆并格式化内容
    // 预先捕获服务器类型选择值到data-selected-value，确保clone后可读取
    (function(){
      var wraps = document.querySelectorAll('[data-suggest-id="server_type"]');
      for(var i=0;i<wraps.length;i++){
        var sel = wraps[i].querySelector('select');
        if(sel){ var v = sel.value || ((sel.options[sel.selectedIndex]||{}).text)||''; wraps[i].setAttribute('data-selected-value', v); }
      }
    })();
    var bodyClone = document.body.cloneNode(true);
    // 移除编辑标记（预览应显示打印样式）
    if(bodyClone){ bodyClone.removeAttribute('data-editing'); }
    // 移除预览自身、工具与编辑控件
    var removeSelectors = ['#preview-overlay', '#edit-toolbar', '.edit-controls'];
    for(var i=0;i<removeSelectors.length;i++){
      var nodes = bodyClone.querySelectorAll(removeSelectors[i]);
      for(var j=0;j<nodes.length;j++){ nodes[j].parentNode.removeChild(nodes[j]); }
    }
    // 统一将结论区从编辑态转为最终态
    finalizeConclusions(bodyClone);
    // 预览中同步将服务器类型选择转为纯文本展示
    (function(){
      var wraps = bodyClone.querySelectorAll('[data-suggest-id="server_type"]');
      for(var i=0;i<wraps.length;i++){
        var wrap = wraps[i];
        var val = wrap.getAttribute('data-selected-value') || '';
        if(!val){ var sel = wrap.querySelector('select'); if(sel){ val=((sel.options[sel.selectedIndex]||{}).text)||sel.value||''; } }
        var td = wrap.closest('td') || wrap;
        td.innerHTML = val || '';
      }
    })();
    var ov = ensurePreviewOverlay();
    var box = ov.querySelector('#preview-content');
    box.innerHTML = bodyClone.innerHTML;
    ov.style.display = 'block';
  }
  function addRow(targetId){ var table=document.querySelector('table[data-suggest-id="'+targetId+'"]'); if(!table) return; var tbody=table.querySelector('tbody')||table;
    var lastRow=tbody.querySelector('tr'); var cols= lastRow? lastRow.querySelectorAll('td').length : 4; var tr=document.createElement('tr');
    for(var i=0;i<cols;i++){ var td=document.createElement('td'); td.setAttribute('contenteditable','true'); tr.appendChild(td);} tbody.appendChild(tr); }
  function removeLastRow(targetId){ var table=document.querySelector('table[data-suggest-id="'+targetId+'"]'); if(!table) return; var tbody=table.querySelector('tbody')||table;
    var rows=[]; var trs=tbody.querySelectorAll('tr'); for(var i=0;i<trs.length;i++){ if(trs[i].querySelectorAll('th').length===0){ rows.push(trs[i]); } } if(rows.length>0){ rows[rows.length-1].parentNode.removeChild(rows[rows.length-1]); } }
  function addConclusionRow(targetId){ 
    var table=document.querySelector('table[data-suggest-id="'+targetId+'"]'); 
    if(!table) return; 
    var tbody=table.querySelector('tbody')||table;
    var rows = tbody.querySelectorAll('tr');
    var nextNum = rows.length + 1;
    var tr=document.createElement('tr');
    var td1=document.createElement('td'); 
    td1.textContent = nextNum; 
    tr.appendChild(td1);
    var td2=document.createElement('td'); 
    td2.setAttribute('contenteditable','true'); 
    tr.appendChild(td2);
    tbody.appendChild(tr); 
  }
  function removeConclusionRow(targetId){ 
    var table=document.querySelector('table[data-suggest-id="'+targetId+'"]'); 
    if(!table) return; 
    var tbody=table.querySelector('tbody')||table;
    var rows=tbody.querySelectorAll('tr'); 
    if(rows.length>1){ 
      rows[rows.length-1].parentNode.removeChild(rows[rows.length-1]); 
    } 
  }
  function autoSave(){ try{ var data=collectData(); localStorage.setItem('report_edits', JSON.stringify(data)); }catch(e){} }
  // 结论输入增强：规范粘贴为纯文本并保留换行、回车插入<br>
  function attachConclusionHandlers(){
    var nodes = document.querySelectorAll('.editable-conclusion');
    for(var i=0;i<nodes.length;i++){
      var el = nodes[i];
      if(el.__handlersInstalled) continue;
      el.__handlersInstalled = true;
      // 规范粘贴：仅保留纯文本与换行
      el.addEventListener('paste', function(e){
        try{
          var cd = (e.clipboardData || window.clipboardData);
          if(!cd) return; 
          var text = cd.getData('text/plain');
          if(typeof text !== 'string') return; 
          e.preventDefault();
          text = text.replace(/\r\n?/g,'\n');
          // 压缩多余空行但保留用户段落
          text = text.replace(/\n{3,}/g,'\n\n');
          // 安全转义并插入<br>
          var html = text.split('\n').map(function(l){
            return l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
          }).join('<br>');
          document.execCommand('insertHTML', false, html);
        }catch(err){}
      });
      // 允许浏览器原生回车换行行为（段落换行）；不做拦截
      el.addEventListener('keydown', function(e){
        // no-op: keep default Enter behavior for better compatibility
      });
    }
  }
  // 结论实时输入不做强制格式化，避免破坏用户的段落与换行
  
  document.addEventListener('input', function(ev){
    var t=ev.target; 
    var ce=(t&&t.getAttribute&&t.getAttribute('contenteditable')==='true');
    var inTable=false; 
    var isConclusion = false;
    
    try{ 
      inTable=!!(t&&t.closest&&t.closest('table[data-suggest-id="advice_table"]')); 
      isConclusion=!!(t&&t.classList&&t.classList.contains('editable-conclusion'));
    }catch(e){}
    
    // 结论输入：不改变用户输入，仅自动保存
    
    if(ce||inTable){ autoSave(); }
  });
  // 页面加载后绑定增强处理并设置编辑标记
  function initEditor(){
    attachConclusionHandlers();
    // 设置编辑标记以启用编辑态样式压缩
    if(document.body){
      document.body.setAttribute('data-editing', 'true');
    }
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', initEditor);
  } else {
    initEditor();
  }
  try{ var cached=localStorage.getItem('report_edits'); if(cached){ applyData(JSON.parse(cached)); } }catch(e){}
  window.__editor = { saveJSON: saveJSON, loadJSON: loadJSON, exportFinalHTML: exportFinalHTML, previewFormatted: previewFormatted, addRow: addRow, removeLastRow: removeLastRow, addConclusionRow: addConclusionRow, removeConclusionRow: removeConclusionRow };
})();
</script>
"""
        return script.replace('__SUG_SUFFIX__', suffix)

    def _mark_server_type_editable(self, html: str) -> str:
        """将特定TD文本“X86数据库服务器 / Oracle ExaData 一体机 (二选一)”替换为下拉选择控件

        生成形如：
        <td><span class="field-inline" data-suggest-id="server_type"><select>...</select></span></td>
        """
        try:
            pattern = re.compile(r'(<td[^>]*>)\s*X86数据库服务器\s*/\s*Oracle ExaData 一体机\s*\(二选一\)\s*(</td>)')
            if not pattern.search(html):
                return html
            replacement = (r'\1'
                            r'<span class="field-inline" data-suggest-id="server_type">'
                            r'<select>'
                            r'<option value="">请选择</option>'
                            r'<option value="X86数据库服务器">X86数据库服务器</option>'
                            r'<option value="Oracle ExaData 一体机">Oracle ExaData 一体机</option>'
                            r'</select>'
                            r'</span>'
                            r'\2')
            return pattern.sub(replacement, html)
        except Exception as e:
            logger.error(f"标记服务器类型可编辑失败: {e}")
            return html
    
    def _extract_title(self) -> str:
        """从MD提取标题"""
        for line in self.md_content.split('\n')[:20]:
            if '# ' in line and ('数据库' in line or '系统' in line):
                return re.sub(r'^#+\s*', '', line).strip()
        return "数据库健康检查报告"
    
    def _process_cover_section(self) -> str:
        """处理封面部分"""
        lines = self.md_content.split('\n')
        cover_end_idx = 0
        
        # 找到封面结束位置 (到"---"分隔线或"# 目录"之前)
        for i, line in enumerate(lines):
            if i > 10 and line.strip() == '---':
                cover_end_idx = i
                break
            if '# 目录' in line:
                cover_end_idx = i
                break
        
        if cover_end_idx == 0:
            cover_end_idx = min(50, len(lines))  # 默认前50行
        
        cover_lines = lines[:cover_end_idx]
        
        # 构建封面HTML - 传统文档风格
        html = ['<div class="cover-page">']
        
        in_table = False
        table_lines = []
        
        for i, line in enumerate(cover_lines):
            # 跳过HTML标签
            if '<div style="text-align: center;">' in line or '</div>' in line:
                continue
            
            # 处理标题
            if line.startswith('# ') and '目录' not in line:
                content = line[2:].strip()
                html.append(f'<h1>{content}</h1>')
            elif line.startswith('## '):
                content = line[3:].strip()
                html.append(f'<h2 style="font-size:22pt;">{content}</h2>')
            # 处理图片
            elif '![' in line:
                match = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', line)
                if match:
                    alt_text = match.group(1)
                    img_path = self._fix_image_path(match.group(2))
                    html.append(f'<img src="{img_path}" alt="{alt_text}" style="max-width:300px; height:auto;">')
            # 处理表格
            elif '|' in line and line.strip():
                if not in_table:
                    in_table = True
                    table_lines = [line]
                else:
                    table_lines.append(line)
                    
                # 检查下一行是否还是表格
                if i + 1 >= len(cover_lines) or (i + 1 < len(cover_lines) and '|' not in cover_lines[i + 1]):
                    # 表格结束，生成HTML
                    if len(table_lines) > 2:  # 至少有标题行和数据行
                        html.append('<div class="cover-info">')
                        html.append(self._parse_markdown_table(table_lines))
                        html.append('</div>')
                    in_table = False
                    table_lines = []
        
        html.append('</div>')  # 关闭 cover-page
        
        return '\n'.join(html)
    
    def _parse_markdown_table(self, lines: List[str]) -> str:
        """解析Markdown表格为HTML"""
        if not lines or len(lines) < 2:
            return ""
        
        html = ['<table>']
        
        # 处理标题行
        header_line = lines[0]
        headers = [cell.strip() for cell in header_line.split('|') if cell.strip()]
        
        if headers:
            html.append('<thead><tr>')
            for header in headers:
                html.append(f'<th>{header}</th>')
            html.append('</tr></thead>')
        
        # 跳过分隔线（第二行）
        if len(lines) > 2:
            html.append('<tbody>')
            
            # 处理数据行
            for line in lines[2:]:
                if '|' not in line or line.strip().startswith('---'):
                    continue
                    
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if cells:
                    html.append('<tr>')
                    for cell in cells:
                        html.append(f'<td>{cell}</td>')
                    html.append('</tr>')
            
            html.append('</tbody>')
        
        html.append('</table>')
        return '\n'.join(html)
    
    def _process_cover_table(self, lines: List[str]) -> str:
        """处理封面表格"""
        table_html = ['<table>']
        in_table = False
        
        for line in lines:
            if '| 项目 |' in line:
                in_table = True
                table_html.append('<thead><tr><th>项目</th><th>信息</th></tr></thead>')
                table_html.append('<tbody>')
            elif in_table and '|---' in line:
                continue  # 跳过分隔线
            elif in_table and '|' in line:
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if len(cells) >= 2:
                    table_html.append(f'<tr><td>{cells[0]}</td><td>{cells[1] if len(cells) > 1 else ""}</td></tr>')
            elif in_table and not line.strip():
                break  # 表格结束
        
        table_html.append('</tbody>')
        table_html.append('</table>')
        
        return '\n'.join(table_html)
    
    def _process_toc_section(self) -> str:
        """处理目录部分 - 传统文档风格带虚线"""
        lines = self.md_content.split('\n')
        toc_lines = []
        in_toc = False
        
        for line in lines:
            if '# 目录' in line:
                in_toc = True
                continue
            elif in_toc and line.strip() == '---':
                break  # 目录结束
            elif in_toc and line.strip().startswith('# ') and '文档控制' not in line:
                break  # 遇到正文开始
            elif in_toc:
                toc_lines.append(line)
        
        if not toc_lines:
            return ""
        
        # 构建目录HTML - 新版卡片式目录
        html = ['<div class="toc-page">']
        html.append('<div class="toc-card">')
        html.append('<h1>目录</h1>')
        html.append('<div class="toc-content">')
        html.append('<div class="toc-list">')
        
        page_num = 1  # 模拟页码
        for line in toc_lines:
            if not line.strip():
                continue
            
            # 转换markdown链接为纯文本
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
            text = text.strip()
            
            if not text:
                continue
            
            # 判断层级
            if text.startswith('-'):
                # 子目录项
                text = text.lstrip('-').strip()
                # 判断是一级还是二级子目录
                if re.match(r'^\d+\.\d+\.', text):  # 如 1.1. 
                    level_class = 'toc-level-2'
                elif re.match(r'^\d+\.\d+\.\d+', text):  # 如 1.1.1
                    level_class = 'toc-level-3'
                else:
                    level_class = 'toc-level-2'
            elif re.match(r'^\d+\.', text):  # 主章节
                level_class = 'toc-level-1'
                page_num += 5  # 主章节间隔页数
            else:
                level_class = 'toc-line'
            
            # 计算锚点id（根据编号前缀生成sec-X或sec-X-Y）
            anchor_id = None
            m = re.match(r'^(\d+)(?:\.(\d+))?', text)
            if m:
                s1 = m.group(1)
                s2 = m.group(2)
                anchor_id = f'sec-{s1}-{s2}' if s2 else f'sec-{s1}'

            # 分离编号与标题文本
            num = ''
            title = text
            m2 = re.match(r'^(\d+(?:\.\d+)*)\.\s*(.*)$', text)
            if m2:
                num = m2.group(1) + '.'
                title = m2.group(2) if m2.group(2) else ''

            # 生成新版目录行（整行可点击）
            level_cls = level_class.replace('toc-level', 'level')
            if anchor_id:
                html.append(
                    f'<a class="toc-link {level_cls}" href="#{anchor_id}" data-page="">' \
                    f'<span class="toc-number">{num}</span>' \
                    f'<span class="toc-title">{title if title else text}</span>' \
                    f'</a>'
                )
            else:
                html.append(
                    f'<div class="toc-link {level_cls}">' \
                    f'<span class="toc-number">{num}</span>' \
                    f'<span class="toc-title">{title if title else text}</span>' \
                    f'</div>'
                )
            page_num += 1
        
        html.append('</div>')  # .toc-list
        html.append('</div>')  # .toc-content
        html.append('</div>')  # .toc-card
        html.append('</div>')  # .toc-page
        
        return '\n'.join(html)
    
    def _process_content_section(self) -> str:
        """处理正文部分"""
        # 找到正文开始位置
        lines = self.md_content.split('\n')
        content_start = 0
        
        # 方法1：查找"文档控制"作为正文开始
        for i, line in enumerate(lines):
            if '# 文档控制' in line:
                content_start = i
                break
        
        # 方法2：如果没找到文档控制，查找第一个带编号的章节
        if content_start == 0:
            for i, line in enumerate(lines):
                if re.match(r'^# \d+\.', line):  # 匹配 "# 1. 健康检查总结" 这样的标题
                    content_start = i
                    break
        
        # 如果还是没找到，查找目录结束后的内容
        if content_start == 0:
            in_toc = False
            for i, line in enumerate(lines):
                if '# 目录' in line:
                    in_toc = True
                elif in_toc and '---' in line:
                    # 跳过分隔线后面的空行
                    for j in range(i+1, min(i+5, len(lines))):
                        if lines[j].strip():
                            content_start = j
                            break
                    break
        
        # 获取正文内容
        content_lines = lines[content_start:]
        
        # 预处理内容：确保列表前后有空行
        processed_lines = []
        for i, line in enumerate(content_lines):
            # 检测需要列表的关键词
            list_triggers = [
                '本次数据库性能检查的工具是',
                '主要从以下方面来检查操作系统的性能',
                '主要从以下方面', 
                '以下的部分是对操作系统的检查'
            ]
            
            # 检查是否包含触发列表的关键词
            if any(trigger in line for trigger in list_triggers):
                processed_lines.append(line)
                processed_lines.append('')  # 添加空行确保列表正确解析
            elif i > 0 and any(trigger in content_lines[i-1] for trigger in list_triggers) and line.strip().startswith('-'):
                # 这是列表的第一项
                processed_lines.append(line)
            elif line.strip().startswith('- ') and i > 0 and content_lines[i-1].strip().startswith('- '):
                # 列表的连续项
                processed_lines.append(line)
            elif i > 0 and content_lines[i-1].strip().startswith('- ') and not line.strip().startswith('- '):
                # 列表结束，添加空行
                processed_lines.append('')
                processed_lines.append(line)
            else:
                processed_lines.append(line)
        
        content = '\n'.join(processed_lines)
        
        # 使用markdown库处理正文
        md = _markdown.Markdown(
            extensions=[
                'tables',
                'fenced_code',
                'codehilite',
                'attr_list'
            ],
            extension_configs={
                'codehilite': {
                    'linenums': False,
                    'css_class': 'highlight'
                }
            }
        )
        
        # 转换正文
        html = md.convert(content)
        
        # 为编号标题注入稳定ID，供目录跳转
        html = self._inject_heading_ids(html)
        
        # 清理列表中的多余<p>标签
        html = self._clean_list_paragraphs(html)
        
        # 修复图片路径
        html = self._fix_all_image_paths(html)
        
        return f'<div class="content">\n{html}\n</div>'

    def _inject_heading_ids(self, html: str) -> str:
        """为正文中以数字编号开头的标题生成稳定的id（sec-X 或 sec-X-Y）。"""
        try:
            import re as _re
            pattern = _re.compile(r'<h([1-6])([^>]*)>(.*?)</h\1>', _re.DOTALL | _re.IGNORECASE)

            def repl(m):
                level = m.group(1)
                attrs = m.group(2)
                inner = m.group(3)
                # 如果已有id则保持
                if _re.search(r'\bid\s*=\s*(["\"])', attrs):
                    return m.group(0)
                # 去除内部HTML标签获取纯文本
                text = _re.sub(r'<[^>]+>', '', inner).strip()
                # 提取编号（支持 "10." 或 "7.1."，点后可无空格）
                mm = _re.match(r'\s*(\d+)(?:\.(\d+))?', text)
                if not mm:
                    return m.group(0)
                s1 = mm.group(1)
                s2 = mm.group(2)
                anchor_id = f'sec-{s1}-{s2}' if s2 else f'sec-{s1}'
                new_attrs = f'{attrs} id="{anchor_id}"'
                return f'<h{level}{new_attrs}>{inner}</h{level}>'

            return pattern.sub(repl, html)
        except Exception as e:
            logger.warning(f"为标题注入ID失败: {e}")
            return html
    
    def _fix_image_path(self, img_path: str) -> str:
        """修复单个图片路径"""
        if img_path.startswith('http'):
            return img_path
        
        if self.md_file_path and self.output_dir:
            # 计算从MD文件位置的绝对路径
            md_dir = self.md_file_path.parent
            img_abs_path = (md_dir / img_path).resolve()
            
            # 计算相对于输出目录的路径
            try:
                img_rel_path = os.path.relpath(img_abs_path, self.output_dir)
                return img_rel_path.replace('\\', '/')
            except ValueError:
                # 如果无法计算相对路径，使用绝对路径
                return str(img_abs_path).replace('\\', '/')
        
        return img_path
    
    def _fix_all_image_paths(self, html: str) -> str:
        """修复所有图片路径"""
        def fix_path(match):
            img_tag = match.group(0)
            src_match = re.search(r'src="([^"]+)"', img_tag)
            
            if src_match:
                img_path = src_match.group(1)
                fixed_path = self._fix_image_path(img_path)
                img_tag = img_tag.replace(src_match.group(0), f'src="{fixed_path}"')
            
            return img_tag
        
        # 查找并替换所有img标签
        html = re.sub(r'<img[^>]+>', fix_path, html)
        
        return html

    def _mark_system_hardware_table_styled(self, html: str) -> str:
        """将 3.1. 系统硬件配置后的第一张表格标记为 sys-hw-table 以应用列宽样式。"""
        try:
            h2_pattern = re.compile(r"<h2[^>]*>\s*3\.1\.[\s\S]*?</h2>")
            m = h2_pattern.search(html)
            if not m:
                return html
            start = m.end()
            t_start = html.find('<table', start)
            if t_start == -1:
                return html
            t_end = html.find('>', t_start)
            if t_end == -1:
                return html
            table_tag = html[t_start:t_end+1]
            if 'class=' in table_tag:
                new_tag = re.sub(r'class="([^"]*)"', lambda mt: f'class="'+mt.group(1)+' sys-hw-table"', table_tag, count=1)
            else:
                new_tag = table_tag.replace('<table', '<table class="sys-hw-table"', 1)
            return html[:t_start] + new_tag + html[t_end+1:]
        except Exception as e:
            logger.warning(f"标记3.1系统硬件配置表样式失败: {e}")
            return html
    
    def _clean_list_paragraphs(self, html: str) -> str:
        """清理列表项中的多余<p>标签，特别是AWR报告部分"""
        # 移除<li>内部的<p>标签，保留内容
        # 匹配模式：<li>\n<p>内容</p>\n</li>
        html = re.sub(r'<li>\s*<p>(.*?)</p>\s*</li>', r'<li>\1</li>', html, flags=re.DOTALL)
        
        # 处理嵌套的情况：<li>后紧跟<p>
        html = re.sub(r'<li>\s*\n*\s*<p>', r'<li>', html)
        html = re.sub(r'</p>\s*\n*\s*</li>', r'</li>', html)
        
        return html
    
    def _convert_html_to_pdf(self, html_file: str, pdf_file: str, suggestions: dict | None = None, final_html_path: str | None = None) -> bool:
        """使用Playwright将HTML转换为PDF，并可选注入建议JSON与输出final HTML

        Args:
            html_file: 输入HTML路径
            pdf_file: 输出PDF路径
            suggestions: 可选，建议内容字典。若提供，将注入DOM。
            final_html_path: 可选，若提供，将输出净化后的final HTML至该路径。
        """
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # 加载HTML文件
                page.goto(f'file://{os.path.abspath(html_file)}')
                
                # 等待页面加载完成
                page.wait_for_load_state('networkidle')

                # 注入分页修正样式，覆盖旧版final HTML中的强制分页规则，减少空白页
                try:
                    page.add_style_tag(content='''
                        /* 覆盖旧版强制分页，按需自然分页以避免空白页 */
                        h1 { page-break-before: auto !important; break-before: auto !important; }
                        .content h1[id^="sec-"] { page-break-before: auto !important; break-before: auto !important; }
                        h1, h2, h3, h4 { page-break-after: auto !important; }
                        pre, pre.highlight, .highlight pre { page-break-inside: auto !important; break-inside: auto !important; }
                        table, tr, img { page-break-inside: auto !important; break-inside: auto !important; }
                    ''')
                except Exception:
                    pass

                # 注入建议数据（如有）
                if suggestions:
                    page.evaluate(
                        """
                        (data) => {
                          // 应用通用可编辑元素
                          Object.keys(data||{}).forEach(function(key){
                            if(key==='advice_table') return;
                            var el=document.querySelector('.editable-conclusion[data-suggest-id="'+key+'"]');
                            if(el){ el.innerText = (data[key]||''); }
                          });
                          // 应用建议表格
                          var rows = data && data['advice_table'];
                          if(Object.prototype.toString.call(rows)==='[object Array]'){
                            var table=document.querySelector('table[data-suggest-id="advice_table"]');
                            if(table){
                              var tbody=table.querySelector('tbody')||table;
                              var trs = tbody.querySelectorAll('tr');
                              for(var i=trs.length-1;i>=0;i--){ if(trs[i].querySelectorAll('th').length===0){ tbody.removeChild(trs[i]); } }
                              for(var r=0;r<rows.length;r++){
                                var tr=document.createElement('tr'); var cols=rows[r]||[];
                                for(var c=0;c<cols.length;c++){
                                  var td=document.createElement('td'); td.setAttribute('contenteditable','true'); td.innerText = cols[c]; tr.appendChild(td);
                                }
                                tbody.appendChild(tr);
                              }
                            }
                          }
                        }
                        """,
                        suggestions
                    )

                # 格式化结论文本，确保适合PDF显示（保留换行并支持列表）
                page.evaluate(
                    r"""
                    () => {
                      function _escapeHtml(s){
                        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                      }
                      function _formatUserTextToHtml(text){
                        if(!text) return '';
                        text = text.replace(/\r\n?/g,'\n').replace(/\t/g,' ');
                        text = text.replace(/[，，]/g,'，').replace(/[。．]/g,'。').replace(/[；;]/g,'；').replace(/[：:]/g,'：');
                        if(text.indexOf('\n')===-1 && text.length>120){ text = text.replace(new RegExp('([。；])\\s*','g'),'$1\n'); }
                        var lines = text.split('\n');
                        var html = [];
                        var listMode = null; var items=[];
                        var bulletRe = new RegExp('^\\s*[-*•·]\\s+');
                        var numRe = new RegExp('^\\s*\\d+[\\.)、]\\s+');
                        function flushList(){ if(!items.length) return; var tag=(listMode==='ol')?'ol':'ul'; html.push('<'+tag+'>'); for(var i=0;i<items.length;i++){ html.push('<li>'+_escapeHtml(items[i])+'</li>'); } html.push('</'+tag+'>'); items=[]; listMode=null; }
                        for(var i=0;i<lines.length;i++){
                          var line=lines[i].replace(/\s+$/,'');
                          if(!line){ if(listMode){ flushList(); } continue; }
                          if(bulletRe.test(line)){ if(listMode && listMode!=='ul'){ flushList(); } listMode='ul'; items.push(line.replace(bulletRe,'')); continue; }
                          if(numRe.test(line)){ if(listMode && listMode!=='ol'){ flushList(); } listMode='ol'; items.push(line.replace(numRe,'')); continue; }
                          if(listMode){ flushList(); }
                          // 保留连续空格，使用 &nbsp; 替换普通空格
                          var escapedLine = _escapeHtml(line).replace(/ {2,}/g, function(spaces) {
                            return spaces.replace(/ /g, '&nbsp;');
                          });
                          html.push('<p>'+ escapedLine +'</p>');
                        }
                        if(listMode){ flushList(); }
                        return html.join('');
                      }
                      var conclusions = document.querySelectorAll('.editable-conclusion');
                      for(var i=0;i<conclusions.length;i++){
                        var el = conclusions[i];
                        var text = el.innerText || el.textContent || '';
                        if(!text || text.trim()===''){ el.innerHTML = ''; el.className='conclusion-output'; continue; }
                        if(text.length > 4000){ text = text.substring(0, 3997) + '...'; }
                        el.innerHTML = _formatUserTextToHtml(text);
                        el.className='conclusion-output';
                      }
                    }
                    """
                )

                # 将服务器类型二选一转为纯文本
                page.evaluate(
                    """
                    () => {
                      var wrap = document.querySelector('[data-suggest-id="server_type"]');
                      if(wrap){
                        var sel = wrap.querySelector('select');
                        var val = '';
                        if(sel){ val = (sel.options[sel.selectedIndex] && sel.options[sel.selectedIndex].text) || sel.value || ''; }
                        var td = wrap.closest('td') || wrap;
                        td.innerHTML = val || '';
                      }
                    }
                    """
                )

                # 净化DOM：移除编辑UI与可编辑标记
                page.evaluate(
                    """
                    () => {
                      var rm = document.querySelectorAll('#edit-toolbar, .edit-controls');
                      for(var i=0;i<rm.length;i++){ rm[i].parentNode.removeChild(rm[i]); }
                      var ed1 = document.querySelectorAll('[contenteditable]');
                      for(var j=0;j<ed1.length;j++){ ed1[j].removeAttribute('contenteditable'); }
                      var ed2 = document.querySelectorAll('[data-suggest-id]');
                      for(var k=0;k<ed2.length;k++){ ed2[k].removeAttribute('data-suggest-id'); }
                      // 移除编辑类名，避免最终样式受影响
                      var cls = document.querySelectorAll('.editable-conclusion');
                      for(var m=0;m<cls.length;m++){ cls[m].className = ''; }
                    }
                    """
                )

                # 可选保存final HTML至与输入同目录，保持资源相对路径可用
                if final_html_path:
                    html_content = page.content()
                    try:
                        with open(final_html_path, 'w', encoding='utf-8') as f:
                            f.write('<!DOCTYPE html>\n')
                            f.write(html_content)
                        logger.info(f"已输出final HTML: {final_html_path}")
                    except Exception as e:
                        logger.warning(f"写入final HTML失败: {final_html_path} 错误: {e}")
                
                # 生成PDF
                page.pdf(
                    path=pdf_file,
                    format='A4',
                    print_background=True,
                    margin={
                        'top': '2.5cm',
                        'right': '2cm', 
                        'bottom': '2.5cm',
                        'left': '2cm'
                    }
                )
                
                browser.close()
                return True
                
        except Exception as e:
            logger.error(f"PDF生成失败: {e}")
            return False
