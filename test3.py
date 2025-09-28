import sys
import usb.core
import usb.util
import time
sys.path.insert(0, '/Users/joe/DSO5102P-Python')

def setup_usb_device(vid=0x049f, pid=0x505a):
    """Manually configure USB device before DSO5102P uses it"""
    print("=== Manual USB Setup ===")
    
    # Find device
    dev = usb.core.find(idVendor=vid, idProduct=pid)
    if dev is None:
        raise ValueError("Device not found")
    
    print(f"Found device: {dev}")
    
    # Reset device
    try:
        print("Resetting device...")
        dev.reset()
        time.sleep(2)  # Wait for reset
        
        # Find device again after reset
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise ValueError("Device not found after reset")
        
    except Exception as e:
        print(f"Reset failed (might be OK): {e}")
    
    # Configure device
    try:
        print("Setting configuration...")
        dev.set_configuration()
        
        print("Claiming interface...")
        usb.util.claim_interface(dev, 0)
        
        print("USB setup complete!")
        return True
        
    except Exception as e:
        print(f"USB configuration failed: {e}")
        return False

# Set up USB first
if setup_usb_device():
    print("\n=== Testing DSO5102P ===")
    try:
        from rcr.dso5102p.DSO5102P import DSO5102P
        
        # Now try to use DSO5102P
        dso = DSO5102P(0x049f, 0x505a, False)
        
        print("Testing basic functions...")
        print("1. System Time:", dso.ReadSystemTime())
        print("2. Echo test:", dso.Echo(b'test'))
        
        print("\nTesting data functions...")
        print("3. Starting acquisition...")
        dso.StartAcquisition()
        
        time.sleep(0.5)  # Wait for data
        
        print("4. Reading CH1 data...")
        ch1_data = dso.ReadSampleData(1)
        print(f"CH1 data length: {len(ch1_data) if ch1_data else 0}")
        
        print("5. Stopping acquisition...")
        dso.StopAcquisition()
        
        print("SUCCESS! Data capture working!")
        
    except Exception as e:
        print(f"DSO5102P failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("USB setup failed")