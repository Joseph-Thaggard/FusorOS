#!/usr/bin/env python3
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
    
    print("\nTesting Channel 1:")
    dso.StartAcquisition()
    import time
    time.sleep(0.1)
    data1 = dso.ReadSampleData(1)
    dso.StopAcquisition()
    print(f"  CH1: {len(data1) if data1 else 'No'} data")
    
    print("\nTesting Channel 2:")
    dso.StartAcquisition()
    time.sleep(0.1)
    data2 = dso.ReadSampleData(2)
    dso.StopAcquisition()
    print(f"  CH2: {len(data2) if data2 else 'No'} data")
