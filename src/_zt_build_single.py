# -*- coding: utf-8 -*-
r"""重建 zfs-tool.py 单文件发行版(工作副本版, 已按审计结论加固)

流程:
1) 读取 zt_fnos.py(开发版)
2) 把 zt_fnos_tpm_unlock.sh.tmpl / .service.tmpl gzip+base64 注入
   _EMBED_TPL_SH_B64 / _EMBED_TPL_SVC_B64(仅空串占位)
3) 整体 gzip+base64 生成 payload
4) 替换 zfs-tool.py 中 _ZT_EMBED_B64 块(从 START_MARK 到 END_MARK)
5) 重建后自校验: 解压 payload 必须与"注入后的开发版"逐字节一致

修复:
- 路径原先写死本机绝对路径, 换到工作副本目录后直接失效 → 改为脚本自身所在目录
- 模板注入失败原先只 WARN 就继续, 可能产出"模板为空"的坏发行版 → 改为硬失败
"""
import base64
import gzip
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.join(BASE, "zt_fnos.py")
TPL_SH = os.path.join(BASE, "zt_fnos_tpm_unlock.sh.tmpl")
TPL_SVC = os.path.join(BASE, "zt_fnos_tpm_unlock.service.tmpl")
OUT = os.path.join(BASE, "zfs-tool.py")

START_MARK = "# ==== generated embed: zt_fnos payload ===="
END_MARK = "# ==== end embed ===="


def b64_wrap(data: bytes, width=76) -> str:
    b = base64.b64encode(data).decode("ascii")
    lines = [b[i:i + width] for i in range(0, len(b), width)]
    return "(\n" + "\n".join('    "%s"' % ln for ln in lines) + "\n)"


def inject_templates(src: str) -> str:
    """把模板文件注入 _EMBED_TPL_*_B64 占位(仅空串占位可注入)。命中失败即硬失败。"""
    for tpl in (TPL_SH, TPL_SVC):
        if not os.path.isfile(tpl):
            sys.exit("ERROR: 缺少模板文件: %s" % tpl)
    for field, tpl_path in (("_EMBED_TPL_SH_B64", TPL_SH),
                            ("_EMBED_TPL_SVC_B64", TPL_SVC)):
        pat = re.compile(r"^%s = \"\"$" % field, re.M)
        if not pat.search(src):
            sys.exit("ERROR: %s 不是空串占位(可能已注入过或格式变了) —— 拒绝构建,"
                     " 以免产出'模板为空'的发行版" % field)
        raw = open(tpl_path, "rb").read()
        # 修复: gzip.compress 的 mtime 默认取"当前时间" ⇒ 每次重建压缩字节流
        # 都不同 ⇒ 同一份源码跨秒重建产物 md5 会变、`_zt_audit_payload.py` 的
        # "payload == 模拟构建" 比对也会误报。固定 mtime=0 让构建可复现。
        val = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")
        src = pat.sub('%s = "%s"' % (field, val), src, count=1)
        print("injected %s <- %s (%d bytes, b64=%d)"
              % (field, os.path.basename(tpl_path), len(raw), len(val)))
    return src


def main():
    with open(DEV, encoding="utf-8", newline="") as fh:
        dev = fh.read()
    injected = inject_templates(dev)
    # 修复: 固定 mtime 让单文件构建可复现（见上面 inject_templates 的注释）
    payload = gzip.compress(injected.encode("utf-8"), 9, mtime=0)
    print("payload gzip bytes:", len(payload))

    with open(OUT, encoding="utf-8", newline="") as fh:
        out = fh.read()
    i_start = out.find(START_MARK)
    i_end = out.find(END_MARK)
    if i_start < 0 or i_end < 0 or i_end <= i_start:
        sys.exit("ERROR: zfs-tool.py 中找不到 embed 标记")
    head = out[:i_start]
    tail = out[i_end + len(END_MARK):]
    new = head + START_MARK + "\n_ZT_EMBED_B64 = " + b64_wrap(payload) + "\n" + END_MARK + tail

    # 自校验(审查 新增): 解压刚写入的 payload, 必须与注入后的开发版逐字节一致
    m = re.search(r"_ZT_EMBED_B64 = \(\n(.*?)\n\)", new, re.S)
    b64 = "".join(re.findall(r'"([A-Za-z0-9+/=]+)"', m.group(1)))
    back = gzip.decompress(base64.b64decode(b64)).decode("utf-8")
    if back != injected:
        sys.exit("ERROR: 自校验失败 —— 内嵌 payload 与注入后的开发版不一致")
    print("self-check: payload 解压 == 注入后开发版  OK (%d 字符)" % len(back))

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print("wrote", OUT, "len", len(new))


if __name__ == "__main__":
    main()
