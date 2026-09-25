# -*- coding: utf-8 -*-
"""单文件加载链路实测(只读): exec zfs-tool.py 模块 → _load_zt_fnos() 解包 payload → main(["-v"])。"""
import importlib.util
import os
import sys

# 修复: 原为写死本机绝对路径 → 改用脚本自身所在目录。
# 注意: 本脚本末尾会执行 main([]) 进入交互菜单, 仅适合在真机/交互终端下跑;
#       在无人值守环境请只跑到 _load_zt_fnos() 那步。
_SINGLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zfs-tool.py")
spec = importlib.util.spec_from_file_location("zfs_tool_mod", _SINGLE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

mod = m._load_zt_fnos()
print("payload 加载成功:", mod is not None)
if mod is not None:
    print("payload SCRIPT_VERSION:", mod.SCRIPT_VERSION)
    rc = mod.main(["-v"])
    print("main(['-v']) 返回码:", rc)
    rc2 = mod.main([])
    print("main([]) 返回码:", rc2)
