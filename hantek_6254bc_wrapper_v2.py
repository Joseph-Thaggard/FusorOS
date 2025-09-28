#!/usr/bin/env python3
"""
Radiation Spectroscopy System for Hantek 6254BC
Using official Hantek SDK (HTHardDll.dll)
Designed for BC-412 plastic scintillator with PMT
"""

import ctypes
import numpy as np
import time
import os
import sys
import csv
from datetime import datetime
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple
import threading
import queue

# Constants from SDK
MAX_CH_NUM = 4
CHANNEL_DATA_SIZE = 65536  # 64KB max per channel

# Timebase indices (from SDK documentation)
TIMEBASE_INDICES = {
    '2ns': 0, '5ns': 1, '10ns': 2, '20ns': 3, '50ns': 4,
    '100ns': 5, '200ns': 6, '500ns': 7, '1us': 8, '2us': 9,
    '5us': 10, '10us': 11, '20us': 12, '50us': 13, '100us': 14,
    '200us': 15, '500us': 16, '1ms': 17, '2ms': 18, '5ms': 19,
    '10ms': 20, '20ms': 21, '50ms': 22, '100ms': 23
}

# Voltage division indices
VOLTAGE_INDICES = {
    '2mV': 0, '5mV': 1, '10mV': 2, '20mV': 3, '50mV': 4,
    '100mV': 5, '200mV': 6, '500mV': 7, '1V': 8, '2V': 9, '5V': 10, '10V': 11
}

# Structures from SDK
class RELAYCONTROL(ctypes.Structure):
    """Hardware relay control structure"""
    _fields_ = [
        ("bCHEnable", ctypes.c_bool * MAX_CH_NUM),
        ("nCHVoltDIV", ctypes.c_ushort * MAX_CH_NUM),
        ("nCHCoupling", ctypes.c_ushort * MAX_CH_NUM),
        ("bCHBWLimit", ctypes.c_bool * MAX_CH_NUM),
        ("nTrigSource", ctypes.c_ushort),
        ("bTrigFilt", ctypes.c_bool),
        ("nALT", ctypes.c_ushort)
    ]

class CONTROLDATA(ctypes.Structure):
    """Control data structure for acquisition"""
    _fields_ = [
        ("nCHSet", ctypes.c_ushort),
        ("nTimeDIV", ctypes.c_ushort),
        ("nTriggerSource", ctypes.c_ushort),
        ("nHTriggerPos", ctypes.c_ushort),
        ("nVTriggerPos", ctypes.c_ushort),
        ("nTriggerSlope", ctypes.c_ushort),
        ("nBufferLen", ctypes.c_ulong),
        ("nReadDataLen", ctypes.c_ulong),
        ("nAlreadyReadLen", ctypes.c_ulong),
        ("nALT", ctypes.c_ushort),
        ("nETSOpen", ctypes.c_ushort),
        ("nLastAddress", ctypes.c_ulong),    # For SCAN/ROLL modes
        ("nAlready", ctypes.c_ulong)          # For SCAN modes
    ]

@dataclass
class Pulse:
    """Radiation pulse data"""
    timestamp: float
    peak_height: float
    energy: float
    baseline: float
    fwhm: float
    is_pileup: bool

