import sys, socket, threading, json, pygame, os, time

HOST = "127.0.0.1"; PORT = 5000
if len(sys.argv) >= 2: HOST = sys.argv[1]
if len(sys.argv) >= 3: PORT = int(sys.argv[2])

SIZE = 15
CELL = 36
GAP  = 16
LEFT = GAP; TOP = GAP

BOARD_W = CELL * SIZE
BOARD_H = CELL * SIZE
RIGHT_COL_W = 280
TIMER_H = 60
BOTTOM_H = 84

W = LEFT + BOARD_W + GAP + RIGHT_COL_W + GAP
H = TOP  + BOARD_H + GAP + BOTTOM_H + GAP
FPS = 60

pygame.init()
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Caro LAN Client")
clock = pygame.time.Clock()

def load_vn_font(size: int):
    for ttf in ["NotoSans-SemiBold.ttf","NotoSans-Regular.ttf","DejaVuSans.ttf","Roboto-Regular.ttf"]:
        p = os.path.join(os.path.dirname(__file__), ttf)
        if os.path.exists(p): return pygame.font.Font(p, size)
    path = pygame.font.match_font(["segoeui","arial","tahoma","dejavusans","notosans","roboto"])
    if path: return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size)

font  = load_vn_font(20)
small = load_vn_font(16)

BG=(12,22,32)
PANEL=(20,34,46)
GRID=(80,115,125)
GRID5=(120,170,180)
BORDER=(48,120,130)
XCOL=(240,240,240); OCOL=(235,85,85); WINCOL=(255,210,64)
TXT=(240,240,245); MUTED=(170,175,185)
BTN_BORDER=(90,140,160)

DIV1 = pygame.Rect(LEFT, TOP, BOARD_W, BOARD_H)
DIV5 = pygame.Rect(DIV1.right + GAP, TOP, RIGHT_COL_W, TIMER_H)
DIV6 = pygame.Rect(DIV1.right + GAP, DIV5.bottom + GAP, RIGHT_COL_W,
                   BOARD_H - TIMER_H - GAP)
