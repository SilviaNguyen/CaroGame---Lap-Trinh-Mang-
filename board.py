class Board:
    def __init__(self, size: int = 15, win_len: int = 5):
        if size < 3 or win_len < 3:
            raise ValueError("size and win_len must be >= 3")
        self.size = size
        self.win_len = win_len
        self.grid = [["" for _ in range(size)] for _ in range(size)]
        self.moves = 0
        self.winner = None
        self.turn = "X"
        self.win_line = None  # [(x,y), ...]

    def reset(self):
        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]
        self.moves = 0
        self.winner = None
        self.turn = "X"
        self.win_line = None

    def place(self, x: int, y: int, symbol: str) -> bool:
        if self.winner:
            return False
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False
        if self.grid[y][x] != "":
            return False
        self.grid[y][x] = symbol
        self.moves += 1
        win, line = self.check_win(x, y, symbol)
        if win:
            self.winner = symbol
            self.win_line = line
        else:
            self.turn = "O" if self.turn == "X" else "X"
        return True

    def check_win(self, x: int, y: int, symbol: str):
        # Trả về (True, danh_sách_tọa_độ) nếu thắng; ngược lại (False, None)
        dirs = [(1, 0), (0, 1), (1, 1), (1, -1)]
        for dx, dy in dirs:
            coords = [(x, y)]
            # + hướng
            nx, ny = x, y
            while True:
                nx += dx; ny += dy
                if 0 <= nx < self.size and 0 <= ny < self.size and self.grid[ny][nx] == symbol:
                    coords.append((nx, ny))
                else:
                    break
            # - hướng
            nx, ny = x, y
            while True:
                nx -= dx; ny -= dy
                if 0 <= nx < self.size and 0 <= ny < self.size and self.grid[ny][nx] == symbol:
                    coords.insert(0, (nx, ny))
                else:
                    break
            if len(coords) >= self.win_len:
                return True, coords
        return False, None

    def is_draw(self) -> bool:
        return self.moves >= self.size * self.size and self.winner is None

    def to_list(self):
        return [row[:] for row in self.grid]
