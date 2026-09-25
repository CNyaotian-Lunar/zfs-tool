#!/usr/bin/env bash
#
# ================================================================
# zfs-tool v4.0
#
# ZFS 运维管理工具箱
#
# 支持:
#   1  Dashboard            11  Dataset Analyzer
#   2  ARC / L2ARC          12  Version
#   3  Health Check         13  Progress(活动进度)
#   4  I/O Monitor          14  Encryption(加密管理)
#   5  Snapshot Manager     15  Pool Manager(池/磁盘)
#   6  Scrub                16  Dataset Manager(数据集管理)
#   7  TRIM                 17  Alerts(告警检查)
#   8  Fragmentation        18  Doctor(自检)
#   9  Dedup                19  History(历史/日志)
#   10 SMART                0   Exit
#
#   Snapshot Manager 内含: 查看/创建/按天清理/保留清理/
#                          diff 对比/rollback 回滚/send·recv 备份
#   SMART 内含: 温度健康 / 短长自检 / 自检日志 / 整体健康
#
# Target:
#   TrueNAS SCALE
#   OpenZFS Linux
#
# 用法:
#   ./zfs-tool.sh            交互菜单
#   ./zfs-tool.sh <command>  直接执行某项功能
#   ./zfs-tool.sh help       查看可用命令
#   ./zfs-tool.sh <command> [-p pool] [-d dataset]
#                           常用功能支持预填池/数据集, 便于脚本化
#   例如: zfs-tool.sh alerts -p tank   /   zfs-tool.sh scrub -p tank
#
# v3.0 -> v4.0 新增/变更:
#   * 新增: 快照 diff 对比、rollback 回滚(强确认)、保留清理(按份数)
#   * 新增: zfs send/recv 备份向导(本地/SSH 远程、全量/增量)
#   * 新增: 加密管理(状态/加载/卸载/更换密钥)
#   * 新增: Pool Manager(vdev 拓扑、导出/导入、磁盘信息、换盘指引)
#   * 新增: Dataset Manager(创建/删除/属性向导/配额/zvol)
#   * 新增: Alerts 阈值告警(容量/碎片/Scrub 过期/错误计数), 可挂 cron
#   * 新增: Progress 活动进度、Doctor 自检、History(zpool history/cron)
#   * 新增: SMART 自检(short/long)与自检日志
#   * 新增: CLI 参数 -p/--pool、-d/--dataset 预填目标
#   * 增强: Dashboard 顶部显示当前告警摘要
#   * 破坏性操作统一"双重确认"护栏
# ================================================================

# 刻意不启用 set -euo pipefail:
# 脚本面向"命令缺失/设备离线"常态, 大量管道期望静默降级,
# 严格模式反而会让某个 smartctl 设备异常把整屏搞崩。
# 依赖处通过显式校验 + || true 处理。

VERSION="4.0"

# ================================================================
# Config
# ================================================================
LOG_DIR="${LOG_DIR:-<NAS数据盘>/1000/logs/zfs-tools}"
LOG_FILE="$LOG_DIR/zfs-tool.log"
LOG_MAX=$((1024*1024))            # 1 MiB 轮转阈值
ARCSTATS_FILE=/proc/spl/kstat/zfs/arcstats

# CLI 参数 -p/--pool -d/--dataset 提供的目标(交互菜单中为空)
TARGET_POOL=""
TARGET_DS=""

# ================================================================
# Colors
# ================================================================
if [[ -t 1 && "$TERM" != "dumb" ]]; then
    RESET='\033[0m'
    RED='\033[1;31m'
    GREEN='\033[1;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[1;34m'
    CYAN='\033[1;36m'
    WHITE='\033[1;37m'
else
    RESET=''; RED=''; GREEN=''; YELLOW=''
    BLUE=''; CYAN=''; WHITE=''
fi

LINE="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LINE_SHORT="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ================================================================
# Common Functions
# ================================================================

log()
{
    mkdir -p "$LOG_DIR" 2>/dev/null || return 0
    if [[ -f "$LOG_FILE" ]]; then
        local size
        size=$(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0)
        if (( size > LOG_MAX )); then
            mv -f "$LOG_FILE" "$LOG_FILE.old" 2>/dev/null || true
        fi
    fi
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

pause()
{
    read -rp "按 Enter 返回..."
}

title()
{
    clear
    printf '%b%s\n%b%s\n' "$CYAN" "$LINE" "$WHITE" "$1"
    if [[ -n "${2:-}" ]]; then
        printf '%b%s%b\n' "$YELLOW" "$2" "$RESET"
    fi
    printf '%b%s\n%b\n' "$CYAN" "$LINE" "$RESET"
}

is_num()
{
    [[ "$1" =~ ^[0-9]+$ ]]
}

command_exists()
{
    command -v "$1" >/dev/null 2>&1
}

require_root()
{
    if [[ "$EUID" -ne 0 ]]; then
        echo -e "${RED}需要 root 权限${RESET}"
        exit 1
    fi
}

check_zfs()
{
    if ! command_exists zpool; then
        echo -e "${RED}未找到 zpool, 请确认运行环境为 TrueNAS/OpenZFS${RESET}"
        exit 1
    fi
    if ! command_exists zfs; then
        echo -e "${RED}未找到 zfs 命令${RESET}"
        exit 1
    fi
}

pool_exists()
{
    [[ -n "$1" ]] && zpool list "$1" >/dev/null 2>&1
}

dataset_exists()
{
    zfs list "$1" >/dev/null 2>&1
}

# 池名列表(无池时为空数组)
pool_names()
{
    zpool list -H -o name 2>/dev/null
}

# 交互输入 Pool 名并校验, 成功返回 0 且全局 POOL 有值。
# 优先用启动扫描的列表做字母/数字快捷选择; 也允许直接输入名称。
ask_pool()
{
    local prompt="${1:-Pool名称}" n
    POOL=""

    # CLI -p 预填
    if [[ -n "$TARGET_POOL" ]]; then
        if pool_exists "$TARGET_POOL"; then
            POOL="$TARGET_POOL"
            echo "使用 Pool: $POOL"
            return 0
        fi
        echo -e "${RED}Pool 不存在: $TARGET_POOL${RESET}"
        return 1
    fi

    refresh_pool_index
    n=${#POOLS_AVAILABLE[@]}
    if (( n == 0 )); then
        echo -e "${RED}系统中没有任何 Pool${RESET}"
        return 1
    fi

    # 只有一个池时自动选择, 免交互
    if (( n == 1 )); then
        POOL="${POOLS_AVAILABLE[0]}"
        echo -e "${CYAN}仅一个 Pool, 自动选择:${RESET} $POOL"
        return 0
    fi

    local blob
    blob=$(printf '%s\n' "${POOLS_AVAILABLE[@]}")
    if ! pick_from_list "$prompt" "$blob"; then
        return 1
    fi

    if [[ -n "$PICK_RES" ]]; then
        POOL="$PICK_RES"
    else
        # 直接输入的名称
        if pool_exists "$PICK_RAW"; then
            POOL="$PICK_RAW"
        else
            echo -e "${RED}Pool 不存在: $PICK_RAW${RESET}"
            return 1
        fi
    fi
    echo -e "${CYAN}已选择 Pool:${RESET} $POOL"
    return 0
}

# 交互输入 Dataset 并校验, 成功返回 0 且全局 DS 有值。
# 支持: 直接输入完整名 / 回车浏览顶层数据集(A/B/C..)后逐级下钻子路径。
ask_dataset()
{
    local prompt="${1:-选择数据集}" ans sub cand
    DS=""

    # CLI -d 预填
    if [[ -n "$TARGET_DS" ]]; then
        if dataset_exists "$TARGET_DS"; then
            DS="$TARGET_DS"
            echo "使用 Dataset: $DS"
            return 0
        fi
        echo -e "${RED}数据集不存在: $TARGET_DS${RESET}"
        return 1
    fi

    # 快速路径: 直接输入完整数据集名
    read -rp "${prompt} [输入完整名, 或回车浏览]: " ans
    if [[ -n "$ans" ]]; then
        if dataset_exists "$ans"; then
            DS="$ans"
            return 0
        fi
        echo -e "${RED}数据集不存在: $ans${RESET}"
        return 1
    fi

    # 浏览模式: 先选顶层数据集
    local blob
    blob=$(zfs list -H -o name -t filesystem,volume 2>/dev/null)
    if [[ -z "$blob" ]]; then
        echo -e "${RED}系统中没有任何数据集${RESET}"
        return 1
    fi
    if ! pick_from_list "顶层数据集" "$blob"; then
        return 1
    fi

    if [[ -n "$PICK_RES" ]]; then
        DS="$PICK_RES"
    else
        if dataset_exists "$PICK_RAW"; then
            DS="$PICK_RAW"
        else
            echo -e "${RED}数据集不存在: $PICK_RAW${RESET}"
            return 1
        fi
    fi
    echo -e "${CYAN}已选择:${RESET} $DS"

    # 逐级下钻子路径, 直到用户回车确认当前选择
    while true; do
        read -rp "继续下钻子路径 [如 vm/win; 回车=使用当前 $DS]: " sub
        [[ -z "$sub" ]] && break
        sub="${sub#/}"
        cand="$DS/$sub"
        if dataset_exists "$cand"; then
            DS="$cand"
            echo -e "${CYAN}→${RESET} $DS"
        else
            echo -e "${YELLOW}子路径不存在: $cand (仍停留在 $DS)${RESET}"
        fi
    done
    return 0
}

confirm_yes()
{
    local ans
    read -rp "${1:-确认执行? (yes): }" ans
    [[ "$ans" == "yes" ]]
}

# 健康状态 -> 彩色圆点
health_icon()
{
    case "$1" in
        ONLINE)   printf '%b●%b' "$GREEN" "$RESET" ;;
        DEGRADED) printf '%b●%b' "$YELLOW" "$RESET" ;;
        *)        printf '%b●%b' "$RED" "$RESET" ;;
    esac
}

# 字节数(整数) -> GiB 字符串
human_gib()
{
    awk -v b="$1" 'BEGIN{printf "%.2f", b/1024/1024/1024}'
}

# 命中率; 样本不足时输出 N/A
hit_rate()
{
    local h=${1:-0} m=${2:-0}
    if (( h + m > 0 )); then
        awk -v h="$h" -v m="$m" 'BEGIN{printf "%.2f%%", h*100/(h+m)}'
    else
        printf 'N/A'
    fi
}

# ================================================================
# v4.0 Common Extras
# ================================================================

# 破坏性操作双重确认: 需要连续回答两次 yes
confirm_destructive()
{
    local desc="${1:-此操作}"
    echo
    echo -e "${RED}⚠ 即将执行: $desc${RESET}"
    echo -e "${RED}⚠ 此操作可能造成数据丢失, 且不可恢复!${RESET}"
    confirm_yes "第一次确认 (输入 yes): " || return 1
    confirm_yes "第二次确认 (再输入 yes): " || return 1
    return 0
}

