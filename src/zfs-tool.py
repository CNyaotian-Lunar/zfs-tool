#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zfs-tool v6.2 — ZFS 运维管理工具箱 (Python 版)
================================================

by CNyaotian with DeepSeek

v6.2 新增:  # C8-VERSION-6.2
  * `alerts` 的碎片判定**按介质分流**: 全 SSD 池(底层设备 `rotational`=0)
    改用独立阈值 `frag_ssd_warn`(默认 90)且**只发 INFO、绝不发 WARN** —— SSD 无寻道
    成本, 碎片率对性能没有意义; 而 `recordsize=8K` 这类小记录 + docker 负载天生碎片
    偏高, `zpool rewrite` 也缓解不了还磨损寿命。HDD / 判不出介质的池沿用原
    `warn_frag`/`crit_frag`。
  * `scrub_warn_days` 30 -> **35**(`scrub_crit_days` 仍 60), 与外部巡检脚本
    的 scrub 判定统一为 35/60 —— 同一件事实不再两套口径。
  * 新增辅助 `_dev_rotational()` / `_pool_all_ssd()`: 走 `zpool status -P` 的完整设备
    路径(ZFS 2.4 的 `status`/`list -v` 用 GUID 显示 vdev 名, 拿不到 sdX) +
    `lsblk -no PKNAME` 取父盘 + `/sys/class/block/*/queue/rotational`。
  * 对抗性审查修复: ① `_pool_all_ssd` **任何认不出的设备行都当判不了**
    (原先裸 GUID 行被静默丢弃, 极端下会把含 HDD 的池判成 SSD 而漏报)；② 该函数里的
    `zpool status -P` 改走 `run_noblock(timeout=20)`(原先无死线, 卡住会挂死整轮告警,
    连 CRIT 一起丢)；③ `/dev/loopN` 候选直接跳过(loop 恒报 rotational=0 会误判)；
    ④ `frag_ssd_warn` 使用时 clamp 到 >= 0。**新增语义**: 全 SSD 池只发 INFO 时不再
    进 `alerts` 退出码(rc 保持 0), 这是既定意图。

v6.1 新增:  # C7-VERSION-6.1
  * Scrub 精细控制(10 个子命令): status / pause / resume / resume-e / continue /
    errors / range / wait / start / stop —— 暂停状态下进度会落盘(重启仍保持)、
    可按 last_scrubbed_txg 续扫、可只扫已知坏块(-e)、可按创建时间区间扫(-S/-E)、
    等待带死线(--timeout)不会挂死；主菜单同步扩到 8 项。
  * 加密 send/recv 增强: `send-file` 支持 --raw(-w) / --compressed(-c) /
    --replicate(-R) / --holds(-h) / -i <基准>，并支持**非交互直发**(脚本可用)；
    预览用 `zfs send -n -v` 做**真估算**流大小 + 目标盘剩余空间检查。
  * 新增 `resume` 命令: 读 receive_resume_token，中断的接收终于有续传入口
    (token 只显示前 16 位, 不写日志/JSON)。
  * 安全/健壮性(四轮对抗性审查): 菜单路径的 --dry-run 逃逸根治(不再"预览变真跑")、
    命令超时不再把工具一起挂死、`alerts` 读不到 scrub 记录时明确告警(不再静默失明)、
    发送目标防符号链接写穿(TOCTOU)、Ctrl-C 不再留孤儿 zfs receive、
    0 字节发送结果判失败、`-i` 缺值/等号形式不再静默降级为全量。

v6.0 新增:
  * Pool Manager 扩展: 删除存储池(双重确认+输名校验)、添加 L2ARC 缓存盘、
    添加 SLOG 日志盘、L2ARC 缓存策略(secondarycache=all/metadata/none)
  * fnOS 加密存储/TPM 全套并入(主菜单 25; 该模块经 _zt_build_single.py 以 gzip+base64
    注入单文件才可用 —— ⚠ 本仓不分发该模块, 需自备 zt_fnos.py; 同目录外部副本仅在
    设了 ZT_FNOS_EXTERNAL=1 时使用)
  * 真机适配: tpm2 新版输出解析(厂商/固件/DA)、ANSI 清屏(去 clear 噪音)
由 v4.0 (bash) 重构而来。纯标准库, 零第三方依赖,
目标平台: TrueNAS SCALE / OpenZFS Linux / 飞牛 fnOS (python3 >= 3.8)。
旧版 zfs-tool.sh (v4.0) 保留不动, 可对照使用。

功能:
  1  Dashboard             13  Progress(活动进度)
  2  ARC / L2ARC           14  Encryption(加密管理)
  3  Health Check          15  Pool Manager
  4  I/O Monitor           16  Dataset Manager
  5  Snapshot Manager      17  Alerts(告警, 退出码 0/1/2)
  6  Scrub                 18  Doctor(自检)
  7  TRIM                  19  History
  8  Fragmentation         20  Schedule(计划任务)
  9  Dedup                 21  Report(体检报告)
  10 SMART                 22  Deep(深度诊断)
  11 Dataset Analyzer      23  Profile(备份配置)
  12 Version               24  Trend(趋势与预测)
                           0   Exit

用法:
  zfs-tool.py                交互菜单
  zfs-tool.py <命令> [选项]   直接执行
  常用选项: -p/--pool P  -d/--dataset D  --json

环境变量: ZT_CONF_DIR 配置目录(默认 /etc/zfs-tool, 回退 ~/.config/zfs-tool)
          告警阈值/[smtp] 邮件通知可用 zfs-tool.conf 配置。

v5.1 新增:
  * SMTP 邮件通知(告警去重/冷却, notify-test 测试)
  * 容量趋势落库与满盘日期预测(trend / trend-collect)
  * 磁盘 SMART 关键属性趋势预警(smart-trend)
  * 多频快照策略 hourly/daily/weekly/monthly(snap-auto <ds> [keep] [label])
  * Profile: 传输限速(pv)/断点续传(-s)/发送后校验/批量 backup-all
  * 体检报告同时输出 .html; systemd timer 模板(替代/补充 crontab)
"""

import os
import re
import sys
import json
import shutil
import signal
import subprocess
import time
from datetime import datetime

# 统一 UTF-8 输出, 避免 GBK/locale 控制台打印 emoji 时报 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION = "6.2"          # C8-VERSION-6.2
PROG = "zfs-tool"

# ---------------------------------------------------------------------------
# 路径与配置
# ---------------------------------------------------------------------------

ENV_LOG_DIR = os.environ.get("ZT_LOG_DIR", "/var/log/zfs-tools")
CONF_DIR = os.environ.get(
    "ZT_CONF_DIR",
    "/etc/zfs-tool" if os.path.isdir("/etc") else os.path.expanduser("~/.config/zfs-tool"),
)
CONF_FILE = os.path.join(CONF_DIR, "zfs-tool.conf")

# 阈值(可被配置文件/环境覆盖)
CONF = {
    "log_dir": ENV_LOG_DIR,
    "log_max": 1024 * 1024,
    "warn_cap": 80,
    "crit_cap": 90,
    "warn_frag": 40,
    "crit_frag": 60,
    # 全 SSD 池的碎片阈值：SSD 无寻道成本，碎片率对性能无意义；
    # recordsize 8K + docker 这类小记录负载天生碎片偏高，zpool rewrite 也缓解不了
    # (还磨损寿命) ⇒ 全 SSD 池只在 >= frag_ssd_warn 时给一条 INFO，绝不发 WARN。
    "frag_ssd_warn": 90,
    # scrub 阈值与外部巡检脚本统一为 35/60(原来这里是 30/60)
    "scrub_warn_days": 35,
    "scrub_crit_days": 60,
    # 磁盘预测: 重分配扇区增量超过该值视为预警
    "smart_realloc_step": 5,
    "smart_pending_crit": 20,
    # 邮件/通知去重冷却秒数(同一摘要重复告警在此时间内不再发送)
    "notify_cooldown": 6 * 3600,
}

# [smtp] 配置节
SMTP_CONF = {
    "host": "",
    "port": 587,
    "user": "",
    "password": "",
    "from": "",
    "to": "",
    "tls": True,
    "enabled": False,
}


# 修复: 配置默认值快照 —— 在 load_conf() 之前取一次(那时 dict 里还是代码
#   里的默认值), 供 _conf_int() 转换失败时回落。
_CONF_INT_DEFAULTS = ((CONF, dict(CONF)), (SMTP_CONF, dict(SMTP_CONF)))


def _conf_int(d, key):
    # 修复: 原来转换失败静默 `pass` —— 坏值以字符串留在 dict 里, 之后每次
    #   log() 都在 int(CONF["log_max"]) 上抛 ValueError(log() 的 try 只接 OSError),
    #   而 log() 几乎每个操作都会调(含 pool destroy) ⇒ conf 里一个 `log_max=1M`
    #   笔误就能炸掉全部操作。改为: 转换失败回落该键的默认值并留痕。
    raw = d.get(key)
    try:
        d[key] = int(raw)
        return d[key]
    except (TypeError, ValueError):
        for _d, _snap in _CONF_INT_DEFAULTS:
            if _d is d and key in _snap:
                d[key] = _snap[key]
                print("警告: 配置项 %s=%r 不是整数, 已回落默认值 %r"
                      % (key, raw, _snap[key]))
                return d[key]
        print("警告: 配置项 %s=%r 不是整数, 且无默认值, 已忽略" % (key, raw))
        return None


def load_conf():
    """读取 zfs-tool.conf:
    - 顶层 key=value 合并到 CONF(阈值等)
    - [smtp] 段合并到 SMTP_CONF(邮件)
    其他 [section] 暂忽略。文件缺失时静默。"""
    section = None
    try:
        with open(CONF_FILE, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().lower()
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().replace("-", "_")
                val = val.strip()
                if section == "smtp":
                    SMTP_CONF[key] = val
                elif section is None and key in CONF:
                    CONF[key] = val
    except OSError:
        pass
    # 类型收尾
    _conf_int(CONF, "warn_cap")
    _conf_int(CONF, "crit_cap")
    _conf_int(CONF, "warn_frag")
    _conf_int(CONF, "crit_frag")
    _conf_int(CONF, "frag_ssd_warn")
    _conf_int(CONF, "scrub_warn_days")
    _conf_int(CONF, "scrub_crit_days")
    _conf_int(CONF, "smart_realloc_step")
    _conf_int(CONF, "smart_pending_crit")
    _conf_int(CONF, "notify_cooldown")
    # 修复: log_max 原来漏在这份清单外 —— 它的坏值不会被回落,
    #   而 log() 几乎每个操作都会读到它。
    _conf_int(CONF, "log_max")
    _conf_int(SMTP_CONF, "port")
    SMTP_CONF["tls"] = str(SMTP_CONF.get("tls", "true")).lower() in ("1", "true", "yes", "on")
    SMTP_CONF["enabled"] = bool(SMTP_CONF.get("host") and SMTP_CONF.get("from")
                                and SMTP_CONF.get("to"))


load_conf()

DATA_DIR = os.path.join(CONF_DIR, "data")
LOG_FILE = os.path.join(CONF["log_dir"], "zfs-tool.log")

# ---------------------------------------------------------------------------
# 颜色 (非 TTY 自动关闭)
# ---------------------------------------------------------------------------

COLOR = bool(sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb")

_C = {
    "reset": "\033[0m",
    "red": "\033[1;31m",
    "green": "\033[1;32m",
    "yellow": "\033[1;33m",
    "blue": "\033[1;34m",
    "cyan": "\033[1;36m",
    "white": "\033[1;37m",
}

LINE = "━" * 44
LINE_SHORT = "━" * 36


def c(kind, text=""):
    if not COLOR:
        return text
    return _C.get(kind, "") + text + _C["reset"]


_LOG_WRITE_FAILED = False       # 写日志失败只告警一次(见 log())


def log(msg):
    """追加一行日志(带轮转)。

    🩸 修复：原来 `except OSError: pass` 把"写日志失败"
    **完全吞掉** —— 而 `--yes` 的"自动确认留痕"（`DESTRUCTIVE auto-confirmed by --yes`）
    也走这里 ⇒ "日志里应该有痕迹"这件事可能**根本不成立**。现在失败时向 stderr
    告警一次（只一次，不刷屏）。
    """
    global _LOG_WRITE_FAILED
    try:
        os.makedirs(CONF["log_dir"], exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > int(CONF["log_max"]):
            os.replace(LOG_FILE, LOG_FILE + ".old")
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError as exc:
        if not _LOG_WRITE_FAILED:
            _LOG_WRITE_FAILED = True
            try:
                sys.stderr.write("警告: 写日志失败(%s): %s —— 本次运行的操作痕迹可能"
                                 "没有落盘\n" % (exc, CONF["log_dir"]))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 子进程封装
# ---------------------------------------------------------------------------


def run(cmd, check=None, stdin_data=None, timeout=None):
    """运行命令。cmd 为 argv 列表(天然防注入)。
    返回 CompletedProcess; 命令缺失/无法启动返回 None。

    🆕 新增: 加可选 `timeout`（秒）。`scrub wait` 动辄几小时、`zfs send -n`
    在大池上也可能很慢 —— **绝不能挂在工具超时上**（本工具的非阻塞执行约定）。
    超时返回 `returncode=124` 的 CompletedProcess（与 `timeout(1)` 同口径），
    调用方按普通失败处理即可，不必各自 try/except。"""
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
          "text": True, "encoding": "utf-8", "errors": "replace"}
    if stdin_data is not None:
        kw["input"] = stdin_data
    # 🩸 修复：原来写 `if timeout:` —— `timeout=0` 会被静默吞掉。
    if timeout is not None:
        kw["timeout"] = timeout
    try:
        return subprocess.run(cmd, **kw)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "",
                                           "命令超时(超过 %s 秒)" % timeout)
    except OSError:
        return None


def run_noblock(cmd, timeout=120):
    """带死线的子进程执行 —— 与 `run()` 的区别是**超时后绝不 `wait()`**。

    🩸 修复：`subprocess.run(timeout=)` 在 POSIX 超时分支是
    `process.kill()` 之后 `process.wait()`；而**D 状态（不可中断 I/O 睡眠）**的进程
    收到 SIGKILL 只会保持 pending ⇒ `wait()` 永久阻塞，超时异常根本抛不出来，
    于是"加了超时"反而是把工具挂死。这里超时后直接返回 `rc=124`，
    残留子进程交给 init 回收（并在 stderr 里提示用户自查）。
    返回 `CompletedProcess`；命令无法启动返回 `None`。
    """
    try:
        # 🩸 修复：独立进程组 —— 超时时可以**整组**收拾（含孙进程），
        #   否则 `p.kill()` 只打死直接子进程，实测有 2 个孤儿 `sleep` 逃逸。
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace",
                             start_new_session=True)
    except OSError:
        return None
    try:
        o, e = p.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, p.returncode, o, e)
    except subprocess.TimeoutExpired as exc:
        # 🩸 修复（低）：**先留下已经拿到的输出** —— POSIX 上
        #   `communicate()` 会把"超时前已读到的部分"放进 `TimeoutExpired`。
        #   原来一律丢成空串 ⇒「空输出」与「命令本来没输出」不可区分，
        #   这正是那条误判（读不到 ⇒ 当作"没有"）的根因之一。
        part_out = exc.output or ""
        part_err = exc.stderr or ""
        if isinstance(part_out, bytes):
            part_out = part_out.decode("utf-8", "replace")
        if isinstance(part_err, bytes):
            part_err = part_err.decode("utf-8", "replace")
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)   # 尽力而为；D 状态时只 pending
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        # 🩸 绝不 p.wait() / p.communicate()：那正是会永久阻塞的地方。
        return subprocess.CompletedProcess(
            cmd, 124, part_out,
            (part_err + "\n" if part_err else "")
            + "命令在 %s 秒内未返回。⚠ **超时不等于未生效**（长任务可能只是慢）——"
              "请先用只读命令核实（如 `zfs-tool.py scrub status` / `zpool status`）"
              "再决定是否重试；若池/盘处于 D 状态(I/O 卡死)，子进程可能无法终止，"
              "可用 `ps -o pid,stat,cmd` 复查。" % timeout)


def out(cmd, text=True):
    """返回 stdout 文本(失败/缺失返回空串)。"""
    p = run(cmd)
    if p is None or p.returncode != 0:
        return ""
    s = p.stdout or ""
    if isinstance(s, bytes):
        s = s.decode("utf-8", "replace")
    return s


def have(cmd):
    return shutil.which(cmd) is not None


def is_num(s):
    return bool(re.fullmatch(r"[0-9]+", s or ""))


# ---------------------------------------------------------------------------
# ZFS 数据层
# ---------------------------------------------------------------------------


def get_pools():
    """全部 Pool 名(按 zpool list 顺序)。"""
    text = out(["zpool", "list", "-H", "-o", "name"])
    return [ln for ln in text.splitlines() if ln.strip()]


def pool_exists(pool):
    if not pool:
        return False
    p = run(["zpool", "list", pool])
    return p is not None and p.returncode == 0


def ds_exists(ds):
    if not ds:
        return False
    p = run(["zfs", "list", ds])
    return p is not None and p.returncode == 0


def ds_prop(ds, prop):
    """取单属性值, 失败返回 ''。"""
    return out(["zfs", "get", "-H", "-o", "value", prop, ds]).strip()


def top_datasets():
    """顶层数据集(filesystem+volume), 按名称排序。"""
    text = out(["zfs", "list", "-H", "-o", "name", "-t", "filesystem,volume"])
    return [ln for ln in text.splitlines() if ln.strip()]


def snapshots(ds):
    """数据集全部快照名(创建时间从新到旧)。"""
    text = out(["zfs", "list", "-H", "-t", "snapshot", "-r", ds, "-o", "name", "-S", "creation"])
    return [ln for ln in text.splitlines() if ln.strip()]


def ds_children(ds):
    text = out(["zfs", "list", "-H", "-r", "-o", "name", ds])
    return [ln for ln in text.splitlines() if ln.strip()]


def human_gib(n):
    try:
        return "%.2f" % (int(n) / 1024 / 1024 / 1024)
    except (TypeError, ValueError):
        return "0.00"


def hit_rate(hits, misses):
    try:
        h, m = int(hits), int(misses)
    except (TypeError, ValueError):
        return "N/A"
    if h + m <= 0:
        return "N/A"
    return "%.2f%%" % (h * 100.0 / (h + m))


# --- arcstats ---------------------------------------------------------------

ARC_KEYS = ("size c_max c hits misses l2_hits l2_misses "
            "l2_size l2_asize mfu_size mru_size metadata_size").split()
ARCSTATS = "/proc/spl/kstat/zfs/arcstats"


def arc_stats():
    """读 arcstats 关键键值(不存在返回空 dict)。"""
    data = {}
    try:
        with open(ARCSTATS, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                parts = ln.split()
                if len(parts) >= 3 and parts[0] in ARC_KEYS:
                    data[parts[0]] = parts[2]
    except OSError:
        pass
    for k in ARC_KEYS:
        data.setdefault(k, "0")
    return data


# --- smartctl ---------------------------------------------------------------


def smart_devices():
    """smartctl --scan-open 结果: [(dev, [args...]), ...]"""
    rows = []
    p = run(["smartctl", "--scan-open"])
    if p is None or p.returncode != 0:
        return rows
    for raw in p.stdout.splitlines():
        raw = raw.split("#", 1)[0].strip()
        if not raw:
            continue
        fields = raw.split()
        dev, args = fields[0], fields[1:]
        rows.append((dev, args))
    return rows


def smart_temp(dev, args):
    """读取温度(整数), 失败返回 None。兼容 SATA/NVMe/SCSI 行尾括号注释。"""
    p = run(["smartctl", "-A", dev] + list(args))
    if p is None or p.returncode != 0:
        return None
    for ln in p.stdout.splitlines():
        if re.search(r"Temperature_Celsius|Airflow_Temperature_Cel|Composite Temperature|Temperature:", ln):
            head = ln.split("(", 1)[0]
            nums = re.findall(r"\d+", head)
            if nums:
                return int(nums[-1])
    return None


# --- zpool status -----------------------------------------------------------


def _state_lines(text):
    """把 zpool status 中 vdev 区的状态行解析成列表:
    [(name, state, read, write, cksum), ...] 仅含五列数字行。"""
    rows = []
    started = False
    for ln in text.splitlines():
        if ln.startswith("config:"):
            started = True
            continue
        if not started:
            continue
        if ln.strip().startswith(("errors:", "actions:")):
            break
        fields = ln.split()
        if len(fields) >= 5 and re.fullmatch(r"\d+", fields[2]) \
                and re.fullmatch(r"\d+", fields[3]) and re.fullmatch(r"\d+", fields[4]):
            rows.append((fields[0], fields[1], int(fields[2]), int(fields[3]), int(fields[4])))
    return rows


def pool_scan_line(pool):
    """返回 zpool status 中 scan:/resilver 行(无则空串)。"""
    # 🩸 修复：只读查询也会卡在 D 状态 ⇒ 走带死线的 run_noblock；
    #   超时等同于"读不到"（返回空串），绝不把工具一起挂住。
    _p = run_noblock(["zpool", "status", pool], timeout=20)
    text = "" if _p is None or _p.returncode == 124 else (_p.stdout or "")
    for ln in text.splitlines():
        if re.match(r"\s*scan:", ln):
            return ln.strip()
    return ""


def scrub_age_days(pool):
    """最近一次 Scrub 距今的天数。进行中返回 0, 无法解析返回 None。"""
    line = pool_scan_line(pool)
    if not line:
        return None
    if "in progress" in line:
        return 0
    m = re.search(r"\bon\s+(.*)$", line)
    if not m:
        return None
    stamp = m.group(1).strip()
    try:
        dt = datetime.strptime(stamp, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        try:
            dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    days = int((datetime.now() - dt).total_seconds() // 86400)
    return max(days, 0)


def pool_io_snapshot(pool):
    """单池瞬时 IO: 返回 (read_mb, write_mb) 或 None。"""
    # 修复: 原来取 f[3]/f[4] —— 那是 operations(IOPS), 却除以 1048576
    # 当 MB/s 用 → dashboard 恒显示 `0.00 MB/s`(个位数 IOPS 除 2^20 必为 0)。
    # `zpool iostat` 7 列行序为 alloc free read-ops write-ops read-bw write-bw,
    # 带宽是 f[5]/f[6]; 配 -p 时其为"字节/秒", 除 1048576 才是 MB/s。
    # (列序依据 Oracle ZFS 管理指南示例 + 真机恒 0.00 的旁证,
    #  标注"需真机复核"。)
    p = run(["zpool", "iostat", "-p", "-y", pool, "1", "1"])
    if p is None or p.returncode != 0:
        return None
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    if not lines:
        return None
    f = lines[-1].split()
    if len(f) < 7:
        return None          # 不足 7 列 → 不是完整数据行(保留 -y 的瞬时采样行)
    try:
        return int(f[5]) / 1048576.0, int(f[6]) / 1048576.0
    except (ValueError, IndexError):
        return None          # 列值非数字(如 `-`) → 交调用方显示 N/A, 不再谎报 0.00


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def _cls():
    """ANSI 清屏(不依赖外部 clear/cls, 管道/非 tty 下无害)。"""
    if sys.stdout.isatty():
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


def title(text, sub=None):
    _cls()
    print(c("cyan", LINE))
    print(c("white", text))
    if sub:
        print(c("yellow", sub))
    print(c("cyan", LINE))
    print()


def pause():
    # 🩸 复验：判据必须**同时**看 stdin 与 stdout ——
    #   在"有控制终端但 stdout 被重定向"的脚本形态下（`script -qec "… > log"`、
    #   部分 CI / sudo 保留 pty），光看 `stdin.isatty()` 仍会 `input()` 并
    #   **永久阻塞**（实测 timeout rc=124）。只有两者都是 tty（真正交互会话）才等。
    try:
        if not (sys.stdout.isatty() and sys.stdin.isatty()):
            return
    except (OSError, ValueError):
        return
    try:
        input(c("cyan", "按 Enter 返回..."))
    except (EOFError, KeyboardInterrupt):
        pass


def cli_hint(lines, header="CLI 直达命令"):
    """打印「菜单项 ↔ 等价命令行」提示。

    🆕 交互优化 ④：原来菜单层级很深(维护模式要点 8→3→4), 却从不告诉
    用户"这件事对应的命令是什么"。这里把等价命令直接标在菜单下面, 让人**能直达**、
    也便于把习惯的动作写进脚本。非 tty 下同样打印(日志/管道里也能检索)。
    """
    if not lines:
        return
    print(c("dim", "  %s:" % header))
    for key, text in lines:
        if key:
            print(c("dim", "    %-3s %s" % (key + ".", text)))
        else:
            print(c("dim", "    %s" % text))


def paged(text, threshold=40):
    """长输出分页：交互终端里超过 `threshold` 行就交给分页器。

    🆕 交互优化 ⑤：长输出(历史/深度诊断等)原来一次性刷屏。
    ⚠️ 只在**真交互终端**下分页 —— 管道 / cron / `zfs-tool.py hist > f.txt`
    一律直出全文，免得脚本里出现"卡在 less 里等人按键"。
    分页器取 `$PAGER`(默认 less)，起不来就退回普通打印。
    """
    argv = (os.environ.get("PAGER") or "less").split() or ["less"]
    if os.path.basename(argv[0]) == "less":
        # -R 保留颜色 · -F 一屏装得下直接退出 · -X 不清屏
        argv = argv + ["-R", "-F", "-X"]
    if sys.stdout.isatty() and len(text.splitlines()) > threshold:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace")
            proc.communicate(text)
            return
        except OSError:
            pass
    print(text)


def ask(prompt):
    # 🩸 复验：真正会挂住脚本的不是 `pause()`，而是这里的 `input()` ——
    #   在"**有控制终端但 stdout 被重定向**"的自动化形态下（`script -qec "… > log"`、
    #   部分 CI / sudo 保留 pty），`input()` 会**永久等人按键**（实测 `timeout` rc=124）。
    #   判据：stdout 不是 tty（没人在看输出）而 stdin 却是终端 ⇒ 这是自动化形态
    #   ⇒ 直接返回空，绝不阻塞。正常交互终端（两者都是 tty）行为不变。
    try:
        if not sys.stdout.isatty() and sys.stdin.isatty():
            return ""
    except (OSError, ValueError):
        return ""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def ask_yes(prompt):
    if FLAG_ASSUME_YES:
        print(c("yellow", "[--yes] 自动确认: " + prompt))
        return True
    return ask(prompt).lower() in ("y", "yes")


def require_root():
    if not _am_root():
        print(c("red", "需要 root 权限"))
        sys.exit(1)


def _am_root():
    """跨平台 root 判断: 非 POSIX(如 Windows 测试环境)一律放行。"""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return True


def _shq(s):
    import shlex
    return shlex.quote(str(s))


def require_pools():
    if not get_pools():
        print(c("red", "系统中没有任何 Pool"))
        return False
    return True


# --- 字母快捷选择 -----------------------------------------------------------


def _disp_len(s):
    """估算字符串的终端显示宽度(中文/emoji/全角按 2 列)。"""
    w = 0
    for ch in s:
        o = ord(ch)
        if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3
                or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F
                or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6
                or 0x20000 <= o <= 0x2FFFD or 0x1F000 <= o <= 0x1FAFF
                or 0x2600 <= o <= 0x27BF):
            w += 2
        else:
            w += 1
    return w


def _pad(s, width):
    """按显示宽度把 s 补齐到 width。"""
    return s + " " * max(0, width - _disp_len(s))


def pick_from_list(title_msg, items, auto_msg="仅一项, 自动选择"):
    """字母/数字快捷选择。返回 (ok, chosen)。
    ok=True 且 chosen 为选定条目; 若输入未命中列表的原样文本, chosen 即该文本。"""
    items = [i for i in items if i]
    if not items:
        print(c("red", "没有可选项目"))
        return False, ""
    if len(items) == 1:
        print(c("cyan", auto_msg + ":") + " " + items[0])
        return True, items[0]

    print()
    print(c("yellow", "%s (共 %d 个):" % (title_msg, len(items))))
    for i, it in enumerate(items):
        if i >= 26:
            print("    (项目超过 26 个, 其余请直接输入名称)")
            break
        print("   %s) %s" % (chr(65 + i), it))
    print()
    sel = ask("选择 [字母/数字] 或直接输入名称(回车取消): ")
    if not sel:
        return False, ""
    sel = sel.upper()
    if re.fullmatch(r"[A-Z]", sel):
        idx = ord(sel) - 65
        if idx < len(items):
            return True, items[idx]
        print(c("red", "选择超出范围 (1-%d)" % len(items)))
        return False, ""
    if is_num(sel):
        idx = int(sel, 10) - 1
        if 0 <= idx < len(items):
            return True, items[idx]
        print(c("red", "选择超出范围 (1-%d)" % len(items)))
        return False, ""
    return True, sel  # 视为直接输入的名称, 交给调用方校验


TARGET_POOL = ""
TARGET_DS = ""


def ask_pool(prompt="Pool名称"):
    """选择 Pool: 优先 CLI -p, 其次唯一池自动, 再字母列表/直输。返回名称或 ''。"""
    global TARGET_POOL
    if TARGET_POOL:
        if pool_exists(TARGET_POOL):
            print("使用 Pool: " + TARGET_POOL)
            return TARGET_POOL
        print(c("red", "Pool 不存在: " + TARGET_POOL))
        TARGET_POOL = ""
        return ""
    pools = get_pools()
    if not pools:
        print(c("red", "系统中没有任何 Pool"))
        return ""
    ok, chosen = pick_from_list(prompt, pools, auto_msg="仅一个 Pool, 自动选择")
    if not ok:
        return ""
    if not pool_exists(chosen):
        print(c("red", "Pool 不存在: " + chosen))
        return ""
    print(c("cyan", "已选择 Pool:") + " " + chosen)
    return chosen


def ask_dataset(prompt="选择数据集"):
    """选择 Dataset: 先试完整名直输; 回车则浏览顶层列表, 可逐级下钻子路径。"""
    global TARGET_DS
    if TARGET_DS:
        if ds_exists(TARGET_DS):
            print("使用 Dataset: " + TARGET_DS)
            return TARGET_DS
        print(c("red", "数据集不存在: " + TARGET_DS))
        TARGET_DS = ""
        return ""

    ans = ask("%s [输入完整名, 或回车浏览]: " % prompt)
    if ans:
        if ds_exists(ans):
            return ans
        print(c("red", "数据集不存在: " + ans))
        return ""

    tops = top_datasets()
    if not tops:
        print(c("red", "系统中没有任何数据集"))
        return ""
    ok, chosen = pick_from_list("顶层数据集", tops)
    if not ok:
        return ""
    if not ds_exists(chosen):
        print(c("red", "数据集不存在: " + chosen))
        return ""
    ds = chosen
    print(c("cyan", "已选择:") + " " + ds)
    while True:
        sub = ask("继续下钻子路径 [如 vm/win; 回车=使用当前 %s]: " % ds)
        if not sub:
            break
        cand = ds + "/" + sub.lstrip("/")
        if ds_exists(cand):
            ds = cand
            print(c("cyan", "→") + " " + ds)
        else:
            print(c("yellow", "子路径不存在: %s (仍停留在 %s)" % (cand, ds)))
    return ds


# ---------------------------------------------------------------------------
# 破坏性操作确认
# ---------------------------------------------------------------------------


def confirm_destructive(desc):
    print()
    print(c("red", "⚠ 即将执行: %s" % desc))
    print(c("red", "⚠ 此操作可能造成数据丢失, 且不可恢复!"))
    if FLAG_ASSUME_YES:
        # 不可逆操作被 --yes 自动放行时, 必须**留痕**(日志里能查到是谁在什么时候放过的)
        print(c("yellow", "[--yes] 已自动确认**不可逆操作** —— 请确认你确实知道自己在做什么"))
        log("DESTRUCTIVE auto-confirmed by --yes: " + desc)
        return True
    if not ask_yes("第一次确认 (输入 yes): "):
        return False
    if not ask_yes("第二次确认 (再输入 yes): "):
        return False
    return True


def confirm_single(desc):
    print()
    print(c("yellow", "即将执行: %s" % desc))
    return ask_yes("确认执行? (yes): ")


# ---------------------------------------------------------------------------
# 菜单分发
# ---------------------------------------------------------------------------


def main_menu():
    # 🩸 修复：主菜单原来**丢弃**每个子功能的返回值
    #   （`fn()` 调完就算），并且 `0. Exit` 写死 `sys.exit(0)` ⇒ 即使子命令
    #   （如 `cmd_scrub()`）内部已经算出失败码，交互式走完菜单后进程退出码仍是 0。
    #   真机复验就是这么抓到的：屏幕上打印了「回读自证未通过」，退出码却是 0。
    menu_rc = 0
    while True:
        title("🧰 ZFS 工具箱 v%s" % VERSION, "by CNyaotian with DeepSeek")
        if _quiesce_guard():
            continue   # 刚执行过恢复, 清屏重绘干净的主菜单
        left = [
            ("1.", "📊 仪表盘"), ("2.", "💾 ARC/L2ARC 缓存"),
            ("3.", "❤️ 健康检查"), ("4.", "📈 I/O 监控"),
            ("5.", "📸 快照管理"), ("6.", "🧹 Scrub 清理"),
            ("7.", "✂ TRIM 回收"), ("8.", "📉 碎片/重写工具"),
            ("9.", "🗜 去重 Dedup"), ("10.", "💽 SMART 监测"),
            ("11.", "📂 数据集分析器"), ("12.", "ℹ 版本信息"),
        ]
        right = [
            ("13.", "⏳ 活动进度"), ("14.", "🔐 加密管理"),
            ("15.", "🗄 Pool 管理"), ("16.", "📁 数据集管理"),
            ("17.", "🚨 告警检查"), ("18.", "🩺 环境自检"),
            ("19.", "📜 历史与日志"), ("20.", "⏰ 计划任务"),
            ("21.", "📄 体检报告"), ("22.", "🔬 深度诊断"),
            ("23.", "💾 备份 Profile"), ("24.", "📈 趋势预测"),
        ]
        print()
        for (ln, ll), (rn, rl) in zip(left, right):
            print(_pad(" %s %s" % (ln, ll), 32) + " %s %s" % (rn, rl))
        print()
        print(" 0. Exit" + _pad("", 14) + "25. 🛠 fnOS 存储/TPM" + _pad("", 6) +
              "h/? 帮助  c 命令对照")
        print()
        choice = ask("选择功能: ").lower()
        mapping = {
            "1": cmd_dashboard, "2": cmd_arc, "3": cmd_health, "4": cmd_iostat,
            "5": cmd_snapshot, "6": cmd_scrub, "7": cmd_trim, "8": cmd_frag,
            "9": cmd_dedup, "10": cmd_smart, "11": cmd_dataset, "12": cmd_version,
            "13": cmd_progress, "14": cmd_encrypt, "15": cmd_poolmgr,
            "16": cmd_dsmgr, "17": cmd_alerts, "18": cmd_doctor, "19": cmd_hist,
            "20": cmd_schedule, "21": cmd_report, "22": cmd_deep, "23": cmd_profile,
            "24": trend_report, "25": cmd_fnos_menu,
        }
        if choice in ("h", "help", "?"):
            usage()
            pause()
            continue
        if choice == "c":
            # 🆕 交互优化 ④: 菜单号 ↔ CLI 命令对照, 让人能从菜单直达命令
            cmd_cli_map()
            continue
        if choice == "0":
            sys.exit(menu_rc)      # 🩸 修复：带出"最近一次非零返回码"
        fn = mapping.get(choice)
        if fn:
            _r = fn()
            # 🩸 修复：记住最近一次非零码（0/None 不覆盖，便于人连续操作）
            if isinstance(_r, int) and _r != 0:
                menu_rc = _r
        else:
            print("无效选择")
            try:
                __import__("time").sleep(1)
            except Exception:
                pass


# 下面各模块中的命令函数由后续文件段落定义, 避免名称前向引用问题,
# 统一在本文件底部按模块汇总。见 cmd_* 函数定义。

# ===========================================================================
# 命令: version / doctor / usage
# ===========================================================================

FLAG_JSON = False          # --json 输出(由 CLI 解析时设置)
# 干跑预览开关(--dry-run / -n), 由 CLI 解析时设置。
# 🩸 规矩: 这个开关**只用命令行参数**实现, 不用环境变量 ——
#    `VAR=1 sudo cmd` 时 sudo 默认不把 VAR 传给子进程, 会导致"以为在预览、其实真执行"。
FLAG_DRY = False
# 🆕 显式同意开关(--yes / -y): 让**脚本化**有正当入口, 替代过去那种"非 tty 默默同意"。
#    它只影响 ask_yes / confirm_*; 且对不可逆操作会**写日志留痕**(见 confirm_destructive)。
FLAG_ASSUME_YES = False


def cmd_version():
    title("ℹ ZFS 版本信息", "内核 / ZFS 用户态与模块版本信息")
    print()
    print("Kernel:")
    print(out(["uname", "-r"]) or "unknown")
    print()
    print("ZFS:")
    print(out(["zfs", "--version"]) or "unknown")
    print()
    print("ZPool:")
    print(out(["zpool", "version"]) or "unknown")
    print()
    print("Kernel Module ZFS:")
    mod = ""
    try:
        with open("/sys/module/zfs/version", encoding="utf-8") as fh:
            mod = fh.read().strip()
    except OSError:
        mod = ""
    print(mod or "unknown")
    print()
    pause()


CORE_BINS = ["zpool", "zfs", "awk", "sed", "grep", "date", "stat"]
OPT_BINS = ["smartctl", "mpstat", "top", "ssh", "pv", "zfs-dedup"]


def cmd_doctor():
    title("🩺 zfs-tool 环境自检", "核心 / 可选依赖与运行环境检查")
    okc = warnc = errc = 0

    def check(name, core=False):
        nonlocal okc, warnc, errc
        if have(name):
            print("  " + c("green", "✔") + " " + name)
            okc += 1
        elif core:
            print("  " + c("red", "✖") + " " + name + " (缺失!)")
            errc += 1
        else:
            print("  " + c("yellow", "-") + " " + name + " (未安装, 相关功能不可用)")
            warnc += 1

    print()
    print(c("white", "核心依赖:"))
    for b in CORE_BINS:
        check(b, core=True)
    print()
    print(c("white", "可选依赖:"))
    for b in OPT_BINS:
        check(b)

    print()
    print(c("white", "环境检查:"))
    try:
        os.makedirs(CONF["log_dir"], exist_ok=True)
        print("  " + c("green", "✔") + " 日志目录可写: " + str(CONF["log_dir"]))
    except OSError:
        print("  " + c("red", "✖") + " 日志目录不可写: " + str(CONF["log_dir"]))
        errc += 1
    if os.path.exists(ARCSTATS):
        print("  " + c("green", "✔") + " arcstats 可读")
    else:
        print("  " + c("yellow", "-") + " 无 arcstats(非 OpenZFS 内核环境?)")
        warnc += 1
    if have("smartctl"):
        n = len(smart_devices())
        print("  " + c("green", "✔") + " smartctl 扫描到约 %d 个设备" % n)

    print()
    print("结果: 正常 %d / 可选缺失 %d / 严重缺失 %d" % (okc, warnc, errc))
    if errc:
        print(c("red", "存在严重缺失, 请先安装对应工具"))
    else:
        print(c("green", "核心依赖完整"))
    pause()


def _fnos_runtime_cmds():
    """内嵌 zt_fnos 模块注册的子命令名(已排序)。

    修复: usage() 原来硬编码只列 8 个 fnOS 子命令, 而 FNOS_CMDS 实有
    44 个(TPM 侧 27 个一个没列)。这里改为从内嵌模块的 SUBCMDS 运行时枚举,
    避免再次过期; 任何失败都降级为 [] (不影响 help 主流程)。
    """
    try:
        mod = _load_zt_fnos()
        names = getattr(mod, "SUBCMDS", None) if mod is not None else None
        if not names:
            return []
        return sorted(names)
    except Exception:
        return []


def _print_fnos_help_fallback():
    print("  (完整子命令清单可在能加载 zt_fnos 的环境执行: zt_fnos.py help)")


def _print_fnos_cmd_list():
    names = _fnos_runtime_cmds()
    if not names:
        _print_fnos_help_fallback()
        return
    print("  zt_fnos 子命令共 %d 个(zt_fnos.py help 看用法):" % len(names))
    for i in range(0, len(names), 6):
        print("    " + " ".join(names[i:i + 6]))
    print("  提示: 这些子命令的参数原样透传; -p/--pool 会被一并透传给 zt_fnos")


def usage():
    print("zfs-tool v%s — ZFS 运维管理工具箱 (Python)" % VERSION)
    print()
    print("用法:")
    print("  zfs-tool.py                 交互菜单")
    print("  zfs-tool.py <命令> [选项]")
    print("  选项: -p/--pool P  -d/--dataset D  --json  --dry-run(-n)  --yes(-y)")
    print("        --dry-run 只预览不执行；--yes 非交互显式同意(供脚本/定时任务用)")
    print()
    print("基础:")
    print("  dashboard       综合仪表盘(带告警摘要)")
    print("  arc             ARC/L2ARC 统计与实时监控")
    print("  health          Pool 健康检查")
    print("  iostat          I/O 实时监控(带宽视角)")
    print("  lat             延迟归因: lat [-p P] [--queue] [--req] [--hist] "
          "[--interval N] [--count N] [--json]")
    print("  checkpoint      池级回滚点: checkpoint [status|create|discard|rollback] [池名]")
    print("  frag            碎片率与建议")
    print("  rewrite         数据重写(OpenZFS 2.4+): rewrite <路径> [-r] [-P] [-v]")
    print("  quiesce         维护模式: quiesce on|off|status|check (暂停/恢复相册·影视·应用·docker; check=覆盖体检)")
    print("  dedup           zfs-dedup(离线去重)")
    print("  version         版本信息")
    print()
    print("快照/备份:")
    print("  snapshot        快照管理菜单")
    print("  snapdiff        快照 diff 对比")
    print("  rollback        回滚快照(双重确认)")
    print("  backup          zfs send/recv 备份向导")
    print("  send-file       快照发送到 .zfs 文件(冷备) [--raw|-w] [--compressed|-c]")
    print("                  [--replicate|-R] [--holds|-h] [-i 基准] [源快照] [目标文件]")
    print("  recv-file       从 .zfs 文件恢复到数据集")
    print("  resume          中断接收的续传: resume [数据集] [--show-token]")
    print("  prune           快照保留清理(最近 N 份)")
    print()
    print("运维:")
    print("  scrub/trim      Scrub / TRIM 管理")
    print("  scrub <子命令>  start|stop|pause|resume|resume-e|continue|errors|range|wait|status [池名]")
    print("                  暂停 -p / 从上次位置续扫 -C / 只扫坏块 -e / 按日期 -S -E / 等待 -w")
    print("  smart           SMART 监控/自检")
    print("  encrypt         加密密钥管理")
    print("  poolmgr         Pool/磁盘管理(含 L2ARC/SLOG/删池)")
    print("  pool-destroy    删除存储池(双重确认+输名校验)")
    print("  l2arc-add       添加 L2ARC 缓存盘")
    print("  slog-add        添加 SLOG 日志盘")
    print("  l2arc-mode      L2ARC 策略: 对数据集设 secondarycache=all|metadata|none")
    print("  dsmgr           Dataset/zvol 管理")
    print("  dataset         数据集分析器")
    print("  progress        进行中的 scrub/resilver/trim")
    print("  doctor          依赖自检")
    print("  hist            历史与日志")
    print()
    print("新增:")
    print("  alerts          阈值告警(退出码 0/1/2, --json, SMTP 通知)")
    print("  schedule        计划任务生成/安装(crontab / systemd)")
    print("  report          体检报告导出(txt+html)")
    print("  deep            深度诊断(zil/ARC/扩展性/Top 榜)")
    print("  profile         备份 Profile 菜单")
    print("  profile-run     按名执行备份: profile-run <name>")
    print("  backup-all      执行全部备份 Profile")
    print("  trend           容量趋势与满盘预测报告")
    print("  trend-collect   采集趋势样本(建议 cron 每日)")
    print("  smart-trend     磁盘 SMART 属性趋势预警(建议 cron)")
    print("  notify-test     发送 SMTP 测试邮件")
    print()
    print("供 cron/脚本的非交互命令:")
    print("  scrub-run <pool>       启动 Scrub")
    print("  snap-auto <ds> [keep] [label]  快照+保留(label: hourly/daily/...)")
    print("  status [--json]        Pool/告警汇总(JSON)")
    print()
    print("fnOS 加密存储/TPM(需自备 zt_fnos.py 模块):")
    print("  pool-create            新建加密存储池向导(选盘/拓扑/密钥/FNOS 注册)")
    print("  scan / detail <pool>   fnOS 环境扫描 / 池详情")
    print("  key-backup / keys-restore / keys-cleanup")
    print("  unlock|lock|destroy <pool>")
    print("  autounlock on|off      启动自动解锁服务(systemd)")
    _print_fnos_cmd_list()       # 修复: 补齐完整子命令清单(8 → 全量)
    print()
    print("交互提示:")
    print("  选择 Pool/Dataset/磁盘时, 输入 A/B/C.. 字母或数字即可;")
    print("  只有一个 Pool 时自动选中; 主菜单内按 h/? 查看本帮助")
    print("  主菜单内按 c 查看「菜单号 ↔ CLI 命令」对照(同一条命令可直接敲)")


# 「菜单号 ↔ CLI 命令」对照表（模块级常量 —— 便于探针逐条校验命令名真实存在，
# 防止表里出现拼错 / 不存在的命令；本表就曾写出过 `tpm-status`、`recovery-guide`
# 两个不存在的命令名，是靠"逐条校验"抓出来的）。
CLI_MAP_ROWS = [
    ("1", "仪表盘", "dashboard"),
    ("2", "ARC/L2ARC", "arc"),
    ("3", "健康检查", "health"),
    ("4", "I/O 监控", "iostat"),
    ("5", "快照管理", "snapshot | snapdiff | rollback | prune | send-file | recv-file"),
    ("6", "Scrub 清理", "scrub | scrub-run"),
    ("7", "TRIM 回收", "trim"),
    ("8", "碎片/重写", "frag | rewrite"),
    ("9", "去重 Dedup", "dedup"),
    ("10", "SMART 监测", "smart | smart-trend"),
    ("11", "数据集分析器", "dataset"),
    ("12", "版本信息", "version"),
    ("13", "活动进度", "progress"),
    ("14", "加密管理", "encrypt"),
    ("15", "Pool 管理", "poolmgr | pool-destroy | l2arc-add | slog-add | l2arc-mode"),
    ("16", "数据集管理", "dsmgr"),
    ("17", "告警检查", "alerts"),
    ("18", "环境自检", "doctor"),
    ("19", "历史与日志", "hist"),
    ("20", "计划任务", "schedule"),
    ("21", "体检报告", "report"),
    ("22", "深度诊断", "deep"),
    ("23", "备份 Profile", "profile | profile-run | backup-all"),
    ("24", "趋势预测", "trend | trend-collect"),
    ("25", "fnOS 存储/TPM", "pool-create | scan | detail | unlock | lock | destroy"),
    ("--", "├ 密钥", "key-backup | key-backup-quick | keys-restore | keys-cleanup"),
    ("--", "└ TPM", "tpm-menu | tpm-list | tpm-info | tpm-seal | tpm-unseal | "
                   "tpm-backup-blobs"),
    ("--", "维护模式", "quiesce"),
]


def cmd_cli_map():
    """打印「主菜单号 ↔ 等价 CLI 命令」对照表。

    🆕 交互优化 ④：交互与逻辑都做过优化。原来的问题是
    **菜单层级太深**(例: 维护模式要 8 → 3 → 4), 而且从不告诉用户"这件事对应的
    命令是什么", 于是同一条命令每次都得点进去、也没法脚本化。
    这张表把 25 个入口与等价命令一一对上, 让人**能直达**。
    """
    title("⌨ 菜单号 ↔ CLI 命令 对照", "同一件事既可走菜单, 也可直接敲命令(便于脚本化/远程)")
    rows = CLI_MAP_ROWS
    for no, name, cmdline in rows:
        print("  %s %s%s" % (_pad(no + ".", 4), _pad(name, 16), c("cyan", cmdline)))
    print()
    print(c("yellow", "  提示: 破坏性命令都支持 --dry-run 先预览; 脚本化自动确认用 --yes"))
    print(c("yellow", "        完整命令清单: 在主菜单按 h/? 查看 usage"))
    pause()


# ===========================================================================
# Alerts (阈值告警)
# ===========================================================================


def _dev_rotational(path):
    """块设备的 rotational 值: '0'=SSD / '1'=HDD / None=判不了。
    入参可为 /dev/sdb1、/dev/disk/by-partuuid/... 等任意路径。"""
    names = []
    pk = out(["lsblk", "-no", "PKNAME", path]).strip().splitlines()
    if pk and pk[0].strip():
        names.append(pk[0].strip())
    real = os.path.basename(os.path.realpath(path)) if path.startswith("/") else path
    trim = real
    while trim and trim[-1].isdigit():
        trim = trim[:-1]
    if trim.endswith("p"):
        trim = trim[:-1]
    names.extend([real, trim])
    for nm in names:
        # 🩸 修复：/dev/loopN 恒报 rotational=0，会把 loop 上的池
        #   误判成 SSD ⇒ 直接跳过该候选（全落空时返回 None，调用方按非 SSD 处理）。
        if not nm or nm.startswith("loop"):
            continue
        try:
            with open("/sys/class/block/%s/queue/rotational" % nm, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            continue
    return None


_POOL_SSD_CACHE = {}


# config 段里出现这些词的行是 vdev 分组名，不是设备
_VDEV_HEADS = ("mirror", "raidz1", "raidz2", "raidz3", "draid", "spare", "spares",
               "logs", "log", "cache", "special", "dedup", "replacing")


def _pool_all_ssd(pool):
    """池的底层设备是否**全为 SSD**。True/False/None(判不了时调用方按非 SSD 处理)。

    ⚠️ 必须用 `zpool status -P`：ZFS 2.4 的 `zpool status`/`list -v` 用 GUID 显示
    vdev 名(如 3edce765-...)，拿不到 sdX。

    🩸 修复：**任何认不出的设备行都当「判不了」**。原来只挑
      `startswith("/dev/")` 的行，裸 GUID 行（单盘掉线时会这样渲染）被静默丢弃且无
      完整性校验 —— 构造出「只剩 NVMe cache 行 ⇒ 池判 True ⇒ 碎片率 99% 从 WARN
      降成 INFO」的漏报。现在只要有一行既不是 /dev/ 路径、也不是已知 vdev 分组名或
      池名，就整池返回 None（调用方回落到原阈值 = 宁多报、不漏报）。
    🩸 修复：改走 `run_noblock(timeout=20)`。原来经 `out()`→
      `run()` 没有死线，实测假 zpool 在 `status -P` 上睡 25 秒就能把整轮 alerts（连
      CRIT 一起）挂死；该分支排在设备错误/scrub 判定之前，卡住等于监控静默失明。
    """
    if pool in _POOL_SSD_CACHE:
        return _POOL_SSD_CACHE[pool]
    res = None
    devs = []
    unknown = False
    _p = run_noblock(["zpool", "status", "-P", pool], timeout=20)
    text = "" if _p is None or _p.returncode == 124 else (_p.stdout or "")
    # 🩸 修复：**只在 `config:` 段内解析设备行**。
    #   `zpool status -P` 输出的前面还有 pool:/state:/scan: 等元数据行，若一并扫进来
    #   会命中「认不出的设备」分支 ⇒ unknown ⇒ 整池判 None ⇒ 回落到 HDD 阈值，
    #   于是全 SSD 池的碎片 WARN 又冒出来（上次修复的回归）。
    #   config 段以 `errors:` / `remove:` / `status:` 之类结束。
    in_config = False
    for ln in text.splitlines():
        t = ln.strip()
        if t.startswith("config:"):
            in_config = True
            continue
        if not in_config or not t:
            continue
        if t.startswith("errors:") or t.startswith("remove:") or t.startswith("status:"):
            break
        head = t.split()[0]
        if head == "NAME" or head == pool:
            continue
        if head.startswith("/dev/"):
            devs.append(head)
        elif head.startswith(_VDEV_HEADS):
            continue
        else:
            unknown = True          # 裸 GUID / 认不出的名字 ⇒ 判不了，保守处理
    if devs and not unknown:
        rotas = [_dev_rotational(d) for d in devs]
        if all(r is not None for r in rotas):
            res = all(r == "0" for r in rotas)
    _POOL_SSD_CACHE[pool] = res
    return res


def alerts_collect():
    """返回 [(level, msg), ...]; level: CRIT/WARN/INFO"""
    alerts = []
    pools = _target_pools()      # 修复: 支持 -p/--pool 过滤
    if not pools:
        alerts.append(("INFO", "系统中没有任何 Pool"))
        return alerts

    for p in pools:
        # 修复: 删掉 `ds_prop(p, "health") if False else ...` 死分支 ——
        #   常量 False 让前半永远不执行, 只剩可读性噪音(ds_prop 另有 8 处调用)。
        health = out(["zpool", "get", "-H", "-o", "value", "health", p]).strip()
        if health == "DEGRADED":
            alerts.append(("CRIT", "Pool %s 状态 DEGRADED(降级)" % p))
        elif health and health != "ONLINE":
            alerts.append(("CRIT", "Pool %s 状态 %s(异常)" % (p, health)))

        # 容量
        cap = out(["zpool", "list", "-H", "-o", "cap", p]).strip().rstrip("%")
        if is_num(cap):
            cap = int(cap)
            if cap >= int(CONF["crit_cap"]):
                alerts.append(("CRIT", "Pool %s 容量已达 %d%%" % (p, cap)))
            elif cap >= int(CONF["warn_cap"]):
                alerts.append(("WARN", "Pool %s 容量偏高 %d%%" % (p, cap)))

        # 碎片（按介质分流）：
        #   全 SSD 池 —— 无寻道成本，碎片率对性能无意义（recordsize 8K + docker 这类
        #   小记录负载天生偏高，zpool rewrite 收益趋零还磨损寿命）⇒ 只在超过
        #   frag_ssd_warn 时给一条 INFO，绝不发 WARN。
        #   HDD 池 / 判不出介质的池 —— 沿用 warn_frag / crit_frag 原阈值。
        frag = out(["zpool", "list", "-H", "-o", "frag", p]).strip().rstrip("%")
        if is_num(frag):
            frag = int(frag)
            if _pool_all_ssd(p) is True:
                # 配置里写成负值也不至于把所有池都报成有碎片
                if frag >= max(0, int(CONF["frag_ssd_warn"])):
                    alerts.append(("INFO", "Pool %s 碎片率 %d%%(全 SSD 池, 仅提示)"
                                          % (p, frag)))
            elif frag >= int(CONF["crit_frag"]):
                alerts.append(("WARN", "Pool %s 碎片率 %d%%" % (p, frag)))
            elif frag >= int(CONF["warn_frag"]):
                alerts.append(("INFO", "Pool %s 碎片率 %d%%" % (p, frag)))

        # 设备错误
        errs = 0
        for name, state, rd, wr, ck in _state_lines(out(["zpool", "status", p])):
            if rd + wr + ck > 0:
                errs += 1
        if errs:
            alerts.append(("CRIT", "Pool %s 有 %d 个设备出现读写校验错误" % (p, errs)))

        # Scrub 过期
        age = scrub_age_days(p)
        if age is not None:
            crit = int(CONF["scrub_crit_days"])
            warn = int(CONF["scrub_warn_days"])
            if age > crit:
                alerts.append(("CRIT", "Pool %s 超过 %d 天未 Scrub (上次 %d 天前)" % (p, crit, age)))
            elif age > warn:
                alerts.append(("WARN", "Pool %s 超过 %d 天未 Scrub (上次 %d 天前)" % (p, warn, age)))
        else:
            # 🩸 修复（高）：`scrub_age_days()` 返回 None 有两种含义 ——
            #   ① 池确实没有 scan 记录（罕见）；② `zpool status` 读不到 / 超时。
            #   原来**两种都静默跳过** ⇒ 实测：给 `zpool status` 加 25 秒延时后
            #   生产池 P2 的「超过 N 天未 Scrub」告警消失、`alerts` 的 cron 退出码
            #   由 1 变 0（**监控静默失明**）；作者自查探针同样复现（3 条 → 1 条）。
            #   ⇒ 这里明确报一条 WARN（宁可多一条提示）。
            alerts.append(("WARN", "Pool %s 读不到 Scrub 记录(zpool status 失败或超时)"
                                   " —— 本次无法判断是否需要 Scrub" % p))
    return alerts


_ALERT_STYLE = {"CRIT": ("red", "✖"), "WARN": ("yellow", "⚠"), "INFO": ("cyan", "ℹ")}


def paint_alert(level, msg):
    kind, icon = _ALERT_STYLE.get(level, ("cyan", "ℹ"))
    print("  " + c(kind, icon) + " " + msg)


def cmd_alerts():
    """告警命令: 打印; --json 时输出 JSON。退出码语义由 CLI 层负责。"""
    global FLAG_JSON
    alerts = alerts_collect()
    if FLAG_JSON:
        payload = {"critical": 0, "warning": 0, "info": 0, "alerts": []}
        for lv, msg in alerts:
            payload["alerts"].append({"level": lv, "message": msg})
            if lv == "CRIT":
                payload["critical"] += 1
            elif lv == "WARN":
                payload["warning"] += 1
            else:
                payload["info"] += 1
        # 修复: 原为 "ok = not alerts" —— 一条 INFO 也让 ok=false,
        # 与 alerts_exit_code()（只有 WARN/CRIT 才非 0）的语义冲突, 消费 JSON 的脚本会误判。
        payload["ok"] = not any(lv in ("WARN", "CRIT") for lv, _ in alerts)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    title("🚨 ZFS 告警检查", "容量 / 碎片 / Scrub 过期 / 设备错误, 退出码 0/1/2 可挂 cron")
    if not alerts:
        print()
        print(c("green", "✔ 一切正常, 没有发现告警"))
    else:
        print()
        crt = wrn = inf = 0
        for lv, msg in alerts:
            paint_alert(lv, msg)
            if lv == "CRIT":
                crt += 1
            elif lv == "WARN":
                wrn += 1
            else:
                inf += 1
        print()
        print("汇总: %s%d 严重%s / %s%d 警告%s / %s%d 提示%s" % (
            c("red"), crt, c("reset"),
            c("yellow"), wrn, c("reset"),
            c("cyan"), inf, c("reset")))
    if sys.stdin.isatty():
        pause()


def alerts_exit_code():
    """按告警返回 0/1/2。"""
    alerts = alerts_collect()
    if any(lv == "CRIT" for lv, _ in alerts):
        return 2
    if any(lv == "WARN" for lv, _ in alerts):
        return 1
    return 0


# ===========================================================================
# Dashboard
# ===========================================================================


def _cpu_usage():
    # mpstat 单次输出形如: "14:02:33  all  0.10 0.05 ... 99.75"
    # 行首是时间戳(或 Average:), all 恒在第 2 列, %idle 在最后一列
    if have("mpstat"):
        p = run(["mpstat", "1", "1"])
        if p and p.returncode == 0:
            for ln in p.stdout.splitlines():
                f = ln.split()
                if len(f) >= 8 and f[1] == "all":
                    try:
                        return "%.1f%% used" % (100.0 - float(f[-1]))
                    except ValueError:
                        break
    p = run(["top", "-bn1"])
    if p and p.returncode == 0:
        for ln in p.stdout.splitlines():
            if re.search(r"Cpu\(s\)", ln):
                for tok in ln.split():
                    if "id" in tok:
                        v = re.sub(r"[^0-9.]", "", tok)
                        if v:
                            try:
                                return "%.1f%% used" % (100.0 - float(v))
                            except ValueError:
                                pass
    return "N/A"


def _free_mem():
    p = run(["free", "-h"])
    if p and p.returncode == 0:
        for ln in p.stdout.splitlines():
            f = ln.split()
            if len(f) >= 3 and f[0] == "Mem:":
                return "%s / %s" % (f[2], f[1])
    return "N/A"


def cmd_dashboard():
    title("📊 ZFS 仪表盘 v%s" % VERSION, "系统 / Pool / ARC / I/O / 磁盘温度 / 当前告警总览")
    print()

    def sysline(k, v):
        print("%-10s %s" % (k + ":", v))

    # ---- 系统 ----
    print(c("white", "🖥 System"))
    sysline("Hostname", out(["hostname"]).strip() or "-")
    sysline("Kernel", out(["uname", "-r"]).strip() or "-")
    sysline("Uptime", out(["uptime", "-p"]).strip() or "-")
    sysline("CPU", _cpu_usage())
    sysline("Memory", _free_mem())

    # ---- 告警摘要 ----
    alerts = alerts_collect()
    if alerts:
        print()
        print(c("white", "⚠ Alert Summary"))
        for lv, msg in alerts[:4]:
            paint_alert(lv, msg)
        if len(alerts) > 4:
            print("  ... 共 %d 条, 用菜单 17 / alerts 查看全部" % len(alerts))
    print()

    # ---- Pool ----
    print(c("white", "🗄 ZFS Pool"))
    pools = _target_pools()      # 修复: 支持 -p/--pool 过滤
    if not pools:
        print("  无 Pool")
    else:
        text = out(["zpool", "list", "-H", "-o",
                    "name,health,alloc,size,cap,frag,dedup"])
        for ln in text.splitlines():
            f = ln.split()
            if len(f) < 7:
                continue
            name, health, alloc, size, cap, frag, dedup = f[:7]
            if health == "ONLINE":
                icon = c("green", "●")
            elif health == "DEGRADED":
                icon = c("yellow", "●")
            else:
                icon = c("red", "●")
            print()
            print(name)
            print("Health : %s %s" % (icon, health))
            print("Used   : %s\nSize   : %s\nUsage  : %s" % (alloc, size, cap))
            print("Frag   : %s\nDedup  : %s" % (frag, dedup))
    print()

    # ---- ARC ----
    print(c("white", "💾 ARC Cache"))
    if os.path.exists(ARCSTATS):
        a = arc_stats()
        print("ARC      : %s GiB / %s GiB" % (human_gib(a["size"]), human_gib(a["c_max"])))
        print("Hit Ratio: %s" % hit_rate(a["hits"], a["misses"]))
        if int(a["l2_size"]) > 0:
            print("L2ARC    : %s GiB, 命中 %s" % (human_gib(a["l2_size"]),
                                                  hit_rate(a["l2_hits"], a["l2_misses"])))
        print()
        print(c("white", "🧠 ARC Breakdown"))
        print("MFU      : %s GiB" % human_gib(a["mfu_size"]))
        print("MRU      : %s GiB" % human_gib(a["mru_size"]))
        print("Metadata : %s GiB" % human_gib(a["metadata_size"]))
    else:
        print("ARC unavailable")
    print()

    # ---- IO ----
    print(c("white", "📈 IO Snapshot"))
    for p in pools:
        print()
        print(p)
        io = pool_io_snapshot(p)
        if io:
            print("Read  : %.2f MB/s" % io[0])
            print("Write : %.2f MB/s" % io[1])
        else:
            print("  N/A")
    print()

    # ---- 磁盘温度 ----
    print(c("white", "🌡 磁盘温度"))
    if not have("smartctl"):
        print("smartctl unavailable")
    else:
        for dev, args in smart_devices():
            t = smart_temp(dev, args)
            print("%s : %s" % (dev, ("%d℃" % t) if t is not None else "N/A"))
    print()
    pause()


# ===========================================================================
# Health Check / Frag / ARC / I/O Monitor / Progress
# ===========================================================================


def cmd_health():
    title("❤️ ZFS 健康检查", "遍历所有 Pool: 健康状态 / 容量 / 设备错误 / 最近 Scrub")
    pools = _target_pools()      # 修复: 支持 -p/--pool 过滤

    if not pools:
        print("无 Pool")
        pause()
        return
    for p in pools:
        print()
        print(c("cyan", LINE_SHORT))
        print("Pool: " + p)
        health = out(["zpool", "get", "-H", "-o", "value", "health", p]).strip()
        color = {"ONLINE": "green", "DEGRADED": "yellow"}.get(health, "red")
        print("Status: " + c(color, health or "?"))
        print()
        print("容量:")
        print(out(["zpool", "list", p, "-o", "name,size,alloc,free,cap,frag"]), end="")
        print()
        print("设备错误:")
        rows = _state_lines(out(["zpool", "status", p]))
        bad = [(n, st, rd, wr, ck) for n, st, rd, wr, ck in rows
               if rd + wr + ck > 0 or st != "ONLINE"]
        if bad:
            for n, st, rd, wr, ck in bad:
                print("  %-16s %-9s READ=%s WRITE=%s CKSUM=%s" % (n, st, rd, wr, ck))
        else:
            print("  无错误")
        print()
        print("Scrub:")
        scan = pool_scan_line(p)
        print("  " + (scan or "无记录"))
        print()
    pause()


def frag_view():
    title("📉 ZFS 碎片分析", "查看单池碎片率并给出整理建议")
    pool = ask_pool()
    if not pool:
        pause()
        return
    frag = out(["zpool", "list", "-H", "-o", "frag", pool]).strip().rstrip("%")
    if not is_num(frag):
        print(c("yellow", "无法获取碎片率"))
        pause()
        return
    frag = int(frag)
    print()
    print("Pool: " + pool)
    print("Fragmentation: %d%%" % frag)
    if frag < 20:
        print(c("green", "状态: 优秀"))
    elif frag < 40:
        print(c("green", "状态: 正常"))
    elif frag < 60:
        print(c("yellow", "状态: 需要关注"))
    else:
        print(c("red", "状态: 较高"))
    if frag >= 40:
        print()
        print("建议:")
        print("- 避免长期高占用")
        print("- 保留至少 20% 空闲空间")
        print("- 大文件/VM 池可考虑迁移或重新写入整理")
        print("- OpenZFS 2.4+: 可用 zfs rewrite 重写数据(见本菜单第 2 项)")
    pause()


# ---------------------------------------------------------------------------
# zfs rewrite: OpenZFS 2.4+ 数据重写(整理布局/让属性变更落地)
# ---------------------------------------------------------------------------

def dry_preview(action, cmds, facts=None, notes=None):
    """统一的干跑输出: 打印「将要做什么 + 将执行的底层命令 + 影响面」, 不执行任何动作。
    返回 0, 供命令入口直接 return。所有会写盘的子命令都应支持 --dry-run 走这里。"""
    print()
    print(c("cyan", "══════════ 干跑预览 (--dry-run)：以下动作都不会真正执行 ══════════"))
    print(c("cyan", "  动作: ") + action)
    if facts:
        for k, v in facts:
            print("  %s: %s" % (k, v))
    print()
    for cmd in cmds:
        print("  将执行: " + cmd)
    if notes:
        print()
        for n in notes:
            print(c("yellow", "  ⚠ " + n))
    print()
    print(c("cyan", "══════════ 干跑结束：没有改动任何东西 ══════════"))
    print()
    log("dry-run preview: " + action)
    return 0


def _dry_cmds_of(argv):
    """把 ['zfs','destroy','x'] 折成一行可读命令(仅为预览展示)。"""
    return " ".join(argv)


def _dataset_of_path(target):
    """给定路径, 返回它所属的 dataset 名(取 mountpoint 最长的匹配)。找不到返回 None。
    只用 zfs list 账簿, 不遍历文件系统。"""
    try:
        p = run(["zfs", "list", "-H", "-o", "name,mountpoint"])
    except Exception:
        return None
    if p is None or p.returncode != 0:
        return None
    best_mp, best_ds = "", None
    for ln in (p.stdout or "").splitlines():
        f = ln.split("\t")
        if len(f) < 2:
            continue
        name, mp = f[0], f[1]
        if mp and mp != "-" and mp != "/" and target.startswith(mp) and len(mp) > len(best_mp):
            best_mp, best_ds = mp, name
    return best_ds


def _rewrite_dry_preview(target, flags, cmd):
    """rewrite 的干跑预览: 范围 / 数据量 / 影响面 / 建议（不执行任何动作）。"""
    facts = [("目标", target)]
    facts.append(("递归 (-r)", "是 —— 会处理该目录下所有文件" if "-r" in flags else "否"))
    facts.append(("保留 birth time (-P)", "是" if "-P" in flags else "否"))
    if "-l" in flags or "-o" in flags:
        facts.append(("限定范围", " ".join(flags)))
    ds = _dataset_of_path(target)
    if ds:
        facts.append(("所在数据集", ds))
        q = run(["zfs", "get", "-H", "-p", "-o", "value", "logicalused", ds])
        if q is not None and q.returncode == 0 and is_num((q.stdout or "").strip()):
            v = int((q.stdout or "").strip())
            facts.append(("该数据集逻辑数据量", human_bytes(v)))
            facts.append(("参考耗时", "按本机实测吞吐估算, 每 TiB 约几十分钟量级(会被让路策略进一步拉长)"))
    else:
        facts.append(("所在数据集", "未匹配到(目标可能不在受管挂载点下)"))
    notes = [
        "rewrite 会重写目标下的数据块(去碎片) —— 期间该目标不应有程序写入(数据库/VM/同步/下载), 否则可能丢失或错乱。",
        "建议顺序: 先 `zfs-tool.py quiesce on --dry-run` 看清会停谁 → `quiesce on` 真停 → 再执行 rewrite。",
        "底层 `zfs rewrite` 本身不支持 -n, 所以上面的影响面由本工具估算(读 ZFS 账簿, 不遍历文件), 仅供参考。",
    ]
    return dry_preview("数据重写 (zfs rewrite)", [cmd], facts=facts, notes=notes)


def zfs_rewrite_supported():
    """探测当前 zfs 是否支持 rewrite 子命令。返回 (ok, 说明)。"""
    p = run(["zfs", "rewrite"])
    if p is None:
        return False, "未找到 zfs 命令"
    if p.returncode == 0:
        return True, ""
    low = ((p.stderr or "") + (p.stdout or "")).lower()
    if any(k in low for k in ("unrecognized", "unknown command", "invalid command")):
        return False, "当前 zfs 不支持 rewrite (需要 OpenZFS 2.4+)"
    return True, ""   # 大概率只是打印了 usage


def _physical_rewrite_ok(pool):
    """检查指定池是否启用 physical_rewrite feature(供 -P 使用)。"""
    text = out(["zpool", "get", "-H", "-o", "value", "feature@physical_rewrite", pool]).strip()
    return text in ("active", "enabled")


def cmd_rewrite():
    """zfs rewrite 交互向导。"""
    title("✍ ZFS 数据重写 (zfs rewrite)", "原样重写数据块: 整理布局 / 让 compression·checksum·copies 变更落地")
    ok, why = zfs_rewrite_supported()
    if not ok:
        print(c("red", why))
        pause()
        return

    print()
    print("说明:")
    print("- 重写会把文件的块写到新位置(逻辑大小不变, recordsize 变更不生效)")
    print("- 适用于: 改了 compression/dedup/copies 后想落地, 或想整理碎片/重排布局")
    print("- 默认会更新 logical birth time: 重写块在快照与增量 send 中会像新数据;")
    print("  用 -P 可保留 birth time(需 pool 启用 physical_rewrite feature)")
    print("- 重写克隆块/快照内块可能增加空间占用")
    print()

    ds = ask_dataset("目标数据集")
    if not ds:
        pause()
        return
    mp = ds_prop(ds, "mountpoint")
    if mp in ("", "none", "legacy"):
        print(c("yellow", "该数据集 mountpoint 为 '%s', 无法定位文件路径" % (mp or "空")))
        print("请改用 CLI: zfs-tool.py rewrite <绝对路径> [-r] [-P] [-v]")
        pause()
        return

    rel = ask("相对子路径(文件或目录; 回车=数据集根): ").strip().lstrip("/")
    target = mp if not rel else os.path.join(mp, rel)
    print("目标: " + target)

    flags = []
    recurse = ask_yes("递归处理目录 (-r)? (y/N): ")
    if recurse:
        flags.append("-r")
    if ask_yes("逐文件打印 (-v)? (y/N): "):
        flags.append("-v")
    use_p = False
    if ask_yes("保留 logical birth time (-P, 推荐用于有备份链的池)? (y/N): "):
        pool = ds.split("/", 1)[0]
        if _physical_rewrite_ok(pool):
            flags.append("-P")
            use_p = True
        else:
            print(c("yellow", "该 Pool 未启用 physical_rewrite feature, 跳过 -P"))
            print(c("yellow", "(若确实需要: zpool set feature@physical_rewrite=enabled %s)" % pool))

    if not os.path.exists(target):
        # 远端目录可能不在本 shell 可见(如 /share), 以 exists 判断会误报
        print(c("yellow", "注意: 本地视角看不到 %s (可能为挂载视图差异), 仍将尝试执行" % target))

    cmd = ["zfs", "rewrite"] + flags + [target]
    if FLAG_DRY:
        return _rewrite_dry_preview(target, flags, " ".join(cmd))
    print()
    print("即将执行: " + " ".join(cmd))
    print(c("yellow", "⚠ 重写会移动大量数据块, 耗时取决于数据量; 建议先在低峰期小范围测试"))
    print()
    # 写入静止确认: 目标正被写入时做 rewrite, 并发写可能丢失或错乱
    print(c("red", "⚠ 重要: rewrite 期间目标若正被写入(数据库/VM/容器/rsync/下载等),"))
    print(c("red", "   并发写入的数据可能丢失或版本错乱! 请先停止相关应用再继续。"))
    if have("lsof"):
        if ask_yes("先列出正在占用目标路径的进程(只读检查)? (y/N): "):
            lp = None
            if os.path.isfile(target):
                lp = run(["lsof", "--", target])
            else:
                lp = run(["lsof", "+D", target])
            if lp and (lp.stdout or "").strip():
                print((lp.stdout or "").strip()[:4000])
            else:
                print("  (未发现打开该路径的进程)")
    print()
    confirm = ask("确认目标已无正在写入的程序? 输入 yes 继续: ")
    if confirm.strip().lower() != "yes":
        print("已取消(建议先停止相关写入应用, 再重新执行 rewrite)")
        pause()
        return
    qstate = None
    if ask_yes("是否自动开启维护模式(暂停相册/影视/应用/docker), 重写完成后自动恢复? (y/N): "):
        qstate = quiesce_pause(interactive=False)
    log("rewrite start " + " ".join(cmd))
    print()
    print("执行中, 请耐心等待...")
    ok = True
    errmsg = ""
    try:
        p = run(cmd)
        if p is None or p.returncode != 0:
            ok = False
            err = (p.stderr if p is not None else "") or ""
            errmsg = err.strip()
    finally:
        # 无论成功失败/中断, 恢复维护模式中的应用
        if qstate:
            print()
            quiesce_resume(qstate)
    if ok:
        print(c("green", "重写完成"))
        log("rewrite finish " + target)
    else:
        print(c("red", "重写失败" + (("(exit %s)" % p.returncode) if p is not None else "")))
        if errmsg:
            print(errmsg)
    pause()


def zfs_rewrite_cli(extra):
    """CLI: rewrite <路径> [-r] [-P] [-v] [-x] [-l 字节] [-o 偏移]"""
    if not extra:
        print("用法: zfs-tool.py rewrite <文件|目录> [-r] [-P] [-v] [-x] [-l 字节] [-o 偏移]")
        return 2
    target = extra[0]
    flags = []
    i = 1
    while i < len(extra):
        a = extra[i]
        if a in ("-r", "-P", "-v", "-x"):
            flags.append(a)
        elif a in ("-l", "-o") and i + 1 < len(extra):
            flags += [a, extra[i + 1]]
            i += 1
        else:
            print(c("yellow", "忽略无法识别的参数: %s" % a))
        i += 1
    ok, why = zfs_rewrite_supported()
    if not ok:
        print(c("red", why))
        return 1
    cmd = ["zfs", "rewrite"] + flags + [target]
    if FLAG_DRY:
        return _rewrite_dry_preview(target, flags, " ".join(cmd))
    print()
    print(c("red", "⚠ 请确保目标文件/目录当前没有程序在写入(数据库/VM/同步/下载等),"))
    print(c("red", "   rewrite 期间并发写入可能丢失或错乱!"))
    print("执行: " + " ".join(cmd))
    p = run(cmd)
    if p is not None and p.returncode == 0:
        print(c("green", "重写完成: " + target))
        log("rewrite finish " + target)
        return 0
    err = (p.stderr if p is not None else "") or ""
    print(c("red", "重写失败"))
    if err:
        print(err.strip())
    return 1


def cmd_frag():
    """碎片清理工具(常驻循环): 可连续执行 查看碎片/重写/维护模式, 0 才返回主菜单。"""
    while True:
        title("📉 ZFS 碎片清理工具", "碎片率 / 数据重写 / 维护模式 — 可连续操作, 0 返回主菜单")
        print()
        print("1. 查看碎片率")
        print("2. 数据重写 (zfs rewrite)")
        print("3. 维护模式 (暂停/恢复写入应用)")
        print("0. 返回主菜单")
        print()
        # 🆕 交互优化 ④: 这三项以前要 8→1/2/3 点进来, 现在直接标出等价命令
        cli_hint([("1", "zfs-tool.py frag"),
                  ("2", "zfs-tool.py rewrite <路径> -r   (先用 --dry-run 预览)"),
                  ("3", "zfs-tool.py quiesce status | on | off | check")])
        print()
        opt = ask("选择: ").strip()
        if opt == "1":
            frag_view()
        elif opt == "2":
            cmd_rewrite()
        elif opt == "3":
            cmd_quiesce()
        elif opt == "0":
            return
        else:
            print("无效选择")
            try:
                __import__("time").sleep(0.8)
            except Exception:
                pass


# ===========================================================================
# 维护模式: 暂停/恢复会写盘的 fnOS 应用(相册/影视/应用中心/docker)
# 供 rewrite / 维护窗口前使用。状态记录到 QUIESCE_STATE 便于一键恢复。
# ===========================================================================

QUIESCE_STATE = os.path.join(DATA_DIR, "quiesce.json")
QUIESCE_SERVICES = ("imagesrv.service", "mediasrv.service")
# 覆盖体检关注的"数据盘"前缀: 只有这些路径上的写句柄才算写入者。
# fnOS 把数据卷挂在 /vol<N>(N 从 1 起); **末尾斜杠必需** —— 否则 startswith 会把
# 卷号位数更多的挂载点(两位数卷号)误判成数据卷。
QUIESCE_VOL_ROOTS = tuple("/vol%d/" % _n for _n in (1, 2))
# 覆盖体检豁免: 这些写入者本就不该被暂停(守护进程 / 工具自身), 不算"漏网"
QUIESCE_AUDIT_EXEMPT = ("dockerd", "zfs-dedup")
# 🩸 自动暂停的安全边界 —— 这些进程绝不 STOP:
#   ① STOP 自己的 ssh/sudo/bash 链 = 进程被冻死, 连 kill -CONT 都发不出来(只能靠人工救);
#   ② STOP PID 1 / 内核线程 = 整机冻结;
#   ③ 登录/调度/日志等系统链路一旦冻结, 会连带一大片服务。
QUIESCE_PROTECT_COMMS = frozenset([
    "init", "systemd", "systemd-journal", "systemd-journald", "systemd-logind",
    "systemd-udevd", "systemd-timesyncd", "dbus-daemon", "dbus-broker",
    "sshd", "sshd-session", "ssh", "sudo", "su",
    "bash", "sh", "dash", "zsh", "sleep", "cron", "crond", "atd",
    "zfs", "zpool", "zdb", "mount", "umount", "fsck",
])
# 自动暂停的活跃度判据: 采样窗口内真实写盘增量 >= 该值才算"真在写"
# (很多进程长期持有 db/日志写句柄却几乎不写, 一律 STOP 会误伤)
QUIESCE_ACTIVE_MIN_BYTES = 4096
QUIESCE_ACTIVE_SAMPLE_SECS = 2.0


def _active_service(name):
    p = run(["systemctl", "is-active", name])
    if p and p.returncode == 0:
        return (p.stdout or "").strip() == "active"
    return False


def _appcenter_pids():
    """返回 [(pid, cmd)]: @appcenter 应用进程(排除应用商店自身)。"""
    res = []
    p = run(["ps", "-eo", "pid,args"])
    if p is None or p.returncode != 0:
        return res
    for ln in p.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        pid, _, args = ln.partition(" ")
        if not pid.isdigit():
            continue
        if "@appcenter" in args and "store-server" not in args \
                and "fnos-apps-store" not in args:
            res.append((int(pid), args[:140]))
    return res


def _docker_containers():
    """返回 [(name, image)]: running docker 容器。"""
    if not have("docker"):
        return []
    p = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"])
    if p is None or p.returncode != 0:
        return []
    rows = []
    for ln in (p.stdout or "").splitlines():
        f = ln.split("\t")
        if len(f) >= 2:
            rows.append((f[0], f[1]))
    return rows


def _load_quiesce_state():
    try:
        with open(QUIESCE_STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _save_quiesce_state(state):
    _ensure_data_dir()
    try:
        with open(QUIESCE_STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _quiesce_preflight():
    """开启维护模式前的预检: 列出当前持有数据盘写句柄的进程(谁会被暂停、谁会继续写)。"""
    writers = _fd_write_targets()
    print()
    if not writers:
        print(c("green", "预检: 当前没有进程持有数据盘写句柄"))
        return
    bypid = {}
    for pid, comm, _flags, path in writers:
        bypid.setdefault(pid, {"comm": comm, "paths": []})["paths"].append(path)
    print(c("cyan", "预检: 当前持有数据盘写句柄的进程 %d 个 —— 不在下面暂停清单里的会照旧写入"
                   % len(bypid)))
    for pid in sorted(bypid):
        print("    pid=%-8d %s" % (pid, bypid[pid]["comm"]))


def quiesce_pause(interactive=True, dry=None):
    """暂停已知写入应用 + 预检发现的清单外活跃写入者。
    🆕 闭环: 预检分类的结果直接决定还要额外 STOP 谁(不再依赖写死的清单)。
    dry=True 时只预告、不执行任何动作(供真跑前预览/自动化测试)。
    返回 state(dict) 供 quiesce_resume 恢复; 失败返回 None。"""
    services = [s for s in QUIESCE_SERVICES if _active_service(s)]
    app_pids = _appcenter_pids()
    containers = _docker_containers()

    if not (services or app_pids or containers):
        print(c("yellow", "未发现需要暂停的相册/影视/应用中心/docker 写入者"))
        return None

    print()
    print(c("yellow", "将暂停以下应用(维护窗口内停止写盘):"))
    for s in services:
        print("  [systemd] " + s)
    for pid, cmd in app_pids:
        print("  [进程%d] %s" % (pid, cmd))
    for name, img in containers:
        print("  [docker] %s (%s)" % (name, img))

    # 🆕 闭环: 预检分类 → 清单外的活跃写入者也一并暂停
    print()
    print(c("cyan", "预检分类中(采样 %.0f 秒真实写盘增量)..." % QUIESCE_ACTIVE_SAMPLE_SECS))
    cls = _quiesce_classify()
    extra = dict(cls["will_pause"])
    if extra:
        print(c("yellow", "预检发现 %d 个清单外的活跃写入者, 将一并暂停:" % len(extra)))
        for pid in sorted(extra):
            print("  [进程%d] %s —— %s" % (pid, extra[pid]["comm"], extra[pid]["why"]))
    else:
        print(c("green", "预检: 除已列出的应用外, 没有别的活跃写入者"))
    if cls["protected"]:
        print()
        print(c("red", "⚠️ 另有 %d 个活跃写入者落在保护名单里, 不会被暂停(需人工处理):"
                       % len(cls["protected"])))
        for pid in sorted(cls["protected"]):
            print("  pid=%-8d %-16s %s" % (pid, cls["protected"][pid]["comm"],
                                           cls["protected"][pid]["why"]))

    if dry is None:
        # 🩸 环境变量在 sudo 下默认「不传递」给子进程 —— 实测踩到:
        #    `ZT_QUIESCE_DRYRUN=1 sudo python3 ...` 时 python 根本看不到它,
        #    结果是"以为在预览、其实真的停了相册与 14 个容器"。
        #    ⇒ 真正确可靠的入口是 CLI 参数 --dry-run(参数在 cmdline 里, sudo 拦不住)。
        dry = os.environ.get("ZT_QUIESCE_DRYRUN", "") not in ("", "0")
    if interactive and not dry:
        print()
        if not confirm_single("确认暂停以上应用?"):
            print("已取消")
            return None

    state = {"time": datetime.now().strftime("%F %T"),
             "services": services, "pids": [p for p, _ in app_pids],
             "containers": [n for n, _ in containers],
             "stopped_pids": sorted(extra.keys()), "errors": []}
    if dry:
        print()
        print(c("cyan", "dry-run 模式 ⇒ 只预告、不执行(不会暂停任何东西)"))
        print(c("cyan", "  入口是 CLI 参数 --dry-run; ⚠️ 别用 ZT_QUIESCE_DRYRUN 环境变量,"
                       " sudo 默认不传递它（拿不到值时别按错误的默认值执行）"))
        print(c("cyan", "  实际会暂停: %d 服务 / %d 应用中心进程 / %d 容器 / %d 清单外进程"
                       % (len(services), len(app_pids), len(containers), len(extra))))
        print(c("cyan", "  本次不写维护记录(免得 off 去恢复根本没被停的东西)"))
        return state
    for s in services:
        p = run(["systemctl", "stop", s])
        if p is None or p.returncode != 0:
            state["errors"].append("stop %s 失败" % s)
        else:
            print("已停止: " + s)
    for pid, _ in app_pids:
        p = run(["kill", "-STOP", str(pid)])
        if p is None or p.returncode != 0:
            state["errors"].append("暂停 pid %d 失败" % pid)
        else:
            print("已暂停进程 %d" % pid)
    # 🆕 清单外的活跃写入者: 已在预检里确认"真在写", 逐个 STOP
    for pid in sorted(extra):
        if not os.path.isdir("/proc/%d" % pid):
            continue        # 预检后已自行退出
        p = run(["kill", "-STOP", str(pid)])
        if p is None or p.returncode != 0:
            state["errors"].append("暂停清单外 pid %d(%s) 失败" % (pid, extra[pid]["comm"]))
        else:
            print("已暂停清单外进程 %d (%s)" % (pid, extra[pid]["comm"]))
    for name, _img in containers:
        p = run(["docker", "pause", name])
        if p is None or p.returncode != 0:
            state["errors"].append("pause %s 失败(容器可能无权限/非运行)" % name)
        else:
            print("已暂停容器: " + name)

    _save_quiesce_state(state)
    log("quiesce pause: services=%s pids=%d extra=%d containers=%d errors=%d" % (
        ",".join(services), len(app_pids), len(extra), len(containers),
        len(state["errors"])))
    if state["errors"]:
        print(c("yellow", "部分暂停失败, 请人工确认: " + "; ".join(state["errors"])))
    else:
        print(c("green", "维护模式已开启: %d 服务 / %d 进程 / %d 容器 / %d 清单外进程" % (
            len(services), len(app_pids), len(containers), len(extra))))
    # 🩸 复检: 把"仍在写盘、却不在暂停清单里"的进程当场报出来
    #    (维护模式开着时若有服务重启/自愈, 新进程不在清单里, 会照写不误)
    print(c("cyan", "--- 开启后复检(仍有写句柄的进程; 保护名单内的不会被自动暂停) ---"))
    quiesce_audit()
    return state


def quiesce_resume(state=None):
    """恢复暂停的应用。state 为空则读取状态文件。返回是否全部成功。"""
    if state is None:
        state = _load_quiesce_state()
    if not state:
        print(c("yellow", "当前没有处于维护模式(无暂停记录)"))
        return True
    ok = True
    for s in state.get("services", []):
        p = run(["systemctl", "start", s])
        if p is None or p.returncode != 0:
            print(c("red", "启动 %s 失败" % s))
            ok = False
        else:
            print("已启动: " + s)
    for pid in state.get("pids", []):
        p = run(["kill", "-CONT", str(pid)])
        if p is None or p.returncode != 0:
            print(c("red", "恢复进程 %d 失败" % pid))
            ok = False
        else:
            print("已恢复进程 %d" % pid)
    # 🆕 恢复预检闭环额外暂停的那些(清单外活跃写入者)
    for pid in state.get("stopped_pids", []):
        p = run(["kill", "-CONT", str(pid)])
        if p is None or p.returncode != 0:
            print(c("yellow", "恢复清单外进程 %d 失败(可能已自行退出)" % pid))
        else:
            print("已恢复清单外进程 %d" % pid)
    for name in state.get("containers", []):
        p = run(["docker", "unpause", name])
        if p is None or p.returncode != 0:
            print(c("yellow", "unpause %s 失败(可能未处于暂停态)" % name))
        else:
            print("已恢复容器: " + name)
    try:
        os.remove(QUIESCE_STATE)
    except OSError:
        pass
    log("quiesce resume")
    print(c("green", "维护模式已关闭(暂停于 %s 的项目已恢复)" % state.get("time", "?")))
    return ok


def quiesce_status():
    state = _load_quiesce_state()
    print()
    if not state:
        print("当前未开启维护模式(无暂停记录)")
        return
    print(c("yellow", "维护模式处于开启状态, 暂停于 %s:" % state.get("time", "?")))
    for s in state.get("services", []):
        print("  [systemd] %s" % s)
    for pid in state.get("pids", []):
        print("  [进程%d]" % pid)
    for pid in state.get("stopped_pids", []):
        print("  [进程%d]  (预检闭环额外暂停的清单外写入者)" % pid)
    for name in state.get("containers", []):
        print("  [docker] %s" % name)
    if state.get("errors"):
        print(c("red", "有失败项: " + "; ".join(state["errors"])))
    print()
    print("记得做完维护后恢复: 菜单选 8 → 3 → 2 或 CLI: zfs-tool.py quiesce off")


def _pid_in_docker(pid):
    """进程是否运行在 docker 容器内(读 cgroup 判断)。"""
    try:
        with open("/proc/%d/cgroup" % pid, encoding="utf-8", errors="replace") as fh:
            return "docker" in fh.read()
    except OSError:
        return False


def _fd_write_targets():
    """遍历 /proc/<pid>/fdinfo, 找出持有 QUIESCE_VOL_ROOTS 下「写」句柄的进程。
    返回 [(pid, comm, flags, path)]。需 root 才能看到他人进程; 无权限者静默跳过。"""
    res = []
    try:
        pids = sorted(d for d in os.listdir("/proc") if d.isdigit())
    except OSError:
        return res
    for pid in pids:
        base = "/proc/%s" % pid
        try:
            with open(os.path.join(base, "comm"), encoding="utf-8", errors="replace") as fh:
                comm = fh.read().strip()
        except OSError:
            continue
        try:
            fds = os.listdir(os.path.join(base, "fd"))
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(os.path.join(base, "fd", fd))
            except OSError:
                continue
            if not target.startswith(QUIESCE_VOL_ROOTS):
                continue
            flags = None
            try:
                with open(os.path.join(base, "fdinfo", fd),
                          encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        if ln.startswith("flags:"):
                            flags = int(ln.split(":", 1)[1].strip(), 8)
                            break
            except (OSError, ValueError):
                continue
            # O_WRONLY=1 / O_RDWR=2; 只读(0)与 O_PATH 不算写入者
            if flags is None or not (flags & 0o3):
                continue
            res.append((int(pid), comm, flags, target))
    return res


def _proc_stat_field(pid, idx):
    """读 /proc/<pid>/stat 的第 idx 个字段(1-based)。失败返回 None。
    注意先定位最后一个 ')' —— comm 里可能带空格与括号。"""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return None
    rp = raw.rfind(")")
    if rp < 0:
        return None
    parts = raw[rp + 2:].split()
    i = idx - 3          # parts[0] 对应 stat 的第 3 个字段(state)
    if i < 0 or i >= len(parts):
        return None
    return parts[i]


def _is_kernel_thread(pid):
    """内核线程判定: cmdline 为空(PID 1 除外)。"""
    if pid == 1:
        return False
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return fh.read(1) == b""
    except OSError:
        return True


def _self_chain_pids():
    """本进程 → PID 1 的整条父进程链(含自身)。
    🩸 这些绝不能被 STOP: 冻结自己的 ssh/sudo/bash 链 = 进程被冻死,
    连 kill -CONT 都发不出来, 只能靠人工登录救。"""
    chain = set()
    pid = os.getpid()
    for _ in range(64):
        if pid <= 0 or pid in chain:
            break
        chain.add(pid)
        ppid = _proc_stat_field(pid, 4)
        if ppid is None:
            break
        try:
            ppid = int(ppid)
        except ValueError:
            break
        if ppid <= 0 or ppid == pid:
            break
        pid = ppid
    return chain


def _write_bytes_of(pid):
    """读 /proc/<pid>/io 的 write_bytes(真实写盘字节)。失败返回 None。"""
    try:
        with open("/proc/%d/io" % pid, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if ln.startswith("write_bytes:"):
                    return int(ln.split(":", 1)[1].strip())
    except (OSError, ValueError):
        pass
    return None


def _quiesce_classify(sample_secs=None):
    """把"持有数据盘写句柄"的进程分类 —— 这是 quiesce 的决策依据(闭环:
    预检结果直接决定还要额外暂停谁)。返回:
      {"will_pause": {},   # 真在写 + 不在任何覆盖清单里   → 维护模式会自动 STOP
       "protected":  {},   # 真在写 + 落在保护名单里       → 不会暂停, 需人工
       "docker":     {},   # 真在写 + 容器内               → 由 docker pause 覆盖
       "covered":    {},   # 真在写 + 已在 service/应用中心清单内
       "exempt":     {},   # 豁免(守护进程/工具自身)
       "idle":       {}}   # 只持有写句柄, 实测无写入增量
    每个 value = {"comm": str, "paths": [str], "why": str}。"""
    if sample_secs is None:
        sample_secs = QUIESCE_ACTIVE_SAMPLE_SECS
    self_chain = _self_chain_pids()
    covered = set(p for p, _ in _appcenter_pids())
    st = _load_quiesce_state()
    if st:
        for key in ("pids", "stopped_pids"):
            for x in st.get(key, []):
                if str(x).isdigit():
                    covered.add(int(x))

    bypid = {}
    for pid, comm, _flags, path in _fd_write_targets():
        bypid.setdefault(pid, {"comm": comm, "paths": [],
                               "kind": "", "why": ""})["paths"].append(path)

    # 第一轮: 按身份归类(豁免者不采样; 其余都要采样确认"是否真在写")
    sample = []
    for pid, info in bypid.items():
        comm = info["comm"]
        if comm in QUIESCE_AUDIT_EXEMPT:
            info["kind"], info["why"] = "exempt", "豁免(守护进程/工具自身)"
            continue
        if pid == 1:
            info["kind"], info["why"] = "protected", "PID 1 —— 停了整机冻结"
        elif pid in self_chain:
            info["kind"], info["why"] = "protected", \
                "本进程自身链(ssh/sudo/bash) —— 停了进程就被冻死"
        elif _is_kernel_thread(pid):
            info["kind"], info["why"] = "protected", "内核线程"
        elif comm in QUIESCE_PROTECT_COMMS:
            info["kind"], info["why"] = "protected", "系统保护名单(登录/调度/日志链路)"
        elif _pid_in_docker(pid):
            info["kind"], info["why"] = "docker", "容器内 —— 由 docker pause 覆盖"
        elif pid in covered:
            info["kind"], info["why"] = "covered", "已在 service/应用中心暂停清单内"
        else:
            info["kind"], info["why"] = "candidate", "不在任何覆盖清单内"
        sample.append(pid)

    # 第二轮: 一次性采样(先全读 → sleep → 再全读), 比逐个 sleep 快 N 倍
    snap_a, snap_b = {}, {}
    if sample:
        snap_a = dict((p, _write_bytes_of(p)) for p in sample)
        time.sleep(sample_secs)
        snap_b = dict((p, _write_bytes_of(p)) for p in sample)

    out = dict((k, {}) for k in
               ("will_pause", "protected", "docker", "covered", "exempt", "idle"))
    for pid, info in bypid.items():
        kind = info["kind"]
        if kind == "exempt":
            out["exempt"][pid] = info
            continue
        x, y = snap_a.get(pid), snap_b.get(pid)
        delta = None if (x is None or y is None) else (y - x)
        if delta is None:
            info["why"] = "读不到 /proc/<pid>/io · " + info["why"]
            out["idle"][pid] = info
        elif delta < QUIESCE_ACTIVE_MIN_BYTES:
            info["why"] = "实测无写入增量 · " + info["why"]
            out["idle"][pid] = info
        else:
            info["why"] = "实测 %.0f 秒写 %s · %s" % (
                sample_secs, human_bytes(delta), info["why"])
            if kind == "candidate":
                out["will_pause"][pid] = info
            elif kind in ("protected", "docker", "covered"):
                out[kind][pid] = info
            else:
                out["idle"][pid] = info
    return out


def quiesce_audit():
    """覆盖体检: 把所有数据盘写入者按"维护模式会不会暂停它"分类, 并给出自动暂停预告。
    🩸 有"真在写、却被保护名单挡住"的进程返回 1(需要人工处理), 否则返回 0。"""
    print()
    print(c("cyan", "🔍 维护模式覆盖体检 (分类 + 自动暂停预告)"))
    print()
    cls = _quiesce_classify()
    total = sum(len(v) for v in cls.values())
    if not total:
        print(c("green", "✅ 当前没有任何进程持有 %s 的写句柄(维护窗口是干净的)"
                       % "/".join(r.rstrip("/") for r in QUIESCE_VOL_ROOTS)))
        print()
        return 0
    order = [
        ("will_pause", "⏸ 清单外的活跃写入者(维护模式会自动 STOP)", "red"),
        ("protected", "🛡 保护名单内的活跃写入者(不会暂停, 需人工处理)", "red"),
        ("covered", "✅ 已在暂停清单内(维护模式会停它们)", "green"),
        ("docker", "🐳 容器内(由 docker pause 覆盖)", "green"),
        ("exempt", "➖ 豁免", "cyan"),
        ("idle", "💤 仅持有写句柄、实测无写入(只记录, 不动它们)", "cyan"),
    ]
    print("当前持有数据盘写句柄的进程: %d 个" % total)
    for key, title, color in order:
        rows = cls[key]
        if not rows:
            continue
        print()
        print(c(color, "  %s —— %d 个" % (title, len(rows))))
        if key == "idle":
            # 这类只是"手里握着句柄", 不逐个刷屏
            for pid in sorted(rows):
                print("    pid=%-8d %s" % (pid, rows[pid]["comm"]))
            continue
        for pid in sorted(rows):
            info = rows[pid]
            print("    pid=%-8d %-16s %s" % (pid, info["comm"], info.get("why", "")))
            for p in info["paths"][:2]:
                print("        -> %s" % p)
            if len(info["paths"]) > 2:
                print("        -> ...(另 %d 个)" % (len(info["paths"]) - 2))
    print()
    print(c("cyan", "  自动暂停判据: 采样 %.0f 秒内 write_bytes 增量 >= %s"
                   % (QUIESCE_ACTIVE_SAMPLE_SECS, human_bytes(QUIESCE_ACTIVE_MIN_BYTES))))
    print(c("cyan", "  保护边界: 自身进程链 / PID 1 / 内核线程 / %s"
                   % "/".join(sorted(list(QUIESCE_PROTECT_COMMS))[:8]) + " …"))
    print(c("cyan", "  豁免: %s" % "/".join(QUIESCE_AUDIT_EXEMPT)))
    print()
    risky = cls["protected"]
    if not risky:
        print(c("green", "✅ 没有「真在写却被保护名单挡住」的进程 —— 开维护模式即可清场"))
        print()
        return 0
    print(c("red", "🔴 %d 个活跃写入者落在保护名单里, 维护模式不会暂停它们:" % len(risky)))
    for pid in sorted(risky):
        print("    pid=%-8d %-16s %s" % (pid, risky[pid]["comm"], risky[pid].get("why", "")))
    print()
    print(c("yellow", "⚠️ 执行会写盘的维护操作(如 zfs-dedup 真跑)前, 请先手工处理以上进程"))
    print(c("yellow", "   (kill -STOP <pid>, 记进维护记录, 事后 kill -CONT 恢复)"))
    print()
    print("说明: 仅统计宿主机可见的 fd; 容器内进程需 --pid=host 才能在容器外看到")
    print()
    return 1


_QUIESCE_PROMPT_SKIPPED = False


def _quiesce_guard():
    """回主菜单防呆: 维护模式仍开启时提醒, 并建议立即恢复(可明确跳过)。
    若本次执行了恢复(有大量输出), 返回 True 让主菜单清屏重绘, 避免日志残留。"""
    global _QUIESCE_PROMPT_SKIPPED
    st = _load_quiesce_state()
    if not st:
        return False
    n = (len(st.get("services", [])) + len(st.get("pids", []))
         + len(st.get("stopped_pids", [])) + len(st.get("containers", [])))
    print()
    print(c("yellow", "⚠ 维护模式仍处于开启状态(自 %s, %d 项被暂停)!" % (st.get("time", "?"), n)))
    if not _QUIESCE_PROMPT_SKIPPED:
        if ask_yes("回到主菜单前建议恢复, 立即关闭维护模式? (y/N, 建议 y): "):
            quiesce_resume(st)
            _QUIESCE_PROMPT_SKIPPED = False
            return True   # 已输出恢复明细, 让外层清屏重绘主菜单
        _QUIESCE_PROMPT_SKIPPED = True
        print(c("yellow", "已跳过本次提醒; 仍可随时用 quiesce off 或 菜单 8→3→2 恢复"))
        print()
    return False


def cmd_quiesce():
    title("🛌 维护模式 (暂停写入应用)", "暂停相册/影视/应用中心/docker, 供 rewrite 或维护窗口使用")
    print()
    print("1. 开启 (预检分类 → 暂停应用 + 清单外活跃写入者)")
    print("2. 关闭 (全部恢复)")
    print("3. 状态查看")
    print("4. 覆盖体检 (分类 + 自动暂停预告)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        st = quiesce_pause(interactive=True)
        if st:
            print(c("cyan", "维护模式已开 → 回车回到碎片工具后, 可立即选 2 执行数据重写"))
        pause()
    elif opt == "2":
        _QUIESCE_PROMPT_SKIPPED = False
        quiesce_resume()
        pause()
    elif opt == "3":
        quiesce_status()
        pause()
    elif opt == "4":
        quiesce_audit()
        pause()
    elif opt == "0":
        return
    else:
        print("无效选择")
        pause()


def quiesce_cli(extra):
    """CLI: quiesce on|off|status|check [--dry-run]"""
    args = list(extra)
    # 🩸 修复：`main()` 解析 `--dry-run` 时会把它从 argv
    #   **摘走**、只设全局 FLAG_DRY ⇒ 这里原来只在 argv 里找它 ⇒
    #   `zfs-tool.py quiesce on --dry-run` 会**真的去停生产服务**
    #   （实测发出 `systemctl stop imagesrv.service / mediasrv.service` +
    #   `docker pause`），而 usage / docstring 白纸黑字承诺"只预告不执行(推荐先跑一次)"。
    #   现在**两个入口都算预览**：全局开关与命令内选项任一为真即 dry。
    dry = bool(FLAG_DRY)
    for flag in ("--dry-run", "--dryrun", "-n"):
        if flag in args:
            args.remove(flag)
            dry = True
    if not args:
        print("用法: zfs-tool.py quiesce on|off|status|check [--dry-run]")
        print("  on    = 预检分类后暂停(含清单外的活跃写入者), 开启后自动复检")
        print("  off   = 全部恢复(含预检闭环额外暂停的进程)")
        print("  check = 覆盖体检: 分类 + 自动暂停预告 (有保护名单内活跃写入者时 rc=1)")
        print("  --dry-run = 只预告不执行(推荐先跑一次; ⚠️ 别用环境变量, sudo 不传)")
        return 2
    if args[0] == "on":
        st = quiesce_pause(interactive=False, dry=dry)
        return 0 if st else 1
    if args[0] == "off":
        # 🩸 复验：`quiesce off --dry-run` 原来**仍然真恢复**服务
        #   （dry 只在 on 分支生效）⇒ dry-run 下必须只报告、不动手。
        if dry:
            print(c("yellow", "【dry-run】不会恢复任何服务。当前被暂停的项目:"))
            try:
                quiesce_status()
            except Exception as exc:            # noqa: BLE001
                print(c("dim", "  （状态读取失败: %s）" % exc))
            print(c("dim", "  去掉 --dry-run 才会真正恢复。"))
            return 0
        return 0 if quiesce_resume() else 1
    if args[0] == "status":
        quiesce_status()
        return 0
    if args[0] in ("check", "audit"):
        return quiesce_audit()
    print("未知参数: %s (可用 on/off/status/check)" % args[0])
    return 2


# ===========================================================================
# fnOS 加密存储 / TPM 桥接(默认走内嵌 payload, 无需同目录 zt_fnos.py)
# ===========================================================================

FNOS_CMDS = frozenset([
    # fnOS 加密存储
    "pool-create", "detect", "scan", "detail", "next-mount", "create-verify",
    "key-backup", "key-backup-quick", "keys-restore", "keys-cleanup",
    "unlock", "lock", "destroy", "autounlock",
    "mount-verify", "mount-fix", "recovery",
    # 补上原先漏登记的一个入口 —— 源脚本功能清单里唯一缺的那个。
    # 实现在 fnOS 扩展模块里(源 bash 脚本:3455/:4424), 但既没有 @_cmd
    # 也没进本白名单 → 单文件里落到"未知命令 rc=2"; 本批已在 zt_fnos.py 侧补了 @_cmd。
    "verify-startup-order",
    # TPM 2.0
    "tpm-detect", "tpm-da", "tpm-capabilities", "tpm-blob-parse",
    "tpm-seal", "tpm-unseal", "tpm-unseal-all", "tpm-list",
    "tpm-reseal", "tpm-remove", "tpm-boot", "tpm-cleanup",
    "tpm-drift", "tpm-diagnose", "tpm-export-key", "tpm-import-key",
    "tpm-selftest", "tpm-verify-pcr", "tpm-install-tools",
    "tpm-pre-reboot", "tpm-backup-blobs", "tpm-menu", "tpm-recovery",
    "tpm-info", "tpm-smart-recommend", "tpm-pcr-read", "tpm-da-reset",
    # 补上模块侧新增的交互式主菜单入口。
    #   与上一条同类漏登记 —— 模块里加了
    #   @_cmd("menu"), 而本白名单没跟上 ⇒ 单文件发行里 `zfs-tool.py menu` 会落
    #   "未知命令 rc=2", 只有直接跑 zt_fnos.py 才可达 = 等于白发。
    "menu",
])

_ZT_MOD = None
# 单文件发行: 内嵌压缩的 zt_fnos.py(gzip+base64), 由构建脚本 _zt_build_single.py 注入。
# ⚠ 本仓不分发 fnOS 模块(它衍生自第三方脚本, 原帖未声明许可) ⇒ 此处留空;
#   需要 fnOS 功能的用户自备 zt_fnos.py 后重新构建, 或放到同目录 + ZT_FNOS_EXTERNAL=1。
_ZT_EMBED_B64 = ""


def _load_zt_fnos():
    """加载 fnOS 模块: 优先内嵌 payload(单文件发行), 其次外部 zt_fnos.py。
    ⚠ 本仓 payload 为空 ⇒ 需 ZT_FNOS_EXTERNAL=1 且同目录存在 zt_fnos.py 才能加载。"""
    global _ZT_MOD
    if _ZT_MOD is not None:
        return _ZT_MOD
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zt_fnos.py")
    src = None
    use_external = os.environ.get("ZT_FNOS_EXTERNAL") == "1" and os.path.exists(path)
    if use_external:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    elif _ZT_EMBED_B64:
        import base64 as _b64
        import gzip as _gz
        src = _gz.decompress(_b64.b64decode(_ZT_EMBED_B64)).decode("utf-8")
    if not src:
        return None
    spec = importlib.util.spec_from_file_location("zt_fnos_mod", path or __file__)
    mod = importlib.util.module_from_spec(spec)
    try:
        if use_external:
            spec.loader.exec_module(mod)
        else:
            exec(compile(src, "<zt_fnos-embedded>", "exec"), mod.__dict__)
    except Exception as exc:      # 加载失败不影响主工具其它功能
        print(c("yellow", "加载 zt_fnos 失败: %s" % exc))
        return None
    _ZT_MOD = mod
    return mod


def fnos_dispatch(args):
    """把 [子命令, 参数...] 透传给 zt_fnos.main()。

    修复: args 现在可能带 `-p/--pool <池>`(由 main() 解析时原样保留),
    一并透传, 不再被顶层参数解析吃掉。⚠ 注意: 截至第 3 批 zt_fnos.py 自身
    并不识别 `-p/--pool`(其子命令多数直接吃位置参数), 因此透传目前只保证
    "不丢参", 不等于"fnOS 侧已生效"——后者由 zt_fnos 侧单独修。
    """
    mod = _load_zt_fnos()
    if mod is None:
        print(c("red", "fnOS 模块不可用(需自备 zt_fnos.py, 或用构建脚本注入 payload)"))
        return 1
    try:
        return int(mod.main(args) or 0)
    except SystemExit:
        return 0


def _fnos_posargs(args):
    """从透传参数里取位置参数(跳过 -p/--pool 及其值、-d/--dataset、--json)。"""
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-p", "--pool", "-d", "--dataset"):
            i += 2
            continue
        if a == "--json":
            i += 1
            continue
        pos.append(a)
        i += 1
    return pos


def _fnos_dispatch_guard(rest):
    """fnOS 子命令的前置校验; 返回非 0 表示应直接以该码退出, 0 表示放行。

    修复: 顶层 `zfs-tool.py detail <不存在的池>` 原来直接透传给
    zt_fnos, 而 display_pool_detail() 对 `zfs get all` 失败不作判断 → 全空
    输出 + exit 0(真机实测)。这里在本体入口先校验池存在, 不存在则 stderr
    报错 + 非 0 返回, 让"池不存在"这件事在两条入口上行为一致。
    只对 detail 生效 —— 其余 fnOS 子命令的池参数语义由 zt_fnos 侧负责。
    """
    if not rest:
        return 0
    pos = _fnos_posargs(rest[1:])
    if rest[0] == "detail" and pos and not pool_exists(pos[0]):
        print("Pool 不存在: %s" % pos[0], file=sys.stderr)
        return 2
    return 0


def cmd_fnos_menu():
    """主菜单 25: fnOS 加密存储 / TPM 常用入口。"""
    while True:
        title("🛠 fnOS 加密存储 / TPM", "基于 zt_fnos.py — 新建加密池向导 / 密钥 / 解锁 / 自动解锁 / TPM(后续)")
        print()
        print(" 1. 新建加密存储池 (向导)")
        print(" 2. 环境扫描 (scan)")
        print(" 3. 密钥: 备份 / 恢复 / 清理")
        print(" 4. 解锁 / 锁定 / 删除存储池")
        print(" 5. 自动解锁服务 (systemd) 开/关")
        print(" 6. 查看池详情")
        print(" 7. TPM 2.0 密封管理")
        print(" 8. 一致性检查 / 修复 mount 表")
        print(" 9. 系统恢复向导")
        print(" 0. 返回主菜单")
        print()
        # 🆕 交互优化 ④: 这里是层级最深的一段(25 → 子菜单 → 子项),
        #    逐项标出等价命令, 免得每次都要顺着菜单点进去。
        cli_hint([("1", "zfs-tool.py pool-create"),
                  ("2", "zfs-tool.py scan"),
                  ("4", "zfs-tool.py unlock | lock | destroy <pool>"),
                  ("5", "zfs-tool.py autounlock on | off"),
                  ("6", "zfs-tool.py detail <pool>"),
                  ("7", "zfs-tool.py tpm-menu | tpm-list | tpm-info | tpm-seal | tpm-unseal"),
                  ("8", "zfs-tool.py mount-verify | mount-fix"),
                  ("9", "zfs-tool.py recovery")])
        print()
        opt = ask("选择: ").strip()
        if opt == "1":
            fnos_dispatch(["pool-create"])
        elif opt == "2":
            fnos_dispatch(["scan"])
        elif opt == "3":
            title("🔑 密钥管理 (fnOS)", "备份 / 恢复 / 清理孤儿密钥")
            print()
            print(" 1. 交互备份(本地/USB, gpg)")
            print(" 2. 快速备份(匹配池)")
            print(" 3. 恢复密钥")
            print(" 4. 清理孤儿密钥")
            print(" 0. 返回")
            cli_hint([("1", "zfs-tool.py key-backup"),
                      ("2", "zfs-tool.py key-backup-quick"),
                      ("3", "zfs-tool.py keys-restore"),
                      ("4", "zfs-tool.py keys-cleanup")])
            print()
            k = ask("选择: ").strip()
            if k == "1":
                fnos_dispatch(["key-backup"])
            elif k == "2":
                fnos_dispatch(["key-backup-quick"])
            elif k == "3":
                fnos_dispatch(["keys-restore"])
            elif k == "4":
                fnos_dispatch(["keys-cleanup"])
        elif opt == "4":
            pool = ask("存储池名称(留空取消): ").strip()
            if pool:
                title("🔓 存储池管理", pool)
                print()
                print(" 1. 解锁挂载    2. 锁定")
                print(" 3. 删除(危险)  0. 返回")
                m = ask("选择: ").strip()
                if m == "1":
                    fnos_dispatch(["unlock", pool])
                elif m == "2":
                    fnos_dispatch(["lock", pool])
                elif m == "3":
                    fnos_dispatch(["destroy", pool])
        elif opt == "5":
            print()
            print(" 1. 安装自动解锁服务")
            print(" 2. 卸载自动解锁服务")
            m = ask("选择: ").strip()
            if m == "1":
                fnos_dispatch(["autounlock", "on"])
            elif m == "2":
                fnos_dispatch(["autounlock", "off"])
        elif opt == "6":
            pool = ask("存储池名称(留空取消): ").strip()
            if pool:
                fnos_dispatch(["detail", pool])
        elif opt == "7":
            title("🔐 TPM 2.0 密封管理 (zt_fnos)", "密封/解封/批量解封/清理明文密钥/引导解锁/诊断")
            print()
            print(" 1. 密封密钥到 TPM (tpm-seal)")
            print(" 2. 解封 (tpm-unseal)")
            print(" 3. 已密封列表 (tpm-list)")
            print(" 4. TPM 引导解锁服务 on/off/verify (tpm-boot)")
            print(" 5. 智能清理明文 .key (tpm-cleanup)")
            print(" 6. 环境/DA 诊断 (tpm-detect)")
            print(" 7. 重新密封 (tpm-reseal)")
            print(" 8. 移除密封降级 (tpm-remove)")
            print(" 0. 返回")
            tp = ask("选择: ").strip()
            if tp == "1":
                pool = ask("存储池名称: ").strip()
                if pool:
                    if ask_yes("使用 PIN 双因素? (y/N): "):
                        fnos_dispatch(["tpm-seal", pool, "--pin"])
                    else:
                        fnos_dispatch(["tpm-seal", pool])
            elif tp == "2":
                pool = ask("存储池名称: ").strip()
                if pool:
                    fnos_dispatch(["tpm-unseal", pool])
            elif tp == "3":
                fnos_dispatch(["tpm-list"])
            elif tp == "4":
                print(" 1. 安装  2. 卸载  3. 验证")
                bo = ask("选择: ").strip()
                if bo == "1":
                    fnos_dispatch(["tpm-boot", "on"])
                elif bo == "2":
                    fnos_dispatch(["tpm-boot", "off"])
                elif bo == "3":
                    fnos_dispatch(["tpm-boot", "verify"])
            elif tp == "5":
                pool = ask("存储池名称(留空=全部可清理): ").strip()
                if pool:
                    fnos_dispatch(["tpm-cleanup", pool])
                else:
                    fnos_dispatch(["tpm-cleanup"])
            elif tp == "6":
                fnos_dispatch(["tpm-detect"])
            elif tp == "7":
                pool = ask("存储池名称: ").strip()
                if pool:
                    fnos_dispatch(["tpm-reseal", pool])
            elif tp == "8":
                pool = ask("存储池名称: ").strip()
                if pool:
                    fnos_dispatch(["tpm-remove", pool])
        elif opt == "8":
            print()
            print(" 1. 一致性检查  2. 修复 mount 表")
            mv = ask("选择: ").strip()
            if mv == "1":
                fnos_dispatch(["mount-verify"])
            elif mv == "2":
                fnos_dispatch(["mount-fix"])
        elif opt == "9":
            fnos_dispatch(["recovery"])
        elif opt == "0":
            return
        else:
            print("无效选择")
            try:
                __import__("time").sleep(0.8)
            except Exception:
                pass


def cmd_arc():
    title("💾 ARC / L2ARC 缓存", "查看 ARC/L2 命中率与分布, 可实时刷新 (Ctrl+C 返回)")
    if not os.path.exists(ARCSTATS):
        print(c("red", "未找到 arcstats"))
        pause()
        return

    def paint():
        a = arc_stats()
        print()
        print("ARC: %s GiB / %s GiB" % (human_gib(a["size"]), human_gib(a["c_max"])))
        print()
        r = hit_rate(a["hits"], a["misses"])
        print("ARC Hit : %s" % (c("green", r) if r != "N/A" else "N/A"))
        r2 = hit_rate(a["l2_hits"], a["l2_misses"])
        print("L2ARC Hit : %s" % (c("cyan", r2) if r2 != "N/A" else "N/A"))
        print()
        print("ARC Breakdown:")
        print("MFU %.2f GiB" % float(human_gib(a["mfu_size"])))
        print("MRU %.2f GiB" % float(human_gib(a["mru_size"])))

    paint()
    print()
    if ask_yes("实时刷新? (y/N): "):
        print("Ctrl+C 返回菜单")

        def _sig(_s, _f):
            raise KeyboardInterrupt

        old = signal.signal(signal.SIGINT, _sig)
        try:
            while True:
                _cls()
                print(c("white", "ZFS ARC Monitor %s" % datetime.now().strftime("%F %T")))
                paint()
                __import__("time").sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGINT, old)
    pause()


def cmd_iostat():
    title("📈 ZFS I/O 监控", "按设定秒数持续刷新全池读写速率 (Ctrl+C 返回)")
    print()
    # 🩸 复验：非交互终端下 `ask()` 恒返回空 ⇒ 直接用默认间隔进入
    #   **无限刷新循环**（死循环 + 刷屏，脚本永不返回）。这里直接拒绝并给替代命令。
    if not sys.stdin.isatty():
        print(c("yellow", "非交互终端下不进入实时监控（会死循环）。替代做法:"))
        print("  一次采样看延迟归因: zfs-tool.py lat")
        return 2
    interval = ask("输入间隔秒数 [默认 2]: ").strip()
    if not interval:
        interval = "2"
    if not is_num(interval) or int(interval) < 1:
        print(c("red", "请输入正整数秒数"))
        pause()
        return
    print()
    print("Ctrl+C 返回菜单")

    def _sig(_s, _f):
        raise KeyboardInterrupt

    old = signal.signal(signal.SIGINT, _sig)
    try:
        while True:
            _cls()
            print(c("white", "ZFS I/O %s" % datetime.now().strftime("%F %T")))
            p = run(["zpool", "iostat", "-p", interval, "1"])
            if p:
                print(p.stdout, end="")
            __import__("time").sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, old)


# ---------------------------------------------------------------------------
# I/O 延迟归因 (`zpool iostat -l/-q/-r/-w`) —— 纯只读
# 现有 `iostat` 只有 ops/带宽视角; 这里补"为什么卡"的延迟归因视角。
# ---------------------------------------------------------------------------
# `zpool iostat -H` **不输出表头**, 列序由 ZFS 固定(实测 ZFS 2.4.1, `-l` 共 18 列)。
LAT_COLS_L = ["pool", "alloc", "free",
              "read_ops", "write_ops", "read_bw", "write_bw",
              "total_wait_read", "total_wait_write",
              "disk_wait_read", "disk_wait_write",
              "syncq_wait_read", "syncq_wait_write",
              "asyncq_wait_read", "asyncq_wait_write",
              "scrub_wait", "trim_wait", "rebuild_wait"]
_LAT_UNITS = {"ns": 1e-6, "us": 1e-3, "ms": 1.0, "s": 1000.0}
# 单次采样窗口上限(秒) —— 防止 `--interval 60 --count 1000` 这类"挂住终端"的输入
_LAT_MAX_WINDOW = 300


def _lat_ms(text):
    """把 `35ms` / `1.2s` / `650ns` 解析成**毫秒浮点**; `-`(无数据)与不可解析返回 None。

    ⚠️ 无数据必须与 0 区分开 —— zpool 用 `-` 表示"本次采样该方向没有 IO"，
    当成 0 会得出"完全没有延迟"的错误结论。
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t or t == "-":
        return None
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s)$", t)
    if not m:
        return None
    try:
        return float(m.group(1)) * _LAT_UNITS[m.group(2)]
    except (ValueError, KeyError):
        return None


def _lat_fmt(v):
    return "-" if v is None else "%.2fms" % v


def _lat_run(pool, extra, interval=1, count=1):
    """跑一次 `zpool iostat <extra> -y -H <pool> <interval> <count>`。

    ⚠️ 实测(ZFS 2.4.1)两条硬约束，写死在这里免得后人踩：
      ① **pool 必须写在 interval/count 之前**，否则 `Unable to parse pools/vdevs list.`
         （`zpool iostat -l -y 1 1 <pool>` 就是错的）；
      ② 必须带 `-y` —— 不带时拿到的是**自启动累计值**，会被当成"当前值"误读。
    返回 (rc, 行列表, 原始 stdout)。
    """
    argv = ["zpool", "iostat"] + list(extra) + ["-y", "-H"]
    if pool:
        argv.append(pool)
    argv += [str(interval), str(count)]
    p = run(argv)
    if p is None or p.returncode != 0:
        return 1, [], ""
    rows = []
    for ln in p.stdout.splitlines():
        if not ln.strip():
            continue
        cells = ln.split("\t") if "\t" in ln else ln.split()
        rows.append([x.strip() for x in cells])
    return 0, rows, p.stdout


def _lat_metrics(row):
    """按 `LAT_COLS_L` 解析一行；**列数不符就返回 None**（调用方原样打印，不硬猜列）。"""
    if len(row) != len(LAT_COLS_L):
        return None
    d = dict(zip(LAT_COLS_L, row))
    m = {"pool": d["pool"], "raw": row}
    for k in ("alloc", "free", "read_ops", "write_ops", "read_bw", "write_bw"):
        m[k] = d[k]
    for k in LAT_COLS_L[7:]:
        m[k] = _lat_ms(d[k])
    m["raw_wait"] = dict((k, d[k]) for k in LAT_COLS_L[7:])
    return m


def _lat_verdict(m):
    """按设计文档的归因规则给结论（结论列表, 建议列表）。

    规则: ① disk_wait ≈ total_wait 且都不小 ⇒ 盘/链路慢；
          ② syncq/asyncq_wait > disk_wait ⇒ ZFS 内部排队(同步写路径 / 写饱和)；
          ③~⑤(请求尺寸 / 积压 / 长尾)需要 `-r`/`-q`/`-w` 采样，这里只给"该怎么继续查"。
    """
    big = 5.0      # 5ms: 家用 raidz2 上"值得看一眼"的阈值
    verdicts, tips = [], []
    pairs = (("写", m.get("total_wait_write"), m.get("disk_wait_write"),
              m.get("syncq_wait_write"), m.get("asyncq_wait_write")),
             ("读", m.get("total_wait_read"), m.get("disk_wait_read"),
              m.get("syncq_wait_read"), m.get("asyncq_wait_read")))
    for tag, tw, dw, sq, aq in pairs:
        if dw is not None and tw is not None and dw >= big and dw >= 0.8 * tw:
            verdicts.append("%s: disk_wait(%s) 与 total_wait(%s) 同量级 ⇒ **瓶颈在盘/链路**"
                            % (tag, _lat_fmt(dw), _lat_fmt(tw)))
        if sq is not None and sq >= big and (dw is None or sq > dw):
            verdicts.append("%s: syncq_wait(%s) > disk_wait(%s) ⇒ **不是慢盘, 是 ZFS "
                            "同步写路径排队**(查 zil / 同步写来源)"
                            % (tag, _lat_fmt(sq), _lat_fmt(dw)))
        if aq is not None and aq >= big and (dw is None or aq > dw):
            verdicts.append("%s: asyncq_wait(%s) > disk_wait(%s) ⇒ **异步写队列排队**(写饱和)"
                            % (tag, _lat_fmt(aq), _lat_fmt(dw)))
        if dw is not None and dw < big and sq is not None and sq < big \
                and aq is not None and aq < big:
            verdicts.append("%s: disk/syncq/asyncq 均在 %.0fms 以内 ⇒ 延迟健康" % (tag, big))
    tips.append("用 `lat --req` 看请求尺寸分布(512B/4K 占比高 ⇒ 随机小 IO)")
    tips.append("用 `lat --queue` 看积压(pend 长期非零 ⇒ 消化不完)")
    return verdicts, tips


def _lat_one(pool, queue=False, req=False, hist=False,
             interval=1, count=1, as_json=False):
    """单池延迟归因；返回 {"rc": int, "data": dict}。"""
    data = {"pool": pool, "latency": None, "verdict": [], "tips": [],
            "extra_samples": []}
    # ⚠️ 真机实测：`-l -q` 的列数与 `-l` **不一样**（多了 pend/activ）
    #   ⇒ `--queue` 不再并进延迟解析（并进去会因列数不符判成 rc=2），
    #   改为与 `-r`/`-w` 同样"单独采样 + 原样输出"。
    extra = ["-l"]
    rc, rows, raw = _lat_run(pool, extra, interval, count)
    if rc != 0:
        data["error"] = "zpool iostat %s 执行失败" % " ".join(extra)
        if not as_json:
            print(c("red", "  zpool iostat 执行失败: " + " ".join(extra)))
        return {"rc": 1, "data": data}
    parsed = [m for m in (_lat_metrics(x) for x in rows) if m]
    if not parsed:
        data["unparsed"] = raw.strip()
        rc = 2
        if not as_json:
            print(c("yellow", "  列数与预期(%d)不符 —— 原样输出, 不做可能误读的解析:"
                    % len(LAT_COLS_L)))
            print(raw.rstrip())
    else:
        m = parsed[0]
        verdicts, tips = _lat_verdict(m)
        data["latency"] = m
        data["verdict"] = verdicts
        data["tips"] = tips
        if not as_json:
            print()
            print(c("white", "▶ Pool: %s   (采样 %d 次, 间隔 %ds)"
                    % (m["pool"], count, interval)))
            print("  total_wait : read %-9s write %s"
                  % (_lat_fmt(m["total_wait_read"]), _lat_fmt(m["total_wait_write"])))
            print("  disk_wait  : read %-9s write %s"
                  % (_lat_fmt(m["disk_wait_read"]), _lat_fmt(m["disk_wait_write"])))
            print("  syncq_wait : read %-9s write %s"
                  % (_lat_fmt(m["syncq_wait_read"]), _lat_fmt(m["syncq_wait_write"])))
            print("  asyncq_wait: read %-9s write %s"
                  % (_lat_fmt(m["asyncq_wait_read"]), _lat_fmt(m["asyncq_wait_write"])))
            print("  scrub/trim/rebuild wait: %s / %s / %s"
                  % (_lat_fmt(m["scrub_wait"]), _lat_fmt(m["trim_wait"]),
                     _lat_fmt(m["rebuild_wait"])))
            print("  ops: read %s write %s    bw: read %s write %s"
                  % (m["read_ops"], m["write_ops"], m["read_bw"], m["write_bw"]))
            print()
            if verdicts:
                for v in verdicts:
                    print(c("cyan", "  归因: " + v))
            else:
                print(c("dim", "  归因: 无异常(各项延迟都低)"))
            for t in tips:
                print(c("dim", "  提示: " + t))
    # `-r` / `-w` 属于**另一组显示模式**(与 -l 互斥, 见 `zpool iostat` usage) ⇒ 单独采样
    for flag, label in (("-r", "请求尺寸直方图 (-r)"),
                        ("-w", "延迟直方图 (-w)"),
                        ("-q", "队列积压 (-q: pend/activ)")):
        want = ((flag == "-r" and req) or (flag == "-w" and hist)
                or (flag == "-q" and queue))
        if not want:
            continue
        r2, _rows2, raw2 = _lat_run(pool, [flag], interval, count)
        data["extra_samples"].append({"mode": flag, "rc": r2, "raw": raw2.strip()})
        if r2 != 0:
            rc = max(rc, 1)
            if not as_json:
                print(c("yellow", "  %s 采样失败" % label))
            continue
        if not as_json:
            print()
            print(c("white", "  %s:" % label))
            paged(raw2.rstrip(), threshold=25)
    return {"rc": rc, "data": data}


def cmd_lat(pool=None, queue=False, req=False, hist=False,
            interval=1, count=1, as_json=False):
    """I/O 延迟归因（纯只读）。默认 `iostat -l`；`--queue` 追加 `-q`。"""
    import json
    pools = [pool] if pool else get_pools()
    if not pools:
        print("无 Pool")
        return 1
    result = {"interval": interval, "count": count, "pools": []}
    rc_all = 0
    for p in pools:
        got = _lat_one(p, queue=queue, req=req, hist=hist,
                       interval=interval, count=count, as_json=as_json)
        result["pools"].append(got["data"])
        rc_all = max(rc_all, got["rc"])
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return rc_all


def _lat_cli(extra):
    """CLI: lat [-p <pool>] [--queue] [--req] [--hist] [--interval N] [--count N]"""
    # ⚠️ `main()` 会把 `-p/--pool` 摘走（只留全局 TARGET_POOL）⇒ 这里必须接回来，
    #    否则 `lat -p <pool>` 会退化成"遍历全部池"（extra 里的 -p 分支永远收不到）。
    pool = TARGET_POOL or None
    queue = req = hist = False
    interval, count = 1, 1
    as_json = FLAG_JSON
    i = 0
    while i < len(extra):
        a = extra[i]
        nxt = extra[i + 1] if i + 1 < len(extra) else ""
        if a in ("-p", "--pool"):
            pool = nxt
            i += 1
        elif a in ("-i", "--interval"):
            interval = int(nxt) if nxt.isdigit() and int(nxt) > 0 else 1
            i += 1
        elif a in ("-c", "--count"):
            count = int(nxt) if nxt.isdigit() and int(nxt) > 0 else 1
            i += 1
        elif a in ("-q", "--queue"):
            queue = True
        elif a == "--req":
            req = True
        elif a == "--hist":
            hist = True
        elif a == "--json":
            as_json = True
        else:
            print(c("yellow", "忽略无法识别的参数: %s" % a))
        i += 1
    if interval * count > _LAT_MAX_WINDOW:
        # 不许无界采样: zpool 会一直占着终端, 脚本里更是会挂住
        old = interval * count
        count = max(1, _LAT_MAX_WINDOW // max(1, interval))
        print(c("yellow", "  interval×count=%d 秒过长, 已收敛为 %d 秒(interval %d × count %d)"
                % (old, interval * count, interval, count)))
    return cmd_lat(pool=pool, queue=queue, req=req, hist=hist,
                   interval=interval, count=count, as_json=as_json)


# ---------------------------------------------------------------------------
# checkpoint —— 池级回滚点
# 用途：`zfs rewrite` / 危险维护**之前**打一个池级回滚点，出事可整池退回。
# ---------------------------------------------------------------------------
def _cp_value(pool):
    """读池的 `checkpoint` 属性；返回 (ok, value)。`-` 表示没有回滚点。

    🩸 判据**不能**看 `zpool checkpoint` 的退出码 —— 实测(ZFS 2.4.1)它**无参数时
    也返回 0**（usage 走 stderr）⇒ 必须回读 `zpool get -H -o value checkpoint`
    看状态是否真的变了（由 `-` 变非 `-`，或反过来）。
    """
    p = run(["zpool", "get", "-H", "-o", "value", "checkpoint", pool])
    if p is None or p.returncode != 0:
        return False, ""
    return True, (p.stdout or "").strip()


def cmd_checkpoint(action=None, pool=None):
    """池级 checkpoint（一次性回滚点）：查看 / 创建 / 丢弃。

    比快照粗（只能有一个、回滚要 export 后 `import --rewind-to-checkpoint`），
    但**便宜且能覆盖元数据层面的破坏** —— 适合"跑一堆重写操作前先钉一个点"。
    """
    pools = [pool] if pool else get_pools()
    if not pools:
        print("无 Pool")
        return 1
    if action in (None, "status"):
        print(c("white", "池级回滚点 (checkpoint) 状态:"))
        for p in pools:
            ok, val = _cp_value(p)
            if not ok:
                print(c("yellow", "  %s: 读取失败" % p))
                continue
            if val and val != "-":
                print(c("green", "  %s: 有回滚点 (%s)" % (p, val)))
            else:
                print("  %s: 无" % p)
        print(c("dim", "  创建: checkpoint create <pool>  |  丢弃: checkpoint discard <pool>"))
        return 0
    if action == "create":
        rc_all = 0
        for p in pools:
            ok, before = _cp_value(p)
            if not ok:
                print(c("red", "  %s: 无法读取 checkpoint 状态, 已跳过" % p))
                rc_all = 1
                continue
            if before and before != "-":
                print(c("yellow", "  %s: 已有回滚点 (%s) —— 要先丢弃才能建新的" % (p, before)))
                continue
            argv = ["zpool", "checkpoint", p]
            if FLAG_DRY:
                dry_preview("创建池级回滚点", [" ".join(argv)], facts=[("池", p)],
                            notes=["checkpoint 会**占用一部分池空间**(记录旧块), 直到被丢弃。",
                                   "⚠️ 一个池同时只能有一个: 再建前必须先 `checkpoint discard`。",
                                   "回滚(需在池未导入时): `zpool import --rewind-to-checkpoint <pool>`。"])
                continue
            if not confirm_destructive("为 %s 创建池级回滚点" % p):
                print("已取消")
                rc_all = 1
                continue
            print("  正在为 %s 创建回滚点..." % p)
            run(argv)
            ok2, after = _cp_value(p)       # 🩸 不看 rc, 回读属性确认
            if ok2 and after and after != "-":
                print(c("green", "  %s: 回滚点已创建 (%s)" % (p, after)))
                log("checkpoint create " + p)
            else:
                print(c("red", "  %s: 创建后回读仍为 '%s' —— 判定失败" % (p, after)))
                rc_all = 1
        return rc_all
    if action == "discard":
        rc_all = 0
        for p in pools:
            ok, before = _cp_value(p)
            if not ok or not before or before == "-":
                print(c("yellow", "  %s: 没有回滚点可丢弃" % p))
                continue
            argv = ["zpool", "checkpoint", "-d", p]
            if FLAG_DRY:
                dry_preview("丢弃池级回滚点", [" ".join(argv)],
                            facts=[("池", p), ("当前回滚点", before)],
                            notes=["⚠ 丢弃后**再也回不到**那个时刻 —— 不可逆。"])
                continue
            if not confirm_destructive("丢弃 %s 的回滚点" % p):
                print("已取消")
                rc_all = 1
                continue
            run(argv)
            ok2, after = _cp_value(p)
            if ok2 and (not after or after == "-"):
                print(c("green", "  %s: 回滚点已丢弃" % p))
                log("checkpoint discard " + p)
            else:
                print(c("red", "  %s: 丢弃后回读仍为 '%s' —— 判定失败" % (p, after)))
                rc_all = 1
        return rc_all
    if action == "rollback":
        print(c("yellow", "回滚到 checkpoint 必须在**池未导入**时做，本工具不代劳。步骤:"))
        print("  1) zpool export <pool>")
        print("  2) zpool import --rewind-to-checkpoint <pool>")
        print("  3) 回滚完成后该 checkpoint 会被自动丢弃")
        print(c("red", "  ⚠ 这会丢弃该回滚点之后的**所有写入**；先确认数据已备份。"))
        return 2
    print("未知动作: %s (可用 status|create|discard|rollback)" % action)
    return 2


def _checkpoint_cli(extra):
    """CLI: checkpoint [status|create|discard|rollback] [池名]"""
    action = None
    pool = TARGET_POOL or None
    for a in extra:
        if a in ("status", "create", "discard", "rollback"):
            action = a
        elif not a.startswith("-"):
            pool = a
        else:
            print(c("yellow", "忽略无法识别的参数: %s" % a))
    return cmd_checkpoint(action, pool)


def cmd_progress():
    title("⏳ ZFS 活动进度", "查看进行中的 scrub / resilver / trim 进度")
    any_act = False
    for p in get_pools():
        text = out(["zpool", "status", p])
        keep = []
        for ln in text.splitlines():
            # 修复: 第二个正则去掉 `resilvered` —— 它会让
            #   `scan: resilvered 1.2T in 0 days`(早已完成的历史 resilver)也命中,
            #   把结束了的扫描报成"进行中", 误导低峰窗口决策。
            if re.search(r"scan:|resilvered|trim:|trimming|replacing", ln) \
                    and re.search(r"in progress|trimming|replacing", ln):
                keep.append(ln.strip())
        if keep:
            any_act = True
            print()
            print(c("white", "▶ Pool: %s" % p))
            for k in keep:
                print("  " + k)
    if not any_act:
        print()
        print("当前没有进行中的 scrub / resilver / trim")
    pause()


# ===========================================================================
# 快照: 查看/创建/按天清理/保留清理/diff/回滚/备份
# ===========================================================================


def destroy_snaps(names):
    """分批销毁快照。

    修复: 原实现丢弃 `zfs destroy` 的返回码, 无条件把整批计入"已删除",
    返回的是"尝试数"而不是"成功数" → 被 hold / 被 clone / 只读数据集上删除失败时,
    调用方照样打印"已删除 N 个"(假成功)。
    现返回 (实际成功数, 尝试总数); 失败批打印首行 stderr 并落日志。
    """
    ok = 0
    tried = 0
    for i in range(0, len(names), 100):
        batch = names[i:i + 100]
        tried += len(batch)
        p = run(["zfs", "destroy"] + batch)
        if p is not None and p.returncode == 0:
            ok += len(batch)
        else:
            err = ((p.stderr if p else "") or "").strip().splitlines()
            first = err[0] if err else ("未找到 zfs 命令" if p is None else "rc=%d" % p.returncode)
            print(c("red", "  ⚠ 销毁失败(%d 个): %s" % (len(batch), first)))
            log("snapshot destroy failed (%d): %s" % (len(batch), first))
    return ok, tried


def _pick_snapshot(ds):
    """交互选择快照, 返回完整快照名或 ''。"""
    snaps = snapshots(ds)
    if not snaps:
        print(c("yellow", "该数据集没有任何快照"))
        return ""
    print()
    print("最近快照 (最多 15 条):")
    for i, s in enumerate(snaps[:15]):
        print("  %2d) %s" % (i + 1, s))
    print()
    sel = ask("输入序号/字母或完整快照名(回车取消): ")
    if not sel:
        return ""
    if is_num(sel):
        idx = int(sel, 10) - 1
        if 0 <= idx < min(15, len(snaps)):
            return snaps[idx]
        print(c("red", "序号超出范围"))
        return ""
    if "@" in sel:
        if ds_exists(sel):
            return sel
        print(c("red", "快照不存在: " + sel))
        return ""
    cand = ds + "@" + sel
    if ds_exists(cand):
        return cand
    print(c("red", "快照不存在: " + sel))
    return ""


def snap_list():
    ds = ask_dataset()
    if not ds:
        return
    print()
    text = out(["zfs", "list", "-t", "snapshot", "-r", ds, "-o", "name,creation,used"])
    print(text, end="")


def snap_create():
    ds = ask_dataset()
    if not ds:
        return
    name = "%s@manual_%s" % (ds, datetime.now().strftime("%Y%m%d_%H%M%S"))
    p = run(["zfs", "snapshot", name])
    if p is not None and p.returncode == 0:
        print(c("green", "创建成功:") + " " + name)
        log("snapshot create " + name)
    else:
        print(c("red", "创建失败: " + name))


def snap_prune():
    ds = ask_dataset()
    if not ds:
        return
    days = ask("删除多少天以前的快照: ").strip()
    if not is_num(days):
        print(c("red", "请输入数字"))
        return
    import time
    limit = time.time() - int(days) * 86400

    names, nums = [], {}
    text = out(["zfs", "list", "-Hp", "-t", "snapshot", "-r", ds, "-o", "name,creation"])
    for ln in text.splitlines():
        f = ln.split("\t")
        if len(f) == 2 and is_num(f[1]):
            nums[f[0]] = int(f[1])
    names = [n for n in nums if nums[n] < limit]

    if not names:
        print("没有可删除的旧快照")
        return
    print()
    print("准备删除 %d 个快照:" % len(names))
    for n in names:
        print("  " + n)
    print()
    print(c("red", "⚠ 删除不可恢复"))
    if not ask_yes("确认删除? (yes): "):
        print("取消")
        return
    n, tried = destroy_snaps(names)   # 修复: 按真实 rc 统计成功数
    if n < tried:
        print(c("yellow", "已删除 %d/%d 个快照, %d 个失败(见上方告警)" % (n, tried, tried - n)))
    else:
        print(c("green", "已删除 %d 个快照" % n))
    log("snapshot prune %s %s days: %d/%d removed" % (ds, days, n, tried))


def snap_keep(ds=None, keep=None, pattern=""):
    """清理快照: 保留最近 keep 份。参数为空则交互询问(菜单路径)。"""
    if ds is None:
        ds = ask_dataset()
        if not ds:
            return 2
        pattern = ask("只处理名称含此前缀的快照(回车=全部): ").strip()
    if keep is None:
        keep_s = ask("保留最近多少份: ").strip()
        if not is_num(keep_s) or int(keep_s) < 1:
            print(c("red", "保留数量必须是 >=1 的整数"))
            return 2
        keep = int(keep_s)

    all_snaps = snapshots(ds)
    if pattern:
        all_snaps = [s for s in all_snaps if pattern in s]
    if len(all_snaps) <= keep:
        print("快照数量(%d)未超过保留数(%d), 无需清理" % (len(all_snaps), keep))
        return 0
    dels = all_snaps[keep:]
    print()
    print("将删除 %d 个快照 (保留最近 %d 份):" % (len(dels), keep))
    for n in dels:
        print("  " + n)
    print()
    print(c("red", "⚠ 删除不可恢复"))
    if FLAG_DRY:
        cmds = ["zfs destroy " + s for s in dels[:15]]
        if len(dels) > 15:
            cmds.append("…(另 %d 个)" % (len(dels) - 15))
        return dry_preview(
            "清理快照(保留最近 %d 份)" % keep, cmds,
            facts=[("数据集", ds), ("待删除", "%d 个" % len(dels)), ("保留", "%d 份" % keep),
                   ("名称前缀过滤", pattern or "(全部)"), ("现有快照", "%d 个" % len(all_snaps))],
            notes=["⚠ 删除不可恢复。",
                   "删快照会断掉以它为基准的增量 send 链; 想保住增量源可用 `zfs bookmark`(不占数据)。",
                   "想先看 ZFS 自己的判断, 可对单个快照跑 `zfs destroy -n <ds>@<snap>`(只报告, 不删)。",
                   "要保留整体撤销能力, 可先打 `zpool checkpoint`(池级回滚点)。"])
    if not ask_yes("确认删除? (yes): "):
        print("取消")
        return 1
    n, tried = destroy_snaps(dels)    # 修复: 按真实 rc 统计成功数
    if n < tried:
        print(c("yellow", "已删除 %d/%d 个快照, %d 个失败(见上方告警)" % (n, tried, tried - n)))
        rc = 1
    else:
        print(c("green", "已删除 %d 个快照" % n))
        rc = 0
    log("snapshot keep-prune %s keep=%d: %d/%d removed" % (ds, keep, n, tried))
    return rc


def snap_diff():
    ds = ask_dataset()
    if not ds:
        return
    snap1 = _pick_snapshot(ds)
    if not snap1:
        return
    print()
    print("对比基准: " + snap1)
    other = ask("另一侧: 快照名(前缀可省略)或留空对比当前文件系统: ").strip()
    if not other:
        p = run(["zfs", "diff", snap1, ds])
    else:
        if "@" not in other:
            other = ds + "@" + other
        if not ds_exists(other):
            print(c("red", "快照不存在: " + other))
            return
        p = run(["zfs", "diff", snap1, other])
    print()
    print("图例: M=修改  A=新增  D=删除  R=重命名  +/- = 内容增减")
    if p is not None and p.returncode == 0:
        print(p.stdout, end="")
    else:
        print(c("red", "对比失败(数据集可能未挂载)"))


def snap_rollback(snap=None):
    """回滚到快照。snap 为空则交互询问(菜单路径)。"""
    if snap is None:
        ds = ask_dataset()
        if not ds:
            return 2
        snap = _pick_snapshot(ds)
        if not snap:
            return 2
    print()
    print(c("red", "⚠ 回滚会把数据集恢复到快照时刻, 之后的修改全部丢失!"))
    if FLAG_DRY:
        # 🩸 修复：原来预览写死 `use_r = False`，而真跑时
        #   带 `--yes` 会让 ask_yes 恒真 ⇒ **预览说"不丢中间快照"、实际却加了 `-r`**，
        #   预览与真跑不一致。现在预览用与真跑相同的判据（带 --yes 就按"会加 -r"预告）。
        use_r = bool(FLAG_ASSUME_YES)
    else:
        use_r = ask_yes("使用 -r 丢弃中间快照? (y/N): ")
    argv = ["zfs", "rollback"]
    if use_r:
        argv.append("-r")
    argv.append(snap)
    print()
    print("即将执行: " + " ".join(argv))
    if FLAG_DRY:
        ds = snap.split("@", 1)[0]
        try:
            newer = [s for s in snapshots(ds)
                     if s.split("@")[-1] > snap.split("@")[-1]]
        except Exception:
            newer = []
        facts = [("目标快照", snap), ("数据集", ds),
                 ("丢弃中间快照(-r)", "是" if use_r else "否"),
                 ("晚于该快照的快照数", "%d 个%s" % (len(newer), "(会被 -r 丢弃)" if use_r and newer else ""))]
        return dry_preview(
            "回滚数据集到快照", [" ".join(argv)], facts=facts,
            notes=["⚠ 不可逆: 该快照之后的**所有修改**都会丢失(除非另有快照/备份)。",
                   "想先看丢了什么: 用 `snapdiff`(对比快照与当前)或 `zfs diff`。",
                   "想留一条退路: 先打 `zpool checkpoint`(池级回滚点)。"])
    if not confirm_destructive(" ".join(argv)):
        print("已取消")
        return 1
    p = run(argv)
    if p is not None and p.returncode == 0:
        print(c("green", "回滚成功: " + snap))
        log("snapshot rollback " + snap)
        return 0
    print(c("red", "回滚失败"))
    return 1


def snap_backup():
    """zfs send/recv 备份向导(本地或 ssh)。"""
    print("—— zfs send/recv 备份向导 ——")
    ds = ask_dataset()
    if not ds:
        return
    snap = _pick_snapshot(ds)
    if not snap:
        return

    incr = ask("发送模式 全量(f)/增量(i 需选基准): ").strip().lower()
    send_cmd = ["zfs", "send"]
    if incr == "i":
        print("选择增量基准快照(比 %s 更早):" % snap)
        base = _pick_snapshot(ds)
        if not base:
            return
        if base == snap:
            print(c("red", "基准不能是同一个快照"))
            return
        send_cmd += ["-i", base]
    send_cmd.append(snap)

    kind = ask("目标类型 本地(l)/ssh(s): ").strip().lower()
    if kind == "s":
        host = ask("SSH 主机(user@host): ").strip()
        if not host:
            print(c("yellow", "已取消"))
            return
        dest = ask("远端目标数据集(建议全新路径): ").strip()
        if not dest:
            print(c("yellow", "已取消"))
            return
        print()
        print("即将执行: %s | ssh %s 'zfs receive %s'" % (" ".join(send_cmd), host, dest))
        print(c("yellow", "提示: 需要 ssh 免密/可登录, 且远端为 root"))
        if not ask_yes("确认执行? (yes): "):
            print("取消")
            return
        log("send start %s -> ssh %s:%s" % (" ".join(send_cmd), host, dest))
        # 修复: dest 会被远端 shell 解释, 必须转义 —— 原来直接拼字符串,
        #   含空格的目标名会被拆错, profile 被改还能在备份机以 root 执行任意命令。
        rc = _pipe_to(send_cmd, ["ssh", host, "zfs receive " + _shq(dest)])
    else:
        dest = ask("本地目标数据集(建议全新路径, 如 pool/backup/xxx): ").strip()
        if not dest:
            print(c("yellow", "已取消"))
            return
        dpool = dest.split("/", 1)[0]
        if not pool_exists(dpool):
            print(c("red", "目标所在 Pool 不存在: " + dpool))
            return
        print()
        print("即将执行: %s | zfs receive %s" % (" ".join(send_cmd), dest))
        if not ask_yes("确认执行? (yes): "):
            print("取消")
            return
        log("send start %s -> local:%s" % (" ".join(send_cmd), dest))
        rc = _pipe_to(send_cmd, ["zfs", "receive", dest])

    if rc == 0:
        print(c("green", "备份完成"))
        log("send finish -> " + dest)
    else:
        print(c("red", "备份失败(exit %d)" % rc))
        print("提示: 全量备份目标数据集不能已存在; 中途断传需 zfs receive -s 续传")


# 修复: 此处原有第 1 个 `_pipe_to(cmd1, cmd2)` 定义(pyflakes 报
# "redefinition of unused '_pipe_to'")。判断依据:
#   ① 文件内后出现的 `_pipe_to()`(原 4606 行, `return _pipe_chain([cmd1, cmd2])`)
#      才是运行时版本;
#   ② 两个调用点 `snap_backup()`(2213/2229)在模块执行完毕后才会被调用,
#      早已拿到新版; 旧版只对**定义顺序在它之前**的代码可见, 而文件里没有;
#   ③ 两版对外契约一致: 都返回 cmd2 退出码、都吞掉 cmd2 的 stdout/stderr
#      (新版在 _pipe_chain 里 `communicate()` 后丢弃)、启动失败都返回 1。
#      唯一差别是旧的 cmd1 用 DEVNULL 吞 stderr, 新的用 PIPE 读取后丢弃 —
#      对调用方不可见。
# 故直接删除该死代码, 保留唯一实现。
# ---- 文件级 SEND / RECEIVE(冷备: 快照 ↔ .zfs 文件) ----


def _run_to_file(argv, path, overwrite=False):
    """把命令 stdout 写入文件(zfs send > file)。
    🩸 修复: 原来无脑 `open(path, "wb")` ——
    目标已存在时**直接截断**（用户手滑输一个已有路径就把原文件毁了）。
    现在默认**拒绝覆盖**；确需覆盖必须由调用方显式传 `overwrite=True`。"""
    # 🩸 修复（高危）：原来先 `os.path.exists()` 判一次、再 `open(path,"wb")` ——
    #   两步之间是**TOCTOU 窗口**（估算最长 600 秒 + 交互确认），把路径换成**符号链接**
    #   就能让 root 写到任意目标（实测发现写穿成功：rc=0，victim 被写入 zfs 流）。
    #   改用 `os.open(..., O_CREAT|O_EXCL|O_NOFOLLOW)`：
    #     · `O_EXCL` —— "不存在才创建"由**内核原子保证**（不覆盖任何已有文件）；
    #     · `O_NOFOLLOW` —— 目标是符号链接时直接 ELOOP 报错，绝不跟随。
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return 1, "目标文件已存在，已拒绝覆盖: " + path
    except OSError as exc:
        return 1, "无法创建目标文件(%s): %s" % (path, exc)
    try:
        with os.fdopen(fd, "wb") as fh:
            p = subprocess.run(argv, stdout=fh, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stderr or "")
    except OSError as exc:
        return 1, str(exc)


def _run_from_file(argv, path):
    """把文件内容作为 stdin 喂给命令(zfs receive < file)。"""
    try:
        with open(path, "rb") as fh:
            p = subprocess.run(argv, stdin=fh, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace")
        return p.returncode, (p.stderr or "")
    except OSError as exc:
        return 1, str(exc)


def _parse_size_zfs(text):
    """把 `288M` / `16.3T` / `1.5K` 这类 ZFS 输出解析成字节数；失败返回 None。

    🩸 修复（高危）：本函数原名 `_parse_size`，与文件后段 DSM 模块里
    **既有的同名函数撞名** —— Python 里后定义者覆盖前者，于是本批新增的
    "`zfs send -n -v` 真估算 + 目标盘空间检查"**100% 静默失效**
    （真机 ZFS 报 62.7G，这里却解析出 None）。改名后唯一；
    `work/check-cmd-tables.py` 也加了"同文件函数重名"静态检查防复发。
    """
    m = re.match(r"^([0-9.]+)\s*([KMGTPE]?)B?$", (text or "").strip(), re.I)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
            "T": 1024 ** 4, "P": 1024 ** 5, "E": 1024 ** 6}[m.group(2).upper()]
    return int(val * mult)


def _snap_exists(snap):
    """快照是否存在（只认 `zfs list -t snapshot`，不猜命名）。"""
    if not snap or "@" not in snap:
        return False
    p = run_noblock(["zfs", "list", "-H", "-t", "snapshot", "-o", "name", snap], timeout=20)
    return p is not None and p.returncode == 0 and bool((p.stdout or "").strip())


def _ds_createtxg(name):
    """快照的 createtxg（用于比较哪个更早）；读不到返回 None（**不假装校验过**）。"""
    p = run_noblock(["zfs", "get", "-H", "-p", "-o", "value", "createtxg", name], timeout=20)
    if p is None or p.returncode != 0:
        return None
    v = (p.stdout or "").strip()
    return int(v) if is_num(v) else None


def _ask_send_opts():
    """交互式询问发送选项（菜单路径）。返回 dict。"""
    opts = {"raw": False, "compressed": False, "replicate": False, "holds": False}
    if not ask_yes("使用高级发送选项(raw/压缩/复制属性/包含 holds)? (y/N): "):
        return opts
    opts["raw"] = ask_yes("  --raw (-w) 原始加密流(密钥未加载也能备份)? (y/N): ")
    if not opts["raw"]:
        opts["compressed"] = ask_yes("  --compressed (-c) 压缩流? (y/N): ")
    opts["replicate"] = ask_yes("  --replicate (-R) 连快照与属性一起复制? (y/N): ")
    opts["holds"] = ask_yes("  --holds (-h) 包含 holds? (y/N): ")
    return opts


def _build_send_cmd(opts, snap, base=None):
    """按选项组装 `zfs send ...`（argv 列表，天然防注入）。"""
    cmd = ["zfs", "send"]
    if opts.get("raw"):
        cmd.append("-w")             # man: -w/--raw 与 -c 互斥
    elif opts.get("compressed"):
        cmd.append("-c")
    if opts.get("replicate"):
        cmd.append("-R")
    if opts.get("holds"):
        cmd.append("-h")
    if base:
        cmd += ["-i", base]
    cmd.append(snap)
    return cmd


def _one_line(s):
    """把字符串里的换行折成可见的 \\n / \\r。

    🩸 修复：目标路径含换行时，预览会被撕裂成多行，而且 `log()`
    会把后半段写成一个**看起来独立的日志行**（日志行注入）。
    """
    return (s or "").replace("\r", "\\r").replace("\n", "\\n")


def _send_opt_conflicts(opts, snap):
    """本地拦下**必然失败**的组合（真机实测：加密数据集上 `-R -i` 必须配 raw）。"""
    ds = snap.split("@")[0]
    enc = ds_prop(ds, "encryption")
    encrypted = bool(enc) and enc not in ("off", "-")
    if opts.get("replicate") and encrypted and not opts.get("raw"):
        return ("数据集 %s 是加密的 (encryption=%s)：`zfs send -R` 会带 properties，"
                "ZFS 要求必须同时用 --raw (-w)（真机实测否则直接报 "
                "\"may not be sent with properties without the raw flag\"）。" % (ds, enc))
    if opts.get("holds") and encrypted and not opts.get("raw"):
        # 🩸 修复：`-h`（holds）与 `-R` 一样会带 properties ⇒ 加密数据集上
        #   必然被 ZFS 拒绝（真机 `zfs send -n -h` rc=1），原来只拦了 `-R`。
        return ("数据集 %s 是加密的 (encryption=%s)：`zfs send -h`（holds）同样会带 "
                "properties，ZFS 要求必须同时用 --raw (-w)（真机实测否则报 "
                "\"may not be sent with properties without the raw flag\"）。" % (ds, enc))
    if opts.get("raw") and opts.get("compressed"):
        return "--raw (-w) 与 --compressed (-c) 不能同时使用。"
    return None


def _send_estimate(send_cmd, timeout=600):
    """用 ZFS 原生 `zfs send -n -v` 做**真估算**（不是本工具自己猜）。
    🆕 新增：返回 `(bytes|None, ZFS 自报原始数字串, 原始输出片段)` ——
    预览里同时给出原始串，便于与手工 `zfs send -n -v` 逐字核对。
    自己带死线 —— 大池上 `-n` 也可能很慢。"""
    argv = list(send_cmd)
    argv[2:2] = ["-n", "-v"]
    p = run(argv, timeout=timeout)
    if p is None:
        return None, "", "无法执行 zfs send（未找到命令）"
    text = ((p.stdout or "") + (p.stderr or "")).strip()
    size, num = None, ""
    for ln in text.splitlines():
        mm = re.search(r"estimated size is\s+(.+?)\s*$", ln)
        if mm:
            num = mm.group(1).strip()
            size = _parse_size_zfs(num)
    return size, num, text[:400]


def cmd_send_file(opts=None, snap=None, base=None, path=None):
    """把快照发送成 .zfs 文件(冷备/异地存档)。

    🆕 新增：支持非交互用法与发送选项 ——
      `send-file [--raw|-w] [--compressed|-c] [--replicate|-R] [--holds|-h]
                 [-i <基准快照>] [<源快照>] [<目标文件>] [--dry-run]`
    · 给 `<源快照>` ⇒ 直发（不需要 tty，脚本可用）；不给 ⇒ 仍走原交互向导。
    · 预览用 ZFS 原生 `zfs send -n -v` 估算流大小，并检查目标盘剩余空间。
    """
    interactive = snap is None
    if interactive:
        print("—— 发送快照到文件 ——")
        ds = ask_dataset()
        if not ds:
            return 2
        snap = _pick_snapshot(ds)
        if not snap:
            return 2
        if opts is None:
            opts = _ask_send_opts()
        if base is None and ask_yes("使用增量发送(-i, 需先有基准)? (y/N): "):
            print("选择增量基准快照:")
            base = _pick_snapshot(ds)
            if not base or base == snap:
                print(c("red", "基准无效"))
                return 2
    opts = dict(opts or {})
    if not _snap_exists(snap):
        print(c("red", "快照不存在: " + str(snap)))
        return 2
    if base:
        if not _snap_exists(base):
            print(c("red", "增量基准快照不存在: " + base))
            return 2
        if base.split("@")[0] != snap.split("@")[0]:
            print(c("red", "基准与源必须是**同一个数据集**的快照（-i 的要求）：%s ≠ %s"
                  % (base.split("@")[0], snap.split("@")[0])))
            return 2
        if base == snap:
            print(c("red", "基准与源是**同一个快照**：%s —— 增量发送要求基准更早。" % snap))
            return 2
        # 🩸 修复：CLI 路径原来没有"基准必须更早"的校验（交互路径靠
        #   `_pick_snapshot` 的选择顺序保证）⇒ 必然被 ZFS 拒绝的组合会被放行 rc=0
        #   （真机 `zfs send -i A A` rc=1 "not an earlier snapshot"）。
        _tb, _ts = _ds_createtxg(base), _ds_createtxg(snap)
        if _tb is not None and _ts is not None and _tb >= _ts:
            print(c("red", "基准快照不比源更早（createtxg %d ≥ %d）—— zfs send -i 会拒绝。"
                  % (_tb, _ts)))
            return 2
        if _tb is None or _ts is None:
            print(c("yellow", "提示: 读不到 createtxg，无法本地校验「基准早于源」；"
                              "若顺序不对，zfs 会在真正发送时报错。"))
    bad = _send_opt_conflicts(opts, snap)
    if bad:
        print(c("red", "发送选项组合不合法: " + bad))
        return 2
    if path is None:
        if interactive:
            path = ask("目标文件路径 [默认 ~/backup/%s.zfs]: " % snap.split("@")[-1]).strip()
        if not path:
            path = os.path.expanduser("~/backup/%s.zfs" % snap.split("@")[-1])
    d = os.path.dirname(path) or "."
    if not os.path.isdir(d):
        print(c("red", "目录不存在: " + d))
        return 2
    # 🩸 修复（CWE-59）：原来用 `os.path.exists(path)` —— **悬空符号链接**
    #   会返回 False ⇒ 预览宣称"不存在（不会覆盖任何东西）"，而 `open(path,"wb")`
    #   会**写穿链接指向的目标**（实测发现写穿成功）。改用 `lexists`（不跟随链接）。
    if os.path.lexists(path):
        _kind = "符号链接" if os.path.islink(path) else "文件"
        print(c("red", "目标路径已存在（%s）: %s" % (_kind, path)))
        print(c("red", "  直接发送会**截断覆盖**它 —— 已中止。请换个路径，或先自行移走该文件。"))
        return 1
    send_cmd = _build_send_cmd(opts, snap, base)
    est, est_num, est_raw = _send_estimate(send_cmd)
    _path_disp = _one_line(path)
    # 🩸 修复：snap / base 同样要折叠换行（否则预览与日志都会被撕裂）
    facts = [("源快照", _one_line(snap)), ("目标文件", _path_disp),
             ("目标现状", "不存在（不会覆盖任何东西）"),
             ("模式", "增量(-i)" if base else "全量"),
             ("发送选项", " ".join(send_cmd[2:-1]) or "(默认：不加选项)")]
    if base:
        facts.append(("基准(-i)", _one_line(base)))
    if est is not None:
        facts.append(("估算流大小", "%s（ZFS 自报 %s）" % (human_bytes(est), est_num)))
    else:
        facts.append(("估算流大小", "读不到（%s）" % (est_raw or "")[:120]))
    notes = ["发送只读源快照、不改源；但会**写入**目标文件（占目标盘空间）。",
             "中途失败会删掉半成品文件（见实现），不会留下损坏的 zfs 流。"]
    if opts.get("raw"):
        notes.append("--raw：接收端 `keylocation` 会默认变成 `prompt` —— 异地恢复要提供密钥，或用 raw 原样保存。")
    if opts.get("replicate"):
        notes.append("--replicate：连快照与属性一起复制，流大小与耗时都远大于单快照。")
    if est is not None:
        try:
            free = shutil.disk_usage(d).free
        except OSError:
            free = None
        if free is not None:
            facts.append(("目标盘剩余", human_bytes(free)))
            if free < est:
                notes.append("⚠ 目标盘剩余(%s) **小于**估算流大小(%s) —— 很可能中途写满失败。"
                             % (human_bytes(free), human_bytes(est)))
                if FLAG_ASSUME_YES:
                    # 🩸 修复：非交互（`--yes`）下**硬拒绝** ——
                    #   脚本场景没人看得到这条提示，写满盘是实打实的失败。
                    print(c("red", "目标盘剩余空间不足（剩余 %s < 估算 %s），已拒绝执行。"
                          % (human_bytes(free), human_bytes(est))))
                    return 2
    if est is None and not FLAG_DRY:
        # 🩸 修复：`est is None`（估算文本解析失败）时，空间检查与
        #   `--yes` 硬拒绝**整体静默失效**（实测发现 `--yes` 照常执行）。
        #   非交互场景下"无法验证空间"不能被默默接受 ⇒ 硬拒绝。
        if FLAG_ASSUME_YES:
            print(c("red", "无法估算流大小（`zfs send -n -v` 没给出数字）—— "
                          "非交互(--yes)下不接受'无法验证目标空间'，已拒绝执行。"))
            return 2
        print(c("yellow", "⚠ 无法估算流大小 —— 本次**没有**做目标空间检查，请自行确认空间充足。"))

    if FLAG_DRY:
        return dry_preview("发送快照到文件（冷备）",
                           ["%s > %s" % (" ".join(send_cmd), _path_disp)],
                           facts=facts, notes=notes)
    print()
    print("即将执行: %s > %s" % (" ".join(send_cmd), _path_disp))
    # 🩸 修复：原来 facts/notes **只在 `--dry-run` 里打印** ⇒ 真跑路径上
    #   连"目标盘剩余 < 估算流大小"这种告警都看不到（实测发现 16.3T vs 54.5G 零告警）。
    for _k, _v in facts:
        print("  %s: %s" % (_k, _v))
    for _n in notes:
        print(c("yellow", "  ⚠ " + _n))
    if not confirm_single("确认发送?"):
        print("取消")
        return 1
    print("发送中...")
    rc, err = _run_to_file(send_cmd, path)
    if rc == 0:
        # 🩸 修复：原来判据是 `rc == 0 and getsize(path) > 0` ——
        #   合法的**空增量流**（rc=0、0 字节）会被当成失败：删掉文件 + 打印空白错误。
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size == 0:
            # 🩸 修复：早期版本曾把它当"合法空增量"，经真机实测反驳 ——
            #   相邻快照的真实增量估算是 21.4G，**0 字节不可能是正常结果**。
            #   而且原来的处理把 0 字节当成功、留下垃圾文件、还往生产日志写"已完成"。
            #   ⇒ 改为 fail-loud：报失败、删掉 0 字节文件、给排查方向。
            print(c("red", "发送返回成功但生成 **0 字节** —— 视为失败：%s" % _one_line(path)))
            print(c("dim", "  可能原因: 发送范围为空(-i 基准与源之间无变化) / 参数不匹配 / 流被丢弃。"))
            print(c("dim", "  可用只读方式复核: zfs send -n -v [-i 基准] <快照>"))
            try:
                os.remove(path)
            except OSError:
                pass
            log("send-file %s -> 0 字节，视为失败(已删)" % _one_line(snap))
            return 1
        print(c("green", "已生成: %s (%s)" % (_one_line(path), human_bytes(size))))
        log("send-file %s -> %s" % (_one_line(snap), _one_line(path)))
        return 0
    print(c("red", "发送失败: " + (err or "").strip()[:400]))
    try:
        os.remove(path)
    except OSError:
        pass
    return 1


def cmd_recv_file(path=None, dest=None):
    """从 .zfs 文件恢复到新数据集。参数为空则交互询问(菜单路径)。"""
    print("—— 从文件接收快照 ——")
    if path is None:
        path = ask("源 .zfs 文件路径: ").strip()
    if not path or not os.path.isfile(path):
        print(c("red", "文件不存在"))
        return 2
    if dest is None:
        dest = ask("目标数据集(全量需不存在; 增量需已有基础链): ").strip()
    if not dest:
        print(c("yellow", "已取消"))
        return 1
    dpool = dest.split("/", 1)[0]
    if not pool_exists(dpool):
        print(c("red", "目标 Pool 不存在: " + dpool))
        return 2
    if ds_exists(dest):
        print(c("yellow", "目标已存在: 接收可能作为增量继续; 若全量将报错"))
    print()
    _path_disp = _one_line(path)       # 🩸 修复：折叠换行，防日志行注入
    print("即将执行: zfs receive %s < %s" % (dest, _path_disp))
    if FLAG_DRY:
        try:
            sz = human_bytes(os.path.getsize(path))
        except OSError:
            sz = "(读不到)"
        return dry_preview(
            "从文件接收快照(会写入数据)",
            ["zfs receive %s < %s" % (dest, path)],
            facts=[("源文件", path), ("源文件大小", sz), ("目标数据集", dest),
                   ("目标是否已存在", "是(将按增量续接)" if ds_exists(dest) else "否(需全量)")],
            notes=["接收会**写入**目标池: 空间不足会中途失败, 建议先看目标池可用空间。",
                   "本工具有 `zfs receive -s` 断点续传, 但**不读 receive_resume_token** ⇒ 中断后没有恢复入口。",
                   "加密池来自文件接收需注意 `-x encryption` / `-o keylocation` 等选项(当前工具未暴露)。"])
    if not confirm_single("确认接收?"):
        print("取消")
        return 1
    print("接收中...")
    rc, err = _run_from_file(["zfs", "receive", dest], path)
    if rc == 0:
        print(c("green", "接收完成: " + dest))
        log("recv-file %s <- %s" % (dest, _one_line(path)))
        return 0
    print(c("red", "接收失败: " + (err or "").strip()[:500]))
    print("提示: 全量接收目标数据集不能已存在; 续传可先 zfs receive -s")
    return 1


def snap_sendrecv():
    """快照菜单 9: 文件级 send/recv 子菜单。"""
    while True:
        title("📦 文件冷备 SEND / RECEIVE", "快照 ↔ .zfs 文件; 用于异地/离线存档")
        print()
        print("1. 发送快照 → 文件 (.zfs)")
        print("2. 从文件恢复 → 数据集")
        print("0. 返回")
        print()
        o = ask("选择: ").strip()
        if o == "1":
            cmd_send_file()
        elif o == "2":
            cmd_recv_file()
        elif o == "0":
            return
        else:
            print("无效选择")


def cmd_snapshot():
    title("📸 ZFS 快照管理", "查看/创建/清理/diff/回滚/send·recv/多频策略/文件冷备")
    print()
    print("1. 查看快照         5. 快照对比 diff")
    print("2. 创建快照         6. 回滚 rollback")
    print("3. 按天数清理       7. send/recv 备份")
    print("4. 保留最近 N 份     8. 策略快照(hourly/daily/...)")
    print("                    9. 文件冷备 send/recv(.zfs)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        snap_list()
    elif opt == "2":
        snap_create()
    elif opt == "3":
        snap_prune()
    elif opt == "4":
        snap_keep()
    elif opt == "5":
        snap_diff()
    elif opt == "6":
        snap_rollback()
    elif opt == "7":
        snap_backup()
    elif opt == "8":
        snap_policy()
    elif opt == "9":
        snap_sendrecv()
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# Scrub / TRIM / Dedup / SMART
# ===========================================================================


def _scrub_progress_brief(pool, seconds=8):
    """就地显示 scrub 进度若干秒（同一行原地刷新），再给一行"继续看"的指引。

    🆕 交互优化 ⑥：scrub 动辄几小时，而原来"启动成功"之后**没有任何反馈**，
    用户只能再点一次菜单才知道在不在跑。这里只占一个短暂的窗口（默认 8 秒）显示**真实**
    进度，不劫持终端；想看全程仍可用菜单 3（实时监控）或 `zfs-tool.py progress`。
    """
    import time as _time
    if not sys.stdout.isatty():
        # 非交互（管道/cron）：只打一次当前状态，不做原地刷新
        scan = pool_scan_line(pool)
        if scan:
            print("  " + scan)
        print(c("yellow", "  继续查看: `zfs-tool.py progress`"))
        return
    end = _time.time() + max(2, int(seconds))
    scan = ""
    while _time.time() < end:
        scan = pool_scan_line(pool) or "无记录"
        sys.stdout.write("\r  " + scan[:120].ljust(100))
        sys.stdout.flush()
        _time.sleep(1.5)
    sys.stdout.write("\r" + " " * 110 + "\r")
    print("  " + (scan or "无记录"))
    print(c("yellow", "  继续查看: 菜单 3 实时监控, 或 `zfs-tool.py progress`"))


# ---------------------------------------------------------------------------
# 🆕 新增：scrub 精细控制（暂停 / 续扫 / 只扫坏块 / 日期区间 / 等待）
#   依据 `man zpool-scrub`（ZFS 2.4.1 实测）：
#     · -p 暂停：**进度定期落盘**，重启或导出再导入后仍保持暂停，直到恢复；
#     · 恢复 = 再发一次 `zpool scrub`（或 `-e`），从上次落盘处续；
#     · -e 只扫已知坏块：需 feature@head_errlog=active、需至少完整扫过一次、
#       **不能与常规 scrub/resilver 并行、不能在常规 scrub 暂停时跑**；
#     · -C 从 last_scrubbed_txg 续；-S/-E 是**按创建时间的部分扫描**（≠ 全池扫过）；
#     · -w 等待完成 —— 池2 全扫实测 04:31:26 ⇒ **必须带超时，绝不裸等**。
#   ⚠️ 判据不靠 zpool 的退出码猜测：状态改变类动作执行后**回读状态自证**
#     （同 `checkpoint` 的教训：无参数时 rc 也可能是 0）。
# ---------------------------------------------------------------------------

# 🩸 修复：新增 `start` / `stop` —— 菜单 opt1/opt4 原来**裸调**
#   `zpool scrub`，绕过了 `--dry-run` 白名单（干跑下真发命令）。现在菜单也走这里，
#   全工具只有 `scrub_action()` 一个 scrub 执行出口。
SCRUB_MODES = ("start", "stop", "pause", "resume", "resume-e", "continue",
               "errors", "range", "wait", "status")


def scrub_stats(pool):
    """解析 `zpool status -j <pool>` 的 scan_stats（真机实测结构见补丁头）。
    任何解析失败返回 None ⇒ 调用方回退文本判据 / 保守处理，**绝不猜成"没在跑"**。"""
    p = run_noblock(["zpool", "status", "-j", pool], timeout=30)
    if p is None or p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout or "{}")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    pools = data.get("pools")
    entry = None
    if isinstance(pools, dict):
        entry = pools.get(pool)
        if not isinstance(entry, dict):        # 兜底：按 GUID 作键的版本
            for v in pools.values():
                if isinstance(v, dict) and v.get("name") == pool:
                    entry = v
                    break
    if not isinstance(entry, dict):
        entry = data                        # 兜底：某些版本顶层直接是池对象
    stats = entry.get("scan_stats") if isinstance(entry, dict) else None
    return stats if isinstance(stats, dict) else None


def scrub_pool_props(pool):
    """取该池 scrub 相关属性。**一次只查一个池** —— 真机实测多池同时查会丢掉池名列，
    无法归属（`zpool get -o property,value` 的 name 列被 -o 去掉了）。"""
    vals = {}
    p = run_noblock(["zpool", "get", "-H", "-p", "-o", "property,value",
                     "last_scrubbed_txg,feature@head_errlog", pool], timeout=30)
    if p is not None and p.returncode == 0:
        for ln in (p.stdout or "").splitlines():
            f = ln.split("\t")
            if len(f) >= 2:
                vals[f[0]] = f[1]
    return vals


def scrub_state(pool):
    """返回 (state, paused)。state ∈ SCANNING/PAUSED/RESILVERING/FINISHED/UNKNOWN。
    JSON 优先、文本兜底；两者都读不到 ⇒ UNKNOWN（调用方据此 fail-closed）。"""
    st = scrub_stats(pool)
    if st is not None:
        paused = (st.get("scrub_pause") or "-").strip() not in ("", "-")
        fn = (st.get("function") or "").strip().upper()
        state = (st.get("state") or "").strip().upper()
        if paused or state == "PAUSED":
            return ("PAUSED", True)
        if state in ("SCANNING", "IN_PROGRESS"):
            return ("RESILVERING" if fn == "RESILVER" else "SCANNING", False)
        if state in ("FINISHED", "CANCELED", "CANCELLED", "NONE"):
            return ("FINISHED", False)
        # 🩸 修复：原来 `return (state or "UNKNOWN", False)` —— 枚举外的
        #   值（实测用 `SCRUBBING` 复现）会被调用方当作"已知状态"从而**绕过 fail-closed**。
        #   状态判据只认白名单，其余一律 UNKNOWN。
        return ("UNKNOWN", False)
    line = pool_scan_line(pool)
    low = (line or "").lower()
    if not line:
        return ("UNKNOWN", False)
    if "paused" in low:
        return ("PAUSED", True)
    if "in progress" in low:
        return ("RESILVERING" if "resilver" in low else "SCANNING", False)
    if "scrub" in low or "resilver" in low:
        return ("FINISHED", False)
    return ("UNKNOWN", False)


def scrub_state_text(st):
    """把 scan_stats 折成一行人话摘要。"""
    if not st:
        return "无记录（或该版本 zpool 不支持 -j）"
    parts = ["%s %s" % ((st.get("function") or "?").strip(), (st.get("state") or "?").strip())]
    for key, label in (("start_time", "开始"), ("end_time", "结束"),
                       ("to_examine", "待扫"), ("examined", "已扫"),
                       ("errors", "错误")):
        v = (st.get(key) or "").strip()
        if v and v != "-":
            parts.append("%s %s" % (label, v))
    if (st.get("scrub_pause") or "-").strip() not in ("", "-"):
        parts.append("**暂停中**(累计 %s 秒)" % ((st.get("scrub_spent_paused") or "?").strip()))
    return " / ".join(parts)


def cmd_scrub_status(json_mode=False, only=None):
    """只读：每池 scrub 进度 / 是否暂停 / 暂停累计秒数 / last_scrubbed_txg。

    🩸 修复：加 `only` —— `scrub status <池名>` 原来被静默忽略
    （列全部池、rc=0、零提示），现在会校验池存在并只报它。
    """
    pools = [only] if only else _target_pools()
    if not pools:
        print("无 Pool")
        return 1
    rows = []
    for p in pools:
        st = scrub_stats(p) or {}
        props = scrub_pool_props(p)
        rows.append({
            "pool": p,
            "function": (st.get("function") or "").strip(),
            # 🩸 修复：`zpool status -j` 不可用时这里会是**空串**，
            #   与真正读到的状态无法区分 ⇒ 归一成 "UNKNOWN"（调用方按未知处理）。
            "state": (st.get("state") or "").strip() or "UNKNOWN",
            "start_time": (st.get("start_time") or "").strip(),
            "end_time": (st.get("end_time") or "").strip(),
            "examined": (st.get("examined") or "").strip(),
            "to_examine": (st.get("to_examine") or "").strip(),
            "errors": (st.get("errors") or "").strip(),
            "paused": (st.get("scrub_pause") or "-").strip() not in ("", "-"),
            "spent_paused": (st.get("scrub_spent_paused") or "").strip(),
            "last_scrubbed_txg": props.get("last_scrubbed_txg", ""),
            "head_errlog": props.get("feature@head_errlog", ""),
            "scan_line": pool_scan_line(p),
        })
    if json_mode:
        print(json.dumps({"pools": rows}, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        print()
        print(c("white", "▶ Pool: %s" % r["pool"]))
        print("    %s" % (r["scan_line"] or "无 scan 记录"))
        print("    暂停中: %s      已暂停累计: %s 秒"
              % ("是" if r["paused"] else "否", r["spent_paused"] or "-"))
        print("    last_scrubbed_txg: %s      feature@head_errlog: %s"
              % (r["last_scrubbed_txg"] or "?", r["head_errlog"] or "?"))
    print()
    return 0


_SCRUB_TIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T_ ](\d{1,2}):(\d{2}))?$")


def _norm_scrub_time(s):
    """规范化成 `YYYY-MM-DD HH:MM`（本地时区；时分可省 ⇒ 补 00:00）。
    非法输入返回 None ⇒ **本地报错，绝不把 `2026-13-99` 丢给 zpool**。"""
    m = _SCRUB_TIME_RE.match((s or "").strip())
    if not m:
        return None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)) if m.group(4) else 0,
                      int(m.group(5)) if m.group(5) else 0)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d %H:%M")


def _scrub_readback_mismatch(mode, before, after, after_state, paused):
    """执行后的「回读自证」判据：返回 True 表示**与预期不符**（动作可能未生效）。

    🩸 修复（中高）：上面那条判据对 `start/continue/errors/range` **恒真**
    （只查 `after_state != "UNKNOWN"`），`stop` 又只查 `"SCANNING"`
    ⇒ 实测用「写操作 rc=0 但什么都不做」的替身让 **5 个模式全部**打印
    「已执行」+ rc=0。现在：
      · 启动类（start/continue/errors/range）改判**扫描起点是否刷新**
        （`scan_stats.start_time` 变化，或状态进入 SCANNING/RESILVERING/PAUSED）
        —— 小池秒扫完也能判出来；
      · `stop` 同时认 `RESILVERING` / `PAUSED` 为"没停下"。
    """
    if mode == "pause":
        return not paused
    if mode in ("resume", "resume-e"):
        return paused
    if mode == "stop":
        return after_state in ("SCANNING", "RESILVERING", "PAUSED")
    # 启动类
    if after_state == "UNKNOWN":
        return True
    if after_state in ("SCANNING", "RESILVERING", "PAUSED"):
        return False
    b = ((before or {}).get("start_time") or "").strip()
    a = ((after or {}).get("start_time") or "").strip()
    return not (a and a != b)


def scrub_action(pool, mode, t_from=None, t_to=None, timeout=None):
    """执行一个 scrub 动作（FLAG_DRY 时只预览）。返回退出码。"""
    if mode == "status":
        # 🩸 修复：原来这里没把 `pool` 传下去 ⇒ 菜单 opt2 选了 A 池
        #   却列出**全部**池（上面只修了 CLI 路径）。
        return cmd_scrub_status(FLAG_JSON, only=pool)
    if not pool_exists(pool):
        print(c("red", "Pool 不存在: " + pool))
        return 2
    props = scrub_pool_props(pool)
    txg = (props.get("last_scrubbed_txg") or "").strip()
    errlog = (props.get("feature@head_errlog") or "").strip()
    state, paused = scrub_state(pool)

    # ---- 本地前置校验：宁可本地明确拒绝，也不把 zpool 的报错原样丢出去 ----
    # 🩸 修复：只有**依赖状态判据**的子命令才因"状态读不到"被拒；
    #   `range`（按日期区间扫）与 `start` / `stop` 不依赖它 —— 从未扫过的池也应该能扫。
    if state == "UNKNOWN" and mode in ("pause", "resume", "resume-e", "continue",
                                       "errors", "wait"):
        print(c("red", "读不到该池的 scrub 状态（无 scan 行且 zpool status -j 不可用）—— 已拒绝执行。"))
        print(c("dim", "  先用 `zfs-tool.py scrub status` 或 `zpool status %s` 确认状态。" % pool))
        return 2
    if mode == "pause":
        if paused:
            print(c("yellow", "该池的 scrub **已经**处于暂停状态 —— 无需再次暂停。"))
            return 1
        if state != "SCANNING":
            print(c("red", "当前没有正在进行的 scrub（状态: %s）—— 没有可暂停的对象。" % state))
            print(c("dim", "  启动扫描: zfs-tool.py scrub-run %s（或菜单 1）" % pool))
            return 1
    elif mode in ("resume", "resume-e"):
        if not paused:
            print(c("red", "该池当前**没有**被暂停的 scrub（状态: %s）。" % state))
            print(c("dim", "  `scrub resume` 只恢复被暂停的扫描；要新起一次扫描请用 scrub-run。"))
            return 1
    elif mode == "continue":
        if txg in ("", "-", "0"):      # 🩸 修复："0" 也是"没有有效 txg"
            print(c("red", "该池没有可续扫的 txg（last_scrubbed_txg 为空/为 0）—— 无法 -C 续扫。"))
            return 1
        if state in ("SCANNING", "RESILVERING") or paused:
            print(c("red", "当前状态为 %s%s —— ZFS 不允许同时进行，已拒绝。"
                  % (state, "（暂停中）" if paused else "")))
            return 1
    elif mode == "errors":
        if errlog != "active":
            print(c("red", "feature@head_errlog = %s（非 active）—— 该池不支持 -e 只扫已知坏块。"
                  % (errlog or "?")))
            return 1
        if txg in ("", "-", "0"):      # 🩸 修复：同上
            print(c("red", "该池还没有完整扫过一次（last_scrubbed_txg 为空/为 0）—— 不能只扫已知坏块。"))
            return 1
        if state in ("SCANNING", "RESILVERING") or paused:
            print(c("red", "当前状态为 %s%s —— man zpool-scrub 明确禁止此时 -e，已拒绝。"
                  % (state, "（暂停中）" if paused else "")))
            return 1
    elif mode == "range":
        nf = _norm_scrub_time(t_from) if t_from else None
        nt = _norm_scrub_time(t_to) if t_to else None
        if t_from and nf is None:
            print(c("red", "起始时间无法解析: %s（应为 YYYY-MM-DD 或 \"YYYY-MM-DD HH:MM\"）" % t_from))
            return 2
        if t_to and nt is None:
            print(c("red", "结束时间无法解析: %s（同上格式）" % t_to))
            return 2
        if nf and nt and nt <= nf:
            print(c("red", "结束时间必须晚于起始时间: %s → %s" % (nf, nt)))
            return 2
        if nf is None and nt is None:
            print(c("red", "range 至少要给一个时间（起始 [-S] 或结束 [-E]）。"))
            return 2
        t_from, t_to = nf, nt
    elif mode == "wait":
        if state not in ("SCANNING", "RESILVERING", "PAUSED"):
            print("该池当前没有进行中的扫描（状态: %s）—— 无需等待。" % state)
            return 0
        if paused:
            print(c("yellow", "该池的 scrub 处于**暂停**状态 —— `-w` 会一直等到你恢复它为止。"))
            print(c("yellow", "  先恢复: zfs-tool.py scrub resume %s" % pool))
            return 1

    # ---- 组装底层命令 ----
    if mode == "start":
        cmd, action = ["zpool", "scrub", pool], "启动 Scrub"
    elif mode == "stop":
        cmd, action = ["zpool", "scrub", "-s", pool], "停止 Scrub"
    elif mode == "pause":
        cmd, action = ["zpool", "scrub", "-p", pool], "暂停 Scrub"
    elif mode == "resume":
        cmd, action = ["zpool", "scrub", pool], "恢复被暂停的 Scrub"
    elif mode == "resume-e":
        cmd, action = ["zpool", "scrub", "-e", pool], "恢复被暂停的 Scrub(-e)"
    elif mode == "continue":
        cmd, action = ["zpool", "scrub", "-C", pool], "从 last_scrubbed_txg 续扫(-C)"
    elif mode == "errors":
        cmd, action = ["zpool", "scrub", "-e", pool], "只扫已知坏块(-e)"
    elif mode == "range":
        cmd = ["zpool", "scrub"]
        if t_from:
            cmd += ["-S", t_from]
        if t_to:
            cmd += ["-E", t_to]
        cmd.append(pool)
        action = "按日期区间扫描(部分扫描)"
    else:
        cmd, action = ["zpool", "scrub", "-w", pool], "等待 Scrub 完成(-w)"

    facts = [("池", pool),
             ("当前 scan 状态", scrub_state_text(scrub_stats(pool))),
             ("暂停中", ("是（累计 %s 秒）" % (props.get("scrub_spent_paused") or "?"))
                        if paused else "否"),
             ("last_scrubbed_txg", txg or "?"),
             ("feature@head_errlog", errlog or "?")]
    if mode == "range":
        facts.append(("时间区间", "%s → %s" % (t_from or "(最早)", t_to or "(最晚)")))
    notes = []
    if mode == "pause":
        notes = ["暂停状态会**定期落盘**：即使系统重启或池导出再导入，scrub 仍保持暂停，直到恢复。",
                 "恢复方式: `zfs-tool.py scrub resume %s`（等价 `zpool scrub %s`）。" % (pool, pool),
                 "⚠ 忘了恢复 = 池长期不扫 —— 别把「暂停」当「停止」用。"]
    elif mode in ("resume", "resume-e"):
        notes = ["恢复后从上次落盘的位置继续，不会从头重扫。"]
    elif mode == "continue":
        notes = ["只覆盖上次中断点之后的块；想全池覆盖仍需一次常规 scrub。"]
    elif mode == "errors":
        notes = ["只扫 `zpool status -v` 报告的已知坏块，很快，但**不能替代**一次完整 scrub。"]
    elif mode == "range":
        notes = ["-S/-E 只覆盖该时间区间**创建**的块 ⇒ 结果**不能**当作「池已全扫」。",
                 "完成后建议补一次常规 scrub（`zfs-tool.py scrub-run %s`）。" % pool,
                 "时间按本机本地时区解释，已规范化为 `YYYY-MM-DD HH:MM`。"]
    elif mode == "wait":
        notes = ["等待期间不占交互；超时（默认 %s 秒）后会打印进度并**正常退出**，不会挂死。"
                 % (timeout or 1800)]

    if FLAG_DRY:
        return dry_preview(action, [" ".join(cmd)], facts=facts, notes=notes)

    if mode == "wait":
        tmo = int(timeout or 1800)
        print("等待 Scrub 完成（最多 %d 秒；另开一窗可用 `zfs-tool.py progress` 看进度）..." % tmo)
        # 🩸 修复：换成绝不 wait 的版本（run(timeout=) 对 D 状态会挂死）。
        p = run_noblock(cmd, timeout=tmo)
        if p is None:
            print(c("red", "无法执行 zpool（未找到命令）"))
            return 1
        if p.returncode == 124:
            print(c("yellow", "等待超时（%d 秒）—— scrub 仍在后台继续，没有被中断。" % tmo))
            print("  " + (pool_scan_line(pool) or "无记录"))
            return 1
        if p.returncode == 0:
            print(c("green", "Scrub 已完成。"))
            log("scrub wait done " + pool)
            print("  " + (pool_scan_line(pool) or "无记录"))
            return 0
        print(c("red", "等待失败: " + ((p.stderr or "").strip()[:300] or "未知原因")))
        return 1

    if not confirm_single("确认执行 `%s`?" % " ".join(cmd)):
        print("取消")
        return 1
    # 🩸 修复：**绝不**用 `run(timeout=)` —— POSIX 超时分支是
    #   `kill()` 再 `wait()`，而 D 状态进程 SIGKILL 只 pending ⇒ wait() 会连工具
    #   一起挂死。`run_noblock` 超时后直接返回 124，绝不 wait。
    st_before = scrub_stats(pool)      # 🩸 修复：为回读自证留"执行前"快照
    p = run_noblock(cmd, timeout=300)
    if p is None:
        print(c("red", "无法执行 zpool（未找到命令）"))
        return 1
    if p.returncode == 124:
        print(c("red", "命令超时（300 秒）—— 底层 I/O 可能已卡死，**未等待完成**。"))
        print(c("yellow", "  请自查残留进程: ps -o pid,stat,cmd | grep zpool"))
        print(c("yellow", "  池若处于 D 状态，用户态无法终止子进程，请勿反复重试。"))
        log("scrub %s %s TIMEOUT(未等待)" % (mode, pool))
        return 124
    if p.returncode == 0:
        print(c("green", "已执行: %s" % " ".join(cmd)))
        log("scrub %s %s" % (mode, pool))
        # 🩸 修复：回读自证**必须参与结论** —— 原来 `rc=0` 就报成功，
        #   即使动作完全没发生（实测用"假成功"替身复现了"已执行"假成功）。
        st_after = scrub_stats(pool)
        st2, paused2 = scrub_state(pool)
        print("  当前状态: %s%s" % (st2, "（暂停中）" if paused2 else ""))
        if _scrub_readback_mismatch(mode, st_before, st_after, st2, paused2):
            print(c("yellow", "  ⚠ 回读自证未通过（%s 之后状态/扫描起点没有按预期变化）"
                              " —— 动作可能未生效。" % mode))
            print(c("dim", "    执行前: %s" % scrub_state_text(st_before)))
            print(c("dim", "    执行后: %s" % scrub_state_text(st_after)))
            log("scrub %s %s 回读不符(实际 %s)" % (mode, pool, st2))
            return 1
        return 0
    print(c("red", "执行失败(rc=%d): %s" % (p.returncode, (p.stderr or "").strip()[:300])))
    return 1


def _scrub_cli(extra):
    """CLI: scrub <子命令> [池名] [时间...] [--timeout N] [--dry-run]"""
    if not extra:
        # 🩸 修复：原来 `cmd_scrub() or 0` 会把菜单路径的真实失败码变成 0。
        _r = cmd_scrub()
        return _r if isinstance(_r, int) else 0
    mode = extra[0]
    if mode not in SCRUB_MODES:
        print(c("red", "未知的 scrub 子命令: %s" % mode))
        print("可用: %s" % " / ".join(SCRUB_MODES))
        return 2
    if mode == "status":
        # 🩸 修复：原来 `status` 在解析 rest **之前**就 return ⇒
        #   `scrub status <池名>` 被静默忽略（列出全部池、rc=0、零提示）。
        pos = [a for a in extra[1:] if not a.startswith("-")]
        if pos:
            if not pool_exists(pos[0]):
                print(c("red", "Pool 不存在: " + pos[0]))
                return 2
            if len(pos) > 1:
                print(c("yellow", "多余的位置参数被忽略: %s" % " ".join(pos[1:])))
            return cmd_scrub_status(FLAG_JSON, only=pos[0])
        return cmd_scrub_status(FLAG_JSON)
    pool = TARGET_POOL or ""
    t_from = t_to = None
    timeout = None
    rest = extra[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-S", "--from") and i + 1 < len(rest):
            t_from, i = rest[i + 1], i + 2
            continue
        if a in ("-E", "--to") and i + 1 < len(rest):
            t_to, i = rest[i + 1], i + 2
            continue
        if a == "--timeout" and i + 1 < len(rest):
            timeout, i = rest[i + 1], i + 2
            continue
        # 🩸 修复：补上 `--timeout=7` / `-S=…` / `-E=…` 等**等号形式** ——
        #   原来它们落到"忽略无法识别的参数"分支，于是 `--timeout=0` 不报错不生效、
        #   `--timeout=7` 被静默丢弃后回落 1800 秒。
        if a.startswith("--timeout="):
            timeout, i = a.split("=", 1)[1], i + 1
            continue
        if a.startswith("-S="):
            t_from, i = a.split("=", 1)[1], i + 1
            continue
        if a.startswith("-E="):
            t_to, i = a.split("=", 1)[1], i + 1
            continue
        if a.startswith("--from="):
            t_from, i = a.split("=", 1)[1], i + 1
            continue
        if a.startswith("--to="):
            t_to, i = a.split("=", 1)[1], i + 1
            continue
        if a.startswith("-"):
            # 🩸 修复：未识别的选项**一律报错**（原来只是"忽略"）——
            #   静默丢弃一个选项 = 让人以为它生效了（fail-closed）。
            print(c("red", "无法识别的参数: %s" % a))
            print(c("dim", "  scrub 只认: -S/--from <起> -E/--to <止> --timeout <秒> 与位置参数"))
            return 2
        elif not pool:
            pool = a
        elif mode == "range" and t_from is None:
            t_from = a
        elif mode == "range" and t_to is None:
            t_to = a
        else:
            print(c("yellow", "多余的位置参数被忽略: %s" % a))
        i += 1
    if not pool:
        print(c("red", "缺少池名。用法: zfs-tool.py scrub %s <池名> [...]" % mode))
        return 2
    if timeout is not None:
        if not is_num(str(timeout)):
            print(c("red", "--timeout 需要一个整数秒数: %s" % timeout))
            return 2
        timeout = int(timeout)
        # 🩸 修复：`--timeout 0` 原来被 `if timeout:` 静默吞掉（回落 1800）；
        #   现在显式校验范围 —— 既不许"0 秒假等待"，也不许"事实永久等待"。
        if timeout < 1 or timeout > 86400:
            print(c("red", "--timeout 必须在 1~86400 秒之间（给了 %d）" % timeout))
            return 2
    return scrub_action(pool, mode, t_from=t_from, t_to=t_to, timeout=timeout)


def _rewrite_cli_required():
    """`CLI_MAP["rewrite"]` 的 fail-closed 兜底：缺参数就报用法 + rc=2。

    🩸 修复：`main()` 的 `elif cmd == "rewrite"` 专属分支优先，本函数
    只在分支被删/改序时才会被 `fn()` 调用 —— 那时必须**明确报错**，绝不能静默进交互向导。
    """
    print(c("red", "rewrite 需要参数: rewrite <路径> [-r] [-P] [-v] [--dry-run]"))
    return 2


def cmd_scrub():
    # 🩸 修复：菜单路径原来**丢弃** `scrub_action()` 的返回值
    #   ⇒ 屏幕上打印「执行失败(rc=99)」而进程退出码仍是 0（脚本/定时任务判不出来）。
    rc = 0
    title("🧹 ZFS Scrub 清理", "启动 / 查看 / 暂停 / 续扫 / 停止 Scrub")
    print()
    print("1. 开始 Scrub\n2. 查看状态\n3. 实时监控\n4. 停止 Scrub")
    print("5. 暂停 (-p，进度落盘)\n6. 从上次位置续扫 (-C)\n7. 只扫已知坏块 (-e)")
    print("8. 按日期区间扫 (-S/-E)\n0. 返回")
    print()
    # 🆕 交互优化 ④: 标出等价命令, 让人能从菜单直达
    cli_hint([("1", "zfs-tool.py scrub-run <pool>"),
              ("2", "zfs-tool.py scrub status [--json]"),
              ("5", "zfs-tool.py scrub pause <pool>"),
              ("6", "zfs-tool.py scrub continue <pool>"),
              ("7", "zfs-tool.py scrub errors <pool>"),
              ("8", "zfs-tool.py scrub range <pool> <起始日期> <结束日期>")])
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        pool = ask_pool()
        if pool:
            # 🩸 修复（高危）：这里原来**裸调** `zpool scrub` ——
            #   菜单路径绕过了 `--dry-run` 白名单，用 fake zpool 在干跑下实测
            #   真发出了 `zpool scrub <pool>`。现在统一走 `scrub_action()`，
            #   全工具只剩这一个 scrub 执行出口（dry-run 下只会预览）。
            rc = scrub_action(pool, "start")
            if rc == 0 and not FLAG_DRY:
                # 🆕 交互优化 ⑥: 启动后不再"打完一行就结束", 就地显示真实进度
                _scrub_progress_brief(pool)
            pause()
    elif opt == "2":
        pool = ask_pool()
        if pool:
            rc = scrub_action(pool, "status")
            pause()
    elif opt == "3":
        # 🩸 修复：实时监控是 `while True` 刷屏 + `sleep(3)` —— 非交互
        #   （管道 / cron）下会**死循环**，实测只能被外部 `timeout` 强杀（rc=124）。
        if not sys.stdin.isatty():
            print(c("red", "实时监控需要交互终端；非交互请用 `zfs-tool.py progress`（一次输出）。"))
            return 2
        pool = ask_pool()
        if pool:
            print("Ctrl+C 返回菜单")

            def _sig(_s, _f):
                raise KeyboardInterrupt

            old = signal.signal(signal.SIGINT, _sig)
            try:
                while True:
                    _cls()
                    print(c("white", "ZFS Scrub Monitor %s" % datetime.now().strftime("%F %T")))
                    scan = pool_scan_line(pool)
                    print("  " + (scan or "无记录"))
                    __import__("time").sleep(3)
            except KeyboardInterrupt:
                pass
            finally:
                signal.signal(signal.SIGINT, old)
    elif opt == "4":
        pool = ask_pool()
        if pool:
            rc = scrub_action(pool, "stop")  # 🩸 修复：同上，统一出口
            pause()
    elif opt in ("5", "6", "7", "8"):
        pool = ask_pool()
        if pool:
            mode = {"5": "pause", "6": "continue", "7": "errors", "8": "range"}[opt]
            tf = tt = None
            if mode == "range":
                tf = ask("起始时间 [YYYY-MM-DD，回车=不限]: ").strip() or None
                tt = ask("结束时间 [YYYY-MM-DD，回车=不限]: ").strip() or None
            rc = scrub_action(pool, mode, t_from=tf, t_to=tt)
            pause()
    elif opt == "0":
        return rc
    else:
        print("无效选择")
        pause()
    return rc


def cmd_trim():
    title("✂ ZFS TRIM", "手动启动 / 查看进度 / 查询 autotrim, SSD 空间回收")
    print()
    print("1. 开始 TRIM\n2. 查看状态\n3. 查看 autotrim\n0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        pool = ask_pool()
        if pool:
            p = run(["zpool", "trim", pool])
            if p is not None and p.returncode == 0:
                print(c("green", "TRIM 已启动: " + pool))
                log("trim start " + pool)
            else:
                print(c("red", "TRIM 启动失败, 可能不支持"))
            pause()
    elif opt == "2":
        pool = ask_pool()
        if pool:
            text = out(["zpool", "status", pool])
            lines = []
            hit = False
            for ln in text.splitlines():
                if re.search(r"trim", ln, re.I):
                    hit = True
                if hit:
                    lines.append(ln.strip())
                    if len(lines) >= 6:
                        break
            print("\n".join(lines) if lines else "当前没有 TRIM 信息")
            pause()
    elif opt == "3":
        pool = ask_pool()
        if pool:
            print(out(["zpool", "get", "autotrim", pool]), end="")
            pause()
    elif opt == "0":
        return
    else:
        print("无效选择")
        pause()


def cmd_dedup():
    title("🗜 ZFS 离线去重 (zfs-dedup)", "调用 zfs-dedup 项目做离线去重, 需 yes 确认")
    if not have("zfs-dedup"):
        print(c("yellow", "未安装 zfs-dedup\n\n项目: https://github.com/Mic92/zfs-dedup"))
        pause()
        return
    print()
    print("输入 zfs-dedup 参数")
    print("例如: -n /mnt/tank/data")
    print()
    print(c("yellow", "⚠ 注意: 不带 -n 会实际执行修改; 建议先 -n 测试"))
    print()
    args = ask("参数: ").split()
    if not args:
        print(c("yellow", "未输入参数, 取消执行"))
        pause()
        return
    print()
    print("即将执行: zfs-dedup " + " ".join(args))
    print(c("red", "⚠ 实际执行可能修改数据"))
    print(c("yellow", "提示: 大范围扫描可能耗时数小时, 期间本界面不会刷新;"))
    print(c("yellow", "      建议改用 nohup 后台执行并落日志, 再回来查看结果"))
    if not ask_yes("确认执行? (yes): "):
        print("取消")
        pause()
        return
    log("dedup start " + " ".join(args))
    p = run(["zfs-dedup"] + args)
    if p is None:
        print(c("red", "无法启动 zfs-dedup(命令缺失或不可执行)"))
        log("dedup failed: cannot exec")
    else:
        so = (p.stdout or "").rstrip()
        se = (p.stderr or "").rstrip()
        if so:
            print(so)
        if se:
            print(c("yellow", se))
        if p.returncode == 0:
            print(c("green", "zfs-dedup 正常结束"))
            log("dedup finish rc=0")
        else:
            print(c("red", "zfs-dedup 失败(exit %s)" % p.returncode))
            log("dedup failed rc=%s" % p.returncode)
    pause()


def pick_disk():
    """字母/数字/设备路径选择磁盘, 返回 (dev, args) 或 None。"""
    devs = smart_devices()
    if not devs:
        print(c("yellow", "未发现可检测磁盘"))
        return None
    if len(devs) == 1:
        print("仅一个磁盘, 自动选择: " + devs[0][0])
        return devs[0]
    names = [d for d, _ in devs]
    ok, chosen = pick_from_list("磁盘", names)
    if not ok:
        return None
    for d, a in devs:
        if d == chosen:
            return (d, a)
    # 用户直输的设备路径
    if os.path.exists(chosen):
        return (chosen, [])
    print(c("red", "设备不存在: " + chosen))
    return None


def smart_overview():
    devs = smart_devices()
    if not devs:
        print(c("yellow", "未发现可检测磁盘"))
        return
    for dev, args in devs:
        print()
        print(LINE_SHORT)
        print(dev)
        p = run(["smartctl", "-A", dev] + list(args))
        if p and p.returncode == 0:
            for ln in p.stdout.splitlines():
                if re.search(r"Temperature|Airflow|Media_Wear|Percentage|\b194\b|\b190\b", ln, re.I):
                    print(ln)


def smart_health():
    pick = pick_disk()
    if not pick:
        return
    dev, args = pick
    print()
    p = run(["smartctl", "-H", dev] + list(args))
    if p and p.returncode == 0:
        for ln in p.stdout.splitlines():
            if re.search(r"SMART overall|result|Health|status", ln, re.I):
                print(ln)
    else:
        print(c("yellow", "无法获取健康状态"))


def smart_run_test():
    pick = pick_disk()
    if not pick:
        return
    dev, args = pick
    t = ask("自检类型 short/long: ").strip().lower()
    if t not in ("short", "long"):
        print(c("red", "请输入 short 或 long"))
        return
    print()
    print(c("yellow", "短检通常数分钟, 长检可能数小时"))
    if not ask_yes("确认对 %s 启动 %s 自检? (yes): " % (dev, t)):
        print("取消")
        return
    p = run(["smartctl", "-t", t, dev] + list(args))
    if p is not None and p.returncode == 0:
        print(c("green", "已启动 %s 自检: %s" % (t, dev)))
        log("smart test %s %s" % (t, dev))
    else:
        print(c("red", "启动失败"))


def smart_selftest():
    pick = pick_disk()
    if not pick:
        return
    dev, args = pick
    print()
    print("自检历史:")
    p = run(["smartctl", "-l", "selftest", dev] + list(args))
    if p and p.returncode == 0:
        print(p.stdout, end="")
    else:
        print(c("yellow", "无自检记录或不可读"))


def cmd_smart():
    title("💽 SMART 监测", "温度总览 / 整体健康 / 自检 / 属性趋势预警")
    if not have("smartctl"):
        print("未找到 smartctl")
        pause()
        return
    print()
    print("1. 温度/属性总览")
    print("2. 整体健康 (SMART -H)")
    print("3. 运行自检 (short/long)")
    print("4. 自检历史")
    print("5. 属性趋势预警 (重分配/挂起扇区)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        smart_overview()
    elif opt == "2":
        smart_health()
    elif opt == "3":
        smart_run_test()
    elif opt == "4":
        smart_selftest()
    elif opt == "5":
        smart_trend_collect(verbose=True)
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# Dataset Analyzer
# ===========================================================================

PROPS_LIST = ["compression", "dedup", "recordsize", "sync", "atime", "checksum",
              "readonly", "encryption", "quota", "refquota", "mountpoint", "copies",
              "snapdir", "primarycache", "secondarycache", "keylocation",
              "keystatus", "encryptionroot"]


def cmd_dataset():
    title("📂 ZFS 数据集分析器", "查看数据集属性 / 空间 / 子数据集, 并给出性能建议")
    ds = ask_dataset()
    if not ds:
        pause()
        return
    print()
    print("Dataset: " + ds)
    print()
    print(LINE_SHORT)
    print()
    for prop in PROPS_LIST:
        print("%-16s %s" % (prop, ds_prop(ds, prop)))
    print()
    print("空间使用:")
    print(out(["zfs", "list", ds, "-o", "name,used,avail,refer"]), end="")
    print()
    print("子 Dataset:")
    print(out(["zfs", "list", "-r", "-o", "name,used,compressratio", ds]), end="")
    print()
    print("性能建议:")
    comp = ds_prop(ds, "compression")
    dedup = ds_prop(ds, "dedup")
    rec = ds_prop(ds, "recordsize")
    if comp == "off":
        print("- Compression 当前关闭")
        print("  普通文件建议: lz4")
    if dedup == "on":
        print("- Dedup 已开启")
        print("- 注意内存消耗")
    if rec in ("1M", "1048576"):
        print("- 大文件优化模式")
    elif rec == "128K":
        print("- 默认模式")
    elif rec:
        print("- Recordsize 特殊设置")
    print()
    pause()


# ===========================================================================
# Pool Manager
# ===========================================================================

_STATE_COLOR = {
    "ONLINE": "green", "DEGRADED": "yellow",
    "FAULTED": "red", "OFFLINE": "red", "UNAVAIL": "red", "REMOVED": "red",
}


def _colorize_line(line):
    if not COLOR:
        return line
    outl = line
    for st, col in _STATE_COLOR.items():
        outl = outl.replace(st, c(col, st))
    return outl


def topo_view():
    pools = get_pools()
    if not pools:
        print("无 Pool")
        return
    for p in pools:
        print()
        print(c("white", "▶ Pool: %s" % p))
        for ln in out(["zpool", "status", p]).splitlines():
            print(_colorize_line(ln))


def pool_export():
    pool = ask_pool()
    if not pool:
        return
    print()
    print(c("red", "⚠ 导出会卸载数据集并让 Pool 从系统消失(数据不动)"))
    print(c("yellow", "提示: 若数据集正被使用会失败, 请先停相关服务"))
    if not confirm_destructive("zpool export " + pool):
        print("已取消")
        return
    p = run(["zpool", "export", pool])
    if p is not None and p.returncode == 0:
        print(c("green", "已导出: " + pool))
        log("pool export " + pool)
    else:
        print(c("red", "导出失败: 可能仍有数据集被占用, 检查挂载/服务"))


def pool_import():
    print()
    print("当前可导入的池:")
    p = run(["zpool", "import"])
    # 修复: 池清单在 stdout(源 bash 脚本:871 用 `2>&1`,
    # 并注释"返回码始终为 1", 故不能靠 rc 判断成功与否)。
    # 原实现只取 p.stderr → 恒为空 → 恒报"没有发现可导入的池"。
    blob = ((p.stdout or "") + (p.stderr or "")) if p else ""
    if "pool:" not in blob:
        print("  没有发现可导入的池")
        return
    names = re.findall(r"^\s*pool:\s*(\S+)", blob, re.M)
    if not names:
        print("  没有发现可导入的池")
        return
    for n in names:
        print("   " + n)
    print()
    name = ask("输入要导入的池名: ").strip()
    if not name:
        print(c("yellow", "已取消"))
        return
    print()
    print(c("red", "⚠ 导入前请确认该池没有在其他主机/系统中处于挂载状态!"))
    if not confirm_destructive("zpool import " + name):
        print("已取消")
        return
    p = run(["zpool", "import", name])
    if p is not None and p.returncode == 0:
        print(c("green", "已导入: " + name))
        log("pool import " + name)
    else:
        print(c("red", "导入失败。若设备路径变化可用: zpool import -d /dev/disk/by-id " + name))


def pool_disks():
    if not have("smartctl"):
        print("未安装 smartctl, 无法读取磁盘信息")
        return
    devs = smart_devices()
    if not devs:
        print("未发现磁盘")
        return
    print()
    print("%-14s %-28s %-16s %6s" % ("DEVICE", "MODEL", "SERIAL", "TEMP"))
    for dev, args in devs:
        info = ""
        p = run(["smartctl", "-i", dev] + list(args))
        if p and p.returncode == 0:
            info = p.stdout
        model = ""
        serial = ""
        for ln in info.splitlines():
            m = re.match(r"^\s*(Device Model|Model Number|Product):\s*(.*)", ln)
            if m and not model:
                model = m.group(2).strip()
            m2 = re.match(r"^\s*Serial (Number|number):\s*(.*)", ln)
            if m2 and not serial:
                serial = m2.group(2).strip()
        temp = smart_temp(dev, args)
        temp_s = ("%d℃" % temp) if temp is not None else "-"
        print("%-14s %-28s %-16s %6s" % (dev, model or "-", serial or "-", temp_s))


def pool_replace_guide():
    found = False
    for p in get_pools():
        rows = _state_lines(out(["zpool", "status", p]))
        bad = [(n, st) for n, st, rd, wr, ck in rows if st != "ONLINE"]
        if not bad:
            continue
        found = True
        print()
        print(c("yellow", "▶ Pool: %s 存在异常设备" % p))
        for n, st in bad:
            print("   %s %s" % (n, st))
        print()
        print("操作模板(按序执行, 请根据实际盘符替换):")
        print("  1) 下线故障盘     : zpool offline %s /dev/disk/by-id/<旧盘ID>" % p)
        print("  2) 物理更换硬盘")
        print("  3) 让 ZFS 接管新盘: zpool replace %s <旧盘ID> <新盘ID>" % p)
        print("  4) 重新上线       : zpool online %s /dev/disk/by-id/<新盘ID>" % p)
        print("查看盘 ID: ls -l /dev/disk/by-id/")
        dev = bad[0][0]
        if os.path.exists("/dev/" + dev):
            hp = run(["smartctl", "-H", "/dev/" + dev])
            if hp and hp.returncode == 0:
                for ln in hp.stdout.splitlines():
                    if re.search(r"SMART overall|result:", ln):
                        print("快速健康检查: " + ln.strip())
    if not found:
        print("所有 Pool 的设备状态正常")


def _add_vdev(pool, kind, devs=None):
    """zpool add 通用: kind = 'cache' 或 'log'。devs 为空则交互询问(菜单路径)。"""
    if not pool_exists(pool):
        print(c("red", "Pool 不存在: " + pool))
        return 2
    print()
    print("当前 vdev 布局:")
    print(out(["zpool", "status", pool]))
    existing = out(["zpool", "status", pool])
    if re.search(r"^\s*(cache|logs)\s*$", existing, re.M):
        print(c("yellow", "提示: 该池已有 %s vdev, 将追加设备" % ("cache" if kind == "cache" else "log")))
    print()
    if devs is None:
        devs_s = ask("输入要添加的设备路径(多个用空格分隔, 建议用 /dev/disk/by-id/): ").strip()
        devs = devs_s.split()
    if not devs:
        print(c("yellow", "已取消"))
        return 1
    for d in devs:
        if not os.path.exists(d):
            print(c("red", "设备不存在: " + d))
            return 2
    label = "L2ARC 缓存盘" if kind == "cache" else "SLOG 日志盘"
    print()
    print(c("yellow", "即将执行: zpool add %s %s %s" % (pool, kind, " ".join(devs))))
    print(c("yellow", "⚠ 请确认设备是空闲整盘/分区, 添加后其数据会被 ZFS 使用!"))
    if FLAG_DRY:
        if kind == "cache":
            role_note = "L2ARC(cache) 是读缓存: 设备掉线/损坏不丢数据, 只是命中率下降。"
        else:
            role_note = "SLOG(log) 承担同步写: 掉盘在极端情况下可能丢最近若干秒的同步写, 建议镜像。"
        return dry_preview(
            "添加 %s" % label,
            ["zpool add %s %s %s" % (pool, kind, " ".join(devs))],
            facts=[("池", pool), ("角色", kind), ("设备", " ".join(devs)),
                   ("设备存在性", "已逐个校验存在")],
            notes=["⚠ 添加后该设备上的原有数据会被 ZFS 接管(等同擦除), 确认它是空闲盘。",
                   role_note,
                   "设备路径建议用 /dev/disk/by-id/, 免得重启后盘符漂移。"])
    if not confirm_single("确认添加 %s?" % label):
        print("取消")
        return 1
    p = run(["zpool", "add", pool, kind] + devs)
    if p is not None and p.returncode == 0:
        print(c("green", "已添加 %s: " % label))
        print(out(["zpool", "status", pool]), end="")
        log("pool add %s %s %s" % (pool, kind, " ".join(devs)))
        return 0
    err = (p.stderr if p is not None else "") or ""
    print(c("red", "添加失败: " + err.strip()[:500]))
    return 1


def pool_l2arc_add(pool=None, devs=None):
    """添加 L2ARC 缓存设备。pool 为空则交互询问。"""
    if pool is None:
        pool = ask_pool()
    if pool:
        return _add_vdev(pool, "cache", devs)
    return 2


def pool_slog_add(pool=None, devs=None):
    """添加 SLOG 日志设备。pool 为空则交互询问。"""
    if pool is None:
        pool = ask_pool()
    if pool:
        return _add_vdev(pool, "log", devs)
    return 2


def pool_destroy(pool=None):
    """删除存储池(强确认: 双重 yes + 再输完整池名)。pool 为空则交互询问。"""
    if pool is None:
        pool = ask_pool()
    if not pool:
        return 2
    if not pool_exists(pool):
        print(c("red", "Pool 不存在: " + pool))
        return 2
    print()
    print("目标池信息:")
    print(out(["zpool", "list", pool, "-o", "name,size,alloc,free,cap,health,comment"]), end="")
    print(out(["zpool", "status", pool]).split("config:")[0], end="")
    print()
    if FLAG_DRY:
        return dry_preview(
            "销毁存储池 (不可逆!)",
            ["zpool destroy -f " + pool],
            facts=[("池", pool),
                   ("失败回退链", "destroy -f → 失败则 export -f → import -N → destroy -f"),
                   ("附带动作", "成功后清理 FNOS mount 表里该池的记录")],
            notes=["⚠⚠ 不可逆: 池内全部数据、快照、克隆引用都会消失, 没有回收站。",
                   "交互路径还要求再输入一次完整池名(防误删), 干跑不执行这一步。",
                   "若只是想暂时下线, 用 zpool export 即可 —— 数据仍在盘上, 可 import 找回。"])
    if not confirm_destructive("zpool destroy -f " + pool):
        print("已取消")
        return 1
    typed = ask("为防误删, 请再次输入完整池名确认: ").strip()
    if typed != pool:
        print(c("red", "名称不匹配, 已取消"))
        return 1
    print()
    print("正在销毁 %s..." % pool)
    destroyed = False
    p = run(["zpool", "destroy", "-f", pool])
    if p is not None and p.returncode == 0:
        destroyed = True
    else:
        # 🩸 修复: 原来**自动**走
        #   `export -f → import -N → destroy -f` 的连环重试（失败后还 sleep 2 秒再 destroy 一次）——
        #   对一个**不可逆**操作做无人干预的多次尝试，而且中途失败会停在
        #   「已导出 / 未挂载」的半完成态（此时存储服务全挂，只能人工 import 救回）。
        #   现在改成**必须先确认**：人同意才走备选路径，且每一步失败立刻停手并给出恢复指引。
        print(c("yellow", "直接销毁失败(池可能被占用)。"))
        print(c("yellow", "备选路径: zpool export -f → zpool import -N → zpool destroy -f"))
        print(c("red", "  ⚠ 这条路径会让池**短暂消失**；若中途失败会停在「已导出/未挂载」的半完成态，"))
        print(c("red", "    存储服务会全挂，需要人工 `zpool import %s` 救回。" % pool))
        if not confirm_destructive("走备选路径(export → import -N → destroy)?"):
            print(c("yellow", "已取消 —— 池保持原状。"))
            return 1
        p = run(["zpool", "export", "-f", pool])
        if p is None or p.returncode != 0:
            # 🩸 修复：显式给失败一个非零退出码 ——
            #   原来这些分支只打印错误、函数**返回 None**, 而 `_pool_destroy_cli`
            #   把 None 当成功 ⇒ `export` 失败 / 池已下线都会变成 rc=0。
            print(c("red", "导出失败，已停手(池仍在原状态)"))
            return 1
        # 修复: "已导出(export)"不等于"已销毁", 不能谎报成功。
        p_imp = run(["zpool", "import", "-N", pool])
        if p_imp is None or p_imp.returncode != 0:
            # 🩸 新增：说清"现在是半完成态"—— 池处于 **exported**，
            #   数据仍在盘上，但 fnOS 的 mount 表记录**没有**清理（这是正确行为：
            #   我们没删池，就不该动记录）⇒ 运维需要知道"存储列表可能显示异常"，
            #   而不是看到一句"池仍存在"就以为一切照旧。
            print(c("red", "池已导出但**未能重新导入** —— 数据仍在磁盘上，请立即手工执行:"))
            print(c("red", "    zpool import %s" % pool))
            print(c("yellow", "  当前状态: 已导出(exported) —— fnOS 存储列表可能显示异常；"))
            print(c("yellow", "  mount 表记录**未**清理（因为池并没有被删除，这是预期行为）。"))
            return 1
        p_des = run(["zpool", "destroy", "-f", pool])
        destroyed = p_des is not None and p_des.returncode == 0
    if destroyed:
        print(c("green", "存储池已删除: " + pool))
        log("pool destroy " + pool)
        # 修复: 与 zt_fnos 的 destroy_pool() 对齐 —— 清掉 fnOS mount 表里
        #   该池的记录。原实现不碰 mount 表(本文件里根本没有 psql/mount 表相关函数),
        #   于是用 `pool-destroy` 删池后, mount 表会留一条指向不存在池的孤儿记录,
        #   fnOS WebUI 的存储列表显示异常。
        #   真机实测：删掉该挂载条目对应的巡检脚本后，mount 表仍会留一条孤儿记录。
        _mod = _load_zt_fnos()
        if _mod is not None and hasattr(_mod, "remove_from_mount"):
            try:
                if _mod.remove_from_mount(pool):
                    print(c("green", "已从 FNOS mount 表移除: " + pool))
                else:
                    print(c("yellow", "FNOS mount 表移除未成功(可稍后用「修复 mount 表」处理)"))
            except Exception as _exc:      # 清表失败不该掩盖"池已删除"这个事实
                print(c("yellow", "FNOS mount 表移除异常: %s" % _exc))
        else:
            print(c("yellow", "zt_fnos 模块不可用, 跳过 FNOS mount 表清理"))
        return 0
    # 🩸 修复: 失败必须是非零退出码(原来返回 None ⇒ `_pool_destroy_cli` 归一成 0)
    print(c("red", "删除失败, 池仍存在, 请检查占用"))
    return 1


def pool_l2arc_mode(ds=None, val=None):
    """设置 dataset 的 secondarycache(影响 L2ARC 缓存哪些数据)。
    ds / val 为空则交互询问(菜单路径); val ∈ all|metadata|none。"""
    if ds is None:
        ds = ask_dataset("L2ARC 策略目标数据集")
    if not ds:
        pause()
        return 2
    cur = ds_prop(ds, "secondarycache")
    print()
    print("当前 %s secondarycache = %s" % (ds, cur or "(读取失败)"))
    if val is None:
        print()
        print("说明: L2ARC 会缓存 secondarycache=all 的数据; metadata 仅元数据; none 不缓存")
        print("  1) all        所有数据进 L2ARC(命中率最高, 耗缓存盘)")
        print("  2) metadata   仅元数据(小容量缓存盘更优)")
        print("  3) none       不缓存(如备份/只读归档)")
        sel = ask("选择 [1-3, 回车取消]: ").strip()
        val = {"1": "all", "2": "metadata", "3": "none"}.get(sel)
    if val not in ("all", "metadata", "none"):
        print("已取消")
        pause()
        return 2
    print()
    print("即将执行: zfs set secondarycache=%s %s" % (val, ds))
    if FLAG_DRY:
        return dry_preview(
            "设置 L2ARC 缓存策略",
            ["zfs set secondarycache=%s %s" % (val, ds)],
            facts=[("数据集", ds), ("当前值", cur or "(读取失败)"), ("目标值", val)],
            notes=["secondarycache 只决定 L2ARC 缓存哪些数据, 不改数据本身, 可随时改回。",
                   "all = 命中率最高但吃缓存盘; metadata = 小容量盘更划算; none = 不缓存(归档/备份)。"])
    if not confirm_single("确认执行?"):
        print("取消")
        pause()
        return
    p = run(["zfs", "set", "secondarycache=" + val, ds])
    if p is not None and p.returncode == 0:
        print(c("green", "已设置 %s secondarycache=%s" % (ds, val)))
        log("l2arc mode %s secondarycache=%s" % (ds, val))
    else:
        # 🩸 修复：原来这里只打印、函数返回 None ⇒
        #   `_l2arc_mode_cli` 归一成 rc=0 —— 设置失败却报成功。
        print(c("red", "设置失败" + ("(rc=%d)" % p.returncode if p is not None else "(无法执行 zfs)")))
        return 1


def _pool_destroy_cli(extra):
    """CLI: pool-destroy <池名> [--dry-run]"""
    if not extra:
        print("用法: zfs-tool.py pool-destroy <池名> [--dry-run]")
        return 2
    r = pool_destroy(extra[0])
    return r if isinstance(r, int) else 0


def _vdev_add_cli(extra, kind):
    """CLI: l2arc-add|slog-add <池名> <设备...> [--dry-run]"""
    name = "l2arc-add" if kind == "cache" else "slog-add"
    if len(extra) < 2:
        print("用法: zfs-tool.py %s <池名> <设备路径...> [--dry-run]" % name)
        return 2
    r = _add_vdev(extra[0], kind, list(extra[1:]))
    return r if isinstance(r, int) else 0


def _l2arc_add_cli(extra):
    return _vdev_add_cli(extra, "cache")


def _slog_add_cli(extra):
    return _vdev_add_cli(extra, "log")


def _l2arc_mode_cli(extra):
    """CLI: l2arc-mode <数据集> <all|metadata|none> [--dry-run]"""
    if len(extra) < 2:
        print("用法: zfs-tool.py l2arc-mode <数据集> <all|metadata|none> [--dry-run]")
        return 2
    r = pool_l2arc_mode(extra[0], extra[1])
    return r if isinstance(r, int) else 0


def _prune_cli(extra):
    """CLI: prune <数据集> <保留份数> [名称前缀] [--dry-run]"""
    if len(extra) < 2:
        print("用法: zfs-tool.py prune <数据集> <保留份数> [名称前缀] [--dry-run]")
        return 2
    ds, keep_s = extra[0], extra[1]
    if not is_num(keep_s) or int(keep_s) < 1:
        print(c("red", "保留份数必须是 >=1 的整数: " + keep_s))
        return 2
    pat = extra[2] if len(extra) >= 3 else ""
    r = snap_keep(ds, int(keep_s), pat)
    return r if isinstance(r, int) else 0


def _rollback_cli(extra):
    """CLI: rollback <数据集@快照> [--dry-run]"""
    if not extra:
        print("用法: zfs-tool.py rollback <数据集@快照> [--dry-run]")
        return 2
    if "@" not in extra[0]:
        print(c("red", "需要完整快照名(形如 pool/ds@snap): " + extra[0]))
        return 2
    r = snap_rollback(extra[0])
    return r if isinstance(r, int) else 0


def _recv_file_cli(extra):
    """CLI: recv-file <源文件> <目标数据集> [--dry-run]"""
    if len(extra) < 2:
        print("用法: zfs-tool.py recv-file <源 .zfs 文件> <目标数据集> [--dry-run]")
        return 2
    r = cmd_recv_file(extra[0], extra[1])
    return r if isinstance(r, int) else 0


def _send_file_cli(extra):
    """CLI: send-file [选项] [<源快照>] [<目标文件>] [--dry-run]

    🩸 修复：原来 `send-file` **没有专属分支**，
    落到 `CLI_MAP` 的 `fn(); rc = 0` ⇒ **退出码恒为 0**（失败也报成功）。
    🆕 新增：不再"把位置参数一律当忽略"—— 给 <源快照> 就走**非交互直发**
    （原实现在非 tty 下 ask() 全空，脚本里这条命令什么都做不了，`--dry-run` 也不可达）。
    """
    opts = {"raw": False, "compressed": False, "replicate": False, "holds": False}
    pos = []
    base = None
    i = 0
    while i < len(extra):
        a = extra[i]
        if a in ("--raw", "-w"):
            opts["raw"] = True
        elif a in ("--compressed", "-c"):
            opts["compressed"] = True
        elif a in ("--replicate", "-R"):
            opts["replicate"] = True
        elif a in ("--holds", "-h"):
            opts["holds"] = True
        elif a in ("-i", "--incremental"):
            # 🩸 修复：原来 `-i` 后面没跟值时，这个分支不成立 ⇒ 落到
            #   "无法识别的参数"被忽略 ⇒ **静默降级成全量发送**（真机：全量 62.7G
            #   vs 增量 21.4G，用户完全不知道）。必须硬报错。
            if i + 1 >= len(extra) or extra[i + 1].startswith("-"):
                print(c("red", "-i/--incremental 需要基准快照名，例如: -i pool@baseline"))
                return 2
            base, i = extra[i + 1], i + 1
        elif a.startswith("-i=") or a.startswith("--incremental="):
            # 🩸 修复：等号形式原来落到"忽略无法识别的参数"⇒ **静默降级为全量**
            #   （真机：`-i=<base>` 打印「模式: 全量」，增量 21.4G vs 全量 62.7G）。
            base = a.split("=", 1)[1]
            if not base:
                print(c("red", "-i=/--incremental= 后面必须跟基准快照名"))
                return 2
        elif a.startswith("-"):
            print(c("yellow", "忽略无法识别的参数: %s" % a))
        else:
            pos.append(a)
        i += 1
    if len(pos) > 2:
        print(c("yellow", "多余的位置参数被忽略: %s" % " ".join(pos[2:])))
    r = cmd_send_file(opts=opts, snap=(pos[0] if pos else None),
                      base=base, path=(pos[1] if len(pos) > 1 else None))
    if isinstance(r, bool):
        return 0 if r else 1
    return r if isinstance(r, int) else 0


# ---------------------------------------------------------------------------
# 🆕 新增：中断接收的续传入口（receive_resume_token）
#   痛点：工具早就用了 `zfs receive -s`（保留部分接收状态），却从不读
#   `receive_resume_token` ⇒ 中断后没有恢复入口，只能从头再传一遍。
#   ⚠ token 是**敏感值**：只可用于同一接收端。本工具只在内存里持有它，
#     显示默认只给前 16 位（`--show-token` 才全显），**绝不写进 log() / --json**。
# ---------------------------------------------------------------------------

def resume_scan():
    """扫所有 fs/vol 的 receive_resume_token。返回 [{ds, token}]；读不到返回 None。"""
    p = run_noblock(["zfs", "get", "-H", "-o", "name,value", "receive_resume_token",
                     "-t", "filesystem,volume"], timeout=30)
    if p is None or p.returncode != 0:
        return None
    rows = []
    for ln in (p.stdout or "").splitlines():
        f = ln.split("\t")
        if len(f) >= 2 and f[1].strip() not in ("-", ""):
            rows.append({"ds": f[0], "token": f[1].strip()})
    return rows


def _mask_token(tok):
    """只显示前 16 位 —— token 不进日志、不进 JSON、默认不回显全文。

    🩸 修复：原来 `len(tok) <= 16` 时**原样返回**（短 token 全显），
    现在一律掩码，并附长度提示。
    """
    tok = tok or ""
    if not tok:
        return ""
    return "%s…(%d 字符)" % (tok[:16], len(tok))


def _pipe_send_recv(token, ds):
    """`zfs send -t <token> | zfs receive -s <ds>`，用 argv 直连（不经 shell）。
    返回 (rc, err)。

    🩸 修复：两侧 stderr 改成**落临时文件**再读。
    原因一（死锁）：原来 `p1.stderr` 是 PIPE，却直到 `p2.communicate()` 之后才读 ——
    上游 stderr 一旦超过管道容量（~64KB）就会阻塞 ⇒ 不关 stdout ⇒ receive 等 EOF
    ⇒ 主线程**永久挂死**（两次复现 rc=124；此时 receive 已在写池）。
    原因二（归因）：原来 receive 先失败时，真正的原因被整条丢弃
    （只报 `zfs send 失败(rc=-13): `，冒号后面是空的）。
    """
    import tempfile
    e1 = tempfile.NamedTemporaryFile(delete=False)
    e2 = tempfile.NamedTemporaryFile(delete=False)
    e1.close()
    e2.close()
    try:
        try:
            f1 = open(e1.name, "wb")
            p1 = subprocess.Popen(["zfs", "send", "-t", token],
                                  stdout=subprocess.PIPE, stderr=f1,
                                  start_new_session=True)   # 修复：独立进程组
        except OSError as exc:
            return 1, "无法启动 zfs send: %s" % exc
        try:
            f2 = open(e2.name, "wb")
            p2 = subprocess.Popen(["zfs", "receive", "-s", ds], stdin=p1.stdout,
                                  stdout=subprocess.DEVNULL, stderr=f2,
                                  start_new_session=True)   # 修复：独立进程组
        except OSError as exc:
            p1.kill()
            f1.close()
            return 1, "无法启动 zfs receive: %s" % exc
        p1.stdout.close()          # 让上游能收到 SIGPIPE
        try:
            p2.wait()
            p1.wait()
        except BaseException:
            # 🩸 修复（高危）：Ctrl-C 时**必须连子进程一起收掉** ——
            #   原实现 `finally` 只删临时文件，`zfs receive -s` 会成**孤儿继续写目标池**
            #   （实测 ppid→1 仍在跑，而且会造出新的 resume token ⇒ 续传工具反造中断）。
            for _p in (p2, p1):
                try:
                    os.killpg(os.getpgid(_p.pid), signal.SIGKILL)
                except Exception:
                    try:
                        _p.kill()
                    except Exception:
                        pass
            raise
        f1.close()
        f2.close()
        err1 = open(e1.name, "rb").read().decode("utf-8", "replace").strip()
        err2 = open(e2.name, "rb").read().decode("utf-8", "replace").strip()
        # 🩸 token 是敏感值：把可能回显的 token 从错误文本里**精确擦除**，
        #   不再依赖"上游恰好不回显"。
        if token:
            err1 = err1.replace(token, "<token>")
            err2 = err2.replace(token, "<token>")
        r1, r2 = p1.returncode, p2.returncode
        if r1 != 0 and r2 != 0:
            return 1, ("zfs send 失败(rc=%d): %s ／ zfs receive 失败(rc=%d): %s"
                       % (r1, err1[:300] or "(无输出)", r2, err2[:300] or "(无输出)"))
        if r1 != 0:
            return 1, "zfs send 失败(rc=%d): %s" % (r1, err1[:300] or "(无输出)")
        if r2 != 0:
            return 1, "zfs receive 失败(rc=%d): %s" % (r2, err2[:300] or "(无输出)")
        return 0, ""
    finally:
        for _p in (e1.name, e2.name):
            try:
                os.unlink(_p)
            except OSError:
                pass


def cmd_resume(ds=None, show_token=False):
    """🆕 新增：中断接收的续传入口。

    · 不给数据集 ⇒ **仅扫描并报告**（无待恢复项时报"未发现"且 rc=0）。
    · 给数据集   ⇒ 预览/执行 `zfs send -t <token> | zfs receive -s <ds>`。
    """
    rows = resume_scan()
    if rows is None:
        print(c("red", "读不到 receive_resume_token（zfs 命令不可用）"))
        return 1
    if not rows:
        if FLAG_JSON:
            print(json.dumps({"resumes": []}, indent=2, ensure_ascii=False))
            return 0
        print("未发现待恢复的接收（所有数据集的 receive_resume_token 均为 \"-\"）")
        return 0
    if not ds:
        if FLAG_JSON:
            # 🩸 修复：原来 `--json` 被静默忽略（反而让"token 不进 JSON"
            #   空成立）。现在真给 JSON，且 **token 一律只给掩码**，绝不整串。
            print(json.dumps({"resumes": [{"dataset": r["ds"],
                                           "token_masked": _mask_token(r["token"])}
                                          for r in rows]},
                             indent=2, ensure_ascii=False))
            return 0
        print(c("cyan", "发现 %d 个待恢复的接收：" % len(rows)))
        for r in rows:
            print("  · %s" % r["ds"])
            print("      token: %s" % (r["token"] if show_token else _mask_token(r["token"])))
        print()
        print("  续传: zfs-tool.py resume <数据集>     （先加 --dry-run 看预览）")
        print(c("dim", "  提示: token 只对**同一个接收端数据集**有效；换机器/换池无效。"))
        return 0
    hit = None
    for r in rows:
        if r["ds"] == ds:
            hit = r
            break
    if hit is None:
        if FLAG_JSON:
            # 🩸 修复：原来 `--json` 只覆盖"无 ds 且有 token"这一条分支，
            #   带 ds（含找不到）与失败分支都退化成纯文本 ⇒ 脚本没法解析。token 仍只给掩码。
            print(json.dumps({"dataset": ds, "found": False,
                              "resumes": [{"dataset": r["ds"],
                                           "token_masked": _mask_token(r["token"])}
                                          for r in rows]},
                             indent=2, ensure_ascii=False))
            return 1
        print(c("red", "该数据集没有待恢复的接收: " + ds))
        print(c("dim", "  有 token 的数据集: %s" % ", ".join(r["ds"] for r in rows)))
        return 1
    cmdline = "zfs send -t <token> | zfs receive -s %s" % ds
    if FLAG_DRY:
        return dry_preview(
            "恢复中断的接收",
            [cmdline],
            facts=[("数据集", ds),
                   ("receive_resume_token",
                    hit["token"] if show_token else _mask_token(hit["token"]))],
            notes=["恢复流的接收端必须与中断时**同一个**数据集；换机器/换池 token 无效。",
                   "token 是敏感值：本工具默认只显示前 16 位，且**不写入日志文件**。",
                   "续传是**写操作**（会往目标数据集继续写入）。"])
    if not FLAG_JSON:
        print()
        print("即将执行: " + cmdline)
    if not confirm_destructive("zfs send -t <token> | zfs receive -s %s" % ds):
        if FLAG_JSON:
            print(json.dumps({"dataset": ds, "result": "canceled"}, ensure_ascii=False))
        print("已取消")
        return 1
    rc, err = _pipe_send_recv(hit["token"], ds)
    if FLAG_JSON:
        # 🩸 修复：执行分支也出 JSON；**token 绝不进 JSON**。
        print(json.dumps({"dataset": ds,
                          "result": "ok" if rc == 0 else "failed",
                          "error": ((err or "").strip()[:400] if rc != 0 else "")},
                         indent=2, ensure_ascii=False))
    if rc == 0:
        print(c("green", "续传完成: " + ds))
        log("resume %s" % ds)          # ⚠ 只记数据集名, 不记 token
        return 0
    print(c("red", "续传失败: " + (err or "").strip()[:400]))
    log("resume failed %s: %s" % (ds, (err or "").strip()[:200]))
    return 1


def _resume_cli(extra):
    """CLI: resume [数据集] [--show-token] [--dry-run]"""
    ds = None
    show = False
    for a in extra:
        if a == "--show-token":
            show = True
        elif not a.startswith("-"):
            ds = a
        else:
            print(c("yellow", "忽略无法识别的参数: %s" % a))
    return cmd_resume(ds, show)


def cmd_brt(pool=None, deep=False):
    """🧬 块克隆（BRT / block cloning）观测 —— **纯只读**，零风险。

    `bcloneused` / `bclonesaved` 是**池级**属性（数据集级会报 invalid property），
    所以按池取。`saved` 越大说明这个池越依赖块克隆（日常 `cp` / `reflink` 都在用）：
    这部分空间**不会**因为删掉某个文件而释放（克隆块被多方引用）。
    `--deep` 会额外跑 `zdb -T`（只读，但会遍历 BRT，大池上较慢）。"""
    if pool is not None:
        if not pool_exists(pool):
            print(c("red", "Pool 不存在: " + pool))
            return 2
        pools = [pool]
    else:
        pools = get_pools()
    if not pools:
        print("无 Pool")
        return 1
    print()
    print(c("cyan", "🧬 块克隆 (BRT / block cloning) 观测"))
    print(c("cyan", "   注: 被克隆共享的块要等引用归零才释放 ⇒ 删单个文件不会立刻还空间。"))
    total_saved = 0
    got_any = False
    for p in pools:
        print()
        print(c("white", "▶ Pool: %s" % p))
        vals = {}
        q = run(["zpool", "get", "-H", "-p", "-o", "property,value",
                 "bcloneused,bclonesaved,bcloneratio", p])
        if q is not None and q.returncode == 0:
            for ln in (q.stdout or "").splitlines():
                f = ln.split("\t")
                if len(f) >= 2:
                    vals[f[0]] = f[1]
        if not vals:
            print(c("yellow", "  读不到 bclone* 属性(feature@block_cloning 是否 active?)"))
        used_b = vals.get("bcloneused", "")
        saved_b = vals.get("bclonesaved", "")
        if is_num(str(used_b)):
            print("    BRT 已用(物理) : %s" % human_bytes(int(used_b)))
            got_any = True
        if is_num(str(saved_b)):
            print("    因克隆省下     : %s" % human_bytes(int(saved_b)))
            total_saved += int(saved_b)
            got_any = True
        if vals.get("bcloneratio"):
            print("    克隆比         : %s" % vals["bcloneratio"])
        try:
            with open("/proc/spl/kstat/zfs/brtstats", encoding="utf-8",
                      errors="replace") as fh:
                for ln in fh:
                    parts = ln.split()
                    if len(parts) >= 3 and parts[0] == "brt_entries":
                        print("    BRT 条目数     : %s" % parts[2])
                        break
        except OSError:
            pass
        if deep:
            # 🩸 新增：非 root 跑 `zdb` 不是优雅报错，而是 SIGABRT(rc=134)
            #   + 断言栈（真机实测 `spa_close(): spa_refcount_count(...) > minref`）。
            #   工具本身已强制 root，但菜单/内部调用可能绕过 ⇒ 这里显式跳过并说明。
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                print(c("yellow", "      [--deep] 需要 root 权限（zdb 非 root 会崩溃），已跳过。"))
            else:
                print(c("cyan", "    [--deep] zdb -T %s ..." % p))
                z = run(["zdb", "-T", p], timeout=1800)
                if z is not None and z.returncode == 0 and (z.stdout or "").strip():
                    for ln in (z.stdout or "").splitlines():
                        if ln.strip():
                            print("      " + ln.rstrip())
                else:
                    print(c("yellow", "      zdb -T 未返回(或该池无 BRT)"))
    if total_saved > 0:
        print()
        print(c("cyan", "合计因块克隆省下: %s" % human_bytes(total_saved)))
    print()
    return 0 if got_any else 1


def _brt_cli(extra):
    """CLI: brt [池名] [--deep]"""
    pool = None
    deep = False
    for a in extra:
        if a == "--deep":
            deep = True
        elif not a.startswith("-"):
            pool = a
        else:
            print(c("yellow", "忽略无法识别的参数: %s" % a))
    return cmd_brt(pool, deep)


def pool_cache_status():
    """查看每池 L2ARC(cache)/SLOG(logs) 状态与 L2 命中统计。"""
    pools = get_pools()
    if not pools:
        print("无 Pool")
        return
    for p in pools:
        print()
        print(c("white", "▶ Pool: %s" % p))
        text = out(["zpool", "status", p])
        lines = text.splitlines()
        # 收集 cache / logs 段(缩进段名起, 到 errors/下一顶格段止)
        def grab(name):
            rows = []
            on = False
            for ln in lines:
                s = ln.strip()
                if not on and s == name and ln[:1].isspace():
                    on = True
                    rows = [ln]
                    continue
                if on:
                    if s.startswith(("errors:", "config:", "scan:", "state:", "pool:")) \
                            or (ln and not ln[0].isspace() and s):
                        break
                    if s:
                        rows.append(ln)
            return rows
        for sec, label in (("cache", "L2ARC (cache)"), ("logs", "SLOG (logs)")):
            rows = grab(sec)
            if rows:
                print("  %s:" % label)
                for r in rows:
                    print("  " + r)
            else:
                print("  %s: (未配置)" % label)
    # L2 命中概览
    if os.path.exists(ARCSTATS):
        a = arc_stats()
        if int(a["l2_size"]) > 0:
            print()
            print("L2ARC 统计:")
            print("  大小: %s GiB / 命中: %s" % (human_gib(a["l2_size"]),
                                                hit_rate(a["l2_hits"], a["l2_misses"])))


def cmd_poolmgr():
    title("🗄 ZFS Pool 管理", "拓扑/导出导入/磁盘/L2ARC/SLOG/删池(强确认)")
    print()
    print("1. vdev 拓扑/状态")
    print("2. 池列表详情")
    print("3. 导出池 (export)")
    print("4. 导入池 (import)")
    print("5. 磁盘信息")
    print("6. 换盘指引")
    print("7. 添加 L2ARC 缓存盘")
    print("8. 添加 SLOG 日志盘")
    print("9. L2ARC 缓存策略 (all/metadata/none)")
    print("10. 删除存储池 (强确认)")
    print("11. L2ARC/SLOG 状态查看")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        topo_view()
    elif opt == "2":
        print()
        print(out(["zpool", "list", "-o",
                   "name,size,alloc,free,cap,dedup,frag,health,expandsize,comment"]), end="")
    elif opt == "3":
        pool_export()
    elif opt == "4":
        pool_import()
    elif opt == "5":
        pool_disks()
    elif opt == "6":
        pool_replace_guide()
    elif opt == "7":
        pool_l2arc_add()
    elif opt == "8":
        pool_slog_add()
    elif opt == "9":
        pool_l2arc_mode()
    elif opt == "10":
        pool_destroy()
    elif opt == "11":
        pool_cache_status()
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# Dataset Manager
# ===========================================================================

VALID_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def dsm_create():
    parent = ask_dataset()
    if not parent:
        return
    new = ask("新数据集名(不含父路径): ").strip()
    if not VALID_NAME.match(new):
        print(c("red", "数据集名只能包含字母/数字/._-"))
        return
    props_s = ask("附加属性 (如 'compression=zstd recordsize=1M', 回车跳过): ").strip()
    opt = []
    if props_s:
        for kv in props_s.split():
            if not re.match(r"^[A-Za-z0-9_]+=[^ \t]+$", kv):
                print(c("red", "非法属性: %s (格式 key=value 且不含空格)" % kv))
                return
            opt.append(kv)
    target = parent + "/" + new
    if ds_exists(target):
        print(c("red", "已存在: " + target))
        return
    print()
    print("即将创建: zfs create %s %s" % (" ".join(opt), target))
    if not ask_yes("确认创建? (yes): "):
        print("取消")
        return
    p = run(["zfs", "create"] + opt + [target])
    if p is not None and p.returncode == 0:
        print(c("green", "已创建: " + target))
        log("dsm create %s %s" % (target, " ".join(opt)))
    else:
        print(c("red", "创建失败"))


def dsm_zvol():
    parent = ask_dataset()
    if not parent:
        return
    new = ask("新 zvol 名: ").strip()
    if not VALID_NAME.match(new):
        print(c("red", "名称只能包含字母/数字/._-"))
        return
    size = ask("大小 (如 20G): ").strip().upper()
    if not re.match(r"^[0-9]+[KMGTPE]?$", size):
        print(c("red", "非法大小: 示例 500M / 20G / 1T"))
        return
    sparse = ask_yes("使用 sparse(按需分配)? (y/N): ")
    target = parent + "/" + new
    print()
    print("即将创建: zfs create -V %s %s %s" % (size, "-s" if sparse else "", target))
    if not ask_yes("确认创建? (yes): "):
        print("取消")
        return
    argv = ["zfs", "create", "-V", size]
    if sparse:
        argv.append("-s")
    argv.append(target)
    p = run(argv)
    if p is not None and p.returncode == 0:
        print(c("green", "已创建 zvol: %s (%s%s)" % (target, size, ", sparse" if sparse else "")))
        log("dsm zvol %s size=%s" % (target, size))
    else:
        print(c("red", "创建失败"))


def dsm_destroy():
    ds = ask_dataset()
    if not ds:
        return
    print()
    print(out(["zfs", "list", ds, "-o", "name,used,refer,compressratio,mountpoint"]), end="")
    recursive = ask_yes("递归删除子数据集(-r)? (y/N): ")
    print()
    print(c("red", "⚠ 删除数据集会永久销毁其全部数据与快照!"))
    argv = ["zfs", "destroy"]
    if recursive:
        argv.append("-r")
    argv.append(ds)
    if not confirm_destructive(" ".join(argv)):
        print("已取消")
        return
    typed = ask("为防误删, 请再次输入完整数据集名确认: ").strip()
    if typed != ds:
        print(c("red", "名称不匹配, 已取消"))
        return
    p = run(argv)
    if p is not None and p.returncode == 0:
        print(c("green", "已删除: " + ds))
        log("dsm destroy %s recursive=%s" % (ds, recursive))
    else:
        print(c("red", "删除失败(可能存在 clone 或子数据集)"))


_DSM_PROPS = [
    ("1", "compression", "lz4 / zstd / on / off"),
    ("2", "recordsize", "4K..1M / 16M"),
    ("3", "sync", "standard / always / disabled"),
    ("4", "atime", "on / off"),
    ("5", "checksum", "on / sha256 / fletcher4"),
    ("6", "copies", "1 / 2 / 3"),
    ("7", "primarycache", "all / metadata / none"),
    ("8", "secondarycache", "all / metadata / none"),
]


def dsm_setprop():
    ds = ask_dataset()
    if not ds:
        return
    print()
    print("常用属性:")
    for num, prop, hint in _DSM_PROPS:
        print("  %s. %-16s (%s)" % (num, prop, hint))
    print("  9. 自定义属性")
    print()
    sel = ask("选择属性序号或输入 prop=value: ").strip()
    if is_num(sel):
        prop = None
        for num, pname, _ in _DSM_PROPS:
            if num == sel:
                prop = pname
                break
        if not prop:
            print("无效序号")
            return
        val = ask("输入 %s 的值: " % prop).strip()
        if not val:
            print(c("yellow", "已取消"))
            return
    else:
        if not re.match(r"^[A-Za-z0-9_]+=[^ \t]+$", sel):
            print(c("red", "格式应为 key=value"))
            return
        prop, _, val = sel.partition("=")
    print()
    print("即将执行: zfs set %s=%s %s" % (prop, val, ds))
    if not ask_yes("确认执行? (yes): "):
        print("取消")
        return
    p = run(["zfs", "set", "%s=%s" % (prop, val), ds])
    if p is not None and p.returncode == 0:
        print(c("green", "已设置: %s %s=%s" % (ds, prop, val)))
        log("dsm set %s %s=%s" % (ds, prop, val))
    else:
        print(c("red", "设置失败(值可能非法)"))


def _parse_size(s):
    """把 '100G' / '1T' 解析成字节数；非法返回 None。"""
    m = re.match(r"^([0-9]+)([KMGTPE]?)$", (s or "").strip().upper())
    if not m:
        return None
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
            "T": 1024 ** 4, "P": 1024 ** 5, "E": 1024 ** 6}[m.group(2)]
    return int(m.group(1)) * mult


def dsm_quota():
    ds = ask_dataset()
    if not ds:
        return
    print()
    print("当前配额:")
    print(out(["zfs", "get", "-o", "property,value", "quota,refquota", ds]), end="")
    print()
    print("1. 设置 quota      2. 清除 quota")
    print("3. 设置 refquota   4. 清除 refquota")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        kind, val = "quota", None
    elif opt == "2":
        kind, val = "quota", "none"
    elif opt == "3":
        kind, val = "refquota", None
    elif opt == "4":
        kind, val = "refquota", "none"
    else:
        print("无效选择")
        return
    used_b = None
    if val is None:
        val = ask("输入大小 (如 100G / 1T): ").strip().upper()
        if not re.match(r"^[0-9]+[KMGTPE]?$", val):
            print(c("red", "非法大小"))
            return
    # 🩸 修复: 下调配额前**先比对当前 used** ——
    #   `zfs set quota` 立即生效，若新配额 < 已用量，之后**所有写入立刻 ENOSPC**
    #   （服务表现为"突然写不进去"），而用户只看到"设置成功"。
    if val != "none":
        p_u = run(["zfs", "get", "-H", "-p", "-o", "value", "used", ds])
        if p_u is not None and p_u.returncode == 0 and is_num((p_u.stdout or "").strip()):
            used_b = int((p_u.stdout or "").strip())
        new_b = _parse_size(val)
        if new_b is not None and used_b is not None and new_b < used_b:
            print()
            print(c("red", "⚠ 新配额比当前用量还小!"))
            print(c("red", "  当前 used = %s，你要设成 %s"
                          % (human_bytes(used_b), val)))
            print(c("red", "  设置后该数据集的**所有新写入会立刻失败**(ENOSPC)，直到用量降下来。"))
            if not confirm_destructive("仍要把它调小到 %s" % val):
                print(c("yellow", "已取消"))
                return 1
    print()
    print("即将执行: zfs set %s=%s %s" % (kind, val, ds))
    if FLAG_DRY:
        return dry_preview(
            "设置数据集配额",
            ["zfs set %s=%s %s" % (kind, val, ds)],
            facts=[("数据集", ds), ("属性", kind), ("目标值", val),
                   ("当前 used", human_bytes(used_b) if used_b is not None else "(未取到)")],
            notes=["quota 限制**数据集及其子级**总量；refquota 只限本数据集自身(不含快照/子级)。",
                   "配额是硬限：达到后写入直接 ENOSPC，不会自动扩容。",
                   "清除配额：`zfs set quota=none`（本菜单选项 2 / 4）。"])
    if not ask_yes("确认执行? (yes): "):
        print("取消")
        return
    p = run(["zfs", "set", "%s=%s" % (kind, val), ds])
    if p is not None and p.returncode == 0:
        print(c("green", "已设置: %s %s=%s" % (ds, kind, val)))
        log("dsm quota %s %s=%s" % (ds, kind, val))
    else:
        print(c("red", "设置失败"))


def cmd_dsmgr():
    title("📁 ZFS 数据集管理", "创建 / 删除 dataset 与 zvol / 属性 / 配额管理")
    print()
    print("1. 创建 Dataset")
    print("2. 创建 zvol")
    print("3. 删除 Dataset")
    print("4. 设置属性")
    print("5. 配额管理")
    print("6. 子数据集列表")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        dsm_create()
    elif opt == "2":
        dsm_zvol()
    elif opt == "3":
        dsm_destroy()
    elif opt == "4":
        dsm_setprop()
    elif opt == "5":
        dsm_quota()
    elif opt == "6":
        ds = ask_dataset()
        if ds:
            print()
            print(out(["zfs", "list", "-r", "-o", "name,used,avail,refer,mountpoint", ds]), end="")
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# Encryption
# ===========================================================================

_ENC_COL = {"available": "green", "unavailable": "red"}


def encrypt_status():
    rows = []
    text = out(["zfs", "list", "-H", "-o", "name,encryption,keystatus,keylocation",
                "-t", "filesystem,volume"])
    for ln in text.splitlines():
        f = ln.split("\t")
        if len(f) >= 3 and f[1] not in ("off", "-"):
            rows.append(f)
    if not rows:
        print("没有发现已加密的数据集")
        return
    print()
    print("%-32s %-14s %-12s %s" % ("NAME", "ENCRYPTION", "KEYSTATUS", "KEYLOCATION"))
    for f in rows:
        n, e, k = f[0], f[1], f[2]
        kl = f[3] if len(f) > 3 else ""
        line = "%-32s %-14s %-12s %s" % (n, e, k, kl)
        if COLOR:
            line = line.replace(k, c(_ENC_COL.get(k, "yellow"), k))
        print(line)


def encrypt_load():
    ds = ask_dataset()
    if not ds:
        return
    rec = ask_yes("递归加载全部子数据集? (y/N): ")
    argv = ["zfs", "load-key"]
    if rec:
        argv.append("-r")
    argv.append(ds)
    p = run(argv)
    if p is not None and p.returncode == 0:
        print(c("green", "密钥已加载: " + ds))
        log("encrypt load-key " + ds)
    else:
        print(c("red", "加载失败(密钥位置可能不可达或需交互输入)"))


def encrypt_unload():
    ds = ask_dataset()
    if not ds:
        return
    rec = ask_yes("递归卸载全部子数据集? (y/N): ")
    argv = ["zfs", "unload-key"]
    if rec:
        argv.append("-r")
    argv.append(ds)
    p = run(argv)
    if p is not None and p.returncode == 0:
        print(c("green", "密钥已卸载: " + ds))
        log("encrypt unload-key " + ds)
    else:
        print(c("red", "卸载失败"))


def encrypt_change():
    ds = ask_dataset()
    if not ds:
        return
    ks = ds_prop(ds, "keystatus")
    if ks != "available":
        print(c("yellow", "密钥状态为 '%s', 需要先加载密钥才能更换" % ks))
        return
    print()
    print(c("red", "⚠ 更换密钥将使用新的口令/密钥材料, 旧密钥立即失效!"))
    if not confirm_destructive("zfs change-key " + ds):
        print("已取消")
        return
    p = run(["zfs", "change-key", ds])
    if p is not None and p.returncode == 0:
        print(c("green", "密钥已更换: " + ds))
        log("encrypt change-key " + ds)
    else:
        print(c("red", "更换失败"))


def cmd_encrypt():
    title("🔐 ZFS 加密管理", "加密状态总览 / 加载 / 卸载 / 更换密钥")
    print()
    print("1. 加密状态总览")
    print("2. 加载密钥 (load-key)")
    print("3. 卸载密钥 (unload-key)")
    print("4. 更换密钥 (change-key)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        encrypt_status()
    elif opt == "2":
        encrypt_load()
    elif opt == "3":
        encrypt_unload()
    elif opt == "4":
        encrypt_change()
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# History / 日志
# ===========================================================================


def hist_zpool():
    pool = ask_pool()
    if not pool:
        return
    # 🆕 交互优化 ⑤: 长输出走分页器（非 tty 自动直出全文）
    body = "\n".join(out(["zpool", "history", pool]).splitlines()[-60:])
    print()
    paged("zpool history (最近 60 条):\n" + body, threshold=25)


def hist_tool_log():
    try:
        with open(LOG_FILE, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        # 🆕 交互优化 ⑤: 同上, 走分页器
        paged("最近 30 条工具日志 (%s):\n%s"
              % (LOG_FILE, "\n".join(lines[-30:])), threshold=25)
    except OSError:
        print()
        print("还没有日志记录")


def hist_cron():
    print()
    print(c("white", "用户 crontab 中与 ZFS 相关的条目:"))
    p = run(["crontab", "-l"])
    found = []
    if p and p.returncode == 0:
        for ln in p.stdout.splitlines():
            if not ln.strip().startswith("#") and \
                    re.search(r"zfs|scrub|trim|snapshot|fstrim", ln, re.I):
                found.append(ln)
    print("\n".join(found) if found else "  (无)")
    print()
    print(c("white", "/etc/cron.d 与系统 cron 目录匹配项:"))
    found = []
    cron_root = "/etc/cron.d"
    targets = []
    if os.path.isdir(cron_root):
        targets.append(cron_root)
    for sub in ("cron.hourly", "cron.daily", "cron.weekly", "cron.monthly"):
        sp = os.path.join("/etc", sub)
        if os.path.isdir(sp):
            targets.append(sp)
    for tp in targets:
        if os.path.isdir(tp):
            for fn in os.listdir(tp):
                fp = os.path.join(tp, fn)
                try:
                    with open(fp, encoding="utf-8", errors="replace") as fh:
                        for ln in fh:
                            if not ln.strip().startswith("#") and \
                                    re.search(r"zfs|scrub|trim|fstrim", ln, re.I):
                                found.append("%s: %s" % (fp, ln.rstrip()))
                except OSError:
                    pass
    print("\n".join(found) if found else "  (无)")
    if have("systemctl"):
        print()
        print(c("white", "systemd 定时器匹配项:"))
        tp = run(["systemctl", "list-timers", "--all", "--no-pager"])
        found = []
        if tp and tp.returncode == 0:
            for ln in tp.stdout.splitlines():
                if re.search(r"zfs|scrub|trim|fstrim", ln, re.I):
                    found.append(ln)
        print("\n".join(found) if found else "  (无)")


def cmd_hist():
    title("📜 历史与日志", "zpool history / 工具日志 / ZFS 相关定时任务")
    print()
    print("1. zpool history")
    print("2. 本工具日志")
    print("3. 定时任务(ZFS 相关)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "1":
        hist_zpool()
    elif opt == "2":
        hist_tool_log()
    elif opt == "3":
        hist_cron()
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# v5: Schedule (crontab 计划任务生成/安装)
# ===========================================================================

CRON_MARK = "# zfs-tool schedule"
TOOL_PATH = os.path.abspath(__file__)
PY_BIN = sys.executable or "python3"


# cron 默认 PATH 不含 `/usr/sbin`，而 `zfs`/`zpool` 正好在那里 ⇒ 计划任务必然调不到它们。
# 修法：在生成的命令行**前面**加 shell 前缀赋值（cron 把整行交给 `sh -c`，语法合法）。
CRON_PATH_PREFIX = "PATH=/usr/sbin:/usr/bin:/sbin:/bin"


def _cron_job(mins, hours, dom, mon, dow, cmdline):
    # 🩸 修复：原来生成的 cron 行**没有 PATH** ——
    #   用户 crontab 默认 `PATH=/usr/bin:/bin`，而 `zfs`/`zpool` 只装在 `/usr/sbin`
    #   ⇒ `snap-auto` / `scrub-run` / `alerts` 三个计划任务**永远调不到 ZFS 工具**，
    #   而且**不会报错**（典型的静默失效：装了计划、看着正常、其实从没成功过）。
    return "%s %s %s %s %s %s %s  %s" % (mins, hours, dom, mon, dow,
                                         CRON_PATH_PREFIX, cmdline, CRON_MARK)


# 修复: 此处原有第 2 个 `snap_auto(ds, keep)` 定义(pyflakes 报
# "redefinition of unused 'snap_auto'")。判断依据:
#   ① Python 同名后定义覆盖前定义, 文件内后出现的
#      `snap_auto(ds, keep, label="daily")`(原 4532 行)才是运行时版本;
#   ② 仅有的两个调用点 `_snap_auto_cli()`(4774)与 `snap_policy()`(4529)
#      都用 `label=` 关键字调用 —— 旧定义没有该形参, 一旦被走到必然
#      TypeError, 反证它们一直走的是新版;
#   ③ 旧版行为是新版的子集(标签写死 daily、快照名不含时分), 删除不改变
#      任何现有调用行为。
# 故直接删除该死代码, 保留唯一实现。
def _read_crontab():
    """读当前用户 crontab, 返回 **(lines, ok)**。
    🩸 修复: 原来读取失败直接 `return []`,
    而调用方把它当成"现在没有任何计划" ⇒ 安装时写回会把**用户全部 crontab 清空**
    (只留本工具新加的行)。现在显式返回 ok —— **False 表示"读失败"(不是真的空),
    调用方必须先检查它, 读失败一律不许写回**。"""
    p = run(["crontab", "-l"])
    if p is None:
        return [], False
    if p.returncode != 0:
        err = ((p.stderr or "") + (p.stdout or "")).lower()
        if "no crontab for" in err:
            return [], True          # 确认"确实还没有 crontab" ⇒ 可以安全写回
        return [], False             # 其它原因(权限 / 命令缺失 / 未知) ⇒ 视为读失败
    return p.stdout.splitlines(), True


def _backup_crontab(lines):
    """写回 crontab 之前先把现状存一份(带时间戳)。返回备份路径或 None。"""
    try:
        _ensure_data_dir()
        path = os.path.join(DATA_DIR, "crontab.bak-%s"
                            % datetime.now().strftime("%Y%m%d-%H%M%S"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + ("\n" if lines else ""))
        return path
    except OSError:
        return None


def _write_crontab(lines):
    data = "\n".join(lines).rstrip() + "\n" if lines else ""
    p = run(["crontab", "-"], stdin_data=data)
    return p is not None and p.returncode == 0


def cmd_schedule():
    title("⏰ ZFS 计划任务", "crontab / systemd 计划: 快照保留 / Scrub / 告警")
    print()
    print("1. 预览并生成 crontab 计划")
    print("2. 查看已安装(本工具)")
    print("3. 卸载全部(本工具生成)")
    print("4. systemd timer 模板")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    if opt == "4":
        cmd_systemd_preview()
        pause()
        return
    if opt == "1":
        jobs = []
        print()
        print("逐项配置计划(不选的项目跳过):")
        if ask_yes("① 每日自动快照+保留? (y/N): "):
            ds = ask_dataset("自动快照数据集")
            if not ds:
                return
            keep = ask("保留 daily 快照份数 [默认 14]: ").strip() or "14"
            hhmm = ask("运行时刻 HH:MM [默认 03:30]: ").strip() or "03:30"
            hh, mm = (hhmm.split(":") + ["", ""])[:2]
            hh = hh or "3"
            mm = mm or "30"
            cmd = "%s %s snap-auto %s %s" % (PY_BIN, _shq(TOOL_PATH), _shq(ds), keep)
            jobs.append(_cron_job(mm, hh, "*", "*", "*", cmd))
        if ask_yes("② 每周自动 Scrub? (y/N): "):
            pool = ask_pool("Scrub 目标池")
            if not pool:
                return
            hhmm = ask("运行时刻 HH:MM [默认 04:00]: ").strip() or "04:00"
            hh, mm = (hhmm.split(":") + ["", ""])[:2]
            hh = hh or "4"
            mm = mm or "0"
            dow = ask("星期几 (0-7, 0=周日) [默认 0]: ").strip() or "0"
            cmd = "%s %s scrub-run %s" % (PY_BIN, _shq(TOOL_PATH), _shq(pool))
            jobs.append(_cron_job(mm, hh, "*", "*", dow, cmd))
        if ask_yes("③ 每日告警检查? (y/N): "):
            hhmm = ask("运行时刻 HH:MM [默认 06:00]: ").strip() or "06:00"
            hh, mm = (hhmm.split(":") + ["", ""])[:2]
            hh = hh or "6"
            mm = mm or "0"
            cmd = "%s %s alerts" % (PY_BIN, _shq(TOOL_PATH))
            jobs.append(_cron_job(mm, hh, "*", "*", "*", cmd))

        if not jobs:
            print(c("yellow", "没有生成任何计划"))
            pause()
            return
        print()
        print("将追加以下 crontab 行:")
        for j in jobs:
            print("  " + j)
        print()
        print(c("yellow", "注: 脚本路径需在 cron 环境可执行; 快照保留由 snap-auto 自动清理"))
        if not ask_yes("确认写入当前用户 crontab? (yes): "):
            print("取消")
            pause()
            return
        cur, ok = _read_crontab()
        if not ok:
            print(c("red", "读取现有 crontab 失败 —— 已中止(避免清空你原有的计划)"))
            print(c("yellow", "  请先手工跑一次 `crontab -l` 确认环境正常后再试"))
            pause()
            return
        if FLAG_DRY:
            # 🆕 目标③：补上 `schedule` 的 --dry-run —— 只列出将要写入的
            #   内容，**不碰 crontab、也不创建备份文件**（dry-run 不该有任何副作用；
            #   此前 `schedule` 是唯一没有预览的破坏性路径）。
            _preview = [ln for ln in cur if CRON_MARK not in ln] + jobs
            print(c("yellow", "【dry-run】不会写入 crontab。将要写入的内容:"))
            for _ln in _preview:
                print("  " + _ln)
            print(c("dim", "  现有 crontab 保持原样；未创建备份。"))
            pause()
            return
        bak = _backup_crontab(cur)
        if not bak:
            print(c("red", "备份现有 crontab 失败 —— 已中止写回(没有退路就不动手)"))
            pause()
            return
        print(c("cyan", "已备份现有 crontab → " + bak))
        cur = [ln for ln in cur if CRON_MARK not in ln]
        cur.extend(jobs)
        if _write_crontab(cur):
            print(c("green", "已写入 %d 条计划" % len(jobs)))
            log("schedule install %d jobs" % len(jobs))
        else:
            print(c("red", "写入失败"))
        pause()
    elif opt == "2":
        _rows, ok = _read_crontab()
        if not ok:
            print(c("red", "读取 crontab 失败 —— 这不是「没有计划」, 是读不到"))
            print(c("yellow", "  请手工 `crontab -l` 确认"))
            pause()
            return
        rows = [ln for ln in _rows if CRON_MARK in ln]
        print()
        if rows:
            for r in rows:
                print("  " + r)
        else:
            print("  尚未安装任何本工具生成的计划")
        pause()
    elif opt == "3":
        rows, ok = _read_crontab()
        if not ok:
            print(c("red", "读取 crontab 失败 —— 已中止(避免误清你原有的计划)"))
            pause()
            return
        mine_all = [ln for ln in rows if CRON_MARK in ln]
        if FLAG_DRY:
            # 🆕 目标③: 卸载路径同样支持 --dry-run（无副作用）。
            print(c("yellow", "【dry-run】不会写入 crontab。将要移除的行:"))
            for _ln in mine_all:
                print("  " + _ln)
            print(c("dim", "  现有 crontab 保持原样；未创建备份。"))
            pause()
            return
        bak = _backup_crontab(rows)
        if not bak:
            # 🩸 修复：同上 —— 卸载也是写回，备份失败就不动手。
            print(c("red", "备份现有 crontab 失败 —— 已中止卸载(没有退路就不动手)"))
            pause()
            return
        print(c("cyan", "已备份现有 crontab → " + bak))
        mine = [ln for ln in rows if CRON_MARK in ln]
        if not mine:
            print("没有可卸载的本工具计划")
            pause()
            return
        print()
        print("将移除 %d 行:" % len(mine))
        for r in mine:
            print("  " + r)
        if not confirm_destructive("从 crontab 移除以上计划"):
            print("已取消")
            pause()
            return
        rest = [ln for ln in rows if CRON_MARK not in ln]
        if _write_crontab(rest):
            print(c("green", "已卸载 %d 行" % len(mine)))
            log("schedule uninstall %d jobs" % len(mine))
        else:
            print(c("red", "移除失败"))
        pause()
    elif opt == "0":
        return
    else:
        print("无效选择")
        pause()


# ===========================================================================
# v5.1: Report (体检报告导出)
# ===========================================================================

def _html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _write_report_html(path, text_lines):
    """把 txt 报告转成简单的自包含 HTML 页面。"""
    body = []
    body.append("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
                "<title>ZFS Report</title>"
                "<style>body{font-family:Consolas,Menlo,monospace;margin:2em;background:#111;color:#ddd}"
                "pre{line-height:1.4}.c{color:#6f6}</style></head><body>")
    body.append("<h3>ZFS 体检报告</h3><pre>")
    for ln in text_lines:
        body.append(_html_escape(ln))
    body.append("</pre></body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")


def cmd_report():
    title("📄 ZFS 体检报告", "一次收集健康/告警/拓扑/SMART 摘要, 导出报告文件留档")
    if not get_pools():
        print("无 Pool, 无需生成报告")
        pause()
        return
    try:
        os.makedirs(CONF["log_dir"], exist_ok=True)
    except OSError:
        pass
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(CONF["log_dir"], "zfs-report-%s.txt" % stamp)

    lines = ["=" * 60,
             "ZFS 体检报告  zfs-tool v%s  %s" % (VERSION, datetime.now().strftime("%F %T")),
             "=" * 60]
    for p in get_pools():
        lines.append("")
        lines.append("== Pool: %s ==" % p)
        health = out(["zpool", "get", "-H", "-o", "value", "health", p]).strip()
        lines.append("Health: " + health)
        cap = out(["zpool", "list", "-H", "-o", "cap", p]).strip()
        frag = out(["zpool", "list", "-H", "-o", "frag", p]).strip()
        lines.append("Cap: %s   Frag: %s" % (cap, frag))
        lines.append("Scan: " + (pool_scan_line(p) or "无记录"))
        errs = [(n, rd, wr, ck) for n, _s, rd, wr, ck
                in _state_lines(out(["zpool", "status", p])) if rd + wr + ck > 0]
        lines.append("设备错误: " + (", ".join(
            "%s R%d/W%d/C%d" % (n, rd, wr, ck) for n, rd, wr, ck in errs) or "无"))
        top = out(["zfs", "list", "-H", "-r", "-o", "name,used,compressratio", p]).splitlines()
        lines.append("数据集用量 Top 8:")
        lines.extend("   " + t for t in top[:8])
    lines.append("")
    lines.append("-- 告警 --")
    lines.extend("[%s] %s" % (lv, msg) for lv, msg in alerts_collect())
    lines.append("")
    lines.append("-- SMART --")
    for dev, args in smart_devices():
        t = smart_temp(dev, args)
        lines.append("%s temp=%s" % (dev, t if t is not None else "N/A"))
    lines.append("")
    lines.append("-- 生成完毕 --")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print()
        print(c("green", "报告已生成: " + path))
        print("共 %d 行; 可用 cat 查看。" % len(lines))
        log("report written " + path)
    except OSError as exc:
        print(c("red", "写入失败: %s" % exc))
    # 同步生成 HTML 版本
    try:
        hpath = path[:-4] + ".html"
        _write_report_html(hpath, lines)
        print(c("green", "HTML 版: " + hpath))
    except OSError as exc:
        print(c("yellow", "HTML 写入失败: %s" % exc))
    pause()


# ===========================================================================
# v5: Deep (深度只读诊断)
# ===========================================================================

ZIL_STATS = "/proc/spl/kstat/zfs/zil"


def deep_zil():
    print()
    print("ZIL 统计 (%s):" % ZIL_STATS)
    try:
        with open(ZIL_STATS, encoding="utf-8", errors="replace") as fh:
            print(fh.read())
    except OSError:
        print(c("yellow", "无 ZIL kstat(非 OpenZFS 或未启用?)"))


DEEP_ARC_KEYS = ["demand_data_hits", "demand_data_misses", "demand_metadata_hits",
                 "demand_metadata_misses", "prefetch_data_hits", "prefetch_data_misses",
                 "prefetch_metadata_hits", "prefetch_metadata_misses", "mfu_ghost_hits",
                 "mru_ghost_hits", "deleted", "recycle_miss", "mutex_miss", "evict_skip"]


def deep_arc_detail():
    print()
    print("ARC 细分类:")
    vals = {}
    try:
        with open(ARCSTATS, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                f = ln.split()
                if len(f) >= 3 and f[0] in DEEP_ARC_KEYS:
                    vals[f[0]] = f[2]
    except OSError:
        print(c("yellow", "无 arcstats"))
        return
    if not vals:
        print(c("yellow", "读取失败"))
        return
    w = max(len(k) for k in vals)
    for k in DEEP_ARC_KEYS:
        if k in vals:
            print("%-*s %s" % (w, k, vals[k]))


def pool_layout(pool):
    """从 zpool status 提取 vdev 组: [{type, disks:[...]}]"""
    groups = []
    cur = None
    started = False
    for ln in out(["zpool", "status", pool]).splitlines():
        if ln.startswith("config:"):
            started = True
            continue
        if not started:
            continue
        if ln.strip().startswith(("errors:", "actions:")):
            break
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip(" "))
        stripped = ln.strip()
        if re.match(r"(mirror|raidz\d*|draid\d*|spare|cache|log|special|dedup)-?\d*$", stripped):
            cur = {"type": stripped, "disks": [], "indent": indent}
            groups.append(cur)
        elif cur is not None and indent > cur["indent"]:
            cur["disks"].append(stripped.split()[0])
    return groups


def deep_expand():
    print()
    print("Pool 布局与扩展性建议(只读分析):")
    for p in get_pools():
        print()
        print(c("white", "▶ %s" % p))
        groups = pool_layout(p)
        if not groups:
            print("   (无 vdev 组信息)")
            continue
        for g in groups:
            print("   %-10s 磁盘数=%d %s" % (g["type"], len(g["disks"]),
                                            " ".join(g["disks"][:6])))
        vtypes = [re.sub(r"[0-9-]+$", "", g["type"]) for g in groups]
        tips = []
        if any(t.startswith("raidz") for t in vtypes):
            tips.append("raidz 组扩容需整组加盘并重建; 建议组内不超过 8-12 块(宽条带重建风险高)")
        if any(t == "mirror" for t in vtypes):
            tips.append("mirror 组可成对扩展(每次 +1 对); 无数量硬上限")
        if not tips:
            tips.append("布局常规; 扩容请按实际冗余需求规划")
        for tip in tips:
            print("   建议: " + tip)
    print()
    print(c("yellow", "提示: 扩容属高危操作, 请先备份并查阅官方文档"))


def human_bytes(n):
    units = ("B", "K", "M", "G", "T", "P")
    f = float(n)
    for u in units:
        if f < 1024 or u == "P":
            return "%.1f%s" % (f, u)
        f /= 1024.0
    return str(n)


def deep_top():
    print()
    print("Dataset 用量 Top 10:")
    top_all = []
    for p in get_pools():
        # 修复: 少了 -p, used 列是 `1.2T`/`936G` 这种人读单位, 被
        # is_num()(纯数字正则)全部滤掉 → 列表恒空, 菜单 22→4 永远只打印标题。
        # 同文件其它取字节数的位置都带 -p(snap_prune 用 -Hp 等), 此处补齐。
        for ln in out(["zfs", "list", "-Hp", "-r", "-o", "name,used", p]).splitlines():
            f = ln.split("\t")
            if len(f) >= 2 and is_num(f[1]) and int(f[1]) > 0:
                top_all.append((int(f[1]), f[0]))
    top_all.sort(reverse=True)
    for val, name in top_all[:10]:
        print("  %12s  %s" % (human_bytes(val), name))


def cmd_deep():
    title("🔬 ZFS 深度诊断", "ZIL / ARC 细分 / 池扩展性建议 / 用量 Top 榜 (全部只读)")
    print()
    print("1. ZIL 统计")
    print("2. ARC 细分类")
    print("3. 池布局与扩展建议")
    print("4. Dataset 用量 Top 10")
    print("0. 返回")
    print()
    cli_hint([("", "等价命令: zfs-tool.py deep   (全部只读)")])
    print()
    opt = ask("选择: ").strip()
    if opt == "0":
        return
    handlers = {"1": deep_zil, "2": deep_arc_detail,
                "3": deep_expand, "4": deep_top}
    fn = handlers.get(opt)
    if fn is None:
        print("无效选择")
    else:
        # 🆕 交互优化 ⑤: 深度诊断输出很长, 统一走分页器
        #    (非交互终端由 paged 自动退回"直出全文", 不会卡住)
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        paged(buf.getvalue().rstrip("\n"), threshold=25)
    pause()


# ===========================================================================
# v5: Profile (备份配置持久化)
# ===========================================================================

PROFILE_DIR = os.path.join(CONF_DIR, "profiles")


def _profile_path(name):
    if not re.match(r"^[A-Za-z0-9_.-]+$", name):
        return None
    return os.path.join(PROFILE_DIR, name + ".json")


def _load_profiles():
    profiles = []
    if not os.path.isdir(PROFILE_DIR):
        return profiles
    for fn in sorted(os.listdir(PROFILE_DIR)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(PROFILE_DIR, fn), encoding="utf-8") as fh:
                    profiles.append((fn[:-5], json.load(fh)))
            except (OSError, ValueError):
                pass
    return profiles


def _save_profile(prof):
    # 修复: dest 会被拼进远端命令(`ssh host "zfs receive <dest>"`),
    #   这里在"保存 profile"这道唯一入口上做字符白名单校验: 只允许 [A-Za-z0-9._/-]。
    #   非法字符(空格/引号/分号/反引号…)既会把目标名拆错, 也可能让备份机以 root
    #   执行任意命令, 因此直接拒绝保存(返回 False, 由调用方报"保存失败")。
    if not re.match(r"^[A-Za-z0-9._/-]+$", prof.get("dest") or ""):
        print(c("red", "目标数据集名含非法字符, 只允许 A-Za-z0-9._/- : %r"
                % (prof.get("dest") or "")))
        return False
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
    except OSError as exc:
        print(c("red", "无法创建配置目录: %s" % exc))
        return False
    fp = _profile_path(prof["name"])
    if not fp:
        return False
    try:
        with open(fp, "w", encoding="utf-8") as fh:
            json.dump(prof, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def profile_create():
    print("—— 新建备份 Profile ——")
    ds = ask_dataset("源数据集")
    if not ds:
        return
    name = ask("Profile 名称(字母数字._-): ").strip()
    if not name or not _profile_path(name):
        print(c("red", "非法名称"))
        return
    kind = ask("目标 本地(l)/ssh(s): ").strip().lower()
    if kind == "s":
        host = ask("SSH 主机(user@host): ").strip()
        dest = ask("远端目标数据集: ").strip()
        if not host or not dest:
            print(c("yellow", "已取消"))
            return
        prof = {"name": name, "source": ds, "kind": "ssh",
                "host": host, "dest": dest, "keep": 7}
    else:
        dest = ask("本地目标数据集(建议全新路径): ").strip()
        if not dest:
            print(c("yellow", "已取消"))
            return
        prof = {"name": name, "source": ds, "kind": "local", "dest": dest, "keep": 7}
    keep = ask("目标端保留快照份数 [默认 7]: ").strip()
    if is_num(keep) and int(keep) > 0:
        prof["keep"] = int(keep)
    rate = ask("传输限速 KB/s (0=不限速; 需要 pv): ").strip()
    prof["rate_kbps"] = int(rate) if is_num(rate) and int(rate) > 0 else 0
    prof["resume"] = ask_yes("断点续传模式(-s, 需要先建好目标)? (y/N): ")
    prof["verify"] = ask_yes("发送后校验(对比 refer 大小)? (y/N): ")
    if _save_profile(prof):
        print(c("green", "已保存 Profile: " + name))
        log("profile create " + name)
    else:
        print(c("red", "保存失败"))


def _verify_backup(src_snap, dest):
    """发送后校验: 在目标端找同名尾快照, 对比 refer 大小(近似完整性检查)。"""
    tail = src_snap.split("@", 1)[1]
    dsnap = ""
    for d in out(["zfs", "list", "-H", "-t", "snapshot", "-r", dest,
                  "-o", "name"]).splitlines():
        if d.endswith("@" + tail):
            dsnap = d
            break
    if not dsnap:
        print(c("yellow", "校验: 目标端未找到快照 @" + tail + " (可能未发送)"))
        return
    src_ref = out(["zfs", "list", "-H", "-o", "refer", src_snap]).strip()
    dst_ref = out(["zfs", "list", "-H", "-o", "refer", dsnap]).strip()
    # 🩸 修复: 原来**只比 refer**(逻辑字节数) ——
    #   两个内容完全不同的快照完全可能 refer 相同 ⇒ 给出"一致"的**假校验**。
    #   现在同时比 **guid**: 同 guid 才是同一份快照(块级同源), 这才是真判据。
    src_guid = out(["zfs", "get", "-H", "-o", "value", "guid", src_snap]).strip()
    dst_guid = out(["zfs", "get", "-H", "-o", "value", "guid", dsnap]).strip()
    guid_ok = bool(src_guid) and src_guid not in ("", "-") and src_guid == dst_guid
    ref_ok = src_ref == dst_ref and src_ref != ""
    ok = guid_ok and ref_ok
    print("校验: 源   %s  refer=%s  guid=%s" % (src_snap, src_ref, src_guid))
    print("      目标 %s  refer=%s  guid=%s  %s" % (
        dsnap, dst_ref, dst_guid,
        c("green", "一致(guid 相同)") if ok else c("red", "不一致!")))
    if not guid_ok:
        print(c("yellow", "  提示: guid 不同 ⇒ 目标不是同一份快照(可能被重发/改写);"))
        print(c("yellow", "        refer 相同**不代表**内容一致, 别只看那一列。"))
    if not ok:
        notify_email("备份校验不一致",
                     "源: %s refer=%s guid=%s\n目标: %s refer=%s guid=%s\n请人工检查。" %
                     (src_snap, src_ref, src_guid, dsnap, dst_ref, dst_guid))


def _run_profile(prof):
    """执行 profile: 建快照 → 增量或全量 send/recv → 目标端保留清理。"""
    # 修复: 原来直接 prof["source"]/prof["dest"] —— profile JSON 少一个键
    #   就 KeyError, 而 backup-all 是循环调用本函数, 一份坏 profile 会让整轮中断。
    #   改为点名报告并只让该份失败(return 1)。
    ds = prof.get("source") or ""
    dest = prof.get("dest") or ""
    if not ds or not dest:
        print(c("red", "Profile %s 缺少 source/dest 字段, 已跳过该份"
                % (prof.get("name") or "(未命名)")))
        return 1
    keep = int(prof.get("keep", 7))
    if not ds_exists(ds):
        print(c("red", "源数据集不存在: " + ds))
        return 1

    snap = "%s@auto_%s" % (ds, datetime.now().strftime("%Y%m%d_%H%M%S"))
    p = run(["zfs", "snapshot", snap])
    if p is None or p.returncode != 0:
        print(c("red", "快照创建失败: " + snap))
        return 1
    print("已创建: " + snap)

    # 找目标端已有同名快照作为增量基准(从新到旧)
    base = None
    if ds_exists(dest):
        dest_tails = set()
        for d in out(["zfs", "list", "-H", "-t", "snapshot", "-r", dest,
                      "-o", "name", "-S", "creation"]).splitlines():
            if "@" in d:
                dest_tails.add(d.split("@", 1)[1])
        for s in snapshots(ds):
            if s.split("@", 1)[1] in dest_tails:
                base = s
                break

    send_cmd = ["zfs", "send"]
    if base:
        send_cmd += ["-i", base]
    send_cmd.append(snap)

    dest_pool = dest.split("/", 1)[0]
    if not pool_exists(dest_pool):
        print(c("red", "目标 Pool 不存在: " + dest_pool))
        return 1

    rate = int(prof.get("rate_kbps", 0) or 0)
    resume = bool(prof.get("resume", False))
    verify = bool(prof.get("verify", False))

    # 组装管道: send [→ pv 限速] → receive
    chain = [send_cmd]
    if rate > 0:
        if have("pv"):
            chain.append(["pv", "-L", str(rate)])
        else:
            print(c("yellow", "未安装 pv, 忽略限速设置"))
    recv_cmd = ["zfs", "receive"]
    if resume:
        recv_cmd.append("-s")
    # 修复: kind/host 改用 .get —— 缺键不再 KeyError(否则一份手改过的
    #   profile 会让 backup-all 整批中断)。
    if prof.get("kind") == "ssh":
        host = prof.get("host") or ""
        print("增量基准: %s" % (base or "(无, 全量)"))
        print("运行: %s | zfs receive %s %s" % (" | ".join(" ".join(x) for x in chain),
                                                "-s " if resume else "", dest))
        # 修复: 同 snap_backup —— dest 交给远端 shell, 必须转义
        chain.append(["ssh", host, "zfs receive " + ("-s " if resume else "") + _shq(dest)])
        rc = _pipe_chain(chain)
    else:
        print("增量基准: %s" % (base or "(无, 全量)"))
        recv_cmd.append(dest)
        chain.append(recv_cmd)
        print("运行: " + " | ".join(" ".join(x) for x in chain))
        rc = _pipe_chain(chain)
        if rc == 0 and verify and not resume and ds_exists(dest):
            _verify_backup(snap, dest)
    if rc != 0:
        print(c("red", "备份失败(exit %d)。全量时目标数据集不能已存在" % rc))
        # 🩸 修复: 失败时**清掉本次刚建的源端快照** ——
        #   否则每失败一次就残留一个 @auto_<时间戳>，日积月累（而它对应的备份并不存在）。
        p_c = run(["zfs", "destroy", snap])
        if p_c is not None and p_c.returncode == 0:
            print(c("yellow", "已清理本次未成功的源端快照: " + snap))
            log("profile cleanup failed-run snapshot: %s" % snap)
        else:
            print(c("yellow", "注意: 源端快照仍在，需人工处理: " + snap))
        return rc
    # 修复: 与 4a/4b 同源 —— 缺 name 键不该让整份备份任务崩掉
    log("profile %s run send %s -> %s" % (prof.get("name") or "(未命名)", snap, dest))

    # 目标端 auto_ 前缀保留清理
    if ds_exists(dest):
        # 🩸 修复: 原来没给 `-S`, `zfs list` 默认**按名字**排,
        #   于是 `pop(0)` 删的是"名字最小的"而不是"最老的"。本工具的 @auto_<YYYYmmdd_HHMMSS>
        #   恰好字典序=时间序才没出事; 但目标端若混入别的命名(如 auto_1 / auto_10) 就会删错。
        #   显式按 creation 升序 ⇒ 永远删最老的。
        autos = [s for s in out(["zfs", "list", "-H", "-t", "snapshot", "-r", dest,
                                 "-o", "name", "-S", "creation"]).splitlines() if "@auto_" in s]
        while len(autos) > keep:
            old = autos.pop(0)
            p = run(["zfs", "destroy", old])   # 修复: 同类假成功, 按 rc 报
            if p is not None and p.returncode == 0:
                print("清理目标端旧快照: " + old)
            else:
                err = ((p.stderr if p else "") or "").strip().splitlines()
                first = err[0] if err else ("未找到 zfs 命令" if p is None else "rc=%d" % p.returncode)
                print(c("yellow", "  ⚠ 目标端旧快照清理失败: %s (%s)" % (old, first)))
                log("profile target prune failed: %s (%s)" % (old, first))
    # 修复: 与 4a/4b/4c 同源, 缺 name 键不该 KeyError
    print(c("green", "Profile 执行完成: " + (prof.get("name") or "(未命名)")))
    return 0


def profile_run(name):
    for n, p in _load_profiles():
        if n == name:
            return _run_profile(p)
    print(c("red", "Profile 不存在: %s" % name))
    return 1


def cmd_profile():
    title("💾 备份 Profile", "保存备份目标配置, 一键执行 send/recv 与保留清理/校验")
    print()
    print("1. 列出 Profile")
    print("2. 新建 Profile")
    print("3. 执行 Profile")
    print("4. 删除 Profile")
    print("5. 全部执行 (backup-all)")
    print("0. 返回")
    print()
    opt = ask("选择: ").strip()
    profs = _load_profiles()
    if opt == "5":
        backup_all()
    elif opt == "1":
        print()
        if not profs:
            print("  (暂无 Profile)")
        for n, p in profs:
            print("  %-20s %s -> %s" % (n, p.get("source"), p.get("dest")))
    elif opt == "2":
        profile_create()
    elif opt == "3":
        if not profs:
            print("暂无 Profile, 请先新建")
        else:
            names = [n for n, _ in profs]
            ok, chosen = pick_from_list("Profile", names)
            if ok:
                profile_run(chosen)
    elif opt == "4":
        if not profs:
            print("暂无 Profile")
        else:
            names = [n for n, _ in profs]
            ok, chosen = pick_from_list("Profile", names)
            if ok:
                fp = _profile_path(chosen)
                if fp and os.path.exists(fp) and confirm_destructive("删除 Profile: " + chosen):
                    os.remove(fp)
                    print(c("green", "已删除: " + chosen))
    elif opt == "0":
        return
    else:
        print("无效选择")
    if opt != "0":
        pause()


# ===========================================================================
# status (JSON 汇总, 供脚本)
# ===========================================================================

def cmd_status():
    payload = {
        "tool": PROG,
        "version": VERSION,
        "time": datetime.now().strftime("%F %T"),
        "alerts": [{"level": lv, "message": msg} for lv, msg in alerts_collect()],
        "pools": [],
    }
    for p in _target_pools():    # 修复: 支持 -p/--pool 过滤
        cap = out(["zpool", "list", "-H", "-o", "cap", p]).strip().rstrip("%")
        frag = out(["zpool", "list", "-H", "-o", "frag", p]).strip().rstrip("%")
        errs = sum(1 for _n, _s, rd, wr, ck
                   in _state_lines(out(["zpool", "status", p])) if rd + wr + ck > 0)
        entry = {
            "name": p,
            "health": out(["zpool", "get", "-H", "-o", "value", "health", p]).strip(),
            "cap": int(cap) if is_num(cap) else None,
            "frag": int(frag) if is_num(frag) else None,
            "errors": errs,
            "scan": pool_scan_line(p),
            "scrub_age_days": scrub_age_days(p),
        }
        payload["pools"].append(entry)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ===========================================================================
# v6: 通知(邮件 SMTP) 与 去重
# ===========================================================================

import hashlib
import smtplib
import time as _time
from email.mime.text import MIMEText
from email.header import Header


def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass


def notify_email(subject, body):
    """通过 [smtp] 配置发送邮件; 返回 (ok, 错误信息)。"""
    if not SMTP_CONF["enabled"]:
        return False, "SMTP 未配置(需 host/from/to)"
    import socket
    host = socket.gethostname()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header("[zfs-tool %s] %s" % (host, subject), "utf-8")
    msg["From"] = SMTP_CONF["from"]
    msg["To"] = SMTP_CONF["to"]
    try:
        srv = smtplib.SMTP(SMTP_CONF["host"], int(SMTP_CONF["port"]) or 25, timeout=15)
        try:
            if SMTP_CONF["tls"]:
                srv.starttls()
            if SMTP_CONF.get("user"):
                srv.login(SMTP_CONF["user"], SMTP_CONF["password"])
            srv.sendmail(SMTP_CONF["from"], SMTP_CONF["to"].split(","), msg.as_string())
        finally:
            try:
                srv.quit()
            except Exception:
                pass
        log("notify email sent: " + subject)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - 通知失败不影响主流程
        log("notify email failed: %s" % exc)
        return False, str(exc)


def _notify_state():
    return os.path.join(DATA_DIR, "notify_state.json")


def maybe_send_alerts(alerts):
    """告警触发邮件: 同摘要冷却期内不重发(默认 6h)。"""
    if not SMTP_CONF["enabled"]:
        return
    serious = [(lv, msg) for lv, msg in alerts if lv in ("CRIT", "WARN")]
    if not serious:
        return
    digest = hashlib.sha256(json.dumps(serious, ensure_ascii=False).encode()).hexdigest()
    now = _time.time()
    state = {}
    _ensure_data_dir()
    try:
        with open(_notify_state(), encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        pass
    cool = int(CONF["notify_cooldown"])
    if state.get("hash") == digest and (now - float(state.get("ts", 0))) < cool:
        return
    lines = ["时间: %s" % datetime.now().strftime("%F %T"),
             "汇总: %d 严重 / %d 警告" % (
                 sum(1 for l, _ in serious if l == "CRIT"),
                 sum(1 for l, _ in serious if l == "WARN")),
             ""]
    for lv, msg in serious:
        lines.append("[%s] %s" % (lv, msg))
    ok, err = notify_email("告警 %d 条" % len(serious), "\n".join(lines))
    if ok:
        # 修复: 落盘原来没有保护 —— 邮件已发出后这里抛 OSError 会打断 cron
        #   退出码, 并丢掉去重状态, 导致下一轮重复发信。与上方读取侧对称。
        try:
            with open(_notify_state(), "w", encoding="utf-8") as fh:
                json.dump({"hash": digest, "ts": now}, fh)
        except OSError as exc:
            log("notify state write failed: %s" % exc)


def notify_test():
    """发送测试邮件。"""
    if not SMTP_CONF["enabled"]:
        print(c("red", "SMTP 未配置: 请在 %s 的 [smtp] 段填写 host/from/to" % CONF_FILE))
        return 1
    ok, err = notify_email("测试邮件",
                           "这是一封来自 zfs-tool v%s 的测试通知。\n如果你收到它, 邮件配置正常。" % VERSION)
    if ok:
        print(c("green", "测试邮件已发送到 " + SMTP_CONF["to"]))
        return 0
    print(c("red", "发送失败: " + err))
    return 1


# ===========================================================================
# v6: 趋势采集与容量预测
# ===========================================================================

TREND_CSV = os.path.join(CONF_DIR, "data", "trend.csv")
SMART_TREND_CSV = os.path.join(CONF_DIR, "data", "smart_trend.csv")


def trend_collect():
    """把当前各池状态追加一行到 trend.csv(建议 cron 每日)。"""
    _ensure_data_dir()
    header = "time,pool,health,cap,frag,errors"
    rows = []
    for p in get_pools():
        cap = out(["zpool", "list", "-H", "-o", "cap", p]).strip().rstrip("%")
        frag = out(["zpool", "list", "-H", "-o", "frag", p]).strip().rstrip("%")
        health = out(["zpool", "get", "-H", "-o", "value", "health", p]).strip()
        errs = sum(1 for _n, _s, rd, wr, ck
                   in _state_lines(out(["zpool", "status", p])) if rd + wr + ck > 0)
        cap = int(cap) if is_num(cap) else ""
        frag = int(frag) if is_num(frag) else ""
        rows.append("%s,%s,%s,%s,%s,%s" % (
            datetime.now().strftime("%Y-%m-%d %H:%M"), p, health, cap, frag, errs))
    write = True
    if os.path.exists(TREND_CSV):
        with open(TREND_CSV, encoding="utf-8") as fh:
            write = fh.read(1) == ""          # 空文件才补表头
    try:
        with open(TREND_CSV, "a", encoding="utf-8") as fh:
            if write:
                fh.write(header + "\n")
            for r in rows:
                fh.write(r + "\n")
    except OSError as exc:
        print(c("red", "写入趋势失败: %s" % exc))
        return 1
    print("已记录 %d 个池到 %s" % (len(rows), TREND_CSV))
    return 0


def _trend_rows():
    rows = []
    try:
        with open(TREND_CSV, encoding="utf-8") as fh:
            header = None
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                if header is None:
                    header = ln.split(",")
                    continue
                f = ln.split(",")
                if len(f) >= 6:
                    rows.append(dict(zip(header, f)))
    except OSError:
        pass
    return rows


def _days_until(cap_points, warn, crit):
    """最小二乘线性拟合 cap% 随时间斜率, 预测到达阈值天数。
    样本不足 2 或不再增长返回 None。"""
    if len(cap_points) < 2:
        return None
    xs = list(range(len(cap_points)))
    ys = [c for c in cap_points]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sxy / sxx
    if slope <= 0:
        return None
    last = ys[-1]
    reach = {}
    for name, th in (("警告", warn), ("严重", crit)):
        if th > last:
            days = (th - last) / slope
            reach[name] = int(days) + 1
    return reach or None


def trend_report():
    """显示各池最近样本与容量预测。"""
    title("📈 ZFS 趋势与预测", "基于 %s 的历史样本(需每日 trend-collect 落库)" % TREND_CSV)
    rows = _trend_rows()
    if not rows:
        print()
        print("还没有趋势数据。可挂 cron 每日执行: zfs-tool.py trend-collect")
        pause()
        return
    by_pool = {}
    for r in rows:
        by_pool.setdefault(r["pool"], []).append(r)
    for pool, items in by_pool.items():
        print()
        print(c("white", "▶ Pool: %s   (样本 %d 条, 最近 %s)" % (
            pool, len(items), items[-1].get("time", ""))))
        print("%-17s %-5s %-5s %-5s" % ("time", "cap%", "frag%", "err"))
        for it in items[-14:]:
            print("%-17s %-5s %-5s %-5s" % (it.get("time", ""), it.get("cap", ""),
                                            it.get("frag", ""), it.get("errors", "")))
        caps = [int(it["cap"]) for it in items if is_num(it.get("cap"))]
        if len(caps) >= 2:
            pred = _days_until(caps, int(CONF["warn_cap"]), int(CONF["crit_cap"]))
            if pred:
                print(c("yellow", "按当前增长速度预测: 距 %s%%(警告) 约 %d 天; 距 %s%%(严重) 约 %d 天" % (
                    CONF["warn_cap"], pred.get("警告", 0),
                    CONF["crit_cap"], pred.get("严重", 0))))
            else:
                print("增长趋缓或样本不足, 暂不预测")
    pause()


# ===========================================================================
# v6: 磁盘 SMART 趋势预警
# ===========================================================================

SMART_WATCH_ATTRS = {
    "reallocated": ("Reallocated_Sector_Ct", 5),
    "pending": ("Current_Pending_Sector", 197),
    "offline": ("Offline_Uncorrectable", 198),
}


def smart_attr_raw(dev, args):
    """读 SMART 关键属性 raw 值: {reallocated, pending, offline} 数字或 None。"""
    vals = {}
    p = run(["smartctl", "-A", dev] + list(args))
    if p is None or p.returncode != 0:
        return None
    for ln in p.stdout.splitlines():
        for key, (name, _aid) in SMART_WATCH_ATTRS.items():
            if re.search(r"\b" + re.escape(name) + r"\b", ln):
                nums = re.findall(r"\d+", ln)
                if nums:
                    vals[key] = int(nums[-1])
                break
    return vals or None


def smart_trend_collect(verbose=True):
    """把当前关键属性追加 smart_trend.csv; 对比上次输出增长预警。"""
    _ensure_data_dir()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not os.path.exists(SMART_TREND_CSV):
        with open(SMART_TREND_CSV, "w", encoding="utf-8") as fh:
            fh.write("time,dev,reallocated,pending,offline\n")
    # 读取上次各盘值
    # 修复: 缺属性的行现在写成 `-`, 读取端必须容错 —— 原来 int("-") 抛
    #   ValueError 会被外层 except 吞掉, 直接中断整个读取循环, `last` 只剩半截数据。
    def _trend_num(s):
        s = (s or "").strip()
        if s in ("", "-"):
            return None
        try:
            return int(s)
        except ValueError:
            return None

    last = {}
    try:
        with open(SMART_TREND_CSV, encoding="utf-8") as fh:
            for ln in fh.readlines()[1:]:
                f = ln.strip().split(",")
                if len(f) == 5 and f[1]:
                    last[f[1]] = {"reallocated": _trend_num(f[2]),
                                  "pending": _trend_num(f[3]),
                                  "offline": _trend_num(f[4])}
    except (OSError, ValueError):
        pass
    rows = []
    changed = 0
    for dev, args in smart_devices():
        vals = smart_attr_raw(dev, args)
        if vals is None:
            continue
        rows.append((dev, vals))
        prev = last.get(dev)
        if prev:
            for k in ("reallocated", "pending", "offline"):
                # 修复: 缺键/`-` 一律跳过比较 —— 原来 `.get(k, 0)` 把"读不到"
                #   当成 0, 一旦下次读到真实值就报"增长 0 -> N"的假预警。
                cur = vals.get(k)
                old = prev.get(k)
                if cur is None or old is None:
                    continue
                if cur > old:
                    changed += 1
                    if verbose:
                        print(c("red" if k == "pending" else "yellow",
                                "⚠ %s %s 增长: %s -> %s" % (dev, k, old, cur)))
    try:
        with open(SMART_TREND_CSV, "a", encoding="utf-8") as fh:
            for dev, vals in rows:
                # 修复: 缺属性写 `-` 而不是 0 —— 补 0 会在下次采样读到
                #   真实值时产生"从 0 增长"的假预警。
                fh.write("%s,%s,%s,%s,%s\n" % (
                    stamp, dev, vals.get("reallocated", "-"),
                    vals.get("pending", "-"), vals.get("offline", "-")))
    except OSError as exc:
        print(c("red", "写入 SMART 趋势失败: %s" % exc))
        return 1
    if verbose:
        print("已记录 %d 块盘到 %s%s" % (len(rows), SMART_TREND_CSV,
                                        " (检测到 %d 项增长)" % changed if changed else ""))
    if changed:
        notify_email("SMART 属性增长预警 (%d 项)" % changed,
                     "时间: %s\n磁盘 SMART 关键属性较上次采样出现增长, 请关注更换。" % stamp)
    return 0


# ===========================================================================
# v6: 快照策略(多频) / 复制增强 / systemd 模板
# ===========================================================================

SNAP_LABELS = ("hourly", "daily", "weekly", "monthly")
SNAP_DEFAULT_KEEP = {"hourly": 48, "daily": 30, "weekly": 12, "monthly": 12}


def snap_policy():
    """交互创建某频次策略快照并清理(标签+保留数)。"""
    ds = ask_dataset("策略快照数据集")
    if not ds:
        return
    ok, label = pick_from_list("快照策略(标签)", list(SNAP_LABELS))
    if not ok:
        return
    default_keep = SNAP_DEFAULT_KEEP.get(label, 14)
    keep = ask("保留 %s 快照份数 [默认 %d]: " % (label, default_keep)).strip() or str(default_keep)
    if not is_num(keep) or int(keep) < 1:
        print(c("red", "保留数量无效"))
        return
    snap_auto(ds, int(keep), label=label)


def snap_auto(ds, keep, label="daily"):
    """非交互: 创建 <label>_ 快照并保留最近 keep 份同标签快照。crontab 用。"""
    if not ds_exists(ds):
        print(c("red", "数据集不存在: " + ds))
        return 1
    name = "%s@%s_%s" % (ds, label, datetime.now().strftime("%Y%m%d_%H%M"))
    if not ds_exists(name):
        p = run(["zfs", "snapshot", name])
        if p is None or p.returncode != 0:
            print(c("red", "快照创建失败: " + name))
            return 1
        print("已创建: " + name)
        log("auto snapshot " + name)
    tag = "@" + label + "_"
    snaps = [s for s in snapshots(ds) if tag in s]
    if len(snaps) > keep:
        # 修复: 原实现不看 rc 就打印"已清理 N 个"(假成功) —— 快照被 hold/
        # 被 clone 时 zfs destroy 必然失败, 但 cron 每小时都报"已清理", 空间从未释放。
        # 这里按真实 rc 统计; 失败计数不改本函数返回码(保 cron 语义不变, 见 md §4 决策)。
        gone = 0
        for s in snaps[keep:]:
            p = run(["zfs", "destroy", s])
            if p is not None and p.returncode == 0:
                gone += 1
                log("auto prune " + s)
            else:
                err = ((p.stderr if p else "") or "").strip().splitlines()
                first = err[0] if err else ("未找到 zfs 命令" if p is None else "rc=%d" % p.returncode)
                print(c("red", "  ⚠ 过期快照销毁失败: %s (%s)" % (s, first)))
                log("auto prune failed: %s (%s)" % (s, first))
        total = len(snaps) - keep
        if gone < total:
            print(c("yellow", "已清理 %d/%d 个过期 %s 快照, %d 个失败" % (gone, total, label, total - gone)))
        else:
            print("已清理 %d 个过期 %s 快照" % (gone, label))
    return 0


def _pipe_chain(cmds):
    """任意长度管道: cmd[0] | cmd[1] | ...; 返回**整体**退出码。
    🩸 修复: 原来 `return procs[-1].returncode` 只取
    **最后一条**命令的 rc ⇒ 实测 `[exit3,exit0]` 与 `[exit0,exit3,exit0]` 都返回 0 ⇒
    `zfs send | pv | zfs receive` 会在 **send 失败**时假报「备份成功」。
    现在逐条收集 rc, **任一非零即整体失败**, 并打印末命令的 stderr。
    注: 上游 stderr 仍走 DEVNULL —— 链式管道里对上游用 PIPE 又有"读错流/死锁"风险,
    失败时下面会明确提示"上游原因需单独重跑"。"""
    if not cmds:
        return 0
    if len(cmds) == 1:
        p = run(cmds[0])
        return p.returncode if p is not None else 1
    procs = []
    try:
        prev = None
        for i, cmd in enumerate(cmds):
            kw = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
            if prev is not None:
                kw["stdin"] = prev.stdout
            if i == len(cmds) - 1:
                kw["stdout"] = subprocess.PIPE
                kw["stderr"] = subprocess.PIPE
                kw["text"] = True
                kw["encoding"] = "utf-8"
                kw["errors"] = "replace"
            procs.append(subprocess.Popen(cmd, **kw))
            prev = procs[-1]
        _out, last_err = procs[-1].communicate()
        for pr in procs[:-1]:
            pr.wait()
        rcs = [pr.returncode for pr in procs]
        bad = [i for i, rc in enumerate(rcs) if rc != 0]
        if bad:
            segs = " | ".join("%s(exit %s)" % (" ".join(cmds[i]), rcs[i]) for i in bad)
            print(c("red", "管道中有命令失败: " + segs))
            if last_err and last_err.strip():
                print(c("red", last_err.strip()[:500]))
            if any(i != len(cmds) - 1 for i in bad):
                print(c("yellow", "  上游命令的 stderr 已随管道丢弃, 其失败原因请单独重跑该命令查看"))
            return rcs[bad[0]] if rcs[bad[0]] is not None else 1
        return 0
    except OSError as exc:
        for pr in procs:
            try:
                pr.kill()
            except Exception:
                pass
        print(c("red", "管道执行失败: %s" % exc))
        return 1


def _pipe_to(cmd1, cmd2):
    return _pipe_chain([cmd1, cmd2])


def backup_all():
    """顺序执行全部 Profile, 汇总失败项。"""
    profs = _load_profiles()
    if not profs:
        print(c("yellow", "暂无 Profile"))
        return 0
    fails = []
    for name, prof in profs:
        print()
        print(c("white", "▶ Profile: %s" % name))
        rc = _run_profile(prof)
        if rc != 0:
            fails.append((name, rc))
    print()
    if fails:
        print(c("red", "完成, 但有失败: " + ", ".join("%s(%d)" % f for f in fails)))
        return 1
    print(c("green", "全部 Profile 执行成功 (%d 个)" % len(profs)))
    return 0


# systemd timer 模板
def systemd_unit(kind, ds="", keep=14, hm="03:30"):
    """返回 (service 行, timer 行); kind=snap|alerts。"""
    hh, mm = hm.split(":") if ":" in hm else ("3", "30")
    if kind == "alerts":
        desc = "zfs-tool 告警检查"
        exec_line = "%s %s alerts" % (PY_BIN, TOOL_PATH)
        oncal = "*-*-* %s:%s:00" % (hh, mm)
        unit_name = "zfs-tool-alerts"
    else:
        desc = "zfs-tool 自动快照 (%s)" % ds
        exec_line = "%s %s snap-auto %s %s %s" % (
            PY_BIN, TOOL_PATH, _shq(ds), keep, "daily")
        oncal = "*-*-* %s:%s:00" % (hh, mm)
        unit_name = "zfs-tool-snap"
    svc = ("[Unit]\nDescription=%s\n\n[Service]\nType=oneshot\n"
           "ExecStart=%s\n" % (desc, exec_line))
    timer = ("[Unit]\nDescription=%s\n\n[Timer]\nOnCalendar=%s\n"
             "Persistent=true\n\n[Install]\nWantedBy=timers.target\n" % (desc, oncal))
    return unit_name, svc, timer


def cmd_systemd_preview():
    """预览并可写入 systemd units(需 root)。"""
    print()
    print("生成 systemd timer(替代或补充 crontab):")
    ds = ""
    keep = "14"
    if ask_yes("包含每日自动快照 timer? (y/N): "):
        ds = ask_dataset("快照数据集")
        if not ds:
            return
        keep = ask("保留份数 [默认 14]: ").strip() or "14"
    include_alerts = ask_yes("包含告警 timer? (y/N): ")
    # 修复: 只有用户真的选了快照才生成 snap unit —— 原来无条件生成并写进
    #   targets, 于是"只要告警"的用户会被动装上一个 `snap-auto <空数据集>` 的
    #   timer, 每天必失败。
    snap_unit = systemd_unit("snap", ds, keep) if ds else None
    name2, svc2, timer2 = systemd_unit("alerts")
    print()
    if snap_unit is not None:
        name, svc, timer = snap_unit
        print("— 预览: %s.service —" % name)
        print(svc)
        print("— 预览: %s.timer —" % name)
        print(timer)
    if include_alerts:
        print("— 预览: %s.service —" % name2)
        print(svc2)
        print("— 预览: %s.timer —" % name2)
        print(timer2)
    print()
    if snap_unit is None and not include_alerts:
        # 修复: 两个都没选就别再问"要不要写入"了
        #   (原来会写入一个空的快照 timer)。
        print(c("yellow", "未选择任何 timer, 无需写入"))
        return
    print(c("yellow", "若同意写入 /etc/systemd/system/, 需要 root 且支持 systemd"))
    if not ask_yes("确认写入并加载? (yes): "):
        print("已取消(可手动复制上面的内容)")
        return
    base = "/etc/systemd/system"
    # 修复: 只在对应 timer 真被选中时才写它的 unit 文件
    #   (原来无条件把 snap 两项塞进 targets)。
    targets = []
    if snap_unit is not None:
        targets.append((snap_unit[0] + ".service", snap_unit[1]))
        targets.append((snap_unit[0] + ".timer", snap_unit[2]))
    if include_alerts:
        targets.append((name2 + ".service", svc2))
        targets.append((name2 + ".timer", timer2))
    for unit, content in targets:
        try:
            with open(os.path.join(base, unit), "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            print(c("red", "写入 %s 失败: %s" % (unit, exc)))
            return
    run(["systemctl", "daemon-reload"])
    failed = []
    for unit, _content in targets:
        if unit.endswith(".timer"):
            # 修复: 取 rc 再报 —— 原来 `run(...)` 的返回码被丢弃,
            #   启用成功与否都打印"已写入并启用"。
            _p = run(["systemctl", "enable", "--now", unit])
            if _p is None or _p.returncode != 0:
                failed.append(unit)
    if failed:
        print(c("red", "以下 timer 启用失败: " + ", ".join(failed)))
        print(c("yellow", "unit 文件已写入, 可手动重试: systemctl enable --now <unit>"))
        return
    print(c("green", "已写入并启用: " + ", ".join(u for u, _ in targets)))
    print("查看: systemctl list-timers | grep zfs-tool")


# ===========================================================================
# CLI 分发与入口
# ===========================================================================

# 修复: `-p/--pool` 真正生效的顶层命令白名单。
#   此前 `TARGET_POOL` 全文件只在 ask_pool()(571 行)被读取, 而这几个命令
#   不经过 ask_pool() → `zfs-tool.py -p no_such_pool_xyz health` 照样遍历
#   全部池、exit 0(真机实测, 参数被静默忽略)。
#   只收"逐池遍历、且不吃位置参数"的只读报告类命令; 其余命令给 -p 一律
#   明确报错(见下面 main() 里的用法错误分支), 绝不猜用户意图。
# 🆕 补 `lat`（按池采样延迟）—— 它必须能接 `-p/--pool`。
#   ⚠️ 真机实测抓到的：没进这张表时 `lat -p <pool>` 会被 main 直接判"不支持 -p" rc=2。
# 🆕 新增：`scrub` 也吃 `-p/--pool`（`scrub status` 用来限定池）。
POOL_FILTER_CMDS = frozenset(["health", "status", "alerts", "dashboard", "lat", "scrub"])


def _target_pools():
    """按 -p/--pool 过滤后的 Pool 列表; 未给 -p 时等价于 get_pools()。"""
    pools = get_pools()
    if not TARGET_POOL:
        return pools
    return [p for p in pools if p == TARGET_POOL]


CLI_MAP = {
    "dashboard": cmd_dashboard,
    "arc": cmd_arc,
    "health": cmd_health,
    "iostat": cmd_iostat,
    "snapshot": cmd_snapshot,
    "send-file": cmd_send_file,
    "recv-file": cmd_recv_file,
    "snapdiff": snap_diff,
    "rollback": snap_rollback,
    "backup": snap_backup,
    "prune": snap_keep,
    "scrub": cmd_scrub,
    "trim": cmd_trim,
    "frag": frag_view,
    # 🩸 修复：原来指向 `zfs_rewrite_cli(extra)`
    #   （必需一参）会 TypeError；改成 `cmd_rewrite` 后又变成 **fail-open**
    #   （专属分支一旦被删/改序，`rewrite` 会静默进交互向导而非报错）。
    #   现在指向"缺参数就报错并给用法"的包装 —— 两种失败模式都不再可能。
    "rewrite": _rewrite_cli_required,
    "dedup": cmd_dedup,
    "smart": cmd_smart,
    "dataset": cmd_dataset,
    "version": cmd_version,
    "progress": cmd_progress,
    "encrypt": cmd_encrypt,
    "poolmgr": cmd_poolmgr,
    "pool-destroy": pool_destroy,
    "l2arc-add": pool_l2arc_add,
    "slog-add": pool_slog_add,
    "l2arc-mode": pool_l2arc_mode,
    "cache-status": pool_cache_status,
    "brt": cmd_brt,
    "lat": cmd_lat,
    "checkpoint": cmd_checkpoint,
    # 🆕 新增：中断接收的续传入口。CLI_MAP 里是**无参**调用 ⇒
    #   `cmd_resume()` 在 ds=None 时只扫描并报告，绝不自动执行续传。
    "resume": cmd_resume,
    "dsmgr": cmd_dsmgr,
    "alerts": cmd_alerts,
    "doctor": cmd_doctor,
    "hist": cmd_hist,
    "schedule": cmd_schedule,
    "report": cmd_report,
    "deep": cmd_deep,
    "profile": cmd_profile,
    "status": cmd_status,
    "trend": trend_report,
    "trend-collect": trend_collect,
    "smart-trend": smart_trend_collect,
    "backup-all": backup_all,
    "notify-test": notify_test,
    "help": usage,
    # 🆕 新增：`usage` 早就列在 DRY_READONLY 白名单里（"已支持预览"名单），
    #   但 CLI_MAP 里**没有这个键** ⇒ `zfs-tool.py usage` 落到「未知命令」rc=1，
    #   而 `zfs-tool.py usage --dry-run` 却能过干跑白名单检查再到「未知命令」—— 自相矛盾。
    #   补成 `help` 的同义命令。（真机复验抓到；同类"双清单"漏登记的教训。）
    "usage": usage,
}


def _scrub_run(pool):
    """非交互 scrub-run <pool>(crontab 用)。"""
    if not pool_exists(pool):
        print(c("red", "Pool 不存在: " + pool))
        return 2
    p = run(["zpool", "scrub", pool])
    if p is not None and p.returncode == 0:
        print("Scrub 已启动: " + pool)
        log("scrub run " + pool)
        return 0
    print(c("red", "Scrub 启动失败"))
    return 1


def _snap_auto_cli(rest):
    """snap-auto <dataset> [keep] [label](crontab 用)。label ∈ hourly/daily/weekly/monthly。"""
    if not rest:
        print("用法: zfs-tool.py snap-auto <dataset> [keep] [label]")
        return 2
    ds = rest[0]
    keep = rest[1] if len(rest) > 1 and is_num(rest[1]) else "14"
    label = rest[2] if len(rest) > 2 and rest[2] in SNAP_LABELS else "daily"
    return snap_auto(ds, int(keep), label=label)


# `--dry-run` 下**允许执行**的两张表：
#   · DRY_SUPPORTED —— 已经真正实现了预览分支的破坏性命令；
#   · DRY_READONLY  —— 本身不写盘 / 不改变状态的只读命令。
# 两张表之外的命令在 `--dry-run` 下一律**拒绝执行**（fail-closed），
# 免得出现"以为在预览、其实真跑了"。
DRY_SUPPORTED = frozenset((
    "rewrite", "pool-destroy", "l2arc-add", "slog-add", "l2arc-mode",
    "prune", "rollback", "recv-file", "send-file", "quiesce",
    "schedule", "checkpoint",
    # 🆕 新增：scrub 全子命令都实现了预览分支（scan_action 走 dry_preview）；
    #   resume 的预览只显示掩码后的 token，且 dry 下不调用 `zfs send -t`。
    "scrub", "resume",
))
DRY_READONLY = frozenset((
    "dashboard", "arc", "health", "iostat", "lat", "version", "progress",
    "doctor", "hist", "status", "trend", "brt", "dataset",
    "snapdiff", "cache-status", "usage",
))
# 🩸 复验：`alerts` **不在** DRY_READONLY 里 —— 它会**真的发 SMTP 告警邮件**，
#   属于有副作用的动作；`--dry-run` 下必须被拒（原来列在里面 ⇒ dry-run 也会真发信）。


def main(argv):
    global TARGET_POOL, TARGET_DS, FLAG_JSON, FLAG_DRY, FLAG_ASSUME_YES
    rest = []
    _pflag_given = False         # 修复: 是否显式给了 -p/--pool
    _extra_opt_flags = []        # 修复: 仅用于 fnOS 子命令的原样透传
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--pool") and i + 1 < len(argv):
            # 修复: 原来这里 `continue` 把 `-p <pool>` 整个吃掉 →
            #   ① 非交互命令(health/status/alerts/dashboard)拿不到它:
            #      TARGET_POOL 全文件只在 ask_pool() 里被读, 而这些命令不经过
            #      ask_pool() → `zfs-tool.py -p no_such_pool_xyz health` 照样
            #      遍历全部池、exit 0(真机实测, 参数被静默忽略);
            #   ② fnOS 子命令(unlock/detail/tpm-* ...)因此收不到 -p/--pool。
            # 现在改为"解析 + 记下来": 命令位置参数不受污染, 选项与取值单独
            # 收进 _extra_opt_flags, 若最终命令是 fnOS 子命令再原样追加到 rest。
            # 🩸 修复：`-p -H` 这类"选项当成值"会把 zpool 的选项投进
            #   池名位置，而 `pool_exists("-H")` 会因 `zpool list -H` 返回 0 而**误判为真**。
            if argv[i + 1].startswith("-"):
                print("参数 %s 后面跟的是 %s —— 看起来是另一个选项，不是 Pool 名"
                      % (a, argv[i + 1]), file=sys.stderr)
                return 2
            TARGET_POOL = argv[i + 1]
            _pflag_given = True
            _extra_opt_flags += [a, argv[i + 1]]
            i += 2
            continue
        if a in ("-p", "--pool"):
            # 末尾缺值: 显式报错(原来会把它当命令名 → "未知命令: -p")
            print("参数 %s 缺少 Pool 名称" % a, file=sys.stderr)
            TARGET_POOL = ""
            return 2
        if a in ("-d", "--dataset") and i + 1 < len(argv):
            # 🩸 复验：`-d --dry-run` 会把 `--dry-run` **当成数据集名吃掉**
            #   ⇒ 干跑开关静默失效、命令照真跑。这里显式拒绝这种"位置写错"的形态。
            if re.match(r"^--?dry", argv[i + 1], re.I) or argv[i + 1] in ("-n", "-N"):
                print("参数 %s 后面跟的是 %s —— 看起来 --dry-run 写错了位置或拼写"
                      % (a, argv[i + 1]), file=sys.stderr)
                return 2
            TARGET_DS = argv[i + 1]
            i += 2
            continue
        if a == "--json":
            FLAG_JSON = True
            i += 1
            continue
        if a in ("--dry-run", "--dryrun", "-n"):
            # 干跑预览开关: 位置无关(命令前/后都能识别), 交给各子命令自行处理
            FLAG_DRY = True
            i += 1
            continue
        if a in ("--yes", "-y"):
            # 🆕 显式同意: 脚本化的正当入口(替代隐式"非 tty 自动同意")
            FLAG_ASSUME_YES = True
            i += 1
            continue
        if re.match(r"^--?dry", a, re.I) or a == "-N":
            # 🩸 修复：近似拼写（`--dry-run=1` /
            #   `--Dry-Run` / `--dry_run` / `-N` …）原来会被当成**位置参数静默吞掉**
            #   —— 命令照跑且没有任何警告（实测 `rollback ds@s --yes --dry-run=1` 真的
            #   执行了 `zfs rollback -r`）。用户以为在预览、其实已经写盘 ⇒ 一律报错。
            print("疑似 --dry-run 拼写错误: %s" % a, file=sys.stderr)
            print("  正确写法: --dry-run / --dryrun / -n（位置无关）", file=sys.stderr)
            return 2
        rest.append(a)
        i += 1

    if not rest:
        if not _am_root():
            print(c("red", "需要 root 权限(或使用 sudo)"))
            return 1
        # 🩸 修复：非交互（管道 / cron）下无参调用会进
        #   交互菜单，而 `ask()` 在 EOF 时恒返回空 ⇒ **死循环**
        #   （实测发现 20 秒输出 13.7KB 也不退出）。现在明确拒绝并给出替代用法。
        if not sys.stdin.isatty():
            print("非交互终端下不能进入交互菜单 —— 请显式给出命令", file=sys.stderr)
            print("  例: zfs-tool.py dashboard | health | alerts | usage", file=sys.stderr)
            return 2
        # 🩸 修复：`main_menu()` 正常退出时走 `sys.exit(menu_rc)`，
        #   这里只兜底它意外返回的情况。
        _rc = main_menu()
        return _rc if isinstance(_rc, int) else 0

    cmd = rest[0]
    if cmd in ("help", "-h", "--help", "?"):
        usage()
        return 0

    # 🩸 修复：`--dry-run` 必须**要么真预览、要么明确拒绝**。
    #   原来只有 10 个函数接了 FLAG_DRY：`profile-run` / `backup-all` / `snap-auto` /
    #   `scrub-run` 以及全部 46 个 fnOS 子命令，在 `--dry-run` 下**照常真执行**
    #   （实测发现跑出 `zfs snapshot …` / `zpool scrub …`），用户却以为在预览。
    #   现在：不在"已支持预览 / 明确只读"两张表里的命令一律**拒绝执行**（fail-closed）。
    if FLAG_DRY and cmd not in DRY_SUPPORTED and cmd not in DRY_READONLY:
        print(c("red", "命令 `%s` 尚未支持 --dry-run，已拒绝执行" % cmd))
        print(c("yellow", "  (避免「以为在预览、其实真跑了」；去掉 --dry-run 才会真正执行)"))
        print(c("dim", "  已支持预览: %s" % " ".join(sorted(DRY_SUPPORTED))))
        return 2

    if cmd != "version" and not _am_root():
        print(c("red", "需要 root 权限(或使用 sudo)"))
        return 1

    extra = rest[1:]
    # 修复: `-p/--pool` 统一处置(在命令分发之前)。
    #   ① 池不存在 → stderr 报错 + exit 2, 不再"静默遍历全部池且 exit 0";
    #   ② 命令不在 POOL_FILTER_CMDS 白名单里 → 明确报"不支持 -p", exit 2
    #      (宁可明确报错, 也不要猜用户意图);
    #   ③ fnOS 子命令 → 把 `-p/--pool <池>` 原样追加回参数, 交给 zt_fnos 透传,
    #      顶层不再吞掉它;
    #   ④ 白名单命令 → 由 _target_pools() 生效过滤。
    if _pflag_given and cmd not in FNOS_CMDS:
        if not pool_exists(TARGET_POOL):
            print("Pool 不存在: %s (来自 -p/--pool)" % TARGET_POOL, file=sys.stderr)
            return 2
        if cmd not in POOL_FILTER_CMDS:
            print("命令 `%s` 不支持 -p/--pool (支持: %s)"
                  % (cmd, "/".join(sorted(POOL_FILTER_CMDS))), file=sys.stderr)
            return 2
    if cmd in FNOS_CMDS and _extra_opt_flags:
        rest += _extra_opt_flags       # 原样透传给 zt_fnos
        extra = rest[1:]
    if cmd == "scrub":
        # 🆕 新增：带子命令走 CLI，不带子命令仍进原交互菜单。
        #   ⚠ 子命令不能塞进 `cmd_scrub()` 的签名 —— CLI_MAP 里是**无参**调用。
        rc = _scrub_cli(extra)
    elif cmd == "resume":
        rc = _resume_cli(extra)
    elif cmd == "scrub-run":
        rc = _scrub_run(extra[0]) if extra else 2
    elif cmd == "snap-auto":
        rc = _snap_auto_cli(extra)
    elif cmd == "profile-run":
        rc = profile_run(extra[0]) if extra else 2
    elif cmd == "trend-collect":
        rc = trend_collect()
    elif cmd == "smart-trend":
        rc = smart_trend_collect(verbose=not FLAG_JSON)
    elif cmd == "backup-all":
        rc = backup_all()
    elif cmd == "notify-test":
        rc = notify_test()
    elif cmd == "rewrite":
        rc = zfs_rewrite_cli(extra)
    elif cmd == "pool-destroy":
        rc = _pool_destroy_cli(extra)
    elif cmd == "l2arc-add":
        rc = _l2arc_add_cli(extra)
    elif cmd == "slog-add":
        rc = _slog_add_cli(extra)
    elif cmd == "l2arc-mode":
        rc = _l2arc_mode_cli(extra)
    elif cmd == "brt":
        rc = _brt_cli(extra)
    elif cmd == "lat":
        rc = _lat_cli(extra)
    elif cmd == "checkpoint":
        rc = _checkpoint_cli(extra)
    elif cmd == "prune":
        rc = _prune_cli(extra)
    elif cmd == "rollback":
        rc = _rollback_cli(extra)
    elif cmd == "recv-file":
        rc = _recv_file_cli(extra)
    elif cmd == "send-file":
        rc = _send_file_cli(extra)
    elif cmd == "quiesce":
        rc = quiesce_cli(extra)
    elif cmd in FNOS_CMDS:
        rc = _fnos_dispatch_guard(rest)
        if rc == 0:
            rc = fnos_dispatch(rest)
    else:
        fn = CLI_MAP.get(cmd)
        if fn is None:
            print(c("red", "未知命令: " + cmd))
            usage()
            return 1
        # 🩸 修复: 原来无条件 `rc = 0`,
        #   于是 CLI_MAP 里的命令**退出码恒为 0** ⇒ cron 分不清"成功"与"没跑 / 被取消"
        #   (真机实测 `trim </dev/null` → rc=0 且什么都没做)。
        #   现在: 命令若返回 int 就采用它; 老命令返回 None 时维持 0(向后兼容)。
        # 🆕 新增：这些命令没有专属分支，位置参数会被**静默丢弃**
        #   （如 `zfs-tool.py status tank` / `scrub tank`）。这里给一条**明确但不阻断**
        #   的提示（stderr），命令行仍照原样执行 —— 绝不让人以为参数生效了。
        if extra:
            print("提示: 命令 `%s` 不接收位置参数，已忽略: %s" % (cmd, " ".join(extra)),
                  file=sys.stderr)
            print("  池用 -p/--pool，数据集用 -d/--dataset；交互类命令请在终端直接运行。",
                  file=sys.stderr)
        _fn_rc = fn()
        if cmd == "alerts":
            rc = alerts_exit_code()
            if not FLAG_JSON:
                maybe_send_alerts(alerts_collect())
        elif isinstance(_fn_rc, int):
            rc = _fn_rc
        else:
            rc = 0
    TARGET_POOL = ""             # 修复: 别让 -p 的池名当退出码传出去
    return rc



# ==== generated embed: zt_fnos payload ====
# ⚠ 本仓不分发 zt_fnos payload —— 它派生自第三方 bash 脚本（原帖未声明许可协议）。
#   需要 fnOS 加密存储 / TPM 功能的用户：自备 zt_fnos.py 后运行
#       python src/_zt_build_single.py
#   重新注入 payload，即可得到与真实部署环境一致的单文件发行版。
#   缺少 payload 时，fnOS 子命令会 fail-safe 退出（主体 ZFS 功能不受影响）。
_ZT_EMBED_B64 = ""
# ==== end embed ====
if __name__ == "__main__":
    try:
        _code = main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
        _code = 130
    sys.exit(_code)
