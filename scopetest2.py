#!/usr/bin/env python3
"""
Workaround script to get Channel 2 working
Tests different approaches to reading CH2 data
"""

import sys
import time
import numpy as np

sys.path.insert(0, '/Users/joe/DSO5102P-Python')
from rcr.dso5102p.DSO5102P import DSO5102P

def test_channel_access():
    """Test different ways to access Channel 2"""
    
    print("="*60)
    print("CHANNEL 2 WORKAROUND TEST")
    print("="*60)
    
    print("\n1. First, verify scope settings:")
    print("   - Press CH2 button on scope (should be lit)")
    print("   - Set scope to AUTO trigger mode")
    print("   - Verify you see a signal on CH2 display")
    
    input("\nPress Enter when ready...")
    
    # Connect
    print("\n2. Connecting to scope...")
    dso = DSO5102P(0x049f, 0x505a, debug=False)
    print("   ✓ Connected")
    
    # Test different channel parameters
    print("\n3. Testing different channel parameters...")
    
    test_params = [
        (2, "Channel 2 as integer"),
        (1, "Channel 1 as baseline test"),
        (0x02, "Channel 2 as hex"),
        ('2', "Channel 2 as string"),
        (b'\x02', "Channel 2 as byte"),
    ]
    
    for param, description in test_params:
        print(f"\n   Testing: {description}")
        print(f"   Parameter: {repr(param)}")
        
        try:
            dso.StartAcquisition()
            time.sleep(0.1)
            
            # Try to read with this parameter
            try:
                data = dso.ReadSampleData(param)
            except TypeError:
                # If parameter type is wrong, try converting
                if isinstance(param, bytes):
                    data = None
                else:
                    data = dso.ReadSampleData(int(param) if param != '2' else 2)
            
            dso.StopAcquisition()
            
            if data and len(data) > 0:
                print(f"   ✓ SUCCESS! Got {len(data)} samples")
                arr = np.array(data)
                print(f"   Range: {np.min(arr):.1f} to {np.max(arr):.1f}")
                return param  # Return working parameter
            else:
                print(f"   ✗ No data returned")
                
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        time.sleep(0.5)
    
    return None

def test_dual_channel():
    """Test reading both channels simultaneously"""
    
    print("\n" + "="*60)
    print("DUAL CHANNEL TEST")
    print("="*60)
    
    dso = DSO5102P(0x049f, 0x505a, debug=False)
    
    print("\nTrying to read both channels...")
    
    # Method 1: Sequential reads
    print("\nMethod 1: Sequential reads")
    dso.StartAcquisition()
    time.sleep(0.2)
    
    data1 = dso.ReadSampleData(1)
    data2 = dso.ReadSampleData(2)
    
    dso.StopAcquisition()
    
    print(f"  CH1: {len(data1) if data1 else 'No'} data")
    print(f"  CH2: {len(data2) if data2 else 'No'} data")
    
    # Method 2: Check if there's a ReadAllChannels method
    print("\nMethod 2: Looking for multi-channel methods...")
    
    multi_methods = [m for m in dir(dso) if 'all' in m.lower() or 'both' in m.lower() or 'multi' in m.lower()]
    if multi_methods:
        print(f"  Found: {multi_methods}")
    else:
        print("  No multi-channel methods found")
    
    # Method 3: Try reading with different memory settings
    print("\nMethod 3: Testing with ForceTrigger...")
    
    try:
        dso.StartAcquisition()
        dso.ForceTrigger()  # Force a trigger
        time.sleep(0.2)
        
        data2 = dso.ReadSampleData(2)
        dso.StopAcquisition()
        
        if data2:
            print(f"  ✓ Got {len(data2)} samples from CH2 with forced trigger")
        else:
            print("  ✗ Still no data from CH2")
    except AttributeError:
        print("  ForceTrigger method not available")
    except Exception as e:
        print(f"  Error: {e}")

def check_scope_state():
    """Check and display scope state"""
    
    print("\n" + "="*60)
    print("SCOPE STATE CHECK")
    print("="*60)
    
    dso = DSO5102P(0x049f, 0x505a, debug=False)
    
    # Try to read scope state
    print("\nChecking available scope methods...")
    
    state_methods = [
        'GetTriggerStatus',
        'GetAcquisitionState', 
        'GetChannelEnable',
        'ReadSystemStatus',
        'GetStatus',
        'IsChannelEnabled',
        'GetChannelState'
    ]
    
    for method in state_methods:
        if hasattr(dso, method):
            print(f"\n{method}:")
            try:
                result = getattr(dso, method)()
                print(f"  Result: {result}")
            except TypeError:
                # Method might need parameters
                try:
                    result1 = getattr(dso, method)(1)
                    result2 = getattr(dso, method)(2)
                    print(f"  CH1: {result1}")
                    print(f"  CH2: {result2}")
                except:
                    print("  (requires different parameters)")
            except Exception as e:
                print(f"  Error: {e}")

def alternative_solution():
    """Provide alternative solution if CH2 doesn't work"""
    
    print("\n" + "="*60)
    print("ALTERNATIVE SOLUTION")
    print("="*60)
    
    print("\nIf Channel 2 is not working through software:")
    
    print("\n1. USE CHANNEL 1 INSTEAD:")
    print("   - Move your signal cable from CH2 to CH1")
    print("   - Update trigger source to CH1 on scope")
    print("   - Use channel=1 in the software")
    
    print("\n2. CHECK DSO5102P LIBRARY:")
    print("   - The library might only support CH1")
    print("   - Look for library documentation")
    print("   - Check: /Users/joe/DSO5102P-Python/rcr/dso5102p/DSO5102P.py")
    
    print("\n3. MODIFY THE LIBRARY:")
    print("   Open DSO5102P.py and look for ReadSampleData function")
    print("   It might have hardcoded channel 1")
    print("   Look for lines like:")
    print("     - self.dev.ctrl_transfer(..., 0x01, ...)  # 0x01 might be CH1")
    print("     - Change to: self.dev.ctrl_transfer(..., channel, ...)")
    
    print("\n4. USE SCOPE'S MATH FUNCTION:")
    print("   - Set Math = CH2")
    print("   - Try reading Math channel if available")

def main():
    """Main test sequence"""
    
    print("\nDSO5102P Channel 2 Diagnostic")
    print("This will test various methods to read Channel 2\n")
    
    # Run tests
    working_param = test_channel_access()
    
    if working_param is not None:
        print("\n" + "="*60)
        print("SUCCESS!")
        print("="*60)
        print(f"Channel 2 works with parameter: {repr(working_param)}")
        print("\nUpdate your code to use this parameter:")
        print(f"  data = dso.ReadSampleData({repr(working_param)})")
    else:
        print("\n" + "="*60)
        print("Channel 2 not accessible with standard methods")
        print("="*60)
        
        # Try additional tests
        test_dual_channel()
        check_scope_state()
        
        # Provide alternatives
        alternative_solution()
        
        print("\n" + "="*60)
        print("RECOMMENDED ACTION:")
        print("="*60)
        print("Use Channel 1 for now:")
        print("1. Move signal to CH1")
        print("2. Set trigger to CH1") 
        print("3. Run: python3 radiation_spectroscopy.py --channel 1")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
    except Exception as e:
        print(f"\nError: {e}")
        print("Try running with sudo")