# ---------------- 字母快捷选择 ----------------

ABC_LIST=({A..Z})          # 选择列表字母表
POOLS_AVAILABLE=()         # 启动/刷新时扫描到的池名缓存
PICK_IDX=-1                # 列表选择结果索引
PICK_RES=""                # 列表选择结果内容(或原样输入)
PICK_RAW=""                # 未命中索引时的原始输入

# 启动与每次选择前刷新池列表缓存
refresh_pool_index()
{
    POOLS_AVAILABLE=()
    mapfile -t POOLS_AVAILABLE < <(pool_names)
}

# 字母/数字 -> 索引, 失败返回 -1 (写回 PICK_IDX)
sel_to_index()
{
    local s="${1^^}" i
    PICK_IDX=-1
    if [[ "$s" =~ ^[A-Z]$ ]]; then
        for (( i = 0; i < 26; i++ )); do
            if [[ "$s" == "${ABC_LIST[$i]}" ]]; then
                PICK_IDX=$i
                return 0
            fi
        done
    elif is_num "$s"; then
        PICK_IDX=$((10#$s - 1))
    fi
}

# 通用字母列表选择: 用 A/B/C.. 或数字代替手输名称
# $1=标题  $2=条目(换行分隔)
# 成功返回 0; 结果在 PICK_RES(命中)或 PICK_RAW(需要调用方自行校验)
pick_from_list()
{
    local title="$1" blob="$2" n=0 i sel
    local -a items=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && items+=("$line")
    done <<< "$blob"

    n=${#items[@]}
    PICK_RES=""
    PICK_RAW=""

    if (( n == 0 )); then
        echo -e "${RED}没有可选项目${RESET}"
        return 1
    fi
    if (( n == 1 )); then
        PICK_RES="${items[0]}"
        return 0
    fi

    echo
    echo -e "${YELLOW}$title (共 $n 个):${RESET}"
    for (( i = 0; i < n && i < 26; i++ )); do
        printf '   %s) %s\n' "${ABC_LIST[$i]}" "${items[i]}"
    done
    if (( n > 26 )); then
        echo "   (项目超过 26 个, 其余请直接输入名称)"
    fi
    echo
    read -rp "选择 [字母/数字] 或直接输入名称(回车取消): " sel
    [[ -z "$sel" ]] && { echo -e "${YELLOW}已取消${RESET}"; return 1; }

    sel_to_index "$sel"
    if (( PICK_IDX >= 0 && PICK_IDX < n )); then
        PICK_RES="${items[$PICK_IDX]}"
    elif [[ "$sel" =~ ^[A-Za-z0-9]+$ ]]; then
        echo -e "${RED}选择超出范围 (1-$n)${RESET}"
        return 1
    else
        PICK_RAW="$sel"          # 原样交给调用方校验(如直接输入的池名)
    fi
    return 0
}

# 列出某 dataset 下全部快照名(按创建时间从新到旧)
snap_names()
{
    zfs list -H -t snapshot -r "$1" -o name -S creation 2>/dev/null
}

# 批量销毁快照: $1 = 换行分隔的快照名单(自动分批, 每批 100)
destroy_snaps_list()
{
    local line n=0 batch=()
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        batch+=("$line")
        if (( ${#batch[@]} % 100 == 0 )); then
            zfs destroy "${batch[@]}" 2>/dev/null
            n=$((n + ${#batch[@]}))
            batch=()
        fi
    done <<< "$1"
    if (( ${#batch[@]} > 0 )); then
        zfs destroy "${batch[@]}" 2>/dev/null
        n=$((n + ${#batch[@]}))
    fi
    echo "$n"
}

# 交互选择快照(基于上屏已打印的列表), 输入序号或全名
# $1=dataset; 返回 0 且 SNAP 为完整快照名
pick_snapshot()
{
    local ds="$1" list n i sel snap
    local -a names
    mapfile -t names < <(snap_names "$ds")
    n=${#names[@]}
    if (( n == 0 )); then
        echo -e "${YELLOW}该数据集没有任何快照${RESET}"
        return 1
    fi

    echo
    echo "最近快照 (最多 15 条):"
    for (( i = 0; i < n && i < 15; i++ )); do
        printf '  %2d) %s\n' "$((i + 1))" "${names[i]}"
    done
    echo
    read -rp "输入序号或完整快照名: " sel

    if is_num "$sel"; then
        local idx=$((sel - 1))
        if (( idx >= 0 && idx < n )); then
            SNAP="${names[idx]}"
            return 0
        fi
        echo -e "${RED}序号超出范围${RESET}"
        return 1
    fi

    # 输入了名字: 允许只输 "dataset@xxx" 或纯快照名补全
    if [[ "$sel" == *"@"* ]]; then
        if [[ "$sel" == "${ds}@"* ]]; then
            SNAP="$sel"
            return 0
        fi
        # 用户可能给了别的 dataset 前缀, 校验存在
        if dataset_exists "$sel"; then
            SNAP="$sel"
            return 0
        fi
    elif [[ -n "$sel" ]]; then
        local cand="${ds}@${sel}"
        if dataset_exists "$cand"; then
            SNAP="$cand"
            return 0
        fi
    fi
    echo -e "${RED}快照不存在: $sel${RESET}"
    return 1
}

# 计算某池最近一次 Scrub 距今的天数(活动中的返回 0, 解析失败返回空)
scrub_age_days()
{
    local pool="$1" scanline ts epoch now age
    scanline=$(zpool status "$pool" 2>/dev/null | grep "scan:" | head -1)
    [[ -n "$scanline" ]] || return 1
    [[ "$scanline" == *"in progress"* ]] && { echo 0; return 0; }
    ts=${scanline##* on }
    ts=$(echo "$ts" | xargs)                     # 去首尾空白
    epoch=$(LC_ALL=C date -d "$ts" +%s 2>/dev/null) || return 1
    now=$(date +%s)
    age=$(((now - epoch) / 86400))
    (( age >= 0 )) && echo "$age" || echo 0
}

# ================================================================
# ARC stats (单次读取)
# ================================================================

# 一次 grep 读出全部关心的 arcstats 键值到全局关联数组 ARC
load_arc()
{
    local k t v
    declare -gA ARC=()
    while read -r k t v; do
        ARC[$k]=$v
    done < <(grep -E \
        '^(size|c_max|c|hits|misses|l2_hits|l2_misses|l2_size|l2_asize|mfu_size|mru_size|metadata_size)[[:space:]]' \
        "$ARCSTATS_FILE" 2>/dev/null)

    for k in size c_max c hits misses l2_hits l2_misses \
             l2_size l2_asize mfu_size mru_size metadata_size; do
        [[ -n "${ARC[$k]:-}" ]] || ARC[$k]=0
    done
}

# 单池 IO 速率快照, 输出 "读 MB/s / 写 MB/s"
pool_io()
{
    zpool iostat -p -y "$1" 1 1 2>/dev/null | tail -1 | \
        awk '{printf "Read  : %.2f MB/s\nWrite : %.2f MB/s\n", $4/1024/1024, $5/1024/1024}'
}

# ================================================================
# SMART
# ================================================================

# 取某个磁盘的当前温度(整数)。smartctl -A 属性行尾可能带
# "(Min/Max 24/36)" 等括号注释, 因此只取第一个 "(" 之前的
# 最后一个纯数字字段, 避免抓错。
smart_temperature()
{
    local dev="$1"; shift
    smartctl -A "$dev" "$@" 2>/dev/null | awk '
        /Temperature_Celsius|Airflow_Temperature_Cel|Composite Temperature|Temperature:/ {
            line = $0
            sub(/\(.*/, "", line)          # 去掉括号注释
            n = split(line, a, " ")
            for (i = n; i >= 1; i--)
                if (a[i] ~ /^[0-9]+$/) { print a[i]; exit }
        }'
}

# smartctl --scan-open 的可用设备行列表(干净化, 去注释)
smart_devices()
{
    smartctl --scan-open 2>/dev/null | while read -r dev rest; do
        [[ -z "$dev" || "$dev" == \#* ]] && continue
        rest=${rest%%#*}
        read -ra smart_args <<< "$rest"
        printf '%s\t' "$dev"
        printf '%s ' "${smart_args[@]}"
        printf '\n'
    done
}

# ================================================================
# Dashboard
# ================================================================

cpu_usage()
{
    if command_exists mpstat; then
        mpstat 1 1 | awk '/Average/ && /all/ {printf "%.1f%% used", 100-$NF}'
    else
        # top 的 idle 字段形如 "95.5 id,", 需要剥离逗号再算
        top -bn1 | awk '
            /Cpu\(s\)/{
                for (i = 1; i <= NF; i++)
                    if ($i ~ /id/) {
                        v = $i
                        gsub(/[^0-9.]/, "", v)
                        if (v != "") { printf "%.1f%% used", 100 - v; exit }
                    }
            }'
    fi
}

cmd_dashboard()
{
    title "📊 ZFS Dashboard v$VERSION" "系统 / Pool / ARC / IO / 磁盘温度 / 当前告警一目了然"
    echo

    local pools
    mapfile -t pools < <(pool_names)

    # ---------------- System ----------------
    echo -e "${WHITE}🖥 System${RESET}"
    printf '%-10s %s\n' "Hostname:" "$(hostname)"
    printf '%-10s %s\n' "Kernel:"   "$(uname -r)"
    printf '%-10s %s\n' "Uptime:"   "$(uptime -p)"
    printf '%-10s %s\n' "CPU:"      "$(cpu_usage)"
    printf '%-10s %s\n' "Memory:"   "$(free -h | awk '/Mem:/{print $3" / "$2}')"

    # ---------------- 告警摘要 ----------------
    alerts_collect
    if (( NALERTS > 0 )); then
        echo
        echo -e "${WHITE}⚠ Alert Summary${RESET}"
        local ai
        for (( ai = 0; ai < NALERTS && ai < 4; ai++ )); do
            paint_alert_line "$ai"
        done
        if (( NALERTS > 4 )); then
            echo "  ... 共 $NALERTS 条, 请用菜单 17 / alerts 查看全部"
        fi
    fi
    echo

    # ---------------- Pool ----------------
    echo -e "${WHITE}🗄 ZFS Pool${RESET}"
    if (( ${#pools[@]} == 0 )); then
        echo "  无 Pool"
    else
        while read -r pname health alloc size cap frag dedup; do
            printf '\n%s\n' "$pname"
            printf 'Health : %b %s\n' "$(health_icon "$health")" "$health"
            printf 'Used   : %s\nSize   : %s\nUsage  : %s\n' "$alloc" "$size" "$cap"
            printf 'Frag   : %s\nDedup  : %s\n' "$frag" "$dedup"
        done < <(zpool list -H -o name,health,alloc,size,cap,frag,dedup 2>/dev/null)
    fi
    echo

    # ---------------- ARC ----------------
    echo -e "${WHITE}💾 ARC Cache${RESET}"
    if [[ -f "$ARCSTATS_FILE" ]]; then
        load_arc
        printf 'ARC      : %s GiB / %s GiB\n' \
            "$(human_gib "${ARC[size]}")" "$(human_gib "${ARC[c_max]}")"
        printf 'Hit Ratio: %s\n' "$(hit_rate "${ARC[hits]}" "${ARC[misses]}")"
        if (( ARC[l2_size] > 0 )); then
            printf 'L2ARC    : %s GiB, 命中 %s\n' \
                "$(human_gib "${ARC[l2_size]}")" \
                "$(hit_rate "${ARC[l2_hits]}" "${ARC[l2_misses]}")"
        fi
        echo
        echo -e "${WHITE}🧠 ARC Breakdown${RESET}"
        printf 'MFU      : %s GiB\n' "$(human_gib "${ARC[mfu_size]}")"
        printf 'MRU      : %s GiB\n' "$(human_gib "${ARC[mru_size]}")"
        printf 'Metadata : %s GiB\n' "$(human_gib "${ARC[metadata_size]}")"
    else
        echo "ARC unavailable"
    fi
    echo

    # ---------------- IO ----------------
    echo -e "${WHITE}📈 IO Snapshot${RESET}"
    if (( ${#pools[@]} == 0 )); then
        echo "  无 Pool"
    else
        for pname in "${pools[@]}"; do
            printf '\n%s\n' "$pname"
            pool_io "$pname" || echo "  N/A"
        done
    fi
    echo

    # ---------------- Disk Temp ----------------
    echo -e "${WHITE}🌡 Disk Temperature${RESET}"
    if command_exists smartctl; then
        local dev args temp sa
        while IFS=$'\t' read -r dev args; do
            [[ -z "$dev" ]] && continue
            read -ra sa <<< "$args"
            temp=$(smart_temperature "$dev" "${sa[@]}")
            if is_num "$temp"; then
                echo "$dev : ${temp}℃"
            else
                echo "$dev : N/A"
            fi
        done < <(smart_devices)
    else
        echo "smartctl unavailable"
    fi
    echo
}

# ================================================================
# Main Menu
# ================================================================

main_menu()
{
    while true; do
        title "🧰 ZFS TOOLBOX v$VERSION"
        echo
        printf ' %-2s %-22s %s\n' "1." "📊 Dashboard"          "10. 💽 SMART"
        printf ' %-2s %-22s %s\n' "2." "💾 ARC / L2ARC"         "11. 📂 Dataset Analyzer"
        printf ' %-2s %-22s %s\n' "3." "❤️  Health Check"      "12. ℹ Version"
        printf ' %-2s %-22s %s\n' "4." "📈 I/O Monitor"         "13. ⏳ Progress 进度"
        printf ' %-2s %-22s %s\n' "5." "📸 Snapshot Manager"   "14. 🔐 Encryption 加密"
        printf ' %-2s %-22s %s\n' "6." "🧹 Scrub"               "15. 🗄 Pool Manager"
        printf ' %-2s %-22s %s\n' "7." "✂ TRIM"                "16. 📁 Dataset Manager"
        printf ' %-2s %-22s %s\n' "8." "📉 Fragmentation"       "17. 🚨 Alerts 告警"
        printf ' %-2s %-22s %s\n' "9." "🗜 Dedup"               "18. 🩺 Doctor 自检"
        echo "                         19. 📜 History 历史"
        echo
        echo " 0. Exit           h/? 帮助"
        echo
        read -rp "选择功能: " choice

        case "$choice" in
            1)  cmd_dashboard ;;
            2)  cmd_arc ;;
            3)  cmd_health ;;
            4)  cmd_iostat ;;
            5)  cmd_snapshot ;;
            6)  cmd_scrub ;;
            7)  cmd_trim ;;
            8)  cmd_frag ;;
            9)  cmd_dedup ;;
            10) cmd_smart ;;
            11) cmd_dataset ;;
            12) cmd_version ;;
            13) cmd_progress ;;
            14) cmd_encrypt ;;
            15) cmd_poolmgr ;;
            16) cmd_dsmgr ;;
            17) cmd_alerts ;;
            18) cmd_doctor ;;
            19) cmd_hist ;;
            h|H|\?|help)
                clear
                usage
                pause
                ;;
            0)  exit 0 ;;
            *)  echo "无效选择"; sleep 1 ;;
        esac
    done
}

# ================================================================
# ARC / L2ARC Monitor
# ================================================================

# 绘制一屏 ARC 信息(供单次与实时刷新共用)
paint_arc()
{
    load_arc
    printf '\nARC: %s GiB / %s GiB\n\n' \
        "$(human_gib "${ARC[size]}")" "$(human_gib "${ARC[c_max]}")"

    local rate
    rate=$(hit_rate "${ARC[hits]}" "${ARC[misses]}")
    if [[ "$rate" == "N/A" ]]; then
        echo "ARC Hit : N/A"
    else
        echo -e "ARC Hit : ${GREEN}${rate}${RESET}"
    fi

    rate=$(hit_rate "${ARC[l2_hits]}" "${ARC[l2_misses]}")
    if [[ "$rate" == "N/A" ]]; then
        echo "L2ARC Hit : N/A"
    else
        echo -e "L2ARC Hit : ${CYAN}${rate}${RESET}"
    fi

    echo
    echo "ARC Breakdown:"
    printf 'MFU %.2f GiB\nMRU %.2f GiB\n' \
        "$(human_gib "${ARC[mfu_size]}")" "$(human_gib "${ARC[mru_size]}")"
}

cmd_arc()
{
    title "💾 ARC / L2ARC Cache" "查看 ARC/L2 命中率与分布, 可实时刷新 (Ctrl+C 返回)"

    if [[ ! -f "$ARCSTATS_FILE" ]]; then
        echo -e "${RED}未找到 arcstats${RESET}"
        pause
        return
    fi

    paint_arc

    echo
    read -rp "实时刷新? (y/N): " watch
    if [[ "$watch" =~ ^[Yy]$ ]]; then
        echo "Ctrl+C 返回菜单"
        trap 'break' INT
        while true; do
            clear
            printf '%bZFS ARC Monitor %s%b\n' "$WHITE" "$(date '+%F %T')" "$RESET"
            paint_arc
            sleep 2
        done
        trap - INT
    fi
    pause
}

# ================================================================
# Health Check
# ================================================================

cmd_health()
{
    title "❤️ ZFS Health Check" "遍历所有 Pool: 健康状态 / 容量 / 设备错误 / 最近 Scrub"
    local pools pname health
    mapfile -t pools < <(pool_names)

    if (( ${#pools[@]} == 0 )); then
        echo "无 Pool"
        pause
        return
    fi

    for pname in "${pools[@]}"; do
        echo -e "${CYAN}${LINE_SHORT}${RESET}"
        echo "Pool: $pname"

        health=$(zpool get -H -o value health "$pname")
        case "$health" in
            ONLINE)   echo -e "Status: ${GREEN}$health${RESET}" ;;
            DEGRADED) echo -e "Status: ${YELLOW}$health${RESET}" ;;
            *)        echo -e "Status: ${RED}$health${RESET}" ;;
        esac

        echo
        echo "容量:"
        zpool list "$pname" -o name,size,alloc,free,cap,frag
        echo

        # vdev 错误统计: 状态非 ONLINE, 或 READ/WRITE/CKSUM 任一非零
        echo "设备错误:"
        zpool status "$pname" | awk '
            $1 == "NAME" { next }
            NF >= 5 && $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ && $5 ~ /^[0-9]+$/ {
                if (($3 + $4 + $5) > 0 || $2 != "ONLINE") {
                    printf "  %-16s %-9s READ=%s WRITE=%s CKSUM=%s\n", $1, $2, $3, $4, $5
                    shown = 1
                }
            }
            END { if (!shown) print "  无错误" }'
        echo

        echo "Scrub:"
        zpool status "$pname" | grep "scan:" || echo "  无记录"
        echo
    done

    pause
}

# ================================================================
# I/O Monitor
# ================================================================

cmd_iostat()
{
    title "📈 ZFS I/O Monitor" "按设定秒数持续刷新全池读写速率 (Ctrl+C 返回)"
    echo
    echo "刷新间隔默认 2 秒"
    read -rp "输入间隔秒数: " interval
    interval=${interval:-2}

    if ! is_num "$interval" || (( interval < 1 )); then
        echo -e "${RED}请输入正整数秒数${RESET}"
        pause
        return
    fi

    echo
    echo "Ctrl+C 返回菜单"

    trap 'break' INT
    while true; do
        clear
        printf '%bZFS I/O %s%b\n' "$WHITE" "$(date '+%F %T')" "$RESET"
        zpool iostat -p "$interval" 1
    done
    trap - INT
}

# ================================================================
# Snapshot Manager
# ================================================================

snap_list()
{
    local ds
    if ! ask_dataset; then
        return
    fi

    echo
    zfs list -t snapshot -r "$DS" -o name,creation,used
}

snap_create()
{
    local ds name
    if ! ask_dataset; then
        return
    fi

    name="${DS}@manual_$(date +%Y%m%d_%H%M%S)"
    if zfs snapshot "$name"; then
        echo -e "${GREEN}创建成功:${RESET} $name"
        log "snapshot create $name"
    else
        echo -e "${RED}创建失败: $name${RESET}"
    fi
}

snap_prune()
{
    local days limit snaps name epoch n i batch done_count
    if ! ask_dataset; then
        return
    fi

    read -rp "删除多少天以前的快照: " days
    if ! is_num "$days"; then
        echo -e "${RED}请输入数字${RESET}"
        return
    fi

    limit=$(date -d "-$days day" +%s)

    # 收集符合条件的快照(creation 为 epoch, 避免 locale 问题)
    mapfile -t snaps < <(
        zfs list -Hp -t snapshot -r "$DS" -o name,creation 2>/dev/null |
        while IFS=$'\t' read -r name epoch; do
            if is_num "$epoch" && (( epoch < limit )); then
                printf '%s\n' "$name"
            fi
        done
    )

    n=${#snaps[@]}
    if (( n == 0 )); then
        echo "没有可删除的旧快照"
        return
    fi

    echo
    echo "准备删除 $n 个快照:"
    for (( i = 0; i < n; i++ )); do
        printf '  %s\n' "${snaps[i]}"
    done
    echo
    echo -e "${RED}⚠ 删除不可恢复${RESET}"
    if ! confirm_yes "确认删除? (yes): "; then
        echo "取消"
        return
    fi

    # 分批 destroy, 避免单条命令行过长
    batch=(); done_count=0
    for (( i = 0; i < n; i++ )); do
        batch+=("${snaps[i]}")
        if (( ${#batch[@]} % 100 == 0 )); then
            zfs destroy "${batch[@]}" 2>/dev/null
            done_count=$((done_count + ${#batch[@]}))
            batch=()
        fi
    done
    if (( ${#batch[@]} > 0 )); then
        zfs destroy "${batch[@]}" 2>/dev/null
        done_count=$((done_count + ${#batch[@]}))
    fi

    echo -e "${GREEN}已删除 $done_count 个快照${RESET}"
    log "snapshot prune $DS $days days: $done_count removed"
}

# 保留清理: 同一数据集/同一前缀下只保留最近 N 份快照
snap_keep()
{
    local ds pattern keep n i name
    local -a names dels
    local deltext

    if ! ask_dataset; then
        return
    fi

    read -rp "只处理名称含此前缀的快照(回车=全部): " pattern
    read -rp "保留最近多少份: " keep
    if ! is_num "$keep" || (( keep < 1 )); then
        echo -e "${RED}保留数量必须是 >=1 的整数${RESET}"
        return
    fi

    # 最新在前, 越过前 keep 份, 剩下的就是候选
    mapfile -t names < <(snap_names "$DS" | grep -F "${pattern}")
    n=${#names[@]}
    if (( n <= keep )); then
        echo "快照数量($n)未超过保留数($keep), 无需清理"
        return
    fi

    dels=()
    for (( i = keep; i < n; i++ )); do
        dels+=("${names[i]}")
    done

    echo
    echo "将删除 ${#dels[@]} 个快照 (保留最近 $keep 份, 前缀 '$pattern'):"
    for name in "${dels[@]}"; do
        printf '  %s\n' "$name"
    done
    echo
    echo -e "${RED}⚠ 删除不可恢复${RESET}"
    if ! confirm_yes "确认删除? (yes): "; then
        echo "取消"
        return
    fi

    deltext=$(printf '%s\n' "${dels[@]}")
    n=$(destroy_snaps_list "$deltext")
    echo -e "${GREEN}已删除 $n 个快照${RESET}"
    log "snapshot keep-prune $DS keep=$keep prefix='$pattern': $n removed"
}

# 快照 diff: 对比两个快照(或快照与当前)之间的变化
snap_diff()
{
    local ds snap1 snap2 sel cmd
    if ! ask_dataset; then
        return
    fi
    if ! pick_snapshot "$DS"; then
        return
    fi
    snap1="$SNAP"

    echo
    echo "对比基准: $snap1"
    read -rp "另一侧: 快照名(前缀可省略)或留空对比当前文件系统: " sel

    if [[ -z "$sel" ]]; then
        cmd=(zfs diff "$snap1" "$DS")
    else
        if [[ "$sel" != *"@"* ]]; then
            sel="${DS}@${sel}"
        fi
        if ! dataset_exists "$sel"; then
            echo -e "${RED}快照不存在: $sel${RESET}"
            return
        fi
        cmd=(zfs diff "$snap1" "$sel")
    fi

    echo
    echo "运行: ${cmd[*]}"
    echo "图例: M=修改  A=新增  D=删除  R=重命名  +/- = 内容增减"
    echo
    "${cmd[@]}" || echo -e "${RED}对比失败(数据集可能未挂载)${RESET}"
}

# 回滚到某快照
snap_rollback()
{
    local ds flags r ans
    if ! ask_dataset; then
        return
    fi
    if ! pick_snapshot "$DS"; then
        return
    fi

    echo
    echo -e "${RED}⚠ 回滚会把数据集恢复到快照时刻, 之后的修改全部丢失!${RESET}"
    read -rp "使用 -r 丢弃中间快照? (y/N): " r
    flags=()
    [[ "$r" =~ ^[Yy]$ ]] && flags+=(-r)

    echo
    echo "即将执行: zfs rollback ${flags[*]} $SNAP"
    if ! confirm_destructive "zfs rollback ${flags[*]} $SNAP"; then
        echo "已取消"
        return
    fi

    if zfs rollback "${flags[@]}" "$SNAP"; then
        echo -e "${GREEN}回滚成功: $SNAP${RESET}"
        log "snapshot rollback $SNAP flags=${flags[*]:-none}"
    else
        echo -e "${RED}回滚失败${RESET}"
    fi
}

# send/recv 备份向导: 本地另一 dataset 或 ssh 远程
snap_backup()
{
    local ds snap base mode kind dest sshhost ans
    local -a send_cmd

    echo "—— zfs send/recv 备份向导 ——"
    if ! ask_dataset; then
        return
    fi
    if ! pick_snapshot "$DS"; then
        return
    fi
    snap="$SNAP"

    read -rp "发送模式 全量(f)/增量(i 需选基准): " mode
    if [[ "$mode" =~ ^[Ii]$ ]]; then
        echo "选择增量基准快照(比 $snap 更早):"
        if ! pick_snapshot "$DS"; then
            return
        fi
        base="$SNAP"
        if [[ "$base" == "$snap" ]]; then
            echo -e "${RED}基准不能是同一个快照${RESET}"
            return
        fi
        send_cmd=(zfs send -i "$base" "$snap")
    else
        send_cmd=(zfs send "$snap")
    fi

    read -rp "目标类型 本地(l)/ssh(s): " kind
    if [[ "$kind" =~ ^[Ss]$ ]]; then
        read -rp "SSH 主机(user@host): " sshhost
        if [[ -z "$sshhost" ]]; then
            echo -e "${YELLOW}已取消${RESET}"
            return
        fi
        read -rp "远端目标数据集(需不存在或可续传, 如 tank/backup/xxx): " dest
        [[ -z "$dest" ]] && { echo -e "${YELLOW}已取消${RESET}"; return; }
        echo
        echo "即将执行:"
        echo "${send_cmd[*]} | ssh $sshhost \"zfs receive $dest\""
        echo -e "${YELLOW}提示: 需要 ssh 免密/可登录, 且远端为 root 或具备 zfs 权限${RESET}"
        if ! confirm_yes "确认执行? (yes): "; then
            echo "取消"
            return
        fi
        log "send start ${send_cmd[*]} -> ssh $sshhost:$dest"
        "${send_cmd[@]}" | ssh "$sshhost" "zfs receive $dest"
        rc=$?
    else
        read -rp "本地目标数据集(建议全新路径, 如 pool/backup/xxx): " dest
        [[ -z "$dest" ]] && { echo -e "${YELLOW}已取消${RESET}"; return; }
        local dpool=${dest%%/*}
        if ! pool_exists "$dpool"; then
            echo -e "${RED}目标所在 Pool 不存在: $dpool${RESET}"
            return
        fi
        echo
        echo "即将执行:"
        echo "${send_cmd[*]} | zfs receive $dest"
        if ! confirm_yes "确认执行? (yes): "; then
            echo "取消"
            return
        fi
        log "send start ${send_cmd[*]} -> local:$dest"
        "${send_cmd[@]}" | zfs receive "$dest"
        rc=$?
    fi

    if (( rc == 0 )); then
        echo -e "${GREEN}备份完成${RESET}"
        log "send finish -> $dest"
    else
        echo -e "${RED}备份失败(exit $rc)${RESET}"
        echo "提示: 全量备份目标数据集不能已存在; 若中途断传需 zfs receive -s 续传"
    fi
}

cmd_snapshot()
{
    title "📸 ZFS Snapshot Manager" "查看 / 创建 / 按天或份数清理 / diff 对比 / 回滚 / send·recv 备份"
    echo
    echo "1. 查看快照         5. 快照对比 diff"
    echo "2. 创建快照         6. 回滚 rollback"
    echo "3. 按天数清理       7. send/recv 备份"
    echo "4. 保留最近 N 份"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1) snap_list ;;
        2) snap_create ;;
        3) snap_prune ;;
        4) snap_keep ;;
        5) snap_diff ;;
        6) snap_rollback ;;
        7) snap_backup ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Scrub Manager
# ================================================================

scrub_scan_line()
{
    zpool status "$POOL" 2>/dev/null | grep "scan:" || echo "  无记录"
}

cmd_scrub()
{
    title "🧹 ZFS Scrub" "启动 / 查看 / 实时监控 / 停止 Scrub, 用于修复静默数据损坏"
    echo
    echo "1. 开始 Scrub"
    echo "2. 查看状态"
    echo "3. 实时监控"
    echo "4. 停止 Scrub"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1)
            if ! ask_pool; then pause; return; fi
            if zpool scrub "$POOL"; then
                echo -e "${GREEN}Scrub 已启动: $POOL${RESET}"
                log "scrub start $POOL"
            else
                echo -e "${RED}启动失败${RESET}"
            fi
            pause
            ;;
        2)
            if ! ask_pool; then pause; return; fi
            scrub_scan_line
            pause
            ;;
        3)
            if ! ask_pool; then pause; return; fi
            echo "Ctrl+C 返回菜单"
            trap 'break' INT
            while true; do
                clear
                printf '%bZFS Scrub Monitor %s%b\n' "$WHITE" "$(date '+%F %T')" "$RESET"
                scrub_scan_line
                sleep 3
            done
            trap - INT
            ;;
        4)
            if ! ask_pool; then pause; return; fi
            zpool scrub -s "$POOL" && echo -e "${GREEN}Scrub 已停止: $POOL${RESET}"
            log "scrub stop $POOL"
            pause
            ;;
        0) return ;;
        *) echo "无效选择"; pause ;;
    esac
}

# ================================================================
# TRIM Manager
# ================================================================

cmd_trim()
{
    title "✂ ZFS TRIM" "手动启动 / 查看进度 / 查询 autotrim, SSD 空间回收"
    echo
    echo "1. 开始 TRIM"
    echo "2. 查看状态"
    echo "3. 查看 autotrim"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1)
            if ! ask_pool; then pause; return; fi
            if zpool trim "$POOL"; then
                echo -e "${GREEN}TRIM 已启动: $POOL${RESET}"
                log "trim start $POOL"
            else
                echo -e "${RED}TRIM 启动失败, 可能不支持${RESET}"
            fi
            pause
            ;;
        2)
            if ! ask_pool; then pause; return; fi
            zpool status "$POOL" | grep -i -A5 "trim" || echo "当前没有 TRIM 信息"
            pause
            ;;
        3)
            if ! ask_pool; then pause; return; fi
            zpool get autotrim "$POOL"
            pause
            ;;
        0) return ;;
        *) echo "无效选择"; pause ;;
    esac
}

# ================================================================
# Fragmentation
# ================================================================

cmd_frag()
{
    title "📉 ZFS Fragmentation" "查看单池碎片率并给出整理建议"
    local frag
    if ! ask_pool; then
        pause
        return
    fi

    frag=$(zpool list -H -o frag "$POOL" | tr -d '%')
    if ! is_num "$frag"; then
        echo -e "${YELLOW}无法获取碎片率${RESET}"
        pause
        return
    fi

    echo
    echo "Pool: $POOL"
    echo "Fragmentation: ${frag}%"

    if   (( frag < 20 )); then echo -e "${GREEN}状态: 优秀${RESET}"
    elif (( frag < 40 )); then echo -e "${GREEN}状态: 正常${RESET}"
    elif (( frag < 60 )); then echo -e "${YELLOW}状态: 需要关注${RESET}"
    else                        echo -e "${RED}状态: 较高${RESET}"
    fi

    if (( frag >= 40 )); then
        echo
        echo "建议:"
        echo "- 避免长期高占用"
        echo "- 保留至少 20% 空闲空间"
        echo "- 大文件/VM 池可考虑迁移或重新写入整理"
    fi

    pause
}

# ================================================================
# Offline Dedup
# ================================================================

cmd_dedup()
{
    title "🗜 Offline ZFS Dedup" "调用 zfs-dedup 项目做离线去重, 危险操作需 yes 确认"
    local args

    if ! command_exists zfs-dedup; then
        echo -e "${YELLOW}"
        echo "未安装 zfs-dedup"
        echo
        echo "项目:"
        echo "https://github.com/Mic92/zfs-dedup"
        echo -e "${RESET}"
        pause
        return
    fi

    echo
    echo "输入 zfs-dedup 参数"
    echo
    echo "例如:"
    echo " -n /mnt/tank/data"
    echo
    echo "⚠️ 注意:"
    echo "- 不带 -n 会实际执行修改"
    echo "- 建议首次运行使用 -n 测试"
    echo

    read -ra args
    if (( ${#args[@]} == 0 )); then
        echo -e "${YELLOW}未输入参数, 取消执行${RESET}"
        pause
        return
    fi

    echo
    echo "即将执行:"
    echo "zfs-dedup ${args[*]}"
    echo
    echo -e "${RED}⚠ 实际执行可能修改数据${RESET}"
    if ! confirm_yes "确认执行? (yes): "; then
        echo "取消"
        pause
        return
    fi

    log "dedup start ${args[*]}"
    zfs-dedup "${args[@]}"
    log "dedup finish ${args[*]}"

    pause
}

# ================================================================
# SMART Monitor
# ================================================================

# 交互选择磁盘: 成功返回 0, 全局 DISK 与 DISK_SA。
# 支持字母/数字快捷选择, 或直接输入设备路径。
pick_disk()
{
    local line sel n
    local -a devs devlist=()
    mapfile -t devs < <(smart_devices)
    if (( ${#devs[@]} == 0 )); then
        echo -e "${YELLOW}未发现可检测磁盘${RESET}"
        return 1
    fi

    # 组装设备名列表交给通用选择器
    for line in "${devs[@]}"; do
        devlist+=("${line%%$'\t'*}")
    done
    n=${#devlist[@]}
    if (( n == 1 )); then
        DISK="${devlist[0]}"
        read -ra DISK_SA <<< "${devs[0]#*$'\t'}"
        echo "仅一个磁盘, 自动选择: $DISK"
        return 0
    fi

    if ! pick_from_list "磁盘" "$(printf '%s\n' "${devlist[@]}")"; then
        return 1
    fi

    if [[ -n "$PICK_RES" ]]; then
        sel="$PICK_RES"
    else
        sel="$PICK_RAW"
        # 允许直接输入设备路径, 不在扫描列表也接受
        if [[ -b "$sel" || -b "/dev/$sel" ]]; then
            [[ "$sel" != "/dev/"* ]] && sel="/dev/$sel"
            DISK="$sel"
            DISK_SA=()
            echo "使用磁盘: $DISK"
            return 0
        fi
        echo -e "${RED}设备不存在: $sel${RESET}"
        return 1
    fi

    DISK="$sel"
    # 找回该设备对应的扫描参数
    local devline=""
    for line in "${devs[@]}"; do
        if [[ "${line%%$'\t'*}" == "$DISK" ]]; then
            devline="$line"
            break
        fi
    done
    read -ra DISK_SA <<< "${devline#*$'\t'}"
    echo "使用磁盘: $DISK"
    return 0
}

# 温度/属性总览(遍历全部盘)
smart_overview()
{
    local line dev args sa output
    local -a devs
    mapfile -t devs < <(smart_devices)
    if (( ${#devs[@]} == 0 )); then
        echo -e "${YELLOW}未发现可检测磁盘${RESET}"
        return
    fi

    for line in "${devs[@]}"; do
        IFS=$'\t' read -r dev args <<< "$line"
        echo
        echo "${LINE_SHORT}"
        echo "$dev"
        read -ra sa <<< "$args"
        output=$(smartctl -A "$dev" "${sa[@]}" 2>/dev/null)
        echo "$output" | grep -Ei "Temperature|Airflow|Media_Wear|Percentage|194|190"
    done
}

smart_health_one()
{
    if ! pick_disk; then
        return
    fi
    echo
    smartctl -H "$DISK" "${DISK_SA[@]}" 2>/dev/null | \
        grep -Ei "SMART overall|result|Health|status" || \
        echo -e "${YELLOW}无法获取健康状态${RESET}"
}

smart_run_test()
{
    if ! pick_disk; then
        return
    fi
    local t
    read -rp "自检类型 short/long: " t
    case "$t" in
        short) ;;
        long) ;;
        *) echo -e "${RED}请输入 short 或 long${RESET}"; return ;;
    esac
    echo
    echo -e "${YELLOW}短检通常数分钟, 长检可能数小时(与盘大小相关)${RESET}"
    if ! confirm_yes "确认对 $DISK 启动 ${t} 自检? (yes): "; then
        echo "取消"
        return
    fi
    if smartctl -t "$t" "$DISK" "${DISK_SA[@]}" 2>/dev/null; then
        echo -e "${GREEN}已启动 ${t} 自检: $DISK${RESET}"
        log "smart test $t $DISK"
    else
        echo -e "${RED}启动失败${RESET}"
    fi
}

smart_selftest_log()
{
    if ! pick_disk; then
        return
    fi
    echo
    echo "自检历史:"
    smartctl -l selftest "$DISK" "${DISK_SA[@]}" 2>/dev/null || \
        echo -e "${YELLOW}无自检记录或不可读${RESET}"
}

cmd_smart()
{
    title "💽 SMART Monitor" "温度总览 / 整体健康 / short·long 自检 / 自检日志"
    echo
    echo "1. 温度/属性总览"
    echo "2. 整体健康 (SMART -H)"
    echo "3. 运行自检 (short/long)"
    echo "4. 自检历史"
    echo "0. 返回"
    echo

    if ! command_exists smartctl; then
        echo "未找到 smartctl"
        pause
        return
    fi

    read -rp "选择: " opt
    case "$opt" in
        1) smart_overview ;;
        2) smart_health_one ;;
        3) smart_run_test ;;
        4) smart_selftest_log ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Dataset Analyzer
# ================================================================

# 取数据集单个属性值(带 '-' 的加密相关属性也能安全取到)
zprop()
{
    zfs get -H -o value "$1" "$2" 2>/dev/null
}

cmd_dataset()
{
    title "📂 ZFS Dataset Analyzer" "查看数据集属性 / 空间 / 子数据集, 并给出性能建议"
    local p props compression dedup record

    if ! ask_dataset; then
        pause
        return
    fi

    echo
    echo "Dataset:"
    echo "$DS"
    echo
    echo "${LINE_SHORT}"

    # 逐属性获取, 避免整条 zfs get 因某个属性不适用而失败
    props=(compression dedup recordsize sync atime checksum readonly
           encryption quota refquota mountpoint copies snapdir
           primarycache secondarycache keylocation keystatus encryptionroot)
    for p in "${props[@]}"; do
        printf '%-16s %s\n' "$p" "$(zprop "$p" "$DS")"
    done

    echo
    echo "空间使用:"
    zfs list "$DS" -o name,used,avail,refer

    echo
    echo "子 Dataset:"
    zfs list -r -o name,used,compressratio "$DS"

    echo
    echo "性能建议:"
    compression=$(zprop compression "$DS")
    dedup=$(zprop dedup "$DS")
    record=$(zprop recordsize "$DS")

    if [[ "$compression" == "off" ]]; then
        echo "- Compression 当前关闭"
        echo "  普通文件建议: lz4"
    fi

    if [[ "$dedup" == "on" ]]; then
        echo "- Dedup 已开启"
        echo "- 注意内存消耗"
    fi

    case "$record" in
        1M|1048576) echo "- 大文件优化模式" ;;
        128K)       echo "- 默认模式" ;;
        *)          echo "- Recordsize 特殊设置" ;;
    esac

    echo
    pause
}

# ================================================================
# Encryption Manager
# ================================================================

# 列出所有已加密(或可加密)数据集及密钥状态
encrypt_status()
{
    local out
    out=$(zfs list -H -o name,encryption,keystatus,keylocation \
          -t filesystem,volume 2>/dev/null |
          awk -F'\t' '$2 != "off" && $2 != "-" {print}')

    if [[ -z "$out" ]]; then
        echo "没有发现已加密的数据集"
        return
    fi
    echo
    printf '%-32s %-12s %-12s %s\n' "NAME" "ENCRYPTION" "KEYSTATUS" "KEYLOCATION"
    while IFS=$'\t' read -r n e k l; do
        local col
        if [[ "$k" == "unavailable" ]]; then
            col="$RED"
        else
            col="$GREEN"
        fi
        printf '%-32s %-12s %b%-12s%b %s\n' "$n" "$e" "$col" "$k" "$RESET" "$l"
    done <<< "$out"
}

# 加载密钥(可递归)
encrypt_load()
{
    local flags=() ans
    if ! ask_dataset; then
        return
    fi
    read -rp "递归加载全部子数据集? (y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] && flags+=(-r)

    if zfs load-key "${flags[@]}" "$DS"; then
        echo -e "${GREEN}密钥已加载: $DS${RESET}"
        log "encrypt load-key $DS ${flags[*]:-}"
    else
        echo -e "${RED}加载失败(密钥位置可能不可达或需交互输入)${RESET}"
    fi
}

# 卸载密钥
encrypt_unload()
{
    local flags=() ans
    if ! ask_dataset; then
        return
    fi
    read -rp "递归卸载全部子数据集? (y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] && flags+=(-r)

    if zfs unload-key "${flags[@]}" "$DS"; then
        echo -e "${GREEN}密钥已卸载: $DS${RESET}"
        log "encrypt unload-key $DS ${flags[*]:-}"
    else
        echo -e "${RED}卸载失败${RESET}"
    fi
}

# 更换密钥
encrypt_change()
{
    if ! ask_dataset; then
        return
    fi
    local ks
    ks=$(zprop keystatus "$DS")
    if [[ "$ks" != "available" ]]; then
        echo -e "${YELLOW}密钥状态为 '$ks', 需要先加载密钥才能更换${RESET}"
        return
    fi

    echo
    echo -e "${RED}⚠ 更换密钥将使用新的口令/密钥材料, 旧密钥立即失效!${RESET}"
    if ! confirm_destructive "zfs change-key $DS"; then
        echo "已取消"
        return
    fi

    if zfs change-key "$DS"; then
        echo -e "${GREEN}密钥已更换: $DS${RESET}"
        log "encrypt change-key $DS"
    else
        echo -e "${RED}更换失败${RESET}"
    fi
}

cmd_encrypt()
{
    title "🔐 ZFS Encryption Manager" "加密状态总览 / 加载 / 卸载 / 更换密钥"
    echo
    echo "1. 加密状态总览"
    echo "2. 加载密钥 (load-key)"
    echo "3. 卸载密钥 (unload-key)"
    echo "4. 更换密钥 (change-key)"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1) encrypt_status ;;
        2) encrypt_load ;;
        3) encrypt_unload ;;
        4) encrypt_change ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Pool Manager
# ================================================================

# 着色显示单池 vdev 拓扑/状态
pool_topology()
{
    local line
    while IFS= read -r line; do
        if [[ -t 1 && "$TERM" != "dumb" ]]; then
            line=${line//ONLINE/${GREEN}ONLINE${RESET}}
            line=${line//DEGRADED/${YELLOW}DEGRADED${RESET}}
            line=${line//FAULTED/${RED}FAULTED${RESET}}
            line=${line//UNAVAIL/${RED}UNAVAIL${RESET}}
            line=${line//OFFLINE/${RED}OFFLINE${RESET}}
            line=${line//REMOVED/${RED}REMOVED${RESET}}
            echo -e "$line"
        else
            echo "$line"
        fi
    done < <(zpool status "$1")
}

topo_view()
{
    local pools pname
    mapfile -t pools < <(pool_names)
    if (( ${#pools[@]} == 0 )); then
        echo "无 Pool"
        return
    fi
    for pname in "${pools[@]}"; do
        echo
        echo -e "${WHITE}▶ Pool: $pname${RESET}"
        pool_topology "$pname"
    done
}

pool_export_one()
{
    if ! ask_pool; then
        return
    fi
    echo
    echo -e "${RED}⚠ 导出会卸载数据集并让 Pool 从系统消失(数据不动)${RESET}"
    echo -e "${YELLOW}提示: 若数据集正被使用会失败, 请先停相关服务${RESET}"
    if ! confirm_destructive "zpool export $POOL"; then
        echo "已取消"
        return
    fi
    if zpool export "$POOL"; then
        echo -e "${GREEN}已导出: $POOL${RESET}"
        log "pool export $POOL"
    else
        echo -e "${RED}导出失败: 可能仍有数据集被占用, 检查挂载/服务${RESET}"
    fi
}

pool_import_one()
{
    local avail name
    echo
    echo "当前可导入的池:"
    avail=$(zpool import 2>&1 | grep -E "pool:" || true)
    if [[ -z "$avail" ]]; then
        echo "  没有发现可导入的池"
        return
    fi
    echo "$avail" | sed 's/^/  /'
    echo
    read -rp "输入要导入的池名: " name
    if [[ -z "$name" ]]; then
        echo -e "${YELLOW}已取消${RESET}"
        return
    fi
    echo
    echo -e "${RED}⚠ 导入前请确认该池没有在其他主机/系统中处于挂载状态!${RESET}"
    if ! confirm_destructive "zpool import $name"; then
        echo "已取消"
        return
    fi
    if zpool import "$name"; then
        echo -e "${GREEN}已导入: $name${RESET}"
        log "pool import $name"
    else
        echo -e "${RED}导入失败。若设备路径变化可用: zpool import -d /dev/disk/by-id $name${RESET}"
    fi
}

# 磁盘概览(名称/型号/序列号/温度)
pool_disks()
{
    if ! command_exists smartctl; then
        echo "未安装 smartctl, 无法读取磁盘信息"
        return
    fi
    local dev args sa line model serial temp
    local -a devs
    mapfile -t devs < <(smart_devices)
    if (( ${#devs[@]} == 0 )); then
        echo "未发现磁盘"
        return
    fi

    echo
    printf '%-12s %-28s %-16s %6s\n' "DEVICE" "MODEL" "SERIAL" "TEMP"
    for line in "${devs[@]}"; do
        IFS=$'\t' read -r dev args <<< "$line"
        read -ra sa <<< "$args"
        model=$(smartctl -i "$dev" "${sa[@]}" 2>/dev/null |
                grep -E "Device Model|Model Number|Product:" | head -1 |
                sed 's/^[^:]*: *//')
        serial=$(smartctl -i "$dev" "${sa[@]}" 2>/dev/null |
                 grep -E "Serial Number|Serial number" | head -1 |
                 sed 's/^[^:]*: *//')
        temp=$(smart_temperature "$dev" "${sa[@]}")
        [[ -z "$model" ]] && model="-"
        [[ -z "$serial" ]] && serial="-"
        [[ "$temp" =~ ^[0-9]+$ ]] || temp="-"
        printf '%-12s %-28s %-16s %6s\n' "$dev" "$model" "$serial" "${temp}℃"
    done
}

# 换盘指引: 找出故障/离线盘并给出操作模板
pool_replace_guide()
{
    local pools pname bad line
    mapfile -t pools < <(pool_names)
    found=0
    for pname in "${pools[@]}"; do
        bad=$(zpool status "$pname" | \
              grep -E "FAULTED|DEGRADED|OFFLINE|UNAVAIL|REMOVED" | \
              grep -vE "state:|pool:|  pool:|errors" | head -5 || true)
        if [[ -z "$bad" ]]; then
            continue
        fi
        found=1
        echo
        echo -e "${YELLOW}▶ Pool: $pname 存在异常设备${RESET}"
        echo "$bad" | sed 's/^/  /'
        echo
        echo "操作模板(按序执行, 请根据实际盘符替换):"
        echo "  1) 下线故障盘     : zpool offline $pname /dev/disk/by-id/<旧盘ID>"
        echo "  2) 物理更换硬盘"
        echo "  3) 让 ZFS 接管新盘: zpool replace $pname /dev/disk/by-id/<旧盘ID> /dev/disk/by-id/<新盘ID>"
        echo "  4) 或自动寻找     : zpool replace $pname <旧盘ID>"
        echo "  5) 重新上线       : zpool online $pname /dev/disk/by-id/<新盘ID>"
        echo "查看盘 ID: ls -l /dev/disk/by-id/"
        echo
        local dev
        dev=$(echo "$bad" | awk 'NR==1{print $1}')
        if [[ -b "/dev/$dev" ]]; then
            echo -e "${WHITE}快速健康检查:${RESET}"
            smartctl -H "/dev/$dev" 2>/dev/null | grep -E "SMART overall|result:" || \
                echo "  (无法读取 /dev/$dev 的健康状态)"
        fi
    done
    if (( found == 0 )); then
        echo "所有 Pool 的设备状态正常"
    fi
}

cmd_poolmgr()
{
    title "🗄 ZFS Pool Manager" "vdev 拓扑 / 池列表 / 导出导入 / 磁盘信息 / 换盘指引"
    echo
    echo "1. vdev 拓扑/状态"
    echo "2. 池列表详情"
    echo "3. 导出池 (export)"
    echo "4. 导入池 (import)"
    echo "5. 磁盘信息"
    echo "6. 换盘指引"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1) topo_view ;;
        2)
            zpool list -o name,size,alloc,free,cap,dedup,frag,health,expandsize,comment
            ;;
        3) pool_export_one ;;
        4) pool_import_one ;;
        5) pool_disks ;;
        6) pool_replace_guide ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Dataset Manager
# ================================================================

# 校验子数据集名与属性串, 防止注入
valid_child_name()
{
    [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]]
}

valid_prop_assignment()
{
    [[ "$1" =~ ^[A-Za-z0-9_]+=[^[:space:]]+$ ]]
}

dsm_create()
{
    local parent new props ans
    if ! ask_dataset; then
        return
    fi
    parent="$DS"

    read -rp "新数据集名(不含父路径): " new
    if ! valid_child_name "$new"; then
        echo -e "${RED}数据集名只能包含字母/数字/._-${RESET}"
        return
    fi

    read -rp "附加属性 (如 'compression=zstd recordsize=1M', 回车跳过): " props
    local -a opt_props=()
    if [[ -n "$props" ]]; then
        read -ra opt_props <<< "$props"
        for p in "${opt_props[@]}"; do
            if ! valid_prop_assignment "$p"; then
                echo -e "${RED}非法属性: $p (格式 key=value 且不含空格)${RESET}"
                return
            fi
        done
    fi

    local target="$parent/$new"
    if dataset_exists "$target"; then
        echo -e "${RED}已存在: $target${RESET}"
        return
    fi

    echo
    echo "即将创建:"
    echo "  zfs create ${opt_props[*]} $target"
    if ! confirm_yes "确认创建? (yes): "; then
        echo "取消"
        return
    fi
    if zfs create "${opt_props[@]}" "$target"; then
        echo -e "${GREEN}已创建: $target${RESET}"
        log "dsm create $target ${opt_props[*]:-}"
    else
        echo -e "${RED}创建失败${RESET}"
    fi
}

dsm_zvol()
{
    local parent new size ans sparse="" target
    if ! ask_dataset; then
        return
    fi
    parent="$DS"

    read -rp "新 zvol 名: " new
    if ! valid_child_name "$new"; then
        echo -e "${RED}名称只能包含字母/数字/._-${RESET}"
        return
    fi
    read -rp "大小 (如 20G): " size
    size=$(echo "$size" | tr '[:lower:]' '[:upper:]')
    if ! [[ "$size" =~ ^[0-9]+[KMGTPE]?$ ]]; then
        echo -e "${RED}非法大小: 示例 500M / 20G / 1T${RESET}"
        return
    fi
    read -rp "使用 sparse(按需分配)? (y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] && sparse="-s"
    target="$parent/$new"

    echo
    echo "即将创建: zfs create -V $size ${sparse} $target"
    if ! confirm_yes "确认创建? (yes): "; then
        echo "取消"
        return
    fi

    if [[ -n "$sparse" ]]; then
        if zfs create -V "$size" -s "$target"; then
            echo -e "${GREEN}已创建 zvol: $target (${size}, sparse)${RESET}"
            log "dsm zvol $target size=$size sparse"
        else
            echo -e "${RED}创建失败${RESET}"
        fi
    else
        if zfs create -V "$size" "$target"; then
            echo -e "${GREEN}已创建 zvol: $target (${size})${RESET}"
            log "dsm zvol $target size=$size"
        else
            echo -e "${RED}创建失败${RESET}"
        fi
    fi
}

dsm_destroy()
{
    local ans confirm
    if ! ask_dataset; then
        return
    fi

    echo
    zfs list "$DS" -o name,used,refer,compressratio,mountpoint
    echo
    read -rp "递归删除子数据集(-r)? (y/N): " ans
    echo
    echo -e "${RED}⚠ 删除数据集会永久销毁其全部数据与快照!${RESET}"
    if ! confirm_destructive "zfs destroy${ans:+ -r} $DS"; then
        echo "已取消"
        return
    fi
    read -rp "为防误删, 请再次输入完整数据集名确认: " confirm
    if [[ "$confirm" != "$DS" ]]; then
        echo -e "${RED}名称不匹配, 已取消${RESET}"
        return
    fi

    if [[ "$ans" =~ ^[Yy]$ ]]; then
        zfs destroy -r "$DS"
    else
        zfs destroy "$DS"
    fi
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}已删除: $DS${RESET}"
        log "dsm destroy $DS recursive=$ans"
    else
        echo -e "${RED}删除失败(可能存在 clone 或子数据集)${RESET}"
    fi
}

dsm_setprop()
{
    local prop val
    if ! ask_dataset; then
        return
    fi

    echo
    echo "常用属性:"
    echo "  1. compression     (lz4 / zstd / on / off)"
    echo "  2. recordsize      (4K/8K/.../1M/16M)"
    echo "  3. sync            (standard / always / disabled)"
    echo "  4. atime           (on / off)"
    echo "  5. checksum        (on / sha256 / fletcher4)"
    echo "  6. copies          (1 / 2 / 3)"
    echo "  7. primarycache    (all / metadata / none)"
    echo "  8. secondarycache  (all / metadata / none)"
    echo "  9. 自定义属性"
    echo
    read -rp "选择属性序号或输入 prop=value: " sel

    if is_num "$sel"; then
        case "$sel" in
            1) prop=compression ;;
            2) prop=recordsize ;;
            3) prop=sync ;;
            4) prop=atime ;;
            5) prop=checksum ;;
            6) prop=copies ;;
            7) prop=primarycache ;;
            8) prop=secondarycache ;;
            *) prop="" ;;
        esac
        [[ -z "$prop" ]] && { echo "无效序号"; return; }
        read -rp "输入 $prop 的值: " val
        [[ -z "$val" ]] && { echo -e "${YELLOW}已取消${RESET}"; return; }
    else
        if ! valid_prop_assignment "$sel"; then
            echo -e "${RED}格式应为 key=value${RESET}"
            return
        fi
        prop=${sel%%=*}
        val=${sel#*=}
    fi

    echo
    echo "即将执行: zfs set $prop=$val $DS"
    if ! confirm_yes "确认执行? (yes): "; then
        echo "取消"
        return
    fi
    if zfs set "$prop=$val" "$DS"; then
        echo -e "${GREEN}已设置: $DS $prop=$val${RESET}"
        log "dsm set $DS $prop=$val"
    else
        echo -e "${RED}设置失败(值可能非法)${RESET}"
    fi
}

dsm_quota()
{
    local kind val
    if ! ask_dataset; then
        return
    fi
    echo
    echo "当前配额:"
    zfs get -o property,value quota,refquota "$DS"
    echo
    echo "1. 设置 quota      2. 清除 quota"
    echo "3. 设置 refquota   4. 清除 refquota"
    echo
    read -rp "选择: " opt

    case "$opt" in
        1) kind=quota ;;
        2) kind=quota; val=none ;;
        3) kind=refquota ;;
        4) kind=refquota; val=none ;;
        *) echo "无效选择"; return ;;
    esac

    if [[ -z "${val:-}" ]]; then
        read -rp "输入大小 (如 100G / 1T): " val
        val=$(echo "$val" | tr '[:lower:]' '[:upper:]')
        if ! [[ "$val" =~ ^[0-9]+[KMGTPE]?$ ]]; then
            echo -e "${RED}非法大小${RESET}"
            return
        fi
    fi

    echo
    echo "即将执行: zfs set $kind=$val $DS"
    if ! confirm_yes "确认执行? (yes): "; then
        echo "取消"
        return
    fi
    if zfs set "$kind=$val" "$DS"; then
        echo -e "${GREEN}已设置: $DS $kind=$val${RESET}"
        log "dsm quota $DS $kind=$val"
    else
        echo -e "${RED}设置失败${RESET}"
    fi
}

