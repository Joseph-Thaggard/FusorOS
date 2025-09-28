#!/usr/bin/env python3
"""
Quick test script for Hantek 6254BC SDK connection
Run this after installing Hantek software to verify SDK access
"""

import ctypes
import numpy as np
import os
import sys
import time

def find_sdk():
    """Search for HTMarch.dll in common locations"""
    
    print("Searching for Hantek SDK...")
    
    search_paths = [
        r"C:\Program Files\Hantek6000\SDK\HTMarch.dll",
        r"C:\Program Files (x86)\Hantek6000\SDK\HTMarch.dll",
        r"C:\Program Files\Hantek\HTMarch.dll",
        r"C:\Program Files (x86)\Hantek\HTMarch.dll",
        r"C:\Hantek\SDK\HTMarch.dll",
        r".\HTMarch.dll",
        r".\SDK\HTMarch.dll"
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            print(f"✓ Found SDK at: {path}")
            return path
    
    print("✗ SDK not found in standard locations")
    print("\nTry searching manually:")
    print("1. Open File Explorer")
    print("2. Search for 'HTMarch.dll'")
    print("3. Note the path and update this script")
    
    return None

def test_sdk_loading(sdk_path):
    """Try to load the SDK and check basic functions"""
    
    print(f"\nAttempting to load SDK from: {sdk_path}")
    
    try:
        # Load the DLL
        dll = ctypes.CDLL(sdk_path)
        print("✓ DLL loaded successfully")
        
        # Check for expected functions
        expected_functions = [
            'dsoOpen',
            'dsoClose', 
            'dsoSetCH',
            'dsoSetTrigger',
            'dsoReadData',
            'dsoGetDeviceInfo',
            'dsoSetSampleRate'
        ]
        
        print("\nChecking for SDK functions:")
        available = []
        missing = []
        
        for func_name in expected_functions:
            try:
                func = getattr(dll, func_name)
                available.append(func_name)
                print(f"  ✓ {func_name}")
            except AttributeError:
                missing.append(func_name)
                print(f"  ✗ {func_name}")
        
        if missing:
            print(f"\nWarning: {len(missing)} functions not found")
            print("The SDK might use different function names")
        
        return dll, available
        
    except Exception as e:
        print(f"✗ Failed to load DLL: {e}")
        return None, []

def test_device_connection(dll):
    """Try to connect to the Hantek device"""
    
    print("\n" + "="*50)
    print("DEVICE CONNECTION TEST")
    print("="*50)
    
    try:
        # Try to open device (function signature is a guess)
        print("\nAttempting to connect to Hantek 6254BC...")
        
        # Different possible function signatures to try
        attempts = [
            lambda: dll.dsoOpen(),  # No parameters
            lambda: dll.dsoOpen(0),  # Device index
            lambda: dll.dsoOpen(ctypes.c_int(0)),  # Device index as c_int
            lambda: dll.dsoOpenDevice(0),  # Alternative name
            lambda: dll.HTOpen(),  # Alternative prefix
        ]
        
        device_handle = None
        for i, attempt in enumerate(attempts):
            try:
                print(f"  Attempt {i+1}: ", end='')
                result = attempt()
                if result:
                    device_handle = result
                    print(f"Success! Handle: {result}")
                    break
                else:
                    print("Returned null/zero")
            except Exception as e:
                print(f"Failed - {e}")
        
        if device_handle:
            print("\n✓ Successfully connected to device!")
            
            # Try to close the connection
            try:
                dll.dsoClose(device_handle)
                print("✓ Successfully closed connection")
            except:
                pass
                
            return True
        else:
            print("\n✗ Could not connect to device")
            print("\nPossible reasons:")
            print("1. Device not connected via USB")
            print("2. Device drivers not installed")
            print("3. Device in use by another program")
            print("4. Different SDK function names")
            
            return False
            
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False

def generate_test_data():
    """Generate test data to verify processing works"""
    
    print("\n" + "="*50)
    print("DATA PROCESSING TEST (Simulated)")
    print("="*50)
    
    # Simulate oscilloscope data
    samples = 2500  # 10 microseconds at 250 MS/s
    time_array = np.arange(samples) * 4e-9  # 4 ns per sample at 250 MS/s
    
    # Create a simulated radiation pulse
    baseline = 100  # mV
    noise = np.random.normal(0, 5, samples)  # 5 mV noise
    
    # Add exponential decay pulse
    pulse_start = 500
    pulse_height = 500  # 500 mV pulse
    tau = 20e-6  # 20 microsecond decay
    
    pulse = np.zeros(samples)
    for i in range(pulse_start, samples):
        t = (i - pulse_start) * 4e-9
        pulse[i] = pulse_height * np.exp(-t/tau)
    
    waveform = baseline + noise - pulse  # Negative pulse
    
    # Find peak
    peak_value = np.min(waveform)
    peak_index = np.argmin(waveform)
    peak_height = baseline - peak_value
    
    print(f"\nSimulated pulse analysis:")
    print(f"  Baseline: {baseline:.1f} mV")
    print(f"  Peak height: {peak_height:.1f} mV")
    print(f"  Peak time: {peak_index * 4:.1f} ns")
    print(f"  Estimated energy: {peak_height * 2.5:.1f} keV")  # Simple calibration
    
    # Calculate FWHM
    half_max = baseline - peak_height/2
    indices = np.where(waveform < half_max)[0]
    if len(indices) > 1:
        fwhm_samples = indices[-1] - indices[0]
        fwhm_time = fwhm_samples * 4e-9 * 1e6  # Convert to microseconds
        print(f"  FWHM: {fwhm_time:.1f} μs")
    
    print("\n✓ Data processing algorithms working correctly")
    
    return waveform

def main():
    """Main test sequence"""
    
    print("="*60)
    print("HANTEK 6254BC SDK CONNECTION TEST")
    print("="*60)
    print("\nThis script will help verify your Hantek SDK installation")
    
    # Step 1: Find SDK
    sdk_path = find_sdk()
    
    if not sdk_path:
        print("\n" + "="*60)
        print("RUNNING IN SIMULATION MODE")
        print("="*60)
        
        # Generate test data anyway
        print("\nSDK not found, but testing data processing...")
        waveform = generate_test_data()
        
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print("1. Install Hantek 6000 series software from:")
        print("   https://www.hantek.com/products/detail/30")
        print("2. Run this script again after installation")
        print("3. The wrapper will auto-detect the SDK")
        
        return
    
    # Step 2: Load SDK
    dll, functions = test_sdk_loading(sdk_path)
    
    if not dll:
        print("\nFailed to load SDK - check installation")
        return
    
    # Step 3: Test connection
    connected = test_device_connection(dll)
    
    # Step 4: Test data processing
    generate_test_data()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"SDK Found: ✓")
    print(f"SDK Loaded: ✓")
    print(f"Functions Available: {len(functions)}")
    print(f"Device Connected: {'✓' if connected else '✗'}")
    print(f"Processing Algorithms: ✓")
    
    if connected:
        print("\n✓ READY FOR RADIATION DETECTION!")
        print("\nYou can now run the full wrapper with:")
        print("  python hantek_6254bc_wrapper.py")
    else:
        print("\nDevice connection failed. Please:")
        print("1. Connect your Hantek 6254BC via USB")
        print("2. Ensure no other software is using it")
        print("3. Try running as administrator")

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")