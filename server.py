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

def read_line_json(sock):
    buffer = ""
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
        time.sleep(0.5)
        now =  time.time()
        with ROOM.lock:
            if ROOM.winner or len(ROOM.players) < 2:
                continue
            if now - ROOM.last_move_ts >= ROOM.timer_duration:
                loser = ROOM.turn
                ROOM.winner = "O" if loser == "X" else "X"
                ROOM.last_move_ts = now
                print(f"[TIMER] Người chơi ({loser}) hết thời gian! => {ROOM.winner} thắng.")
                ROOM.broadcast({
                    "type": "timeout",
                    "message": f"Hết giờ! Người chơi {loser} đã thua."
                })
                ROOM.status()

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
                          
def handle_client(sock, addr):    
    print(f"{addr} connected")    
    try:
        while True:
            data = read_line_json(sock)
            if data is None:
                break
        
            t = data.get("type")
            if t == "join":
                name = data.get("name", "player")
                ROOM.join(sock, name)
                conn_info[sock] = {"name": name}
                continue

            info = conn_info.get(sock)
            if not info:
                try:
                    sock.sendall((json.dumps({"type": "error", "message": "join first"}) + "\n").encode("utf-8"))
                except:
                    pass
                continue

            if t == "move":
                sym = next((p["symbol"] for p in ROOM.players if p["sock"]==sock), None)
                if not sym:
                    try: sock.sendall((json.dumps({"type":"error","message":"no symbol yet"})+"\n").encode("utf-8"))
                    except: pass
                    continue
                
                try:
                    x = int(data.get("x",-1)); y = int(data.get("y",-1))
                except:
                    x, y = -1, -1
                
                res = ROOM.make_move(x,y,sym)
                if res.get("type")=="error":
                    try: sock.sendall((json.dumps(res)+"\n").encode("utf-8"))
                    except: pass
                else:
                    try: log_move(ROOM, x, y, sym)
                    except: pass
                continue

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
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((host, port))
    except Exception as e:
        print(f"[!] Không thể gán {host}:{port}. Error: {e}")
        return
    server.listen(5)
    print(f"[OK] Server listening on {host}:{port}")

    if args.turn_timer > 0:
        threading.Thread(target=timer_loop, daemon=True).start()

    try:
        while True:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("Shutting down server (KeyboardInterrupt).")
    except Exception as e:
        print(f"Server main loop error: {e}")
    finally:
        try:
            server.close()
        except:
            pass

if __name__ == "__main__":
    main()