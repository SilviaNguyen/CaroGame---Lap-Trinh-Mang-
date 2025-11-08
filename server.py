import json
import socket
import threading
from board import Board
import time

host = '0.0.0.0'
port = 5000

board = Board(size=15, win_len=5)
players = []
ready_players = set()
symbols = ["X", "O"]

is_running = False
is_server_running = False
server_socket = None
lock = threading.RLock()

turn_time = 30
turn_timer = None
ping_interval = 10

def safe_close(conn):
    try:
        conn.close()
    except:
        pass
       
def send(client, data): 
    payload = (json.dumps(data) + "\n").encode("utf-8")
    try:
        client.sendall(payload)
    except:
        safe_close(client)
        
def broadcast(data):
    with lock:
        for p in players[:]:
            conn = p.get("conn")
            try:
                send(conn, data)
            except Exception as e:
                print(f"[!] Lỗi gửi tới {p.get('addr')}: {e}. Xóa client này.")
                safe_close(conn)
                players.remove(p) 

def start_turn_timer(player):
    global turn_timer
    if turn_timer:
        turn_timer.cancel()
    turn_timer = threading.Timer(turn_time, handle_timeout, [player])
    turn_timer.start()

def handle_timeout(player):
    if not is_running:
        return
    
    with lock:
        loser = player["symbol"]
        winner = "O" if loser == "X" else "X"
        print(f"[TIMER] Người chơi {player['addr']} hết thời gian!")
        print(f"[TIMER] Người chơi {player['addr']} ({loser}) hết thời gian! => {winner} thắng.")
        broadcast({
            "type": "timeout",
            "message": f"Người chơi {loser} hết thời gian! {winner} thắng!"
        })
        end_game(winner=winner)

def end_game(winner = None, draw = False):   
    global turn_timer, is_running, ready_players
    
    with lock:
        is_running = False
        ready_players.clear()
        if turn_timer:
            turn_timer.cancel()
            turn_timer = None
    
    if winner:
        message = f"Người chơi {winner} đã thắng rồi!"
    elif board.is_draw():
        message = "Ván đấu hòa!"
    else:
        message = "Ván đấu kết thúc!"
    
    broadcast({
        "type": "end",
        "message": message
    }) 
    print(f"[GAME] {message}")

    time.sleep(2)
    with lock:
        board.reset() 
                 
def handle_move(player, x, y): 
    global turn_timer
    
    if not is_running:
        send(player["conn"], {"type": "info", "message": "Game chưa bắt đầu lại. Hãy chờ người chơi khác nhấn 'Ready'."})
        return

    with lock:
        if board.turn != player["symbol"]:
            send(player["conn"], {"type": "error", "message": "Từ từ thôi, chưa đến lượt bạn!"})
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
        end_game(winner=board.winner)
    elif board.is_draw():
        end_game(draw = True)
    else:
        board.turn = "O" if board.turn == "X" else "X"
        next_player = next((p for p in players if p["symbol"] == board.turn), None)
        if next_player:
            start_turn_timer(next_player) 

def start_game():     
    board.reset()
    board.turn = "X"
    
    broadcast({
        "type": "start",
        "message": "Trò chơi bắt đầu!",
        "board": board.to_list(),
        "turn": board.turn
    })
    print(f"Đã bắt đầu ván mới!")
    first_player = next((p for p in players if p["symbol"] == board.turn), None)
    if first_player:
        start_turn_timer(first_player)
    
def client_ping_loop(player):
    conn = player["conn"]
    
    while True:
        if "last_pong" in player:
            if time.time() - player["last_pong"] > ping_interval * 3:
                print(f"[PING] {player['addr']} không phản hồi -> ngắt kết nối.")
                safe_close(conn)
                break
        else:
            player["last_pong"] = time.time()

        send(conn, {"type": "ping"})
        time.sleep(ping_interval)

                    
def handle_client(conn, addr):
    global players, is_running
    
    print(f"Kết nối từ {addr}")
    player = {"conn": conn, "addr": addr, "symbol": None}
    
    with lock:
        if len(players) >= 2:    
            send(conn, {"type": "info", "message": "Phòng đã đầy mất rồi!"})
            safe_close(conn)
            return
    
        player["symbol"] = symbols[len(players)]
        players.append(player)
        send(conn, {"type": "assign", "symbol": player["symbol"]})
        print(f"Người chơi {addr} là '{player['symbol']}'")
            
        if len(players) == 2:
            broadcast({"type": "info", "message": "Cả hai đã vào phòng, hãy nhấn 'Ready' để bắt đầu!"})

    threading.Thread(target=client_ping_loop, args=(player,), daemon=True).start()

    buffer = ""
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buffer += data.decode("utf-8")
            
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    msg = json.loads(line)
                    
                    if msg["type"] == "pong":
                        player["last_pong"] = time.time()
                    elif msg["type"] == "move":
                        x, y = msg["x"], msg["y"]
                        handle_move(player, x, y)
                    elif msg["type"] == "ready":
                        with lock:
                            ready_players.add(player["symbol"])
                            print(f"[READY] {player['symbol']} đã sẵn sàng ({len(ready_players)}/2)")
                            if len(ready_players) == 2 and not is_running:
                                is_running = True
                                start_game()
                except Exception as e:
                    send(conn, {"type": "error", "message": str(e)})
    except (ConnectionResetError, OSError):  
        print(f"[!] Client {addr} mất kết nối.")
    finally:
        with lock:
            if player in players:
                players.remove(player)
            broadcast({"type": "info", "message": f"Người chơi {player['symbol']} đã thoát!"})
            if len(players) < 2:
                board.reset()
        safe_close(conn)
        print(f"[SERVER] Đã đóng kết nối với {addr}. Còn lại: {len(players)}")
    
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