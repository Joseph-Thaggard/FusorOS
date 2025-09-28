import tkinter as tk
from datetime import datetime
import csv
from tkinter import ttk
import serial
import threading
import time
import sys
import os
import cv2
import matplotlib
import subprocess
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque
from PIL import Image, ImageTk

stop_threads = False

# === CONFIG ===
SERIAL_PORT = '/dev/cu.usbmodem11301'
BAUD_RATE = 9600
PLOT_WINDOW = 30
BOOL_MFC = False

# === Create run-specific output folder ===
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
run_dir = os.path.abspath(f"run_{timestamp_str}")
os.makedirs(run_dir, exist_ok=True)
print(f"[INFO] Data for this run will be saved to: {run_dir}")

# === Serial Setup ===
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# === State ===
valve_state = {"fuel": False, "vacuum": False}
telemetry = deque(maxlen=1000)
mfc_setpoint = 0.0
mfc_setpoint_history = deque(maxlen=1000)

log_file_path = os.path.join(run_dir, "fusor_log.csv")
log_file = open(log_file_path, mode="w", newline="")
log_writer = csv.writer(log_file)
log_writer.writerow(["Time", "Action", "Pin", "Value"])

terminal_log_path = os.path.join(run_dir, "terminal_log.csv")
terminal_log_file = open(terminal_log_path, mode="w", newline="")
terminal_log_writer = csv.writer(terminal_log_file)
terminal_log_writer.writerow(["Time", "Raw Line"])

video_path = os.path.join(run_dir, "camera_recording.mp4")
video_writer = None
frame_width = 640
frame_height = 480
fps = 30

def send_command(cmd):
    ser.write((cmd + '\n').encode())

def safe_exit():
    global stop_threads
    try:
        stop_threads = True
        if ser.is_open:
            send_command("SAFE_STATE")
            time.sleep(0.1)
            ser.close()
    except Exception as e:
        print(f"Error during exit: {e}")
    log_file.close()
    terminal_log_file.close()
    if video_writer:
        video_writer.release()
    cap.release()
    print("Logging stopped. Cleaning CSV...")
    try:
        subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "clean_csv.py"), terminal_log_path],
            check=True
            )
        print("CSV cleaning completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error while cleaning CSV: {e}")
    root.quit()

root = tk.Tk()
root.title("Plasma Generator Control Panel")
root.geometry("1400x700")

main_frame = ttk.Frame(root)
main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

left_frame = ttk.Frame(main_frame)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
log_box = tk.Text(left_frame, height=10, width=40, state=tk.DISABLED)
log_box.pack(pady=10)

state_label = tk.Label(left_frame, text="", font=("Arial", 12), justify="left")
state_label.pack(pady=10)

mfc_label = ttk.Label(left_frame, text="Set MFC Flow (0-100 sccm):")
mfc_label.pack(pady=(10, 0))
mfc_entry = ttk.Entry(left_frame)
mfc_entry.pack(pady=2)

def set_mfc():
    global mfc_setpoint
    try:
        val = float(mfc_entry.get())

        if BOOL_MFC == True:
            if val == 0:
                mfc_setpoint = val
                mfc_setpoint_history.append((time.time(), val))
                send_command(f"SET_MFC:{val:.1f}")
                log_event(f"MFC Setpoint Changed to {val:.1f} sccm", pin="5", value=val)
            if val == 100:
                mfc_setpoint = val
                mfc_setpoint_history.append((time.time(), val))
                send_command(f"SET_MFC:{val:.1f}")
                log_event(f"MFC Setpoint Changed to {val:.1f} sccm", pin="5", value=val)
            else:
                print("Enter 0/100 for boolean testing")
        else: 
            if 0.0 <= val <= 100.0:
                mfc_setpoint = val
                mfc_setpoint_history.append((time.time(), val))
                send_command(f"SET_MFC:{val:.1f}")
                log_event(f"MFC Setpoint Changed to {val:.1f} sccm", pin="5", value=val)
            else:
                print("[WARN] MFC setpoint out of range.")
    except ValueError:
        print("[ERROR] Invalid MFC entry.")

set_mfc_button = ttk.Button(left_frame, text="Apply MFC", command=set_mfc)
set_mfc_button.pack(pady=(0, 10))

def update_state_display():
    fuel = "OPEN" if valve_state["fuel"] else "CLOSED"
    vac = "OPEN" if valve_state["vacuum"] else "CLOSED"
    state_label.config(text=f"Fuel Valve: {fuel}\nVacuum Valve: {vac}")

def fuel_open():
    send_command("FUEL_OPEN")
    valve_state["fuel"] = True
    update_state_display()
    log_event("Fuel valve OPEN", pin=9, value=0)

def fuel_close():
    send_command("FUEL_CLOSE")
    valve_state["fuel"] = False
    update_state_display()
    log_event("Fuel valve CLOSED", pin=9, value=1)

def vacuum_open():
    send_command("VACUUM_OPEN")
    valve_state["vacuum"] = True
    update_state_display()
    log_event("Vacuum valve OPEN", pin=10, value=0)

def vacuum_close():
    send_command("VACUUM_CLOSE")
    valve_state["vacuum"] = False
    update_state_display()
    log_event("Vacuum valve CLOSED", pin=10, value=1)

