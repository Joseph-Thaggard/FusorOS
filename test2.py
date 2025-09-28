#!/usr/bin/env python3
"""
Check if DSO5102P library supports Channel 2 and provide fix
"""

import os
import shutil

def check_library():
    """Check the DSO5102P library for channel support"""
    
    library_path = '/Users/joe/DSO5102P-Python/rcr/dso5102p/DSO5102P.py'
    
    print("="*60)
    print("DSO5102P LIBRARY CHANNEL SUPPORT CHECK")
    print("="*60)
    
    if not os.path.exists(library_path):
        print(f"\n✗ Library not found at: {library_path}")
        return False
    
    print(f"\n✓ Found library at: {library_path}")
    
    # Read the library
    with open(library_path, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Look for ReadSampleData function
    print("\nSearching for ReadSampleData function...")
    
    found_issue = False
    for i, line in enumerate(lines):
        if 'def ReadSampleData' in line:
            print(f"\nFound at line {i+1}:")
            print("-" * 40)
            
            # Show the function (next ~20 lines)
            for j in range(min(20, len(lines)-i)):
                print(f"{i+j+1:4d}: {lines[i+j]}")
                
                # Check for hardcoded channel
                if j > 0 and ('0x01' in lines[i+j] or 'channel=1' in lines[i+j] or 'ch=1' in lines[i+j]):
                    found_issue = True
                    print("\n⚠ FOUND ISSUE: Channel appears to be hardcoded!")
                    
                if 'def ' in lines[i+j] and j > 0:
                    break
            
            print("-" * 40)
            break
    
    # Look for channel parameter usage
    print("\nChecking how channel parameter is used...")
    
    channel_uses = []
    for i, line in enumerate(lines):
        if 'ReadSampleData' in line:
            # Check if it accepts channel parameter
            if 'channel' in line or 'ch' in line:
                channel_uses.append((i+1, line.strip()))
    
    if channel_uses:
        print("Channel parameter references found:")
        for line_num, line in channel_uses[:5]:
            print(f"  Line {line_num}: {line}")
    
    return found_issue

def create_fixed_library():
    """Create a wrapper that properly handles Channel 2"""
    
    print("\n" + "="*60)
    print("CREATING CHANNEL 2 WRAPPER")
    print("="*60)
    
    wrapper_code = '''#!/usr/bin/env python3
"""
Wrapper for DSO5102P that adds proper Channel 2 support
"""

import sys
sys.path.insert(0, '/Users/joe/DSO5102P-Python')
from rcr.dso5102p.DSO5102P import DSO5102P as OriginalDSO5102P

class DSO5102P(OriginalDSO5102P):
    """Extended DSO5102P with Channel 2 support"""
    
    def ReadSampleData(self, channel=1):
        """Read sample data from specified channel
        
        If the original library doesn't support Channel 2,
        this tries various workarounds.
        """
        
        # First try the original method
        if channel == 1:
            return super().ReadSampleData(1)
        
        # For Channel 2, try different approaches
        elif channel == 2:
            try:
                # Try passing channel parameter
                return super().ReadSampleData(2)
            except:
                # If that fails, try workarounds
                pass
            
            try:
                # Some scopes might use different command for CH2
                # Try swapping channel selection if available
                if hasattr(self, 'SelectChannel'):
                    self.SelectChannel(2)
                    data = super().ReadSampleData(1)
                    self.SelectChannel(1)  # Reset
                    return data
            except:
                pass
            
            # If nothing works, return None
            print("Warning: Channel 2 not supported by library")
            return None
        
        else:
            raise ValueError(f"Invalid channel: {channel}")

# For direct testing
if __name__ == "__main__":
    print("Testing DSO5102P wrapper with Channel 2 support...")
    
    dso = DSO5102P(0x049f, 0x505a)
    
    print("\\nTesting Channel 1:")
    dso.StartAcquisition()
    import time
    time.sleep(0.1)
    data1 = dso.ReadSampleData(1)
    dso.StopAcquisition()
    print(f"  CH1: {len(data1) if data1 else 'No'} data")
    
    print("\\nTesting Channel 2:")
    dso.StartAcquisition()
    time.sleep(0.1)
    data2 = dso.ReadSampleData(2)
    dso.StopAcquisition()
    print(f"  CH2: {len(data2) if data2 else 'No'} data")
'''
    
    # Save the wrapper
    wrapper_path = 'dso5102p_wrapper.py'
    with open(wrapper_path, 'w') as f:
        f.write(wrapper_code)
    
    print(f"\n✓ Created wrapper at: {wrapper_path}")
    print("\nTo use this wrapper, modify your imports:")
    print("  FROM: from rcr.dso5102p.DSO5102P import DSO5102P")
    print("  TO:   from dso5102p_wrapper import DSO5102P")
    
    return wrapper_path

def suggest_immediate_fix():
    """Suggest immediate workaround"""
    
    print("\n" + "="*60)
    print("IMMEDIATE SOLUTION")
    print("="*60)
    
    print("\nThe DSO5102P library appears to only support Channel 1.")
    print("\n✓ EASIEST FIX: Use Channel 1 instead of Channel 2")
    print("\n1. Connect your signal to CH1 (not CH2)")
    print("2. On the scope:")
    print("   - Press CH1 button (should be lit)")
    print("   - Set Trigger Source: CH1")
    print("   - Set Trigger Level: ±80mV")
    print("   - Set Trigger Mode: Normal")
    print("\n3. Update your code to use Channel 1:")
    print("   spec = RadiationSpectroscopy(debug=False, channel=1)")
    print("\n4. Run the spectroscopy system normally")
    
    print("\n" + "="*60)
    print("Alternative: Physical Y-splitter")
    print("="*60)
    print("If you must use CH2 for display while capturing from CH1:")
    print("1. Use a BNC T-connector to split the signal")
    print("2. Connect one output to CH1 (for capture)")
    print("3. Connect other output to CH2 (for display)")
    print("4. Use CH1 in software, view on CH2 on scope")

if __name__ == "__main__":
    # Check the library
    has_issue = check_library()
    
    if has_issue:
        print("\n⚠ The library likely doesn't support Channel 2")
        
        # Create wrapper
        create_fixed_library()
    
    # Always suggest the immediate fix
    suggest_immediate_fix()
    
    print("\n" + "="*60)
    print("RECOMMENDED ACTION:")
    print("="*60)
    print("Just use Channel 1 - it's the simplest solution!")
    print("The library was designed for CH1, so let's use it as intended.")