class HantekSDK:
    """Wrapper for Hantek SDK DLL functions"""
    
    def __init__(self, dll_path: str = None):
        """Initialize SDK wrapper"""
        if dll_path is None:
            # Search for SDK in common locations
            search_paths = [
                r"C:\Program Files\Hantek6000\SDK",
                r"C:\Program Files (x86)\Hantek6000\SDK",
                r"C:\Hantek\SDK",
                os.path.dirname(os.path.abspath(__file__))
            ]
            
            for path in search_paths:
                hard_dll = os.path.join(path, "HTHardDll.dll")
                if os.path.exists(hard_dll):
                    dll_path = path
                    break
            
            if dll_path is None:
                raise FileNotFoundError("Hantek SDK not found. Please install Hantek software.")
        
        # Load DLLs
        self.hard_dll = ctypes.CDLL(os.path.join(dll_path, "HTHardDll.dll"))
        self.soft_dll = ctypes.CDLL(os.path.join(dll_path, "HTSoftDll.dll"))
        
        # Setup function signatures
        self._setup_functions()
        
    def _setup_functions(self):
        """Setup DLL function signatures"""
        # dsoHTSearchDevice
        self.hard_dll.dsoHTSearchDevice.argtypes = [ctypes.POINTER(ctypes.c_short)]
        self.hard_dll.dsoHTSearchDevice.restype = ctypes.c_ushort
        
        # dsoInitHard
        self.hard_dll.dsoInitHard.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoInitHard.restype = ctypes.c_ushort
        
        # dsoHTDeviceConnect
        self.hard_dll.dsoHTDeviceConnect.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoHTDeviceConnect.restype = ctypes.c_ushort
        
        # dsoHTSetCHPos
        self.hard_dll.dsoHTSetCHPos.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort,
            ctypes.c_ushort, ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetCHPos.restype = ctypes.c_ushort
        
        # dsoHTSetVTriggerLevel
        self.hard_dll.dsoHTSetVTriggerLevel.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetVTriggerLevel.restype = ctypes.c_ushort
        
        # dsoHTSetHTriggerLength
        self.hard_dll.dsoHTSetHTriggerLength.argtypes = [
            ctypes.c_ushort, ctypes.POINTER(CONTROLDATA), ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetHTriggerLength.restype = ctypes.c_ushort
        
        # dsoHTSetCHAndTrigger
        self.hard_dll.dsoHTSetCHAndTrigger.argtypes = [
            ctypes.c_ushort, ctypes.POINTER(RELAYCONTROL), ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetCHAndTrigger.restype = ctypes.c_ushort
        
        # dsoHTSetSampleRate
        self.hard_dll.dsoHTSetSampleRate.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, 
            ctypes.POINTER(RELAYCONTROL), ctypes.POINTER(CONTROLDATA)
        ]
        self.hard_dll.dsoHTSetSampleRate.restype = ctypes.c_ushort
        
        # dsoHTStartCollectData
        self.hard_dll.dsoHTStartCollectData.argtypes = [ctypes.c_ushort, ctypes.c_ushort]
        self.hard_dll.dsoHTStartCollectData.restype = ctypes.c_ushort
        
        # dsoHTGetState
        self.hard_dll.dsoHTGetState.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoHTGetState.restype = ctypes.c_ushort
        
        # dsoHTGetData
        self.hard_dll.dsoHTGetData.argtypes = [
            ctypes.c_ushort,
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(CONTROLDATA)
        ]
        self.hard_dll.dsoHTGetData.restype = ctypes.c_ushort
        
        # dsoHTADCCHModGain
        self.hard_dll.dsoHTADCCHModGain.argtypes = [ctypes.c_ushort, ctypes.c_ushort]
        self.hard_dll.dsoHTADCCHModGain.restype = ctypes.c_ushort
        
        # dsoHTSetAmpCalibrate
        self.hard_dll.dsoHTSetAmpCalibrate.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort,
            ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)
        ]
        self.hard_dll.dsoHTSetAmpCalibrate.restype = ctypes.c_ushort
        
        # dsoHTSetRamAndTrigerControl  
        self.hard_dll.dsoHTSetRamAndTrigerControl.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort, 
            ctypes.c_ushort, ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetRamAndTrigerControl.restype = ctypes.c_ushort
        
        # dsoHTSetTrigerMode
        self.hard_dll.dsoHTSetTrigerMode.argtypes = [
            ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort
        ]
        self.hard_dll.dsoHTSetTrigerMode.restype = ctypes.c_ushort

