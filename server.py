import socket, argparse, os, json, threading, time, pathlib
from board import Board
import time, datetime

def parse_args():
    p = argparse.ArgumentParser(description="Caro Game Server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--size", type=int, default=15)
    p.add_argument("--win", type=int, default=5)
    p.add_argument("--logdir", default="", help="Thư mục ghi log; rỗng =off")
    p.add_argument("--enable-chat", action="store_true")
    p.add_argument("--enable-rooms", action="store_true")
    p.add_argument("--turn-timer", type=int, default=30, help="Thời gian tối đa mỗi lượt (giây); 0 = off")
    return p.parse_args()
args = parse_args()

ROOM = None
conn_info = {} 
class RoomState:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.board = Board(size=args.size, win_len=args.win)
        self.players = []
        self.turn = "X"
        self.winner = None
        self.lock = threading.Lock()
        self.last_move_ts = time.time()  # dùng cho timer
        self.timer_duration = args.turn_timer # Sẽ lấy giá trị default=30
        self.history = []

    def broadcast(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        for p in list(self.players):
            try:
                p["sock"].sendall(data)
            except Exception:
                pass

    def _send_one(self, p, obj):
        try:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            p["sock"].sendall(data)
        except Exception:
            pass
    def send_assign(self, p):
        msg = {"type": "assign", "symbol": p["symbol"], "your_turn": (p["symbol"] == self.turn)}
        self._send_one(p, msg)

    def assign_symbols_if_ready(self):
        if len(self.players) == 2:
            self.players[0]["symbol"] = "X"
            self.players[1]["symbol"] = "O"
            self.board.reset()
            self.turn = self.board.turn
            self.winner = None
            self.last_move_ts = time.time() # Reset timer
            self.history = []
            for p in self.players:
                self.send_assign(p)
            self.push_state()

    def send_assign(self, p):
        msg = {"type":"assign","symbol":p["symbol"],"your_turn":(p["symbol"]==self.turn)}
        self._send_one(p, msg)

    def _send_one(self, p, obj):
        try: p["sock"].sendall((json.dumps(obj)+"\n").encode())
        except: pass

    def push_state(self, last=None):
        # grid là dạng chuỗi/2D… tuỳ board của nhóm; nếu board cung cấp get_grid(), dùng trực tiếp
        grid = getattr(self.board, "grid", None)
        msg = {"type":"state","grid":grid,"turn":self.turn,"winner":self.winner,"last":last, "timer_duration": args.turn_timer, "last_move_ts": self.last_move_ts}

        self.broadcast(msg)
            
    def join(self, sock, name):
        with self.lock:
            if len(self.players) >= 2:
                self._send_one({"sock":sock}, {"type":"error","message":"room full"})
                return
            self.players.append({"sock": sock, "name": name, "symbol": None})
            self.assign_symbols_if_ready()
                 
    def handle_move(self, x, y, player_symbol): 
        with self.lock:
            if self.winner:
                return {"type": "error", "message": "Game finished"}
            if player_symbol != self.turn:
                return {"type": "error", "message": "Calm down. It is not your turn!"}
            ok = self.board.place(x, y, player_symbol)  
            if not ok:
                return {"type":"error","message":"invalid move"}
            self.history.append((x, y, player_symbol))
            self.turn = self.board.turn
            self.last_move_ts = time.time()# Reset timer sau nước đi
            # xác định thắng
            if self.board.check_win_from(x, y):  
                self.winner = player_symbol
            elif self.board.is_draw():
                self.winner = "draw"
            elif self.board.is_draw():
                self.winner="draw"
            self.push_state(last={"x":x,"y":y,"player":player_symbol})
            return {"type":"ok"}
          
    def undo_last(self):
        with self.lock:
            if not self.history:
                return {"type":"error", "message":"no moves to undo"}
            
            x, y, player_symbol = self.history.pop()

            if self.board.in_bounds(x, y) and self.board.get(x, y):
                self.board.grid[y][x] = ""
                self.board.moves = max(0, self.board.moves - 1)

            # Cập nhật lượt đi sau undo
            self.board.turn = player_symbol
            self.turn = self.board.turn

            self.winner = None # Xóa kết quả thắng (Nếu có)
            self.last_move_ts = time.time () 
            self.push_state()
            return {"type":"ok"}

# === System Integration: room registry & connection map ===
rooms = {}            # room_id -> RoomState
conn_info = {}        # sock -> {"room":"default","name":"A","symbol":"X"}

def get_room(room_id: str) -> RoomState:
    if not args.enable_rooms:
        room_id = "default"
    if room_id not in rooms:
        rooms[room_id] = RoomState(room_id)
    return rooms[room_id]
def read_line_json(sock): 
    buf = b""
    while True:
        try:
            data = sock.recv(1024)
            if not data:
                return None

            buffer += data.decode("utf-8", "ignore")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line)
                except Exception:
                    return {"type": "error", "message": "bad json"}

        except Exception:
            return None