cmd_dsmgr()
{
    title "📁 ZFS Dataset Manager" "创建 / 删除 dataset 与 zvol / 属性 / 配额管理"
    echo
    echo "1. 创建 Dataset"
    echo "2. 创建 zvol"
    echo "3. 删除 Dataset"
    echo "4. 设置属性"
    echo "5. 配额管理"
    echo "6. 子数据集列表"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1) dsm_create ;;
        2) dsm_zvol ;;
        3) dsm_destroy ;;
        4) dsm_setprop ;;
        5) dsm_quota ;;
        6)
            if ask_dataset; then
                echo
                zfs list -r -o name,used,avail,refer,mountpoint "$DS"
            fi
            ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Alerts (阈值告警, 可挂 cron)
# ================================================================

ALERT_RC=0
NALERTS=0

add_alert()
{
    ALERT_KIND+=("$1")
    ALERT_TEXT+=("$2")
    NALERTS=$((NALERTS + 1))
}

# 收集全部告警到 ALERT_KIND / ALERT_TEXT 全局数组
alerts_collect()
{
    local pools pname cap frag health scanline errcount age warn_days crit_days

    ALERT_KIND=(); ALERT_TEXT=(); NALERTS=0

    warn_days=${ZT_SCRUB_WARN_DAYS:-30}
    crit_days=${ZT_SCRUB_CRIT_DAYS:-60}

    mapfile -t pools < <(pool_names)
    if (( ${#pools[@]} == 0 )); then
        add_alert INFO "系统中没有任何 Pool"
        return
    fi

    for pname in "${pools[@]}"; do
        health=$(zpool get -H -o value health "$pname")
        case "$health" in
            ONLINE)
                ;;
            DEGRADED)
                add_alert CRIT "Pool $pname 状态 DEGRADED(降级)"
                ;;
            *)
                add_alert CRIT "Pool $pname 状态 $health(异常)"
                ;;
        esac

        cap=$(zpool list -H -o cap "$pname" | tr -d '%')
        if is_num "$cap"; then
            if (( cap >= 90 )); then
                add_alert CRIT "Pool $pname 容量已达 ${cap}%"
            elif (( cap >= 80 )); then
                add_alert WARN "Pool $pname 容量偏高 ${cap}%"
            fi
        fi

        frag=$(zpool list -H -o frag "$pname" | tr -d '%')
        if is_num "$frag"; then
            if (( frag >= 60 )); then
                add_alert WARN "Pool $pname 碎片率 ${frag}%"
            elif (( frag >= 40 )); then
                add_alert INFO "Pool $pname 碎片率 ${frag}%"
            fi
        fi

        errcount=$(zpool status "$pname" | awk '
            $1=="NAME"{next}
            NF>=5 && $3~/^[0-9]+$/ && $4~/^[0-9]+$/ && $5~/^[0-9]+$/ {
                if (($3+$4+$5)>0) n++
            }
            END{print n+0}')
        if (( errcount > 0 )); then
            add_alert CRIT "Pool $pname 有 $errcount 个设备出现读写校验错误"
        fi

        if age=$(scrub_age_days "$pname"); then
            if (( age > crit_days )); then
                add_alert CRIT "Pool $pname 已超过 ${crit_days} 天未 Scrub (上次 ${age} 天前)"
            elif (( age > warn_days )); then
                add_alert WARN "Pool $pname 超过 ${warn_days} 天未 Scrub (上次 ${age} 天前)"
            fi
        fi
    done
}

# 着色打印一条告警(供 dashboard 与 cmd_alerts 共用)
paint_alert_line()
{
    local i="$1" kind icon color text
    kind="${ALERT_KIND[$i]}"
    text="${ALERT_TEXT[$i]}"
    case "$kind" in
        CRIT) icon="✖"; color="$RED" ;;
        WARN) icon="⚠"; color="$YELLOW" ;;
        *)    icon="ℹ"; color="$CYAN" ;;
    esac
    echo -e "  ${color}${icon}${RESET} ${text}"
}

