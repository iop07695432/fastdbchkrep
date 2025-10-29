#!/bin/bash
# FastDBCheckRep 便捷启动脚本

# 配置二进制文件路径（优先使用打包好的二进制文件）
# 用户可以通过设置环境变量 FASTDBCHKREP_BINARY 来指定自定义路径
FASTDBCHKREP_BINARY="${FASTDBCHKREP_BINARY:-$PWD/binary/fastdbchkrep/fastdbchkrep}"

# 设置环境变量（动态解析site-packages路径，避免写死版本号）
resolve_python_and_site() {
  # 优先使用项目内venv的python3
  if [[ -x "$PWD/venv/bin/python3" ]]; then
    PY_BIN="$PWD/venv/bin/python3"
  else
    PY_BIN="python3"
  fi
  # 解析site-packages路径
  PY_SITE=$($PY_BIN - <<'PY'
import sysconfig, sys
print(sysconfig.get_paths().get('purelib',''))
PY
)
  echo "$PY_BIN|$PY_SITE"
}

IFS='|' read -r __PY_BIN __PY_SITE <<< "$(resolve_python_and_site)"
# 合并PYTHONPATH（不覆盖已有设置）
if [[ -n "$__PY_SITE" ]]; then
  export PYTHONPATH="$__PY_SITE:$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
else
  export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
fi

# 检查Python路径
if ! python3 --version >/dev/null 2>&1; then
    echo "❌ 未找到python3，请先安装Python 3"
    exit 1
fi

# 若打包的 Playwright 浏览器资源存在（onedir 完整版），则自动设置路径
if [[ -z "$PLAYWRIGHT_BROWSERS_PATH" ]]; then
  if [[ -d "$PWD/dist/fastdbchkrep/ms-playwright" ]]; then
    export PLAYWRIGHT_BROWSERS_PATH="$PWD/dist/fastdbchkrep/ms-playwright"
  elif [[ -d "$PWD/ms-playwright" ]]; then
    export PLAYWRIGHT_BROWSERS_PATH="$PWD/ms-playwright"
  fi
fi

# 路径标准化处理函数：去除末尾的斜杠
normalize_path() {
    local path="$1"
    # 去除路径末尾的斜杠，但保留根目录的斜杠
    if [[ "$path" == "/" ]]; then
        echo "$path"
    else
        echo "${path%/}"
    fi
}

# 参数验证函数
validate_parse_params() {
    local dbtype="$1"
    local dbmodel="$2"
    local import_dir="$3"
    local import_dir_1="$4"
    local import_dir_2="$5"
    local import_dir_3="$6"
    local import_dir_4="$7"
    local jsonout="$8"

    # 验证必需参数
    if [[ -z "$dbtype" ]]; then
        echo "❌ 错误：-dbtype 参数不能为空"
        return 1
    fi

    if [[ -z "$dbmodel" ]]; then
        echo "❌ 错误：-dbmodel 参数不能为空" 
        return 1
    fi

    if [[ -z "$jsonout" ]]; then
        echo "❌ 错误：-jsonout 参数不能为空"
        return 1
    fi

    # 验证数据库类型
    case "$dbtype" in
        "oracle"|"mysql"|"postgresql"|"sqlserver")
            ;;
        *)
            echo "❌ 错误：-dbtype 必须是 oracle、mysql、postgresql 或 sqlserver 之一"
            return 1
            ;;
    esac

    # 验证数据库模型
    case "$dbmodel" in
        "one"|"rac")
            ;;
        *)
            echo "❌ 错误：-dbmodel 必须是 one 或 rac 之一"
            return 1
            ;;
    esac

    # 根据数据库模型验证输入目录
    if [[ "$dbmodel" == "one" ]]; then
        if [[ -z "$import_dir" ]]; then
            echo "❌ 错误：单机模式(-dbmodel one)需要指定 -import_dir 参数"
            return 1
        fi
        if [[ ! -d "$import_dir" ]]; then
            echo "❌ 错误：输入目录不存在：$import_dir"
            return 1
        fi
    elif [[ "$dbmodel" == "rac" ]]; then
        if [[ -z "$import_dir_1" ]] || [[ -z "$import_dir_2" ]]; then
            echo "❌ 错误：RAC模式(-dbmodel rac)需要至少指定 -import_dir_1 和 -import_dir_2 参数"
            return 1
        fi
        if [[ ! -d "$import_dir_1" ]]; then
            echo "❌ 错误：输入目录1不存在：$import_dir_1"
            return 1
        fi
        if [[ ! -d "$import_dir_2" ]]; then
            echo "❌ 错误：输入目录2不存在：$import_dir_2"
            return 1
        fi
        # 检查可选的第3、4个目录
        if [[ -n "$import_dir_3" ]] && [[ ! -d "$import_dir_3" ]]; then
            echo "❌ 错误：输入目录3不存在：$import_dir_3"
            return 1
        fi
        if [[ -n "$import_dir_4" ]] && [[ ! -d "$import_dir_4" ]]; then
            echo "❌ 错误：输入目录4不存在：$import_dir_4"
            return 1
        fi
    fi

    # 检查输出目录的父目录是否存在
    local jsonout_parent
    jsonout_parent=$(dirname "$jsonout")
    if [[ ! -d "$jsonout_parent" ]]; then
        echo "❌ 错误：输出目录的父目录不存在：$jsonout_parent"
        return 1
    fi

    return 0
}

