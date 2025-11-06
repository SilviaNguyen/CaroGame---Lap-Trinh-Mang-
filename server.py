import json
import socket
import threading
from board import Board


host = '0.0.0.0'
port = 5000

board = Board(size=15, win_len=5)
players = []
symbols = ["X", "O"]
lock = threading.Lock()

    
def send(client, data):
    payload = (json.dumps(data) + "\n").encode("utf-8")
    client.sendall(payload)
    
def broadcast(data):
    for p in players:
        for p in players[:]:
            conn = p.get("conn")
            try:
                send(conn, data)
            except:
                pass

def handle_move(player, x, y):
    with lock:
        symbol = player["symbol"]
        valid = board.place(x, y, symbol)
        if not valid:
            send(player["conn"], {"type": "error", "message": "Nước đi không hợp lệ!"})
            return
        data = {
            "type": "update",
            "board": board.to_list(),
            "turn": board.turn,
            "winner": board.winner,
            "draw": board.is_draw()
        }
        broadcast(data)
        
        if board.winner:
            broadcast({"type": "end", "message": f"Người chơi {board.winner} đã thắng!"})
        elif board.is_draw():
            broadcast({"type": "end", "message": "Ván đấu hòa!"})
            
def handler_client(conn, addr):
    print(f"Kết nối từ {addr}")
    player = {"conn": conn, "addr": addr, "symbol": None}
    with lock:
        if len(players) >= 2:
            try:    
                send(conn, {"type": "info", "message": "Phòng đã đầy mất rồi!"})
            except:
                pass
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
            broadcast({
                "type": "start",
                "message": "Trò chơi bắt đầu!",
                "board": board.to_list(),
                "turn": board.turn
            })
    
    conn.settimeout(5.0)
    buffer = ""
    
    try:
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    continue
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
            except socket.timeout:
                continue  
    except Exception as e:
        print(f"[!] Lỗi với client {addr}: {e}")
    finally:
        print(f"[x] Đóng kết nối với {addr}")
        with lock:
            if player in players:
                players.remove(player)
        conn.close()
         
def main():                   
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    print("Đang chờ kết nối...")
    server_socket.listen(5)

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=handler_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    main()