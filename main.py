#!/usr/bin/env python3
"""
FastDBCheckRep 主入口脚本
使用方法:
  python main.py parse      # 解析元数据
  python main.py report     # 生成报告
  python main.py --help     # 查看帮助
"""
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

def validate_path_exists(path_str: str, param_name: str) -> Path:
    """验证路径是否存在并返回Path对象"""
    path = Path(path_str)
    if not path.exists():
        raise ValueError(f"{param_name} 路径不存在: {path_str}")
    return path

def validate_directory_exists(path_str: str, param_name: str) -> Path:
    """验证目录是否存在并返回Path对象"""
    path = Path(path_str)
    if not path.is_dir():
        raise ValueError(f"{param_name} 目录不存在: {path_str}")
    return path

def validate_file_exists(path_str: str, param_name: str) -> Path:
    """验证文件是否存在并返回Path对象"""
    path = Path(path_str)
    if not path.is_file():
        raise ValueError(f"{param_name} 文件不存在: {path_str}")
    return path

def validate_parent_directory_exists(path_str: str, param_name: str) -> Path:
    """验证父目录是否存在并返回Path对象"""
    path = Path(path_str)
    if not path.parent.exists():
        raise ValueError(f"{param_name} 的父目录不存在: {path.parent}")
    return path

def handle_parse_command(args) -> int:
    """处理parse命令"""
    try:
        # 验证必需参数
        if not args.dbtype:
            print("❌ 错误：-dbtype 参数不能为空")
            return 1
        
        if not args.dbmodel:
            print("❌ 错误：-dbmodel 参数不能为空")
            return 1
        
        if not args.jsonout:
            print("❌ 错误：-jsonout 参数不能为空")
            return 1

        # 验证数据库类型和模型
        if args.dbtype not in ['oracle', 'mysql', 'postgresql', 'sqlserver']:
            print("❌ 错误：-dbtype 必须是 oracle、mysql、postgresql 或 sqlserver 之一")
            return 1

        if args.dbmodel not in ['one', 'rac']:
            print("❌ 错误：-dbmodel 必须是 one 或 rac 之一")
            return 1

        # 验证输入目录
        import_dirs = []
        if args.dbmodel == 'one':
            if not args.import_dir:
                print("❌ 错误：单机模式(-dbmodel one)需要指定 -import_dir 参数")
                return 1
            import_dir = validate_directory_exists(args.import_dir, "-import_dir")
            import_dirs.append(str(import_dir))
        else:  # rac模式
            if not args.import_dir_1 or not args.import_dir_2:
                print("❌ 错误：RAC模式(-dbmodel rac)需要至少指定 -import_dir_1 和 -import_dir_2 参数")
                return 1
            
            import_dir_1 = validate_directory_exists(args.import_dir_1, "-import_dir_1")
            import_dir_2 = validate_directory_exists(args.import_dir_2, "-import_dir_2")
            import_dirs.extend([str(import_dir_1), str(import_dir_2)])
            
            if args.import_dir_3:
                import_dir_3 = validate_directory_exists(args.import_dir_3, "-import_dir_3")
                import_dirs.append(str(import_dir_3))
            
            if args.import_dir_4:
                import_dir_4 = validate_directory_exists(args.import_dir_4, "-import_dir_4")
                import_dirs.append(str(import_dir_4))

        # 验证输出目录
        jsonout_path = validate_parent_directory_exists(args.jsonout, "-jsonout")

        # 根据数据库类型选择对应的parser
        if args.dbtype == 'mysql':
            from fastdbchkrep.meta.mysql.parser import parse_mysql_metadata
            parse_func = parse_mysql_metadata
        else:
            from fastdbchkrep.meta.parser import parse_metadata
            parse_func = parse_metadata
        
        if not args.quiet:
            print(f"开始解析数据库元数据...")
            print(f"  数据库类型: {args.dbtype}")
            print(f"  数据库模型: {args.dbmodel}")
            print(f"  输入目录: {import_dirs}")
            print(f"  输出目录: {jsonout_path}")
        
        # 调用解析函数
        if args.dbtype == 'mysql':
            # MySQL专用接口，不需要db_type和db_model参数
            success = parse_func(
                import_dirs=import_dirs,
                json_out_dir=str(jsonout_path),
                identifier=getattr(args, 'identifier', None),
                log_dir=None
            )
        else:
            # 其他数据库使用通用接口
            success = parse_func(
                db_type=args.dbtype,
                db_model=args.dbmodel,
                import_dirs=import_dirs,
                json_out_dir=str(jsonout_path),
                identifier=getattr(args, 'identifier', None),
                log_dir=None
            )
        
        if success:
            if not args.quiet:
                print("✅ Parse命令执行成功")
            return 0
        else:
            print("❌ Parse命令执行失败")
            return 1

    except ValueError as e:
        print(f"❌ 参数验证失败: {e}")
        return 1
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("请确保fastdbchkrep包正确安装")
        return 1
    except Exception as e:
        print(f"❌ Parse命令执行失败: {e}")
        return 1

