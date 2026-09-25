# -*- coding: utf-8 -*-
r"""payload 一致性审计(只读), 工作副本版:
1) 从 zfs-tool.py 提取 _ZT_EMBED_B64, gzip 解压得单文件内嵌源码
2) 模拟 _zt_build_single.py: 读取 zt_fnos.py, 注入两个 .tmpl 到 _EMBED_TPL_*_B64
3) 比较: 内嵌源码 vs 模拟构建结果 —— 不一致说明单文件没跟上开发版
4) 输出差异摘要(前 40 处) + 关键统计

修复:
- 路径原先写死本机绝对路径 → 改为脚本自身所在目录
- simulate_build 里占位正则匹配失败原先**静默跳过**(会导致审计假通过) → 改为直接报错退出
"""
import base64
import difflib
import gzip
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.join(BASE, "zt_fnos.py")
TPL_SH = os.path.join(BASE, "zt_fnos_tpm_unlock.sh.tmpl")
TPL_SVC = os.path.join(BASE, "zt_fnos_tpm_unlock.service.tmpl")
SINGLE = os.path.join(BASE, "zfs-tool.py")


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def extract_embed(src):
    m = re.search(r"_ZT_EMBED_B64 = \(\n(.*?)\n\)", src, re.S)
    if not m:
        sys.exit("ERROR: 找不到 _ZT_EMBED_B64 块")
    b64 = "".join(re.findall(r'"([A-Za-z0-9+/=]+)"', m.group(1)))
    return gzip.decompress(base64.b64decode(b64)).decode("utf-8")


def tpl_b64(path):
    raw = open(path, "rb").read()
    # 修复: 与 _zt_build_single.py 保持同样的 mtime=0，否则每次"模拟构建"
    # 的压缩字节流都不同 ⇒ 明明内容一致也会误报 "payload != 模拟构建"。
    return base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")


def simulate_build(dev):
    s = dev
    for field, path in (("_EMBED_TPL_SH_B64", TPL_SH),
                        ("_EMBED_TPL_SVC_B64", TPL_SVC)):
        pat = re.compile(r"^%s = \"\"$" % field, re.M)
        if not pat.search(s):
            sys.exit("ERROR: %s 不是空串占位 —— 无法模拟构建(开发版可能已被注入过)。"
                     " 审计中止, 不做假通过。" % field)
        s = pat.sub('%s = "%s"' % (field, tpl_b64(path)), s, count=1)
    return s


def main():
    single = read(SINGLE)
    payload_src = extract_embed(single)
    dev = read(DEV)
    built = simulate_build(dev)

    print("== 统计 ==")
    print("zfs-tool.py 总行数      :", single.count("\n") + 1)
    print("zt_fnos.py 开发版行数   :", dev.count("\n") + 1)
    print("payload 解压后行数      :", payload_src.count("\n") + 1)
    print("模拟构建后行数          :", built.count("\n") + 1)

    if payload_src == built:
        print("payload == zt_fnos.py+模板注入 : OK(完全一致)")
    else:
        print("payload != 模拟构建 !!!")
        d1 = list(difflib.unified_diff(payload_src.splitlines(), built.splitlines(),
                                       "payload(单文件内)", "zt_fnos.py+注入模拟", lineterm=""))
        print("diff 总行数:", len(d1))
        shown = 0
        for ln in d1:
            if ln[:1] in "+-" and ln[:3] not in ("+++", "---"):
                print(ln[:200])
                shown += 1
                if shown >= 40:
                    print("...(截断, 共 %d 行 diff)" % len(d1))
                    break
        if shown == 0:
            print("(unified_diff 无 +/- 内容行, 仅位置差异?)")

    print("\n== payload vs 开发版 zt_fnos.py(预期仅 2 行模板 b64 差异) ==")
    d2 = list(difflib.unified_diff(payload_src.splitlines(), dev.splitlines(),
                                   "payload", "zt_fnos.py 开发版", lineterm=""))
    only_lines = [ln for ln in d2 if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    non_tpl = [ln for ln in only_lines if "_EMBED_TPL_" not in ln]
    print("差异内容行总数:", len(only_lines), "| 其中非模板行:", len(non_tpl))
    for ln in non_tpl[:30]:
        print(ln[:200])

    def names(src):
        return sorted(re.findall(r"^def ([a-zA-Z_][a-zA-Z0-9_]*)", src, re.M))

    a, b = names(payload_src), names(dev)
    print("\n== def 清单对比(payload vs 开发版) ==")
    print("payload def 数:", len(a), "| 开发版 def 数:", len(b))
    miss = [x for x in b if x not in a]
    extra = [x for x in a if x not in b]
    print("开发版有而 payload 缺:", miss if miss else "无")
    print("payload 有而开发版缺:", extra if extra else "无")

    # 额外检查(审查): 内嵌模板的换行符必须已归一化(不能带 CR)
    print("\n== payload 内 _EMBED_TPL_* 状态(含 CRLF 检查) ==")
    for m in re.finditer(r'^_EMBED_TPL_(SH|SVC)_B64 = "([^"]*)"', payload_src, re.M):
        val = m.group(2)
        if not val:
            print("_EMBED_TPL_%s_B64 = 空串 (发行版会缺模板!)" % m.group(1))
            continue
        raw = gzip.decompress(base64.b64decode(val))
        print("_EMBED_TPL_%s_B64 长度(b64)=%d 解出=%d 字节  CR 数=%d"
              % (m.group(1), len(val), len(raw), raw.count(b"\r")))


if __name__ == "__main__":
    main()
