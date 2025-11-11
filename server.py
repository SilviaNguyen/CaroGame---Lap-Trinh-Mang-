import json, argparse, pathlib, os
import socket
import threading
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
    p.add_argument("--turn-timer", type=int, default=30, help="Thời gian tối đa mỗi lượt (giây); 0 = off. VD: 30")
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
        self.last_move_ts = time.time()
        self.timer_duration = args.turn_timer

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
            self.last_move_ts = time.time()
            for p in self.players:
                self.send_assign(p)
            self.push_state()
     
    def status(self, last=None):
        grid = self.board.to_list() if hasattr(self.board, "to_list") else getattr(self.board, "grid", None)
        msg = {
            "type": "state",
            "grid": grid,
            "turn": self.turn,
            "winner": self.winner,
            "last": last,
            "timer_duration": args.turn_timer,
            "last_move_ts": self.last_move_ts
        }
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

            valid = self.board.place(x, y, player_symbol)
            if not valid:
                return {"type": "error", "message": "Invalid move"}

            if self.board.check_win_from(x, y):
                self.winner = player_symbol
            elif self.board.is_draw():
                self.winner = "draw"

            self.push_state(last={"x": x, "y": y, "player": player_symbol})
            return {"type": "valid"}

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
                    ROOM.push_state()
        try: sock.close()
        except: pass
        print(f"[x] {addr} disconnected")
    
def server_loop():
    global is_server_running, server_socket
    is_server_running = True
    server_socket.listen(5)
    print("Đang chờ kết nối...")
    
    try:
        while is_server_running:
            try:
                server_socket.settimeout(1.0)
                client, addr = server_socket.accept()
                if not is_server_running:
                    safe_close(client)
                    break

                thread = threading.Thread(target=handle_client, args=(client, addr), daemon=True)
                thread.start()
            except socket.timeout:
                continue
            except OSError:
                break
    except KeyboardInterrupt:
        print("\n Dừng bằng bàn phím.")
    finally:
        shutdown_server()
        
def shutdown_server():
    global is_server_running, players, server_socket, turn_timer
    print("Đang tắt server...")
    
    is_server_running = False
    
    with lock:
        for p in players[:]:
            conn = p["conn"]
            send(conn, {"type": "info", "message": "Server đã tắt."})
            safe_close(conn)
        players.clear()
        
        if turn_timer:
            turn_timer.cancel()
            turn_timer = None
            
    if server_socket:
        try:
            server_socket.close()
        except:
            pass
        server_socket = None
    print("[SERVER] Đã dừng hoàn toàn.")
            
def main():     
    global server_socket              
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        server_socket.bind((host, port))
    except OSError as e:
        print(f"[x] Không thể bind tới {host}:{port} ({e}).")
        return

    print("Khởi động server game Caro...")
    server_thread = threading.Thread(target=server_loop)
    server_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_server()

if __name__ == "__main__":
    main()