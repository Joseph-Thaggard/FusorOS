#!/usr/bin/env python3
"""
Hantek 6254BC SDK Wrapper for Radiation Detection
Supports BC-412 scintillator with PMT for spectroscopy
Windows-specific implementation using HTHardDll SDK
Corrected to use actual Hantek SDK structure
"""

import ctypes
import numpy as np
import time
import os
import csv
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from enum import Enum
import threading
import queue
from pathlib import Path

# ================================================================================
# SDK CONSTANTS (from documentation)
# ================================================================================

MAX_CH_NUM = 4
MAX_BUFFER_SIZE = 65536  # 64KB per channel

# Timebase indices (Table 1 from SDK)
TIMEBASE_INDICES = {
    '2ns': 0, '5ns': 1, '10ns': 2, '20ns': 3, '50ns': 4,
    '100ns': 5, '200ns': 6, '500ns': 7, '1us': 8, '2us': 9,
    '5us': 10, '10us': 11, '20us': 12, '50us': 13, '100us': 14,
    '200us': 15, '500us': 16, '1ms': 17, '2ms': 18, '5ms': 19,
    '10ms': 20, '20ms': 21, '50ms': 22, '100ms': 23, '200ms': 24,
    '500ms': 25, '1s': 26, '2s': 27, '5s': 28, '10s': 29,
    '20s': 30, '50s': 31, '100s': 32, '200s': 33, '500s': 34, '1000s': 35
}

# Voltage division indices (Table 3 from SDK)
VOLTAGE_DIV_INDICES = {
    '2mV': 0, '5mV': 1, '10mV': 2, '20mV': 3, '50mV': 4,
    '100mV': 5, '200mV': 6, '500mV': 7, '1V': 8, '2V': 9, '5V': 10, '10V': 11
}

# Actual voltage values in Volts (for calculations)
VOLTAGE_DIV_VALUES = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]

# ================================================================================
# SDK STRUCTURES (from HTHardDll documentation)
# ================================================================================

class RELAYCONTROL(ctypes.Structure):
    """Hardware relay control structure"""
    _fields_ = [
        ("bCHEnable", ctypes.c_bool * MAX_CH_NUM),      # Channel on/off
        ("nCHVoltDIV", ctypes.c_ushort * MAX_CH_NUM),   # Voltage division index
        ("nCHCoupling", ctypes.c_ushort * MAX_CH_NUM),  # 0=DC, 1=AC, 2=GND
        ("bCHBWLimit", ctypes.c_bool * MAX_CH_NUM),     # Bandwidth limit
        ("nTrigSource", ctypes.c_ushort),               # 0-3=CH1-4, 5=EXT, 6=EXT/10
        ("bTrigFilt", ctypes.c_bool),                   # High frequency rejection
        ("nALT", ctypes.c_ushort)                       # Alternate trigger
    ]

class CONTROLDATA(ctypes.Structure):
    """Control data structure for acquisition"""
    _fields_ = [
        ("nCHSet", ctypes.c_ushort),           # Channel enable bits
        ("nTimeDIV", ctypes.c_ushort),         # Timebase index
        ("nTriggerSource", ctypes.c_ushort),   # Trigger source
        ("nHTriggerPos", ctypes.c_ushort),     # Horizontal trigger position (0-100)
        ("nVTriggerPos", ctypes.c_ushort),     # Vertical trigger position (0-255)
        ("nTriggerSlope", ctypes.c_ushort),    # 0=rise, 1=fall
        ("nBufferLen", ctypes.c_ulong),        # Buffer length
        ("nReadDataLen", ctypes.c_ulong),      # Data length to read
        ("nAlreadyReadLen", ctypes.c_ulong),   # Already read length
        ("nALT", ctypes.c_ushort),             # Alternate trigger
        ("nETSOpen", ctypes.c_ushort),         # ETS mode
        ("nLastAddress", ctypes.c_ulong),      # For SCAN mode
        ("nAlready", ctypes.c_ulong)           # For SCAN mode
    ]

# ================================================================================
# DATA STRUCTURES
# ================================================================================

@dataclass
class PulseData:
    """Container for individual pulse information"""
    timestamp: float
    channel: int
    peak_height: float  # in V
    pulse_area: float
    baseline: float
    fwhm: float  # Full Width at Half Maximum in microseconds
    is_pileup: bool
    raw_waveform: Optional[np.ndarray] = None

@dataclass
class AcquisitionSettings:
    """Configuration for data acquisition"""
    timebase: str = '20us'  # For 80us pulses
    voltage_div: str = '500mV'  # Initial range for PMT signals
    samples_per_acquisition: int = 10000  # Samples to read
    trigger_level: int = 100  # 0-255 scale
    trigger_channel: int = 0  # 0-3 for CH1-4
    trigger_slope: int = 1  # 1 = falling edge for negative pulses
    channels_active: List[int] = None
    channel_mode: int = 1  # 1, 2, or 4 channel mode
    
    def __post_init__(self):
        if self.channels_active is None:
            self.channels_active = [0]  # Default to channel 1 (index 0)

