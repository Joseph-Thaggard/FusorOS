#!/usr/bin/env python3
"""
Plasma Generator Control System Data Visualizer

This tool can visualize data from plasma generator control systems with support for:
1. Raw Arduino data with cleaned format (Time,T,P,VHV,IHV,FMFC,V1,V2,DEMO)
2. Event data showing control system actions
3. Raw data format from the uploaded file (Time,Raw Line with DATA: prefix)

Usage:
    python plasma_visualizer.py --data data_file.csv --variables T,P,VHV --events events_file.csv
    python plasma_visualizer.py --data data_file.csv --variables IHV,FMFC --time-range 14:42:05 14:42:10
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import argparse
import numpy as np
import re
from pathlib import Path

class PlasmaDataVisualizer:
    def __init__(self):
        self.data = None
        self.events = None
        self.time_col = 'Time'
        
        # Variable descriptions for better plotting
        self.var_descriptions = {
            'T': 'Operational Time (ms)',  # Time since program start
            'P': 'Pressure (Pa)',
            'VHV': 'High Voltage (V)',
            'IHV': 'High Voltage Current (A)',
            'FMFC': 'Mass Flow Controller (SCCM)',
            'V1': 'Valve 1 State',
            'V2': 'Valve 2 State',
            'DEMO': 'Demo Mode',
            'Time': 'Real Time (HH:MM:SS)'  # Wall clock time
        }
        
        # Set up matplotlib styling
        plt.style.use('seaborn-v0_8' if 'seaborn-v0_8' in plt.style.available else 'default')
        self.setup_plot_style()
    
    def setup_plot_style(self):
        """Configure matplotlib for better-looking plots"""
        plt.rcParams['figure.figsize'] = (12, 8)
        plt.rcParams['font.size'] = 10
        plt.rcParams['axes.grid'] = True
        plt.rcParams['grid.alpha'] = 0.3
        plt.rcParams['lines.linewidth'] = 1.5
    
    def parse_time(self, time_str):
        """Parse time string in HH:MM:SS.mmm format"""
        try:
            # Handle the format HH:MM:SS.mmm
            return datetime.strptime(time_str, '%H:%M:%S.%f').time()
        except ValueError:
            try:
                # Fallback for HH:MM:SS format
                return datetime.strptime(time_str, '%H:%M:%S').time()
            except ValueError:
                print(f"Warning: Could not parse time '{time_str}'")
                return None
    
    def load_raw_data(self, filepath):
        """Load data from raw format (like the uploaded file)"""
        data_rows = []
        event_rows = []
        
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            parts = line.split(',', 1)
            if len(parts) != 2:
                continue
                
            time_str, content = parts
            
            if content.startswith('DATA:'):
                # Parse data line: DATA:T=33,P=1999.0000,VHV=0.2,IHV=0.0557,FMFC=5.3763,V1=0,V2=0,DEMO=0
                data_part = content[5:]  # Remove 'DATA:'
                data_dict = {self.time_col: time_str}  # Use detected time column name
                
                for item in data_part.split(','):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        try:
                            data_dict[key] = float(value)
                        except ValueError:
                            data_dict[key] = value
                
                data_rows.append(data_dict)
            
            elif content.startswith('CMD'):
                # Parse command/event line
                event_rows.append({
                    self.time_col: time_str,
                    'Event': content,
                    'Type': 'Command'
                })
        
        if data_rows:
            self.data = pd.DataFrame(data_rows)
            self.convert_time_column(self.data)
            print(f"Detected variables from raw data: {', '.join(self.get_available_variables())}")
        
        if event_rows:
            self.events = pd.DataFrame(event_rows)
            self.convert_time_column(self.events)
        
        print(f"Loaded {len(data_rows)} data points and {len(event_rows)} events")
        return self.data is not None
    
    def load_clean_data(self, filepath):
        """Load data from cleaned CSV format"""
        try:
            self.data = pd.read_csv(filepath)
            # Auto-detect time column (first column is assumed to be time)
            if len(self.data.columns) > 0:
                self.time_col = self.data.columns[0]
                print(f"Detected time column: '{self.time_col}'")
            self.convert_time_column(self.data)
            print(f"Loaded {len(self.data)} data points from cleaned format")
            print(f"Detected variables: {', '.join(self.get_available_variables())}")
            return True
        except Exception as e:
            print(f"Error loading clean data: {e}")
            return False
    
    def load_events(self, filepath):
        """Load events data from CSV file"""
        try:
            self.events = pd.read_csv(filepath)
            self.convert_time_column(self.events)
            print(f"Loaded {len(self.events)} events")
            return True
        except Exception as e:
            print(f"Error loading events: {e}")
            return False
    
    def convert_time_column(self, df):
        """Convert time column to datetime for plotting"""
        if self.time_col in df.columns:
            # Create a base date (today) and combine with time
            base_date = datetime.now().date()
            df['datetime'] = df[self.time_col].apply(
                lambda x: datetime.combine(base_date, self.parse_time(x)) if self.parse_time(x) else None
            )
            df = df.dropna(subset=['datetime'])
        
        # Also create operational time datetime if T exists
        if 'T' in df.columns and pd.api.types.is_numeric_dtype(df['T']):
            # Convert T (milliseconds) to seconds and create timedelta from start
            start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            df['op_datetime'] = df['T'].apply(lambda x: start_time + timedelta(milliseconds=x) if pd.notna(x) else None)
    
    def auto_detect_format(self, filepath):
        """Auto-detect data format and load accordingly"""
        try:
            # First try to read as CSV
            test_df = pd.read_csv(filepath, nrows=5)
            if len(test_df.columns) > 2:
                # Check if first column looks like time
                first_col = test_df.columns[0].lower()
                if 'time' in first_col or test_df.iloc[0, 0].count(':') >= 2:
                    print(f"Detected CSV format with columns: {', '.join(test_df.columns)}")
                    return self.load_clean_data(filepath)
        except:
            pass
        
        # Try raw format
        print("Attempting to load as raw format...")
        return self.load_raw_data(filepath)
    
    def get_available_variables(self):
        """Get list of available variables for plotting (excluding time columns)"""
        if self.data is None:
            return []
        return [col for col in self.data.columns if col not in [self.time_col, 'datetime']]
    
    def get_numeric_variables(self):
        """Get list of numeric variables suitable for plotting"""
        if self.data is None:
            return []
        numeric_vars = []
        for var in self.get_available_variables():
            if pd.api.types.is_numeric_dtype(self.data[var]):
                numeric_vars.append(var)
        return numeric_vars
    
    def auto_select_variables(self):
        """Auto-select variables for plotting - prioritize main plasma parameters"""
        numeric_vars = self.get_numeric_variables()
        
        if not numeric_vars:
            return []
        
        # Priority order for plasma generator variables
        # T is operational time (time since program start) - most important for analysis
        priority_vars = ['T', 'P', 'VHV', 'IHV', 'FMFC', 'V1', 'V2']
        
        # Select variables in priority order if they exist
        selected_vars = []
        for var in priority_vars:
            if var in numeric_vars:
                selected_vars.append(var)
        
        # Add any remaining numeric variables (excluding 'Time' which is real time)
        for var in numeric_vars:
            if var not in selected_vars and var.lower() != 'time':
                selected_vars.append(var)
        
        return selected_vars
    
    def plot_variables(self, variables=None, time_range=None, save_path=None, show_events=True, 
                      event_legend_path=None, use_operational_time=False):
        """Plot specified variables over time with numbered event indicators"""
        if self.data is None:
            print("No data loaded!")
            return
        
        # Auto-select variables if none specified
        if variables is None:
            variables = self.auto_select_variables()
            if not variables:
                print("No suitable variables found for plotting!")
                return
            print(f"Auto-selected variables: {', '.join(variables)}")
            print("Note: 'T' represents operational time (ms since program start)")
            if 'Time' in self.get_available_variables():
                print("      'Time' represents real time (HH:MM:SS) and is used for x-axis")
        
        # Determine which time axis to use
        if use_operational_time and 'op_datetime' in self.data.columns:
            time_column = 'op_datetime'
            time_label = 'Operational Time'
            time_format = '%M:%S'  # Minutes:Seconds for operational time
            print("Using operational time (T) for x-axis")
        else:
            time_column = 'datetime'
            time_label = 'Real Time'
            time_format = '%H:%M:%S'  # Hours:Minutes:Seconds for real time
            if use_operational_time:
                print("Warning: Operational time not available, using real time")
            else:
                print("Using real time for x-axis")
        
        # Filter data by time range if specified
        plot_data = self.data.copy()
        if time_range:
            start_time, end_time = time_range
            # For operational time, convert time range to operational format
            if use_operational_time and 'op_datetime' in plot_data.columns:
                mask = (plot_data[time_column] >= start_time) & (plot_data[time_column] <= end_time)
            else:
                mask = (plot_data['datetime'] >= start_time) & (plot_data['datetime'] <= end_time)
            plot_data = plot_data[mask]
        
        if plot_data.empty:
            print("No data in specified time range!")
            return
        
        # Prepare event data and numbering
        event_legend = []
        filtered_events = None
        if show_events and self.events is not None and not self.events.empty:
            filtered_events = self.events.copy()
            if time_range:
                # Use real time for event filtering regardless of plot time axis
                mask = (filtered_events['datetime'] >= start_time) & (filtered_events['datetime'] <= end_time)
                filtered_events = filtered_events[mask]
            
            # Create numbered event legend
            for i, (_, event) in enumerate(filtered_events.iterrows(), 1):
                event_text = event.get('Event', 'Unknown Event')
                event_time = event[self.time_col]
                event_legend.append(f"E{i}: {event_time} - {event_text}")
        
        # Create subplots
        n_vars = len(variables)
        fig, axes = plt.subplots(n_vars, 1, figsize=(14, 4*n_vars), sharex=True)
        
        if n_vars == 1:
            axes = [axes]
        
        # Plot each variable
        for i, var in enumerate(variables):
            if var not in plot_data.columns:
                print(f"Warning: Variable '{var}' not found in data")
                continue
            
            ax = axes[i]
            ax.plot(plot_data[time_column], plot_data[var], 'b-', alpha=0.8, linewidth=1.5)
            
            # Set labels
            ylabel = self.var_descriptions.get(var, var)
            ax.set_ylabel(ylabel, fontsize=12)
            time_desc = " (Operational)" if use_operational_time else " (Real)"
            ax.set_title(f'{var} vs {time_label}{time_desc}', fontsize=14, fontweight='bold')
            
            # Add grid
            ax.grid(True, alpha=0.3)
            ax.set_axisbelow(True)
            
            # Add numbered event indicators
            if show_events and filtered_events is not None and not filtered_events.empty:
                y_min, y_max = ax.get_ylim()
                y_range = y_max - y_min
                
                for event_num, (_, event) in enumerate(filtered_events.iterrows(), 1):
                    # Use appropriate time column for event positioning
                    if use_operational_time and 'op_datetime' in event.index:
                        event_time = event['op_datetime']
                    else:
                        event_time = event['datetime']
                    
                    # Draw vertical line
                    ax.axvline(x=event_time, color='red', linestyle='--', alpha=0.7, linewidth=2)
                    
                    # Add numbered circle marker
                    marker_y = y_max - (0.05 * y_range)
                    ax.scatter(event_time, marker_y, s=200, c='red', marker='o', 
                             zorder=10, edgecolor='white', linewidth=2, alpha=0.9)
                    
                    # Add event number
                    ax.text(event_time, marker_y, f'E{event_num}', 
                           ha='center', va='center', fontsize=10, fontweight='bold', 
                           color='white', zorder=11)
                    
                    # Adjust y-axis limits to accommodate markers
                    ax.set_ylim(y_min, y_max + (0.08 * y_range))
        
        # Format x-axis
        axes[-1].set_xlabel(f'{time_label}', fontsize=12)
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter(time_format))
        
        # Adjust time locator based on time type
        if use_operational_time:
            axes[-1].xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        else:
            axes[-1].xaxis.set_major_locator(mdates.SecondLocator(interval=10))
        
        plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45)
        
        # Add event legend as text box on the first subplot if events exist
        if show_events and event_legend:
            legend_text = "Event Reference:\n" + "\n".join(event_legend)
            axes[0].text(0.02, 0.98, legend_text, transform=axes[0].transAxes, 
                        fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', 
                        facecolor='wheat', alpha=0.8), family='monospace')
        
        plt.tight_layout()
        
        # Save event legend to separate file if requested
        if event_legend_path and event_legend:
            with open(event_legend_path, 'w') as f:
                f.write("Plasma Generator Event Log\n")
                f.write("=" * 40 + "\n\n")
                for event_entry in event_legend:
                    f.write(event_entry + "\n")
                f.write(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            print(f"Event legend saved to {event_legend_path}")
        
        # Save or show plot
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")
        else:
            plt.show()
        
        # Print event legend to console
        if event_legend:
            print("\n=== Event Reference ===")
            for event_entry in event_legend:
                print(f"Event legend saved to {event_legend_path}")
        
        # Save or show plot
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")
        else:
            plt.show()
        
        # Print event legend to console
        if event_legend:
            print("\n=== Event Reference ===")
            for event_entry in event_legend:
                print(event_entry)
    
    def create_dashboard(self, save_path=None, event_legend_path=None, use_operational_time=False):
        """Create a comprehensive dashboard with all variables and numbered events"""
        if self.data is None:
            print("No data loaded!")
            return
        
        # Get numeric variables
        numeric_vars = self.get_numeric_variables()
        
        if not numeric_vars:
            print("No numeric variables found!")
            return
        
        # Determine which time axis to use
        if use_operational_time and 'op_datetime' in self.data.columns:
            time_column = 'op_datetime'
            time_label = 'Operational Time'
            time_format = '%M:%S'
            print("Dashboard using operational time (T) for x-axis")
        else:
            time_column = 'datetime'
            time_label = 'Real Time'
            time_format = '%H:%M:%S'
            if use_operational_time:
                print("Warning: Operational time not available, using real time")
        
        # Prepare event data and numbering
        event_legend = []
        if self.events is not None and not self.events.empty:
            for i, (_, event) in enumerate(self.events.iterrows(), 1):
                event_text = event.get('Event', 'Unknown Event')
                event_time = event[self.time_col]
                event_legend.append(f"E{i}: {event_time} - {event_text}")
        
        # Create dashboard
        fig = plt.figure(figsize=(16, 12))
        time_desc = " (Operational)" if use_operational_time else " (Real)"
        fig.suptitle(f'Plasma Generator Control System Dashboard - {time_label}{time_desc}', 
                    fontsize=16, fontweight='bold')
        
        n_vars = len(numeric_vars)
        rows = int(np.ceil(n_vars / 2))
        
        for i, var in enumerate(numeric_vars):
            ax = plt.subplot(rows, 2, i+1)
            
            # Plot main data
            ax.plot(self.data[time_column], self.data[var], 'b-', alpha=0.8, linewidth=1.5, label=var)
            
            # Add numbered event indicators
            if self.events is not None and not self.events.empty:
                y_min, y_max = ax.get_ylim()
                y_range = y_max - y_min
                
                for event_num, (_, event) in enumerate(self.events.iterrows(), 1):
                    # Use appropriate time column for event positioning
                    if use_operational_time and 'op_datetime' in event.index:
                        event_time = event['op_datetime']
                    else:
                        event_time = event['datetime']
                    
                    # Draw vertical line
                    ax.axvline(x=event_time, color='red', linestyle='--', alpha=0.6, linewidth=1)
                    
                    # Add numbered circle marker (smaller for dashboard)
                    marker_y = y_max - (0.05 * y_range)
                    ax.scatter(event_time, marker_y, s=100, c='red', marker='o', 
                             zorder=10, edgecolor='white', linewidth=1, alpha=0.8)
                    
                    # Add event number
                    ax.text(event_time, marker_y, f'E{event_num}', 
                           ha='center', va='center', fontsize=8, fontweight='bold', 
                           color='white', zorder=11)
                
                # Adjust y-axis limits to accommodate markers
                ax.set_ylim(y_min, y_max + (0.08 * y_range))
            
            # Formatting
            ylabel = self.var_descriptions.get(var, var)
            ax.set_ylabel(ylabel, fontsize=10)
            ax.set_title(f'{var}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=45)
            
            # Format time axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter(time_format))
        
        plt.tight_layout()
        
        # Save event legend to separate file if requested
        if event_legend_path and event_legend:
            with open(event_legend_path, 'w') as f:
                f.write("Plasma Generator Dashboard Event Log\n")
                f.write("=" * 50 + "\n\n")
                for event_entry in event_legend:
                    f.write(event_entry + "\n")
                f.write(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            print(f"Event legend saved to {event_legend_path}")
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Dashboard saved to {save_path}")
        else:
            plt.show()
        
        # Print event legend to console
        if event_legend:
            print("\n=== Event Reference for Dashboard ===")
            for event_entry in event_legend:
                print(event_entry)
    
    def print_summary(self):
        """Print summary of loaded data"""
        if self.data is not None:
            print("\n=== Data Summary ===")
            print(f"Data points: {len(self.data)}")
            print(f"Time range: {self.data[self.time_col].iloc[0]} to {self.data[self.time_col].iloc[-1]}")
            print(f"Available variables: {', '.join(self.get_available_variables())}")
            
            print("\n=== Variable Statistics ===")
            numeric_vars = self.get_numeric_variables()
            
            for var in numeric_vars:
                data_series = self.data[var]
                print(f"{var}: min={data_series.min():.3f}, max={data_series.max():.3f}, "
                      f"mean={data_series.mean():.3f}, std={data_series.std():.3f}")
        
        if self.events is not None:
            print(f"\n=== Events ===")
            print(f"Event count: {len(self.events)}")
            if 'Event' in self.events.columns:
                event_types = self.events['Event'].value_counts()
                print("Event types:")
                for event_type, count in event_types.items():
                    print(f"  {event_type}: {count}")

def main():
    parser = argparse.ArgumentParser(description='Visualize plasma generator control system data')
    parser.add_argument('--data', required=True, help='Path to data file')
    parser.add_argument('--events', help='Path to events file (optional)')
    parser.add_argument('--variables', help='Comma-separated list of variables to plot')
    parser.add_argument('--dashboard', action='store_true', help='Create comprehensive dashboard')
    parser.add_argument('--save', help='Save plot to file instead of displaying')
    parser.add_argument('--event-legend', help='Save event reference to text file')
    parser.add_argument('--time-range', nargs=2, help='Time range to plot (start end in HH:MM:SS format)')
    parser.add_argument('--operational-time', action='store_true', 
                       help='Use operational time (T) instead of real time for x-axis')
    
    args = parser.parse_args()
    
    # Create visualizer
    viz = PlasmaDataVisualizer()
    
    # Load data
    print(f"Loading data from {args.data}...")
    if not viz.auto_detect_format(args.data):
        print("Failed to load data!")
        return
    
    # Load events if specified
    if args.events:
        print(f"Loading events from {args.events}...")
        viz.load_events(args.events)
    
    # Print summary
    viz.print_summary()
    
    # Handle time range
    time_range = None
    if args.time_range:
        base_date = datetime.now().date()
        try:
            start_time = datetime.combine(base_date, datetime.strptime(args.time_range[0], '%H:%M:%S').time())
            end_time = datetime.combine(base_date, datetime.strptime(args.time_range[1], '%H:%M:%S').time())
            time_range = (start_time, end_time)
        except ValueError:
            print("Invalid time range format. Use HH:MM:SS")
    
    # Create plots
    if args.dashboard:
        viz.create_dashboard(save_path=args.save, event_legend_path=args.event_legend,
                           use_operational_time=args.operational_time)
    elif args.variables:
        variables = [v.strip() for v in args.variables.split(',')]
        viz.plot_variables(variables, time_range=time_range, save_path=args.save, 
                         event_legend_path=args.event_legend, 
                         use_operational_time=args.operational_time)
    else:
        # Auto-plot all variables if none specified
        print("No variables specified, auto-plotting all numeric variables...")
        viz.plot_variables(time_range=time_range, save_path=args.save, 
                         event_legend_path=args.event_legend,
                         use_operational_time=args.operational_time)
        variables = [v.strip() for v in args.variables.split(',')]
        viz.plot_variables(variables, time_range=time_range, save_path=args.save, 
                         event_legend_path=args.event_legend)
if __name__ == "__main__":
    main()