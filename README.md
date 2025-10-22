# CaroGame---Lap-Trinh-Mang-
Project Ket Thuc Mon Hoc - Lap Trinh Mang

# CARO LAN GAME  
## Môn: Lập Trình Mạng – Python Socket Programming

### 1. Giới thiệu

Dự án **CARO LAN GAME** được xây dựng nhằm minh họa các kiến thức về **lập trình mạng TCP/IP**, **xử lý song song bằng luồng (threading)** và **tích hợp hệ thống (System Integration)** trong Python.  
Ứng dụng cho phép **hai người chơi** tham gia cùng một ván Caro qua mạng LAN (hoặc chạy trên cùng máy tính).  

Mục tiêu của đề tài:
- Xây dựng **core mechanics** của game Caro (Gomoku).
- Ứng dụng **socket TCP** để truyền thông giữa Client và Server.
- Tích hợp hoàn chỉnh ba lớp: **Logic – Network – Giao diện (GUI)**.
- Cung cấp nền tảng có thể mở rộng thành hệ thống nhiều phòng, có chat, thời gian, và lưu lịch sử.

---

### 2. Cấu trúc dự án

caro-net/
│
├── board.py # Xử lý logic bàn cờ, kiểm tra thắng/thua
├── server.py # Chương trình Server – quản lý kết nối, cập nhật trạng thái
├── client_pygame.py # Chương trình Client – giao diện PyGame và socket client
├── requirements.txt # Danh sách thư viện cần cài đặt
└── README.md # Tài liệu hướng dẫn


---

### 3. Công nghệ sử dụng

| Thành phần | Vai trò |
|-------------|----------|
| Python 3.9+ | Ngôn ngữ lập trình chính |
| Socket TCP/IP | Giao tiếp giữa server và client |
| JSON Protocol | Định dạng truyền dữ liệu |
| Threading | Xử lý đồng thời nhiều client |
| PyGame | Thư viện hiển thị và xử lý sự kiện giao diện |

---

### 4. Kiến trúc hệ thống (System Integration)

#### 4.1. Mô hình tổng quát

+---------------------+ TCP Socket +----------------------+
| Client A | <--------------------> | Server |
| (PyGame Interface) | | (Board + Threading) |
+---------------------+ +----------------------+
| |
| |
| TCP Socket |
| |
v v
+---------------------+ +----------------------+
| Client B | | Board Logic (X/O) |
| (PyGame Interface) | | - Check win |
+---------------------+ | - Validate move |
+----------------------+


#### 4.2. Thành phần chính

- **Board (board.py)**  
  Quản lý toàn bộ bàn cờ, kiểm tra thắng/thua, điều khiển lượt đi.  
  Hỗ trợ cấu hình kích thước (15x15) và số lượng quân thắng (5 liên tiếp).

- **Server (server.py)**  
  - Khởi tạo socket TCP.  
  - Quản lý danh sách người chơi.  
  - Gán ký hiệu “X” và “O”.  
  - Phát thông tin trạng thái sau mỗi nước đi.  
  - Duy trì trò chơi đồng bộ giữa các client.

- **Client (client_pygame.py)**  
  - Kết nối tới server, gửi yêu cầu tham gia.  
  - Hiển thị bàn cờ, xử lý thao tác chuột.  
  - Gửi nước đi và nhận cập nhật theo thời gian thực.

---

### 5. Giao thức truyền thông (JSON Protocol)

#### 5.1. Client → Server

| Loại | Mô tả | Ví dụ |
|------|--------|-------|
| `join` | Tham gia phòng | `{"type":"join","name":"Alice"}` |
| `move` | Gửi nước đi | `{"type":"move","x":7,"y":10}` |
| `chat` | Gửi tin nhắn | `{"type":"chat","msg":"hello"}` |

#### 5.2. Server → Client

| Loại | Mô tả | Ví dụ |
|------|--------|-------|
| `assign` | Gán ký hiệu cho người chơi | `{"type":"assign","symbol":"X","your_turn":true}` |
| `state` | Cập nhật trạng thái bàn cờ | `{"type":"state","board":[...],"turn":"O","winner":null}` |
| `start` | Bắt đầu ván mới | `{"type":"start","size":15,"win_len":5}` |
| `chat` | Tin nhắn từ người khác | `{"type":"chat","from":"Bob","msg":"Hi!"}` |
| `error` | Thông báo lỗi | `{"type":"error","message":"illegal move"}` |

---

### 6. Hướng dẫn cài đặt và chạy chương trình

#### 6.1. Cài đặt môi trường

python -m venv .venv
source .venv/Scripts/activate        # Windows
# hoặc
source .venv/bin/activate            # Linux/macOS

pip install -r requirements.txt

6.2. Chạy Server

python server.py --host 0.0.0.0 --port 5000 --size 15 --win 5

6.3. Chạy Client

    Trên cùng một máy:

python client_pygame.py --server 127.0.0.1 --port 5000 --name Alice
python client_pygame.py --server 127.0.0.1 --port 5000 --name Bob

    Qua mạng LAN (thay 127.0.0.1 bằng địa chỉ IP của máy chạy server):

python client_pygame.py --server 192.168.1.20 --port 5000 --name Player1

7. Luồng hoạt động

    Hai client kết nối tới server.

    Server gán ký hiệu X và O cho người chơi.

    Người chơi X đi trước, gửi tọa độ nước đi.

    Server kiểm tra tính hợp lệ, cập nhật bàn cờ và gửi lại trạng thái cho cả hai bên.

    Khi một người chơi có 5 quân liên tiếp, server xác định người thắng và thông báo kết quả.

8. Mở rộng đề xuất
Tính năng	Mô tả
Nhiều phòng chơi:	Quản lý nhiều trận Caro cùng lúc trên server
Giao diện chat:	Cho phép trò chuyện trực tiếp trong cửa sổ PyGame
Giới hạn thời gian:	Thêm bộ đếm thời gian cho mỗi lượt đi
Ghi log ván chơi:	Lưu lịch sử nước đi vào tệp JSON hoặc Excel
Kết nối internet:	Mở cổng và chơi qua IP công cộng hoặc VPS

    Công cụ: Visual Studio Code / PyCharm

    Năm học: 2025
