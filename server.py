import json, socket, threading, time, random, string
from board import Board

HOST = "127.0.0.1"
PORT = 5000
lock = threading.Lock()
rooms = {}
conn_map = {}
mm_queue = []
TURN_SECONDS = 30

def _send(conn, obj):
    try:
        conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except:
        pass

def _broadcast(room, obj):
    for p in room["players"]:
        _send(p["conn"], obj)

def _gen_room_id(prefix="MM", length=4):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-" + "".join(random.choices(chars, k=length))

def _set_deadline(room, seconds=TURN_SECONDS):
    room["deadline"] = time.time() + seconds

def room_id_of(room):
    for k,v in rooms.items():
        if v is room:
            return k
    return "?"

def _start_game_locked(room):
    room["board"].reset()
    room["board"].turn = "X"
    _set_deadline(room)
    print(f"[SERVER] Start game in {room_id_of(room)} | turn=X deadline={int(room['deadline'])}")
    _broadcast(room, {
        "type":"start",
        "message":"Trò chơi bắt đầu!",
        "board":room["board"].to_list(),
        "turn":room["board"].turn,
        "win_line":None,
        "deadline": room["deadline"],
        "turn_seconds": TURN_SECONDS
    })

def _assign_symbol_for(room):
    used = {p["symbol"] for p in room["players"]}
    if "X" not in used: return "X"
    if "O" not in used: return "O"
    return None

def _join_room_locked(room_id, conn, addr, force_symbol=None):
    room = rooms.get(room_id)
    if not room:
        room = {"board": Board(), "players": [], "deadline": None}
        rooms[room_id] = room
    if len(room["players"]) >= 2:
        _send(conn, {"type":"error","message":"Phòng đã đủ 2 người"})
        return None, None
    sym = force_symbol if force_symbol else _assign_symbol_for(room)
    if sym is None:
        _send(conn, {"type":"error","message":"Phòng đã đủ người"})
        return None, None
    player = {"conn": conn, "addr": addr, "symbol": sym}
    room["players"].append(player)
    conn_map[conn] = {"room": room_id, "player": player}
    print(f"[SERVER] Join room {room_id} | {addr} -> {sym}")
    _send(conn, {"type":"welcome","room":room_id,"symbol":sym})
    if len(room["players"]) == 2:
        print(f"[SERVER] Matched room {room_id} | players: {[p['symbol'] for p in room['players']]}")
        _start_game_locked(room)
    else:
        _send(conn, {"type":"info","message":"Đang đợi người chơi thứ hai...","win_line":None})
    return room, player

def _leave_queue_locked(conn):
    removed = False
    for i in range(len(mm_queue)-1, -1, -1):
        if mm_queue[i]["conn"] is conn:
            mm_queue.pop(i); removed = True
    if removed:
        print("[SERVER] Queue: removed client")
        _send(conn, {"type":"info","message":"Đã rời hàng đợi"})

def _try_match_locked():
    while len(mm_queue) >= 2:
        a = mm_queue.pop(0); b = mm_queue.pop(0)
        c1, a1 = a["conn"], a["addr"]
        c2, a2 = b["conn"], b["addr"]
        if c1 in conn_map or c2 in conn_map:
            continue
        room_id = _gen_room_id("MM")
        print(f"[SERVER] Queue matched -> {room_id}")
        _join_room_locked(room_id, c1, a1, "X")
        _join_room_locked(room_id, c2, a2, "O")
        _send(c1, {"type":"info","message":f"Đã ghép cặp • Phòng: {room_id}"})
        _send(c2, {"type":"info","message":f"Đã ghép cặp • Phòng: {room_id}"})

def _handle_move(room, player, x, y):
    board = room["board"]
    if player not in room["players"]:
        _send(player["conn"], {"type":"error","message":"Bạn không còn trong phòng"}); return
    if board.winner:
        _send(player["conn"], {"type":"error","message":"Ván đã kết thúc"}); return
    if board.turn != player["symbol"]:
        _send(player["conn"], {"type":"error","message":"Chưa đến lượt bạn"}); return
    if not board.place(x, y, player["symbol"]):
        _send(player["conn"], {"type":"error","message":"Nước đi không hợp lệ"}); return
    _set_deadline(room)
    print(f"[SERVER] Move {room_id_of(room)} | {player['symbol']} -> ({x},{y}) next={board.turn}")
    upd = {
        "type":"update",
        "board":board.to_list(),
        "turn":board.turn,
        "winner":board.winner,
        "draw":board.is_draw(),
        "win_line":board.win_line,
        "deadline": room["deadline"],
        "turn_seconds": TURN_SECONDS
    }
    _broadcast(room, upd)
    if upd["winner"]:
        print(f"[SERVER] Win {room_id_of(room)} -> {upd['winner']}")
        _broadcast(room, {"type":"end","message":f"Người chơi {upd['winner']} thắng!","win_line":upd["win_line"]})
    elif upd["draw"]:
        print(f"[SERVER] Draw {room_id_of(room)}")
        _broadcast(room, {"type":"end","message":"Hòa!","win_line":None})

