#!/usr/bin/env python3
"""
Real-time Radiation Monitoring Dashboard
Interactive visualization for radiation spectroscopy system
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button, Slider, TextBox
import matplotlib.gridspec as gridspec
from collections import deque
import time
from datetime import datetime
from scipy import signal
import threading
import warnings

# Suppress matplotlib warnings for empty data
warnings.filterwarnings("ignore", category=UserWarning)

class RadiationMonitorDashboard:
    def __init__(self, spectroscopy_system):
        """Initialize real-time monitoring dashboard
        
        Args:
            spectroscopy_system: Instance of RadiationSpectroscopy class
        """
        self.spec = spectroscopy_system
        
        # Data buffers
        self.count_rate_history = deque(maxlen=300)  # 5 minutes at 1Hz update
        self.time_history = deque(maxlen=300)
        self.pulse_height_scatter = deque(maxlen=1000)
        self.pulse_time_scatter = deque(maxlen=1000)
        
        # Display parameters
        self.spectrum_log_scale = False  # Start with linear scale
        self.energy_scale = False
        self.auto_scale = True
        self.roi_markers = []  # Regions of interest
        
        # Statistics
        self.update_counter = 0
        self.last_update_time = time.time()
        
        # Setup the figure
        self.setup_figure()
        
    def setup_figure(self):
        """Setup the monitoring dashboard figure"""
        
        # Create figure with custom layout
        self.fig = plt.figure(figsize=(16, 10))
        self.fig.suptitle('Radiation Spectroscopy Monitor', fontsize=16, fontweight='bold')
        
        # Create grid layout
        gs = gridspec.GridSpec(3, 3, figure=self.fig, 
                              height_ratios=[2, 1, 1],
                              width_ratios=[2, 1, 1])
        
        # Main spectrum display
        self.ax_spectrum = self.fig.add_subplot(gs[0, :])
        self.ax_spectrum.set_title('Energy Spectrum')
        self.ax_spectrum.set_xlabel('Channel')
        self.ax_spectrum.set_ylabel('Counts')
        self.ax_spectrum.grid(True, alpha=0.3)
        self.ax_spectrum.set_xlim(0, self.spec.num_channels)
        self.ax_spectrum.set_ylim(0, 10)  # Initial y-limit for empty spectrum
        
        # Count rate history
        self.ax_rate = self.fig.add_subplot(gs[1, 0])
        self.ax_rate.set_title('Count Rate History')
        self.ax_rate.set_xlabel('Time (s)')
        self.ax_rate.set_ylabel('Rate (cps)')
        self.ax_rate.grid(True, alpha=0.3)
        
        # Pulse height vs time scatter
        self.ax_scatter = self.fig.add_subplot(gs[1, 1:])
        self.ax_scatter.set_title('Pulse Heights vs Time')
        self.ax_scatter.set_xlabel('Time (s)')
        self.ax_scatter.set_ylabel('Pulse Height')
        self.ax_scatter.grid(True, alpha=0.3)
        
        # Statistics panel
        self.ax_stats = self.fig.add_subplot(gs[2, 0])
        self.ax_stats.axis('off')
        self.stats_text = self.ax_stats.text(0.05, 0.95, '', transform=self.ax_stats.transAxes,
                                             fontsize=10, verticalalignment='top',
                                             fontfamily='monospace')
        
        # Control panel
        self.ax_controls = self.fig.add_subplot(gs[2, 1:])
        self.ax_controls.axis('off')
        
        # Add control buttons
        self.setup_controls()
        
        # Initialize plot elements
        self.spectrum_line, = self.ax_spectrum.plot([], [], 'b-', linewidth=0.5)
        self.rate_line, = self.ax_rate.plot([], [], 'g-', linewidth=1)
        self.scatter_points = self.ax_scatter.scatter([], [], s=1, alpha=0.5, c='blue')
        
        plt.tight_layout()
        
    def setup_controls(self):
        """Setup interactive controls"""
        
        # Button positions
        button_width = 0.15
        button_height = 0.08
        
        # Start/Stop button
        self.btn_startstop = Button(plt.axes([0.65, 0.12, button_width, button_height]), 
                                   'Start Acquisition')
        self.btn_startstop.on_clicked(self.toggle_acquisition)
        
        # Clear spectrum button
        self.btn_clear = Button(plt.axes([0.82, 0.12, button_width, button_height]), 
                               'Clear Spectrum')
        self.btn_clear.on_clicked(self.clear_spectrum)
        
        # Save button
        self.btn_save = Button(plt.axes([0.65, 0.03, button_width, button_height]), 
                              'Save Spectrum')
        self.btn_save.on_clicked(self.save_spectrum)
        
        # Log scale toggle
        self.btn_log = Button(plt.axes([0.82, 0.03, button_width, button_height]), 
                             'Toggle Log')
        self.btn_log.on_clicked(self.toggle_log_scale)
        
    def update_display(self, frame):
        """Update all display elements"""
        
        self.update_counter += 1
        current_time = time.time()
        
        # Update spectrum
        channels = np.arange(self.spec.num_channels)
        spectrum = self.spec.spectrum
        
        # Only update spectrum plot if there's data
        total_counts = np.sum(spectrum)
        max_counts = np.max(spectrum) if total_counts > 0 else 0
        
        if total_counts > 0:
            self.spectrum_line.set_data(channels, spectrum)
            
            if self.auto_scale:
                self.ax_spectrum.relim()
                self.ax_spectrum.autoscale_view()
                
                # Only set log scale if there's actual data
                if self.spectrum_log_scale and max_counts > 0:
                    try:
                        self.ax_spectrum.set_yscale('log')
                        self.ax_spectrum.set_ylim(bottom=0.5, top=max_counts * 1.5)
                    except ValueError:
                        # Fall back to linear if log scale fails
                        self.ax_spectrum.set_yscale('linear')
                        self.ax_spectrum.set_ylim(bottom=0, top=max_counts * 1.1)
                else:
                    self.ax_spectrum.set_yscale('linear')
                    if max_counts > 0:
                        self.ax_spectrum.set_ylim(bottom=0, top=max_counts * 1.1)
        else:
            # Handle empty spectrum case
            self.spectrum_line.set_data(channels, spectrum)
            self.ax_spectrum.set_yscale('linear')
            self.ax_spectrum.set_ylim(bottom=0, top=10)  # Default range for empty spectrum
        
        # Update count rate history
        if self.spec.real_time > 0:
            current_rate = self.spec.total_counts / self.spec.real_time
            self.count_rate_history.append(current_rate)
            self.time_history.append(self.spec.real_time)
            
            if len(self.time_history) > 1:
                self.rate_line.set_data(list(self.time_history), list(self.count_rate_history))
                self.ax_rate.relim()
                self.ax_rate.autoscale_view()
        
        # Update pulse scatter plot
        if len(self.spec.pulse_history) > 0:
            recent_pulses = list(self.spec.pulse_history)[-1000:]  # Last 1000 pulses
            
            if recent_pulses and self.spec.start_time:
                times = [(p.timestamp - self.spec.start_time) for p in recent_pulses]
                heights = [p.peak_height for p in recent_pulses]
                
                # Create color map based on pile-up status
                colors = ['red' if p.is_pileup else 'blue' for p in recent_pulses]
                
                # Update scatter plot
                self.ax_scatter.clear()
                self.ax_scatter.scatter(times, heights, s=1, alpha=0.5, c=colors)
                self.ax_scatter.set_xlabel('Time (s)')
                self.ax_scatter.set_ylabel('Pulse Height')
                self.ax_scatter.set_title('Pulse Heights vs Time')
                self.ax_scatter.grid(True, alpha=0.3)
        
        # Update statistics
        self.update_statistics()
        
        # Calculate update rate
        if self.update_counter % 10 == 0:
            dt = current_time - self.last_update_time
            update_rate = 10.0 / dt if dt > 0 else 0
            self.last_update_time = current_time
            print(f"Display update rate: {update_rate:.1f} Hz")
        
        return self.spectrum_line, self.rate_line, self.stats_text
    
    def update_statistics(self):
        """Update statistics display"""
        
        stats = []
        stats.append("═══ STATISTICS ═══")
        stats.append(f"Total Counts:  {self.spec.total_counts:8d}")
        stats.append(f"Rejected:      {self.spec.rejected_counts:8d}")
        
        if self.spec.real_time > 0:
            rate = self.spec.total_counts / self.spec.real_time
            stats.append(f"Count Rate:    {rate:8.1f} cps")
            stats.append(f"Real Time:     {self.spec.real_time:8.1f} s")
            stats.append(f"Live Time:     {self.spec.live_time:8.1f} s")
            
            dead_time_pct = (1 - self.spec.live_time/self.spec.real_time) * 100
            stats.append(f"Dead Time:     {dead_time_pct:8.1f} %")
            
            if self.spec.rejected_counts > 0:
                pileup_rate = self.spec.rejected_counts / self.spec.real_time
                stats.append(f"Pile-up Rate:  {pileup_rate:8.1f} cps")
        
        # Find highest channel with counts
        if np.sum(self.spec.spectrum) > 0:
            max_channel = np.argmax(self.spec.spectrum)
            max_counts = self.spec.spectrum[max_channel]
            stats.append(f"Peak Channel:  {max_channel:8d}")
            stats.append(f"Peak Counts:   {max_counts:8d}")
        
        self.stats_text.set_text('\n'.join(stats))
    
    def toggle_acquisition(self, event):
        """Toggle data acquisition"""
        
        if self.spec.acquisition_active:
            self.spec.stop_acquisition()
            self.btn_startstop.label.set_text('Start Acquisition')
            print("Acquisition stopped")
        else:
            # Start acquisition in background thread
            thread = threading.Thread(target=self.spec.start_acquisition)
            thread.daemon = True
            thread.start()
            self.btn_startstop.label.set_text('Stop Acquisition')
            print("Acquisition started")
    
    def clear_spectrum(self, event):
        """Clear the spectrum"""
        
        self.spec.spectrum.fill(0)
        self.spec.total_counts = 0
        self.spec.rejected_counts = 0
        self.spec.pulse_history.clear()
        self.spec.start_time = time.time()
        self.spec.real_time = 0
        self.spec.live_time = 0
        
        # Clear history buffers
        self.count_rate_history.clear()
        self.time_history.clear()
        self.pulse_height_scatter.clear()
        self.pulse_time_scatter.clear()
        
        print("Spectrum cleared")
    
    def save_spectrum(self, event):
        """Save current spectrum"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"spectrum_{timestamp}.csv"
        self.spec.save_spectrum(filename)
        print(f"Spectrum saved to {filename}")
    
    def toggle_log_scale(self, event):
        """Toggle logarithmic scale"""
        
        self.spectrum_log_scale = not self.spectrum_log_scale
        
        # Check if there's data before setting log scale
        total_counts = np.sum(self.spec.spectrum)
        max_counts = np.max(self.spec.spectrum) if total_counts > 0 else 0
        
        if self.spectrum_log_scale and max_counts > 0:
            try:
                self.ax_spectrum.set_yscale('log')
                self.ax_spectrum.set_ylim(bottom=0.5, top=max_counts * 1.5)
                print("Logarithmic scale enabled")
            except ValueError:
                # Can't use log scale with no positive data
                self.ax_spectrum.set_yscale('linear')
                self.spectrum_log_scale = False
                print("Cannot use log scale - no data. Using linear scale.")
        else:
            self.ax_spectrum.set_yscale('linear')
            if max_counts > 0:
                self.ax_spectrum.set_ylim(bottom=0, top=max_counts * 1.1)
            else:
                self.ax_spectrum.set_ylim(bottom=0, top=10)
            print("Linear scale enabled")
    
    def add_roi(self, start_channel, end_channel, label='ROI'):
        """Add a region of interest to the spectrum
        
        Args:
            start_channel: Starting channel
            end_channel: Ending channel
            label: ROI label
        """
        
        # Add shaded region
        roi = self.ax_spectrum.axvspan(start_channel, end_channel, 
                                       alpha=0.2, color='yellow',
                                       label=label)
        self.roi_markers.append((start_channel, end_channel, label, roi))
        
        # Calculate ROI statistics
        roi_counts = np.sum(self.spec.spectrum[start_channel:end_channel+1])
        print(f"ROI '{label}': Channels {start_channel}-{end_channel}, Counts: {roi_counts}")
    
    def calculate_roi_statistics(self):
        """Calculate statistics for all ROIs"""
        
        print("\n═══ ROI Statistics ═══")
        
        for start, end, label, _ in self.roi_markers:
            roi_counts = np.sum(self.spec.spectrum[start:end+1])
            roi_background = (end - start + 1) * np.mean(self.spec.spectrum)
            net_counts = roi_counts - roi_background
            
            print(f"{label}:")
            print(f"  Gross counts: {roi_counts}")
            print(f"  Net counts: {net_counts:.0f}")
            
            if self.spec.real_time > 0:
                rate = roi_counts / self.spec.real_time
                print(f"  Count rate: {rate:.2f} cps")
    
    def start(self, update_interval=1000):
        """Start the monitoring dashboard
        
        Args:
            update_interval: Update interval in milliseconds
        """
        
        print("Starting radiation monitor dashboard...")
        print("Controls:")
        print("  - Click 'Start Acquisition' to begin")
        print("  - Click 'Clear Spectrum' to reset")
        print("  - Click 'Save Spectrum' to save data")
        print("  - Click 'Toggle Log' for log/linear scale")
        
        # Setup animation
        self.animation = FuncAnimation(self.fig, self.update_display,
                                     interval=update_interval,
                                     blit=False, cache_frame_data=False)
        
        plt.show()
    
    def stop(self):
        """Stop the monitoring dashboard"""
        
        if hasattr(self, 'animation'):
            self.animation.event_source.stop()
        
        if self.spec.acquisition_active:
            self.spec.stop_acquisition()


def run_monitor(spectroscopy_system):
    """Convenience function to run the monitor
    
    Args:
        spectroscopy_system: Instance of RadiationSpectroscopy class
    """
    
    monitor = RadiationMonitorDashboard(spectroscopy_system)
    
    # Add some example ROIs for common isotopes
    if spectroscopy_system.energy_calibration is not None:
        # Add ROIs for Na-22 peaks
        # These would need to be converted to channels based on calibration
        # monitor.add_roi(500, 522, "Na-22 511keV")
        # monitor.add_roi(1264, 1284, "Na-22 1274keV")
        pass
    
    try:
        monitor.start(update_interval=500)  # Update every 500ms
    except KeyboardInterrupt:
        monitor.stop()
        print("\nMonitor stopped")


if __name__ == "__main__":
    # This would typically be imported and used with the main spectroscopy system
    print("This module should be used with the RadiationSpectroscopy system")
    print("Example usage:")
    print("  from radiation_spectroscopy import RadiationSpectroscopy")
    print("  from radiation_monitor import run_monitor")
    print("  ")
    print("  spec = RadiationSpectroscopy()")
    print("  run_monitor(spec)")