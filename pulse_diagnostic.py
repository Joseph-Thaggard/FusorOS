#!/usr/bin/env python3
"""
Pulse Detection Diagnostic Tool
Helps diagnose why pulses aren't being detected
"""

import sys
import numpy as np
import time
import matplotlib.pyplot as plt

# Add DSO5102P library path
sys.path.insert(0, '/Users/joe/DSO5102P-Python')
from rcr.dso5102p.DSO5102P import DSO5102P

def diagnose_signal(vid=0x049f, pid=0x505a, channel=2):
    """Run comprehensive signal diagnostics
    
    Args:
        vid: USB Vendor ID
        pid: USB Product ID
        channel: Oscilloscope channel to use (1 or 2)
    """
    
    print("="*60)
    print("PULSE DETECTION DIAGNOSTIC TOOL")
    print(f"Using Channel {channel}")
    print("="*60)
    
    # Initialize scope
    print("\n1. Initializing DSO5102P...")
    try:
        dso = DSO5102P(vid, pid, debug=False)
        print("   ✓ Connected successfully")
    except Exception as e:
        print(f"   ✗ Failed to connect: {e}")
        return
    
    print(f"\n2. Checking scope settings for CH{channel}...")
    print("   Please verify on your scope:")
    print(f"   - CH{channel} input coupling: DC")
    print(f"   - CH{channel} probe: 1X (not 10X)")
    print(f"   - Trigger source: CH{channel}")
    print("   - Trigger mode: Normal (not Auto)")
    print("   - Time base: 5-20 μs/div")
    print("   - Vertical scale: 100-500 mV/div")
    
    input("\nPress Enter when scope is configured...")
    
    print(f"\n3. Acquiring raw waveforms from CH{channel}...")
    print("   (This will capture whatever is on screen)")
    
    waveforms = []
    stats = []
    
    for i in range(5):
        print(f"\n   Capture {i+1}/5:")
        
        try:
            # Start and capture from specified channel
            dso.StartAcquisition()
            time.sleep(0.1)  # Short wait
            data = dso.ReadSampleData(channel)  # Use specified channel
            dso.StopAcquisition()
            
            if data and len(data) > 0:
                waveform = np.array(data)
                waveforms.append(waveform)
                
                # Calculate statistics
                baseline = np.mean(waveform[:50]) if len(waveform) > 50 else np.mean(waveform)
                corrected = waveform - baseline
                
                stats_dict = {
                    'samples': len(waveform),
                    'raw_min': np.min(waveform),
                    'raw_max': np.max(waveform),
                    'raw_mean': np.mean(waveform),
                    'raw_std': np.std(waveform),
                    'baseline': baseline,
                    'min_deviation': np.min(corrected),
                    'max_deviation': np.max(corrected),
                    'peak_to_peak': np.max(waveform) - np.min(waveform)
                }
                stats.append(stats_dict)
                
                print(f"     Samples: {stats_dict['samples']}")
                print(f"     Raw range: {stats_dict['raw_min']:.1f} to {stats_dict['raw_max']:.1f}")
                print(f"     Baseline: {stats_dict['baseline']:.1f}")
                print(f"     Peak-to-peak: {stats_dict['peak_to_peak']:.1f}")
                print(f"     Max deviation: {abs(stats_dict['min_deviation']):.1f} (neg), {stats_dict['max_deviation']:.1f} (pos)")
                
                # Check for pulse-like features
                threshold = 20  # mV
                if abs(stats_dict['min_deviation']) > threshold:
                    print(f"     → Possible NEGATIVE pulse detected ({abs(stats_dict['min_deviation']):.1f} mV)")
                if stats_dict['max_deviation'] > threshold:
                    print(f"     → Possible POSITIVE pulse detected ({stats_dict['max_deviation']:.1f} mV)")
                if stats_dict['peak_to_peak'] < 10:
                    print(f"     ⚠ Very small signal - check connections")
                    
            else:
                print(f"     ✗ No data received")
                
        except Exception as e:
            print(f"     ✗ Capture failed: {e}")
        
        time.sleep(0.5)
    
    print("\n4. Analysis Summary:")
    
    if len(stats) > 0:
        # Aggregate statistics
        all_peak_to_peak = [s['peak_to_peak'] for s in stats]
        all_max_dev = [max(abs(s['min_deviation']), s['max_deviation']) for s in stats]
        
        print(f"\n   Signal characteristics:")
        print(f"   - Average peak-to-peak: {np.mean(all_peak_to_peak):.1f} units")
        print(f"   - Max deviation seen: {np.max(all_max_dev):.1f} units")
        print(f"   - Signal variation: {np.std(all_peak_to_peak):.1f}")
        
        # Determine signal type
        neg_pulses = sum(1 for s in stats if abs(s['min_deviation']) > s['max_deviation'])
        pos_pulses = len(stats) - neg_pulses
        
        print(f"\n   Pulse polarity:")
        print(f"   - Negative-going pulses: {neg_pulses}/5")
        print(f"   - Positive-going pulses: {pos_pulses}/5")
        
        if neg_pulses > pos_pulses:
            polarity = 'negative'
        elif pos_pulses > neg_pulses:
            polarity = 'positive'
        else:
            polarity = 'both'
        
        # Recommendations
        print(f"\n5. RECOMMENDATIONS:")
        print(f"   Based on the analysis, try these settings:")
        
        avg_max_dev = np.mean(all_max_dev)
        if avg_max_dev < 10:
            print(f"   ⚠ VERY WEAK SIGNAL DETECTED")
            print(f"   - Check PMT high voltage")
            print(f"   - Move source closer to detector")
            print(f"   - Check cable connections")
            trigger_level = 10
            noise_threshold = 5
        elif avg_max_dev < 50:
            print(f"   → Weak signal detected")
            trigger_level = max(20, avg_max_dev * 0.5)
            noise_threshold = 10
        elif avg_max_dev < 200:
            print(f"   → Moderate signal detected")
            trigger_level = avg_max_dev * 0.6
            noise_threshold = 15
        else:
            print(f"   → Strong signal detected")
            trigger_level = avg_max_dev * 0.7
            noise_threshold = 20
        
        print(f"\n   Suggested settings for radiation_spectroscopy.py:")
        print(f"   - Trigger level: ±{trigger_level:.0f} mV")
        print(f"   - Pulse polarity: '{polarity}'")
        print(f"   - Noise threshold: {noise_threshold:.0f} mV")
        
        # Plot waveforms if available
        if len(waveforms) > 0 and input("\n   Plot waveforms? (y/n): ").lower() == 'y':
            plt.figure(figsize=(12, 8))
            
            for i, wf in enumerate(waveforms[:3]):  # Plot first 3
                plt.subplot(3, 1, i+1)
                baseline = np.mean(wf[:50]) if len(wf) > 50 else np.mean(wf)
                plt.plot(wf - baseline, linewidth=0.5)
                plt.axhline(y=0, color='k', linestyle='--', alpha=0.3)
                plt.axhline(y=trigger_level, color='r', linestyle='--', alpha=0.5, label=f'Trigger +{trigger_level:.0f}')
                plt.axhline(y=-trigger_level, color='r', linestyle='--', alpha=0.5, label=f'Trigger -{trigger_level:.0f}')
                plt.ylabel('Amplitude (mV)')
                plt.title(f'Waveform {i+1}')
                plt.grid(True, alpha=0.3)
                if i == 0:
                    plt.legend()
            
            plt.xlabel('Sample')
            plt.tight_layout()
            plt.show()
            
    else:
        print("   ✗ No data collected. Check USB connection and try again.")
    
    print("\n6. Next steps:")
    print("   1. Apply the recommended settings to your spectroscopy system")
    print("   2. If still no pulses, try Manual trigger mode on scope")
    print("   3. Use an oscilloscope probe to verify signal at PMT output")
    print("   4. Check that radiation source is present and active")

