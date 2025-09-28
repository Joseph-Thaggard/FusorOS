#!/usr/bin/env python3
"""
Main entry point for Radiation Spectroscopy System
Integrates the spectroscopy system with the monitoring dashboard
"""

import sys
import time
import threading
from datetime import datetime

# Import the main components
# Note: Save the previous artifacts as separate files:
# - radiation_spectroscopy.py (the main RadiationSpectroscopy class)
# - radiation_monitor.py (the RadiationMonitorDashboard class)

# Add path if needed
sys.path.insert(0, '/Users/joe/DSO5102P-Python')

# Import our modules
from radiation_spectroscopy import RadiationSpectroscopy
from radiation_monitor import RadiationMonitorDashboard, run_monitor

def test_acquisition_speed(spec, num_pulses=100):
    """Test the acquisition speed of the system"""
    print("\n=== Testing Acquisition Speed ===")
    print(f"Attempting to acquire {num_pulses} pulses...")
    
    start_time = time.time()
    successful_pulses = 0
    
    for i in range(num_pulses):
        pulse = spec.acquire_single_pulse(timeout=0.01)
        if pulse:
            successful_pulses += 1
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{num_pulses} attempts...")
    
    elapsed = time.time() - start_time
    
    print(f"\nResults:")
    print(f"  Successful acquisitions: {successful_pulses}/{num_pulses}")
    print(f"  Time elapsed: {elapsed:.2f} seconds")
    print(f"  Acquisition rate: {successful_pulses/elapsed:.1f} Hz")
    print(f"  Average time per attempt: {elapsed/num_pulses*1000:.1f} ms")
    print(f"  Success rate: {successful_pulses/num_pulses*100:.1f}%")
    
    if successful_pulses < num_pulses:
        dead_time = (1 - successful_pulses/num_pulses) * 100
        print(f"  Estimated dead time: {dead_time:.1f}%")
    
    return successful_pulses, elapsed

def run_dashboard_mode(spec):
    """Run the system with the real-time monitoring dashboard"""
    print("\n=== Starting Dashboard Mode ===")
    print("This will open an interactive window with real-time monitoring")
    
    # Create and start the dashboard
    dashboard = RadiationMonitorDashboard(spec)
    
    # Optional: Add ROIs if calibrated
    if spec.energy_calibration is not None:
        print("Adding regions of interest...")
        # Example: Add ROI for Na-22 511 keV peak
        # You'll need to convert energy to channel based on your calibration
        # dashboard.add_roi(start_channel, end_channel, "Na-22 511keV")
    
    try:
        # Start the dashboard (this blocks until window is closed)
        dashboard.start(update_interval=500)  # Update every 500ms
    except KeyboardInterrupt:
        dashboard.stop()
        print("\nDashboard closed")
    except Exception as e:
        print(f"Dashboard error: {e}")
        dashboard.stop()

def run_background_acquisition(spec, duration=60):
    """Run acquisition in background with console output"""
    print(f"\n=== Background Acquisition ({duration} seconds) ===")
    print("Press Ctrl+C to stop early")
    
    # Start acquisition in a thread
    spec.acquisition_active = True
    spec.processing_active = True
    
    acq_thread = threading.Thread(target=spec.acquisition_thread)
    proc_thread = threading.Thread(target=spec.processing_thread)
    
    acq_thread.daemon = True
    proc_thread.daemon = True
    
    acq_thread.start()
    proc_thread.start()
    
    start_time = time.time()
    last_counts = 0
    
    try:
        while (time.time() - start_time) < duration:
            time.sleep(1)
            
            # Calculate rates
            current_counts = spec.total_counts
            new_counts = current_counts - last_counts
            last_counts = current_counts
            
            total_rate = current_counts / max(1, spec.real_time)
            
            # Clear line and print stats
            print(f"\r  Counts: {current_counts:6d} | "
                  f"Rate: {total_rate:6.1f} cps | "
                  f"Instant: {new_counts:3d} cps | "
                  f"Rejected: {spec.rejected_counts:4d} | "
                  f"Time: {spec.real_time:.1f}s", end='', flush=True)
            
    except KeyboardInterrupt:
        print("\n\nAcquisition interrupted by user")
    
    # Stop acquisition
    spec.stop_acquisition()
    print(f"\n\nFinal statistics:")
    print(f"  Total counts: {spec.total_counts}")
    print(f"  Average rate: {spec.total_counts/spec.real_time:.1f} cps")
    print(f"  Pile-up rejected: {spec.rejected_counts}")

