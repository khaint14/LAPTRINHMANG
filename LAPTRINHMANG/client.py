import socket
import json
import tkinter as tk
from tkinter import messagebox, ttk
import re
import pyperclip

SERVER_HOST = 'localhost'
SERVER_PORT = 5555

def send_json(sock, obj):
    data = json.dumps(obj) + '\n'
    sock.sendall(data.encode('utf-8'))

def recv_json(sock, buffer):
    while '\n' not in buffer:
        chunk = sock.recv(4096).decode('utf-8')
        if not chunk:
            return None, buffer
        buffer += chunk
    line, rest = buffer.split('\n', 1)
    return json.loads(line), rest

class TicketBookingClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Hệ thống Đặt Vé Xe (Client1)")
        self.root.geometry("900x650")
        self.root.configure(bg="#f6f8fa")
        self.buffer = ''
        self.client_id = None

        self.connect_to_server()
        self.get_client_id()
        self.selected_trip = None
        self.seat_rects = {}

        self.setup_ui()
        self.view_trips()

    def connect_to_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_HOST, SERVER_PORT))
        except Exception as e:
            messagebox.showerror("Lỗi kết nối", f"Không thể kết nối server: {e}")
            self.root.quit()

    def get_client_id(self):
        send_json(self.sock, {"command": "get_client_id"})
        resp, self.buffer = recv_json(self.sock, self.buffer)
        if resp and resp.get("status") == "success":
            self.client_id = resp["client_id"]

    def refresh_all(self):
        self.view_trips()
        if self.selected_trip:
            self.display_seats()


    def setup_ui(self):
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill='x')
        ttk.Label(top, text="HỆ THỐNG ĐẶT VÉ XE", font=("Helvetica", 18, "bold")).pack(side='left')
        ttk.Button(top, text="Cập nhật", command=self.refresh_all).pack(side='right', padx=4)
        ttk.Button(top, text="Thoát", command=self.quit).pack(side='right', padx=4)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill='both', expand=True)

        # Left: trips
        left = ttk.Frame(main)
        left.pack(side='left', fill='y', padx=(0,12))

        ttk.Label(left, text="Danh sách chuyến", font=("Helvetica", 12, "bold")).pack(pady=(0,6))
        self.trip_tree = ttk.Treeview(left, columns=("trip","free"), show='headings', height=12)
        self.trip_tree.heading('trip', text='Chuyến')
        self.trip_tree.heading('free', text='Ghế trống')
        self.trip_tree.column('trip', width=260)
        self.trip_tree.column('free', width=80, anchor='center')
        self.trip_tree.pack(fill='y')
        self.trip_tree.bind('<<TreeviewSelect>>', self.on_trip_select)

        # Remove "Add trip" and "Delete trip" buttons → user only view/select
        ttk.Button(left, text="Xem vé", command=self.view_all_bookings).pack(pady=8)

        # Right: seat map
        right = ttk.Frame(main)
        right.pack(side='left', fill='both', expand=True)

        self.seat_label = ttk.Label(right, text="Sơ đồ ghế (chọn chuyến)", font=("Helvetica", 14, "bold"))
        self.seat_label.pack(pady=6)

        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg='white', height=420)
        self.canvas.pack(side='left', fill='both', expand=True, padx=(0,6))
        self.info_area = tk.Text(canvas_frame, width=36, state='disabled', wrap='word')
        self.info_area.pack(side='right', fill='y')

        status = ttk.Frame(right, padding=6)
        status.pack(fill='x', pady=6)
        ttk.Label(status, text="■ Ghế trống", foreground='green').pack(side='left', padx=6)
        ttk.Label(status, text="■ Ghế đã đặt", foreground='red').pack(side='left', padx=6)

    def send_request(self, request):
        try:
            send_json(self.sock, request)
            obj, self.buffer = recv_json(self.sock, self.buffer)
            return obj
        except Exception as e:
            messagebox.showerror("Lỗi", f"Lỗi khi giao tiếp server: {e}")
            return {'status':'error','message':str(e)}

    def view_trips(self):
        resp = self.send_request({'command':'view_trips'})
        if resp.get('status') == 'success':
            server_trips = resp.get('trips', {})
            for it in self.trip_tree.get_children():
                self.trip_tree.delete(it)
            for trip_id, free in server_trips.items():
                self.trip_tree.insert('', 'end', values=(trip_id, free))
        else:
            messagebox.showerror("Lỗi", resp.get('message','Không xác định'))

    def on_trip_select(self, event):
        sel = self.trip_tree.selection()
        if not sel:
            return
        self.selected_trip = self.trip_tree.item(sel[0])['values'][0]
        self.seat_label.config(text=f"Sơ đồ ghế cho chuyến: {self.selected_trip}")
        self.display_seats()

    def display_seats(self):
        if not self.selected_trip:
            messagebox.showwarning("Cảnh báo", "Chọn chuyến trước nhé.")
            return
        resp = self.send_request({'command':'get_seats','trip_id':self.selected_trip})
        if resp.get('status') == 'success':
            booked_info = resp.get('booked_seats', {})
            booked = {num:info for num,info in booked_info.items()}
            self.draw_seat_map(booked)
        else:
            messagebox.showerror("Lỗi", resp.get('message','Không xác định'))

    def draw_seat_map(self, booked):
        self.canvas.delete('all')
        self.seat_rects.clear()
        seat_size = 60
        padding = 14
        rows = 5
        cols = 4
        for r in range(rows):
            for c in range(cols):
                num = r*cols + c + 1
                x1 = c*(seat_size+padding)+padding
                y1 = r*(seat_size+padding)+padding
                x2 = x1 + seat_size
                y2 = y1 + seat_size

                if str(num) in booked:
                # Kiểm tra chủ sở hữu ghế
                    if booked[str(num)]['owner_id'] == self.client_id:
                        color = 'yellow'   # Ghế của mình
                    else:
                        color = 'red'      # Ghế của người khác
                else:
                    color = 'green'        # Ghế trống

                rect = self.canvas.create_rectangle(x1, y1, x2, y2,
                                                fill=color, outline='black',
                                                tags=('seat', str(num)))
                self.canvas.create_text((x1+x2)/2, (y1+y2)/2,
                                    text=str(num), font=('Helvetica',14,'bold'))
                self.seat_rects[num] = rect

                if color == 'green':
                    self.canvas.tag_bind(rect, '<Button-1>',
                                     lambda e, n=num: self.open_booking_dialog(n))
                elif color == 'yellow':
                    self.canvas.tag_bind(rect, '<Button-1>',
                                     lambda e, n=num: self.try_cancel(n, booked[str(n)]))
                    self.canvas.tag_bind(rect, '<Enter>',
                                     lambda e, n=num: self.show_booking_info(booked[str(n)]))
                    self.canvas.tag_bind(rect, '<Leave>', lambda e: self.clear_info_area())
                elif color == 'red':
                    self.canvas.tag_bind(rect, '<Enter>',
                                     lambda e, n=num: self.show_booking_info(booked[str(n)]))
                    self.canvas.tag_bind(rect, '<Leave>', lambda e: self.clear_info_area())


    def open_booking_dialog(self, seat_num):
        dialog = tk.Toplevel(self.root)
        dialog.title("Đặt vé")
        dialog.geometry("420x260")
        ttk.Label(dialog, text=f"Chuyến: {self.selected_trip}", font=('Helvetica',12,'bold')).pack(pady=8)
        ttk.Label(dialog, text=f"Ghế: {seat_num}").pack()
        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text="Tên:").grid(row=0,column=0,sticky='w')
        name_entry = ttk.Entry(frm, width=30); name_entry.grid(row=0,column=1,padx=6,pady=6)
        ttk.Label(frm, text="SĐT (10 số):").grid(row=1,column=0,sticky='w')
        phone_entry = ttk.Entry(frm, width=30); phone_entry.grid(row=1,column=1,padx=6,pady=6)

        def confirm():
            name = name_entry.get().strip()
            phone = phone_entry.get().strip()
            if not re.match(r'^[A-Za-z\s]{2,}$', name):
                messagebox.showwarning("Lỗi", "Tên không hợp lệ.", parent=dialog); return
            if not re.match(r'^\d{10}$', phone):
                messagebox.showwarning("Lỗi", "SĐT phải 10 chữ số.", parent=dialog); return
            resp = self.send_request({'command':'book_seat','trip_id':self.selected_trip,'seat_num':seat_num,'user_info':{'name':name,'phone':phone}})
            if resp.get('status')=='success':
                msg = resp.get('message','')
                ticket = msg.split('Mã vé:')[-1].strip() if 'Mã vé:' in msg else ''
                messagebox.showinfo("Thành công", msg, parent=dialog)
                if ticket:
                    pyperclip.copy(ticket)
                dialog.destroy()
                self.display_seats()
                self.view_trips()
            else:
                messagebox.showerror("Lỗi", resp.get('message','Không xác định'), parent=dialog)

        ttk.Button(dialog, text="Đặt vé", command=confirm).pack(pady=6)
        ttk.Button(dialog, text="Hủy", command=dialog.destroy).pack()

    def try_cancel(self, seat_num, booking_info):
        if booking_info.get("owner_id") != self.client_id:
            messagebox.showwarning("Không thể hủy", "Bạn không thể hủy vé của người khác.")
            return
        self.open_cancel_dialog(seat_num)

    def show_booking_info(self, info):
        txt = f"Tên: {info['user_info']['name']}\nSĐT: {info['user_info']['phone']}\nThời gian: {info['timestamp']}\nMã vé: {info['ticket_id']}\n"
        self.info_area.config(state='normal'); self.info_area.delete('1.0','end'); self.info_area.insert('end', txt); self.info_area.config(state='disabled')

    def clear_info_area(self):
        self.info_area.config(state='normal'); self.info_area.delete('1.0','end'); self.info_area.config(state='disabled')

    def open_cancel_dialog(self, seat_num):
        dialog = tk.Toplevel(self.root); dialog.title("Hủy vé"); dialog.geometry("420x260")
        ttk.Label(dialog, text=f"Chuyến: {self.selected_trip}").pack(pady=6)
        ttk.Label(dialog, text=f"Ghế: {seat_num}").pack()
        ttk.Label(dialog, text="Nhập mã vé:").pack(pady=6)
        entry = ttk.Entry(dialog, width=30); entry.pack()
        def do_cancel():
            code = entry.get().strip()
            if not code:
                messagebox.showwarning("Lỗi", "Nhập mã vé để xác nhận.", parent=dialog); return
            resp2 = self.send_request({'command':'cancel_booking','trip_id':self.selected_trip,'seat_num':seat_num,'ticket_id':code})
            if resp2.get('status')=='success':
                messagebox.showinfo("Thành công", resp2.get('message'), parent=dialog)
                dialog.destroy(); self.display_seats(); self.view_trips()
            else:
                messagebox.showerror("Lỗi", resp2.get('message'), parent=dialog)
        ttk.Button(dialog, text="Xác nhận hủy", command=do_cancel).pack(pady=6)
        ttk.Button(dialog, text="Hủy", command=dialog.destroy).pack()

    def view_all_bookings(self):
        if not self.selected_trip:
            messagebox.showwarning("Cảnh báo", "Chọn chuyến đã.")
            return
        resp = self.send_request({
            'command': 'get_seats',
            'trip_id': self.selected_trip,
            'only_mine': True
        })
        if resp.get('status') == 'success':
            dialog = tk.Toplevel(self.root)
            dialog.title("Vé của tôi")
            dialog.geometry("500x400")
            text = tk.Text(dialog, wrap='word')
            text.pack(fill='both', expand=True)
            bookings = resp.get('booked_seats', {})
            if not bookings:
                text.insert('end', 'Bạn chưa đặt vé nào.\n')
            else:
                for seat, info in sorted(bookings.items(), key=lambda x: int(x[0])):
                    user = info['user_info']
                    ts = info['timestamp']
                    tid = info['ticket_id']
                    text.insert('end', f"Ghế {seat}: {user['name']} - {user['phone']} - {ts} - mã: {tid}\n\n")
            text.config(state='disabled')
        else:
            messagebox.showerror("Lỗi", resp.get('message', ''))


    def quit(self):
        try:
            self.sock.close()
        except:
            pass
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    style.theme_use('clam')
    app = TicketBookingClient(root)
    root.mainloop()