cmd_alerts()
{
    title "🚨 ZFS Alerts" "容量 / 碎片 / Scrub 过期 / 设备错误检查, 退出码 0/1/2 可挂 cron"
    local i crt=0 wrn=0 inf=0

    alerts_collect
    if (( NALERTS == 0 )); then
        echo
        echo -e "${GREEN}✔ 一切正常, 没有发现告警${RESET}"
        ALERT_RC=0
    else
        echo
        for (( i = 0; i < NALERTS; i++ )); do
            paint_alert_line "$i"
            case "${ALERT_KIND[$i]}" in
                CRIT) crt=$((crt + 1)) ;;
                WARN) wrn=$((wrn + 1)) ;;
                *)    inf=$((inf + 1)) ;;
            esac
        done
        echo
        echo "汇总: ${RED}$crt 严重${RESET} / ${YELLOW}$wrn 警告${RESET} / ${CYAN}$inf 提示${RESET}"
        if (( crt > 0 )); then
            ALERT_RC=2
        elif (( wrn > 0 )); then
            ALERT_RC=1
        else
            ALERT_RC=0
        fi
    fi
    echo "(退出码: 0=正常 1=警告 2=严重, 便于 cron 使用)"
    if [[ -t 0 ]]; then
        pause
    fi
}

# ================================================================
# Progress Monitor (进行中的 scrub / resilver / trim)
# ================================================================