class RadiationSpectroscopy:
    """Main radiation spectroscopy system"""
    
    def __init__(self, device_index: int = 0, channel: int = 0, debug: bool = False):
        """
        Initialize radiation spectroscopy system
        
        Args:
            device_index: Hantek device index (0 for first device)
            channel: Channel to use (0-3 for CH1-CH4)
            debug: Enable debug output
        """
        self.device_index = device_index
        self.channel = channel
        self.debug = debug
        
        # Initialize SDK
        print("Initializing Hantek SDK...")
        self.sdk = HantekSDK()
        
        # Device connection
        self.connected = False
        self.connect_device()
        
        # Setup default parameters for BC-412 scintillator
        self.setup_for_radiation()
        
        # Data storage
        self.spectrum = np.zeros(8192)  # 8192 channel MCA
        self.pulse_history = deque(maxlen=1000)
        self.total_counts = 0
        self.rejected_counts = 0
        
        # Calibration
        self.energy_calibration = lambda ch: ch * 2.0  # Default 2 keV/channel
        
        # Acquisition control
        self.acquiring = False
        self.acquisition_thread = None
        self.start_time = time.time()
        self.live_time = 0
        self.real_time = 0
        
    def connect_device(self):
        """Connect to Hantek device"""
        # Search for devices
        dev_info = (ctypes.c_short * 32)()
        num_devices = self.sdk.hard_dll.dsoHTSearchDevice(dev_info)
        
        if num_devices == 0:
            raise RuntimeError("No Hantek devices found")
        
        print(f"Found {num_devices} device(s)")
        
        # Initialize device
        if self.sdk.hard_dll.dsoInitHard(self.device_index) == 0:
            raise RuntimeError("Failed to initialize device")
        
        # Check connection
        if self.sdk.hard_dll.dsoHTDeviceConnect(self.device_index) == 0:
            raise RuntimeError("Device not connected")
        
        self.connected = True
        print(f"Connected to device {self.device_index}")
        
    def setup_for_radiation(self):
        """Configure scope for radiation detection"""
        # Setup relay control
        self.relay_control = RELAYCONTROL()
        
        # Enable selected channel
        for i in range(MAX_CH_NUM):
            self.relay_control.bCHEnable[i] = (i == self.channel)
        
        # Set voltage range (start with 500mV for BC-412)
        self.relay_control.nCHVoltDIV[self.channel] = VOLTAGE_INDICES['500mV']
        
        # DC coupling
        self.relay_control.nCHCoupling[self.channel] = 0  # DC
        
        # No bandwidth limit for fast pulses
        self.relay_control.bCHBWLimit[self.channel] = False
        
        # Trigger settings
        self.relay_control.nTrigSource = self.channel
        self.relay_control.bTrigFilt = False  # No filter
        self.relay_control.nALT = 0  # No alternate
        
        # Setup control data
        self.control_data = CONTROLDATA()
        self.control_data.nCHSet = 1 << self.channel  # Enable channel bit
        self.control_data.nTimeDIV = TIMEBASE_INDICES['20us']  # 20us/div for 80us pulses
        self.control_data.nTriggerSource = self.channel
        self.control_data.nHTriggerPos = 20  # 20% pre-trigger
        self.control_data.nVTriggerPos = 100  # Trigger level (adjust based on signal)
        self.control_data.nTriggerSlope = 1  # Falling edge for negative pulses
        self.control_data.nBufferLen = 10000  # Buffer size
        self.control_data.nReadDataLen = 10000  # Read length
        
        # Apply settings
        self._apply_settings()
        
    def _apply_settings(self):
        """Apply hardware settings to device"""
        # Set channel mode (single channel = 1)
        ch_mode = sum(self.relay_control.bCHEnable)
        self.sdk.hard_dll.dsoHTADCCHModGain(self.device_index, ch_mode)
        
        # Set channel and trigger
        self.sdk.hard_dll.dsoHTSetCHAndTrigger(
            self.device_index,
            ctypes.byref(self.relay_control),
            self.control_data.nTimeDIV
        )
        
        # Set sample rate
        self.sdk.hard_dll.dsoHTSetSampleRate(
            self.device_index,
            0,  # Normal mode
            ctypes.byref(self.relay_control),
            ctypes.byref(self.control_data)
        )
        
        # Set channel position (center)
        self.sdk.hard_dll.dsoHTSetCHPos(
            self.device_index,
            self.relay_control.nCHVoltDIV[self.channel],
            128,  # Center position
            self.channel,
            ch_mode
        )
        
        # Set trigger level
        self.sdk.hard_dll.dsoHTSetVTriggerLevel(
            self.device_index,
            self.control_data.nVTriggerPos,
            4  # Sensitivity
        )
        
        # Set trigger mode (edge trigger)
        self.sdk.hard_dll.dsoHTSetTrigerMode(
            self.device_index,
            0,  # Edge trigger
            self.control_data.nTriggerSlope,
            0   # DC coupling
        )
        
        # Set RAM and trigger control
        self.sdk.hard_dll.dsoHTSetRamAndTrigerControl(
            self.device_index,
            self.control_data.nTimeDIV,
            self.control_data.nCHSet,
            self.control_data.nTriggerSource,
            0  # No peak detection
        )
        
        # Set horizontal trigger length
        self.sdk.hard_dll.dsoHTSetHTriggerLength(
            self.device_index,
            ctypes.byref(self.control_data),
            ch_mode
        )
        
        # Amplitude calibration
        volt_divs = (ctypes.c_ushort * 4)()
        ch_positions = (ctypes.c_ushort * 4)()
        for i in range(4):
            volt_divs[i] = self.relay_control.nCHVoltDIV[i]
            ch_positions[i] = 128
        
        self.sdk.hard_dll.dsoHTSetAmpCalibrate(
            self.device_index,
            self.control_data.nCHSet,
            self.control_data.nTimeDIV,
            volt_divs,
            ch_positions
        )
        
    def acquire_pulse(self) -> Optional[Pulse]:
        """Acquire a single pulse"""
        try:
            # Start acquisition (single shot mode)
            start_control = 0x04  # Stop after one acquisition
            if self.sdk.hard_dll.dsoHTStartCollectData(self.device_index, start_control) == 0:
                return None
            
            # Wait for trigger and acquisition complete
            timeout = time.time() + 0.1  # 100ms timeout
            while time.time() < timeout:
                state = self.sdk.hard_dll.dsoHTGetState(self.device_index)
                if state & 0x02:  # Acquisition complete
                    break
                time.sleep(0.001)
            else:
                return None  # Timeout
            
            # Read data
            ch_data = [
                (ctypes.c_ushort * self.control_data.nReadDataLen)()
                for _ in range(4)
            ]
            
            if self.sdk.hard_dll.dsoHTGetData(
                self.device_index,
                ch_data[0], ch_data[1], ch_data[2], ch_data[3],
                ctypes.byref(self.control_data)
            ) == 0:
                return None
            
            # Extract channel data
            raw_data = np.array(ch_data[self.channel][:self.control_data.nReadDataLen])
            
            # Convert to voltage
            # Formula: (data - position) * voltage_div / 32
            position = 128
            volt_div_values = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
            volt_div = volt_div_values[self.relay_control.nCHVoltDIV[self.channel]]
            
            voltage_data = (raw_data.astype(float) - position) * volt_div / 32.0
            
            # Process pulse
            return self._process_pulse(voltage_data)
            
        except Exception as e:
            if self.debug:
                print(f"Acquisition error: {e}")
            return None
    
    def _process_pulse(self, data: np.ndarray) -> Optional[Pulse]:
        """Process raw pulse data"""
        if len(data) < 100:
            return None
        
        # Find baseline (average of first 20% of samples)
        baseline_samples = int(len(data) * 0.2)
        baseline = np.mean(data[:baseline_samples])
        
        # Subtract baseline
        pulse_data = data - baseline
        
        # Find peak (minimum for negative pulses)
        peak_idx = np.argmin(pulse_data)
        peak_height = abs(pulse_data[peak_idx])
        
        # Check if valid pulse (above noise threshold)
        if peak_height < 0.02:  # 20mV threshold
            return None
        
        # Check for pile-up (multiple peaks)
        is_pileup = self._detect_pileup(pulse_data, peak_idx)
        
        # Calculate FWHM
        fwhm = self._calculate_fwhm(pulse_data, peak_idx)
        
        # Convert to energy channel
        energy_channel = int(peak_height * 1000)  # Simple linear conversion
        if energy_channel >= 8192:
            energy_channel = 8191
        
        # Create pulse object
        pulse = Pulse(
            timestamp=time.time(),
            peak_height=peak_height,
            energy=self.energy_calibration(energy_channel),
            baseline=baseline,
            fwhm=fwhm,
            is_pileup=is_pileup
        )
        
        return pulse
    
    def _detect_pileup(self, data: np.ndarray, peak_idx: int) -> bool:
        """Detect pulse pile-up"""
        # Simple pile-up detection: look for multiple peaks
        threshold = abs(data[peak_idx]) * 0.5
        
        # Find all points below threshold (for negative pulses)
        below_threshold = np.where(data < -threshold)[0]
        
        if len(below_threshold) < 2:
            return False
        
        # Check for gaps indicating multiple pulses
        gaps = np.diff(below_threshold)
        if np.any(gaps > 20):  # Gap of >20 samples
            return True
        
        return False
    
    def _calculate_fwhm(self, data: np.ndarray, peak_idx: int) -> float:
        """Calculate Full Width at Half Maximum"""
        half_max = data[peak_idx] / 2.0
        
        # Find points at half maximum
        left_idx = peak_idx
        while left_idx > 0 and data[left_idx] < half_max:
            left_idx -= 1
        
        right_idx = peak_idx
        while right_idx < len(data) - 1 and data[right_idx] < half_max:
            right_idx += 1
        
        # Convert to time (assuming sample rate)
        fwhm_samples = right_idx - left_idx
        return fwhm_samples  # In samples for now
    
    def acquisition_loop(self):
        """Main acquisition loop (runs in thread)"""
        self.acquiring = True
        pulse_count = 0
        
        while self.acquiring:
            pulse = self.acquire_pulse()
            
            if pulse:
                if not pulse.is_pileup:
                    # Add to spectrum
                    energy_channel = int(pulse.peak_height * 1000)
                    if 0 <= energy_channel < 8192:
                        self.spectrum[energy_channel] += 1
                        self.total_counts += 1
                    
                    # Store pulse
                    self.pulse_history.append(pulse)
                    pulse_count += 1
                    
                    if self.debug and pulse_count % 100 == 0:
                        rate = pulse_count / (time.time() - self.start_time)
                        print(f"Count rate: {rate:.1f} Hz, Total: {self.total_counts}")
                else:
                    self.rejected_counts += 1
            
            # Update timing
            self.real_time = time.time() - self.start_time
            self.live_time = self.real_time * (self.total_counts / (self.total_counts + self.rejected_counts))
    
    def start_acquisition(self):
        """Start acquisition in background thread"""
        if not self.acquiring:
            self.start_time = time.time()
            self.acquisition_thread = threading.Thread(target=self.acquisition_loop)
            self.acquisition_thread.start()
            print("Acquisition started")
    
    def stop_acquisition(self):
        """Stop acquisition"""
        if self.acquiring:
            self.acquiring = False
            if self.acquisition_thread:
                self.acquisition_thread.join(timeout=2)
            print("Acquisition stopped")
    
    def calibrate_energy(self, channels: List[int], energies: List[float]):
        """
        Calibrate energy scale
        
        Args:
            channels: List of peak channel numbers
            energies: List of corresponding energies in keV
        """
        if len(channels) < 2:
            print("Need at least 2 points for calibration")
            return
        
        # Linear fit
        coeffs = np.polyfit(channels, energies, 1)
        self.energy_calibration = lambda ch: coeffs[0] * ch + coeffs[1]
        
        print(f"Energy calibration: E = {coeffs[0]:.3f} * channel + {coeffs[1]:.3f} keV")
    
    def save_spectrum(self, filename: str):
        """Save spectrum to CSV file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not filename.endswith('.csv'):
            filename = f"{filename}_{timestamp}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Channel', 'Counts', 'Energy_keV'])
            
            for i in range(len(self.spectrum)):
                if self.spectrum[i] > 0:
                    energy = self.energy_calibration(i)
                    writer.writerow([i, int(self.spectrum[i]), energy])
        
        # Write metadata
        meta_filename = filename.replace('.csv', '_meta.txt')
        with open(meta_filename, 'w') as f:
            f.write(f"Acquisition date: {datetime.now()}\n")
            f.write(f"Real time: {self.real_time:.1f} s\n")
            f.write(f"Live time: {self.live_time:.1f} s\n")
            f.write(f"Total counts: {self.total_counts}\n")
            f.write(f"Rejected counts: {self.rejected_counts}\n")
            f.write(f"Count rate: {self.total_counts/self.real_time if self.real_time > 0 else 0:.1f} cps\n")
        
        print(f"Spectrum saved to {filename}")
    
    def clear_spectrum(self):
        """Clear spectrum and counters"""
        self.spectrum.fill(0)
        self.total_counts = 0
        self.rejected_counts = 0
        self.pulse_history.clear()
        self.start_time = time.time()
        print("Spectrum cleared")
    
    def get_statistics(self) -> dict:
        """Get acquisition statistics"""
        count_rate = self.total_counts / self.real_time if self.real_time > 0 else 0
        dead_time = 1 - (self.live_time / self.real_time) if self.real_time > 0 else 0
        
        return {
            'total_counts': self.total_counts,
            'rejected_counts': self.rejected_counts,
            'real_time': self.real_time,
            'live_time': self.live_time,
            'count_rate': count_rate,
            'dead_time_percent': dead_time * 100
        }

def main():
    """Main entry point for testing"""
    print("==============================================")
    print("Hantek 6254BC Radiation Spectroscopy System")
    print("==============================================\n")
    
    try:
        # Initialize system
        spec = RadiationSpectroscopy(device_index=0, channel=0, debug=True)
        
        while True:
            print("\n1. Start acquisition")
            print("2. Stop acquisition")
            print("3. Show statistics")
            print("4. Save spectrum")
            print("5. Clear spectrum")
            print("6. Energy calibration")
            print("7. Exit")
            
            choice = input("Select option: ")
            
            if choice == '1':
                spec.start_acquisition()
            elif choice == '2':
                spec.stop_acquisition()
            elif choice == '3':
                stats = spec.get_statistics()
                print(f"\nStatistics:")
                print(f"  Total counts: {stats['total_counts']}")
                print(f"  Count rate: {stats['count_rate']:.1f} cps")
                print(f"  Real time: {stats['real_time']:.1f} s")
                print(f"  Live time: {stats['live_time']:.1f} s")
                print(f"  Dead time: {stats['dead_time_percent']:.1f}%")
            elif choice == '4':
                filename = input("Enter filename (without extension): ")
                spec.save_spectrum(filename)
            elif choice == '5':
                spec.clear_spectrum()
            elif choice == '6':
                print("Enter calibration points (Na-22: 511, 1274 keV)")
                ch1 = int(input("Channel 1: "))
                e1 = float(input("Energy 1 (keV): "))
                ch2 = int(input("Channel 2: "))
                e2 = float(input("Energy 2 (keV): "))
                spec.calibrate_energy([ch1, ch2], [e1, e2])
            elif choice == '7':
                spec.stop_acquisition()
                break
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()