# 参数验证函数 - report命令
validate_report_params() {
    local mdout="$1"
    local company_name="$2"
    local user_company="$3"
    local application_name="$4"

    # 验证必需参数
    if [[ -z "$mdout" ]]; then
        echo "❌ 错误：-mdout 参数不能为空"
        return 1
    fi

    if [[ -z "$company_name" ]]; then
        echo "❌ 错误：-company_name 参数不能为空"
        return 1
    fi

    if [[ -z "$user_company" ]]; then
        echo "❌ 错误：-user_company 参数不能为空"
        return 1
    fi

    if [[ -z "$application_name" ]]; then
        echo "❌ 错误：-application_name 参数不能为空"
        return 1
    fi

    # 验证公司名称
    case "$company_name" in
        "鼎诚科技"|"伟宏智能")
            ;;
        *)
            echo "❌ 错误：-company_name 必须是 '鼎诚科技' 或 '伟宏智能' 之一"
            return 1
            ;;
    esac

    # 检查输出目录的父目录是否存在
    local mdout_parent
    mdout_parent=$(dirname "$mdout")
    if [[ ! -d "$mdout_parent" ]]; then
        echo "❌ 错误：输出目录的父目录不存在：$mdout_parent"
        return 1
    fi

    return 0
}

# 显示帮助信息
show_help() {
    echo "========================================"
    echo "FastDBCheckRep - 数据库巡检报告生成工具"
    echo "========================================"
    echo ""
    echo "用法: ./fastdbchkrep.sh <命令> [选项]"
    echo ""
    echo "可用命令:"
    echo "  parse     从原始数据生成JSON元数据文件"
    echo "  report    从JSON/TXT文件生成Markdown报告"
    echo "  htmltopdf 将HTML（可编辑版）转换为PDF文档"
    echo "  help      显示此帮助信息"
    echo ""
    echo "使用 './fastdbchkrep.sh <命令> --help' 查看各命令的详细帮助"
    echo ""
    echo "快速示例:"
    echo "  1. 解析 Oracle 单机: ./fastdbchkrep.sh parse -import_dir /data -dbtype oracle -dbmodel one -jsonout /json"
    echo "  2. 解析 MySQL 单机: ./fastdbchkrep.sh parse -import_dir /data -dbtype mysql -dbmodel one -jsonout /json"
    echo "  3. 生成报告 (Oracle/MySQL): ./fastdbchkrep.sh report -import_json /json/file.json -mdout /md -company_name 鼎诚科技 -user_company 客户名 -application_name 系统名"
    echo "  4. 生成报告 (SQL Server): ./fastdbchkrep.sh report -import_txt /data/HealthCheck.txt -mdout /md -company_name 鼎诚科技 -user_company 客户名 -application_name 系统名"
    echo "  5. 转换PDF: ./fastdbchkrep.sh htmltopdf -import_html /md/report.editable.html -pdfout /pdf -pdfname report"
}

