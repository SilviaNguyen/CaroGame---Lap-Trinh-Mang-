import sys, os, socket, threading
 si/undo-contract
from typing import Optional, Tuple, List

from typing import Optional, Tuple
 main
import pygame
 integration
import json
import time

from board import Board  
 main

# ===================== Font helper (Unicode VN) =====================
def _resolve_vn_font() -> Optional[str]:
    pygame.font.init()
    names = ["segoe ui","arial unicode ms","tahoma","roboto","noto sans","dejavu sans","liberation sans"]
    for n in names:
        p = pygame.font.match_font(n)
        if p: return p
    common = [
        r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\Tahoma.ttf", r"C:\Windows\Fonts\arialuni.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for p in common:
        if os.path.exists(p): return p
    return None

 si/undo-contract
# ===================== Game logic (5-in-a-row) =====================
class Move:
    x: int
    y: int
    player: str

class Board:
    def __init__(self, size: int = 15, win_len: int = 5):
        if size < 3 or win_len < 3: raise ValueError("Invalid board parameters")
        self.size=size; self.win_len=win_len
        self.grid=[["" for _ in range(size)] for _ in range(size)]
        self.turn="X"; self.moves: List[Move]=[]; self.winner: Optional[str]=None; self.win_line=None

    def in_bounds(self,x,y): return 0<=x<self.size and 0<=y<self.size

    def place(self,x,y):
        if not self.in_bounds(x,y) or self.grid[y][x] or self.winner: return False
        self.grid[y][x]=self.turn; self.moves.append(Move(x,y,self.turn))
        win, line = self._check_win_with_line(x,y)
        if win: self.winner=self.turn; self.win_line=line
        else: self.turn="O" if self.turn=="X" else "X"
        return True

    def _line_dir(self,x,y,dx,dy):
        me=self.grid[y][x]; pts=[(x,y)]
        cx,cy=x+dx,y+dy
        while 0<=cx<self.size and 0<=cy<self.size and self.grid[cy][cx]==me:
            pts.append((cx,cy)); cx+=dx; cy+=dy
        cx,cy=x-dx,y-dy
        while 0<=cx<self.size and 0<=cy<self.size and self.grid[cy][cx]==me:
            pts.insert(0,(cx,cy)); cx-=dx; cy-=dy
        return pts

    def _check_win_with_line(self,x,y):
        for dx,dy in [(1,0),(0,1),(1,1),(1,-1)]:
            pts=self._line_dir(x,y,dx,dy)
            if len(pts)>=self.win_len: return True, pts[:self.win_len]
        return False, None

    def undo(self):
        if not self.moves or self.winner: return False
        last=self.moves.pop(); self.grid[last.y][last.x]=""; self.winner=None; self.win_line=None; self.turn=last.player; return True

    def reset(self):
        self.grid=[["" for _ in range(self.size)] for _ in range(self.size)]
        self.turn="X"; self.moves.clear(); self.winner=None; self.win_line=None

# ===================== Network (optional) =====================

# ===================== Network (client TCP, dòng-kết-thúc bằng '\n') =====================
 main
class NetClient:
    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.on_message = None
        self.alive = False

    def connect(self, host: str, port: int):
        self.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect((host, port))
        self.alive = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        buf = b""
        try:
            while self.alive and self.sock:
                data = self.sock.recv(1024)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if self.on_message:
                        try:
                            self.on_message(line.decode("utf-8", "ignore").strip())
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            self.alive = False
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
            self.sock = None

    def send_line(self, text: str):
        if not self.sock:
            return
        try:
            self.sock.sendall((text + "\n").encode("utf-8"))
        except Exception:
            self.close()

    def close(self):
        self.alive = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

# ===================== Palette (màu) =====================
PAL = {
    "BG_TOP": (6, 54, 78),
    "BG_BOTTOM": (10, 88, 120),
    "BOARD_CARD": (14, 116, 144),
    "BOARD_EDGE": (236, 253, 245),
    "GRID_LINE": (210, 236, 245),
    "X": (163, 226, 233),
    "O": (240, 83, 64),
    "TXT_LIGHT": (245, 251, 255),
    "TXT_DARK": (31, 41, 55),
    "MUTED_DARK": (82, 92, 105),
    "SIDEBAR_BG": (255, 255, 255),
    "BTN": (16, 185, 129),
    "BTN_HOVER": (5, 150, 105),
    "BTN_TEXT": (255, 255, 255),
    "LAST_GLOW": (255, 255, 255, 90),
    "WIN": (34, 197, 94),
    "SHADOW": (0, 0, 0, 110),
}

# ===================== Helpers vẽ =====================
def lerp(a,b,t): return a + (b-a)*t

def gradient_rect(surf, rect, c1, c2):
    x,y,w,h = rect
    for i in range(h):
        t = i / max(1, h-1)
        c = (int(lerp(c1[0],c2[0],t)), int(lerp(c1[1],c2[1],t)), int(lerp(c1[2],c2[2],t)))
        pygame.draw.line(surf, c, (x, y+i), (x+w, y+i))

def soft_card(surf, rect, radius=22, color=(255,255,255), shadow_rgba=(0,0,0,110), offset=(0,8), blur=16):
    sx,sy = offset
    sh = pygame.Surface((rect.w+blur*2, rect.h+blur*2), pygame.SRCALPHA)
    for i in range(blur,0,-2):
        alpha = int(shadow_rgba[3] * (i/blur))
        pygame.draw.rect(sh, (*shadow_rgba[:3], alpha),
                         pygame.Rect(i,i,rect.w+blur-i,rect.h+blur-i), border_radius=radius+3)
    surf.blit(sh,(rect.x-blur//2+sx, rect.y-blur//2+sy))
    pygame.draw.rect(surf, color, rect, border_radius=radius)

def render_text_wrapped(surf, text, font, color, rect, line_spacing=6):
    words = text.replace("\n", " \n ").split(" ")
    x,y = rect.x, rect.y; maxw=rect.w; used=0; line=""
    for w in words:
        if w == "\n":
            if line:
                img = font.render(line, True, color); surf.blit(img,(x,y))
                y += img.get_height()+line_spacing; used += img.get_height()+line_spacing; line=""
            else:
                y += font.get_height()+line_spacing; used += font.get_height()+line_spacing
            continue
        test = (line + " " + w).strip()
        tw,_ = font.size(test)
        if tw <= maxw:
            line = test
        else:
            img = font.render(line, True, color); surf.blit(img,(x,y))
            y += img.get_height()+line_spacing; used += img.get_height()+line_spacing; line=w
    if line:
        img = font.render(line, True, color); surf.blit(img,(x,y)); used += img.get_height()
    return used

class Button:
    def __init__(self, rect, text):
        self.rect=rect; self.text=text; self.hover=0.0
    def update(self, mouse):
        self.hover = lerp(self.hover, 1.0 if self.rect.collidepoint(mouse) else 0.0, 0.25)
    def draw(self, surf, font):
        color = PAL["BTN_HOVER"] if self.hover>0.5 else PAL["BTN"]
        soft_card(surf, self.rect, 14, color, (0,0,0,80), (0,6), 12)
        t = font.render(self.text, True, PAL["BTN_TEXT"])
        surf.blit(t, t.get_rect(center=self.rect.center))

# ===================== App =====================
class CaroApp:
    def __init__(self, size=15, win_len=5):
        pygame.init()
        self.board = Board(size, win_len)
        self.cell  = 40
        self.margin = 40
        self.sidebar_w = 320
        self.toolbar_h = 96

        board_w = 2*self.margin + size*self.cell
        board_h = 2*self.margin + size*self.cell
        width  = board_w + self.sidebar_w + 60
        height = board_h + self.toolbar_h + 30
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Caro LAN Client")

        fp = _resolve_vn_font()
        if fp:
 si/undo-contract
            self.font = pygame.font.Font(fp, 20)
            self.small= pygame.font.Font(fp, 16)
            self.big  = pygame.font.Font(fp, 34)
            self.timer_font = pygame.font.Font(fp, 28) # Font cho timer
        else:
            self.font=pygame.font.SysFont(None,20)
            self.small=pygame.font.SysFont(None,16)
            self.big=pygame.font.SysFont(None,34)
            self.timer_font = pygame.font.SysFont(None, 32)

            self.font  = pygame.font.Font(fp, 20)
            self.small = pygame.font.Font(fp, 16)
            self.big   = pygame.font.Font(fp, 34)
        else:
            self.font  = pygame.font.SysFont(None, 20)
            self.small = pygame.font.SysFont(None, 16)
            self.big   = pygame.font.SysFont(None, 34)
 main

        tb_y = 20 + board_h + (self.toolbar_h-56)//2
        self.buttons = [
            Button(pygame.Rect(self.margin, tb_y, 120, 56), "New"),
            Button(pygame.Rect(self.margin+140, tb_y, 120, 56), "Undo"),
            Button(pygame.Rect(self.margin+280, tb_y, 140, 56), "Connect"),
        ]

 si/undo-contract
        self.status = "Sẵn sàng (Local 2 người)."
        self.net = NetClient()
        self.net.on_message = self.on_message
        self.remote_enabled = False

        self.status="Sẵn sàng (Local 2 người)."
        self.net = NetClient(); self.net.on_message = self.on_message; self.remote_enabled=False
 main

        self.board_card = pygame.Rect(20, 20, board_w, board_h)
        self.sidebar    = pygame.Rect(40 + board_w, 20, self.sidebar_w, board_h)
        self.toolbar    = pygame.Rect(20, 20+board_h, width-40, self.toolbar_h)
        self.my_symbol = None

        #Xóa timer "giả"
        self.timer_duration = 0  
        self.last_move_ts = 0    
        self.time_remaining = 0  

    # --------- Network callback ----------
    def on_message(self, line: str):
integration
        try:
            data=json.loads(line)

        except json.JSONDecodeError:
            print("Dữ liệu không có trong JSON", line)
            return
        
        msg_type = data.get("type")
        if msg_type == "assign":
            self.my_symbol = data.get("symbol")
            your_turn = data.get("your_turn",False)
            if self.my_symbol:
                if your_turn:
                    self.status = f"Bạn cầm quân {self.my_symbol} và đi trước."
                else:
                    self.status = f"Bạn cầm quân {self.my_symbol}. Đang chờ đối thủ đi trước."
            elif msg_type == "state":
                # Cập nhật trạng thái bàn cờ từ server
                grid = data.get("grid",[])
                turn = data.get("turn")
                winner = data.get("winner")
                last_move = data.get("last")

                # Lấy thông tin timer "thật" từ server
                self.timer_duration = data.get("timer_duration", 0)
                self.last_move_ts = data.get("last_move_ts", 0)

                
                if grid and isinstance(grid, list) and len(grid) > 0:
                    self.board.size = len(grid)
                    self.board.grid = [row[:] for row in grid]
                    self.board.turn = turn
                    self.board.winner = winner

                # Cập nhật thông báo trạng thái
                if winner:
                    # Có người thắng hoặc hòa
                    if winner in ("X", "O"):
                        self.status = f"Ván đấu kết thúc! {winner} thắng." 
                    else: 
                        self.status = "Ván đấu hòa!"
                    self.time_remaining = 0 # Dừng timer khi có kết quả 
                else: 
                    # Sửa: Xóa logic tự reset timer
                    if self.my_symbol and self.my_symbol == turn:
                        self.status = "Đến lược bạn đi "
                    else: 
                        self.status = "Đang chờ lượt đối thủ..."
                    # Nếu có nước đi cuối cùng và không phải do mình, hiển thị tọa độ đó
                    if last_move and last_move.get("player") and last_move.get("player") != self.my_symbol:
                        lx, ly = last_move["x"], last_move["y"]
                        self.status = f"Đối thủ đi ({lx},{ly}).+ {self.status}"

            elif msg_type == "error":
                # Báo lỗi từ server
                err = data.get("message", "Đã có lỗi xảy ra")
                self.status = "Lỗi" + err

            elif msg_type == "chat":
                #Nhận tin nhắn chat
                sender = data.get("from", "")
                msg = data.get("message","")

                # Hiển thị chat
                if sender:
                    self.status = f"[Chat] {sender}:{msg}"
                else:
                    self.status = f"[Chat] {msg}"
            else:
                print("Thông điệp không xử lý:", data)

        parts = line.split()
        if not parts: return
        cmd = parts[0].upper()
        if cmd=="MOVE" and len(parts)>=3:
            try:
                x=int(parts[1]); y=int(parts[2])
                # Board.place của bạn yêu cầu symbol -> dùng lượt hiện tại
                self.board.place(x, y, self.board.turn)
                self.status=f"Đối thủ đi ({x},{y}). Lượt: {self.board.turn}"
            except Exception:
                pass
        elif cmd=="RESET":
            self.board.reset(); self.status="Bàn cờ đã reset từ xa."
        elif cmd=="UNDO":
            # Nếu board.py không hỗ trợ undo, lệnh này sẽ không làm gì
            try:
                self.board.undo()
                self.status="Đối thủ vừa Undo."
            except Exception:
                self.status="Đối thủ yêu cầu Undo (board không hỗ trợ)."
        elif cmd in ("HELLO","WELCOME"):
            self.status="Server: "+" ".join(parts[1:])
main

    # --------- Draw ----------
    def draw_bg(self):
        gradient_rect(self.screen, self.screen.get_rect(), PAL["BG_TOP"], PAL["BG_BOTTOM"])

    def draw_board(self):
        soft_card(self.screen, self.board_card, 24, PAL["BOARD_CARD"], PAL["SHADOW"], (0,10), 18)
        pygame.draw.rect(self.screen, PAL["BOARD_EDGE"], self.board_card, 4, border_radius=24)

        ox = self.board_card.x + self.margin
        oy = self.board_card.y + self.margin

        for i in range(self.board.size+1):
            x = ox + i*self.cell
            pygame.draw.line(self.screen, PAL["GRID_LINE"], (x, oy), (x, oy + self.board.size*self.cell), 1)
        for j in range(self.board.size+1):
            y = oy + j*self.cell
            pygame.draw.line(self.screen, PAL["GRID_LINE"], (ox, y), (ox + self.board.size*self.cell, y), 1)

        # last move glow (chỉ khi có lịch sử dạng list)
        last_move = None
        if hasattr(self.board, "moves"):
            mv = self.board.moves
            if isinstance(mv, list) and len(mv) > 0 and hasattr(mv[-1], "x") and hasattr(mv[-1], "y"):
                last_move = mv[-1]
        if last_move is not None:
            cx = ox + last_move.x*self.cell + self.cell//2
            cy = oy + last_move.y*self.cell + self.cell//2
            g = pygame.Surface((self.cell,self.cell), pygame.SRCALPHA)
            pygame.draw.circle(g, PAL["LAST_GLOW"], (self.cell//2,self.cell//2), self.cell//2-3)
            self.screen.blit(g, (cx-self.cell//2, cy-self.cell//2))

        # stones
        for y in range(self.board.size):
            for x in range(self.board.size):
                v = self.board.grid[y][x]
                if not v: continue
                cx = ox + x*self.cell + self.cell//2
                cy = oy + y*self.cell + self.cell//2
                if v=="X":
                    d = self.cell//2 - 8
                    pygame.draw.line(self.screen, PAL["X"], (cx-d,cy-d),(cx+d,cy+d), 10)
                    pygame.draw.line(self.screen, PAL["X"], (cx-d,cy+d),(cx+d,cy-d), 10)
                else:
                    r = self.cell//2 - 8
                    pygame.draw.circle(self.screen, PAL["O"], (cx,cy), r, 10)

        # winner line
        if getattr(self.board, "winner", None) and getattr(self.board, "win_line", None):
            (x0,y0) = self.board.win_line[0]; (x1,y1) = self.board.win_line[-1]
            start = (ox + x0*self.cell + self.cell//2, oy + y0*self.cell + self.cell//2)
            end   = (ox + x1*self.cell + self.cell//2, oy + y1*self.cell + self.cell//2)
            for w in (18,14,10):
                pygame.draw.line(self.screen, PAL["WIN"], start, end, w)

        head = self.font.render(f"Lượt: {self.board.turn}", True, PAL["TXT_LIGHT"])
        self.screen.blit(head, (self.board_card.x+18, self.board_card.y+10))

    def draw_sidebar(self):
        soft_card(self.screen, self.sidebar, 24, PAL["SIDEBAR_BG"], PAL["SHADOW"], (0,10), 18)
        pad=24; x=self.sidebar.x+pad; y=self.sidebar.y+pad
        title=self.big.render("Trạng thái", True, PAL["TXT_DARK"]); self.screen.blit(title,(x,y)); y+=title.get_height()+8
        used=render_text_wrapped(self.screen, self.status, self.font, PAL["TXT_DARK"],
                                 pygame.Rect(x,y,self.sidebar.w-2*pad, 240)); y+=used+14
        tips_title=self.font.render("Hướng dẫn", True, PAL["MUTED_DARK"]); self.screen.blit(tips_title,(x,y)); y+=tips_title.get_height()+6
        tips=("• Click chuột để đánh.\n"
              "• N: ván mới, U: Undo, C: Connect.\n"
              "• Mặc định kết nối 127.0.0.1:5000.")
        render_text_wrapped(self.screen, tips, self.small, PAL["MUTED_DARK"],
                            pygame.Rect(x,y,self.sidebar.w-2*pad, 400))

    def draw_toolbar(self, mouse_pos):
        soft_card(self.screen, self.toolbar, 20, PAL["SIDEBAR_BG"], PAL["SHADOW"], (0,8), 14)
        for b in self.buttons:
            b.update(mouse_pos); b.draw(self.screen, self.font)
        if getattr(self.board, "winner", None):
            msg=f"{self.board.winner} thắng! Chọn New để chơi lại."
            rect=pygame.Rect(self.buttons[-1].rect.right+20, self.toolbar.y+18,
                             self.toolbar.right-(self.buttons[-1].rect.right+36), 70)
            render_text_wrapped(self.screen, msg, self.big, PAL["TXT_DARK"], rect)

    def draw_all(self):
        self.draw_bg()
        self.draw_board()
        self.draw_sidebar()
        self.draw_toolbar(pygame.mouse.get_pos())
        pygame.display.flip()

    # --------- Event helpers ----------
    def grid_at(self, pos) -> Optional[Tuple[int,int]]:
        ox = self.board_card.x + self.margin
        oy = self.board_card.y + self.margin
        area = pygame.Rect(ox, oy, self.board.size*self.cell, self.board.size*self.cell)
        if not area.collidepoint(pos): return None
        gx=(pos[0]-ox)//self.cell; gy=(pos[1]-oy)//self.cell
        if 0<=gx<self.board.size and 0<=gy<self.board.size: return (int(gx), int(gy))
        return None

    def on_click(self, pos):
        for b in self.buttons:
            if b.rect.collidepoint(pos):
 si/undo-contract
                if b.text=="New": 
                    self.board.reset() 
                    self._send(json.dumps({"type":"reset"}))
                    self.status="Bắt đầu ván mới."

integration
                if b.text=="New": self.board.reset(); self._send(json.dumps({"type":"reset"})); self.status="Bắt đầu ván mới."
 main
                elif b.text=="Undo":
                    if self.board.undo(): self._send(json.dumps({"type":"undo"})); self.status="Đã Undo."
                elif b.text=="Connect": 
                    self.try_connect_dialog()
                return
        
        if self.remote_enabled and self.my_symbol:
            if self.board.winner:
                self.status = "Ván đấu đã kết thúc. Bấm 'New' để chơi lại."
                return
            if self.board.turn != self.my_symbol:
                self.status = "Chưa đến lượt của bạn!"
                return
        elif not self.remote_enabled and self.board.winner:
            self.status = "Ván đấu đã kết thúc. Bấm 'New' để chơi lại."
            return

        g=self.grid_at(pos)
        if g and self.board.place(*g):
            self.status=f"Đánh ({g[0]},{g[1]}). Lượt: {self.board.turn}"
            self._send(json.dumps({"type": "move", "x": g[0], "y": g[1]}))

                if b.text=="New":
                    self.board.reset(); self._send("RESET"); self.status="Bắt đầu ván mới."
                elif b.text=="Undo":
                    try:
                        if self.board.undo(): self._send("UNDO"); self.status="Đã Undo."
                    except Exception:
                        self.status="Yêu cầu Undo (board không hỗ trợ)."
                elif b.text=="Connect":
                    self.try_connect_dialog()
                return
        g = self.grid_at(pos)
        if g:
            # Board.place của bạn cần symbol:
            if self.board.place(g[0], g[1], self.board.turn):
                self.status=f"Đánh ({g[0]},{g[1]}). Lượt: {self.board.turn}"
                self._send(f"MOVE {g[0]} {g[1]}")
main

    def _send(self, text: str):
        if self.remote_enabled:
            self.net.send_line(text)

    def try_connect_dialog(self):
        host="127.0.0.1"; port=5000
        try:
 integration
            self.net.connect(host,port)
            self.remote_enabled=True
            player_name = "player"
            join_msg = {"type":"join","name": player_name, "room": "default"}
            self.net.send_line(json.dumps(join_msg))
            self.status=f"Đã kết nối {host}:{port}. Đang chờ ghép phòng..."; 

            self.net.connect(host, port)
            self.remote_enabled=True
            self.status=f"Đã kết nối {host}:{port}"
            self._send("HELLO client")
 main
        except Exception as e:
            self.remote_enabled=False
            self.status=f"Không thể kết nối: {e}"

    # --------- Run loop ----------
    def run(self):
        clock = pygame.time.Clock()
        while True:

            # ===== Sửa: Tính toán timer "thật" =====
            if (self.remote_enabled and 
                self.timer_duration > 0 and 
                self.last_move_ts > 0 and 
                not self.board.winner):
                
                # Tính toán dựa trên thời gian hiện tại và timestamp từ server
                elapsed = time.time() - self.last_move_ts
                self.time_remaining = max(0, self.timer_duration - elapsed)
            else:
                self.time_remaining = 0 # Không có timer

            # Xử lý input    
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
 si/undo-contract
                    self.net.close()
                    pygame.quit()
                    sys.exit(0)
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.on_click(ev.pos)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_n: 
                        self.board.reset()
                        self._send(json.dumps({"type": "reset"}))
                        self.status = "Bắt đầu ván mới."
                    elif ev.key == pygame.K_u:
                        if self.board.undo(): 
                            self._send("UNDO")
                    elif ev.key == pygame.K_c: 
                        self.try_connect_dialog()

            self.draw_all() 

                    self.net.close(); pygame.quit(); sys.exit(0)
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.on_click(ev.pos)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_n:
                        self.board.reset(); self._send("RESET")
                    elif ev.key == pygame.K_u:
                        try:
                            if self.board.undo(): self._send("UNDO")
                        except Exception:
                            pass
                    elif ev.key == pygame.K_c:
                        self.try_connect_dialog()
            self.draw_all()
 main
            clock.tick(60)

if __name__ == "__main__":
    print("RUNNING:", __file__)
    app = CaroApp(size=15, win_len=5)
    app.run()
