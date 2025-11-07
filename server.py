import json
import socket
import threading
from board import Board


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

if __name__ == "__main__":
    main()