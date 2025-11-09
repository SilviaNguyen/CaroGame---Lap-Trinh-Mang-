 integration
import socket, argparse, os, json, threading, time, pathlib

import json
import socket
 main
import threading
from board import Board
from datetime import datetime

 integration
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
class RoomState:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.board = Board(size=args.size, win_len=args.win)
        self.players = []   # [{sock, name, symbol}]  len<=2
        self.turn = "X"
        self.winner = None
        self.lock = threading.Lock()
        self.last_move_ts = time.time()  
        self.timer_duration = args.turn_timer # Sẽ lấy giá trị default=30

    def broadcast(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        for p in list(self.players):
            try: 
                p["sock"].sendall(data)
            except Exception: pass

    def assign_symbols_if_ready(self):
        if len(self.players) == 2:
            self.players[0]["symbol"] = "X"
            self.players[1]["symbol"] = "O"
            # Reset bàn cờ khi đủ 2 người
            self.board.reset()
            self.turn = self.board.turn
            self.winner = None
            self.last_move_ts = time.time() # Reset timer
            for p in self.players:
                self.send_assign(p)
            self.push_state()

    def send_assign(self, p):
        msg = {"type":"assign","symbol":p["symbol"], "your_turn": (p["symbol"] == self.turn)}
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

            ok = self.board.place(x, y, player_symbol)
            if not ok:
                return {"type":"error","message":"invalid move"}
            self.turn = self.board.turn
            self.last_move_ts = time.time() # Reset timer sau nước đi
            # xác định thắng
            if self.board.check_win_from(x, y):
                self.winner = player_symbol
            elif self.board.is_draw(): # Sửa lỗi logic: check_win_from trả về bool
                self.winner = "draw"

            self.push_state(last={"x": x,"y": y,"player": player_symbol})
            return {"type": "ok"}
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
        except Exception:
            return None
        
def timer_loop():
    if args.turn_timer <= 0:
        print("[INFO] Turn timer is disabled.")
        return
    
    print(f"[INFO] Turn timer enabled: {args.turn_timer} seconds per turn.")

    while True:
        time.sleep(0.5)
        now = time.time()
        for r in list(rooms.values()):
            with r.lock:
                if r.winner or len(r.players) < 2:
                    continue

                # timer_duration được lấy từ RoomState (đã gán default 30)
                if now - r.last_move_ts >= r.timer_duration:
                    # Hết giờ
                    loser = r.turn
                    r.winner = "O" if r.turn == "X" else "X"
                    r.last_move_ts = now

                    print(f"[TIMER] Phòng {r.room_id}: Người chơi {loser} hết giờ. {r.winner} thắng.")
                     
                    r.broadcast({"type": "error","message": f"Hết giờ! {loser} đã thua.",})
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
                r.join(sock, name)  
                conn_info[sock] = {"room": room_id, "name": name}
                continue

         
            info = conn_info.get(sock)
            if not info:
                try: sock.sendall(b'{"type":"error","message":"join first"}\n')
                except: pass
                continue

            r = get_room(info["room"])

            if t == "move":
                sym = None
                for p in r.players:
                    if p["sock"] is sock:
                        sym = p["symbol"]
                        break

                if not sym:
                    try: sock.sendall(b'{"type":"error","message":"no symbol yet"}\n')
                    except: pass
                    continue

                try:
                    x = int(obj.get("x", -1))
                    y = int(obj.get("y", -1))
                except Exception:
                    x, y = -1, -1 # Đánh dấu là invalid
                res = r.make_move(x, y, sym)

                if res and res.get("type") == "error":
                    try: sock.sendall((json.dumps(res) + "\n").encode())
                    except: pass
                else:
                    try: log_move(r, x, y, sym)
                    except: pass
                continue

            elif t == "chat" and args.enable_chat:
                r.broadcast({"type":"chat","from":info.get("name","?"),"message":obj.get("message","")})
                continue

            elif t == "reset":
                info = conn_info.get(sock)
                if not info:
                    continue
                r = get_room(info["room"])
                with r.lock:
                    r.board.reset()
                    r.turn = "X"
                    r.winner = None
                    r.last_move_ts = time.time() # Reset timer
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
                    if len(r.players) < 2:
                        r.winner = None # Reset game nếu 1 người thoát
                        r.board.reset()
                        r.push_state()
        try: sock.close()
        except: pass
        print(f"[x] {addr} disconnected")
             
def main():
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


host = '0.0.0.0'
port = 5000

board = Board(size=15, win_len=5)
players = []
symbols = ["X", "O"]

is_running = False
server_socket = None
lock = threading.Lock()

turn_time = 30
turn_timer = None
    
def send(client, data): 
    payload = (json.dumps(data) + "\n").encode("utf-8")
    client.sendall(payload)
    
def broadcast(data):
    with lock:
        for p in players[:]:
            conn = p.get("conn")
            try:
                send(conn, data)
            except Exception as e:
                print(f"[!] Lỗi gửi tới {p.get('addr')}: {e}. Xóa client này.")
                try:
                    conn.close()
                except:
                    pass
                players.remove(p) 

def start_turn_timer(player):
    global turn_timer
    if turn_timer:
        turn_timer.cancel()
    turn_timer = threading.Timer(turn_time, handle_timeout, [player])
    turn_timer.start()

def handle_timeout(player):
    with lock:
        print(f"[TIMER] Người chơi {player['addr']} hết thời gian!")
        broadcast({
            "type": "timeout",
            "message": f"Người chơi {player['symbol']} hết thời gian!"
        })
        
        board.turn = "O" if board.turn == "X" else "X"

        next_player = next(p for p in players if p["symbol"] == board.turn)
        start_turn_timer(next_player) 
                 
def handle_move(player, x, y):
    global turn_timer
    with lock:
        if board.turn != player["symbol"]:
            send(player["conn"], {"type": "error", "message": "Từ từ thôi chưa đến lượt bạn!"})
            return

        valid = board.place(x, y, player["symbol"])
        if not valid:
            send(player["conn"], {"type": "error", "message": "Nước đi không hợp lệ rồi!"})
            return
        
        if turn_timer:
            turn_timer.cancel()
            turn_timer = None
            
    data = {
        "type": "update",
        "board": board.to_list(),
        "turn": board.turn,
        "winner": board.winner,
        "draw": board.is_draw()
    }
    broadcast(data)
    
    if board.winner:
        broadcast({"type": "end", "message": f"Người chơi {board.winner} đã thắng rồi!"})
    elif board.is_draw():
        broadcast({"type": "end", "message": "Ván đấu hòa!"})
    else:
        board.turn = "O" if board.turn == "X" else "X"
        next_player = next(p for p in players if p["symbol"] == board.turn)
        start_turn_timer(next_player) 
          
def handle_client(conn, addr):

    global players, is_running
    
    print(f"Kết nối từ {addr}")
    player = {"conn": conn, "addr": addr, "symbol": None}
    
    with lock:
        if len(players) >= 2:    
            send(conn, {"type": "info", "message": "Phòng đã đầy mất rồi!"})
            conn.close()
            return
    
        player["symbol"] = symbols[len(players)]
        players.append(player)
        try:
            send(conn, {"type": "assign", "symbol": player["symbol"]})
        except Exception as e:
            print(f"[!] Không gửi được assign cho {addr}: {e}")
        print(f"Người chơi {addr} là '{player['symbol']}'")

    with lock:     
        if len(players) == 2:
            board.reset()
            board.turn = "X"
            broadcast({
                "type": "start",
                "message": "Trò chơi bắt đầu!",
                "board": board.to_list(),
                "turn": board.turn
            })
        first_player = next(p for p in players if p["symbol"] == board.turn)
        print(f"Bạn chơi đầu tiên. Hãy bắt đầu nước chơi!")
        start_turn_timer(first_player)
        
    buffer = ""
    
    try:
        while is_running:
            if not is_running:
                break
            data = conn.recv(1024)
            buffer += data.decode("utf-8")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    msg = json.loads(line)
                    if msg["type"] == "move":
                        x, y = msg["x"], msg["y"]
                        handle_move(player, x, y)
                except Exception as e:
                    send(conn, {"type": "error", "message": str(e)})
    except (ConnectionResetError, OSError):  
        print(f"[!] Client {addr} mất kết nối.")
    except Exception as e:
        print(f"[x] Đóng kết nối với {addr}: {e}")
    finally:
        with lock:
            if player in players:
                players.remove(player)
            broadcast({"type": "info", "message": f"Người chơi {player['symbol']} đã thoát!"})
            if len(players) < 2:
                board.reset()
        conn.close()
        print(f"[SERVER] Đã đóng kết nối với {addr}. Còn lại: {len(players)}")

def server_loop():
    global is_running, server_socket
    is_running = True
    server_socket.listen(5)
    print("Đang chờ kết nối...")
    
    try:
        while is_running:
            try:
                server_socket.settimeout(1.0)
                client, addr = server_socket.accept()
                if not is_running:
                    client.close()
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
    global is_running, players, server_socket
    print("Đang tắt server...")
    
    is_running = False
    
    with lock:
        for p in players[:]:
            conn = p["conn"]
            try:
                send(conn, {"type": "info", "message": "Server đã tắt."})
                conn.close()
            except:
                pass
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
    server_thread = threading.Thread(target=server_loop, daemon=True)
    server_thread.start()
    
    try:
        while True:
            pass  # giữ cho main thread không thoát
    except KeyboardInterrupt:
        shutdown_server()
main

if __name__ == "__main__":
    main()