def quick_spectrum_check(spec, duration=10):
    """Quick spectrum acquisition and display"""
    print(f"\n=== Quick Spectrum Check ({duration} seconds) ===")
    
    # Clear previous data
    spec.spectrum.fill(0)
    spec.total_counts = 0
    spec.rejected_counts = 0
    
    # Acquire
    print("Acquiring...")
    spec.start_acquisition(duration=duration)
    
    # Find and display peaks
    if spec.total_counts > 0:
        print(f"\nAcquired {spec.total_counts} counts")
        peaks = spec.find_peaks(min_counts=10)
        
        # Simple text-based spectrum display
        print("\nSpectrum preview (text mode):")
        display_text_spectrum(spec.spectrum)
    else:
        print("No counts acquired. Check detector and settings.")

def display_text_spectrum(spectrum, width=80, height=20):
    """Display a simple text-based spectrum"""
    import numpy as np
    
    # Compress spectrum to display width
    compressed = []
    bin_size = len(spectrum) // width
    
    if bin_size == 0:
        print("Spectrum array too small to display")
        return
    
    for i in range(width):
        start = i * bin_size
        end = min(start + bin_size, len(spectrum))
        if start < len(spectrum):
            compressed.append(np.max(spectrum[start:end]))
    
    # Normalize to height
    max_val = max(compressed) if compressed else 0
    if max_val == 0:
        print("No data to display")
        return
    
    # Print spectrum
    for h in range(height, 0, -1):
        line = ""
        threshold = (h / height) * max_val
        for val in compressed:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        print(line)
    
    print("─" * width)
    print(f"Channel: 0{' ' * (width-15)}4096")

def main_menu():
    """Main menu for the spectroscopy system"""
    
    print("\n" + "="*60)
    print("   RADIATION SPECTROSCOPY SYSTEM")
    print("   BC-412 Plastic Scintillator + DSO5102P")
    print("="*60)
    
    # Ask for channel selection
    channel = input("\nWhich oscilloscope channel to use (1 or 2) [2]: ").strip()
    channel = int(channel) if channel else 2
    
    # Initialize the spectroscopy system with selected channel
    try:
        print(f"\nInitializing system on Channel {channel}...")
        spec = RadiationSpectroscopy(debug=False, channel=channel)
        print(f"✓ System ready on CH{channel}")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        print("\nTroubleshooting:")
        print("1. Check USB connection")
        print("2. Run with sudo if permission denied")
        print("3. Ensure oscilloscope is powered on")
        return 1
    
    while True:
        print("\n" + "="*40)
        print("MAIN MENU")
        print("="*40)
        print("1. Run Dashboard (GUI mode)")
        print("2. Quick spectrum check (10s)")
        print("3. Background acquisition (console)")
        print("4. Test acquisition speed")
        print("5. Energy calibration wizard")
        print("6. Save current spectrum")
        print("7. Load spectrum from file")
        print("8. System diagnostics")
        print("9. Trigger settings")
        print("10. Test signal detection")
        print("11. About")
        print("0. Exit")
        print("="*40)
        
        try:
            choice = input("\nSelect option: ").strip()
            
            if choice == '1':
                # Run with dashboard
                run_dashboard_mode(spec)
                
            elif choice == '2':
                # Quick spectrum
                duration = input("Duration in seconds [10]: ").strip()
                duration = int(duration) if duration else 10
                quick_spectrum_check(spec, duration)
                
            elif choice == '3':
                # Background acquisition
                duration = input("Duration in seconds [60]: ").strip()
                duration = int(duration) if duration else 60
                run_background_acquisition(spec, duration)
                
            elif choice == '4':
                # Test speed
                num = input("Number of pulses to test [100]: ").strip()
                num = int(num) if num else 100
                test_acquisition_speed(spec, num)
                
            elif choice == '5':
                # Calibration wizard
                run_calibration_wizard(spec)
                
            elif choice == '6':
                # Save spectrum
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = input(f"Filename [spectrum_{timestamp}.csv]: ").strip()
                filename = filename if filename else f"spectrum_{timestamp}.csv"
                spec.save_spectrum(filename)
                print(f"Saved to {filename}")
                
            elif choice == '7':
                # Load spectrum
                filename = input("Filename to load: ").strip()
                if filename:
                    load_spectrum(spec, filename)
                
            elif choice == '8':
                # Diagnostics
                run_diagnostics(spec)
                
            elif choice == '9':
                # Trigger settings
                adjust_trigger_settings(spec)
                
            elif choice == '10':
                # Test signal detection
                spec.test_acquisition(num_samples=10)
                
            elif choice == '11':
                # About
                print_about()
                
            elif choice == '0':
                # Exit
                print("\nShutting down...")
                spec.stop_acquisition()
                break
                
            else:
                print("Invalid option. Please try again.")
                
        except KeyboardInterrupt:
            print("\n\nOperation cancelled")
            continue
        except Exception as e:
            print(f"\nError: {e}")
            continue
    
    print("Thank you for using the Radiation Spectroscopy System")
    print("Goodbye!")
    return 0

