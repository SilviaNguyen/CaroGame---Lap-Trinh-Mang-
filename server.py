import json, socket, threading
from board import Board

HOST = "127.0.0.1"
PORT = 5000

lock = threading.Lock()
rooms = {}  # { room_name: { "board": Board(), "players": [...] } }

def _send(conn, obj):
    try: conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except: pass

def _broadcast(room, obj):
    for p in room["players"]:
        _send(p["conn"], obj)

def _start_game_locked(room):
    room["board"].reset()
    room["board"].turn = "X"
    _broadcast(room, {
        "type": "start",
        "message": "Trò chơi bắt đầu!",
        "board": room["board"].to_list(),
        "turn": room["board"].turn,
        "win_line": None
    })

def _assign_symbol_locked(room):
    used = {p["symbol"] for p in room["players"]}
    if "X" not in used: return "X"
    if "O" not in used: return "O"
    return None

def _handle_move(room, player, x, y):
    with lock:
        board = room["board"]

        if player not in room["players"]:
            _send(player["conn"], {"type":"error","message":"Bạn không còn trong phòng"})
            return

        if board.winner:
            _send(player["conn"], {"type":"error","message":"Ván đã kết thúc"})
            return

        if board.turn != player["symbol"]:
            _send(player["conn"], {"type":"error","message":"Chưa đến lượt bạn"})
            return

        ok = board.place(x, y, player["symbol"])
        if not ok:
            _send(player["conn"], {"type":"error","message":"Nước đi không hợp lệ"})
            return

        upd = {
            "type": "update",
            "board": board.to_list(),
            "turn": board.turn,
            "winner": board.winner,
            "draw": board.is_draw(),
            "win_line": board.win_line
        }

    _broadcast(room, upd)

    if upd["winner"]:
        _broadcast(room, {"type":"end","message":f"Người chơi {upd['winner']} thắng!", "win_line": upd["win_line"]})
    elif upd["draw"]:
        _broadcast(room, {"type":"end","message":"Hòa!", "win_line": None})

def _cleanup_player(room_name, player):
    with lock:
        room = rooms.get(room_name)
        if not room: return
        if player in room["players"]:
            room["players"].remove(player)
        room["board"].reset()
        _broadcast(room, {"type":"info","message":f"{player['symbol']} đã rời phòng. Sẽ tạo ván mới khi đủ 2 người.", "win_line": None})
        if not room["players"]:
            del rooms[room_name]

def _handle_client(conn, addr):
    print("[SERVER] Kết nối từ", addr)
    buf = ""
    room_name = None
    player = None

    try:
        while True:
            try:
                data = conn.recv(4096)
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
            if not data:
                break

            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
    finally:
        try: conn.close()
        except: pass
        if room_name and player:
            _cleanup_player(room_name, player)
        print("[SERVER] Ngắt kết nối", addr)

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(64)
    print(f"[SERVER] Listening on {HOST}:{PORT}")
    try:
        while True:
            c, a = s.accept()
            threading.Thread(target=_handle_client, args=(c, a), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    main()
