import tkinter as tk
from tkinter import filedialog, messagebox
import serial
import csv
import threading
import time

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# ====== Parameters ======
PORT = "/dev/cu.usbserial-140"          # Change to your Arduino port
BAUD = 115200
NUM_POINTS = 100000     # Length of log
# ========================

def start_logging():
    def worker():
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(2)  # wait for Arduino reset
        except Exception as e:
            messagebox.showerror("Error", f"Could not open serial port:\n{e}")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not filename:
            ser.close()
            return

        xs, ys = [], []

        with open(filename, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Index", "Value"])  # header row

            for i in range(NUM_POINTS):
                try:
                    line = ser.readline().decode().strip()
                    if line.isdigit():
                        val = int(line)
                        xs.append(i)
                        ys.append(val)
                        writer.writerow([i, val])

                        # GUI status update
                        status_var.set(f"Collected {i+1}/{NUM_POINTS}")
                        root.update_idletasks()

                        # Only update plot if enabled
                        if plot_enabled.get():
                            if i % 20 == 0:  # update every 20 samples for speed
                                ax.clear()
                                ax.plot(xs, ys, color="blue")
                                ax.set_ylim(0, 1023)
                                ax.set_xlim(0, max(100, i))
                                ax.set_title("Live Analog Input (A0)")
                                ax.set_xlabel("Sample #")
                                ax.set_ylabel("Value (0–1023)")
                                canvas.draw()
                except Exception:
                    pass

        ser.close()
        messagebox.showinfo("Done", f"Saved {NUM_POINTS} samples to {filename}")

    threading.Thread(target=worker, daemon=True).start()

# ===== GUI =====
root = tk.Tk()
root.title("Arduino Analog Logger")

status_var = tk.StringVar()
status_var.set("Ready to log...")

tk.Label(root, text="Arduino Analog Data Logger", font=("Arial", 14)).pack(pady=10)
tk.Button(root, text="Start Logging", command=start_logging, font=("Arial", 12)).pack(pady=5)

# Toggle for plotting
plot_enabled = tk.BooleanVar(value=True)
tk.Checkbutton(root, text="Enable Live Plotting", variable=plot_enabled).pack(pady=5)

tk.Label(root, textvariable=status_var, font=("Arial", 10)).pack(pady=10)

# ===== Matplotlib Figure =====
fig, ax = plt.subplots(figsize=(6,3))
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
canvas.draw()

root.mainloop()

