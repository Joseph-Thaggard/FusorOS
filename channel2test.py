#!/usr/bin/env python3
"""
Quick test script for Channel 2 radiation detection
"""

import sys
import time
import numpy as np

# Add path if needed
sys.path.insert(0, '/Users/joe/DSO5102P-Python')

from radiation_spectroscopy import RadiationSpectroscopy

def quick_test_ch2():
    """Quick test specifically for Channel 2"""
    
    print("="*60)
    print("CHANNEL 2 RADIATION DETECTION TEST")
    print("="*60)
    
    # Initialize on Channel 2
    print("\nInitializing system on Channel 2...")
    spec = RadiationSpectroscopy(debug=True, channel=2)  # Channel 2, debug on
    
    # Configure for your expected signal
    spec.set_trigger_parameters(
        level=80,           # ±80mV trigger as requested
        polarity='both',    # Detect both positive and negative
        noise_threshold=15  # 15mV noise threshold
    )
    
    print("\n" + "="*40)
    print("CURRENT CONFIGURATION:")
    print("="*40)
    print(f"Channel: CH2")
    print(f"Trigger: ±{spec.trigger_level} mV")
    print(f"Polarity: {spec.pulse_polarity}")
    print(f"Window: {spec.acquisition_window*1e6:.0f} μs")
    print(f"Sample Rate: {spec.sample_rate/1e6:.1f} MS/s")
    print("="*40)
    
    # Test 1: Single pulse acquisition
    print("\n1. Testing single pulse acquisition...")
    pulse = spec.acquire_single_pulse(timeout=1.0)
    
    if pulse:
        print(f"   ✓ Pulse detected!")
        print(f"   Height: {pulse.peak_height:.1f} mV")
        print(f"   Area: {pulse.pulse_area:.1f}")
        print(f"   FWHM: {pulse.fwhm*1e6:.1f} μs")
    else:
        print("   ✗ No pulse detected")
    
    # Test 2: Multiple acquisitions
    print("\n2. Testing 10 acquisitions...")
    successful = 0
    heights = []
    
    for i in range(10):
        pulse = spec.acquire_single_pulse(timeout=0.5)
        if pulse:
            successful += 1
            heights.append(pulse.peak_height)
            print(f"   {i+1:2d}. ✓ {pulse.peak_height:.1f} mV", end="")
            if pulse.is_pileup:
                print(" (pile-up)")
            else:
                print()
        else:
            print(f"   {i+1:2d}. ✗ No pulse")
        time.sleep(0.1)
    
    print(f"\n   Success rate: {successful}/10 ({successful*10}%)")
    if heights:
        print(f"   Average height: {np.mean(heights):.1f} mV")
        print(f"   Range: {np.min(heights):.1f} - {np.max(heights):.1f} mV")
    
    # Test 3: Continuous acquisition test
    print("\n3. Testing continuous acquisition for 5 seconds...")
    print("   Press Ctrl+C to stop early")
    
    spec.spectrum.fill(0)  # Clear spectrum
    spec.total_counts = 0
    spec.rejected_counts = 0
    
    start_time = time.time()
    last_count = 0
    
    try:
        spec.acquisition_active = True
        spec.start_time = start_time
        
        while time.time() - start_time < 5:
            pulse = spec.acquire_single_pulse(timeout=0.01)
            
            # Display progress
            if spec.total_counts > last_count:
                rate = spec.total_counts / (time.time() - start_time)
                print(f"   Counts: {spec.total_counts:4d} | Rate: {rate:6.1f} cps | Rejected: {spec.rejected_counts:3d}", end='\r')
                last_count = spec.total_counts
            
    except KeyboardInterrupt:
        print("\n   Stopped by user")
    finally:
        spec.acquisition_active = False
        elapsed = time.time() - start_time
    
    print(f"\n\n   Results:")
    print(f"   - Total counts: {spec.total_counts}")
    print(f"   - Time: {elapsed:.1f} seconds")
    print(f"   - Average rate: {spec.total_counts/elapsed:.1f} cps")
    print(f"   - Pile-up rejected: {spec.rejected_counts}")
    
    # Show spectrum summary if we got data
    if spec.total_counts > 0:
        print("\n4. Spectrum summary:")
        
        # Find highest channel with counts
        nonzero = np.where(spec.spectrum > 0)[0]
        if len(nonzero) > 0:
            print(f"   - Channels with data: {len(nonzero)}")
            print(f"   - Channel range: {nonzero[0]} - {nonzero[-1]}")
            
            # Find peak
            peak_channel = np.argmax(spec.spectrum)
            peak_counts = spec.spectrum[peak_channel]
            print(f"   - Peak channel: {peak_channel} ({peak_counts} counts)")
            
            # Simple spectrum display
            print("\n   Mini spectrum (top 20 channels):")
            sorted_channels = np.argsort(spec.spectrum)[::-1][:20]
            for ch in sorted_channels[:5]:
                if spec.spectrum[ch] > 0:
                    bar = "█" * int(spec.spectrum[ch] * 20 / peak_counts)
                    print(f"   Ch {ch:4d}: {bar} {spec.spectrum[ch]} counts")

def manual_scope_check():
    """Instructions for manual scope verification"""
    print("\n" + "="*60)
    print("MANUAL SCOPE VERIFICATION")
    print("="*60)
    print("\n1. Set your oscilloscope to:")
    print("   - Channel 2 active")
    print("   - Trigger: Auto mode")
    print("   - Vertical: 100-500 mV/div")
    print("   - Horizontal: 10-20 μs/div")
    print("   - Coupling: DC")
    
    print("\n2. Place radioactive source near detector")
    
    print("\n3. You should see:")
    print("   - Pulses appearing on CH2")
    print("   - Note their amplitude (mV)")
    print("   - Note their polarity (up or down)")
    print("   - Note their width (μs)")
    
    print("\n4. Then set trigger:")
    print("   - Mode: Normal")
    print("   - Source: CH2")
    print("   - Level: About 50% of pulse height")
    print("   - Slope: Falling (for negative) or Rising (for positive)")
    
    print("\n5. Pulses should now trigger consistently")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Channel 2 radiation detection')
    parser.add_argument('--manual', action='store_true', help='Show manual scope check instructions')
    parser.add_argument('--trigger', type=float, default=80, help='Trigger level in mV (default: 80)')
    parser.add_argument('--polarity', choices=['positive', 'negative', 'both'], 
                       default='both', help='Pulse polarity (default: both)')
    
    args = parser.parse_args()
    
    if args.manual:
        manual_scope_check()
    else:
        try:
            # Run the test
            quick_test_ch2()
            
            print("\n" + "="*60)
            print("TEST COMPLETE")
            print("="*60)
            print("\nIf no pulses detected:")
            print("1. Run with --manual flag for scope setup guide")
            print("2. Check signal is connected to CH2 (not CH1)")
            print("3. Verify PMT high voltage is on")
            print("4. Try adjusting trigger: --trigger 50")
            print("5. Try specific polarity: --polarity negative")
            
        except KeyboardInterrupt:
            print("\n\nTest interrupted")
        except Exception as e:
            print(f"\nError: {e}")
            print("\nTry:")
            print("  sudo python3 test_ch2.py")