# 显示parse命令帮助
show_parse_help() {
    echo "Parse命令 - 解析数据库元数据"
    echo ""
    echo "用法: ./fastdbchkrep.sh parse [选项]"
    echo ""
    echo "选项:"
    echo "  单机模式:"
    echo "    -import_dir <路径>        输入目录路径"
    echo "  "
    echo "  RAC模式:"
    echo "    -import_dir_1 <路径>      节点1输入目录"
    echo "    -import_dir_2 <路径>      节点2输入目录"
    echo "    -import_dir_3 <路径>      节点3输入目录（可选）"
    echo "    -import_dir_4 <路径>      节点4输入目录（可选）"
    echo "  "
    echo "  通用参数:"
    echo "    -dbtype <类型>            数据库类型 (oracle|mysql|postgresql|sqlserver)"
    echo "    -dbmodel <模型>           数据库模型 (one|rac)"
    echo "    -jsonout <路径>           JSON输出目录"
    echo "    --identifier <标识>       自定义标识符（可选）"
    echo "    --quiet                   静默模式"
    echo ""
    echo "示例:"
    echo "  # Oracle单机模式"
    echo "  ./fastdbchkrep.sh parse \\"
    echo "    -import_dir \"/data/hnkafka_oms_20250902\" \\"
    echo "    -dbtype oracle \\"
    echo "    -dbmodel one \\"
    echo "    -jsonout \"/data/json\""
    echo ""
    echo "  # Oracle RAC模式（2节点）"
    echo "  ./fastdbchkrep.sh parse \\"
    echo "    -import_dir_1 \"/data/node1_data\" \\"
    echo "    -import_dir_2 \"/data/node2_data\" \\"
    echo "    -dbtype oracle \\"
    echo "    -dbmodel rac \\"
    echo "    -jsonout \"/data/json\""
    echo ""
    echo "  # MySQL单机模式（当前仅生成JSON）"
    echo "  ./fastdbchkrep.sh parse \\"
    echo "    -import_dir \"/data/dbos_mysql_20250914\" \\"
    echo "    -dbtype mysql \\"
    echo "    -dbmodel one \\"
    echo "    -jsonout \"/data/json\""
}

# 显示report命令帮助
show_report_help() {
    echo "Report命令 - 生成巡检报告"
    echo ""
    echo "用法: ./fastdbchkrep.sh report [选项]"
    echo ""
    echo "必需参数（互斥）:"
    echo "  -import_json <文件>       输入的JSON元数据文件 (Oracle/MySQL)"
    echo "  -import_txt <文件>        输入的TXT巡检文件 (SQL Server)"
    echo "  注意：-import_json 和 -import_txt 互斥，只能提供一个"
    echo ""
    echo "其他必需参数:"
    echo "  -mdout <路径>             Markdown输出目录"
    echo "  -company_name <名称>      公司名称 (鼎诚科技|伟宏智能)"
    echo "  -user_company <名称>      客户单位名称"
    echo "  -application_name <名称>  应用系统名称"
    echo ""
    echo "可选参数:"
    echo "  -suptime <小时>           现场支持总时间（小时数）"
    echo "  -supname <姓名>           支持工程师姓名"
    echo "  --quiet                   静默模式"
    echo ""
    echo "示例:"
    echo "  # Oracle/MySQL (从 JSON)"
    echo "  ./fastdbchkrep.sh report \\"
    echo "    -import_json \"/data/json/oracle-one-hnkafka_oms.json\" \\"
    echo "    -mdout \"/data/md\" \\"
    echo "    -company_name \"鼎诚科技\" \\"
    echo "    -user_company \"海南电网\" \\"
    echo "    -application_name \"OMS调度系统\""
    echo ""
    echo "  # SQL Server (从 TXT)"
    echo "  ./fastdbchkrep.sh report \\"
    echo "    -import_txt \"/data/file/172.18.0.2-HealthCheck-20251023.txt\" \\"
    echo "    -mdout \"/data/md\" \\"
    echo "    -company_name \"鼎诚科技\" \\"
    echo "    -user_company \"海南电网\" \\"
    echo "    -application_name \"OMS调度系统\""
    echo ""
    echo "  # 包含工程师信息"
    echo "  ./fastdbchkrep.sh report \\"
    echo "    -import_json \"/data/json/oracle-one-hnkafka_oms.json\" \\"
    echo "    -mdout \"/data/md\" \\"
    echo "    -company_name \"鼎诚科技\" \\"
    echo "    -user_company \"海南电网\" \\"
    echo "    -application_name \"OMS调度系统\" \\"
    echo "    -suptime \"4\" \\"
    echo "    -supname \"王力\""
}