DIV2 = pygame.Rect(LEFT, DIV1.bottom + GAP, (BOARD_W - 2*GAP)//3, BOTTOM_H)
DIV3 = pygame.Rect(DIV2.right + GAP, DIV2.top, (BOARD_W - 2*GAP)//3, BOTTOM_H)
DIV4 = pygame.Rect(DIV3.right + GAP, DIV2.top, (BOARD_W - 2*GAP)//3, BOTTOM_H)

QUEUE_TICK = pygame.USEREVENT + 1
HEARTBEAT_TICK = pygame.USEREVENT + 2
QUEUE_INTERVAL_MS = 2000
HEARTBEAT_INTERVAL_MS = 5000  # 5s ping server

class Net:
    def __init__(self, onmsg):
        self.onmsg=onmsg; self.sock=None; self.buf=""; self.connected=False; self.err=""; self.lock=threading.Lock()
    def connect(self, host, port):
        self.close()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            self.sock = s
            self.connected = True
            threading.Thread(target=self.reader, daemon=True).start()
            return True
        except Exception as e:
            self.err = f"Không kết nối được: {e}"
            self.connected = False
            return False
    def reader(self):
        try:
            while self.connected and self.sock:
                data=self.sock.recv(4096)
                if not data: break
                self.buf += data.decode("utf-8")
                while "\n" in self.buf:
                    line, self.buf = self.buf.split("\n",1)
                    line=line.strip()
                    if not line: continue
                    try: self.onmsg(json.loads(line))
                    except: pass
        except Exception as e:
            self.err=str(e)
        self.connected=False; self.close()
    def send(self, obj):
        if not(self.connected and self.sock): return
        try:
            data=(json.dumps(obj)+"\n").encode("utf-8")
            with self.lock: self.sock.sendall(data)
        except Exception as e:
            self.err=str(e); self.connected=False; self.close()
    def close(self):
        try:
            if self.sock: self.sock.close()
        except: pass
        self.sock=None; self.connected=False
    def start_heartbeat(self):
        if self.connected: pygame.time.set_timer(HEARTBEAT_TICK, HEARTBEAT_INTERVAL_MS)
    def stop_heartbeat(self):
        pygame.time.set_timer(HEARTBEAT_TICK, 0)

class State:
    def __init__(self):
        self.grid=[["" for _ in range(SIZE)] for _ in range(SIZE)]
        self.turn="X"; self.me="?"; self.winner=None; self.draw=False
        self.win_line=None; self.room="?"; self.in_queue=False
        self.status="Nhấn Kết nối để vào hàng đợi."
        self.deadline=None; self.turn_seconds=30
    def _update_turn_status(self):
        if self.winner or self.draw: return
        self.status = "Đến lượt bạn" if self.me==self.turn else "Chưa đến lượt bạn"
    def apply(self, m):
        t=m.get("type")
        if t=="welcome":
            self.me=m.get("symbol","?"); self.room=m.get("room","?"); self.in_queue=False
            pygame.time.set_timer(QUEUE_TICK,0)
            self.status=f"Đã vào phòng {self.room}. Bạn là {self.me}"
            net.send({"type":"sync"})
        elif t=="start":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=None; self.draw=False; self.win_line=None
            self.deadline=m.get("deadline"); self.turn_seconds=m.get("turn_seconds",30)
            self._update_turn_status()
        elif t=="update":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=m.get("winner"); self.draw=m.get("draw",False)
            self.win_line=m.get("win_line"); self.deadline=m.get("deadline",self.deadline)
            self.turn_seconds=m.get("turn_seconds",self.turn_seconds)
            if not(self.winner or self.draw): self._update_turn_status()
        elif t=="end":
            self.status=m.get("message","Kết thúc ván")
            if m.get("win_line") is not None: self.win_line=m.get("win_line")
        elif t in ("info","error"):
            msg=m.get("message","")
            if msg: self.status=msg
        elif t=="assign":
            self.me = m.get("symbol","?")
            self.status = f"Bạn là {self.me}"
            your_turn = m.get("your_turn", False)
            if your_turn:
                self.status += " • Đến lượt bạn"
            else:
                self.status += " • Chưa đến lượt bạn"
        elif t=="info":
            msg=m.get("message","")
            if msg:
                self.status=msg
                if "đang chờ người chơi khác" in msg.lower():
                    self.winner=None
                    self.draw=False


st=State()
net=Net(lambda m: st.apply(m))
def join_queue():
    if net.connected:
        st.in_queue = True
        st.room = "?"
        st.status = "Đang xếp hàng ghép cặp..."
        net.send({"type": "queue", "action": "join", "name": "player"})
        pygame.time.set_timer(QUEUE_TICK, QUEUE_INTERVAL_MS)

def leave_queue():
    if net.connected:
        st.in_queue = False
        st.room = "?"
        net.send({"type": "queue", "action": "leave"})
        pygame.time.set_timer(QUEUE_TICK, 0)

def draw_frame(rect):
    pygame.draw.rect(screen, PANEL, rect, border_radius=0)
    pygame.draw.rect(screen, BTN_BORDER, rect, 2, border_radius=0)

def pill_bar(surf, rect, ratio, bg_col, fill_col):
    pygame.draw.rect(surf, bg_col, rect, border_radius=rect.height//2)
    ratio=max(0.0, min(1.0, ratio))
    if ratio<=0: return
    fill_w=max(1, int(rect.width*ratio))
    tmp=pygame.Surface((fill_w, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(tmp, fill_col, tmp.get_rect(), border_radius=rect.height//2)
    surf.blit(tmp, (rect.x, rect.y))

def draw_board(st):
    draw_frame(DIV1)
    inner = DIV1.inflate(-12, -12)
    pygame.draw.rect(screen, BORDER, inner, 2, border_radius=0)

    grid_rect = inner.inflate(-10, -10)
    grid_rect.width  = CELL * SIZE
    grid_rect.height = CELL * SIZE
    grid_rect.x = inner.x + (inner.width  - grid_rect.width) // 2
    grid_rect.y = inner.y + (inner.height - grid_rect.height) // 2

    gx0, gy0 = grid_rect.x, grid_rect.y
    
    for i in range(SIZE + 1):
        x = gx0 + i*CELL
        y = gy0 + i*CELL
        col = GRID5 if i%5==0 else GRID
        if i <= SIZE:
            pygame.draw.aaline(screen, col, (x, gy0), (x, gy0 + SIZE * CELL))
        if i <= SIZE:
            pygame.draw.aaline(screen, col, (gx0, y), (gx0 + SIZE * CELL, y))

    old_clip = screen.get_clip()
    screen.set_clip(grid_rect.inflate(-2, -2))

    for y in range(SIZE):
        for x in range(SIZE):
            v = st.grid[y][x]
            if not v: continue
            cx = gx0 + x*CELL + CELL//2
            cy = gy0 + y*CELL + CELL//2
            if v == "X":
                s = CELL//2 - 6
                pygame.draw.line(screen, XCOL, (cx-s, cy-s), (cx+s, cy+s), 5)
                pygame.draw.line(screen, XCOL, (cx-s, cy+s), (cx+s, cy-s), 5)
            else:
                r = CELL//2 - 6
                pygame.draw.circle(screen, OCOL, (cx, cy), r, 5)

    if st.win_line and len(st.win_line) >= 2:
        (sx,sy) = st.win_line[0]; (ex,ey) = st.win_line[-1]
        sx = gx0 + sx*CELL + CELL//2; sy = gy0 + sy*CELL + CELL//2
        ex = gx0 + ex*CELL + CELL//2; ey = gy0 + ey*CELL + CELL//2
        pygame.draw.line(screen, WINCOL, (sx,sy), (ex,ey), 7)

    screen.set_clip(old_clip)

def draw_button(rect, text, enabled=True):
    pygame.draw.rect(screen, PANEL, rect, border_radius=12)
    pygame.draw.rect(screen, BTN_BORDER, rect, 2, border_radius=12)
    label = font.render(text, True, (255,255,255) if enabled else MUTED)
    screen.blit(label, label.get_rect(center=rect.center))

def draw_bottom_controls():
    if not net.connected:
        text_connect, en = "Kết nối", True
    else:
        if st.in_queue or not st.deadline:
            text_connect = "Đang tìm ..."
        else:
            text_connect = "Đã vào phòng"
        en = False  
    draw_button(DIV2, text_connect, enabled=en)

    # Nút ván mới
    can_reset = net.connected and (st.winner or st.draw or len(st.grid)>0)
    draw_button(DIV3, "Ván mới", enabled=can_reset)

    # Nút hủy kết nối
    draw_button(DIV4, "Hủy kết nối", enabled=net.connected)


def draw_timer(st):
    draw_frame(DIV5)
    inner = DIV5.inflate(-12, -12)
    if st.winner or st.draw:
        ratio = 0.0
        text = f"Ván đã kết thúc • {st.winner} thắng!" if st.winner else "Ván hòa!"
    elif st.deadline:
        remain = max(0.0, st.deadline - time.time())
        ratio  = min(1.0, remain / max(1, st.turn_seconds))
        text   = f"Lượt: {st.turn}  •  {int(remain)}s"
    else:
        ratio = 0.0
        text = "Lượt: —  •  —s"
    bar_h = 16
    bar_rect = pygame.Rect(inner.x, inner.centery - bar_h//2, inner.width, bar_h)
    bg_col = (28,48,64)
    fill_col = (60,160,100) if st.me==st.turn else (150,120,60)
    pill_bar(screen, bar_rect, ratio, bg_col, fill_col)
    label = small.render(text, True, (255,255,255))
    screen.blit(label, label.get_rect(center=(bar_rect.centerx, bar_rect.top - 12)))

def wrap_text(text, font, max_width):
    words = text.split(" "); lines = []; cur = ""
    for w in words:
        test = w if cur=="" else cur+" "+w
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            if cur: lines.append(cur)
            if font.size(w)[0] <= max_width:
                cur = w
            else:
                cut = ""
                for ch in w:
                    if font.size(cut+ch)[0] <= max_width: cut += ch
                    else:
                        if cut: lines.append(cut); cut = ch
                cur = cut
    if cur: lines.append(cur)
    return lines

def draw_info(st):
    draw_frame(DIV6)
    info = [
        f"Trạng thái mạng: {'ON' if net.connected else 'OFF'}",
        f"Bạn: {st.me}   •   Lượt: {st.turn}",
        f"Phòng: {st.room}",
        ""
    ]
    maxw = DIV6.width - 28
    wrapped = []
    for para in str(st.status).split("\n"):
        wrapped += wrap_text(para, small, maxw) if para else [""]
    lines = info + wrapped
    x, y = DIV6.x + 14, DIV6.y + 12
    for line in lines:
        screen.blit(small.render(line, True, TXT), (x, y))
        y += 22

def board_cell_from_pos(pos):
    inner = DIV1.inflate(-12, -12)
    grid_rect = inner.inflate(-10, -10)
    grid_rect.width  = CELL * SIZE
    grid_rect.height = CELL * SIZE
    grid_rect.x = inner.x + (inner.width  - grid_rect.width) // 2
    grid_rect.y = inner.y + (inner.height - grid_rect.height) // 2
    if not grid_rect.collidepoint(pos): 
        return None
    gx = (pos[0] - grid_rect.x) // CELL
    gy = (pos[1] - grid_rect.y) // CELL
    if 0 <= gx < SIZE and 0 <= gy < SIZE: 
        return int(gx), int(gy)
    return None

def main():
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_c:
                    if not net.connected:
                        if net.connect(HOST, PORT):
                            st.status="Đã kết nối • Đang xếp hàng ghép cặp..."
                            join_queue()

                        else:
                            print(f"[DEBUG] Kết nối thất bại: {net.err}") 
                            st.status = "Oops! Không kết nối được với máy chủ. Vui lòng thử lại sau."

                elif e.key == pygame.K_n and net.connected:
                    net.send({"type":"reset"})
            elif e.type == QUEUE_TICK:
                if st.in_queue and net.connected and st.room in ("?","",None):
                    net.send({"type":"queue","action":"join","name":"player"})
            elif e.type == HEARTBEAT_TICK:
                if net.connected:
                    try: net.send({"type":"ping"})
                    except: st.status="Mất kết nối với máy chủ rồi :(("; net.connected=False; st.in_queue=False; st.room="?"; net.stop_heartbeat()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                # giữ nguyên logic click
                cell = board_cell_from_pos(e.pos)
                if cell and net.connected and not st.winner and not st.draw:
                    if st.me != st.turn:
                        st.status = "Chưa đến lượt bạn"
                    else:
                        x,y = cell
                        if st.grid[y][x] == "":
                            net.send({"type":"move","x":x,"y":y})
                        else:
                            st.status = "Ô đã có quân"
                if DIV2.collidepoint(e.pos):
                    if not net.connected:
                        if net.connect(HOST, PORT):
                            st.status="Đã kết nối • Đang xếp hàng ghép cặp..."
                            join_queue()
                            net.start_heartbeat()
                        else:
                            st.status=f"Lỗi: {net.err}"
                elif DIV3.collidepoint(e.pos):
                    if net.connected:
                        leave_queue()
                        net.send({"type":"reset"})
                        join_queue()
                elif DIV4.collidepoint(e.pos):
                        leave_queue()
                        net.close()
                        st.status="Đã ngắt kết nối"
                        net.stop_heartbeat()

        screen.fill(BG)
        draw_board(st)
        draw_timer(st)
        draw_info(st)
        draw_bottom_controls()
        pygame.display.flip()
        clock.tick(FPS)

    net.close(); pygame.quit(); sys.exit()

if __name__ == "__main__":
    main()
