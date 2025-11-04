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
    client.sendall((json.dumps(data) + "\n").encode("utf-8"))

def broadcast(data):
    for p in players:
        try:
            send(p["conn"], data)
        except:
            pass

def hadle_move(player, x, y):
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
    client_socket.sendall("Chào mừng bạn Caro Game!\n".encode('utf-8'))
    player = {"conn": conn, "addr": addr, "symbol": None}
    with lock:
        if len(players) >= 2:
            send(conn, {"type": "info", "message": "Phòng đã đầy mất rồi!"})
            conn.close()
            return
        player["symbol"] = symbols[len(players)]
        players.append(player)
        send(conn, {"type": "assign", "symbol": player["symbol"]})
        print(f"Người chơi {addr} là '{player['symbol']}'")
        
    if len(players) == 2:
        broadcast({
            "type": "start",
            "message": "Trò chơi bắt đầu!",
            "board": board.to_list(),
            "turn": board.turn
        })
    
    try:
        buffer = ""
        while True:
            data = conn.recv(1024)
            if not data:
                print(f"Đã ngắt kết nối!")
                break
            message = data.decode("utf-8").strip()
            print(f"[{addr}] -> {message}")
            # phản hồi lại client
            client_socket.sendall(f"Server nhận: {message}\n".encode("utf-8"))
    except Exception as e:
        print(f"[!] Lỗi với client {addr}: {e}")
    finally:
        client_socket.close()
        print(f"[x] Đóng kết nối với {addr}")           
                   
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((host, port))
print("Đang chờ kết nối...")
server_socket.listen(5)

while True:
    client_socket, addr = server_socket.accept()
    thread = threading.Thread(target=handler_client, args=(client_socket, addr))
    thread.start()
    client_socket.sendall("Chào mừng bạn Caro Game!\n")    