# 显示htmltopdf命令帮助
show_htmltopdf_help() {
    echo "HtmlToPdf命令 - 将HTML（可编辑版）转换为PDF"
    echo ""
    echo "用法: ./fastdbchkrep.sh htmltopdf [选项]"
    echo ""
    echo "必需参数:"
    echo "  -import_html <文件>      输入的HTML文件路径（建议使用 *.editable.html）"
    echo "  -pdfout <路径>            输出目录（保存PDF）"
    echo "  -pdfname <名称>           输出文件名（不含扩展名）"
    echo ""
    echo "说明:"
    echo "  编辑HTML时可在页面顶部使用工具条保存/加载JSON或导出最终HTML；"
    echo "  转PDF时会自动隐藏编辑UI，保留版式。"
    echo ""
    echo "示例:"
    echo "  ./fastdbchkrep.sh htmltopdf \\"
    echo "    -import_html \"/data/md/oracle/hnkafka_oms_20250902/hnkafka_oms.editable.html\" \\"
    echo "    -pdfout \"/data/pdf\" \\"
    echo "    -pdfname \"2025年第三季度_海南电网_OMS系统_数据库巡检报告\""
    echo ""
    echo "注意事项:"
    echo "  - 确保已安装Playwright和Chromium浏览器"
    echo "  - 首次使用请运行: playwright install chromium"
    echo "  - PDF采用A4纸张格式，适合打印"
}

# Parse命令处理
handle_parse() {
    local import_dir=""
    local import_dir_1=""
    local import_dir_2=""
    local import_dir_3=""
    local import_dir_4=""
    local dbtype=""
    local dbmodel=""
    local jsonout=""
    local quiet="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -import_dir)
                import_dir=$(normalize_path "$2")
                shift 2
                ;;
            -import_dir_1)
                import_dir_1=$(normalize_path "$2")
                shift 2
                ;;
            -import_dir_2)
                import_dir_2=$(normalize_path "$2")
                shift 2
                ;;
            -import_dir_3)
                import_dir_3=$(normalize_path "$2")
                shift 2
                ;;
            -import_dir_4)
                import_dir_4=$(normalize_path "$2")
                shift 2
                ;;
            -dbtype)
                dbtype="$2"
                shift 2
                ;;
            -dbmodel)
                dbmodel="$2"
                shift 2
                ;;
            -jsonout)
                jsonout=$(normalize_path "$2")
                shift 2
                ;;
            --quiet)
                quiet="true"
                shift
                ;;
            --help|-h)
                show_parse_help
                exit 0
                ;;
            *)
                echo "❌ 未知参数：$1"
                echo ""
                show_parse_help
                exit 1
                ;;
        esac
    done

    # 验证参数
    if ! validate_parse_params "$dbtype" "$dbmodel" "$import_dir" "$import_dir_1" "$import_dir_2" "$import_dir_3" "$import_dir_4" "$jsonout"; then
        exit 1
    fi

    # 构建Python参数
    local python_args=()
    python_args+=("-dbtype" "$dbtype")
    python_args+=("-dbmodel" "$dbmodel")
    python_args+=("-jsonout" "$jsonout")
    
    if [[ "$dbmodel" == "one" ]]; then
        python_args+=("-import_dir" "$import_dir")
    else
        python_args+=("-import_dir_1" "$import_dir_1")
        python_args+=("-import_dir_2" "$import_dir_2")
        if [[ -n "$import_dir_3" ]]; then
            python_args+=("-import_dir_3" "$import_dir_3")
        fi
        if [[ -n "$import_dir_4" ]]; then
            python_args+=("-import_dir_4" "$import_dir_4")
        fi
    fi

    if [[ "$quiet" == "true" ]]; then
        python_args+=("--quiet")
    fi

    # 执行Python脚本
    run_cli parse "${python_args[@]}"
}