cmd_progress()
{
    title "⏳ ZFS Activity Progress" "查看进行中的 scrub / resilver / trim 进度"
    local pools pname any=0
    mapfile -t pools < <(pool_names)

    for pname in "${pools[@]}"; do
        local block
        block=$(zpool status "$pname" 2>/dev/null | \
                grep -E "scan:|resilvered|trim:|trimming|replacing" | \
                grep -E "in progress|resilvered|trimming|replacing" || true)
        if [[ -n "$block" ]]; then
            any=1
            echo
            echo -e "${WHITE}▶ Pool: $pname${RESET}"
            echo "$block"
        fi
    done

    if (( any == 0 )); then
        echo
        echo "当前没有进行中的 scrub / resilver / trim"
    fi
    pause
}

# ================================================================
# Doctor (依赖自检)
# ================================================================

cmd_doctor()
{
    title "🩺 zfs-tool Doctor" "核心 / 可选依赖与运行环境自检"
    local c okc=0 warnc=0 errc=0

    echo
    echo -e "${WHITE}核心依赖:${RESET}"
    for c in zpool zfs awk sed grep date stat; do
        if command_exists "$c"; then
            echo -e "  ${GREEN}✔${RESET} $c"
            okc=$((okc + 1))
        else
            echo -e "  ${RED}✖${RESET} $c (缺失!)"
            errc=$((errc + 1))
        fi
    done

    echo
    echo -e "${WHITE}可选依赖:${RESET}"
    for c in smartctl mpstat top ssh pv zfs-dedup; do
        if command_exists "$c"; then
            echo -e "  ${GREEN}✔${RESET} $c"
        else
            echo -e "  ${YELLOW}-${RESET} $c (未安装, 相关功能不可用)"
            warnc=$((warnc + 1))
        fi
    done

    echo
    echo -e "${WHITE}环境检查:${RESET}"
    if mkdir -p "$LOG_DIR" 2>/dev/null; then
        echo -e "  ${GREEN}✔${RESET} 日志目录可写: $LOG_DIR"
    else
        echo -e "  ${RED}✖${RESET} 日志目录不可写: $LOG_DIR"
        errc=$((errc + 1))
    fi
    if [[ -f "$ARCSTATS_FILE" ]]; then
        echo -e "  ${GREEN}✔${RESET} arcstats 可读"
    else
        echo -e "  ${YELLOW}-${RESET} 无 arcstats(非 OpenZFS 内核环境?)"
        warnc=$((warnc + 1))
    fi
    if command_exists smartctl; then
        local cnt
        cnt=$(smartctl --scan 2>/dev/null | grep -cv '^#' || true)
        echo -e "  ${GREEN}✔${RESET} smartctl 扫描到约 $cnt 个设备"
    fi
    local zmod=""
    zmod=$(cat /sys/module/zfs/version 2>/dev/null || echo unknown)
    echo -e "  ${CYAN}ℹ${RESET} ZFS 内核模块版本: $zmod"

    echo
    echo "结果: 正常 $okc / 可选缺失 $warnc / 严重缺失 $errc"
    if (( errc > 0 )); then
        echo -e "${RED}存在严重缺失, 请先安装对应工具${RESET}"
    else
        echo -e "${GREEN}核心依赖完整${RESET}"
    fi
    pause
}