def _timeout_check_loop():
    while True:
        time.sleep(0.25)
        now = time.time()
        with lock:
            for room_id, room in list(rooms.items()):
                board = room["board"]
                if len(room["players"]) < 2:
                    continue
                if board.winner or board.is_draw():
                    continue
                dl = room.get("deadline")
                if not dl:
                    continue
                if now >= dl:
                    loser = board.turn
                    winner = "O" if loser == "X" else "X"
                    board.winner = winner
                    print(f"[SERVER] Timeout {room_id} | {loser} lose -> {winner} win")
                    _broadcast(room, {
                        "type":"update",
                        "board":board.to_list(),
                        "turn":board.turn,
                        "winner":board.winner,
                        "draw":board.is_draw(),
                        "win_line":board.win_line,
                        "deadline": dl,
                        "turn_seconds": TURN_SECONDS
                    })
                    _broadcast(room, {"type":"end","message":f"{loser} hết giờ • {winner} thắng!","win_line":board.win_line})

def _cleanup_conn(conn):
    with lock:
        _leave_queue_locked(conn)
        info = conn_map.pop(conn, None)
        if not info: return
        room_id = info["room"]; player = info["player"]
        room = rooms.get(room_id)
        if not room: return
        if player in room["players"]:
            room["players"].remove(player)
        room["board"].reset()
        room["deadline"] = None
        print(f"[SERVER] Client left | room {room_id} {player['symbol']}")
        _broadcast(room, {"type":"info","message":f"{player['symbol']} đã rời phòng. Sẽ tạo ván mới khi đủ 2 người.","win_line":None})
        if not room["players"]:
            del rooms[room_id]
            print(f"[SERVER] Room {room_id} closed")

def _handle_client(conn, addr):
    print(f"[SERVER] Connect {addr}")
    buf = ""
    try:
        while True:
            try:
                data = conn.recv(4096)
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
            if not data: break
            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n",1)
                line = line.strip()
                if not line: continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    _send(conn, {"type":"error","message":"Lệnh không hợp lệ"}); continue
                t = msg.get("type","")
                if t == "queue":
                    action = msg.get("action","join")
                    with lock:
                        if action == "join":
                            if not any(item["conn"] is conn for item in mm_queue):
                                mm_queue.append({"conn": conn, "addr": addr})
                                print(f"[SERVER] Queue join {addr}")
                                _send(conn, {"type":"info","message":"Đã vào hàng đợi ghép cặp"})
                                _try_match_locked()
                            else:
                                _send(conn, {"type":"info","message":"Đang ở hàng đợi"})
                        elif action == "leave":
                            print(f"[SERVER] Queue leave {addr}")
                            _leave_queue_locked(conn)
                        else:
                            _send(conn, {"type":"error","message":"Hành động không hợp lệ"})
                elif t == "move":
                    with lock:
                        cm = conn_map.get(conn)
                        if cm:
                            room = rooms.get(cm["room"])
                            if room: _handle_move(room, cm["player"], int(msg["x"]), int(msg["y"]))
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})
                elif t == "reset":
                    with lock:
                        cm = conn_map.get(conn)
                        if cm:
                            room = rooms.get(cm["room"])
                            if room and len(room["players"]) == 2:
                                print(f"[SERVER] Reset room {cm['room']}")
                                _start_game_locked(room)
                        else:
                            _send(conn, {"type":"error","message":"Chưa tham gia phòng"})
                elif t == "sync":
                    with lock:
                        cm = conn_map.get(conn)
                        if cm:
                            room = rooms.get(cm["room"])
                            if room:
                                b = room["board"]
                                _send(conn, {
                                    "type":"update",
                                    "board":b.to_list(),
                                    "turn":b.turn,
                                    "winner":b.winner,
                                    "draw":b.is_draw(),
                                    "win_line":b.win_line,
                                    "deadline": room.get("deadline"),
                                    "turn_seconds": TURN_SECONDS
                                })
                        else:
                            _send(conn, {"type":"info","message":"Bạn chưa ở phòng nào. Đang xếp hàng ghép cặp..."})
                else:
                    _send(conn, {"type":"error","message":"Lệnh không hợp lệ"})
    finally:
        try: conn.close()
        except: pass
        _cleanup_conn(conn)
        print(f"[SERVER] Disconnect {addr}")

def main():
    threading.Thread(target=_timeout_check_loop, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
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
        print("[SERVER] Stopped")

if __name__ == "__main__":
    main()