def test_continuous_capture(vid=0x049f, pid=0x505a, channel=2, duration=10):
    """Test continuous capture rate
    
    Args:
        vid: USB Vendor ID
        pid: USB Product ID
        channel: Oscilloscope channel to use (1 or 2)
        duration: Test duration in seconds
    """
    
    print(f"\n=== Testing Continuous Capture on CH{channel} for {duration}s ===")
    
    try:
        dso = DSO5102P(vid, pid, debug=False)
        
        captures = 0
        pulses_found = 0
        start_time = time.time()
        
        print("Capturing...")
        while time.time() - start_time < duration:
            try:
                dso.StartAcquisition()
                time.sleep(0.01)
                data = dso.ReadSampleData(channel)  # Use specified channel
                dso.StopAcquisition()
                
                if data and len(data) > 0:
                    captures += 1
                    
                    # Quick pulse check
                    waveform = np.array(data)
                    baseline = np.mean(waveform[:20]) if len(waveform) > 20 else np.mean(waveform)
                    max_dev = np.max(np.abs(waveform - baseline))
                    
                    if max_dev > 20:  # 20mV threshold
                        pulses_found += 1
                        print(f"  Pulse {pulses_found}: {max_dev:.1f} mV", end='\r')
                        
            except Exception as e:
                print(f"  Error: {e}")
                try:
                    dso.StopAcquisition()
                except:
                    pass
        
        elapsed = time.time() - start_time
        
        print(f"\n\nResults:")
        print(f"  Total captures: {captures}")
        print(f"  Pulses found: {pulses_found}")
        print(f"  Capture rate: {captures/elapsed:.1f} Hz")
        if captures > 0:
            print(f"  Pulse detection rate: {pulses_found/captures*100:.1f}%")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("\nPulse Detection Diagnostic Tool")
    print("This will help identify why pulses aren't being detected\n")
    
    # Ask for channel selection
    channel = input("Which channel to use (1 or 2) [2]: ").strip()
    channel = int(channel) if channel else 2
    
    print(f"\nUsing Channel {channel}")
    
    print("\n1. Run full diagnostics")
    print("2. Test continuous capture")
    print("3. Exit")
    
    choice = input("\nSelect option: ").strip()
    
    if choice == '1':
        diagnose_signal(channel=channel)
    elif choice == '2':
        duration = int(input("Duration in seconds [10]: ").strip() or "10")
        test_continuous_capture(channel=channel, duration=duration)
    else:
        print("Exiting...")
        
    