# ================================================================
# History / 日志
# ================================================================

hist_zpool()
{
    local pname
    if ! ask_pool; then
        return
    fi
    echo
    echo "zpool history (最近 60 条):"
    zpool history "$POOL" 2>/dev/null | tail -60 || echo "无法读取 history"
}

hist_tool_log()
{
    echo
    if [[ -f "$LOG_FILE" ]]; then
        echo "最近 30 条工具日志 ($LOG_FILE):"
        tail -30 "$LOG_FILE"
    else
        echo "还没有日志记录"
    fi
}

hist_cron()
{
    echo
    echo -e "${WHITE}用户 crontab 中与 ZFS 相关的条目:${RESET}"
    if crontab -l 2>/dev/null | grep -Ei "zfs|scrub|trim|snapshot|fstrim" | grep -v '^#'; then
        :
    else
        echo "  (无)"
    fi
    echo
    echo -e "${WHITE}/etc/cron.d 与系统 cron 目录匹配项:${RESET}"
    grep -RnsEi "zfs|scrub|fstrim|trim" /etc/cron* 2>/dev/null | grep -v '^#' || echo "  (无)"
    if command_exists systemctl; then
        echo
        echo -e "${WHITE}systemd 定时器匹配项:${RESET}"
        systemctl list-timers --all --no-pager 2>/dev/null | \
            grep -Ei "zfs|scrub|trim|fstrim" || echo "  (无)"
    fi
}

