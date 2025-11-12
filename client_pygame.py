import sys, socket, threading, json, pygame, os, string

HOST = "127.0.0.1"; PORT = 5000
if len(sys.argv)>=2: HOST = sys.argv[1]
if len(sys.argv)>=3: PORT = int(sys.argv[2])

SIZE=15; CELL=36; MARGIN=24
W=MARGIN*2+CELL*SIZE; H=MARGIN*2+CELL*SIZE+56
FPS=60

pygame.init()
screen=pygame.display.set_mode((W,H)); pygame.display.set_caption("Caro LAN Client")
clock=pygame.time.Clock()

# resend queue every 2s until matched
QUEUE_TICK = pygame.USEREVENT + 1
QUEUE_INTERVAL_MS = 2000

def load_vn_font(size: int):
    for ttf in ["NotoSans-SemiBold.ttf","NotoSans-Regular.ttf","DejaVuSans.ttf","Roboto-Regular.ttf"]:
        p = os.path.join(os.path.dirname(__file__), ttf)
        if os.path.exists(p):
            return pygame.font.Font(p, size)
    candidates = ["segoeui","arial","tahoma","dejavusans","notosans","roboto","arialunicodems"]
    path = pygame.font.match_font(candidates)
    if path: return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size)

font = load_vn_font(20); small = load_vn_font(14); tiny = load_vn_font(13)

BG=(18,48,58); PANEL=(22,62,72); GRID=(70,130,140); GRID5=(120,180,190)
BORDER=(36,96,106); XCOL=(235,240,240); OCOL=(235,85,85); WINCOL=(255,210,64)
BAR=(0,0,0); TXT=(245,245,245); MUTED=(165,170,180); BAR_H=56

class Net:
    def __init__(self, onmsg):
        self.onmsg=onmsg; self.sock=None; self.buf=""; self.connected=False; self.err=""; self.lock=threading.Lock()
    def connect(self, host, port):
        self.close()
        try:
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect((host,port))
            self.sock=s; self.connected=True; threading.Thread(target=self.reader, daemon=True).start()
            return True
        except Exception as e:
            self.err=str(e); self.connected=False; return False
    def reader(self):
        try:
            while self.connected and self.sock:
                data=self.sock.recv(4096)
                if not data: break
                self.buf+=data.decode("utf-8")
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

class State:
    def __init__(self):
        self.grid=[["" for _ in range(SIZE)] for _ in range(SIZE)]
        self.turn="X"; self.me="?"; self.winner=None; self.draw=False
        self.win_line=None; self.room="?"
        self.in_queue=False
        self.status="Nhấn C để kết nối (tự xếp hàng ghép cặp). N: Ván mới • Esc: Thoát"

    def _update_turn_status(self):
        if self.winner or self.draw: return
        self.status = "Đến lượt bạn" if self.me == self.turn else "Chưa đến lượt bạn"

    def apply(self, m):
        t = m.get("type")

        if t == "welcome":
            self.me   = m.get("symbol","?")
            self.room = m.get("room","?")
            self.in_queue = False
            pygame.time.set_timer(QUEUE_TICK, 0)  # stop auto-join
            self.status = f"Đã vào phòng '{self.room}'. Bạn là {self.me}"
            net.send({"type":"sync"})

        elif t == "start":
            self.grid = m.get("board", self.grid)
            self.turn = m.get("turn",  self.turn)
            self.winner=None; self.draw=False; self.win_line=None
            self._update_turn_status()

        elif t == "update":
            self.grid   = m.get("board", self.grid)
            self.turn   = m.get("turn",  self.turn)
            self.winner = m.get("winner")
            self.draw   = m.get("draw", False)
            self.win_line = m.get("win_line")
            if not (self.winner or self.draw):
                self._update_turn_status()

        elif t == "end":
            self.status = m.get("message","Kết thúc ván")
            if m.get("win_line") is not None:
                self.win_line = m.get("win_line")

        elif t in ("info","error"):
            msg = m.get("message","")
            if msg: self.status = msg

st = State()
net = Net(lambda m: st.apply(m))