def run_calibration_wizard(spec):
    """Interactive calibration wizard"""
    print("\n=== Energy Calibration Wizard ===")
    print("This wizard will help you calibrate the energy scale")
    print("\nCommon calibration sources:")
    print("  Na-22: 511 keV, 1274 keV")
    print("  Cs-137: 662 keV")
    print("  Co-60: 1173 keV, 1332 keV")
    print("  Am-241: 59.5 keV")
    
    # Check if spectrum has data
    if spec.total_counts < 100:
        print("\n⚠ Warning: Spectrum has very few counts.")
        print("Consider acquiring more data first.")
        if input("Continue anyway? (y/n): ").lower() != 'y':
            return
    
    # Find peaks automatically
    print("\nSearching for peaks...")
    peaks = spec.find_peaks(min_counts=10)
    
    if len(peaks) == 0:
        print("No peaks found. Acquire more data and try again.")
        return
    
    print(f"\nFound {len(peaks)} peaks")
    print("Top 5 peaks:")
    for i, (ch, counts) in enumerate(peaks[:5]):
        print(f"  {i+1}. Channel {ch:.1f}: {counts} counts")
    
    # Get calibration points
    num_points = int(input("\nHow many calibration points? [2]: ").strip() or "2")
    
    channels = []
    energies = []
    
    for i in range(num_points):
        print(f"\nCalibration point {i+1}:")
        
        # Option to use detected peak
        use_peak = input("Use detected peak? (y/n) [y]: ").strip().lower()
        
        if use_peak != 'n' and i < len(peaks):
            peak_num = int(input(f"Which peak? (1-{min(5, len(peaks))}) [1]: ").strip() or "1") - 1
            channel = peaks[peak_num][0]
            print(f"Using channel {channel:.1f}")
        else:
            channel = float(input("Enter channel number: ").strip())
        
        energy = float(input("Enter energy (keV): ").strip())
        
        channels.append(channel)
        energies.append(energy)
    
    # Perform calibration
    order = int(input("\nPolynomial order (1=linear, 2=quadratic) [1]: ").strip() or "1")
    
    try:
        coeffs, rms_error = spec.calibrate_energy(channels, energies, order)
        
        print("\n✓ Calibration successful!")
        print(f"RMS error: {rms_error:.2f} keV")
        
        # Test calibration
        print("\nCalibration check:")
        for ch, en in zip(channels, energies):
            predicted = spec.pulse_height_to_energy(ch / spec.adc_to_channel_factor)
            error = predicted - en
            print(f"  Channel {ch:.1f} → {predicted:.1f} keV (error: {error:+.1f} keV)")
        
    except Exception as e:
        print(f"Calibration failed: {e}")

def adjust_trigger_settings(spec):
    """Adjust trigger and detection settings"""
    print("\n=== Trigger Settings ===")
    print(f"Current settings:")
    print(f"  Trigger level: ±{spec.trigger_level} mV")
    print(f"  Pulse polarity: {spec.pulse_polarity}")
    print(f"  Noise threshold: {spec.noise_threshold} mV")
    print(f"  Sample rate: {spec.sample_rate/1e6:.1f} MS/s")
    print(f"  Acquisition window: {spec.acquisition_window*1e6:.1f} μs")
    
    print("\nOptions:")
    print("1. Set trigger level")
    print("2. Set pulse polarity")
    print("3. Set noise threshold")
    print("4. Quick presets")
    print("5. Back to main menu")
    
    choice = input("\nSelect option: ").strip()
    
    if choice == '1':
        level = input(f"Enter trigger level in mV [current: {spec.trigger_level}]: ").strip()
        if level:
            spec.set_trigger_parameters(level=float(level))
    
    elif choice == '2':
        print("Pulse polarity options:")
        print("  1. Negative pulses only")
        print("  2. Positive pulses only")
        print("  3. Both (auto-detect)")
        pol_choice = input("Select: ").strip()
        polarity_map = {'1': 'negative', '2': 'positive', '3': 'both'}
        if pol_choice in polarity_map:
            spec.set_trigger_parameters(polarity=polarity_map[pol_choice])
    
    elif choice == '3':
        threshold = input(f"Enter noise threshold in mV [current: {spec.noise_threshold}]: ").strip()
        if threshold:
            spec.set_trigger_parameters(noise_threshold=float(threshold))
    
    elif choice == '4':
        print("\nQuick presets:")
        print("1. Sensitive (±50mV trigger, 10mV noise)")
        print("2. Standard (±80mV trigger, 15mV noise)")
        print("3. High energy (±200mV trigger, 30mV noise)")
        print("4. Very sensitive (±30mV trigger, 5mV noise)")
        
        preset = input("Select preset: ").strip()
        if preset == '1':
            spec.set_trigger_parameters(level=50, noise_threshold=10)
        elif preset == '2':
            spec.set_trigger_parameters(level=80, noise_threshold=15)
        elif preset == '3':
            spec.set_trigger_parameters(level=200, noise_threshold=30)
        elif preset == '4':
            spec.set_trigger_parameters(level=30, noise_threshold=5)