# ================================================================================
# HANTEK SDK WRAPPER
# ================================================================================

class Hantek6254BC:
    """
    Wrapper for Hantek 6254BC oscilloscope using HTHardDll SDK
    Provides both real hardware interface and simulation mode
    """
    
    def __init__(self, sdk_path: str = None, test_mode: bool = False):
        """
        Initialize Hantek wrapper
        
        Args:
            sdk_path: Path to SDK folder containing DLLs
            test_mode: If True, operates in simulation mode without hardware
        """
        self.test_mode = test_mode
        self.device_index = 0  # First device
        self.hard_dll = None
        self.soft_dll = None
        self.meas_dll = None
        self.is_connected = False
        self.settings = AcquisitionSettings()
        
        # Control structures
        self.relay_control = RELAYCONTROL()
        self.control_data = CONTROLDATA()
        
        # Data buffers for each channel
        self.channel_buffers = {
            0: np.zeros(self.settings.samples_per_acquisition, dtype=np.uint16),
            1: np.zeros(self.settings.samples_per_acquisition, dtype=np.uint16),
            2: np.zeros(self.settings.samples_per_acquisition, dtype=np.uint16),
            3: np.zeros(self.settings.samples_per_acquisition, dtype=np.uint16)
        }
        
        if not test_mode:
            self._load_sdk(sdk_path)
        else:
            print("=== HANTEK 6254BC WRAPPER - TEST MODE ===")
            print("Simulating hardware responses for development")
            self.is_connected = True
    
    def _load_sdk(self, sdk_path: str = None):
        """Load the Hantek SDK DLLs"""
        
        # Search for SDK in common locations
        search_paths = []
        if sdk_path:
            search_paths.append(sdk_path)
        
        # Common installation paths
        search_paths.extend([
            r"C:\Program Files\Hantek6000\SDK",
            r"C:\Program Files (x86)\Hantek6000\SDK",
            r"C:\Hantek\SDK",
            r".\SDK",
            r"."
        ])
        
        for path in search_paths:
            hard_dll_path = os.path.join(path, "HTHardDll.dll")
            soft_dll_path = os.path.join(path, "HTSoftDll.dll")
            meas_dll_path = os.path.join(path, "HTMeasDll.dll")
            
            if os.path.exists(hard_dll_path):
                try:
                    self.hard_dll = ctypes.CDLL(hard_dll_path)
                    self.soft_dll = ctypes.CDLL(soft_dll_path) if os.path.exists(soft_dll_path) else None
                    self.meas_dll = ctypes.CDLL(meas_dll_path) if os.path.exists(meas_dll_path) else None
                    self._setup_dll_functions()
                    print(f"✓ Loaded Hantek SDK from: {path}")
                    return
                except Exception as e:
                    print(f"Failed to load DLL from {path}: {e}")
        
        # If no DLL found, offer test mode
        print("WARNING: HTHardDll.dll not found. Running in test mode.")
        print("To use real hardware, ensure SDK is installed.")
        self.test_mode = True
        self.is_connected = True
    
    def _setup_dll_functions(self):
        """Define function signatures for SDK calls based on documentation"""
        if not self.hard_dll:
            return
        
        # Device discovery and initialization
        self.hard_dll.dsoHTSearchDevice.argtypes = [ctypes.POINTER(ctypes.c_short)]
        self.hard_dll.dsoHTSearchDevice.restype = ctypes.c_ushort
        
        self.hard_dll.dsoInitHard.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoInitHard.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTDeviceConnect.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoHTDeviceConnect.restype = ctypes.c_ushort
        
        # Channel configuration
        self.hard_dll.dsoHTSetCHPos.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # voltage div
            ctypes.c_ushort,  # position (0-255)
            ctypes.c_ushort,  # channel
            ctypes.c_ushort   # channel mode
        ]
        self.hard_dll.dsoHTSetCHPos.restype = ctypes.c_ushort
        
        # Trigger configuration
        self.hard_dll.dsoHTSetVTriggerLevel.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # position (0-255)
            ctypes.c_ushort   # sensitivity
        ]
        self.hard_dll.dsoHTSetVTriggerLevel.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTSetHTriggerLength.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.POINTER(CONTROLDATA),  # control data
            ctypes.c_ushort   # channel mode
        ]
        self.hard_dll.dsoHTSetHTriggerLength.restype = ctypes.c_ushort
        
        # Relay and channel setup
        self.hard_dll.dsoHTSetCHAndTrigger.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.POINTER(RELAYCONTROL),  # relay control
            ctypes.c_ushort   # time div
        ]
        self.hard_dll.dsoHTSetCHAndTrigger.restype = ctypes.c_ushort
        
        # Sample rate configuration
        self.hard_dll.dsoHTSetSampleRate.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # YT format (0=Normal, 1=Scan, 2=Roll)
            ctypes.POINTER(RELAYCONTROL),
            ctypes.POINTER(CONTROLDATA)
        ]
        self.hard_dll.dsoHTSetSampleRate.restype = ctypes.c_ushort
        
        # Data acquisition
        self.hard_dll.dsoHTStartCollectData.argtypes = [ctypes.c_ushort, ctypes.c_ushort]
        self.hard_dll.dsoHTStartCollectData.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTGetState.argtypes = [ctypes.c_ushort]
        self.hard_dll.dsoHTGetState.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTGetData.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.POINTER(ctypes.c_ushort),  # CH1 data
            ctypes.POINTER(ctypes.c_ushort),  # CH2 data
            ctypes.POINTER(ctypes.c_ushort),  # CH3 data
            ctypes.POINTER(ctypes.c_ushort),  # CH4 data
            ctypes.POINTER(CONTROLDATA)
        ]
        self.hard_dll.dsoHTGetData.restype = ctypes.c_ushort
        
        # Additional setup functions
        self.hard_dll.dsoHTADCCHModGain.argtypes = [ctypes.c_ushort, ctypes.c_ushort]
        self.hard_dll.dsoHTADCCHModGain.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTSetTrigerMode.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # trigger mode (0=edge, 1=pulse, 2=video)
            ctypes.c_ushort,  # trigger slope (0=rise, 1=fall)
            ctypes.c_ushort   # trigger couple (0=DC, 1=AC)
        ]
        self.hard_dll.dsoHTSetTrigerMode.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTSetRamAndTrigerControl.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # time div
            ctypes.c_ushort,  # CH set
            ctypes.c_ushort,  # trigger source
            ctypes.c_ushort   # peak detection
        ]
        self.hard_dll.dsoHTSetRamAndTrigerControl.restype = ctypes.c_ushort
        
        self.hard_dll.dsoHTSetAmpCalibrate.argtypes = [
            ctypes.c_ushort,  # device index
            ctypes.c_ushort,  # CH set
            ctypes.c_ushort,  # time div
            ctypes.POINTER(ctypes.c_ushort),  # volt div array
            ctypes.POINTER(ctypes.c_ushort)   # position array
        ]
        self.hard_dll.dsoHTSetAmpCalibrate.restype = ctypes.c_ushort
    
    # ============================================================================
    # CONNECTION MANAGEMENT
    # ============================================================================
    
    def connect(self) -> bool:
        """
        Connect to the oscilloscope
        
        Returns:
            True if connection successful
        """
        if self.test_mode:
            self.is_connected = True
            print("Connected to simulated Hantek 6254BC")
            return True
        
        try:
            # Search for devices
            dev_info = (ctypes.c_short * 32)()
            for i in range(32):
                dev_info[i] = -1  # Initialize as no device
            
            num_devices = self.hard_dll.dsoHTSearchDevice(dev_info)
            
            if num_devices == 0:
                print("✗ No Hantek devices found")
                return False
            
            print(f"Found {num_devices} device(s)")
            
            # Find first available device
            for i in range(32):
                if dev_info[i] == 0:  # Device present
                    self.device_index = i
                    break
            
            # Initialize hardware
            if self.hard_dll.dsoInitHard(self.device_index) == 0:
                print("✗ Failed to initialize hardware")
                return False
            
            # Check connection
            if self.hard_dll.dsoHTDeviceConnect(self.device_index) == 0:
                print("✗ Device not connected")
                return False
            
            self.is_connected = True
            print(f"✓ Connected to Hantek 6254BC (device {self.device_index})")
            self._configure_for_radiation()
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the oscilloscope"""
        if self.test_mode:
            self.is_connected = False
            print("Disconnected from simulated device")
            return
        
        # SDK doesn't provide explicit disconnect, just mark as disconnected
        self.is_connected = False
        print("Disconnected from Hantek 6254BC")
    
    def _configure_for_radiation(self):
        """Configure scope for radiation detection with BC-412"""
        if self.test_mode:
            return
        
        try:
            # Setup relay control for channels
            for i in range(MAX_CH_NUM):
                self.relay_control.bCHEnable[i] = (i in self.settings.channels_active)
                if i in self.settings.channels_active:
                    self.relay_control.nCHVoltDIV[i] = VOLTAGE_DIV_INDICES[self.settings.voltage_div]
                    self.relay_control.nCHCoupling[i] = 0  # DC coupling
                    self.relay_control.bCHBWLimit[i] = False  # No bandwidth limit
            
            # Trigger configuration
            self.relay_control.nTrigSource = self.settings.trigger_channel
            self.relay_control.bTrigFilt = False
            self.relay_control.nALT = 0
            
            # Setup control data
            self.control_data.nCHSet = sum(1 << ch for ch in self.settings.channels_active)
            self.control_data.nTimeDIV = TIMEBASE_INDICES[self.settings.timebase]
            self.control_data.nTriggerSource = self.settings.trigger_channel
            self.control_data.nHTriggerPos = 20  # 20% pre-trigger
            self.control_data.nVTriggerPos = self.settings.trigger_level
            self.control_data.nTriggerSlope = self.settings.trigger_slope
            self.control_data.nBufferLen = self.settings.samples_per_acquisition
            self.control_data.nReadDataLen = self.settings.samples_per_acquisition
            self.control_data.nALT = 0
            self.control_data.nETSOpen = 0
            
            # Determine channel mode
            num_channels = len(self.settings.channels_active)
            if num_channels <= 1:
                ch_mode = 1
            elif num_channels == 2:
                ch_mode = 2
            else:
                ch_mode = 4
            
            # Apply settings in correct order (from SDK flow chart)
            
            # 1. Set ADC channel mode
            self.hard_dll.dsoHTADCCHModGain(self.device_index, ch_mode)
            
            # 2. Set sample rate
            self.hard_dll.dsoHTSetSampleRate(
                self.device_index,
                0,  # Normal mode
                ctypes.byref(self.relay_control),
                ctypes.byref(self.control_data)
            )
            
            # 3. Set channel and trigger
            self.hard_dll.dsoHTSetCHAndTrigger(
                self.device_index,
                ctypes.byref(self.relay_control),
                self.control_data.nTimeDIV
            )
            
            # 4. Set trigger mode
            self.hard_dll.dsoHTSetTrigerMode(
                self.device_index,
                0,  # Edge trigger
                self.settings.trigger_slope,
                0   # DC coupling
            )
            
            # 5. Set RAM and trigger control
            self.hard_dll.dsoHTSetRamAndTrigerControl(
                self.device_index,
                self.control_data.nTimeDIV,
                self.control_data.nCHSet,
                self.control_data.nTriggerSource,
                0  # No peak detection
            )
            
            # 6. Set channel positions
            for ch in self.settings.channels_active:
                self.hard_dll.dsoHTSetCHPos(
                    self.device_index,
                    self.relay_control.nCHVoltDIV[ch],
                    128,  # Center position
                    ch,
                    ch_mode
                )
            
            # 7. Set trigger level
            self.hard_dll.dsoHTSetVTriggerLevel(
                self.device_index,
                self.control_data.nVTriggerPos,
                4  # Sensitivity
            )
            
            # 8. Set horizontal trigger length
            self.hard_dll.dsoHTSetHTriggerLength(
                self.device_index,
                ctypes.byref(self.control_data),
                ch_mode
            )
            
            # 9. Amplitude calibration
            volt_divs = (ctypes.c_ushort * 4)()
            ch_positions = (ctypes.c_ushort * 4)()
            for i in range(4):
                volt_divs[i] = self.relay_control.nCHVoltDIV[i] if i in self.settings.channels_active else 0
                ch_positions[i] = 128  # Center
            
            self.hard_dll.dsoHTSetAmpCalibrate(
                self.device_index,
                self.control_data.nCHSet,
                self.control_data.nTimeDIV,
                volt_divs,
                ch_positions
            )
            
            print(f"✓ Configured for radiation detection")
            print(f"  Channels: {[ch+1 for ch in self.settings.channels_active]}")
            print(f"  Timebase: {self.settings.timebase}")
            print(f"  Voltage: {self.settings.voltage_div}/div")
            print(f"  Trigger: Ch{self.settings.trigger_channel+1} @ level {self.settings.trigger_level}")
            
        except Exception as e:
            print(f"Configuration error: {e}")
    
    # ============================================================================
    # DATA ACQUISITION
    # ============================================================================
    
    def acquire_single(self, channel: int = 0) -> np.ndarray:
        """
        Acquire a single waveform from specified channel
        
        Args:
            channel: Channel index (0-3 for CH1-4)
            
        Returns:
            Numpy array of voltage values in V
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to device")
        
        if channel not in [0, 1, 2, 3]:
            raise ValueError(f"Invalid channel: {channel}")
        
        if self.test_mode:
            return self._generate_test_pulse(channel)
        
        # Real hardware acquisition
        try:
            # Start acquisition (single shot)
            start_control = 0x04  # Bit 2: stop after acquisition
            if self.hard_dll.dsoHTStartCollectData(self.device_index, start_control) == 0:
                print("Failed to start acquisition")
                return np.zeros(self.settings.samples_per_acquisition)
            
            # Wait for acquisition complete
            timeout = time.time() + 0.5  # 500ms timeout
            while time.time() < timeout:
                state = self.hard_dll.dsoHTGetState(self.device_index)
                # Bit 1: acquisition finished, Bit 0: triggered
                if state & 0x02:  # Acquisition complete
                    break
                time.sleep(0.001)
            else:
                print("Acquisition timeout")
                return np.zeros(self.settings.samples_per_acquisition)
            
            # Prepare data buffers
            ch_data = [
                (ctypes.c_ushort * self.control_data.nReadDataLen)()
                for _ in range(4)
            ]
            
            # Read data
            if self.hard_dll.dsoHTGetData(
                self.device_index,
                ch_data[0], ch_data[1], ch_data[2], ch_data[3],
                ctypes.byref(self.control_data)
            ) == 0:
                print("Failed to read data")
                return np.zeros(self.settings.samples_per_acquisition)
            
            # Extract and convert channel data
            raw_data = np.array(ch_data[channel][:self.control_data.nReadDataLen], dtype=np.float64)
            
            # Convert to voltage using SDK formula:
            # V = (data - position) * voltage_div / 32
            position = 128  # Center position
            volt_div = VOLTAGE_DIV_VALUES[self.relay_control.nCHVoltDIV[channel]]
            
            voltage_data = (raw_data - position) * volt_div / 32.0
            
            return voltage_data
            
        except Exception as e:
            print(f"Acquisition error: {e}")
            return np.zeros(self.settings.samples_per_acquisition)
    
    def acquire_multi_channel(self, channels: List[int] = None) -> Dict[int, np.ndarray]:
        """
        Acquire from multiple channels simultaneously
        
        Args:
            channels: List of channel indices (default: active channels)
            
        Returns:
            Dictionary of channel -> waveform arrays
        """
        if channels is None:
            channels = self.settings.channels_active
        
        if self.test_mode:
            # In test mode, generate separate pulses
            return {ch: self._generate_test_pulse(ch) for ch in channels}
        
        # Real hardware: single acquisition gets all channels
        try:
            # Start acquisition
            start_control = 0x04  # Single shot
            if self.hard_dll.dsoHTStartCollectData(self.device_index, start_control) == 0:
                return {ch: np.zeros(self.settings.samples_per_acquisition) for ch in channels}
            
            # Wait for completion
            timeout = time.time() + 0.5
            while time.time() < timeout:
                state = self.hard_dll.dsoHTGetState(self.device_index)
                if state & 0x02:
                    break
                time.sleep(0.001)
            else:
                return {ch: np.zeros(self.settings.samples_per_acquisition) for ch in channels}
            
            # Prepare buffers
            ch_data = [
                (ctypes.c_ushort * self.control_data.nReadDataLen)()
                for _ in range(4)
            ]
            
            # Read all channels at once
            if self.hard_dll.dsoHTGetData(
                self.device_index,
                ch_data[0], ch_data[1], ch_data[2], ch_data[3],
                ctypes.byref(self.control_data)
            ) == 0:
                return {ch: np.zeros(self.settings.samples_per_acquisition) for ch in channels}
            
            # Convert each requested channel
            results = {}
            position = 128
            
            for ch in channels:
                raw_data = np.array(ch_data[ch][:self.control_data.nReadDataLen], dtype=np.float64)
                volt_div = VOLTAGE_DIV_VALUES[self.relay_control.nCHVoltDIV[ch]]
                voltage_data = (raw_data - position) * volt_div / 32.0
                results[ch] = voltage_data
            
            return results
            
        except Exception as e:
            print(f"Multi-channel acquisition error: {e}")
            return {ch: np.zeros(self.settings.samples_per_acquisition) for ch in channels}
    
    def _generate_test_pulse(self, channel: int) -> np.ndarray:
        """Generate simulated radiation pulse for testing"""
        samples = self.settings.samples_per_acquisition
        
        # Time array based on timebase
        timebase_values = {
            '20us': 20e-6,
            '50us': 50e-6,
            '100us': 100e-6
        }
        timebase_s = timebase_values.get(self.settings.timebase, 20e-6)
        
        # Calculate actual sample rate from timebase
        # 250 points per division, 10 divisions on screen
        sample_rate = 250 / timebase_s
        time_array = np.arange(samples) / sample_rate
        
        # Baseline with noise
        baseline = 0.1 + np.random.normal(0, 0.005, samples)  # 100mV baseline, 5mV noise
        
        # Randomly decide if this acquisition has a pulse (30% chance)
        if np.random.random() < 0.3:
            # Generate radiation pulse (negative-going for PMT)
            pulse_start = samples // 4
            
            # Random pulse height (50mV to 2V)
            pulse_height = np.random.uniform(0.05, 2.0)
            
            # BC-412 characteristic: 80us shaped pulse
            tau = 80e-6 / 3  # Decay constant for ~80us total width
            
            pulse = np.zeros(samples)
            for i in range(pulse_start, min(pulse_start + int(300e-6 * sample_rate), samples)):
                t = (i - pulse_start) / sample_rate
                pulse[i] = pulse_height * np.exp(-t / tau)
            
            waveform = baseline - pulse  # Negative pulse
            
            # Occasionally add pile-up (10% chance)
            if np.random.random() < 0.1:
                second_start = pulse_start + int(40e-6 * sample_rate)
                if second_start < samples:
                    second_height = np.random.uniform(0.03, 0.5)
                    for i in range(second_start, min(second_start + int(200e-6 * sample_rate), samples)):
                        t = (i - second_start) / sample_rate
                        waveform[i] -= second_height * np.exp(-t / tau)
        else:
            waveform = baseline
        
        return waveform
    
    # ============================================================================
    # PULSE PROCESSING
    # ============================================================================
    
    def process_pulse(self, waveform: np.ndarray, channel: int = 0) -> Optional[PulseData]:
        """
        Process waveform to extract pulse parameters
        
        Args:
            waveform: Raw waveform data in V
            channel: Channel index
            
        Returns:
            PulseData object or None if no valid pulse
        """
        if len(waveform) < 100:
            return None
        
        # Calculate baseline from first 20% of samples
        baseline_samples = int(len(waveform) * 0.2)
        baseline = np.mean(waveform[:baseline_samples])
        noise_level = np.std(waveform[:baseline_samples])
        
        # Subtract baseline and invert for negative pulses
        corrected = baseline - waveform
        
        # Find peak
        peak_idx = np.argmax(corrected)
        peak_height = corrected[peak_idx]
        
        # Threshold check (must be > 3 sigma above noise and > 20mV)
        if peak_height < max(3 * noise_level, 0.02):
            return None
        
        # Calculate pulse area (integral)
        pulse_start = max(0, peak_idx - 50)
        pulse_end = min(len(corrected), peak_idx + 200)
        
        # Use proper time step for integration
        timebase_values = {'20us': 20e-6, '50us': 50e-6, '100us': 100e-6}
        timebase_s = timebase_values.get(self.settings.timebase, 20e-6)
        sample_rate = 250 / timebase_s
        dt = 1.0 / sample_rate
        
        pulse_area = np.trapz(corrected[pulse_start:pulse_end]) * dt
        
        # Calculate FWHM
        half_max = peak_height / 2
        indices = np.where(corrected > half_max)[0]
        if len(indices) > 1:
            fwhm = (indices[-1] - indices[0]) / sample_rate * 1e6  # Convert to microseconds
        else:
            fwhm = 0
        
        # Pile-up detection
        is_pileup = self._detect_pileup(corrected, peak_idx)
        
        return PulseData(
            timestamp=time.time(),
            channel=channel,
            peak_height=peak_height,
            pulse_area=pulse_area,
            baseline=baseline,
            fwhm=fwhm,
            is_pileup=is_pileup,
            raw_waveform=waveform if peak_height > 0.1 else None  # Save significant pulses
        )
    
    def _detect_pileup(self, waveform: np.ndarray, primary_peak_idx: int) -> bool:
        """Detect pulse pile-up using peak finding"""
        try:
            from scipy import signal
            
            # Find peaks with minimum height and distance
            min_height = np.max(waveform) * 0.2  # 20% of max
            min_distance = 50  # Minimum 50 samples between peaks
            
            peaks, properties = signal.find_peaks(
                waveform, 
                height=min_height, 
                distance=min_distance
            )
            
            # Multiple significant peaks indicate pile-up
            if len(peaks) > 1:
                return True
            
            # Also check for distorted tail (pile-up on decay)
            if primary_peak_idx + 100 < len(waveform):
                tail_start = primary_peak_idx + 50
                tail_end = min(primary_peak_idx + 200, len(waveform))
                tail = waveform[tail_start:tail_end]
                
                # Check if tail has unexpected rises
                if len(tail) > 0:
                    expected_decay = waveform[primary_peak_idx] * np.exp(-np.arange(len(tail)) / 50)
                    deviation = np.abs(tail - expected_decay[:len(tail)])
                    if np.max(deviation) > 0.3 * waveform[primary_peak_idx]:
                        return True
            
        except ImportError:
            # Fallback if scipy not available
            pass
        
        return False


