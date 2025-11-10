import json, socket, threading
from board import Board

HOST = "127.0.0.1"
PORT = 5000

lock = threading.Lock()
# rooms: { room_name: { "board": Board(), "players": [ {"conn":..., "addr":..., "symbol": "X"|"O"} ] } }
rooms = {}

def _send(conn, obj):
    try:
        conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except:
        pass

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
                # client đóng đột ngột / mạng rớt
                break
            if not data:
                # client đóng bình thường
                break

            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n",1)
                line = line.strip()
                if not line: continue

                msg = None
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    parts = line.split()
                    if parts and parts[0].upper()=="RESET":
                        if room_name and player:
                            with lock:
                                room = rooms.get(room_name)
                                if room and len(room["players"]) == 2:
                                    _start_game_locked(room)
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})
                        continue
                    if parts and parts[0].upper()=="MOVE" and len(parts)>=3:
                        if room_name and player:
                            room = rooms.get(room_name)
                            if room:
                                _handle_move(room, player, int(parts[1]), int(parts[2]))
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})
                        continue
                    _send(conn, {"type":"error","message":"Lệnh không hợp lệ"})
                    continue

                if msg:
                    t = msg.get("type","")
                    if t == "join":
                        requested = str(msg.get("room","default"))
                        with lock:
                            room = rooms.get(requested)
                            if not room:
                                room = {"board": Board(), "players": []}
                                rooms[requested] = room

                            if len(room["players"]) >= 2:
                                _send(conn, {"type":"error","message":"Phòng đã đủ 2 người"})
                                try: conn.close()
                                except: pass
                                print("[SERVER] Từ chối người thứ 3", addr, "-> room:", requested)
                                return

                            sym = _assign_symbol_locked(room)
                            if sym is None:
                                _send(conn, {"type":"error","message":"Phòng đã đủ người"})
                                try: conn.close()
                                except: pass
                                return

                            player = {"conn": conn, "addr": addr, "symbol": sym}
                            room["players"].append(player)
                            room_name = requested
                            print(f"[SERVER] {addr} vào phòng '{room_name}' -> {sym}")
                            _send(conn, {"type":"welcome","room":room_name,"symbol":sym})

                            if len(room["players"]) == 2:
                                _start_game_locked(room)
                            else:
                                _send(conn, {"type":"info","message":"Đang đợi người chơi thứ hai...", "win_line": None})

                    elif t == "move":
                        if room_name and player:
                            room = rooms.get(room_name)
                            if room: _handle_move(room, player, int(msg["x"]), int(msg["y"]))
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})

                    elif t == "reset":
                        if room_name and player:
                            with lock:
                                room = rooms.get(room_name)
                                if room and len(room["players"]) == 2:
                                    _start_game_locked(room)
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})

                    elif t == "sync":
                        if room_name:
                            with lock:
                                room = rooms.get(room_name)
                                if room:
                                    b = room["board"]
                                    _send(conn, {"type":"update","board":b.to_list(),"turn":b.turn,
                                                 "winner":b.winner,"draw":b.is_draw(),"win_line":b.win_line})
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})
                    else:
                        _send(conn, {"type":"error","message":"Lệnh không hợp lệ"})
    finally:
        try: conn.close()
        except: pass
        if room_name and player:
            _cleanup_player(room_name, player)
        print("[SERVER] Ngắt kết nối", addr)

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # best-effort keepalive
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except: pass
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
