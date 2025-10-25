import socket
import threading

host = '0.0.0.0'
port = 5000

def handler_client(client_socket, addr):
    print(f"Kết nối từ {addr}")
    client_socket.sendall("Chào mừng bạn Caro Game!\n".encode('utf-8'))
    client_socket.close()
    
    try:
        while True:
            data = client_socket.recv(1024)
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