# ================================================================================
# MULTI-CHANNEL ACQUISITION MANAGER
# ================================================================================

class MultiChannelAcquisition:
    """
    Manages continuous acquisition from multiple channels
    Handles up to 3 detectors on channels 1-3 (indices 0-2)
    """
    
    def __init__(self, scope: Hantek6254BC, channels: List[int] = None):
        """
        Initialize multi-channel acquisition
        
        Args:
            scope: Hantek6254BC instance
            channels: List of channel indices (0-3)
        """
        self.scope = scope
        self.channels = channels or [0]  # Default to CH1
        self.running = False
        
        # Data storage
        self.pulse_queue = queue.Queue(maxsize=10000)
        self.spectra = {ch: np.zeros(8192) for ch in self.channels}
        self.total_counts = {ch: 0 for ch in self.channels}
        self.rejected_counts = {ch: 0 for ch in self.channels}
        
        # Timing
        self.start_time = time.time()
        self.acquisition_cycles = 0
        
        # Acquisition thread
        self.acquisition_thread = None
        
    def start(self):
        """Start continuous acquisition"""
        if self.running:
            print("Acquisition already running")
            return
        
        self.running = True
        self.start_time = time.time()
        self.acquisition_cycles = 0
        self.acquisition_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
        self.acquisition_thread.start()
        print(f"Started acquisition on channels: {[ch+1 for ch in self.channels]}")
    
    def stop(self):
        """Stop acquisition"""
        self.running = False
        if self.acquisition_thread:
            self.acquisition_thread.join(timeout=2)
        print("Acquisition stopped")
        print(f"Total cycles: {self.acquisition_cycles}")
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            print(f"Rate: {self.acquisition_cycles/elapsed:.1f} acquisitions/sec")
    
    def _acquisition_loop(self):
        """Main acquisition loop running in separate thread"""
        
        while self.running:
            try:
                # Acquire from all channels simultaneously
                waveforms = self.scope.acquire_multi_channel(self.channels)
                self.acquisition_cycles += 1
                
                # Process each channel
                for ch, waveform in waveforms.items():
                    pulse = self.scope.process_pulse(waveform, ch)
                    
                    if pulse:
                        if not pulse.is_pileup:
                            # Add to spectrum (simple linear binning)
                            # Scale peak height to channel number (2 keV/channel default)
                            energy_channel = int(pulse.peak_height * 1000)  # mV to channel
                            if 0 <= energy_channel < 8192:
                                self.spectra[ch][energy_channel] += 1
                                self.total_counts[ch] += 1
                        else:
                            self.rejected_counts[ch] += 1
                        
                        # Queue for further processing
                        try:
                            self.pulse_queue.put_nowait(pulse)
                        except queue.Full:
                            pass  # Drop oldest if queue full
                
                # Rate limiting to prevent CPU overload
                time.sleep(0.001)  # 1ms between acquisitions
                
            except Exception as e:
                print(f"Acquisition error: {e}")
                time.sleep(0.1)
    
    def get_spectrum(self, channel: int) -> np.ndarray:
        """Get current spectrum for a channel"""
        return self.spectra.get(channel, np.zeros(8192))
    
    def get_statistics(self) -> Dict:
        """Get acquisition statistics"""
        elapsed = time.time() - self.start_time
        stats = {
            'elapsed_time': elapsed,
            'acquisition_cycles': self.acquisition_cycles,
            'acquisition_rate': self.acquisition_cycles / elapsed if elapsed > 0 else 0,
            'channels': {}
        }
        
        for ch in self.channels:
            count_rate = self.total_counts[ch] / elapsed if elapsed > 0 else 0
            stats['channels'][ch] = {
                'total_counts': self.total_counts[ch],
                'rejected_counts': self.rejected_counts[ch],
                'count_rate': count_rate,
                'dead_time_percent': (self.rejected_counts[ch] / 
                                     (self.total_counts[ch] + self.rejected_counts[ch]) * 100
                                     if (self.total_counts[ch] + self.rejected_counts[ch]) > 0 else 0)
            }
        
        return stats
    
    def save_spectra(self, prefix: str = "spectrum"):
        """Save all spectra to CSV files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for ch in self.channels:
            filename = f"{prefix}_ch{ch+1}_{timestamp}.csv"
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Channel', 'Counts', 'Energy_keV'])
                
                spectrum = self.spectra[ch]
                for i, counts in enumerate(spectrum):
                    if counts > 0:  # Only save non-zero channels
                        energy = i * 2.0  # 2 keV/channel default calibration
                        writer.writerow([i, int(counts), energy])
            
            print(f"Saved spectrum for CH{ch+1} to {filename}")
            print(f"  Total counts: {self.total_counts[ch]}")
            print(f"  Rejected (pile-up): {self.rejected_counts[ch]}")


# ================================================================================
# TEST AND DEMONSTRATION
# ================================================================================

def test_basic_functions():
    """Test basic wrapper functionality"""
    print("\n" + "="*60)
    print("HANTEK 6254BC WRAPPER TEST")
    print("="*60)
    
    # Initialize in test mode
    scope = Hantek6254BC(test_mode=True)
    
    # Test connection
    if scope.connect():
        print("✓ Connection test passed")
    
    # Test single acquisition
    print("\nTesting single channel acquisition...")
    waveform = scope.acquire_single(channel=0)
    print(f"  Acquired {len(waveform)} samples")
    print(f"  Range: {np.min(waveform):.3f} to {np.max(waveform):.3f} V")
    
    # Test pulse processing
    pulse = scope.process_pulse(waveform, channel=0)
    if pulse:
        print(f"  Detected pulse: {pulse.peak_height:.3f} V, FWHM: {pulse.fwhm:.1f} μs")
    else:
        print("  No pulse detected")
    
    # Test multi-channel
    print("\nTesting multi-channel acquisition...")
    scope.settings.channels_active = [0, 1, 2]  # CH1-3
    multi_data = scope.acquire_multi_channel()
    for ch, data in multi_data.items():
        print(f"  Channel {ch+1}: {len(data)} samples")
    
    scope.disconnect()
    print("\n✓ Basic tests completed")

def test_continuous_acquisition():
    """Test continuous acquisition with multiple channels"""
    print("\n" + "="*60)
    print("CONTINUOUS ACQUISITION TEST")
    print("="*60)
    
    # Initialize scope
    scope = Hantek6254BC(test_mode=True)
    scope.connect()
    
    # Setup 3-channel acquisition (3 detectors)
    scope.settings.channels_active = [0, 1, 2]  # CH1-3
    acquisition = MultiChannelAcquisition(scope, channels=[0, 1, 2])
    
    # Run for 10 seconds
    print("\nAcquiring data for 10 seconds...")
    acquisition.start()
    
    for i in range(10):
        time.sleep(1)
        stats = acquisition.get_statistics()
        print(f"  {i+1}s - ", end="")
        for ch in [0, 1, 2]:
            ch_stats = stats['channels'][ch]
            print(f"CH{ch+1}: {ch_stats['total_counts']} counts, ", end="")
        print(f"Rate: {stats['acquisition_rate']:.1f} Hz")
    
    acquisition.stop()
    
    # Save results
    print("\nSaving spectra...")
    acquisition.save_spectra("test_spectrum")
    
    # Final statistics
    stats = acquisition.get_statistics()
    print("\nFinal Statistics:")
    for ch, ch_stats in stats['channels'].items():
        print(f"  CH{ch+1}:")
        print(f"    Total counts: {ch_stats['total_counts']}")
        print(f"    Count rate: {ch_stats['count_rate']:.1f} cps")
        print(f"    Dead time: {ch_stats['dead_time_percent']:.1f}%")
    
    scope.disconnect()
    print("\n✓ Continuous acquisition test completed")

def main():
    """Main entry point with menu"""
    print("\n" + "="*60)
    print("HANTEK 6254BC RADIATION DETECTION SYSTEM")
    print("BC-412 Scintillator Support")
    print("="*60)
    
    # Check for SDK
    sdk_paths = [
        r"C:\Program Files\Hantek6000\SDK",
        r"C:\Program Files (x86)\Hantek6000\SDK"
    ]
    
    sdk_exists = False
    for path in sdk_paths:
        if os.path.exists(os.path.join(path, "HTHardDll.dll")):
            sdk_exists = True
            print(f"\n✓ SDK found at: {path}")
            break
    
    if not sdk_exists:
        print("\n⚠ WARNING: HTHardDll.dll not found")
        print("Running in TEST MODE")
        print("\nTo use real hardware:")
        print("1. Install Hantek 6000 series software")
        print("2. Ensure HTHardDll.dll is in the SDK folder")
        test_mode = True
    else:
        test_mode = False
        print("✓ Hardware mode available")
    
    print("\nOptions:")
    print("1. Test basic functions")
    print("2. Test continuous acquisition") 
    print("3. Run radiation spectroscopy (real hardware)")
    print("4. Exit")
    
    choice = input("\nSelect option (1-4): ")
    
    if choice == '1':
        test_basic_functions()
    elif choice == '2':
        test_continuous_acquisition()
    elif choice == '3':
        if test_mode:
            print("\nHardware mode not available - running simulation")
            test_continuous_acquisition()
        else:
            print("\nStarting radiation spectroscopy system...")
            # Initialize with real hardware
            scope = Hantek6254BC(test_mode=False)
            if scope.connect():
                acquisition = MultiChannelAcquisition(scope, channels=[0])  # Start with CH1
                
                print("\nCommands:")
                print("  'start' - Start acquisition")
                print("  'stop' - Stop acquisition")
                print("  'stats' - Show statistics")
                print("  'save' - Save spectrum")
                print("  'quit' - Exit")
                
                while True:
                    cmd = input("\n> ").strip().lower()
                    
                    if cmd == 'start':
                        acquisition.start()
                    elif cmd == 'stop':
                        acquisition.stop()
                    elif cmd == 'stats':
                        stats = acquisition.get_statistics()
                        print(f"Elapsed: {stats['elapsed_time']:.1f}s")
                        for ch, ch_stats in stats['channels'].items():
                            print(f"CH{ch+1}: {ch_stats['total_counts']} counts @ {ch_stats['count_rate']:.1f} cps")
                    elif cmd == 'save':
                        acquisition.save_spectra("radiation_spectrum")
                    elif cmd == 'quit':
                        acquisition.stop()
                        scope.disconnect()
                        break
                    else:
                        print("Unknown command")
            else:
                print("Failed to connect to hardware")
    elif choice == '4':
        print("Goodbye!")
    else:
        print("Invalid option")

if __name__ == "__main__":
    main()

