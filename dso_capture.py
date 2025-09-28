#!/usr/bin/env python3
"""
DSO5102P Oscilloscope Data Capture and Analysis Tool
Captures waveform data, exports to CSV, and performs pulse analysis
"""

import sys
import usb.core
import usb.util
import time
import csv
import numpy as np
from datetime import datetime
import os

# Add DSO5102P library path
sys.path.insert(0, '/Users/joe/DSO5102P-Python')
from rcr.dso5102p.DSO5102P import DSO5102P

class DSO5102PCapture:
    def __init__(self, vid=0x049f, pid=0x505a, debug=False):
        self.vid = vid
        self.pid = pid
        self.debug = debug
        self.dso = None
        self.setup_device()
    
    def setup_device(self, max_retries=3):
        """Setup USB device and initialize DSO5102P with better error handling"""
        print("=== Setting up DSO5102P ===")
        
        # Check if running with sudo
        if os.geteuid() != 0:
            print("⚠️  Warning: Not running as root. If you get permission errors, try:")
            print("   sudo python3 dso_capture.py")
            print()
        
        for attempt in range(max_retries):
            try:
                # Find device
                print(f"Attempt {attempt + 1}: Looking for DSO5102P...")
                dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
                
                if dev is None:
                    if attempt < max_retries - 1:
                        print("Device not found, waiting and retrying...")
                        time.sleep(3)
                        continue
                    else:
                        raise ValueError("DSO5102P not found. Check USB connection.")
                
                print(f"Found device: VID={hex(dev.idVendor)}, PID={hex(dev.idProduct)}")
                
                # Try gentle setup without reset first
                try:
                    print("Attempting gentle USB setup...")
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                    print("USB configuration successful (gentle)")
                    
                except Exception as e:
                    print(f"Gentle setup failed: {e}")
                    print("Trying with device reset...")
                    
                    # Reset and reconfigure
                    dev.reset()
                    time.sleep(3)  # Longer wait after reset
                    
                    # Find device again after reset
                    dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
                    if dev is None:
                        raise Exception("Device disappeared after reset")
                    
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                    print("USB configuration successful (with reset)")
                
                # Initialize DSO5102P
                print("Initializing DSO5102P library...")
                self.dso = DSO5102P(self.vid, self.pid, self.debug)
                
                # Test basic communication
                print("Testing communication...")
                system_time = self.dso.ReadSystemTime()
                print(f"✅ Connected to DSO5102P - System time: {system_time}")
                return  # Success!
                
            except usb.core.USBError as e:
                if "Access denied" in str(e) or "insufficient permissions" in str(e):
                    print(f"❌ Permission denied. Please run with sudo:")
                    print(f"   sudo python3 {sys.argv[0]}")
                    raise Exception("Insufficient permissions. Run with sudo.")
                elif "No such device" in str(e):
                    print(f"❌ Device disconnected. Attempt {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        print("Waiting for device to reconnect...")
                        time.sleep(5)
                        continue
                else:
                    print(f"❌ USB error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
            except Exception as e:
                print(f"❌ Setup error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        
        raise Exception(f"Failed to setup DSO5102P after {max_retries} attempts")
    
    def capture_waveform(self, wait_time=1.0, max_retries=5):
        """Capture waveform data from both channels"""
        if not self.dso:
            raise Exception("DSO5102P not initialized")
        
        print(f"Starting waveform capture (wait: {wait_time}s)...")
        
        for attempt in range(max_retries):
            try:
                # Start acquisition
                self.dso.StartAcquisition()
                print(f"Acquisition started (attempt {attempt + 1})")
                
                # Wait for data to be captured
                time.sleep(wait_time)
                
                # Read data from both channels
                print("Reading channel data...")
                ch1_data = self.dso.ReadSampleData(1)
                ch2_data = self.dso.ReadSampleData(2)
                
                # Stop acquisition
                self.dso.StopAcquisition()
                
                # Check if we got data
                ch1_len = len(ch1_data) if ch1_data else 0
                ch2_len = len(ch2_data) if ch2_data else 0
                
                print(f"Captured - CH1: {ch1_len} samples, CH2: {ch2_len} samples")
                
                if ch1_len > 0 or ch2_len > 0:
                    return ch1_data, ch2_data
                
                # If no data, try longer wait time
                wait_time *= 1.5
                print(f"No data captured, retrying with longer wait ({wait_time:.1f}s)...")
                
            except Exception as e:
                print(f"Capture attempt {attempt + 1} failed: {e}")
                try:
                    self.dso.StopAcquisition()
                except:
                    pass
                time.sleep(0.5)
        
        print("Failed to capture data after all retries")
        return None, None
    
    def save_csv(self, ch1_data, ch2_data, filename=None, sample_rate=1e6):
        """Save waveform data to CSV file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dso5102p_capture_{timestamp}.csv"
        
        if ch1_data is None and ch2_data is None:
            print("No data to save")
            return None
        
        # Convert to numpy arrays
        ch1_array = np.array(ch1_data) if ch1_data else None
        ch2_array = np.array(ch2_data) if ch2_data else None
        
        # Determine max length
        max_len = 0
        if ch1_array is not None:
            max_len = max(max_len, len(ch1_array))
        if ch2_array is not None:
            max_len = max(max_len, len(ch2_array))
        
        if max_len == 0:
            print("No valid data to save")
            return None
        
        # Write CSV
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow([
                'Sample', 'Time_s', 'Time_ms', 'Time_us', 
                'CH1_Raw', 'CH2_Raw', 'CH1_mV', 'CH2_mV'
            ])
            
            # Data rows
            time_step = 1.0 / sample_rate
            for i in range(max_len):
                time_s = i * time_step
                time_ms = time_s * 1000
                time_us = time_s * 1000000
                
                ch1_raw = ch1_array[i] if ch1_array is not None and i < len(ch1_array) else 0
                ch2_raw = ch2_array[i] if ch2_array is not None and i < len(ch2_array) else 0
                
                # Convert to mV (approximate - actual conversion depends on scope settings)
                # DSO5102P typically uses 8-bit ADC, so 0-255 range
                ch1_mv = (ch1_raw - 128) * 10  # Rough conversion
                ch2_mv = (ch2_raw - 128) * 10
                
                writer.writerow([i, time_s, time_ms, time_us, ch1_raw, ch2_raw, ch1_mv, ch2_mv])
        
        print(f"Data saved to {filename} ({max_len} samples)")
        return filename
    
    def analyze_pulses(self, data, threshold=10, min_width=5):
        """Simple pulse detection and analysis"""
        if data is None or len(data) == 0:
            return []
        
        data_array = np.array(data)
        baseline = np.median(data_array)
        
        # Find pulses above threshold
        above_threshold = data_array > (baseline + threshold)
        
        # Find pulse edges
        rising_edges = np.where(np.diff(above_threshold.astype(int)) == 1)[0]
        falling_edges = np.where(np.diff(above_threshold.astype(int)) == -1)[0]
        
        pulses = []
        for i, start in enumerate(rising_edges):
            # Find corresponding falling edge
            end_candidates = falling_edges[falling_edges > start]
            if len(end_candidates) > 0:
                end = end_candidates[0]
                width = end - start
                
                if width >= min_width:
                    pulse_data = data_array[start:end+1]
                    pulses.append({
                        'start': start,
                        'end': end,
                        'width': width,
                        'amplitude': np.max(pulse_data) - baseline,
                        'area': np.sum(pulse_data - baseline)
                    })
        
        return pulses
    
    def quick_capture(self):
        """Quick capture and analysis"""
        print("=== Quick Waveform Capture ===")
        
        start_time = time.time()
        ch1_data, ch2_data = self.capture_waveform()
        capture_time = (time.time() - start_time) * 1000
        
        print(f"Capture completed in {capture_time:.1f}ms")
        
        if ch1_data is None and ch2_data is None:
            print("No data captured. Check:")
            print("- Signal connections to CH1/CH2")
            print("- Trigger settings on scope")
            print("- Signal amplitude and frequency")
            return
        
        # Save to CSV
        filename = self.save_csv(ch1_data, ch2_data)
        
        # Basic analysis
        if ch1_data:
            ch1_array = np.array(ch1_data)
            print(f"CH1 Analysis:")
            print(f"  Samples: {len(ch1_array)}")
            print(f"  Range: {np.min(ch1_array)} - {np.max(ch1_array)}")
            print(f"  Mean: {np.mean(ch1_array):.1f}")
            print(f"  Std Dev: {np.std(ch1_array):.1f}")
            
            # Pulse analysis
            pulses = self.analyze_pulses(ch1_data)
            print(f"  Pulses detected: {len(pulses)}")
            for i, pulse in enumerate(pulses[:5]):  # Show first 5 pulses
                print(f"    Pulse {i+1}: width={pulse['width']}, amp={pulse['amplitude']:.1f}")
        
        if ch2_data:
            ch2_array = np.array(ch2_data)
            print(f"CH2 Analysis:")
            print(f"  Samples: {len(ch2_array)}")
            print(f"  Range: {np.min(ch2_array)} - {np.max(ch2_array)}")
            print(f"  Mean: {np.mean(ch2_array):.1f}")
            print(f"  Std Dev: {np.std(ch2_array):.1f}")
        
        return filename
    
    def continuous_monitor(self, duration=60, interval=5):
        """Continuously capture data for specified duration"""
        print(f"=== Continuous Monitoring ({duration}s, every {interval}s) ===")
        
        start_time = time.time()
        capture_count = 0
        
        while time.time() - start_time < duration:
            try:
                ch1_data, ch2_data = self.capture_waveform(wait_time=1.0)
                
                if ch1_data or ch2_data:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"continuous_{timestamp}.csv"
                    self.save_csv(ch1_data, ch2_data, filename)
                    
                    # Quick pulse analysis
                    if ch1_data:
                        pulses = self.analyze_pulses(ch1_data)
                        print(f"Capture {capture_count}: {len(pulses)} pulses detected")
                    
                    capture_count += 1
                else:
                    print(f"Capture {capture_count}: No data")
                
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")
                break
            except Exception as e:
                print(f"Capture error: {e}")
            
            time.sleep(interval)
        
        print(f"Monitoring complete. {capture_count} captures saved.")
    
    def remote_control_test(self):
        """Test remote control capabilities"""
        print("=== Remote Control Test ===")
        
        try:
            # Test button simulation
            print("Testing button controls...")
            # Note: KeyTrigger might need specific button codes
            
            # Test screen capture
            print("Taking screenshot...")
            screenshot = self.dso.Screenshot()
            
            # Save screenshot
            from PIL import Image
            img = Image.fromarray(screenshot.astype('uint8'))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_file = f"screenshot_{timestamp}.png"
            img.save(screenshot_file)
            print(f"Screenshot saved: {screenshot_file}")
            
        except Exception as e:
            print(f"Remote control test failed: {e}")

def main():
    """Main function with menu interface"""
    print("DSO5102P Data Capture Tool")
    print("=" * 40)
    
    try:
        # Initialize scope
        scope = DSO5102PCapture(debug=False)
        
        while True:
            print("\nOptions:")
            print("1. Quick capture and analysis")
            print("2. Continuous monitoring")
            print("3. Remote control test")
            print("4. Exit")
            
            choice = input("\nSelect option (1-4): ").strip()
            
            if choice == '1':
                scope.quick_capture()
            elif choice == '2':
                duration = int(input("Duration (seconds): ") or "60")
                interval = int(input("Interval (seconds): ") or "5")
                scope.continuous_monitor(duration, interval)
            elif choice == '3':
                scope.remote_control_test()
            elif choice == '4':
                print("Goodbye!")
                break
            else:
                print("Invalid option")
                
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())