#!/usr/bin/env python3
"""
Radiation Spectroscopy System for DSO5102P Oscilloscope
Designed for BC-412 plastic scintillator with PMT
Performs pulse height analysis and builds energy spectra
"""

import sys
import usb.core
import usb.util
import time
import csv
import numpy as np
from datetime import datetime
import os
import json
import threading
import queue
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List, Dict
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy import signal, optimize
from scipy.interpolate import interp1d

# Add DSO5102P library path
sys.path.insert(0, '/Users/joe/DSO5102P-Python')
from rcr.dso5102p.DSO5102P import DSO5102P

@dataclass
class PulseData:
    """Container for individual pulse information"""
    timestamp: float
    peak_height: float  # Absolute value of peak
    pulse_area: float
    baseline: float
    fwhm: float  # Full Width at Half Maximum
    rise_time: float
    is_pileup: bool
    raw_waveform: Optional[np.ndarray] = None
    
class RadiationSpectroscopy:
    def __init__(self, vid=0x049f, pid=0x505a, debug=False, channel=2):
        """Initialize radiation spectroscopy system
        
        Args:
            vid: USB Vendor ID
            pid: USB Product ID  
            debug: Enable debug output
            channel: Oscilloscope channel to use (1 or 2)
        """
        self.vid = vid
        self.pid = pid
        self.debug = debug
        self.channel = channel  # Which scope channel to use
        self.dso = None
        
        # Acquisition parameters
        self.sample_rate = 10e6  # 10 MS/s for better resolution
        self.acquisition_window = 20e-6  # 20 microseconds window
        self.pulse_width = 80e-6  # 80 microseconds shaped pulse
        self.samples_per_pulse = int(self.acquisition_window * self.sample_rate)  # 200 samples at 10MS/s
        
        # Pulse detection parameters - made more flexible
        self.noise_threshold = 15  # mV (lowered for better sensitivity)
        self.trigger_level = 80  # mV absolute value (will detect both + and -)
        self.pulse_polarity = 'both'  # 'positive', 'negative', or 'both'
        self.baseline_samples = 20  # Samples for baseline (reduced for 20us window)
        self.pileup_threshold = 1.5  # Ratio for pile-up detection
        
        # MCA parameters
        self.num_channels = 4096  # MCA channels
        self.spectrum = np.zeros(self.num_channels, dtype=int)
        self.energy_calibration = None  # Will store calibration coefficients
        self.adc_to_channel_factor = 10  # Initial scaling factor
        
        # Statistics
        self.total_counts = 0
        self.rejected_counts = 0
        self.live_time = 0
        self.real_time = 0
        self.start_time = None
        
        # Data storage
        self.pulse_queue = queue.Queue(maxsize=10000)
        self.pulse_history = deque(maxlen=1000)  # Keep last 1000 pulses
        
        # Threading control
        self.acquisition_active = False
        self.processing_active = False
        
        self.setup_device()
    
    def setup_device(self, max_retries=3):
        """Setup USB device and initialize DSO5102P"""
        print("=== Setting up DSO5102P for Radiation Spectroscopy ===")
        
        for attempt in range(max_retries):
            try:
                # Find device
                print(f"Attempt {attempt + 1}: Looking for DSO5102P...")
                dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
                
                if dev is None:
                    if attempt < max_retries - 1:
                        print("Device not found, retrying...")
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError("DSO5102P not found. Check USB connection.")
                
                # Setup USB
                try:
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                except:
                    dev.reset()
                    time.sleep(2)
                    dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                
                # Initialize DSO5102P
                self.dso = DSO5102P(self.vid, self.pid, self.debug)
                print("✅ Connected to DSO5102P")
                
                # Configure scope for radiation detection
                self.configure_scope()
                return
                
            except Exception as e:
                print(f"Setup error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        raise Exception(f"Failed to setup DSO5102P after {max_retries} attempts")
    
    def configure_scope(self):
        """Configure oscilloscope settings for radiation detection"""
        print("Configuring scope for radiation pulses...")
        
        try:
            # Note: These are placeholder commands - adjust based on actual DSO5102P API
            # The actual commands depend on your DSO5102P library implementation
            
            # Set sample rate
            # self.dso.SetSampleRate(self.sample_rate)
            
            # Set trigger mode
            # self.dso.SetTriggerMode('EDGE')
            # self.dso.SetTriggerSlope('FALLING' if self.pulse_polarity == 'negative' else 'RISING')
            # self.dso.SetTriggerLevel(self.trigger_level)
            
            # Set memory depth
            # self.dso.SetMemoryDepth(self.samples_per_pulse * 2)
            
            print("Scope configuration complete")
            
        except Exception as e:
            print(f"Warning: Could not configure scope automatically: {e}")
            
        print("\n=== RECOMMENDED SCOPE SETTINGS ===")
        print(f"Channel: CH{self.channel}")
        print(f"Sample Rate: {self.sample_rate/1e6:.1f} MS/s")
        print(f"Trigger Level: ±{self.trigger_level} mV")
        print(f"Trigger Mode: Edge trigger on CH{self.channel}")
        print(f"Trigger Slope: {'Falling' if self.pulse_polarity == 'negative' else 'Rising' if self.pulse_polarity == 'positive' else 'Either'}")
        print(f"Time Base: {self.acquisition_window*1e6/10:.1f} μs/div (for {self.acquisition_window*1e6:.0f}μs window)")
        print(f"Vertical Scale: Adjust so pulses are 2-6 divisions tall")
        print(f"Trigger Holdoff: ~100 μs (to avoid re-triggering)")
        print("="*35)
    
    def set_trigger_parameters(self, level=None, polarity=None, noise_threshold=None):
        """Adjust trigger parameters on the fly
        
        Args:
            level: Trigger level in mV (absolute value)
            polarity: 'positive', 'negative', or 'both'
            noise_threshold: Noise threshold in mV
        """
        if level is not None:
            self.trigger_level = abs(level)
            print(f"Trigger level set to ±{self.trigger_level} mV")
        
        if polarity is not None:
            if polarity in ['positive', 'negative', 'both']:
                self.pulse_polarity = polarity
                print(f"Pulse polarity set to '{polarity}'")
            else:
                print(f"Invalid polarity. Use 'positive', 'negative', or 'both'")
        
        if noise_threshold is not None:
            self.noise_threshold = noise_threshold
            print(f"Noise threshold set to {self.noise_threshold} mV")
        
        # Reconfigure scope if connected
        self.configure_scope()
    
    def process_pulse(self, waveform: np.ndarray, timestamp: float) -> Optional[PulseData]:
        """Process a single pulse waveform and extract parameters
        
        Handles both positive and negative pulses based on configuration
        """
        
        if len(waveform) < self.baseline_samples * 2:
            return None
        
        try:
            # Calculate baseline from first samples
            baseline = np.mean(waveform[:self.baseline_samples])
            
            # Subtract baseline
            corrected = waveform - baseline
            
            # Find peak based on polarity setting
            if self.pulse_polarity == 'negative':
                peak_idx = np.argmin(corrected)
                peak_height = abs(corrected[peak_idx])
            elif self.pulse_polarity == 'positive':
                peak_idx = np.argmax(corrected)
                peak_height = corrected[peak_idx]
            else:  # 'both' - detect largest deviation from baseline
                min_val = np.min(corrected)
                max_val = np.max(corrected)
                if abs(min_val) > abs(max_val):
                    peak_idx = np.argmin(corrected)
                    peak_height = abs(corrected[peak_idx])
                else:
                    peak_idx = np.argmax(corrected)
                    peak_height = corrected[peak_idx]
            
            # Check if peak is above noise threshold
            if peak_height < self.noise_threshold:
                if self.debug:
                    print(f"Peak {peak_height:.1f}mV below threshold {self.noise_threshold}mV")
                return None
            
            # Calculate pulse area (integral) - use smaller window for 20us
            window_start = max(0, peak_idx - 10)
            window_end = min(len(corrected), peak_idx + 30)
            pulse_area = abs(np.trapz(corrected[window_start:window_end]))
            
            # Calculate FWHM
            half_max = peak_height / 2
            indices = np.where(abs(corrected) > half_max)[0]
            if len(indices) > 1:
                fwhm = (indices[-1] - indices[0]) / self.sample_rate
            else:
                fwhm = 0
            
            # Calculate rise time (10% to 90%)
            try:
                if peak_idx > 0:
                    pre_peak = abs(corrected[:peak_idx])
                    rise_10 = np.where(pre_peak > peak_height * 0.1)[0]
                    rise_90 = np.where(pre_peak > peak_height * 0.9)[0]
                    if len(rise_10) > 0 and len(rise_90) > 0:
                        rise_time = abs(rise_90[0] - rise_10[-1]) / self.sample_rate
                    else:
                        rise_time = 0
                else:
                    rise_time = 0
            except:
                rise_time = 0
            
            # Simple pile-up detection for shorter window
            is_pileup = self.detect_pileup_simple(corrected, peak_idx)
            
            if self.debug:
                print(f"Pulse: height={peak_height:.1f}mV, area={pulse_area:.1f}, FWHM={fwhm*1e6:.1f}us")
            
            return PulseData(
                timestamp=timestamp,
                peak_height=peak_height,
                pulse_area=pulse_area,
                baseline=baseline,
                fwhm=fwhm,
                rise_time=rise_time,
                is_pileup=is_pileup,
                raw_waveform=waveform if self.debug else None
            )
            
        except Exception as e:
            if self.debug:
                print(f"Pulse processing error: {e}")
            return None
    
    def detect_pileup_simple(self, waveform: np.ndarray, primary_peak_idx: int) -> bool:
        """Simplified pile-up detection for short acquisition window"""
        
        # Look for multiple peaks
        threshold = self.noise_threshold * 1.5
        
        # Check for secondary peaks
        if self.pulse_polarity == 'both':
            # Look for any significant secondary peaks
            peaks_pos, _ = signal.find_peaks(waveform, height=threshold, distance=10)
            peaks_neg, _ = signal.find_peaks(-waveform, height=threshold, distance=10)
            total_peaks = len(peaks_pos) + len(peaks_neg)
            return total_peaks > 1
        else:
            # Single polarity check
            if self.pulse_polarity == 'negative':
                peaks, _ = signal.find_peaks(-waveform, height=threshold, distance=10)
            else:
                peaks, _ = signal.find_peaks(waveform, height=threshold, distance=10)
            return len(peaks) > 1
    
    def detect_pileup(self, waveform: np.ndarray, primary_peak_idx: int) -> bool:
        """Detect pulse pile-up using multiple methods"""
        
        # Method 1: Look for multiple peaks
        peaks, properties = signal.find_peaks(-waveform, 
                                             height=self.noise_threshold,
                                             distance=50)
        if len(peaks) > 1:
            # Check if secondary peak is significant
            heights = properties['peak_heights']
            if len(heights) > 1 and heights[1] > heights[0] * 0.3:
                return True
        
        # Method 2: Check pulse tail for anomalies
        tail_start = primary_peak_idx + int(self.pulse_width * self.sample_rate * 0.5)
        if tail_start < len(waveform) - 10:
            tail = waveform[tail_start:]
            if abs(np.min(tail)) > self.noise_threshold * 2:
                return True
        
        # Method 3: Check for abnormal pulse width
        pulse_threshold = abs(waveform[primary_peak_idx]) * 0.1
        pulse_indices = np.where(abs(waveform) > pulse_threshold)[0]
        if len(pulse_indices) > 0:
            pulse_duration = (pulse_indices[-1] - pulse_indices[0]) / self.sample_rate
            if pulse_duration > self.pulse_width * 1.5:
                return True
        
        return False
    
    def add_to_spectrum(self, pulse: PulseData):
        """Add pulse to MCA spectrum"""
        
        if pulse.is_pileup:
            self.rejected_counts += 1
            return
        
        # Convert pulse height to MCA channel
        channel = int(pulse.peak_height * self.adc_to_channel_factor)
        
        # Apply energy calibration if available
        if self.energy_calibration is not None:
            energy = self.pulse_height_to_energy(pulse.peak_height)
            channel = self.energy_to_channel(energy)
        
        # Add to spectrum if within range
        if 0 <= channel < self.num_channels:
            self.spectrum[channel] += 1
            self.total_counts += 1
            
            # Store pulse data
            self.pulse_history.append(pulse)
    
    def pulse_height_to_energy(self, pulse_height: float) -> float:
        """Convert pulse height to energy using calibration"""
        if self.energy_calibration is None:
            return pulse_height
        
        # Polynomial calibration: E = a0 + a1*PH + a2*PH^2 + ...
        coeffs = self.energy_calibration
        return np.polyval(coeffs[::-1], pulse_height)
    
    def energy_to_channel(self, energy: float) -> int:
        """Convert energy to MCA channel"""
        if self.energy_calibration is None:
            return int(energy * self.adc_to_channel_factor)
        
        # Inverse calibration - simplified linear approximation
        # For more accuracy, use polynomial root finding
        channel = int(energy / self.energy_calibration[1])
        return min(max(0, channel), self.num_channels - 1)
    
    def calibrate_energy(self, peak_channels: List[int], peak_energies: List[float], order=2):
        """Perform energy calibration using known peaks
        
        Args:
            peak_channels: List of peak channel numbers
            peak_energies: List of corresponding energies in keV
            order: Polynomial order for calibration (default 2 for quadratic)
        """
        
        if len(peak_channels) != len(peak_energies):
            raise ValueError("Number of channels and energies must match")
        
        if len(peak_channels) < order + 1:
            raise ValueError(f"Need at least {order + 1} peaks for order {order} calibration")
        
        # Fit polynomial: Energy = f(channel)
        self.energy_calibration = np.polyfit(peak_channels, peak_energies, order)
        
        # Calculate calibration quality
        fitted_energies = np.polyval(self.energy_calibration, peak_channels)
        residuals = peak_energies - fitted_energies
        rms_error = np.sqrt(np.mean(residuals**2))
        
        print(f"Energy calibration complete:")
        print(f"  Coefficients: {self.energy_calibration}")
        print(f"  RMS error: {rms_error:.2f} keV")
        
        return self.energy_calibration, rms_error
    
    def acquire_single_pulse(self, timeout=5.0) -> Optional[PulseData]:
        """Acquire and process a single pulse with diagnostic output"""
        
        try:
            # Start acquisition
            self.dso.StartAcquisition()
            
            # Wait for trigger - shorter wait for faster response
            time.sleep(0.01)  # 10ms wait
            
            # Read waveform from configured channel
            waveform = self.dso.ReadSampleData(self.channel)
            
            # Stop acquisition
            self.dso.StopAcquisition()
            
            if waveform and len(waveform) > 0:
                waveform_array = np.array(waveform)
                
                # Diagnostic output in debug mode
                if self.debug:
                    print(f"\nWaveform stats (CH{self.channel}):")
                    print(f"  Samples: {len(waveform_array)}")
                    print(f"  Min: {np.min(waveform_array):.1f}")
                    print(f"  Max: {np.max(waveform_array):.1f}")
                    print(f"  Mean: {np.mean(waveform_array):.1f}")
                    print(f"  StdDev: {np.std(waveform_array):.1f}")
                    
                    # Check if there's a significant deviation from baseline
                    baseline = np.mean(waveform_array[:20])
                    max_deviation = max(abs(np.max(waveform_array) - baseline),
                                      abs(np.min(waveform_array) - baseline))
                    print(f"  Max deviation from baseline: {max_deviation:.1f}")
                
                pulse = self.process_pulse(waveform_array, time.time())
                if pulse:
                    self.add_to_spectrum(pulse)
                    return pulse
                elif self.debug:
                    print("  No valid pulse detected in waveform")
            else:
                if self.debug:
                    print("No waveform data received")
                    
        except Exception as e:
            if self.debug:
                print(f"Acquisition error: {e}")
            try:
                self.dso.StopAcquisition()
            except:
                pass
        
        return None
    
    def test_acquisition(self, num_samples=10):
        """Test acquisition and display diagnostic information
        
        Args:
            num_samples: Number of acquisition attempts to make
        """
        print(f"\n=== Testing Acquisition ({num_samples} samples) ===")
        print(f"Current settings:")
        print(f"  Trigger level: ±{self.trigger_level} mV")
        print(f"  Pulse polarity: {self.pulse_polarity}")
        print(f"  Noise threshold: {self.noise_threshold} mV")
        print(f"  Sample rate: {self.sample_rate/1e6:.1f} MS/s")
        print(f"  Window: {self.acquisition_window*1e6:.1f} μs")
        print("\nAcquiring...")
        
        # Store original debug state
        original_debug = self.debug
        self.debug = True
        
        successful = 0
        for i in range(num_samples):
            print(f"\nSample {i+1}/{num_samples}:")
            pulse = self.acquire_single_pulse(timeout=1.0)
            if pulse:
                successful += 1
                print(f"  ✓ Pulse detected: {pulse.peak_height:.1f} mV")
            else:
                print(f"  ✗ No pulse detected")
            time.sleep(0.1)
        
        # Restore debug state
        self.debug = original_debug
        
        print(f"\n=== Test Results ===")
        print(f"Successful captures: {successful}/{num_samples}")
        print(f"Success rate: {successful/num_samples*100:.1f}%")
        
        if successful == 0:
            print("\n⚠ No pulses detected. Try:")
            print("  1. Check signal connection to CH1")
            print("  2. Verify PMT high voltage is on")
            print("  3. Place radioactive source near detector")
            print("  4. Adjust trigger level (currently ±{self.trigger_level} mV)")
            print("  5. Check pulse polarity setting (currently '{self.pulse_polarity}')")
            print("  6. Manually trigger the scope to verify signal presence")
    
    def acquisition_thread(self):
        """Background thread for continuous acquisition"""
        
        print("Starting acquisition thread...")
        self.start_time = time.time()
        
        while self.acquisition_active:
            try:
                pulse = self.acquire_single_pulse()
                
                if pulse:
                    self.pulse_queue.put(pulse)
                    
                # Update timing statistics
                self.real_time = time.time() - self.start_time
                
                # Simple dead time estimation
                self.live_time = self.real_time * 0.95  # Assume 5% dead time
                
            except Exception as e:
                print(f"Acquisition thread error: {e}")
                time.sleep(0.1)
        
        print("Acquisition thread stopped")
    
    def processing_thread(self):
        """Background thread for processing pulses"""
        
        print("Starting processing thread...")
        
        while self.processing_active:
            try:
                # Get pulse from queue (timeout prevents hanging)
                pulse = self.pulse_queue.get(timeout=0.1)
                
                # Additional processing if needed
                # For now, pulses are already added to spectrum in acquire_single_pulse
                
                # Could add advanced processing here:
                # - Coincidence detection
                # - Anti-coincidence gating
                # - Time-stamped list mode data
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing thread error: {e}")
        
        print("Processing thread stopped")
    
    def start_acquisition(self, duration=None):
        """Start continuous data acquisition
        
        Args:
            duration: Acquisition duration in seconds (None for indefinite)
        """
        
        self.acquisition_active = True
        self.processing_active = True
        
        # Start threads
        acq_thread = threading.Thread(target=self.acquisition_thread)
        proc_thread = threading.Thread(target=self.processing_thread)
        
        acq_thread.start()
        proc_thread.start()
        
        if duration:
            time.sleep(duration)
            self.stop_acquisition()
            acq_thread.join()
            proc_thread.join()
    
    def stop_acquisition(self):
        """Stop data acquisition"""
        
        print("Stopping acquisition...")
        self.acquisition_active = False
        self.processing_active = False
        time.sleep(0.5)  # Allow threads to finish
    
    def save_spectrum(self, filename=None):
        """Save spectrum to CSV file"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"spectrum_{timestamp}.csv"
        
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write metadata
            writer.writerow(['# Radiation Spectrum Data'])
            writer.writerow([f'# Date: {datetime.now()}'])
            writer.writerow([f'# Total Counts: {self.total_counts}'])
            writer.writerow([f'# Live Time: {self.live_time:.2f} s'])
            writer.writerow([f'# Real Time: {self.real_time:.2f} s'])
            writer.writerow([f'# Rejected (pile-up): {self.rejected_counts}'])
            
            if self.energy_calibration is not None:
                writer.writerow([f'# Energy Calibration: {self.energy_calibration.tolist()}'])
            
            writer.writerow([])
            
            # Write spectrum data
            writer.writerow(['Channel', 'Counts', 'Energy_keV'])
            
            for channel, counts in enumerate(self.spectrum):
                energy = self.pulse_height_to_energy(channel / self.adc_to_channel_factor)
                writer.writerow([channel, counts, energy])
        
        print(f"Spectrum saved to {filename}")
        return filename
    
    def plot_spectrum(self, energy_scale=False, log_scale=True):
        """Plot the current spectrum
        
        Args:
            energy_scale: Plot vs energy instead of channel
            log_scale: Use logarithmic y-axis
        """
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # Main spectrum
        channels = np.arange(self.num_channels)
        
        if energy_scale and self.energy_calibration is not None:
            x_data = [self.pulse_height_to_energy(ch / self.adc_to_channel_factor) 
                     for ch in channels]
            x_label = 'Energy (keV)'
        else:
            x_data = channels
            x_label = 'Channel'
        
        ax1.step(x_data, self.spectrum, where='mid', linewidth=0.5)
        ax1.set_xlabel(x_label)
        ax1.set_ylabel('Counts')
        ax1.set_title(f'Radiation Spectrum - {self.total_counts} total counts')
        
        if log_scale:
            ax1.set_yscale('log')
            ax1.set_ylim(bottom=0.5)
        
        ax1.grid(True, alpha=0.3)
        
        # Count rate history
        if len(self.pulse_history) > 0:
            times = [p.timestamp - self.start_time for p in self.pulse_history]
            energies = [p.peak_height for p in self.pulse_history]
            
            ax2.scatter(times, energies, s=1, alpha=0.5)
            ax2.set_xlabel('Time (s)')
            ax2.set_ylabel('Pulse Height')
            ax2.set_title('Pulse Height vs Time')
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def find_peaks(self, min_counts=10, min_distance=10):
        """Find peaks in spectrum for calibration
        
        Args:
            min_counts: Minimum counts for peak detection
            min_distance: Minimum distance between peaks (channels)
            
        Returns:
            List of (channel, counts) tuples
        """
        
        # Smooth spectrum for better peak detection
        smoothed = signal.savgol_filter(self.spectrum, 11, 3)
        
        # Find peaks
        peaks, properties = signal.find_peaks(smoothed, 
                                             height=min_counts,
                                             distance=min_distance)
        
        # Refine peak positions using parabolic interpolation
        refined_peaks = []
        for peak in peaks:
            if 1 < peak < self.num_channels - 1:
                # Fit parabola to 3 points around peak
                y = self.spectrum[peak-1:peak+2]
                if len(y) == 3:
                    # Parabolic interpolation
                    a = (y[0] - 2*y[1] + y[2]) / 2
                    b = (y[2] - y[0]) / 2
                    if a < 0:  # Ensure it's a maximum
                        x_offset = -b / (2*a)
                        refined_peak = peak + x_offset
                        refined_peaks.append((refined_peak, self.spectrum[peak]))
        
        # Sort by counts (highest first)
        refined_peaks.sort(key=lambda x: x[1], reverse=True)
        
        print(f"Found {len(refined_peaks)} peaks:")
        for i, (ch, counts) in enumerate(refined_peaks[:10]):  # Show top 10
            energy = self.pulse_height_to_energy(ch / self.adc_to_channel_factor) if self.energy_calibration else 0
            print(f"  Peak {i+1}: Channel {ch:.1f}, Counts {counts}, Energy {energy:.1f} keV")
        
        return refined_peaks
    
    def calculate_resolution(self, peak_channel: int, window: int = 50) -> float:
        """Calculate energy resolution (FWHM) at a peak
        
        Args:
            peak_channel: Channel number of peak
            window: Window size around peak for fitting
            
        Returns:
            FWHM in channels (or keV if calibrated)
        """
        
        # Extract region around peak
        start = max(0, peak_channel - window)
        end = min(self.num_channels, peak_channel + window)
        
        x = np.arange(start, end)
        y = self.spectrum[start:end]
        
        # Fit Gaussian
        try:
            # Initial parameters
            amplitude = y[peak_channel - start]
            mean = peak_channel
            std = 5.0  # Initial guess
            
            def gaussian(x, a, mu, sigma):
                return a * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
            
            popt, _ = optimize.curve_fit(gaussian, x, y, 
                                         p0=[amplitude, mean, std],
                                         bounds=([0, start, 0.1], 
                                                [np.inf, end, window]))
            
            # Calculate FWHM
            fwhm_channels = 2.355 * popt[2]  # FWHM = 2.355 * sigma for Gaussian
            
            if self.energy_calibration is not None:
                # Convert to energy resolution
                energy = self.pulse_height_to_energy(peak_channel / self.adc_to_channel_factor)
                fwhm_kev = fwhm_channels * self.energy_calibration[1]  # Simplified - assumes linear
                resolution_percent = (fwhm_kev / energy) * 100
                
                print(f"Resolution at {energy:.1f} keV: {fwhm_kev:.2f} keV ({resolution_percent:.2f}%)")
                return fwhm_kev
            else:
                print(f"Resolution: {fwhm_channels:.2f} channels")
                return fwhm_channels
                
        except Exception as e:
            print(f"Could not fit Gaussian: {e}")
            return 0

def main():
    """Main function for radiation spectroscopy"""
    
    print("=" * 60)
    print("Radiation Spectroscopy System")
    print("BC-412 Plastic Scintillator with DSO5102P")
    print("=" * 60)
    
    try:
        # Initialize system
        spec = RadiationSpectroscopy(debug=False)
        
        while True:
            print("\n" + "="*40)
            print("Radiation Spectroscopy Menu:")
            print("1. Quick measurement (10 seconds)")
            print("2. Timed acquisition")
            print("3. Continuous acquisition (manual stop)")
            print("4. Energy calibration")
            print("5. Find peaks")
            print("6. Plot spectrum")
            print("7. Save spectrum")
            print("8. Clear spectrum")
            print("9. System statistics")
            print("0. Exit")
            print("="*40)
            
            choice = input("Select option: ").strip()
            
            if choice == '1':
                print("\nAcquiring data for 10 seconds...")
                spec.start_acquisition(duration=10)
                print(f"Acquired {spec.total_counts} counts")
                
            elif choice == '2':
                duration = int(input("Duration (seconds): ") or "60")
                print(f"\nAcquiring data for {duration} seconds...")
                spec.start_acquisition(duration=duration)
                print(f"Acquired {spec.total_counts} counts")
                
            elif choice == '3':
                print("\nStarting continuous acquisition...")
                print("Press Ctrl+C to stop")
                spec.start_acquisition()
                try:
                    while spec.acquisition_active:
                        time.sleep(1)
                        rate = spec.total_counts / max(1, spec.real_time)
                        print(f"\rCounts: {spec.total_counts}, Rate: {rate:.1f} cps", end='')
                except KeyboardInterrupt:
                    spec.stop_acquisition()
                    print(f"\nStopped. Total: {spec.total_counts} counts")
                    
            elif choice == '4':
                print("\nEnergy Calibration")
                print("Example for Na-22: Channel 256 = 511 keV, Channel 640 = 1274 keV")
                
                # Get calibration points
                num_points = int(input("Number of calibration points: ") or "2")
                channels = []
                energies = []
                
                for i in range(num_points):
                    ch = float(input(f"Peak {i+1} channel: "))
                    en = float(input(f"Peak {i+1} energy (keV): "))
                    channels.append(ch)
                    energies.append(en)
                
                order = int(input("Polynomial order (1=linear, 2=quadratic): ") or "1")
                spec.calibrate_energy(channels, energies, order)
                
            elif choice == '5':
                min_counts = int(input("Minimum counts for peak: ") or "10")
                peaks = spec.find_peaks(min_counts=min_counts)
                
            elif choice == '6':
                energy = input("Plot vs energy? (y/n): ").lower() == 'y'
                fig = spec.plot_spectrum(energy_scale=energy)
                plt.show()
                
            elif choice == '7':
                filename = input("Filename (empty for auto): ").strip() or None
                spec.save_spectrum(filename)
                
            elif choice == '8':
                if input("Clear spectrum? (y/n): ").lower() == 'y':
                    spec.spectrum.fill(0)
                    spec.total_counts = 0
                    spec.rejected_counts = 0
                    spec.pulse_history.clear()
                    print("Spectrum cleared")
                    
            elif choice == '9':
                print("\n=== System Statistics ===")
                print(f"Total counts: {spec.total_counts}")
                print(f"Rejected (pile-up): {spec.rejected_counts}")
                if spec.real_time > 0:
                    print(f"Count rate: {spec.total_counts/spec.real_time:.1f} cps")
                    print(f"Live time: {spec.live_time:.2f} s")
                    print(f"Real time: {spec.real_time:.2f} s")
                    print(f"Dead time: {(1 - spec.live_time/spec.real_time)*100:.1f}%")
                
            elif choice == '0':
                print("Exiting...")
                spec.stop_acquisition()
                break
                
            else:
                print("Invalid option")
                
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())