cmd_hist()
{
    title "📜 History & Logs" "zpool history / 工具日志 / ZFS 相关定时任务"
    echo
    echo "1. zpool history"
    echo "2. 本工具日志"
    echo "3. 定时任务(ZFS 相关)"
    echo "0. 返回"
    echo

    read -rp "选择: " opt
    case "$opt" in
        1) hist_zpool ;;
        2) hist_tool_log ;;
        3) hist_cron ;;
        0) return ;;
        *) echo "无效选择" ;;
    esac

    if [[ "$opt" != "0" ]]; then
        pause
    fi
}

# ================================================================
# Version
# ================================================================

cmd_version()
{
    title "ℹ ZFS Version" "内核 / ZFS 用户态与模块版本信息"
    echo
    echo "Kernel:"
    uname -r
    echo
    echo "ZFS:"
    zfs --version 2>/dev/null || echo "unknown"
    echo
    echo "ZPool:"
    zpool version 2>/dev/null || echo "unknown"
    echo
    echo "Kernel Module ZFS:"
    if [[ -f /sys/module/zfs/version ]]; then
        cat /sys/module/zfs/version
    else
        echo "unknown"
    fi
    echo
    pause
}

# ================================================================
# CLI Mode
# ================================================================

usage()
{
    echo "zfs-tool v$VERSION — ZFS 运维管理工具箱"
    echo
    echo "用法:"
    echo "  zfs-tool.sh                     交互菜单"
    echo "  zfs-tool.sh <命令> [-p pool] [-d dataset]"
    echo
    echo "基础:"
    echo "  dashboard       综合仪表盘(带告警摘要)"
    echo "  arc             ARC/L2ARC 统计与实时监控"
    echo "  health          Pool 健康检查"
    echo "  iostat          I/O 实时监控"
    echo "  frag            碎片率与建议"
    echo "  dedup           zfs-dedup(离线去重)"
    echo "  version         版本信息"
    echo
    echo "快照/备份:"
    echo "  snapshot        快照管理菜单"
    echo "  snapdiff        快照 diff 对比"
    echo "  rollback        回滚快照(双重确认)"
    echo "  backup          zfs send/recv 备份向导"
    echo "  prune           快照保留清理(最近 N 份)"
    echo
    echo "运维:"
    echo "  scrub           清理/状态/监控"
    echo "  trim            TRIM 管理"
    echo "  smart           SMART 监控/自检"
    echo "  encrypt         加密密钥管理"
    echo "  poolmgr         Pool/磁盘管理"
    echo "  dsmgr           Dataset/zvol 管理"
    echo "  dataset         数据集分析器"
    echo "  alerts          阈值告警(退出码 0/1/2, 可挂 cron)"
    echo "  progress        进行中的 scrub/resilver/trim"
    echo "  doctor          依赖自检"
    echo "  hist            历史与日志"
    echo
    echo "通用:"
    echo "  help            本帮助"
    echo
    echo "交互提示:"
    echo "  选择 Pool/Dataset/磁盘时, 输入 A/B/C.. 字母或数字即可(池名启动时已扫描);"
    echo "  只有一个 Pool 时自动选中; 主菜单内按 h/? 随时查看本帮助"
}

