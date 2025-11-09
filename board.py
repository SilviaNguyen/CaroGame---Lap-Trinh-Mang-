from typing import List, Optional, Tuple

class Board:
    def __init__(self, size: int = 15, win_len: int = 5):
        if size < 3 or win_len < 3:
            raise ValueError("size and win_len must be >= 3")
        self.size = size
        self.win_len = win_len
        self.grid: List[List[str]] = [["" for _ in range(size)] for _ in range(size)]
        self.moves = 0
        self.winner: Optional[str] = None
        self.turn: str = "X"  # X đi trước

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def get(self, x: int, y: int) -> Optional[str]:
        if not self.in_bounds(x,y):
            return None
        return self.grid[y][x]

    def place(self, x: int, y: int, symbol: str) -> bool:
        if self.winner is not None:
            return False
        if not self.in_bounds(x, y) or self.grid[y][x] != "" or symbol != self.turn:
            return False
        self.grid[y][x] = symbol
        self.moves += 1
        if self.check_win_from(x, y):
            self.winner = symbol
        else:
            self.turn = "O" if self.turn == "X" else "X"
        return True

    def line_count(self, x: int, y: int, dx: int, dy: int) -> int:
        sym = self.get(x, y)
        if sym == "":
            return 0
        total = 1
        # tiến
        cx, cy = x + dx, y + dy
        while self.in_bounds(cx, cy) and self.get(cx, cy) == sym:
            total += 1
            cx += dx
            cy += dy
        # lùi
        cx, cy = x - dx, y - dy
        while self.in_bounds(cx, cy) and self.get(cx, cy) == sym:
            total += 1
            cx -= dx
            cy -= dy
        return total

    def check_win_from(self, x: int, y: int) -> bool:
        directions = [(1,0),(0,1),(1,1),(1,-1)]
        for dx, dy in directions:
            if self.line_count(x, y, dx, dy) >= self.win_len:
                return True
        return False

    def is_draw(self) -> bool:
        return self.winner is None and self.moves >= self.size * self.size

    def to_list(self) -> List[List[str]]:
        return self.grid

    @classmethod
    def from_list(cls, grid: List[List[str]], turn: str, win_len: int):
        b = cls(size=len(grid), win_len=win_len)
        b.grid = grid
        b.turn = turn
        # Recompute moves quickly
        b.moves = sum(1 for row in grid for c in row if c)
        return b
    
    # === HÀM MỚI ĐƯỢC THÊM ĐỂ XỬ LÝ NÚT NEW===
    def reset(self): 
        """Sửa lỗi crash khi bấm New Game."""
        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]
        self.moves = 0
        self.winner = None
        self.turn = "X"