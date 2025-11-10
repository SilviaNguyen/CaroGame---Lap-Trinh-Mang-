import sys, socket, threading, json, pygame

HOST = "127.0.0.1"; PORT = 5000
if len(sys.argv)>=2: HOST = sys.argv[1]
if len(sys.argv)>=3: PORT = int(sys.argv[2])
ROOM = "lobby1"
if len(sys.argv)>=4: ROOM = sys.argv[3]

SIZE=15; CELL=36; MARGIN=20
W=MARGIN*2+CELL*SIZE; H=MARGIN*2+CELL*SIZE+60; FPS=60

pygame.init()
screen=pygame.display.set_mode((W,H)); pygame.display.set_caption("Caro LAN Client")
clock=pygame.time.Clock(); font=pygame.font.SysFont(None,22); small=pygame.font.SysFont(None,16)

BG=(18,48,58); GRID=(60,120,130); LINE=(32,90,100)
XCOL=(230,240,240); OCOL=(235,85,85); BAR=(236,240,245); TXT=(28,44,54); MUTED=(95,105,115)

class Net:
    def __init__(self, onmsg):
        self.onmsg=onmsg; self.sock=None; self.buf=""; self.connected=False; self.err=""; self.lock=threading.Lock()
    def connect(self, host, port):
        self.close()
        try:
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect((host,port))
            self.sock=s; self.connected=True; threading.Thread(target=self.reader, daemon=True).start()
            # gửi join ngay
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
        self.status=f"Nhấn C để kết nối • ROOM={ROOM}"
    def apply(self, m):
        t=m.get("type")
        if t=="welcome":
            self.me=m.get("symbol","?"); self.status=f"Đã vào phòng '{m.get('room','?')}'. Bạn là {self.me}"
            net.send({"type":"sync"})
        elif t=="start":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=None; self.draw=False; self.status="Ván mới bắt đầu"
        elif t=="update":
            self.grid=m.get("board",self.grid); self.turn=m.get("turn",self.turn)
            self.winner=m.get("winner"); self.draw=m.get("draw",False)
        elif t=="end":
            self.status=m.get("message","Kết thúc ván")
        elif t in ("info","error"):
            self.status=m.get("message","")

def draw_board(st):
    rect=pygame.Rect(MARGIN,MARGIN,CELL*SIZE,CELL*SIZE)
    pygame.draw.rect(screen,LINE,rect,2)
    for i in range(1,SIZE):
        x=MARGIN+i*CELL; y=MARGIN+i*CELL
        pygame.draw.line(screen,GRID,(x,MARGIN),(x,MARGIN+CELL*SIZE),1)
        pygame.draw.line(screen,GRID,(MARGIN,y),(MARGIN+CELL*SIZE,y),1)
    for y in range(SIZE):
        for x in range(SIZE):
            v=st.grid[y][x]
            if not v: continue
            cx=MARGIN+x*CELL+CELL//2; cy=MARGIN+y*CELL+CELL//2
            if v=="X":
                s=CELL//2-6
                pygame.draw.line(screen,XCOL,(cx-s,cy-s),(cx+s,cy+s),4)
                pygame.draw.line(screen,XCOL,(cx-s,cy+s),(cx+s,cy-s),4)
            else:
                r=CELL//2-6; pygame.draw.circle(screen,OCOL,(cx,cy),r,4)
    return rect

def draw_status(st, net):
    bar=pygame.Rect(0,H-60,W,60); pygame.draw.rect(screen,BAR,bar)
    left=f"{'ON' if net.connected else 'OFF'} • You: {st.me} • Turn: {st.turn} • Room: {ROOM}"
    right=st.status
    screen.blit(font.render(left,True,TXT),(12,H-44))
    screen.blit(font.render(right,True,TXT),(12,H-22))
    tips="C: Connect/Disconnect   N: New   Esc: Quit"
    w=small.size(tips)[0]; screen.blit(small.render(tips,True,MUTED),(W-w-12,H-20))

st = State()
net = Net(lambda m: st.apply(m))

def main():
    global net, st
    running=True
    while running:
        for e in pygame.event.get():
            if e.type==pygame.QUIT: running=False
            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE: running=False
                elif e.key==pygame.K_c:
                    if not net.connected:
                        ok=net.connect(HOST,PORT)
                        st.status="Connected" if ok else f"Lỗi: {net.err}"
                    else:
                        net.close(); st.status="Disconnected"
                elif e.key==pygame.K_n and net.connected:
                    net.send({"type":"reset"})
            elif e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                rect=pygame.Rect(MARGIN,MARGIN,CELL*SIZE,CELL*SIZE)
                if rect.collidepoint(e.pos) and net.connected and not st.winner and not st.draw:
                    if st.me!=st.turn:
                        st.status="Chưa đến lượt bạn"
                    else:
                        gx=(e.pos[0]-MARGIN)//CELL; gy=(e.pos[1]-MARGIN)//CELL
                        if 0<=gx<SIZE and 0<=gy<SIZE:
                            if st.grid[gy][gx]=="":
                                net.send({"type":"move","x":int(gx),"y":int(gy)})
                            else:
                                st.status="Ô đã có quân"
        screen.fill(BG); draw_board(st); draw_status(st,net)
        pygame.display.flip(); clock.tick(FPS)
    net.close(); pygame.quit(); sys.exit()

if __name__=="__main__":
    main()
