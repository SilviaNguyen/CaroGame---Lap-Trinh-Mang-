import sys, socket, threading, json, pygame, os

HOST = "127.0.0.1"; PORT = 5000
if len(sys.argv)>=2: HOST = sys.argv[1]
if len(sys.argv)>=3: PORT = int(sys.argv[2])
ROOM = "lobby1"
if len(sys.argv)>=4: ROOM = sys.argv[3]

SIZE=15; CELL=36; MARGIN=24
W=MARGIN*2+CELL*SIZE; H=MARGIN*2+CELL*SIZE+52  # bar thấp
FPS=60

pygame.init()
screen=pygame.display.set_mode((W,H)); pygame.display.set_caption("Caro LAN Client")
clock=pygame.time.Clock()

# ---------- Font Unicode đẹp ----------
def load_vn_font(size: int):
    for ttf in ["NotoSans-SemiBold.ttf","NotoSans-Regular.ttf","DejaVuSans.ttf","Roboto-Regular.ttf"]:
        p = os.path.join(os.path.dirname(__file__), ttf)
        if os.path.exists(p):
            return pygame.font.Font(p, size)
    candidates = ["segoeui","arial","tahoma","dejavusans","notosans","roboto","arialunicodems"]
    path = pygame.font.match_font(candidates)
    if path: return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size)

font = load_vn_font(20)
small = load_vn_font(14)

# ---------- Palette ----------
BG=(18,48,58)
PANEL=(22,62,72)
GRID=(70,130,140)
GRID5=(120,180,190)
BORDER=(36,96,106)
XCOL=(235,240,240)
OCOL=(235,85,85)
WINCOL=(255,210,64)

BAR=(0,0,0)      # status bar nền đen
TXT=(245,245,245)
MUTED=(165,170,180)
BAR_H=52

class Net:
    def __init__(self, onmsg):
        self.onmsg=onmsg; self.sock=None; self.buf=""; self.connected=False; self.err=""; self.lock=threading.Lock()
    def connect(self, host, port):
        self.close()
        try:
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect((host,port))
            self.sock=s; self.connected=True; threading.Thread(target=self.reader, daemon=True).start()
            self.send({"type":"join","room":ROOM})
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
        self.win_line=None
        self.status=f"Nhấn C để kết nối • ROOM={ROOM}"

    def _update_turn_status(self):
        if self.winner or self.draw: return
        self.status = "Đến lượt bạn" if self.me == self.turn else "Chưa đến lượt bạn"

    def apply(self, m):
        t=m.get("type")
        if t=="welcome":
            self.me=m.get("symbol","?"); self.status=f"Đã vào phòng '{m.get('room','?')}'. Bạn là {self.me}"
            net.send({"type":"sync"})
        elif t=="start":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=None; self.draw=False; self.win_line=None
            self._update_turn_status()
        elif t=="update":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=m.get("winner"); self.draw=m.get("draw",False)
            self.win_line=m.get("win_line")
            if not (self.winner or self.draw):
                self._update_turn_status()
        elif t=="end":
            self.status=m.get("message","Kết thúc ván")
            if m.get("win_line") is not None:
                self.win_line = m.get("win_line")
        elif t in ("info","error"):
            self.status=m.get("message","")

st = State()
net = Net(lambda m: st.apply(m))

def draw_board(st):
    # panel bo góc
    panel = pygame.Rect(MARGIN-8, MARGIN-8, CELL*SIZE+16, CELL*SIZE+16)
    pygame.draw.rect(screen, PANEL, panel, border_radius=14)

    # khung bàn
    board_rect = pygame.Rect(MARGIN, MARGIN, CELL*SIZE, CELL*SIZE)
    pygame.draw.rect(screen, BORDER, board_rect, width=2, border_radius=10)

    # lưới mịn; đậm mỗi 5 ô
    for i in range(1, SIZE):
        x = MARGIN + i*CELL
        y = MARGIN + i*CELL
        col = GRID5 if i % 5 == 0 else GRID
        pygame.draw.aaline(screen, col, (x,MARGIN), (x,MARGIN+CELL*SIZE))
        pygame.draw.aaline(screen, col, (MARGIN,y), (MARGIN+CELL*SIZE,y))

    # quân cờ
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

    # đường thắng
    if st.win_line and len(st.win_line) >= 2:
        (sx,sy) = st.win_line[0]
        (ex,ey) = st.win_line[-1]
        sx = MARGIN + sx*CELL + CELL//2
        sy = MARGIN + sy*CELL + CELL//2
        ex = MARGIN + ex*CELL + CELL//2
        ey = MARGIN + ey*CELL + CELL//2
        pygame.draw.line(screen, WINCOL, (sx,sy), (ex,ey), 7)

def draw_status(st, net):
    bar=pygame.Rect(0, H-BAR_H, W, BAR_H)
    pygame.draw.rect(screen, BAR, bar)
    left=f"{'ON' if net.connected else 'OFF'} • Bạn: {st.me} • Lượt: {st.turn} • Phòng: {ROOM}"
    right=st.status
    screen.blit(small.render(left,True,TXT),(12, H-BAR_H+10))
    screen.blit(small.render(right,True,TXT),(12, H-BAR_H+28))
    tips="C: Kết nối/Ngắt   N: Ván mới   Esc: Thoát"
    w=small.size(tips)[0]
    screen.blit(small.render(tips,True,MUTED),(W-w-12, H-BAR_H+28))

def main():
    running=True
    while running:
        for e in pygame.event.get():
            if e.type==pygame.QUIT: running=False
            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE: running=False
                elif e.key==pygame.K_c:
                    if not net.connected:
                        ok=net.connect(HOST,PORT)
                        st.status="Đã kết nối" if ok else f"Lỗi: {net.err}"
                    else:
                        net.close(); st.status="Đã ngắt kết nối"
                elif e.key==pygame.K_n and net.connected:
                    net.send({"type":"reset"})
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
