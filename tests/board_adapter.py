# tests/board_adapter.py
"""
Adapter giúp test tự khớp API board.py của nhóm:
- Tự dò tên hàm đặt quân: place/make_move/set_move và thứ tự tham số (x,y) hoặc (y,x).
- Tự map ký hiệu: 'X'/'O' hoặc 1/2 hoặc 'x'/'o'.
- Tự dò hàm/thuộc tính kiểm tra thắng: check_win/is_win_at/has_winner/winner/get_winner.
"""

from __future__ import annotations
import typing as t

# Các biến thể ký hiệu có thể gặp trong dự án
SYMBOL_MAPS: list[dict[str, t.Any]] = [
    {"X": "X", "O": "O"},
    {"X": "x", "O": "o"},
    {"X": 1,   "O": 2},
]

# Các biến thể hàm đặt quân + thứ tự tham số
CALL_ORDERS = [
    ("place",     ("x", "y", "p")),
    ("place",     ("y", "x", "p")),
    ("make_move", ("x", "y", "p")),
    ("make_move", ("y", "x", "p")),
    ("set_move",  ("x", "y", "p")),
    ("set_move",  ("y", "x", "p")),
]

def _try_place(b, x: int, y: int, p: str) -> bool:
    last_exc = None
    for fn_name, order in CALL_ORDERS:
        fn = getattr(b, fn_name, None)
        if not callable(fn):
            continue
        for sym in SYMBOL_MAPS:
            px = sym.get(p, p)
            try:
                args = (x, y, px) if order == ("x", "y", "p") else (y, x, px)
                ret = fn(*args)
                # Nhiều code không trả về gì => hiểu là thành công
                return True if ret is None else bool(ret)
            except Exception as e:
                last_exc = e
                continue
    # Không khớp được API
    return False

def _check_win(b, x: int, y: int, p: str) -> bool:
    # 1) hàm theo toạ độ
    for name in ("check_win", "is_win_at"):
        fn = getattr(b, name, None)
        if callable(fn):
            try:
                return bool(fn(x, y))
            except Exception:
                pass
            try:
                return bool(fn(y, x))
            except Exception:
                pass
    # 2) has_winner()/winner/get_winner (hàm hoặc thuộc tính)
    for name in ("has_winner", "winner", "get_winner"):
        attr = getattr(b, name, None)
        if callable(attr):
            try:
                w = attr()
            except Exception:
                w = None
        else:
            w = attr
        if w is not None:
            s = str(w).upper()
            return s in (p.upper(), "1" if p == "X" else "2")
    # 3) không có API rõ ràng -> coi như chưa thắng
    return False

class BoardAdapter:
    """Lớp bọc quanh Board để test dùng thống nhất .place()/.check_win()."""
    def __init__(self, board):
        self.board = board

    def place(self, x: int, y: int, p: str) -> bool:
        return _try_place(self.board, x, y, p)

    def check_win(self, x: int, y: int, p: str) -> bool:
        return _check_win(self.board, x, y, p)