def timer_loop():
    if args.turn_timer <= 0:
        print("[INFO] Turn timer is disabled.")
        return
    
    print(f"[INFO] Turn timer enabled: {args.turn_timer} seconds per turn.")
    
    while True:
        time.sleep(0.5) # Kiểm tra mỗi nửa giây
        now = time.time()
        for r in list(rooms.values()):
            with r.lock:
                if r.winner or len(r.players) < 2:
                    continue
                
                # timer_duration được lấy từ RoomState (đã gán default 30)
                if now - r.last_move_ts >= r.timer_duration:
                    # Hết giờ!
                    loser = r.turn
                    r.winner = "O" if loser == "X" else "X"
                    r.last_move_ts = now # Reset timer để không bị lặp
                    
                    print(f"[TIMER] Phòng {r.room_id}: Người chơi {loser} hết giờ. {r.winner} thắng.")
                    
                    r.broadcast(
                        {
                            "type": "error",
                            "message": f"Hết giờ! {loser} đã thua.",
                        }
                    )
                    # Gửi state cuối cùng với người chiến thắng
                    r.push_state()
LOG_DIR = pathlib.Path(args.logdir) if args.logdir else None
if LOG_DIR:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_move(room: RoomState, x, y, player):
    if not LOG_DIR:
        return
    rec = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "room": room.room_id,
        "player": player,
        "x": x, "y": y,
        "turn_after": room.turn,
        "winner": room.winner
    }
    try:
        with (LOG_DIR / f"{datetime.utcnow().date()}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        print(f"[ERROR] Could not write log: {e}")

def handler_client(sock, addr):
    print(f"[+] {addr} connected")
    try:
        while True:
            data = read_line_json(sock)
            if data is None:
                break
        
            t = data.get("type")
            if t == "join":
                room_id = obj.get("room", "default")
                name = obj.get("name", "player")
                r = get_room(room_id)
                r.join(sock, name)  # gán X/O khi đủ 2 người + push_state
                conn_info[sock] = {"room": room_id, "name": name}
                continue

            info = conn_info.get(sock)
            if not info:
                try: sock.sendall(b'{"type":"error","message":"join first"}\n')
                except: pass
                continue
            r = get_room(info["room"])

            if t == "move":
                # tìm symbol của sock này
                sym = None
                for p in r.players:
                    if p["sock"] is sock:
                        sym = p["symbol"]
                        break
                if not sym:
                    try: sock.sendall((json.dumps({"type":"error","message":"no symbol yet"})+"\n").encode("utf-8"))
                    except: pass
                    continue
                try: 
                    x = int(obj.get("x", -1))
                    y = int(obj.get("y", -1))
                except Exception:
                    x, y = -1 -1
                res = r.make_move(x, y, sym)
                if res and res.get("type") == "error":
                    try: sock.sendall((json.dumps(res) + "\n").encode("utf-8"))
                    except: pass
                else:
                    try: log_move(r, x, y, sym)
                    except: pass
                continue
            elif t == "chat" and args.enable_chat:
                info = conn_info.get(sock, {"name":"?"})
                room_id = info.get("room", "default")
                r = get_room(room_id)
                r.broadcast({"type":"chat","from":info.get("name","?"),"message":obj.get("message","")})
                continue
            elif t == "error":
                # client gửi báo lỗi? bỏ qua
                pass
            elif t == "reset":
                with r.lock:
                    r.board.reset()
                    r.turn = "X"
                    r.winner = None
                    r.last_move_ts = time.time() # Reset timer
                    r.history = []
                r.push_state()
                continue
            elif t == "undo":
                res = r.undo_last()
                try:
                    sock.sendall((json.dumps(res) + "\n").encode("utf-8"))
                except: pass
                continue
            else:
                try: sock.sendall(b'{"type":"error","message":"unknown type"}\n')
                except: pass
    except Exception as e:
        print(f"[!] {addr} error: {e}")
    finally:
        info = conn_info.pop(sock,None)
        if info:
            with ROOM.lock:
                ROOM.players = [p for p in ROOM.players if p["sock"]!=sock]
                if len(ROOM.players)<2:
                    ROOM.winner=None
                    ROOM.board.reset()
                    ROOM.status()
        try: sock.close()
        except: pass
        print(f"[x] {addr} disconnected")
            
def main():     
    global ROOM
    ROOM = RoomState("default")
    
    host, port = args.host, args.port

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except Exception as e:
        print(f"[FATAL] Could not bind to {host}:{port}. Error: {e}")
        return
    srv.listen(5)
    print(f"[OK] Server listening on {host}:{port}")
    if args.turn_timer > 0:
        threading.Thread(target=timer_loop, daemon=True).start()

    try:
        while True:
            client, addr = srv.accept()
            threading.Thread(target=handler_client, args=(client, addr), daemon=True).start()

    except KeyboardInterrupt:
        print("Shutting down server (KeyboardInterrupt).")
    except Exception as e:
        print(f"Server main loop error: {e}")
    finally:
        try:
            srv.close()
        except:
            pass

if __name__ == "__main__":
    main()