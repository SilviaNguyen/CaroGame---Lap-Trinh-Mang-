import json, argparse, pathlib, os
import socket, threading, time, random, string
from board import Board
from datetime import datetime

def parse_args():
    p = argparse.ArgumentParser(description="Caro Game Server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--size", type=int, default=15)
    p.add_argument("--win", type=int, default=5)
    p.add_argument("--logdir", default="", help="Thư mục ghi log; rỗng = off")
    p.add_argument("--turn-timer", type=int, default=30, help="Thời gian tối đa mỗi lượt (giây); 0 = off")
    return p.parse_args()

args = parse_args()
rooms = {}
conn_map = {}
mm_queue = []
lock = threading.Lock()
LOG_DIR = pathlib.Path(args.logdir) if args.logdir else None
if LOG_DIR:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

class RoomState:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.board = Board(size=args.size, win_len=args.win)
        self.players = []
        self.turn = "X"
        self.winner = None
        self.deadline = None
        self.lock = threading.Lock()

    def broadcast(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        for p in list(self.players):
            try:
                p["sock"].sendall(data)
            except: pass

    def send_one(self, player, obj):
        try:
            player["sock"].sendall((json.dumps(obj)+"\n").encode("utf-8"))
        except: pass

    def push_state(self):
        msg = {
            "type":"update",
            "board": self.board.to_list(),
            "turn": self.board.turn,
            "winner": self.board.winner,
            "draw": self.board.is_draw(),
            "win_line": getattr(self.board,"win_line",None),
            "deadline": self.deadline,
            "turn_seconds": args.turn_timer
        }
        self.broadcast(msg)

    def join(self, sock, addr, force_symbol=None):
        with self.lock:
            if len(self.players) >= 2:
                self.send_one({"sock": sock}, {"type":"error","message":"Room full"})
                return None
            used_symbols = {p["symbol"] for p in self.players}
            sym = force_symbol or ("X" if "X" not in used_symbols else "O")
            player = {"sock": sock, "addr": addr, "symbol": sym}
            self.players.append(player)
            conn_map[sock] = {"room": self.room_id, "player": player}
            self.send_one(player, {"type":"welcome","room":self.room_id,"symbol":sym})
            if len(self.players) == 2:
                self.board.reset()
                self.board.turn = "X"
                self.deadline = time.time() + args.turn_timer
                self.push_state()
            else:
                self.send_one(player, {"type":"info","message":"Đang đợi người chơi thứ hai..."})
            return player

    def handle_move(self, player, x, y):
        with self.lock:
            board = self.board
            if player not in self.players:
                self.send_one(player, {"type":"error","message":"Bạn không còn trong phòng"})
                return
            if board.winner:
                self.send_one(player, {"type":"error","message":"Ván đã kết thúc"})
                return
            if board.turn != player["symbol"]:
                self.send_one(player, {"type":"error","message":"Chưa đến lượt bạn"})
                return
            if not board.place(x, y, player["symbol"]):
                self.send_one(player, {"type":"error","message":"Nước đi không hợp lệ"})
                return
            self.deadline = time.time() + args.turn_timer
            self.push_state()
            if board.winner:
                self.broadcast({"type":"end","message":f"Người chơi {board.winner} thắng!","win_line":board.win_line})
            elif board.is_draw():
                self.broadcast({"type":"end","message":"Hòa!","win_line":None})

def _gen_room_id(prefix="RM", length=4):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-"+ "".join(random.choices(chars,k=length))

def _leave_queue_locked(sock):
    for i in range(len(mm_queue)-1,-1,-1):
        if mm_queue[i]["sock"]==sock:
            mm_queue.pop(i)
            try: sock.sendall((json.dumps({"type":"info","message":"Left queue"})+"\n").encode("utf-8"))
            except: pass

def _try_match_locked():
    while len(mm_queue) >= 2:
        a = mm_queue.pop(0)
        b = mm_queue.pop(0)
        sock1, addr1 = a["sock"], a["addr"]
        sock2, addr2 = b["sock"], b["addr"]
        if sock1 in conn_map or sock2 in conn_map: continue
        room_id = _gen_room_id()
        room = RoomState(room_id)
        rooms[room_id] = room
        room.join(sock1, addr1, "X")
        room.join(sock2, addr2, "O")
        try:
            sock1.sendall((json.dumps({"type":"info","message":f"Đã ghép cặp • Phòng: {room_id}"})+"\n").encode("utf-8"))
            sock2.sendall((json.dumps({"type":"info","message":f"Đã ghép cặp • Phòng: {room_id}"})+"\n").encode("utf-8"))
        except: pass

def _timeout_check_loop():
    while True:
        time.sleep(0.25)
        now = time.time()
        with lock:
            for room in rooms.values():
                with room.lock:
                    if len(room.players)<2: continue
                    if room.board.winner or room.board.is_draw(): continue
                    if not room.deadline: continue
                    if now >= room.deadline:
                        loser = room.board.turn
                        winner = "O" if loser=="X" else "X"
                        room.board.winner = winner
                        room.push_state()
                        room.broadcast({"type":"end","message":f"{loser} hết giờ • {winner} thắng!","win_line":room.board.win_line})

def _cleanup_conn(sock):
    with lock:
        _leave_queue_locked(sock)
        info = conn_map.pop(sock,None)
        if not info: return
        room_id = info["room"]; player = info["player"]
        room = rooms.get(room_id)
        if not room: return
        with room.lock:
            if player in room.players:
                room.players.remove(player)
            room.board.reset()
            room.deadline = None
            room.broadcast({"type":"info","message":f"{player['symbol']} đã rời phòng. Đang chờ người chơi khác..."})
            if not room.players:
                del rooms[room_id]

def handle_client(sock, addr):
    print(f"[CONNECT] {addr}")
    buf = ""
    try:
        while True:
            data = sock.recv(4096)
            if not data: break
            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n",1)
                line=line.strip()
                if not line: continue
                try: msg = json.loads(line)
                except: continue
                t = msg.get("type","")
                with lock:
                    if t=="queue":
                        action = msg.get("action","join")
                        if action=="join":
                            if not any(i["sock"]==sock for i in mm_queue):
                                mm_queue.append({"sock":sock,"addr":addr})
                                sock.sendall((json.dumps({"type":"info","message":"Đã vào hàng đợi ghép cặp"})+"\n").encode("utf-8"))
                                _try_match_locked()
                        elif action=="leave": _leave_queue_locked(sock)
                    elif t=="move":
                        cm = conn_map.get(sock)
                        if cm: cm_room = rooms.get(cm["room"])
                        if cm_room: cm_room.handle_move(cm["player"], int(msg.get("x",-1)), int(msg.get("y",-1)))
                    elif t=="reset":
                        cm = conn_map.get(sock)
                        if cm:
                            cm_room = rooms.get(cm["room"])
                            if cm_room and len(cm_room.players)==2:
                                cm_room.board.reset()
                                cm_room.board.turn="X"
                                cm_room.deadline=time.time()+args.turn_timer
                                cm_room.push_state()
                    elif t=="sync":
                        cm = conn_map.get(sock)
                        if cm:
                            cm_room = rooms.get(cm["room"])
                            if cm_room:
                                b = cm_room.board
                                sock.sendall((json.dumps({
                                    "type":"update",
                                    "board":b.to_list(),
                                    "turn":b.turn,
                                    "winner":b.winner,
                                    "draw":b.is_draw(),
                                    "win_line":b.win_line,
                                    "deadline": cm_room.deadline,
                                    "turn_seconds": args.turn_timer
                                })+"\n").encode("utf-8"))
    finally:
        _cleanup_conn(sock)
        try: sock.close()
        except: pass
        print(f"[DISCONNECT] {addr}")

def main():
    threading.Thread(target=_timeout_check_loop, daemon=True).start()
    threading.Thread(target=_queue_health_check_loop, daemon=True).start()
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(64)
    server.settimeout(1.0)
    print(f"[OK] Server listening on {args.host}:{args.port}")

    client_sockets = []

    try:
        while True:
            try:
                client, addr = server.accept()
                client_sockets.append(client)
                threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("[INFO] Server đang tắt (Ctrl+C)")
    finally:
        for csock in client_sockets:
            try:
                csock.close()
            except: pass
        try:
            server.close()
        except:
            pass
        print("[INFO] Server closed")

if __name__ == "__main__":
    main()