def handle_report_command(args) -> int:
    """处理report命令"""
    try:
        # 验证互斥参数：-import_json 和 -import_txt 必须且只能提供一个
        has_json = hasattr(args, 'import_json') and args.import_json
        has_txt = hasattr(args, 'import_txt') and args.import_txt

        if not has_json and not has_txt:
            print("❌ 错误：必须提供 -import_json 或 -import_txt 参数之一")
            return 1

        if has_json and has_txt:
            print("❌ 错误：-import_json 和 -import_txt 参数互斥，只能提供一个")
            return 1

        # 验证必需参数
        if not args.mdout:
            print("❌ 错误：-mdout 参数不能为空")
            return 1

        if not args.company_name:
            print("❌ 错误：-company_name 参数不能为空")
            return 1

        if not args.user_company:
            print("❌ 错误：-user_company 参数不能为空")
            return 1

        if not args.application_name:
            print("❌ 错误：-application_name 参数不能为空")
            return 1

        # 验证公司名称
        if args.company_name not in ['鼎诚科技', '伟宏智能']:
            print("❌ 错误：-company_name 必须是 '鼎诚科技' 或 '伟宏智能' 之一")
            return 1

        mdout_path = validate_parent_directory_exists(args.mdout, "-mdout")

        # 根据输入类型路由到不同的处理逻辑
        if has_txt:
            # SQL Server TXT 流程
            return handle_sqlserver_txt_report(args, mdout_path)
        else:
            # Oracle/MySQL JSON 流程
            return handle_json_report(args, mdout_path)

    except ValueError as e:
        print(f"❌ 参数验证失败: {e}")
        return 1
    except Exception as e:
        print(f"❌ Report命令执行失败: {e}")
        return 1


def handle_json_report(args, mdout_path: str) -> int:
    """处理 JSON 输入的报告生成（Oracle/MySQL）"""
    try:
        # 验证输入文件
        import_json = validate_file_exists(args.import_json, "-import_json")

        # 导入报告生成模块
        from fastdbchkrep.report.api import generate_report_from_json

        # 调用报告生成逻辑
        if not args.quiet:
            print(f"开始生成报告...")
            print(f"  输入JSON: {import_json}")
            print(f"  输出目录: {mdout_path}")

        # 生成报告，传入mdout_path参数
        kwargs = {
            'json_file': import_json,
            'output_dir': mdout_path,
            'company_name': args.company_name,
            'user_company': args.user_company,
            'application_name': args.application_name,
            'quiet': args.quiet
        }

        # 添加可选参数
        if hasattr(args, 'suptime') and args.suptime:
            kwargs['suptime'] = args.suptime
        if hasattr(args, 'supname') and args.supname:
            kwargs['supname'] = args.supname

        success = generate_report_from_json(**kwargs)

        if success:
            if not args.quiet:
                print(f"✅ 报告生成成功！")
            return 0
        else:
            print(f"❌ 报告生成失败，请检查日志")
            return 1

    except Exception as e:
        print(f"❌ JSON报告生成失败: {e}")
        return 1


