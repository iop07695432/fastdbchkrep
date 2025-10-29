"""
AWR HTML渲染截图模块
使用Playwright + Chromium实现AWR报告的高质量截图
"""
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import tempfile
import json
from loguru import logger

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright未安装，AWR HTML截图功能不可用")


class HTMLCapture:
    """AWR HTML截图工具类"""
    
    # AWR报告常用章节别名（推荐使用 capture_by_summary() 方法直接传入summary文本）
    AWR_SELECTORS = {
        # === 核心章节（保留常用别名便于快速使用） ===
        "database_info": 'table[summary="This table displays database instance information"]',
        "host_info": 'table[summary="This table displays host information"]',
        "snapshot_info": 'table[summary="This table displays snapshot information"]',
        "load_profile": 'table[summary="This table displays load profile"]',
        "instance_efficiency": 'table[summary="This table displays instance efficiency percentages"]',
        "top_wait_events": 'table[summary="This table displays top 10 wait events by total wait time"]',
        "wait_class_stats": 'table[summary="This table displays wait class statistics ordered by total wait time"]',
        "foreground_wait_events": 'table[summary="This table displays Foreground Wait Events and their wait statistics"]',
        "top_sql_elapsed": 'table[summary="This table displays top SQL by elapsed time"]',
        "top_sql_cpu": 'table[summary="This table displays top SQL by CPU time"]',
        "cache_sizes": 'table[summary="This table displays cache sizes and other statistics for different types of cache"]',
        "shared_pool": 'table[summary="This table displays shared pool statistics"]',
        
        # === 注意 ===
        # 对于其他AWR章节，推荐使用 capture_by_summary() 方法
        # 直接传入summary属性文本，支持智能匹配和跨行文本
    }
    
    def __init__(self, 
                 device_scale_factor: float = 2.5, 
                 timeout: int = 30000,
                 compress_images: bool = True,
                 max_file_size_kb: int = 200):
        """
        初始化HTML截图工具
        
        Args:
            device_scale_factor: 设备缩放因子，提高图片质量 (建议2.0-3.0)
            timeout: 页面加载超时时间(毫秒)
            compress_images: 是否压缩图片
            max_file_size_kb: 最大文件大小(KB)，超过此大小会进行压缩
        """
        self.device_scale_factor = device_scale_factor
        self.timeout = timeout
        self.compress_images = compress_images
        self.max_file_size_kb = max_file_size_kb
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    def __enter__(self):
        """上下文管理器：启动浏览器"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright未安装，无法使用HTML截图功能")
        
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=['--disable-web-security', '--disable-features=VizDisplayCompositor']
            )
            self.page = self.browser.new_page(
                viewport={"width": 1600, "height": 1400},
                device_scale_factor=self.device_scale_factor
            )
            return self
        except Exception as e:
            logger.error(f"启动Playwright浏览器失败: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：清理资源"""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
        except Exception as e:
            logger.warning(f"关闭Playwright浏览器时出现警告: {e}")
    
    def _compress_image(self, image_path: Path) -> bool:
        """
        压缩图片文件，减小文件大小同时保持质量
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            是否成功压缩
        """
        if not PIL_AVAILABLE:
            logger.debug("PIL不可用，跳过图片压缩")
            return False
            
        try:
            # 检查文件大小
            file_size_kb = image_path.stat().st_size / 1024
            if file_size_kb <= self.max_file_size_kb:
                logger.debug(f"文件大小 {file_size_kb:.1f}KB 无需压缩")
                return False
            
            logger.info(f"压缩图片: {image_path.name} ({file_size_kb:.1f}KB -> 目标<{self.max_file_size_kb}KB)")
            
            # 打开原图片
            with Image.open(image_path) as img:
                # 转换为RGB模式（如果是RGBA）
                if img.mode in ('RGBA', 'LA', 'P'):
                    # 创建白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # 计算目标质量
                original_size = image_path.stat().st_size
                target_size = self.max_file_size_kb * 1024
                
                # 渐进式压缩，从高质量开始
                qualities = [95, 85, 75, 65, 55, 45]
                
                for quality in qualities:
                    # 保存到临时文件测试大小
                    temp_path = image_path.with_suffix('.temp.jpg')
                    img.save(temp_path, 'JPEG', quality=quality, optimize=True)
                    
                    compressed_size = temp_path.stat().st_size
                    if compressed_size <= target_size:
                        # 替换原文件
                        temp_path.replace(image_path.with_suffix('.png'))
                        final_size_kb = compressed_size / 1024
                        logger.success(f"压缩成功: {file_size_kb:.1f}KB -> {final_size_kb:.1f}KB (质量{quality})")
                        return True
                    else:
                        # 删除临时文件，尝试更低质量
                        temp_path.unlink()
                
                # 如果所有质量都不满足，使用最低质量
                img.save(image_path.with_suffix('.png'), 'PNG', optimize=True)
                final_size = image_path.stat().st_size
                final_size_kb = final_size / 1024
                logger.warning(f"使用最大压缩: {file_size_kb:.1f}KB -> {final_size_kb:.1f}KB")
                return True
                
        except Exception as e:
            logger.error(f"图片压缩失败: {e}")
            return False
    
    def extract_style_from_html(self, html_path: Path) -> str:
        """
        从AWR HTML文件中提取<style>标签内容
        
        Args:
            html_path: AWR HTML文件路径
            
        Returns:
            提取的CSS样式字符串
        """
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # 查找<style>标签
            start_tag = "<style type=\"text/css\">"
            end_tag = "</style>"
            
            start_index = html_content.find(start_tag)
            if start_index == -1:
                logger.warning(f"未找到<style>标签: {html_path}")
                return ""
            
            start_index += len(start_tag)
            end_index = html_content.find(end_tag, start_index)
            if end_index == -1:
                logger.warning(f"未找到</style>结束标签: {html_path}")
                return ""
            
            css_content = html_content[start_index:end_index].strip()
            logger.debug(f"成功提取CSS样式，长度: {len(css_content)}字符")
            return css_content
            
        except Exception as e:
            logger.error(f"提取CSS样式失败: {e}")
            return ""
    
    def create_styled_html_for_element(self, 
                                     original_html_path: Path,
                                     css_selector: str,
                                     include_spacing: bool = True) -> str:
        """
        创建包含样式的独立HTML文档，用于截图
        
        Args:
            original_html_path: 原始AWR HTML文件路径
            css_selector: CSS选择器
            include_spacing: 是否包含前后的<p/>间距元素
            
        Returns:
            完整的HTML文档字符串
        """
        try:
            # 读取原始HTML内容
            with open(original_html_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # 提取CSS样式
            css_styles = self.extract_style_from_html(original_html_path)
            
            # 使用简单的字符串匹配提取目标元素
            target_html = self._extract_element_with_spacing(
                original_content, css_selector, include_spacing
            )
            
            if not target_html:
                logger.error(f"未找到匹配的HTML元素: {css_selector}")
                return ""
            
            # 构建完整的HTML文档
            styled_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWR Section</title>
    <style type="text/css">
{css_styles}
    </style>
</head>
<body class="awr">
{target_html}
</body>
</html>
            """.strip()
            
            logger.debug(f"成功创建样式化HTML文档，长度: {len(styled_html)}字符")
            return styled_html
            
        except Exception as e:
            logger.error(f"创建样式化HTML失败: {e}")
            return ""
    
    def _find_summary_with_flexible_matching(self, html_content: str, summary_value: str) -> int:
        """
        使用灵活匹配查找summary属性，支持跨行和空格差异
        
        Args:
            html_content: HTML内容
            summary_value: 要查找的summary值
            
        Returns:
            找到的位置索引，未找到返回-1
        """
        try:
            # 标准化函数：移除多余空格，保留单个空格
            def normalize_text(text):
                import re
                # 将换行符、制表符等空白字符替换为单个空格
                text = re.sub(r'\s+', ' ', text.strip())
                return text
            
            # 标准化要搜索的summary文本
            normalized_search = normalize_text(summary_value)
            
            # 查找所有summary属性
            import re
            summary_pattern = r'summary="([^"]*(?:\n[^"]*)*)"'
            matches = re.finditer(summary_pattern, html_content, re.MULTILINE | re.DOTALL)
            
            for match in matches:
                html_summary = match.group(1)
                normalized_html = normalize_text(html_summary)
                
                # 比较标准化后的文本
                if normalized_search.lower() == normalized_html.lower():
                    logger.debug(f"灵活匹配成功: '{normalized_search}' -> '{normalized_html}'")
                    return match.start()
            
            # 如果没有找到完全匹配，尝试部分匹配
            for match in matches:
                html_summary = match.group(1)
                normalized_html = normalize_text(html_summary)
                
                # 检查是否包含核心关键词
                if (len(normalized_search) > 20 and 
                    normalized_search.lower() in normalized_html.lower()):
                    logger.debug(f"部分匹配成功: '{normalized_search}' 在 '{normalized_html}' 中")
                    return match.start()
            
            return -1
            
        except Exception as e:
            logger.error(f"灵活匹配查找失败: {e}")
            return -1
    
    def _extract_element_with_spacing(self, 
                                    html_content: str, 
                                    css_selector: str, 
                                    include_spacing: bool) -> str:
        """
        从HTML内容中提取目标元素及其前后间距
        
        Args:
            html_content: 原始HTML内容
            css_selector: CSS选择器
            include_spacing: 是否包含<p/>间距
            
        Returns:
            提取的HTML片段
        """
        try:
            # 从CSS选择器提取summary属性值
            # 例如: table[summary="This table displays database instance information"]
            if 'summary="' in css_selector:
                summary_start = css_selector.find('summary="') + len('summary="')
                summary_end = css_selector.find('"', summary_start)
                summary_value = css_selector[summary_start:summary_end]
            else:
                logger.error(f"CSS选择器格式不正确: {css_selector}")
                return ""
            
            # 使用灵活匹配查找summary属性
            table_start = self._find_summary_with_flexible_matching(html_content, summary_value)
            if table_start == -1:
                logger.error(f"未找到summary属性: {summary_value}")
                return ""
            
            # 向前查找table开始标签
            table_open_start = html_content.rfind('<table', 0, table_start)
            if table_open_start == -1:
                logger.error(f"未找到table开始标签")
                return ""
            
            # 向后查找table结束标签
            table_close_end = html_content.find('</table>', table_start) + len('</table>')
            if table_close_end == len('</table>') - 1:  # find返回-1的情况
                logger.error(f"未找到table结束标签")
                return ""
            
            # 提取table内容
            table_content = html_content[table_open_start:table_close_end]
            
            if not include_spacing:
                return table_content
            
            # 包含前后的<p/>间距
            # 向前查找<p />标签
            prev_p_start = html_content.rfind('<p />', 0, table_open_start)
            start_pos = prev_p_start if prev_p_start != -1 else table_open_start
            
            # 向后查找<p />标签
            next_p_end = html_content.find('<p />', table_close_end)
            if next_p_end != -1:
                next_p_end += len('<p />')
                end_pos = next_p_end
            else:
                end_pos = table_close_end
            
            result_content = html_content[start_pos:end_pos]
            
            # 在结果后面添加2个额外的<p />元素，使显示更美观
            result_content += '<p /><p />'
            logger.debug(f"成功提取HTML元素，长度: {len(result_content)}字符")
            return result_content
            
        except Exception as e:
            logger.error(f"提取HTML元素失败: {e}")
            return ""
    
    def capture_by_summary(self,
                         html_file_path: Path,
                         summary_text: str,
                         output_file_name: str,
                         output_dir: Path,
                         include_spacing: bool = True) -> str:
        """
        直接通过summary属性文本截取AWR报告章节
        
        Args:
            html_file_path: AWR HTML文件路径
            summary_text: summary属性的完整文本
            output_file_name: 输出文件名(不含扩展名)
            output_dir: 输出目录
            include_spacing: 是否包含前后间距
            
        Returns:
            成功时返回生成的图片文件名，失败时返回错误信息
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "获取 AWR 报告图片失败 - Playwright未安装"
        
        try:
            css_selector = f'table[summary="{summary_text}"]'
            
            # 创建样式化的HTML内容
            styled_html = self.create_styled_html_for_element(
                html_file_path, css_selector, include_spacing
            )
            
            if not styled_html:
                return "获取 AWR 报告图片失败 - HTML内容提取失败"
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{output_file_name}.png"
            
            # 使用临时文件进行截图
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', 
                                           encoding='utf-8', delete=False) as temp_file:
                temp_file.write(styled_html)
                temp_html_path = Path(temp_file.name)
            
            try:
                # 执行截图
                success = self._perform_screenshot(temp_html_path, output_file, css_selector)
                if success:
                    # 如果启用压缩且图片存在，尝试压缩
                    if self.compress_images and output_file.exists():
                        self._compress_image(output_file)
                    
                    logger.info(f"AWR章节截图成功: {output_file}")
                    return output_file.name
                else:
                    return "获取 AWR 报告图片失败 - 截图执行失败"
                    
            finally:
                # 清理临时文件
                try:
                    temp_html_path.unlink()
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"AWR章节截图失败: {e}")
            return "获取 AWR 报告图片失败"
    
    def capture_awr_section(self, 
                          html_file_path: Path,
                          section_name: str,
                          output_dir: Path,
                          include_spacing: bool = True) -> str:
        """
        截取AWR报告指定章节并生成图片
        
        Args:
            html_file_path: AWR HTML文件路径
            section_name: 章节名称 (在AWR_SELECTORS中定义)
            output_dir: 输出目录
            include_spacing: 是否包含前后间距
            
        Returns:
            成功时返回生成的图片文件名，失败时返回错误信息
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "获取 AWR 报告图片失败 - Playwright未安装"
        
        if section_name not in self.AWR_SELECTORS:
            return f"获取 AWR 报告图片失败 - 未知章节: {section_name}"
        
        try:
            css_selector = self.AWR_SELECTORS[section_name]
            
            # 创建样式化的HTML内容
            styled_html = self.create_styled_html_for_element(
                html_file_path, css_selector, include_spacing
            )
            
            if not styled_html:
                return "获取 AWR 报告图片失败 - HTML内容提取失败"
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"awr_{section_name}.png"
            
            # 使用临时文件进行截图
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', 
                                           encoding='utf-8', delete=False) as temp_file:
                temp_file.write(styled_html)
                temp_html_path = Path(temp_file.name)
            
            try:
                # 执行截图
                success = self._perform_screenshot(temp_html_path, output_file, css_selector)
                if success:
                    # 如果启用压缩且图片存在，尝试压缩
                    if self.compress_images and output_file.exists():
                        self._compress_image(output_file)
                    
                    logger.info(f"AWR章节截图成功: {output_file}")
                    return output_file.name
                else:
                    return "获取 AWR 报告图片失败 - 截图执行失败"
                    
            finally:
                # 清理临时文件
                try:
                    temp_html_path.unlink()
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"AWR章节截图失败: {e}")
            return "获取 AWR 报告图片失败"
    
    def _perform_screenshot(self, 
                          html_file_path: Path, 
                          output_path: Path,
                          css_selector: str) -> bool:
        """
        执行实际的截图操作
        
        Args:
            html_file_path: HTML文件路径
            output_path: 输出图片路径
            css_selector: CSS选择器
            
        Returns:
            截图是否成功
        """
        try:
            if not self.page:
                logger.error("页面对象未初始化")
                return False
            
            # 加载HTML文件
            file_url = f"file://{html_file_path.absolute()}"
            self.page.goto(file_url, timeout=self.timeout)
            
            # 等待页面加载完成
            self.page.wait_for_load_state("networkidle")
            
            # 查找目标元素并截图 - 修复白边问题
            try:
                # 直接截图table元素，避免右侧白边
                table_element = self.page.locator("table").first
                if table_element.count() > 0:
                    # 获取table元素的边界框
                    bounding_box = table_element.bounding_box()
                    if bounding_box:
                        # 检查边界框是否有效
                        if (bounding_box["width"] > 0 and bounding_box["height"] > 0 and
                            bounding_box["x"] >= 0 and bounding_box["y"] >= 0):
                            
                            # 获取页面尺寸
                            viewport = self.page.viewport_size
                            page_width = viewport["width"]
                            page_height = viewport["height"]
                            
                            # 确保截图区域在页面范围内
                            clip_x = max(0, min(bounding_box["x"] - 5, page_width - 10))
                            clip_y = max(0, min(bounding_box["y"] - 5, page_height - 10))
                            clip_width = min(bounding_box["width"] + 10, page_width - clip_x)
                            clip_height = min(bounding_box["height"] + 10, page_height - clip_y)
                            
                            # 检查最终的截图区域是否有效
                            if clip_width > 10 and clip_height > 10:
                                self.page.screenshot(
                                    path=str(output_path),
                                    clip={
                                        "x": clip_x,
                                        "y": clip_y,
                                        "width": clip_width,
                                        "height": clip_height
                                    }
                                )
                                return True
                            else:
                                logger.warning(f"截图区域过小: {clip_width}x{clip_height}，尝试元素截图")
                                table_element.screenshot(path=str(output_path))
                                return True
                        else:
                            logger.warning(f"边界框无效: {bounding_box}，尝试元素截图")
                            table_element.screenshot(path=str(output_path))
                            return True
                    else:
                        # fallback到元素截图
                        logger.warning("无法获取边界框，使用元素截图")
                        table_element.screenshot(path=str(output_path))
                        return True
                else:
                    logger.error("未找到table元素")
                    return False
                    
            except Exception as e:
                logger.error(f"元素定位或截图失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"截图执行失败: {e}")
            return False
    
    def capture_multiple_sections(self,
                                html_file_path: Path,
                                section_names: List[str],
                                output_dir: Path,
                                include_spacing: bool = True) -> Dict[str, str]:
        """
        批量截取多个AWR章节
        
        Args:
            html_file_path: AWR HTML文件路径
            section_names: 章节名称列表
            output_dir: 输出目录
            include_spacing: 是否包含前后间距
            
        Returns:
            字典，键为章节名，值为截图结果（文件名或错误信息）
        """
        results = {}
        
        # 检查浏览器是否已启动，如果没有则启动
        need_context_manager = self.browser is None
        
        try:
            if need_context_manager:
                with self:  # 使用上下文管理器
                    for section_name in section_names:
                        result = self.capture_awr_section(
                            html_file_path, section_name, output_dir, include_spacing
                        )
                        results[section_name] = result
                        logger.info(f"章节 {section_name} 处理完成: {result}")
            else:
                # 浏览器已启动，直接使用
                for section_name in section_names:
                    result = self.capture_awr_section(
                        html_file_path, section_name, output_dir, include_spacing
                    )
                    results[section_name] = result
                    logger.info(f"章节 {section_name} 处理完成: {result}")
        
        except Exception as e:
            logger.error(f"批量截图失败: {e}")
            # 为所有未处理的章节返回错误信息
            for section_name in section_names:
                if section_name not in results:
                    results[section_name] = "获取 AWR 报告图片失败"
        
        return results
    
    @classmethod
    def get_available_sections(cls) -> Dict[str, str]:
        """
        获取所有可用的AWR章节及其描述
        
        Returns:
            字典，键为章节名，值为CSS选择器
        """
        return cls.AWR_SELECTORS.copy()
    
    @staticmethod
    def is_available() -> bool:
        """检查HTML截图功能是否可用"""
        return PLAYWRIGHT_AVAILABLE


def capture_by_summary_simple(html_path: Path,
                             summary_text: str,
                             output_file_name: str,
                             output_dir: Path) -> str:
    """
    简化的通过summary属性截取AWR章节的函数
    
    Args:
        html_path: AWR HTML文件路径
        summary_text: summary属性的完整文本
        output_file_name: 输出文件名(不含扩展名)
        output_dir: 输出目录
        
    Returns:
        截图结果（文件名或错误信息）
    """
    if not HTMLCapture.is_available():
        return "获取 AWR 报告图片失败 - 截图功能不可用"
    
    try:
        with create_html_capture() as capture:
            return capture.capture_by_summary(html_path, summary_text, output_file_name, output_dir)
    except Exception as e:
        logger.error(f"通过summary截图失败: {e}")
        return "获取 AWR 报告图片失败"


# 工具函数
def create_html_capture(device_scale_factor: float = 2.5,
                       compress_images: bool = True,
                       max_file_size_kb: int = 200) -> HTMLCapture:
    """创建HTMLCapture实例的工厂函数"""
    return HTMLCapture(
        device_scale_factor=device_scale_factor,
        compress_images=compress_images,
        max_file_size_kb=max_file_size_kb
    )


def capture_awr_section_simple(html_path: Path, 
                             section_name: str, 
                             output_dir: Path) -> str:
    """
    简化的AWR章节截图函数
    
    Args:
        html_path: AWR HTML文件路径
        section_name: 章节名称
        output_dir: 输出目录
        
    Returns:
        截图结果（文件名或错误信息）
    """
    if not HTMLCapture.is_available():
        return "获取 AWR 报告图片失败 - 截图功能不可用"
    
    try:
        with create_html_capture() as capture:
            return capture.capture_awr_section(html_path, section_name, output_dir)
    except Exception as e:
        logger.error(f"简化截图失败: {e}")
        return "获取 AWR 报告图片失败"


def capture_multiple_awr_sections_simple(html_path: Path,
                                        section_names: List[str],
                                        output_dir: Path) -> Dict[str, str]:
    """
    简化的批量AWR章节截图函数
    
    Args:
        html_path: AWR HTML文件路径
        section_names: 章节名称列表
        output_dir: 输出目录
        
    Returns:
        字典，键为章节名，值为截图结果
    """
    if not HTMLCapture.is_available():
        return {name: "获取 AWR 报告图片失败 - 截图功能不可用" for name in section_names}
    
    results = {}
    try:
        # 使用上下文管理器确保资源清理
        with create_html_capture() as capture:
            for section_name in section_names:
                result = capture.capture_awr_section(html_path, section_name, output_dir)
                results[section_name] = result
                logger.info(f"章节 {section_name} 处理完成: {result}")
        
        return results
        
    except Exception as e:
        logger.error(f"批量截图失败: {e}")
        # 为所有未处理的章节返回错误信息
        for section_name in section_names:
            if section_name not in results:
                results[section_name] = "获取 AWR 报告图片失败"
        
        return results