def draw_board(st):
    panel = pygame.Rect(MARGIN-8, MARGIN-8, CELL*SIZE+16, CELL*SIZE+16)
    pygame.draw.rect(screen, PANEL, panel, border_radius=14)

    board_rect = pygame.Rect(MARGIN, MARGIN, CELL*SIZE, CELL*SIZE)
    pygame.draw.rect(screen, BORDER, board_rect, width=2, border_radius=10)

    for i in range(1, SIZE):
        x = MARGIN + i*CELL; y = MARGIN + i*CELL
        col = GRID5 if i % 5 == 0 else GRID
        pygame.draw.aaline(screen, col, (x,MARGIN), (x,MARGIN+CELL*SIZE))
        pygame.draw.aaline(screen, col, (MARGIN,y), (MARGIN+CELL*SIZE,y))

    for y in range(SIZE):
        for x in range(SIZE):
            v=st.grid[y][x]
            if not v: continue
            cx=MARGIN+x*CELL+CELL//2; cy=MARGIN+y*CELL+CELL//2
            if v=="X":
                s=CELL//2-6
                pygame.draw.line(screen,XCOL,(cx-s,cy-s),(cx+s,cy+s),5)
                pygame.draw.line(screen,XCOL,(cx-s,cy+s),(cx+s,cy-s),5)
            else:
                r=CELL//2-6; pygame.draw.circle(screen,OCOL,(cx,cy),r,5)

    if st.win_line and len(st.win_line) >= 2:
        (sx,sy) = st.win_line[0]; (ex,ey) = st.win_line[-1]
        sx = MARGIN + sx*CELL + CELL//2; sy = MARGIN + sy*CELL + CELL//2
        ex = MARGIN + ex*CELL + CELL//2; ey = MARGIN + ey*CELL + CELL//2
        pygame.draw.line(screen, WINCOL, (sx,sy), (ex,ey), 7)

def draw_status(st, net):
    bar = pygame.Rect(0, H - BAR_H, W, BAR_H)
    pygame.draw.rect(screen, BAR, bar)

    info = f"{'ON' if net.connected else 'OFF'} • Bạn: {st.me} • Lượt: {st.turn} • Phòng: {st.room}"
    screen.blit(small.render(info, True, TXT), (12, H - BAR_H + 8))

    screen.blit(small.render(st.status, True, TXT), (12, H - BAR_H + 28))


def main():
    running=True
    while running:
        for e in pygame.event.get():
            if e.type==pygame.QUIT:
                running=False

            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE:
                    running=False
                elif e.key==pygame.K_c:
                    if not net.connected:
                        ok=net.connect(HOST,PORT)
                        if ok:
                            st.status="Đã kết nối • Đang xếp hàng ghép cặp..."
                            st.in_queue=True
                            net.send({"type":"queue","action":"join"})
                            pygame.time.set_timer(QUEUE_TICK, QUEUE_INTERVAL_MS)
                        else:
                            st.status=f"Lỗi: {net.err}"
                    else:
                        net.close()
                        st.status="Đã ngắt kết nối"; st.room="?"; st.in_queue=False
                        pygame.time.set_timer(QUEUE_TICK, 0)
                elif e.key==pygame.K_n and net.connected:
                    net.send({"type":"reset"})

            elif e.type == QUEUE_TICK:
                if st.in_queue and net.connected and st.room in ("?","",None):
                    net.send({"type":"queue","action":"join"})

            elif e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                board_rect = pygame.Rect(MARGIN, MARGIN, CELL*SIZE, CELL*SIZE)
                if board_rect.collidepoint(e.pos) and net.connected and not st.winner and not st.draw:
                    if st.me!=st.turn:
                        st.status="Chưa đến lượt bạn"
                    else:
                        gx=(e.pos[0]-MARGIN)//CELL; gy=(e.pos[1]-MARGIN)//CELL
                        if 0<=gx<SIZE and 0<=gy<SIZE and st.grid[gy][gx]=="":
                            net.send({"type":"move","x":int(gx),"y":int(gy)})
                        else:
                            st.status="Ô đã có quân"

        screen.fill(BG)
        draw_board(st)
        draw_status(st,net)
        pygame.display.flip(); clock.tick(FPS)

    net.close(); pygame.quit(); sys.exit()

if __name__=="__main__":
    main()