# Report命令处理
handle_report() {
    local import_json=""
    local import_txt=""
    local mdout=""
    local company_name=""
    local user_company=""
    local application_name=""
    local suptime=""
    local supname=""
    local quiet="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -import_json)
                import_json="$2"
                shift 2
                ;;
            -import_txt)
                import_txt="$2"
                shift 2
                ;;
            -mdout)
                mdout=$(normalize_path "$2")
                shift 2
                ;;
            -company_name)
                company_name="$2"
                shift 2
                ;;
            -user_company)
                user_company="$2"
                shift 2
                ;;
            -application_name)
                application_name="$2"
                shift 2
                ;;
            -suptime)
                suptime="$2"
                shift 2
                ;;
            -supname)
                supname="$2"
                shift 2
                ;;
            --quiet)
                quiet="true"
                shift
                ;;
            --help|-h)
                show_report_help
                exit 0
                ;;
            *)
                echo "❌ 未知参数：$1"
                echo ""
                show_report_help
                exit 1
                ;;
        esac
    done

    # 验证互斥参数：-import_json 和 -import_txt 必须且只能提供一个
    if [[ -z "$import_json" && -z "$import_txt" ]]; then
        echo "❌ 错误：必须提供 -import_json 或 -import_txt 参数之一"
        echo ""
        show_report_help
        exit 1
    fi

    if [[ -n "$import_json" && -n "$import_txt" ]]; then
        echo "❌ 错误：-import_json 和 -import_txt 参数互斥，只能提供一个"
        echo ""
        show_report_help
        exit 1
    fi

    # 验证其他必需参数
    if ! validate_report_params "$mdout" "$company_name" "$user_company" "$application_name"; then
        exit 1
    fi

    # 构建Python参数
    local python_args=()

    # 根据输入类型添加参数
    if [[ -n "$import_json" ]]; then
        python_args+=("-import_json" "$import_json")
    else
        python_args+=("-import_txt" "$import_txt")
    fi

    python_args+=("-mdout" "$mdout")
    python_args+=("-company_name" "$company_name")
    python_args+=("-user_company" "$user_company")
    python_args+=("-application_name" "$application_name")

    # 添加可选参数（带验证）
    if [[ -n "$suptime" ]]; then
        # 验证suptime是否为有效数字
        if ! [[ "$suptime" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
            echo "⚠️ 警告：-suptime 参数值 '$suptime' 不是有效数字，将被忽略"
        else
            python_args+=("-suptime" "$suptime")
        fi
    fi

    if [[ -n "$supname" ]]; then
        # 验证supname长度（不应太长）
        if [[ ${#supname} -gt 50 ]]; then
            echo "⚠️ 警告：-supname 参数值过长（超过50个字符），将被截断"
            supname="${supname:0:50}"
        fi
        python_args+=("-supname" "$supname")
    fi

    if [[ "$quiet" == "true" ]]; then
        python_args+=("--quiet")
    fi

    # 执行Python脚本
    run_cli report "${python_args[@]}"
}

handle_htmltopdf() {
    local import_html=""
    local pdfout=""
    local pdfname=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -import_html)
                import_html="$(normalize_path "$2")"
                shift 2
                ;;
            -pdfout)
                pdfout="$(normalize_path "$2")"
                shift 2
                ;;
            -pdfname)
                pdfname="$2"
                shift 2
                ;;
            --help|-h)
                show_htmltopdf_help
                exit 0
                ;;
            *)
                echo "❌ 未知参数：$1"
                echo ""
                show_htmltopdf_help
                exit 1
                ;;
        esac
    done

    if [[ -z "$import_html" ]]; then
        echo "❌ 错误：-import_html 参数不能为空"
        exit 1
    fi
    if [[ -z "$pdfout" ]]; then
        echo "❌ 错误：-pdfout 参数不能为空"
        exit 1
    fi
    if [[ -z "$pdfname" ]]; then
        echo "❌ 错误：-pdfname 参数不能为空"
        exit 1
    fi

    if [[ ! -f "$import_html" ]]; then
        echo "❌ 错误：HTML文件不存在：$import_html"
        exit 1
    fi

    local parent_dir=$(dirname "$pdfout")
    if [[ ! -d "$parent_dir" ]]; then
        echo "❌ 错误：输出目录的父目录不存在：$parent_dir"
        exit 1
    fi

    echo "📄 开始转换HTML文档到PDF"
    echo "  输入文件: $import_html"
    echo "  输出目录: $pdfout"
    echo "  文件名称: $pdfname"

    run_cli htmltopdf \
        -import_html "$import_html" \
        -pdfout "$pdfout" \
        -pdfname "$pdfname"
}

