import socket
import threading
import json
import re
from datetime import datetime
import uuid

# =====================
# Dữ liệu chuyến chung
# =====================
trips = {
    'BINH DINH -> HCM': {'total_seats': 20, 'booked_seats': {}},
    'HCM -> BINH DINH': {'total_seats': 20, 'booked_seats': {}},
    'DAK LAK -> HCM': {'total_seats': 20, 'booked_seats': {}},
    'HCM -> DAK LAK': {'total_seats': 20, 'booked_seats': {}},
}

lock = threading.Lock()

# =====================
# Helper gửi/nhận JSON
# =====================
def send_json(sock, obj):
    data = json.dumps(obj) + "\n"
    sock.sendall(data.encode("utf-8"))

def recv_json(sock, buffer):
    while "\n" not in buffer:
        chunk = sock.recv(4096).decode("utf-8")
        if not chunk:
            return None, buffer
        buffer += chunk
    line, rest = buffer.split("\n", 1)
    return json.loads(line), rest

# =====================
# Validate
# =====================
def is_valid_phone(phone):
    return bool(re.match(r'^\d{10}$', phone))

def is_valid_name(name):
    return bool(re.match(r'^[A-Za-z\s]{2,}$', name))

def generate_ticket_id():
    return str(uuid.uuid4())[:8]

def handle_client(sock, addr):
    buffer = ""
    client_id = str(uuid.uuid4())  # ID duy nhất cho client
    print(f"[+] Client {addr} kết nối với ID {client_id}")

    try:
        while True:
            req, buffer = recv_json(sock, buffer)
            if req is None:
                if buffer == "":
                    break
                else:
                    continue

            cmd = req.get("command")

            if cmd == "get_client_id":
                send_json(sock, {"status": "success", "client_id": client_id})

            elif cmd == "view_trips":
                with lock:
                    available = {
                        t: info['total_seats'] - len(info['booked_seats'])
                        for t, info in trips.items()
                    }
                send_json(sock, {"status": "success", "trips": available})

            elif cmd == "get_seats":
                trip_id = req.get("trip_id")
                only_mine = req.get("only_mine", False)
                with lock:
                    if trip_id in trips:
                        if only_mine:
                            booked = {int(s): info for s, info in trips[trip_id]['booked_seats'].items()
                                if info['owner_id'] == client_id}
                        else:
                            booked = {int(s): info for s, info in trips[trip_id]['booked_seats'].items()}
                        send_json(sock, {"status": "success", "booked_seats": booked})
                    else:
                        send_json(sock, {"status": "error", "message": "Chuyến không tồn tại"})

            elif cmd == "book_seat":
                trip_id = req.get("trip_id")
                seat_num = req.get("seat_num")
                user_info = req.get("user_info", {})

                with lock:
                    if trip_id not in trips:
                        send_json(sock, {"status": "error", "message": "Chuyến không tồn tại"})
                    elif not is_valid_name(user_info.get("name", "")):
                        send_json(sock, {"status": "error", "message": "Tên không hợp lệ"})
                    elif not is_valid_phone(user_info.get("phone", "")):
                        send_json(sock, {"status": "error", "message": "SĐT không hợp lệ"})
                    elif seat_num < 1 or seat_num > trips[trip_id]['total_seats']:
                        send_json(sock, {"status": "error", "message": "Số ghế không hợp lệ"})
                    elif str(seat_num) in trips[trip_id]['booked_seats']:
                        send_json(sock, {"status": "error", "message": "Ghế đã được đặt"})
                    else:
                        tid = generate_ticket_id()
                        trips[trip_id]['booked_seats'][str(seat_num)] = {
                            "user_info": user_info,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "ticket_id": tid,
                            "owner_id": client_id
                        }
                        send_json(sock, {"status": "success", "message": f"Đặt vé thành công! Mã vé: {tid}"})

            elif cmd == "get_booking_info":
                trip_id = req.get("trip_id")
                seat_num = req.get("seat_num")
                with lock:
                    if trip_id in trips and str(seat_num) in trips[trip_id]['booked_seats']:
                        send_json(sock, {"status": "success", "info": trips[trip_id]['booked_seats'][str(seat_num)]})
                    else:
                        send_json(sock, {"status": "error", "message": "Không tìm thấy thông tin vé"})

            elif cmd == "cancel_booking":
                trip_id = req.get("trip_id")
                seat_num = req.get("seat_num")
                ticket_id = req.get("ticket_id")
                with lock:
                    if trip_id in trips and str(seat_num) in trips[trip_id]['booked_seats']:
                        booking = trips[trip_id]['booked_seats'][str(seat_num)]
                        if booking['ticket_id'] != ticket_id:
                            send_json(sock, {"status": "error", "message": "Mã vé sai"})
                        elif booking['owner_id'] != client_id:
                            send_json(sock, {"status": "error", "message": "Bạn không thể hủy vé của người khác"})
                        else:
                            del trips[trip_id]['booked_seats'][str(seat_num)]
                            send_json(sock, {"status": "success", "message": "Hủy vé thành công"})
                    else:
                        send_json(sock, {"status": "error", "message": "Không tìm thấy vé"})

            else:
                send_json(sock, {"status": "error", "message": "Lệnh không hợp lệ"})

    except Exception as e:
        print(f"[!] Lỗi với client {addr}: {e}")
    finally:
        sock.close()
        print(f"[-] Client {addr} ngắt kết nối")

def start_server(host='localhost', port=5555):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"Server chạy tại {host}:{port}")
    try:
        while True:
            client_sock, addr = server.accept()
            threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("Tắt server.")
    finally:
        server.close()

if __name__ == "__main__":
    start_server()