def log_event(action, pin=None, value=None):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] {action}"
    if pin is not None and value is not None:
        entry += f" | Pin {pin} = {'HIGH' if value else 'LOW'}"
    log_box.config(state=tk.NORMAL)
    log_box.insert(tk.END, entry + "\n")
    log_box.see(tk.END)
    log_box.config(state=tk.DISABLED)
    log_writer.writerow([timestamp, action, pin, "HIGH" if value else "LOW" if value is not None else ""])
    log_file.flush()

tk.Button(left_frame, text="Fuel OPEN", command=fuel_open, width=15, bg="lightgreen").pack(pady=3)
tk.Button(left_frame, text="Fuel CLOSE", command=fuel_close, width=15, bg="salmon").pack(pady=3)
tk.Button(left_frame, text="Vacuum OPEN", command=vacuum_open, width=15, bg="lightblue").pack(pady=3)
tk.Button(left_frame, text="Vacuum CLOSE", command=vacuum_close, width=15, bg="orange").pack(pady=3)
tk.Button(left_frame, text="KILL / EXIT", command=safe_exit, width=15, bg="black", fg="white").pack(pady=10)

update_state_display()

right_frame = ttk.Frame(main_frame)
right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 6), sharex=True)

line_pressure, = ax1.plot([], [], lw=2, label="Pressure")
ax1.set_ylabel("Pressure (mTorr)")
ax1.grid(True)

ax1b = ax1.twinx()
line_flow, = ax1b.plot([], [], 'r--', label="Flow Rate")
line_setpoint, = ax1b.plot([], [], 'k--', label="Setpoint")
ax1b.set_ylabel("Flow (sccm)", color='red')

line_vhv, = ax2.plot([], [], 'g-', lw=2, label="HV Voltage")
line_ihv, = ax2.plot([], [], 'b--', lw=2, label="HV Current")
ax2.set_ylabel("HV Output")
ax2.set_xlabel("Time (s)")
ax2.grid(True)

canvas = FigureCanvasTkAgg(fig, master=right_frame)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

camera_window = tk.Toplevel(root)
camera_window.title("Live Camera View")
camera_window.geometry("640x520")
camera_window.lift()
camera_window.focus_force()
camera_frame = tk.Label(camera_window)
camera_frame.pack(fill=tk.BOTH, expand=True)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

focus_scale = tk.Scale(camera_window, from_=0, to=255, label="Focus", orient=tk.HORIZONTAL, command=lambda v: cap.set(cv2.CAP_PROP_FOCUS, float(v)))
focus_scale.set(100)
focus_scale.pack()

brightness_scale = tk.Scale(camera_window, from_=0, to=255, label="Brightness", orient=tk.HORIZONTAL, command=lambda v: cap.set(cv2.CAP_PROP_BRIGHTNESS, float(v)))
brightness_scale.set(128)
brightness_scale.pack()

contrast_scale = tk.Scale(camera_window, from_=0, to=255, label="Contrast", orient=tk.HORIZONTAL, command=lambda v: cap.set(cv2.CAP_PROP_CONTRAST, float(v)))
contrast_scale.set(128)
contrast_scale.pack()

camera_timestamp = None
video_writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))

def update_camera():
    global camera_timestamp
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            frame = cv2.resize(frame, (frame_width, frame_height))
            camera_timestamp = time.time()
            try:
                video_writer.write(frame)
            except Exception as e:
                print(f"[WARN] Could not write frame: {e}")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            camera_frame.imgtk = imgtk
            camera_frame.configure(image=imgtk)
    if not stop_threads:
        camera_frame.after(30, update_camera)

update_camera()

def update_plot():
    if telemetry:
        times, pressure, flow, vhv, ihv = zip(*telemetry)
        t0 = times[0]
        times = [t - t0 for t in times]
        line_pressure.set_data(times, pressure)
        line_flow.set_data(times, flow)
        setpoint_times, setpoint_vals = zip(*mfc_setpoint_history) if mfc_setpoint_history else ([], [])
        setpoint_times = [t - t0 for t in setpoint_times]
        line_setpoint.set_data(setpoint_times, setpoint_vals)
        line_vhv.set_data(times, vhv)
        line_ihv.set_data(times, ihv)
        ax1.set_xlim(max(0, times[-1] - PLOT_WINDOW), times[-1])
        ax1.set_ylim(0, max(10, max(pressure)*1.1))
        ax1b.set_ylim(0, max(100, max(list(flow) + [mfc_setpoint])*1.2))
        ax2.set_xlim(max(0, times[-1] - PLOT_WINDOW), times[-1])
        ax2.set_ylim(0, max(30, max(vhv)*1.2))
        canvas.draw()
    root.after(100, update_plot)

update_plot()

def poll_serial():
    try:
        if ser.in_waiting:
            line = ser.readline().decode().strip()
            terminal_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], line])
            terminal_log_file.flush()
            if line.startswith("DATA:"):
                parts = dict(pair.split('=') for pair in line[5:].split(','))
                t = int(parts['T']) / 1000
                pressure = float(parts['P'])
                flow = float(parts['FMFC'])
                vhv = float(parts['VHV'])
                ihv = float(parts['IHV'])
                telemetry.append((t, pressure, flow, vhv, ihv))
    except Exception as e:
        print(f"Serial poll error: {e}")
    finally:
        root.after(33, poll_serial)


poll_serial()
root.mainloop()