# 检查Python环境
check_python() {
    if ! command -v "$__PY_BIN" &> /dev/null; then
        echo "❌ 错误：未找到python3，请先安装Python 3"
        exit 1
    fi
    
    # 检查Python版本（更安全的方式）
    local python_version
    python_version=$($__PY_BIN -c 'import sys; print(sys.version_info.major * 10 + sys.version_info.minor)' 2>/dev/null)
    
    if [[ -z "$python_version" ]]; then
        echo "⚠️ 警告：无法检测Python版本，继续执行..."
        return 0
    fi
    
    if [[ "$python_version" -lt 36 ]]; then
        local major=$((python_version / 10))
        local minor=$((python_version % 10))
        echo "❌ 错误：Python版本过低（${major}.${minor}），需要3.6或更高版本"
        exit 1
    fi
}

# 依赖检查（仅在report/htmltopdf前检查markdown存在）
check_dependencies_for_report() {
  # markdown仅在生成HTML时需要
  if ! "$__PY_BIN" -c 'import markdown' >/dev/null 2>&1; then
    echo "❌ 依赖缺失：未找到 Python 包 markdown"
    echo "   请先执行：source venv/bin/activate && pip install -r requirements.txt"
    exit 1
  fi
}

# 首选调用的CLI（优先打包后的二进制）
run_cli() {
  # 执行优先级：
  # 1. FASTDBCHKREP_BINARY 环境变量指定的二进制文件
  # 2. FASTDBCHKREP_BIN 环境变量（保持向后兼容）
  # 3. binary/fastdbchkrep/fastdbchkrep (新的默认位置)
  # 4. dist/fastdbchkrep/fastdbchkrep
  # 5. bin/fastdbchkrep
  # 6. 系统PATH中的fastdbchkrep
  # 7. 回退到源码方式 (python main.py)
  
  local self_dir="$PWD"
  
  # 检查新的FASTDBCHKREP_BINARY变量或默认binary目录
  if [[ -x "$FASTDBCHKREP_BINARY" ]]; then
    echo "🚀 使用二进制文件: $FASTDBCHKREP_BINARY"
    "$FASTDBCHKREP_BINARY" "$@"
  elif [[ -n "$FASTDBCHKREP_BIN" ]] && [[ -x "$FASTDBCHKREP_BIN" ]]; then
    "$FASTDBCHKREP_BIN" "$@"
  elif [[ -x "$self_dir/binary/fastdbchkrep/fastdbchkrep" ]]; then
    echo "🚀 使用二进制文件: $self_dir/binary/fastdbchkrep/fastdbchkrep"
    "$self_dir/binary/fastdbchkrep/fastdbchkrep" "$@"
  elif [[ -x "$self_dir/dist/fastdbchkrep/fastdbchkrep" ]]; then
    "$self_dir/dist/fastdbchkrep/fastdbchkrep" "$@"
  elif [[ -x "$self_dir/bin/fastdbchkrep" && ! -d "$self_dir/bin/fastdbchkrep" ]]; then
    "$self_dir/bin/fastdbchkrep" "$@"
  elif command -v fastdbchkrep >/dev/null 2>&1; then
    fastdbchkrep "$@"
  else
    # 回退到源码方式
    echo "📝 使用源码方式运行"
    check_python
    python3 main.py "$@"
  fi
}

# 主逻辑
# 检查是否有可用的二进制文件
BINARY_AVAILABLE=false
if [[ -x "$FASTDBCHKREP_BINARY" ]] || [[ -x "$PWD/binary/fastdbchkrep/fastdbchkrep" ]]; then
    BINARY_AVAILABLE=true
fi

# 如果有二进制文件，直接使用二进制文件处理所有命令
if [[ "$BINARY_AVAILABLE" == "true" ]]; then
    # 直接调用run_cli，它会自动选择合适的执行方式
    run_cli "$@"
else
    # 没有二进制文件时，使用源码方式
    check_python
    
    # 处理命令
    case "$1" in
        "parse")
            shift
            handle_parse "$@"
            ;;
        "report")
            shift
            check_dependencies_for_report
            handle_report "$@"
            ;;
        "htmltopdf")
            shift
            # htmltopdf基于现有HTML，通常不需要markdown；无需强检
            handle_htmltopdf "$@"
            ;;
        "help"|"-h"|"--help"|"")
            show_help
            ;;
        *)
            echo "❌ 未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
fi
