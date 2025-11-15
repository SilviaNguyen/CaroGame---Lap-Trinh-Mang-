import json, socket, threading, time

HOST, PORT = "127.0.0.1", 5000

def read_line(sock):
    buf = b""
    while True:
        ch = sock.recv(1)
        if not ch: return None
        buf += ch
        if ch == b"\n": return json.loads(buf.decode().strip())

def start_server_thread():
    import server as srv
    # nếu server.py có hàm main(host, port, size, win) thì gọi; nếu không, import side-effect mở listener.
    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    time.sleep(0.5)

def test_two_clients_flow():
    start_server_thread()

    a = socket.create_connection((HOST, PORT))
    b = socket.create_connection((HOST, PORT))
    a.sendall(b'{"type":"join","name":"A"}\n')
    b.sendall(b'{"type":"join","name":"B"}\n')

    msg_a = read_line(a)   # expect 'assign' cho A
    msg_b = read_line(b)   # expect 'assign' cho B
    assert msg_a["type"] == "assign" and msg_b["type"] == "assign"

    # người có your_turn = True đi trước:
    first = a if msg_a.get("your_turn") else b
    first.sendall(b'{"type":"move","x":7,"y":7}\n')

    st_a = read_line(a)
    st_b = read_line(b)
    assert st_a["type"] == "state" and st_b["type"] == "state"

def test_undo_contract_simple():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM )
    s.connect(("127.0.0.1", 5000))
    s.sendall((json.dumps({"type":"join", "name":"t1", "room":"default"})+ "\n").encode("utf-8"))

    s.sendall((json.dumps({"type":"move", "x":0, "y":0}) + "\n").encode("utf-8"))
    time.sleep(0.1)

    s.sendall((json.dumps({"type":"undo"}) + "\n").encode("utf-8"))
    s.settimeout(0.5)
    data = s.recv(4096).decode("utf-8")
    assert "error" not in data.lower()
    s.close()