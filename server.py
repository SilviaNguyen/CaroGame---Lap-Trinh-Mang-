import socket, argparse, os, json, threading, time, pathlib
import threading
from board import Board
from datetime import datetime

def parse_args():
    p = argparse.ArgumentParser(description="Caro Game Server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--size", type=int, default=15)
    p.add_argument("--win", type=int, default=5)
    p.add_argument("--logdir", default="", help="Thư mục ghi log; rỗng =off")
    p.add_argument("--enable-chat", action="store_true")
    p.add_argument("--enable-rooms", action="store_true")
    p.add_argument("--turn-timer", type=int, default=0, help="Thời gian tối đa mỗi lượt (giây); 0 = off")
    return p.parse_args()
args = parse_args()
class RoomState:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.board = Board(size=args.size, win_len=args.win)
        self.players = []   # [{sock, name, symbol}]  len<=2
        self.turn = "X"
        self.winner = None
        self.lock = threading.Lock()
        self.last_move_ts = time.time()  # dùng cho timer

    def broadcast(self, obj):
        data = (json.dumps(obj) + "\n").encode()
        for p in list(self.players):
            try: p["sock"].sendall(data)
            except: pass

    def assign_symbols_if_ready(self):
        if len(self.players) == 2:
            self.players[0]["symbol"] = "X"
            self.players[1]["symbol"] = "O"
            for p in self.players:
                self.send_assign(p)

            # phát state khởi tạo
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
        msg = {"type":"state","grid":grid,"turn":self.turn,"winner":self.winner,"last":last}
        self.broadcast(msg)

    def join(self, sock, name):
        with self.lock:
            if len(self.players) >= 2:
                self._send_one({"sock":sock}, {"type":"error","message":"room full"})
                return
            self.players.append({"sock":sock,"name":name,"symbol":None}) 
            self.assign_symbols_if_ready() 

    def make_move(self, x, y, player_symbol):
        with self.lock:
            if self.winner: 
                return {"type":"error","message":"game finished"}
            if player_symbol != self.turn:
                return {"type":"error","message":"not your turn"}

            ok = self.board.place(x, y, player_symbol)  # đổi tên nếu API khác
            if not ok:
                return {"type":"error","message":"invalid move"}

            self.last_move_ts = time.time()
            # xác định thắng
            if self.board.check_win_from(x, y):   # đổi tên nếu API khác
                self.winner = player_symbol

            # đổi lượt nếu chưa có winner
            if not self.winner and self.board.is_draw():
                self.winner="draw"

            self.push_state(last={"x":x,"y":y,"player":player_symbol})
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
        ch = sock.recv(1)
        if not ch:
            return None
        buf += ch
        if ch == b"\n":
            s = buf.decode().strip()
            try: 
                return json.loads(s)
            except Exception:
                return {"type":"error","message":"bad json"}
def timer_loop():
    if args.turn_timer <= 0:
        return
    while True:
        time.sleep(0.5)
        now = time.time()
        for r in list(rooms.values()):
            with r.lock:
                if r.winner or len(r.players) < 2:
                    continue
                if now - r.last_move_ts >= args.turn_timer:
                    r.turn = "O" if r.turn == "X" else "X"
                    r.last_move_ts = now
                    r.broadcast({"type":"error","message":"timeout -> switch turn"})
                    r.push_state()
LOG_DIR = pathlib.Path(args.logdir) if args.logdir else None
if LOG_DIR:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_move(room: RoomState, x, y, player):
    if not LOG_DIR:
        return
    rec = {
        "ts": datetime.utcnow().isoformat()+"Z",
        "room": room.room_id,
        "player": player, "x": x, "y": y,
        "turn_after": room.turn, "winner": room.winner
    }
    with (LOG_DIR / f"{datetime.utcnow().date()}.jsonl").open("a", encoding="utf-8") as f:
        import json
        f.write(json.dumps(rec) + "\n")

def handler_client(sock, addr):
    print(f"[+] {addr} connected")
    try:
        while True:
            obj = read_line_json(sock)
            if not obj:
                break

            t = obj.get("type")
            if t == "join":
                room_id = obj.get("room", "default")
                name = obj.get("name", "player")
                r = get_room(room_id)
                r.join(sock, name)  # gán X/O khi đủ 2 người + push_state
                conn_info[sock] = {"room": room_id, "name": name}

            elif t == "move":
                info = conn_info.get(sock)
                if not info:
                    try: sock.sendall(b'{"type":"error","message":"join first"}\n')
                    except: pass
                    continue
                r = get_room(info["room"])
                # tìm symbol của sock này
                sym = None
                for p in r.players:
                    if p["sock"] is sock:
                        sym = p["symbol"]
                        break
                if not sym:
                    try: sock.sendall(b'{"type":"error","message":"no symbol yet"}\n')
                    except: pass
                    continue

                x = int(obj.get("x", -1))
                y = int(obj.get("y", -1))
                res = r.make_move(x, y, sym)
                if res and res.get("type") == "error":
                    try: sock.sendall((json.dumps(res) + "\n").encode())
                    except: pass
                else:
                    # (tuỳ chọn) ghi log
                    try: log_move(r, x, y, sym)
                    except: pass

            elif t == "chat" and args.enable_chat:
                info = conn_info.get(sock, {"name":"?"})
                room_id = info.get("room", "default")
                r = get_room(room_id)
                r.broadcast({"type":"chat","from":info.get("name","?"),"message":obj.get("message","")})

            elif t == "error":
                # client gửi báo lỗi? bỏ qua
                pass
            elif t == "reset":
                info = conn_info.get(sock)
                if not info:
                    continue
                r = get_room(info["room"])
                with r.lock:
                    # tạo lại board mới cho phòng
                    r.board = Board(size=args.size, win_len=args.win)
                    r.turn = "X"
                    r.winner = None
                # gửi state mới cho cả phòng
                r.push_state()

            else:
                try: sock.sendall(b'{"type":"error","message":"unknown type"}\n')
                except: pass

    except Exception as e:
        print(f"[!] {addr} error: {e}")
    finally:
        # remove from room
        info = conn_info.pop(sock, None)
        if info:
            r = rooms.get(info["room"])
            if r:
                with r.lock:
                    r.players = [p for p in r.players if p["sock"] is not sock]
                # phát state mới (1 người còn lại vẫn xem được bàn)
                r.push_state()
        try: sock.close()
        except: pass
        print(f"[x] {addr} disconnected")
             
def main():
    host, port = args.host, args.port
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    print(f"[OK] Server listening on {host}:{port}")

    # bật timer nếu cấu hình
    if args.turn_timer > 0:
        threading.Thread(target=timer_loop, daemon=True).start()

    while True:
        client, addr = srv.accept()
        threading.Thread(target=handler_client, args=(client, addr), daemon=True).start()

if __name__ == "__main__":
    main()

