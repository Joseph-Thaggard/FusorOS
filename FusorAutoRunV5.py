#!/usr/bin/env python3
"""
FusorAutoRun.py - Version 4
---------------------------
Execute FusorProgram-generated CSV command files with full variable and parameter support.

New in V4:
- Complete variable substitution in all numeric fields
- Function parameters with proper scoping
- Variable assignment and tracking
- Runtime expression evaluation
- Enhanced function call argument passing
- Nested variable scope management

Compatible with FusorProgramV7 output format.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import serial
import time
import threading
import csv
import os
from datetime import datetime
import sys
from collections import deque
import re

# Matplotlib for live plots
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# ===== CONFIG =====
SERIAL_PORT = '/dev/cu.usbmodem1301'
BAUD_RATE   = 9600
PLOT_WINDOW_SECONDS = 120

# ===== Runtime / Logging setup =====
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
run_dir = os.path.abspath(f"run_{timestamp_str}")
os.makedirs(run_dir, exist_ok=True)

terminal_log_path = os.path.join(run_dir, "terminal_log.csv")
program_log_path  = os.path.join(run_dir, "program_events.csv")

terminal_log_file = open(terminal_log_path, mode="w", newline="")
terminal_log_writer = csv.writer(terminal_log_file)
terminal_log_writer.writerow(["Time", "Raw Line"])

program_log_file = open(program_log_path, mode="w", newline="")
program_log_writer = csv.writer(program_log_file)
program_log_writer.writerow(["Time", "Event", "Details"])

print(f"[INFO] Logs will be saved under: {run_dir}")

# ===== Serial Setup =====
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

def send_command(cmd: str):
    """Send a single command string over serial."""
    try:
        ser.write((cmd + "\n").encode())
        program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "Send:", cmd])
        program_log_file.flush()
    except Exception as e:
        program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "ERROR", f"send_command: {e}"])
        program_log_file.flush()

# ===== Enhanced Variable Management =====
class VariableScope:
    """Manages variable scoping for functions and execution contexts"""
    
    def __init__(self, parent_scope=None):
        self.variables = {}
        self.parent_scope = parent_scope
    
    def set(self, name, value):
        """Set a variable in this scope"""
        # Try to evaluate if it's a numeric string
        if isinstance(value, str):
            try:
                # Check if it's a reference to another variable
                if value.startswith('{') and value.endswith('}'):
                    ref_name = value[1:-1]
                    value = self.get(ref_name)
                else:
                    # Try to parse as number
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
            except:
                pass  # Keep as string if not numeric
        
        self.variables[name] = value
    
    def get(self, name, default=None):
        """Get a variable, checking parent scopes if not found"""
        if name in self.variables:
            return self.variables[name]
        elif self.parent_scope:
            return self.parent_scope.get(name, default)
        else:
            return default
    
    def update(self, other_dict):
        """Update multiple variables at once"""
        for name, value in other_dict.items():
            self.set(name, value)
    
    def copy(self):
        """Create a shallow copy of this scope"""
        new_scope = VariableScope(self.parent_scope)
        new_scope.variables = self.variables.copy()
        return new_scope
    
    def all_variables(self):
        """Get all variables including from parent scopes"""
        all_vars = {}
        if self.parent_scope:
            all_vars.update(self.parent_scope.all_variables())
        all_vars.update(self.variables)
        return all_vars

class FunctionDefinition:
    """Represents a function with parameters and body"""
    
    def __init__(self, name, parameters, commands):
        self.name = name
        self.parameters = []  # List of parameter names
        self.commands = commands
        
        # Parse parameter string
        if parameters:
            self.parameters = [p.strip() for p in parameters.split(',')]
    
    def call(self, arguments, parent_scope):
        """Execute function with given arguments and parent scope"""
        # Create new scope for function execution
        func_scope = VariableScope(parent_scope)
        
        # Bind arguments to parameters
        for i, param_name in enumerate(self.parameters):
            if i < len(arguments):
                # Evaluate argument in parent scope context
                arg_value = evaluate_expression(arguments[i], parent_scope)
                func_scope.set(param_name, arg_value)
            else:
                # Default to 0 if not enough arguments
                func_scope.set(param_name, 0)
        
        return func_scope

def evaluate_expression(expr, scope):
    """Evaluate an expression that might contain variables"""
    if not expr:
        return 0
    
    # Handle string expressions
    expr_str = str(expr).strip()
    
    # Check for variable reference {var_name}
    if expr_str.startswith('{') and expr_str.endswith('}'):
        var_name = expr_str[1:-1]
        value = scope.get(var_name)
        if value is not None:
            return value
        else:
            # Variable not found, try to return as number or keep as string
            try:
                return float(var_name)
            except:
                return expr_str
    
    # Try to evaluate as number
    try:
        if '.' in expr_str:
            return float(expr_str)
        else:
            return int(expr_str)
    except:
        # Check if it might be a variable name without braces
        value = scope.get(expr_str)
        if value is not None:
            return value
        return expr_str

def substitute_variables(cmd, scope):
    """Substitute all {variable} references in a command string"""
    if not cmd or not isinstance(cmd, str):
        return cmd
    
    def replace_var(match):
        var_name = match.group(1)
        value = scope.get(var_name)
        if value is not None:
            return str(value)
        return match.group(0)  # Keep original if variable not found
    
    # Replace {variable_name} patterns
    return re.sub(r'\{(\w+)\}', replace_var, cmd)

# ===== Enhanced Program Execution Classes =====
class FunctionLibraryManager:
    """Manages external function libraries"""
    
    def __init__(self):
        self.library_paths = []
        self.external_functions = {}  # function_name -> commands list
        
    def add_library_path(self, path):
        """Add a library path and scan for functions"""
        if os.path.isdir(path) and path not in self.library_paths:
            self.library_paths.append(path)
            self.scan_library(path)
            return True
        return False
    
    def scan_library(self, library_path):
        """Scan library directory for function files"""
        try:
            for filename in os.listdir(library_path):
                if filename.endswith(('.txt', '.csv', '.func')):
                    func_name = os.path.splitext(filename)[0]
                    file_path = os.path.join(library_path, filename)
                    
                    # Load function commands from file
                    commands = self.load_function_file(file_path)
                    if commands:
                        self.external_functions[func_name] = commands
                        
        except Exception as e:
            print(f"Error scanning library {library_path}: {e}")
    
    def load_function_file(self, file_path):
        """Load function commands from a file"""
        commands = []
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and metadata
                    if line and not line.startswith('#'):
                        commands.append(line)
        except Exception:
            pass
        return commands
    
    def load_function_mapping(self, func_name, file_path):
        """Load a specific function from a file path"""
        if os.path.exists(file_path):
            commands = self.load_function_file(file_path)
            if commands:
                self.external_functions[func_name] = commands
                return True
        return False
    
    def get_function(self, func_name):
        """Get function commands by name"""
        return self.external_functions.get(func_name)

class ProgramContext:
    """Execution context for program state management with enhanced variable support"""
    
    def __init__(self):
        self.functions = {}  # function_name -> FunctionDefinition
        self.global_scope = VariableScope()  # Global variable scope
        self.current_scope = self.global_scope  # Current execution scope
        self.scope_stack = []  # Stack for nested scopes
        self.loop_stack = []  # For nested loops
        self.conditional_stack = []  # For nested conditionals
        self.execution_stopped = False
        self.library_manager = FunctionLibraryManager()
        
    def define_function(self, name, parameters, commands):
        """Define a function with parameters"""
        self.functions[name] = FunctionDefinition(name, parameters, commands)
        
    def call_function(self, name, arguments_str):
        """Call a function with arguments"""
        # Parse arguments
        arguments = []
        if arguments_str:
            # Split by comma but respect nested parentheses
            args = self.parse_arguments(arguments_str)
            arguments = args
        
        # Check internal functions first
        if name in self.functions:
            func_def = self.functions[name]
            # Create function scope
            func_scope = func_def.call(arguments, self.current_scope)
            return func_def.commands, func_scope
        
        # Check external functions
        external_func = self.library_manager.get_function(name)
        if external_func:
            # External functions don't have parameters, just return commands
            return external_func, self.current_scope
            
        raise ValueError(f"Function '{name}' not defined")
    
    def parse_arguments(self, args_str):
        """Parse comma-separated arguments, handling nested expressions"""
        arguments = []
        current_arg = ""
        paren_depth = 0
        
        for char in args_str:
            if char == ',' and paren_depth == 0:
                arguments.append(current_arg.strip())
                current_arg = ""
            else:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                current_arg += char
        
        if current_arg.strip():
            arguments.append(current_arg.strip())
        
        return arguments
    
    def push_scope(self, new_scope=None):
        """Push a new scope onto the stack"""
        self.scope_stack.append(self.current_scope)
        if new_scope:
            self.current_scope = new_scope
        else:
            self.current_scope = VariableScope(self.current_scope)
    
    def pop_scope(self):
        """Pop scope from stack"""
        if self.scope_stack:
            self.current_scope = self.scope_stack.pop()

class CommandParser:
    """Parse and execute enhanced commands with full variable support"""
    
    def __init__(self, context: ProgramContext):
        self.context = context
        
    def parse_program_text(self, text_lines):
        """Parse program text into executable structure"""
        commands = []
        functions = {}
        autorun_config = {"libraries": [], "function_maps": {}}
        
        i = 0
        parsing_mode = "normal"
        
        while i < len(text_lines):
            line = text_lines[i].strip()
            
            # Handle AutoRun configuration sections
            if line == "# [AUTORUN:LIBRARIES]":
                parsing_mode = "libraries"
                i += 1
                continue
            elif line == "# [/AUTORUN:LIBRARIES]":
                parsing_mode = "normal"
                i += 1
                continue
            elif line == "# [AUTORUN:EXTERNAL_FUNCTIONS]":
                parsing_mode = "functions"
                i += 1
                continue
            elif line == "# [/AUTORUN:EXTERNAL_FUNCTIONS]":
                parsing_mode = "normal"
                i += 1
                continue
            
            # Parse based on mode
            if parsing_mode == "libraries":
                if line.startswith("# LIBRARY_PATH="):
                    lib_path = line[15:]
                    autorun_config["libraries"].append(lib_path)
            elif parsing_mode == "functions":
                if line.startswith("# FUNCTION_MAP="):
                    mapping = line[15:]
                    if ":" in mapping:
                        func_name, file_path = mapping.split(":", 1)
                        autorun_config["function_maps"][func_name] = file_path
            else:
                # Normal parsing
                if not line or line.startswith('#'):
                    i += 1
                    continue
                    
                # Handle function definitions with parameters
                if line.startswith('DEFINE_FUNCTION') or line.startswith('FUNCTION '):
                    func_name, func_params = self.extract_function_info(line)
                    func_commands, i = self.parse_function_body(text_lines, i + 1)
                    functions[func_name] = {
                        "parameters": func_params,
                        "commands": func_commands
                    }
                    continue
                    
                commands.append(line)
            
            i += 1
            
        return commands, functions, autorun_config
    
    def extract_function_info(self, line):
        """Extract function name and parameters from definition line"""
        if line.startswith('DEFINE_FUNCTION'):
            # Format: DEFINE_FUNCTION func_name(param1, param2)
            rest = line[15:].strip()
            if '(' in rest:
                func_name = rest[:rest.index('(')]
                params_str = rest[rest.index('(')+1:rest.rindex(')')]
                return func_name, params_str
            else:
                return rest, ""
        elif line.startswith('FUNCTION '):
            # Format: FUNCTION func_name(params):
            rest = line[9:].rstrip(':')
            if '(' in rest:
                func_name = rest[:rest.index('(')]
                params_str = rest[rest.index('(')+1:rest.rindex(')')]
                return func_name, params_str
            else:
                return rest, ""
        return "unknown_function", ""
    
    def parse_function_body(self, lines, start_idx):
        """Parse function body until RETURN or END_FUNCTION"""
        commands = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i].strip()
            
            if (line == "RETURN_FUNCTION" or line == "RETURN" or 
                line == "END_FUNCTION" or line.startswith("END_FUNCTION")):
                break
                
            if line and not line.startswith('#'):
                commands.append(line.lstrip())
            i += 1
            
        return commands, i + 1

# ===== Telemetry State =====
telemetry_lock = threading.Lock()
t0 = time.time()
telemetry_times = deque(maxlen=5000)
pressure_vals   = deque(maxlen=5000)
flow_vals       = deque(maxlen=5000)
vhv_vals        = deque(maxlen=5000)
ihv_vals        = deque(maxlen=5000)

latest = {
    "P": None,      # pressure
    "FMFC": None,   # flow reading
    "VHV": None,    # HV voltage
    "IHV": None,    # HV current
    "T": None,      # ms since boot
}

stop_threads = False

def serial_reader():
    """Continuously read serial and parse telemetry"""
    while not stop_threads:
        try:
            if ser.in_waiting:
                line = ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                
                terminal_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], line])
                terminal_log_file.flush()
                
                if line.startswith("DATA:"):
                    try:
                        payload = line[5:]
                        parts = dict(pair.split('=') for pair in payload.split(','))
                        with telemetry_lock:
                            latest["T"] = int(parts.get('T', '0'))
                            latest["P"] = float(parts.get('P', 'nan'))
                            latest["FMFC"] = float(parts.get('FMFC', 'nan'))
                            latest["VHV"] = float(parts.get('VHV', 'nan'))
                            latest["IHV"] = float(parts.get('IHV', 'nan'))
                            
                            telemetry_times.append(time.time() - t0)
                            pressure_vals.append(latest["P"])
                            flow_vals.append(latest["FMFC"])
                            vhv_vals.append(latest["VHV"])
                            ihv_vals.append(latest["IHV"])
                    except Exception as pe:
                        program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "WARN", f"Parse error: {pe}"])
                        program_log_file.flush()
            else:
                time.sleep(0.01)
        except Exception as e:
            program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "ERROR", f"serial_reader: {e}"])
            program_log_file.flush()
            time.sleep(0.1)

# ===== GUI Setup =====
root = tk.Tk()
root.title("Fusor AutoRun V4 - Full Variable Support")

# Frames
left = ttk.Frame(root)
left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

right = ttk.Frame(root, width=420)
right.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)

# Plot figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 6), dpi=100)

# Plot 1: Pressure and Flow
line_pressure, = ax1.plot([], [], label="Pressure (torr)")
ax1.set_ylabel("Pressure (torr)")
ax1.set_xlim(0, PLOT_WINDOW_SECONDS)

ax1b = ax1.twinx()
line_flow, = ax1b.plot([], [], label="Flow (sccm)", color='orange')
ax1b.set_ylabel("Flow (sccm)")

# Plot 2: HV voltage and current
line_vhv, = ax2.plot([], [], label="HV Voltage (kV)")
line_ihv, = ax2.plot([], [], label="HV Current (mA)", color='red')
ax2.set_xlabel("Time (s)")
ax2.set_ylabel("HV")

# Legends
ax1.legend(loc="upper left")
ax1b.legend(loc="upper right")
ax2.legend(loc="upper left")

canvas = FigureCanvasTkAgg(fig, master=left)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Right-side controls and logs
controls_frame = ttk.LabelFrame(right, text="Controls")
controls_frame.pack(fill=tk.X, pady=4)

program_path_var = tk.StringVar(value="")
ttk.Entry(controls_frame, textvariable=program_path_var, width=38).grid(row=0, column=0, padx=4, pady=4)

def browse_program():
    path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Text", "*.txt"), ("All files","*.*")])
    if path:
        program_path_var.set(path)

ttk.Button(controls_frame, text="Browse", command=browse_program).grid(row=0, column=1, padx=4, pady=4)
ttk.Button(controls_frame, text="Run Program", command=lambda: start_program(program_path_var.get())).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
ttk.Button(controls_frame, text="Kill / Exit", command=lambda: safe_exit()).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
ttk.Button(controls_frame, text="Validate Program", command=lambda: validate_program(program_path_var.get())).grid(row=2, column=0, padx=4, pady=4, sticky="ew")

status_var = tk.StringVar(value="Idle")
ttk.Label(controls_frame, textvariable=status_var).grid(row=3, column=0, columnspan=2, padx=4, pady=4)

# Variable display frame
var_frame = ttk.LabelFrame(right, text="Variables")
var_frame.pack(fill=tk.X, pady=4)
var_text = tk.Text(var_frame, height=6, wrap="word", font=("Courier", 9))
var_text.pack(fill=tk.BOTH, expand=True)

# Program log
log_frame = ttk.LabelFrame(right, text="Program Log")
log_frame.pack(fill=tk.BOTH, expand=True, pady=6)
log_box = tk.Text(log_frame, height=15, wrap="word", font=("Courier", 9))
log_box.pack(fill=tk.BOTH, expand=True)

def log_event(event: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    program_log_writer.writerow([ts, "EVENT", event])
    program_log_file.flush()
    log_box.insert(tk.END, f"[{ts}] {event}\n")
    log_box.see(tk.END)

def update_variable_display(context):
    """Update variable display with current scope"""
    var_text.delete(1.0, tk.END)
    all_vars = context.current_scope.all_variables()
    
    if all_vars:
        var_text.insert(tk.END, "Current Variables:\n")
        for name, value in sorted(all_vars.items()):
            var_text.insert(tk.END, f"  {name} = {value}\n")
    else:
        var_text.insert(tk.END, "No variables defined")

# ===== Plot updater =====
def update_plots():
    try:
        with telemetry_lock:
            if len(telemetry_times) > 1:
                tmin = max(0, telemetry_times[-1] - PLOT_WINDOW_SECONDS)
                times = [t for t in telemetry_times if t >= tmin]
                pvals = list(pressure_vals)[-len(times):]
                fvals = list(flow_vals)[-len(times):]
                vvals = list(vhv_vals)[-len(times):]
                ivals = list(ihv_vals)[-len(times):]

                line_pressure.set_data(times, pvals)
                line_flow.set_data(times, fvals)
                line_vhv.set_data(times, vvals)
                line_ihv.set_data(times, ivals)

                ax1.set_xlim(max(0, times[0]) if times else 0, max(PLOT_WINDOW_SECONDS, times[-1]) if times else PLOT_WINDOW_SECONDS)
                if pvals:
                    ax1.set_ylim(0, max(1.0, max(pvals)*1.15))
                if fvals:
                    ax1b.set_ylim(0, max(10.0, max(fvals + [0.0])*1.2))
                if vvals:
                    ax2.set_ylim(0, max(10.0, max(vvals + [0.0])*1.2))

                canvas.draw()
    except Exception:
        pass
    root.after(100, update_plots)

# ===== Enhanced Program Loading =====
def load_program_text(path: str):
    """Load program text from CSV or text file"""
    program_lines = []
    
    if path.endswith('.csv'):
        try:
            with open(path, newline='') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            if not rows:
                return program_lines
            
            # Check for structured CSV from FusorProgramV7
            header_row = None
            data_start = 0
            
            for i, row in enumerate(rows):
                if any('Block_Type' in str(cell) or 'Command' in str(cell) for cell in row):
                    header_row = row
                    data_start = i + 1
                    break
            
            if header_row:
                # Find column indices
                command_col = -1
                for i, header in enumerate(header_row):
                    if 'Command' in str(header):
                        command_col = i
                        break
                
                if command_col >= 0:
                    # Extract commands
                    for row in rows[data_start:]:
                        if row and len(row) > command_col:
                            command = row[command_col].strip()
                            if command and not command.startswith('#'):
                                program_lines.append(command)
                    
                    return program_lines
            
            # Try simple CSV parsing
            for row in rows:
                if row and len(row) > 0:
                    for cell in row:
                        cell_str = str(cell).strip()
                        if any(cmd in cell_str for cmd in ['FUNCTION', 'WHILE', 'FOR', 'IF', 'CALL_FUNCTION',
                                                            'OPEN_', 'CLOSE_', 'SET_', 'DELAY', 
                                                            'WAIT', 'END_', 'SAFE_STATE', 'PUMP_', 'SET_VAR']):
                            if not cell_str.startswith('#'):
                                program_lines.append(cell_str)
                                break
                                
        except Exception as e:
            raise Exception(f"Failed to read CSV: {e}")
            
        return program_lines
    else:
        # Load from text file
        with open(path, 'r') as f:
            return [line.strip() for line in f.readlines()]

# ===== Validation =====
def validate_program(path: str):
    """Validate program structure before execution"""
    if not path or not os.path.exists(path):
        messagebox.showerror("Error", "Please select a valid program file.")
        return
    
    try:
        program_text = load_program_text(path)
        context = ProgramContext()
        parser = CommandParser(context)
        
        validation_results = []
        
        commands, functions, autorun_config = parser.parse_program_text(program_text)
        
        validation_results.append(f"Total lines: {len(program_text)}")
        validation_results.append(f"Main commands: {len(commands)}")
        validation_results.append(f"Functions defined: {len(functions)}")
        
        # Check function parameters
        for func_name, func_data in functions.items():
            if func_data.get("parameters"):
                validation_results.append(f"  • {func_name}({func_data['parameters']})")
            else:
                validation_results.append(f"  • {func_name}()")
        
        # Check for undefined function calls
        func_calls = [cmd for cmd in commands if cmd.startswith("CALL_FUNCTION")]
        for call_cmd in func_calls:
            parts = call_cmd.split(None, 1)
            if len(parts) > 1:
                func_call = parts[1]
                func_name = func_call.split('(')[0]
                if func_name not in functions and func_name not in autorun_config.get("function_maps", {}):
                    validation_results.append(f"WARNING: Undefined function: {func_name}")
        
        messagebox.showinfo("Validation Results", "\n".join(validation_results))
        
    except Exception as e:
        messagebox.showerror("Validation Error", f"Failed to validate: {e}")

# ===== Program Execution =====
exec_thread = None

def start_program(path: str):
    global exec_thread
    if not path or not os.path.exists(path):
        messagebox.showerror("Error", "Please select a valid program file.")
        return
    if exec_thread and exec_thread.is_alive():
        messagebox.showwarning("Busy", "Program is already running.")
        return
    exec_thread = threading.Thread(target=lambda: execute_enhanced_program(path), daemon=True)
    exec_thread.start()

def execute_enhanced_program(path: str):
    """Execute program with full variable support and nested external functions"""
    status_var.set("Running")
    log_event(f"Starting program V4: {path}")
    
    try:
        # Load and parse program
        program_text = load_program_text(path)
        context = ProgramContext()
        parser = CommandParser(context)
        
        commands, functions, autorun_config = parser.parse_program_text(program_text)
        
        # Load library paths first
        for lib_path in autorun_config.get("libraries", []):
            if os.path.exists(lib_path):
                context.library_manager.add_library_path(lib_path)
                log_event(f"Added library path: {lib_path}")
        
        # Load external function mappings
        external_loaded = set()  # Track loaded external functions
        functions_to_load = list(autorun_config.get("function_maps", {}).items())
        
        # Keep loading until all dependencies are resolved
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while functions_to_load and iteration < max_iterations:
            iteration += 1
            newly_loaded = []
            still_to_load = []
            
            for func_name, file_path in functions_to_load:
                if func_name not in external_loaded:
                    if os.path.exists(file_path):
                        # Load the external function file
                        func_text = load_program_text(file_path)
                        
                        # Parse the external function for nested dependencies
                        func_parser = CommandParser(context)
                        func_commands, nested_functions, nested_config = func_parser.parse_program_text(func_text)
                        
                        # If this is just commands (no function definition), treat as simple external
                        if not nested_functions:
                            context.define_function(func_name, "", func_commands)
                            log_event(f"Loaded external function: {func_name}")
                            external_loaded.add(func_name)
                            newly_loaded.append(func_name)
                        else:
                            # Load any nested function definitions
                            for nested_name, nested_data in nested_functions.items():
                                context.define_function(nested_name, nested_data["parameters"], nested_data["commands"])
                                log_event(f"Loaded nested function: {nested_name} from {func_name}")
                            
                            # The main commands become the function body
                            if func_commands:
                                context.define_function(func_name, "", func_commands)
                            
                            external_loaded.add(func_name)
                            newly_loaded.append(func_name)
                        
                        # Add any new external dependencies found
                        for nested_func, nested_path in nested_config.get("function_maps", {}).items():
                            if nested_func not in external_loaded and (nested_func, nested_path) not in still_to_load:
                                still_to_load.append((nested_func, nested_path))
                                log_event(f"Found nested dependency: {nested_func}")
                    else:
                        log_event(f"[WARN] External function file not found: {file_path}")
                        still_to_load.append((func_name, file_path))
            
            # Update the list for next iteration
            functions_to_load = still_to_load
            
            # If we didn't load anything new, break to prevent infinite loop
            if not newly_loaded and functions_to_load:
                log_event(f"[WARN] Could not resolve dependencies: {[f[0] for f in functions_to_load]}")
                break
        
        # Store internal function definitions with parameters
        for func_name, func_data in functions.items():
            context.define_function(func_name, func_data["parameters"], func_data["commands"])
            log_event(f"Defined function: {func_name}({func_data.get('parameters', '')})")
        
        log_event(f"Loaded {len(functions)} internal functions, {len(external_loaded)} external functions, {len(commands)} main commands")
        
        # Execute main program
        execute_command_list(commands, context)
        
    except Exception as e:
        log_event(f"[ERROR] Program failed: {e}")
        messagebox.showerror("Execution Error", f"Program failed: {e}")
    
    log_event("Program completed")
    status_var.set("Idle")
    update_variable_display(context)

def execute_command_list(commands, context: ProgramContext, depth=0):
    """Execute a list of commands with variable support"""
    if depth > 10:
        raise Exception("Maximum recursion depth exceeded")
    
    i = 0
    while i < len(commands) and not stop_threads and not context.execution_stopped:
        cmd = commands[i].strip()
        
        if not cmd or cmd.startswith('#'):
            i += 1
            continue
        
        # Substitute variables in the command
        cmd = substitute_variables(cmd, context.current_scope)
        
        try:
            # Handle variable assignment
            if cmd.startswith("SET_VAR"):
                execute_set_var(cmd, context)
                update_variable_display(context)
                i += 1
                continue
            
            # Handle function calls with arguments
            elif cmd.startswith("CALL_FUNCTION"):
                parts = cmd.split(None, 1)
                if len(parts) > 1:
                    func_call = parts[1]
                    
                    # Parse function name and arguments
                    if '(' in func_call:
                        func_name = func_call[:func_call.index('(')]
                        args_str = func_call[func_call.index('(')+1:func_call.rindex(')')]
                        
                        log_event(f"Calling function: {func_name}({args_str})")
                        
                        # Get function and execute with proper scope
                        try:
                            func_commands, func_scope = context.call_function(func_name, args_str)
                            
                            # Push function scope
                            context.push_scope(func_scope)
                            update_variable_display(context)
                            
                            # Execute function body
                            execute_command_list(func_commands, context, depth + 1)
                            
                            # Pop function scope
                            context.pop_scope()
                            update_variable_display(context)
                            
                            log_event(f"Function {func_name} completed")
                            
                        except Exception as fe:
                            log_event(f"[ERROR] Function call failed: {fe}")
                    else:
                        # No arguments
                        func_name = func_call
                        log_event(f"Calling function: {func_name}")
                        try:
                            func_commands, func_scope = context.call_function(func_name, "")
                            context.push_scope(func_scope)
                            execute_command_list(func_commands, context, depth + 1)
                            context.pop_scope()
                            update_variable_display(context)
                            log_event(f"Function {func_name} completed")
                        except Exception as fe:
                            log_event(f"[ERROR] Function call failed: {fe}")
                
                i += 1
                continue
            
            # Handle loop structures
            elif cmd.startswith(("WHILE", "FOR", "REPEAT")):
                loop_body, i = extract_loop_body(commands, i)
                execute_loop(cmd, loop_body, context, depth + 1)
                continue
                
            # Handle conditional structures  
            elif cmd.startswith("IF"):
                if_body, else_body, i = extract_conditional_body(commands, i)
                execute_conditional(cmd, if_body, else_body, context, depth + 1)
                continue
                
            # Handle basic commands
            else:
                execute_basic_command(cmd, context)
                i += 1
                
        except Exception as e:
            log_event(f"[ERROR] executing '{cmd}': {e}")
            i += 1

def execute_set_var(cmd, context):
    """Execute SET_VAR command"""
    # Format: SET_VAR name=value
    rest = cmd[7:].strip()
    if '=' in rest:
        var_name, var_value = rest.split('=', 1)
        var_name = var_name.strip()
        var_value = var_value.strip()
        
        # Evaluate the value
        evaluated_value = evaluate_expression(var_value, context.current_scope)
        context.current_scope.set(var_name, evaluated_value)
        
        log_event(f"Set variable: {var_name} = {evaluated_value}")

def extract_loop_body(commands, start_idx):
    """Extract loop body commands until END_LOOP"""
    body_commands = []
    i = start_idx + 1
    loop_depth = 1
    
    while i < len(commands) and loop_depth > 0:
        cmd = commands[i].strip()
        
        if cmd.startswith(("WHILE", "FOR", "REPEAT")):
            loop_depth += 1
        elif cmd == "END_LOOP":
            loop_depth -= 1
            
        if loop_depth > 0:
            body_commands.append(cmd)
            
        i += 1
    
    return body_commands, i

def extract_conditional_body(commands, start_idx):
    """Extract if/else body commands until END_IF"""
    if_commands = []
    else_commands = []
    i = start_idx + 1
    if_depth = 1
    in_else = False
    
    while i < len(commands) and if_depth > 0:
        cmd = commands[i].strip()
        
        if cmd.startswith("IF"):
            if_depth += 1
        elif cmd == "END_IF":
            if_depth -= 1
        elif cmd == "ELSE" and if_depth == 1:
            in_else = True
            i += 1
            continue
            
        if if_depth > 0:
            if in_else:
                else_commands.append(cmd)
            else:
                if_commands.append(cmd)
                
        i += 1
    
    return if_commands, else_commands, i

def execute_loop(loop_cmd, body_commands, context: ProgramContext, depth):
    """Execute loop with variable support"""
    log_event(f"Starting loop: {loop_cmd}")
    
    # Substitute variables in loop command
    loop_cmd = substitute_variables(loop_cmd, context.current_scope)
    
    if loop_cmd.startswith("WHILE"):
        # Parse WHILE condition
        condition_expr = loop_cmd[5:].strip()
        iteration = 0
        max_iterations = 10000
        
        while iteration < max_iterations and not stop_threads:
            # Evaluate condition with current variables
            if not evaluate_condition(condition_expr, context.current_scope):
                break
            
            log_event(f"Loop iteration {iteration + 1}")
            execute_command_list(body_commands, context, depth)
            
            if context.execution_stopped:
                break
                
            iteration += 1
            time.sleep(0.01)
            
        if iteration >= max_iterations:
            log_event("[WARN] Loop reached maximum iterations")
    
    elif loop_cmd.startswith("FOR"):
        # Parse FOR loop: FOR var FROM start TO end
        parts = loop_cmd[3:].split()
        if len(parts) >= 5 and parts[1] == "FROM" and parts[3] == "TO":
            var_name = parts[0]
            start_val = evaluate_expression(parts[2], context.current_scope)
            end_val = evaluate_expression(parts[4], context.current_scope)
            
            # Create loop variable in current scope
            for i in range(int(start_val), int(end_val) + 1):
                context.current_scope.set(var_name, i)
                update_variable_display(context)
                
                log_event(f"Loop iteration: {var_name} = {i}")
                execute_command_list(body_commands, context, depth)
                
                if context.execution_stopped or stop_threads:
                    break
                    
                time.sleep(0.01)
    
    elif loop_cmd.startswith("REPEAT"):
        # Parse REPEAT n TIMES
        parts = loop_cmd[6:].split()
        if parts and parts[-1] == "TIMES":
            count = evaluate_expression(parts[0], context.current_scope)
            
            for i in range(int(count)):
                log_event(f"Repeat iteration {i + 1}/{int(count)}")
                execute_command_list(body_commands, context, depth)
                
                if context.execution_stopped or stop_threads:
                    break
                    
                time.sleep(0.01)
    
    log_event("Loop completed")

def execute_conditional(if_cmd, if_commands, else_commands, context: ProgramContext, depth):
    """Execute conditional with variable support"""
    # Substitute variables in condition
    if_cmd = substitute_variables(if_cmd, context.current_scope)
    condition_expr = if_cmd[2:].strip()
    
    if evaluate_condition(condition_expr, context.current_scope):
        log_event(f"Condition TRUE: {condition_expr}")
        if if_commands:
            execute_command_list(if_commands, context, depth)
    else:
        log_event(f"Condition FALSE: {condition_expr}")
        if else_commands:
            execute_command_list(else_commands, context, depth)

def evaluate_condition(condition_expr, scope):
    """Evaluate a condition expression with variable support"""
    try:
        # Substitute variables first
        condition_expr = substitute_variables(condition_expr, scope)
        condition_expr = condition_expr.replace(" ", "")
        
        # Map condition variables to telemetry keys
        if condition_expr.upper().startswith("PRESSURE"):
            key = "P"
            rest = condition_expr[8:]
        elif condition_expr.upper().startswith("FLOW"):
            key = "FMFC" 
            rest = condition_expr[4:]
        elif condition_expr.upper().startswith("VHV") or condition_expr.upper().startswith("HV_VOLTAGE"):
            key = "VHV"
            rest = condition_expr[3:] if condition_expr.upper().startswith("VHV") else condition_expr[10:]
        elif condition_expr.upper().startswith("IHV") or condition_expr.upper().startswith("HV_CURRENT"):
            key = "IHV"
            rest = condition_expr[3:] if condition_expr.upper().startswith("IHV") else condition_expr[10:]
        else:
            return False
            
        # Extract operator and value
        op = None
        for candidate in ["<=", ">=", "==", "!=", "<", ">"]:
            if candidate in rest:
                op = candidate
                break
                
        if not op:
            return False
            
        threshold = evaluate_expression(rest.split(op)[1], scope)
        
        # Get current value
        with telemetry_lock:
            current_val = latest.get(key)
            
        if current_val is None:
            return False
            
        # Evaluate condition
        if op == "<": return current_val < threshold
        if op == ">": return current_val > threshold  
        if op == "<=": return current_val <= threshold
        if op == ">=": return current_val >= threshold
        if op == "==": return abs(current_val - threshold) < 1e-6
        if op == "!=": return abs(current_val - threshold) >= 1e-6
        
        return False
        
    except Exception as e:
        log_event(f"[WARN] Condition evaluation error: {e}")
        return False

def execute_basic_command(cmd, context):
    """Execute a basic hardware command with variable substitution"""
    try:
        # Substitute variables in command
        cmd = substitute_variables(cmd, context.current_scope)
        
        if cmd in ("OPEN_FUEL_VALVE", "CLOSE_FUEL_VALVE", "OPEN_VACUUM_VALVE", "CLOSE_VACUUM_VALVE"):
            mapping = {
                "OPEN_FUEL_VALVE":   "FUEL_OPEN",
                "CLOSE_FUEL_VALVE":  "FUEL_CLOSE", 
                "OPEN_VACUUM_VALVE": "VACUUM_OPEN",
                "CLOSE_VACUUM_VALVE":"VACUUM_CLOSE",
            }
            send = mapping[cmd]
            log_event(f"Send {send}")
            send_command(send)

        elif cmd.startswith("SET_MFC"):
            # Accept both "SET_MFC 12.3" or "SET_MFC:12.3" formats
            if ':' in cmd:
                val = evaluate_expression(cmd.split(':')[1], context.current_scope)
            else:
                parts = cmd.split()
                val = evaluate_expression(parts[1], context.current_scope) if len(parts) > 1 else 0.0
            send = f"SET_MFC:{float(val):.1f}"
            log_event(f"Send {send}")
            send_command(send)

        elif cmd.startswith("SET_HV"):
            parts = cmd.split()
            voltage = evaluate_expression(parts[1], context.current_scope) if len(parts) > 1 else 0.0
            send = f"SET_HV:{float(voltage):.1f}"
            log_event(f"Send {send}")
            send_command(send)

        elif cmd.startswith("PUMP_"):
            if cmd == "PUMP_ON":
                send = "PUMP_ON"
            elif cmd == "PUMP_OFF":
                send = "PUMP_OFF"
            else:
                send = cmd
            log_event(f"Send {send}")
            send_command(send)

        elif cmd.startswith("DELAY"):
            parts = cmd.split()
            duration = evaluate_expression(parts[1], context.current_scope) if len(parts) > 1 else 0.0
            log_event(f"Delay {float(duration)} s")
            t_end = time.time() + float(duration)
            while not stop_threads and time.time() < t_end:
                time.sleep(0.05)

        elif cmd.startswith("WAIT"):
            execute_wait_command(cmd, context)

        elif cmd == "SAFE_STATE":
            log_event("Send SAFE_STATE")
            send_command("SAFE_STATE")

        else:
            # Unknown command - log but don't error
            log_event(f"[INFO] Skipping non-hardware command: {cmd}")

    except Exception as e:
        log_event(f"[ERROR] executing basic command '{cmd}': {e}")

def execute_wait_command(cmd, context):
    """Execute WAIT command with variable support"""
    try:
        # Substitute variables
        cmd = substitute_variables(cmd, context.current_scope)
        
        expr = cmd[5:].strip() if cmd.startswith("WAIT ") else cmd[4:].strip()
        condition_expr = expr.replace(" ", "")
        
        # Parse condition (same as evaluate_condition)
        if condition_expr.upper().startswith("PRESSURE"):
            key = "P"
            rest = condition_expr[8:]
        elif condition_expr.upper().startswith("FLOW"):
            key = "FMFC"
            rest = condition_expr[4:]
        elif condition_expr.upper().startswith("HV_VOLTAGE"):
            key = "VHV"
            rest = condition_expr[10:]
        elif condition_expr.upper().startswith("HV_CURRENT"):
            key = "IHV"
            rest = condition_expr[10:]
        elif condition_expr.upper().startswith("VHV"):
            key = "VHV"
            rest = condition_expr[3:]
        elif condition_expr.upper().startswith("IHV"):
            key = "IHV"
            rest = condition_expr[3:]
        else:
            raise ValueError(f"Unknown WAIT variable in: {cmd}")
            
        # Extract operator and threshold
        op = None
        for candidate in ["<=", ">=", "==", "!=", "<", ">"]:
            if candidate in rest:
                op = candidate
                break
                
        if not op:
            raise ValueError(f"No operator found in WAIT: {cmd}")
            
        threshold = evaluate_expression(rest.split(op)[1], context.current_scope)
        log_event(f"Wait until {key} {op} {threshold}")
        
        def satisfied(val):
            if val is None:
                return False
            if op == "<": return val < threshold
            if op == ">": return val > threshold
            if op == "<=": return val <= threshold
            if op == ">=": return val >= threshold
            if op == "==": return abs(val - threshold) < 1e-6
            if op == "!=": return abs(val - threshold) >= 1e-6
            return False

        # Wait for condition
        start_time = time.time()
        timeout = 300  # 5 minute timeout
        
        while not stop_threads and (time.time() - start_time) < timeout:
            with telemetry_lock:
                val = latest.get(key)
            if satisfied(val):
                log_event(f"Condition met: {key}={val:.2f} (target: {op}{threshold})")
                return
            time.sleep(0.1)
            
        if (time.time() - start_time) >= timeout:
            log_event(f"[WARN] WAIT condition timeout after {timeout}s: {cmd}")
        
    except Exception as werr:
        log_event(f"[WARN] WAIT parse error: {werr} | '{cmd}'")

def safe_exit():
    global stop_threads
    try:
        stop_threads = True
        
        try:
            send_command("SAFE_STATE")
            time.sleep(0.1)
        except Exception:
            pass
            
        if ser and ser.is_open:
            ser.close()
    finally:
        try:
            terminal_log_file.close()
        except Exception:
            pass
        try:
            program_log_file.close()
        except Exception:
            pass
        root.quit()

# Start serial reader thread
reader_thread = threading.Thread(target=serial_reader, daemon=True)
reader_thread.start()

# Start plot updater
update_plots()

# Handle window close
root.protocol("WM_DELETE_WINDOW", safe_exit)

def main_cli_override():
    # Allow CLI overrides for serial port and program path
    args = sys.argv[1:]
    if len(args) >= 1:
        global ser
        try:
            port = args[0]
            if port:
                ser.close()
                time.sleep(0.1)
                globals()['SERIAL_PORT'] = port
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                print(f"[INFO] Using serial port: {SERIAL_PORT}")
        except Exception as e:
            print(f"[WARN] Failed to switch serial port: {e}")
    if len(args) >= 2:
        program_path = args[1]
        if os.path.exists(program_path):
            program_path_var.set(program_path)
            print(f"[INFO] Loaded program: {program_path}")

if __name__ == "__main__":
    main_cli_override()
    print("[INFO] FusorAutoRun V4 started - Full variable support enabled")
    root.mainloop()