def handle_sqlserver_txt_report(args, mdout_path: str) -> int:
    """处理 TXT 输入的报告生成（SQL Server）"""
    try:
        from pathlib import Path

        # 验证输入文件
        import_txt = validate_file_exists(args.import_txt, "-import_txt")

        # 导入 SQL Server 报告生成模块
        from fastdbchkrep.report.sqlserver import MarkdownGenerator

        # 调用报告生成逻辑
        if not args.quiet:
            print(f"开始生成 SQL Server 报告...")
            print(f"  输入TXT: {import_txt}")
            print(f"  输出目录: {mdout_path}")

        # 创建生成器实例
        generator = MarkdownGenerator(
            db_type="sqlserver",
            output_dir=Path(mdout_path),
            company_name=args.company_name,
            user_company=args.user_company,
            application_name=args.application_name,
            suptime=getattr(args, 'suptime', None),
            supname=getattr(args, 'supname', None)
        )

        # 生成报告
        success = generator.generate_from_txt(Path(import_txt), quiet=args.quiet)

        if success:
            if not args.quiet:
                print(f"✅ SQL Server 报告生成成功！")
            return 0
        else:
            print(f"❌ SQL Server 报告生成失败，请检查日志")
            return 1

    except Exception as e:
        print(f"❌ SQL Server TXT报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

def handle_htmltopdf_command(args) -> int:
    """处理htmltopdf命令（从可编辑HTML生成PDF）"""
    try:
        # 验证必需参数
        if not args.import_html:
            print("❌ 错误：-import_html 参数不能为空")
            return 1

        if not args.pdfout:
            print("❌ 错误：-pdfout 参数不能为空")
            return 1

        if not args.pdfname:
            print("❌ 错误：-pdfname 参数不能为空")
            return 1

        # 验证输入文件和输出目录
        import_html = validate_file_exists(args.import_html, "-import_html")
        pdfout_path = validate_parent_directory_exists(args.pdfout, "-pdfout")

        print("📄 开始将HTML转换为PDF")
        print(f"  输入文件: {import_html}")
        print(f"  输出目录: {pdfout_path}")
        print(f"  文件名称: {args.pdfname}")

        # 导入转换模块
        from fastdbchkrep.report.pdf import MarkdownToPdfConverter

        converter = MarkdownToPdfConverter()
        success, pdf_file = converter.html_to_pdf(
            html_file=str(import_html),
            output_dir=str(pdfout_path),
            output_name=args.pdfname
        )

        if success:
            print(f"✅ 转换成功！")
            print(f"  PDF文件: {pdf_file}")
            return 0
        else:
            print(f"❌ 转换失败，请检查日志")
            return 1

    except ValueError as e:
        print(f"❌ 参数验证失败: {e}")
        return 1
    except Exception as e:
        print(f"❌ htmltopdf命令执行失败: {e}")
        return 1

def main():
    parser = argparse.ArgumentParser(
        description='FastDBCheckRep - 数据库巡检报告生成工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子命令:
  parse     解析数据库元数据
  report    生成巡检报告
  htmltopdf 将HTML（可编辑版）转换为PDF

Parse命令示例:
  # Oracle单机
  python main.py parse \\
    -import_dir "/path/to/data" \\
    -dbtype oracle \\
    -dbmodel one \\
    -jsonout "/path/to/json"
    
  # Oracle RAC
  python main.py parse \\
    -import_dir_1 "/path/to/node1" \\
    -import_dir_2 "/path/to/node2" \\
    -dbtype oracle \\
    -dbmodel rac \\
    -jsonout "/path/to/json"

Report命令示例:
  # Oracle/MySQL (从 JSON)
  python main.py report \\
    -import_json "/path/to/meta.json" \\
    -mdout "/path/to/md" \\
    -company_name "鼎诚科技" \\
    -user_company "海南电网" \\
    -application_name "OMS调度系统"

  # SQL Server (从 TXT)
  python main.py report \\
    -import_txt "/path/to/172.18.0.2-HealthCheck-20251023.txt" \\
    -mdout "/path/to/md" \\
    -company_name "鼎诚科技" \\
    -user_company "海南电网" \\
    -application_name "OMS调度系统"

htmltopdf命令示例:
  python main.py htmltopdf \\
    -import_html "/path/to/report.editable.html" \\
    -pdfout "/path/to/pdf" \\
    -pdfname "2025年第三季度_海南电网_OMS系统_ORACLE数据库巡检报告_20250902"
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # parse子命令
    parse_parser = subparsers.add_parser('parse', help='解析数据库元数据')
    parse_parser.add_argument('-import_dir', type=str, help='输入目录(单机模式)')
    parse_parser.add_argument('-import_dir_1', type=str, help='输入目录1(RAC模式)')
    parse_parser.add_argument('-import_dir_2', type=str, help='输入目录2(RAC模式)')
    parse_parser.add_argument('-import_dir_3', type=str, help='输入目录3(RAC模式，可选)')
    parse_parser.add_argument('-import_dir_4', type=str, help='输入目录4(RAC模式，可选)')
    parse_parser.add_argument('-dbtype', type=str, required=True,
                             choices=['oracle', 'mysql', 'postgresql', 'sqlserver'],
                             help='数据库类型')
    parse_parser.add_argument('-dbmodel', type=str, required=True,
                             choices=['one', 'rac'],
                             help='数据库模型')
    parse_parser.add_argument('-jsonout', type=str, required=True,
                             help='JSON输出目录')
    parse_parser.add_argument('--identifier', type=str,
                             help='自定义标识符(可选，默认自动生成)')
    parse_parser.add_argument('--quiet', action='store_true', help='静默模式')

    # report子命令 - 使用互斥参数组
    report_parser = subparsers.add_parser('report', help='生成巡检报告')

    # 创建互斥参数组：-import_json 和 -import_txt 只能选一个
    input_group = report_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-import_json', type=str,
                             help='输入JSON文件路径 (Oracle/MySQL)')
    input_group.add_argument('-import_txt', type=str,
                             help='输入TXT文件路径 (SQL Server)')

    # 其他必需参数
    report_parser.add_argument('-mdout', type=str, required=True,
                             help='Markdown输出目录')
    report_parser.add_argument('-company_name', type=str, required=True,
                             choices=['鼎诚科技', '伟宏智能'],
                             help='公司名称')
    report_parser.add_argument('-user_company', type=str, required=True,
                             help='客户单位名称')
    report_parser.add_argument('-application_name', type=str, required=True,
                             help='应用系统名称')
    report_parser.add_argument('-suptime', type=str,
                             help='现场支持总时间（小时）')
    report_parser.add_argument('-supname', type=str,
                             help='支持工程师姓名')
    report_parser.add_argument('--quiet', action='store_true', help='静默模式')
    
    # htmltopdf子命令
    htmltopdf_parser = subparsers.add_parser('htmltopdf', help='将HTML（可编辑版）转换为PDF')
    htmltopdf_parser.add_argument('-import_html', type=str, required=True,
                                  help='输入HTML文件路径（建议使用*.editable.html）')
    htmltopdf_parser.add_argument('-pdfout', type=str, required=True,
                                  help='输出目录路径（PDF文件保存位置）')
    htmltopdf_parser.add_argument('-pdfname', type=str, required=True,
                                  help='输出文件名（不含扩展名）')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'parse':
            return handle_parse_command(args)
        elif args.command == 'report':
            return handle_report_command(args)
        elif args.command == 'htmltopdf':
            return handle_htmltopdf_command(args)
    except KeyboardInterrupt:
        print("\n❌ 操作被用户取消")
        return 1
    except Exception as e:
        print(f"❌ 程序执行异常: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