def run_diagnostics(spec):
    """Run system diagnostics"""
    print("\n=== System Diagnostics ===")
    
    # Check USB connection
    print("\n1. USB Connection:")
    try:
        import usb.core
        dev = usb.core.find(idVendor=spec.vid, idProduct=spec.pid)
        if dev:
            print("   ✓ DSO5102P detected")
            print(f"   Device: VID={hex(dev.idVendor)}, PID={hex(dev.idProduct)}")
        else:
            print("   ✗ DSO5102P not detected")
    except Exception as e:
        print(f"   ✗ USB error: {e}")
    
    # Check communication
    print("\n2. Communication Test:")
    try:
        # Try to read from scope
        spec.dso.StartAcquisition()
        time.sleep(0.1)
        data = spec.dso.ReadSampleData(1)
        spec.dso.StopAcquisition()
        
        if data:
            print(f"   ✓ Communication OK (received {len(data)} samples)")
        else:
            print("   ⚠ Communication works but no data received")
    except Exception as e:
        print(f"   ✗ Communication failed: {e}")
    
    # Check performance
    print("\n3. Performance:")
    print(f"   Total counts: {spec.total_counts}")
    print(f"   Rejected counts: {spec.rejected_counts}")
    if spec.real_time > 0:
        print(f"   Average rate: {spec.total_counts/spec.real_time:.1f} cps")
    print(f"   Queue size: {spec.pulse_queue.qsize()}")
    print(f"   History buffer: {len(spec.pulse_history)} pulses")
    
    # Memory usage
    print("\n4. Memory Usage:")
    spectrum_mb = spec.spectrum.nbytes / (1024*1024)
    print(f"   Spectrum array: {spectrum_mb:.2f} MB")
    
    # Calibration status
    print("\n5. Calibration:")
    if spec.energy_calibration is not None:
        print(f"   ✓ Energy calibration active")
        print(f"   Coefficients: {spec.energy_calibration}")
    else:
        print("   ✗ No energy calibration")

def load_spectrum(spec, filename):
    """Load spectrum from file"""
    try:
        import csv
        import numpy as np
        
        # Read CSV file
        with open(filename, 'r') as f:
            reader = csv.reader(f)
            
            # Skip header lines
            for line in reader:
                if line and not line[0].startswith('#'):
                    break
            
            # Read spectrum data
            spec.spectrum.fill(0)
            for row in reader:
                if len(row) >= 2:
                    channel = int(row[0])
                    counts = int(row[1])
                    if 0 <= channel < spec.num_channels:
                        spec.spectrum[channel] = counts
        
        spec.total_counts = np.sum(spec.spectrum)
        print(f"✓ Loaded spectrum from {filename}")
        print(f"  Total counts: {spec.total_counts}")
        
    except Exception as e:
        print(f"✗ Failed to load spectrum: {e}")

def print_about():
    """Print about information"""
    print("\n" + "="*60)
    print("RADIATION SPECTROSCOPY SYSTEM")
    print("="*60)
    print("Version: 1.0.0")
    print("Hardware: Hantek DSO5102P Oscilloscope")
    print("Detector: BC-412 Plastic Scintillator with PMT")
    print("\nCapabilities:")
    print("  • Pulse height analysis (PHA)")
    print("  • Energy calibration")
    print("  • Pile-up rejection")
    print("  • Real-time spectrum display")
    print("  • Count rates up to 3 kHz")
    print("  • Energy range: 100 keV - 14 MeV")
    print("\nDeveloped for radiation detection and spectroscopy")
    print("="*60)

if __name__ == "__main__":
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('TkAgg')  # Use TkAgg backend for better compatibility
        import matplotlib.pyplot as plt
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("\nPlease install required packages:")
        print("  pip install numpy matplotlib scipy")
        sys.exit(1)
    
    # Run the main menu
    exit(main_menu())