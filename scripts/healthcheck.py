import os, sys, importlib

# Xác định repo root = thư mục cha của 'scripts'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

modules = ("board", "server", "client_pygame")
for m in modules:
    try:
        importlib.import_module(m)
        print(f"[OK] import {m}")
    except Exception as e:
        print(f"[ERR] import {m} -> {type(e).__name__}: {e}")
        # giữ nguyên non-zero exit để CI bắt được
        raise