cli_mode()
{
    case "${1:-}" in
        dashboard) cmd_dashboard ;;
        arc)       cmd_arc ;;
        health)    cmd_health ;;
        iostat)    cmd_iostat ;;
        snapshot)  cmd_snapshot ;;
        snapdiff)  cmd_snapdiff_cli ;;
        rollback)  cmd_rollback_cli ;;
        backup)    cmd_backup_cli ;;
        prune)     cmd_prune_cli ;;
        scrub)     cmd_scrub ;;
        trim)      cmd_trim ;;
        frag)      cmd_frag ;;
        dedup)     cmd_dedup ;;
        smart)     cmd_smart ;;
        dataset)   cmd_dataset ;;
        dsmgr)     cmd_dsmgr ;;
        poolmgr)   cmd_poolmgr ;;
        encrypt)   cmd_encrypt ;;
        alerts)    cmd_alerts ;;
        progress)  cmd_progress ;;
        doctor)    cmd_doctor ;;
        hist)      cmd_hist ;;
        version)   cmd_version ;;
        help|-h|--help) usage ;;
        *)         return 1 ;;
    esac
    return 0
}

# 快照类命令的 CLI 轻量入口(需 -d 提供数据集, 否则回落到对应菜单逻辑)
cmd_snapdiff_cli()
{
    cmd_need_ds snap_diff || snap_diff
}

cmd_rollback_cli()
{
    cmd_need_ds snap_rollback || snap_rollback
}

cmd_backup_cli()
{
    cmd_need_ds snap_backup || snap_backup
}

cmd_prune_cli()
{
    cmd_need_ds snap_keep || snap_keep
}

# 有 TARGET_DS 时直接执行指定函数并退出; 否则进入交互菜单
cmd_need_ds()
{
    if [[ -n "$TARGET_DS" ]]; then
        "$1"
        return 0
    fi
    return 1
}

# ================================================================
# Entry
# ================================================================

main()
{
    local cmd rest=()

    # 提取通用选项 -p/--pool 与 -d/--dataset, 其余为命令
    while (( $# > 0 )); do
        case "$1" in
            -p|--pool)
                if (( $# >= 2 )); then
                    TARGET_POOL="$2"
                    shift 2
                else
                    shift
                fi
                ;;
            -d|--dataset)
                if (( $# >= 2 )); then
                    TARGET_DS="$2"
                    shift 2
                else
                    shift
                fi
                ;;
            *)
                rest+=("$1")
                shift
                ;;
        esac
    done

    # 帮助在任何环境下都可读, 不要求 root
    if (( ${#rest[@]} > 0 )); then
        cmd="${rest[0]}"
        if [[ "$cmd" == "help" || "$cmd" == "-h" || "$cmd" == "--help" || "$cmd" == "?" ]]; then
            usage
            exit 0
        fi
    fi

    # 运行环境要求
    require_root
    check_zfs

    # 启动即扫描池名, 供全脚本字母快捷选择使用
    refresh_pool_index

    if (( ${#rest[@]} > 0 )); then
        cmd="${rest[0]}"
        if (( ${#rest[@]} > 1 )); then
            echo -e "${YELLOW}警告: 忽略多余参数: ${rest[*]:1}${RESET}"
        fi
        if cli_mode "$cmd"; then
            if [[ "$cmd" == "alerts" ]]; then
                exit "$ALERT_RC"
            fi
            exit 0
        else
            echo -e "${RED}未知命令: $cmd${RESET}"
            echo
            usage
            exit 1
        fi
    fi

    main_menu
}

main "$@"
