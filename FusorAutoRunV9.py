#!/usr/bin/env python3
"""
FusorAutoRun.py - Version 9
---------------------------
Execute FusorProgram-generated CSV/JSON command files with full variable and parameter support.

New in V9:
- Full JSON file support for FusorProgramV8 exports
- Nested external function loading with dependency resolution
- Enhanced debug output for troubleshooting
- Complete variable substitution in all numeric fields
- Function parameters with proper scoping
- Variable assignment and tracking
- Runtime expression evaluation
- TEST MODE for hardware-free testing

Compatible with FusorProgramV8 output format (JSON and CSV).
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
import json

# Matplotlib for live plots
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# ===== EARLY CLI PROCESSING =====
def process_cli_args():
    """Process CLI arguments before any hardware initialization"""
    global TEST_MODE
    TEST_MODE = False
    
    args = sys.argv[1:]
    if "--test" in args:
        TEST_MODE = True
        args.remove("--test")
        print("[INFO] Test mode enabled via command line")
    
    return args

# Process CLI args immediately
remaining_args = process_cli_args()

# ===== CONFIG =====
SERIAL_PORT = '/dev/cu.usbmodem1301'
BAUD_RATE   = 9600
PLOT_WINDOW_SECONDS = 120

# ===== Test Mode Configuration =====
simulated_pressure = 100.0
simulated_flow = 0.0
simulated_vhv = 0.0
simulated_ihv = 0.0

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
print(f"[INFO] FusorAutoRun V9 - Full JSON/CSV Support Enabled")

# ===== Serial Setup (Completely Deferred) =====
ser = None

def initialize_serial():
    """Initialize serial connection based on test mode setting"""
    global ser, TEST_MODE
    
    if TEST_MODE:
        print("[INFO] TEST MODE - No hardware connection")
        return
        
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[INFO] Connected to hardware on {SERIAL_PORT}")
    except Exception as e:
        print(f"[WARN] Failed to connect to {SERIAL_PORT}: {e}")
        print(f"[INFO] Falling back to TEST MODE")
        TEST_MODE = True

def send_command(cmd: str):
    """Send a single command string over serial or simulate in test mode."""
    global simulated_pressure, simulated_flow, simulated_vhv, simulated_ihv
    
    try:
        if TEST_MODE:
            # Simulate hardware responses
            response = simulate_hardware_command(cmd)
            if response:
                # Log simulated response
                terminal_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], f"SIM_RESPONSE: {response}"])
        else:
            # Real hardware communication
            if ser and ser.is_open:
                ser.write((cmd + "\n").encode())
            else:
                program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "ERROR", "Serial port not available"])
                
        program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "Send:", f"{cmd} {'[SIMULATED]' if TEST_MODE else ''}"])
        program_log_file.flush()
        
    except Exception as e:
        program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "ERROR", f"send_command: {e}"])
        program_log_file.flush()

def simulate_hardware_command(cmd: str):
    """Simulate hardware responses for test mode"""
    global simulated_pressure, simulated_flow, simulated_vhv, simulated_ihv
    
    if cmd.startswith("SET_MFC:"):
        try:
            setpoint = float(cmd.split(':')[1])
            # Simulate flow response (simplified physics)
            simulated_flow = setpoint * 0.8 + (setpoint * 0.4 * (time.time() % 1))  # Some variation
            return f"MFC set to {setpoint}%"
        except:
            pass
    
    elif cmd.startswith("SET_HV:"):
        try:
            voltage = float(cmd.split(':')[1])
            # Simulate HV response
            simulated_vhv = voltage * 0.9 + (voltage * 0.1 * (time.time() % 1))  # Some variation
            simulated_ihv = voltage * 0.01 if voltage > 0 else 0  # Simple current relationship
            return f"HV set to {voltage}kV"
        except:
            pass
    
    elif cmd == "FUEL_OPEN":
        simulated_pressure += 50  # Pressure rises when fuel opens
        return "Fuel valve opened"
        
    elif cmd == "FUEL_CLOSE":
        simulated_pressure = max(0, simulated_pressure - 20)  # Pressure drops
        return "Fuel valve closed"
        
    elif cmd == "VACUUM_OPEN":
        simulated_pressure = max(0, simulated_pressure - 30)  # Vacuum lowers pressure
        return "Vacuum valve opened"
        
    elif cmd == "VACUUM_CLOSE":
        simulated_pressure += 10  # Less pumping, pressure rises
        return "Vacuum valve closed"
        
    elif cmd == "PUMP_ON":
        simulated_pressure = max(0, simulated_pressure - 40)  # Pumping lowers pressure
        return "Pump started"
        
    elif cmd == "PUMP_OFF":
        simulated_pressure += 20  # No pumping, pressure rises
        return "Pump stopped"
        
    elif cmd == "SAFE_STATE":
        simulated_pressure = 100.0
        simulated_flow = 0.0
        simulated_vhv = 0.0
        simulated_ihv = 0.0
        return "System in safe state"
    
    return None

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

# ===== JSON Support Functions =====
def load_program_from_json(json_path):
    """Load program from JSON file exported by FusorProgramV8"""
    try:
        with open(json_path, 'r') as f:
            program_data = json.load(f)
            
        print(f"[DEBUG] JSON loaded with keys: {list(program_data.keys())}")
        
        # Extract external function mappings from blocks
        external_functions = {}
        library_paths = program_data.get("function_libraries", [])
        
        # Find external function calls in blocks
        for block_data in program_data.get("blocks", []):
            if (block_data.get("type") == "function_call" and 
                block_data.get("is_external_function", False)):
                
                func_name = block_data["parameters"].get("function_name")
                func_path = block_data.get("function_file_path")
                
                if func_name and func_path:
                    external_functions[func_name] = func_path
                    print(f"[DEBUG] Found external function: {func_name} -> {func_path}")
        
        # Convert blocks to command lines
        program_lines = convert_json_blocks_to_commands(program_data.get("blocks", []))
        
        print(f"[DEBUG] Converted {len(program_lines)} command lines from JSON")
        
        return program_lines, external_functions, library_paths
        
    except Exception as e:
        print(f"[ERROR] Failed to load JSON: {e}")
        raise

def convert_json_blocks_to_commands(blocks):
    """Convert JSON block data to executable command lines"""
    commands = []
    
    # Sort blocks by position (top to bottom, left to right)
    sorted_blocks = sorted(blocks, key=lambda b: (b["y"], b["x"]))
    
    for block_data in sorted_blocks:
        block_type = block_data["type"]
        params = block_data["parameters"]
        
        # Convert block to command based on type
        if block_type == "start":
            commands.append("# START")
            
        elif block_type == "variable_define":
            var_name = params.get("var_name", "myVar")
            var_value = params.get("var_value", "0")
            commands.append(f"SET_VAR {var_name}={var_value}")
            
        elif block_type == "valve_control":
            valve = params.get("valve", "fuel")
            state = params.get("state", "open")
            action = "OPEN" if state == "open" else "CLOSE"
            commands.append(f"{action}_{valve.upper()}_VALVE")
            
        elif block_type == "delay":
            duration = params.get("duration", 1.0)
            commands.append(f"DELAY {duration}")
            
        elif block_type == "hv_control":
            voltage = params.get("voltage", 0)
            commands.append(f"SET_HV {voltage}")
            
        elif block_type == "pump_control":
            state = params.get("state", "on")
            commands.append(f"PUMP_{'ON' if state == 'on' else 'OFF'}")
            
        elif block_type == "mfc_control":
            setpoint = params.get("setpoint", 0)
            commands.append(f"SET_MFC {setpoint}")
            
        elif block_type == "wait_condition":
            condition = params.get("condition", "pressure")
            operator = params.get("operator", "<")
            value = params.get("value", 100)
            commands.append(f"WAIT {condition.upper()}{operator}{value}")
            
        elif block_type == "safe_state":
            commands.append("SAFE_STATE")
            
        elif block_type == "comment":
            text = params.get("text", "Comment")
            commands.append(f"# {text}")
            
        elif block_type == "function_call":
            func_name = params.get("function_name", "my_function")
            args = params.get("arguments", "")
            if args:
                commands.append(f"CALL_FUNCTION {func_name}({args})")
            else:
                commands.append(f"CALL_FUNCTION {func_name}()")
                
        elif block_type == "function_define":
            func_name = params.get("function_name", "my_function")
            func_params = params.get("function_parameters", "")
            if func_params:
                commands.append(f"DEFINE_FUNCTION {func_name}({func_params})")
            else:
                commands.append(f"DEFINE_FUNCTION {func_name}")
            
        elif block_type == "function_return":
            commands.append("RETURN_FUNCTION")
            
        elif block_type == "loop_start":
            loop_type = params.get("loop_type", "while")
            if loop_type == "while":
                condition = params.get("condition", "pressure")
                operator = params.get("operator", "<")
                value = params.get("value", 100)
                commands.append(f"WHILE {condition.upper()}{operator}{value}")
            elif loop_type == "for":
                var_name = params.get("var_name", "i")
                start_val = params.get("start_value", 0)
                end_val = params.get("end_value", 10)
                commands.append(f"FOR {var_name} FROM {start_val} TO {end_val}")
            elif loop_type == "repeat":
                count = params.get("repeat_count", 5)
                commands.append(f"REPEAT {count} TIMES")
                
        elif block_type == "loop_end":
            commands.append("END_LOOP")
            
        elif block_type == "conditional":
            condition = params.get("condition", "pressure")
            operator = params.get("operator", "<")
            value = params.get("value", 100)
            commands.append(f"IF {condition.upper()}{operator}{value}")
            
        elif block_type == "else_block":
            commands.append("ELSE")
            
        elif block_type == "endif_block":
            commands.append("END_IF")
            
        elif block_type == "end":
            commands.append("# END")
    
    return commands

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
    """Continuously read serial and parse telemetry, or simulate in test mode"""
    global simulated_pressure, simulated_flow, simulated_vhv, simulated_ihv
    
    while not stop_threads:
        try:
            if TEST_MODE:
                # Simulate telemetry data
                time.sleep(0.1)  # 10Hz update rate
                
                # Add some realistic variations and drift
                time_factor = time.time() * 0.1
                
                # Pressure naturally drifts
                simulated_pressure += (50 - simulated_pressure) * 0.001  # Slow drift toward 50
                simulated_pressure += 0.5 * (time.time() % 1 - 0.5)  # Small random variation
                simulated_pressure = max(0, simulated_pressure)
                
                # Flow follows MFC setting with some lag
                simulated_flow = max(0, simulated_flow * 0.99)  # Decay if no input
                
                # HV decays without input
                simulated_vhv = max(0, simulated_vhv * 0.995)
                simulated_ihv = max(0, simulated_ihv * 0.995)
                
                # Create simulated DATA line
                simulated_line = f"DATA:T={int(time.time()*1000)%1000000},P={simulated_pressure:.2f},FMFC={simulated_flow:.2f},VHV={simulated_vhv:.2f},IHV={simulated_ihv:.3f}"
                
                # Process the simulated line
                terminal_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], f"SIM:{simulated_line}"])
                terminal_log_file.flush()
                
                # Parse simulated telemetry
                try:
                    payload = simulated_line[5:]  # Remove "DATA:"
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
                    program_log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f")[:-3], "WARN", f"Simulated parse error: {pe}"])
                    program_log_file.flush()
                    
            else:
                # Real hardware communication
                if ser and ser.in_waiting:
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
root.title("Fusor AutoRun V9 - Full JSON/CSV Variable Support")

def update_title():
    """Update window title based on test mode"""
    mode_text = " [TEST MODE]" if TEST_MODE else " [HARDWARE]"
    root.title(f"Fusor AutoRun V9 - Full JSON/CSV Variable Support{mode_text}")

update_title()

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

# Test mode control
test_frame = ttk.Frame(controls_frame)
test_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

test_mode_var = tk.BooleanVar(value=TEST_MODE)

def toggle_test_mode():
    global TEST_MODE, ser
    TEST_MODE = test_mode_var.get()
    
    if TEST_MODE:
        # Switch to test mode
        if ser and ser.is_open:
            try:
                ser.close()
            except:
                pass
        ser = None
        status_var.set("Test Mode")
        log_event("Switched to TEST MODE - Hardware simulation enabled")
    else:
        # Switch to hardware mode
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            status_var.set("Hardware Mode")
            log_event(f"Switched to HARDWARE MODE - Connected to {SERIAL_PORT}")
        except Exception as e:
            messagebox.showerror("Hardware Error", f"Failed to connect to {SERIAL_PORT}: {e}\nStaying in test mode.")
            test_mode_var.set(True)
            TEST_MODE = True
            status_var.set("Test Mode (Hardware Unavailable)")
    
    update_title()
    update_status_color()

test_mode_check = ttk.Checkbutton(
    test_frame, 
    text="Test Mode (No Hardware)", 
    variable=test_mode_var,
    command=toggle_test_mode
)
test_mode_check.pack(side="left")

# Simulation controls (only visible in test mode)
sim_frame = ttk.Frame(controls_frame)
sim_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=2)

def update_simulation_controls():
    """Show/hide simulation controls based on test mode"""
    if TEST_MODE:
        # Show simulation controls
        ttk.Label(sim_frame, text="Simulation:", font=("Arial", 8)).pack(side="left")
        
        sim_pressure_var = tk.DoubleVar(value=simulated_pressure)
        ttk.Label(sim_frame, text="P:", font=("Arial", 8)).pack(side="left", padx=(10,0))
        pressure_spinbox = ttk.Spinbox(sim_frame, from_=0, to=1000, width=6, 
                                     textvariable=sim_pressure_var, increment=10)
        pressure_spinbox.pack(side="left", padx=(2,5))
        
        def update_sim_pressure():
            global simulated_pressure
            simulated_pressure = sim_pressure_var.get()
        
        sim_pressure_var.trace("w", lambda *args: update_sim_pressure())
        
        # Reset simulation button
        def reset_simulation():
            global simulated_pressure, simulated_flow, simulated_vhv, simulated_ihv
            simulated_pressure = 100.0
            simulated_flow = 0.0
            simulated_vhv = 0.0
            simulated_ihv = 0.0
            sim_pressure_var.set(100.0)
            log_event("Simulation reset to defaults")
        
        ttk.Button(sim_frame, text="Reset Sim", command=reset_simulation, width=8).pack(side="right")
    else:
        # Hide simulation controls
        for widget in sim_frame.winfo_children():
            widget.destroy()

# Initial setup of simulation controls
update_simulation_controls()

# Update simulation controls when test mode changes
original_toggle = toggle_test_mode
def enhanced_toggle_test_mode():
    original_toggle()
    update_simulation_controls()

test_mode_check.configure(command=enhanced_toggle_test_mode)

program_path_var = tk.StringVar(value="")
ttk.Entry(controls_frame, textvariable=program_path_var, width=38).grid(row=2, column=0, padx=4, pady=4)

def browse_program():
    try:
        # Use simpler file type specification for macOS compatibility
        path = filedialog.askopenfilename(
            filetypes=[
                ("JSON files", "*.json"),
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        if path:
            program_path_var.set(path)
    except Exception as e:
        # Fallback if file dialog fails
        print(f"[ERROR] File dialog failed: {e}")
        # Try without filetypes parameter as last resort
        try:
            path = filedialog.askopenfilename()
            if path:
                program_path_var.set(path)
        except:
            messagebox.showerror("Error", "File browser failed. Please type the file path manually.")

ttk.Button(controls_frame, text="Browse", command=browse_program).grid(row=2, column=1, padx=4, pady=4)
ttk.Button(controls_frame, text="Run Program", command=lambda: start_program(program_path_var.get())).grid(row=3, column=0, padx=4, pady=4, sticky="ew")
ttk.Button(controls_frame, text="Kill / Exit", command=lambda: safe_exit()).grid(row=3, column=1, padx=4, pady=4, sticky="ew")
ttk.Button(controls_frame, text="Validate Program", command=lambda: validate_program(program_path_var.get())).grid(row=4, column=0, padx=4, pady=4, sticky="ew")

status_var = tk.StringVar(value="Test Mode" if TEST_MODE else "Idle")
status_label = ttk.Label(controls_frame, textvariable=status_var)
status_label.grid(row=4, column=1, padx=4, pady=4)

# Add test status indicator
def update_status_color():
    """Update status label color based on mode"""
    if TEST_MODE:
        status_label.configure(foreground="blue")
    else:
        status_label.configure(foreground="green")

update_status_color()

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
    """Load program text from JSON, CSV, or text file"""
    program_lines = []
    
    print(f"[DEBUG] Loading file: {path}")
    
    if path.endswith('.json'):
        try:
            # Load JSON file
            program_lines, external_functions, library_paths = load_program_from_json(path)
            
            # Create autorun config sections
            autorun_lines = []
            
            # Add library paths if any
            if library_paths:
                autorun_lines.append("# [AUTORUN:LIBRARIES]")
                for lib_path in library_paths:
                    autorun_lines.append(f"# LIBRARY_PATH={lib_path}")
                autorun_lines.append("# [/AUTORUN:LIBRARIES]")
            
            # Add external function mappings
            if external_functions:
                autorun_lines.append("# [AUTORUN:EXTERNAL_FUNCTIONS]")
                for func_name, func_path in external_functions.items():
                    autorun_lines.append(f"# FUNCTION_MAP={func_name}:{func_path}")
                autorun_lines.append("# [/AUTORUN:EXTERNAL_FUNCTIONS]")
            
            # Combine autorun config with program lines
            program_lines = autorun_lines + program_lines
            
            print(f"[DEBUG] JSON loaded: {len(program_lines)} lines, {len(external_functions)} external functions")
            
        except Exception as e:
            print(f"[ERROR] Failed to load JSON: {e}")
            raise Exception(f"Failed to read JSON: {e}")
            
    elif path.endswith('.csv'):
        try:
            with open(path, newline='') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            if not rows:
                return program_lines
            
            print(f"[DEBUG] CSV has {len(rows)} rows")
            
            # Check for structured CSV from FusorProgramV8
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
                    
                    print(f"[DEBUG] Extracted {len(program_lines)} commands from structured CSV")
                    return program_lines
            
            # Try simple CSV parsing - each row is a command
            for row in rows:
                if row and len(row) > 0:
                    for cell in row:
                        cell_str = str(cell).strip()
                        if cell_str:  # Non-empty line
                            program_lines.append(cell_str)
                            break  # Only take first cell per row
                            
            print(f"[DEBUG] Simple CSV parsing: {len(program_lines)} lines")
                                
        except Exception as e:
            print(f"[ERROR] Failed to read CSV: {e}")
            raise Exception(f"Failed to read CSV: {e}")
            
    else:
        # Load from text file
        try:
            with open(path, 'r') as f:
                program_lines = [line.strip() for line in f.readlines()]
            print(f"[DEBUG] Text file loaded: {len(program_lines)} lines")
        except Exception as e:
            print(f"[ERROR] Failed to read text file: {e}")
            raise Exception(f"Failed to read text file: {e}")
            
    return program_lines

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
        
        validation_results.append(f"File type: {path.split('.')[-1].upper()}")
        validation_results.append(f"Total lines: {len(program_text)}")
        validation_results.append(f"Main commands: {len(commands)}")
        validation_results.append(f"Functions defined: {len(functions)}")
        
        # Check function parameters
        for func_name, func_data in functions.items():
            if func_data.get("parameters"):
                validation_results.append(f"  • {func_name}({func_data['parameters']})")
            else:
                validation_results.append(f"  • {func_name}()")
        
        # Check external function mappings
        external_funcs = autorun_config.get("function_maps", {})
        if external_funcs:
            validation_results.append(f"External functions: {len(external_funcs)}")
            for func_name, func_path in external_funcs.items():
                exists = "✓" if os.path.exists(func_path) else "✗"
                validation_results.append(f"  {exists} {func_name} -> {os.path.basename(func_path)}")
        
        # Check for undefined function calls
        func_calls = [cmd for cmd in commands if cmd.startswith("CALL_FUNCTION")]
        for call_cmd in func_calls:
            parts = call_cmd.split(None, 1)
            if len(parts) > 1:
                func_call = parts[1]
                func_name = func_call.split('(')[0]
                if func_name not in functions and func_name not in external_funcs:
                    validation_results.append(f"WARNING: Undefined function: {func_name}")
        
        messagebox.showinfo("Validation Results", "\n".join(validation_results))
        
    except Exception as e:
        messagebox.showerror("Validation Error", f"Failed to validate: {e}")

# ===== Program Execution Functions =====
def execute_enhanced_program(path: str):
    """Execute program with full variable support and nested external functions"""
    status_var.set("Running")
    log_event(f"Starting program V9: {path}")
    
    try:
        # Load and parse program
        program_text = load_program_text(path)
        context = ProgramContext()
        parser = CommandParser(context)
        
        commands, functions, autorun_config = parser.parse_program_text(program_text)
        
        log_event(f"Parsed {len(commands)} commands, {len(functions)} functions")
        
        # Load library paths first
        for lib_path in autorun_config.get("libraries", []):
            if os.path.exists(lib_path):
                context.library_manager.add_library_path(lib_path)
                log_event(f"Added library path: {lib_path}")
        
        # Load external function mappings with dependency resolution
        external_loaded = set()
        functions_to_load = list(autorun_config.get("function_maps", {}).items())
        
        # Keep loading until all dependencies are resolved
        max_iterations = 10
        iteration = 0
        
        while functions_to_load and iteration < max_iterations:
            iteration += 1
            newly_loaded = []
            still_to_load = []
            
            for func_name, file_path in functions_to_load:
                if func_name not in external_loaded:
                    if os.path.exists(file_path):
                        try:
                            if context.library_manager.load_function_mapping(func_name, file_path):
                                log_event(f"Loaded external function: {func_name}")
                                external_loaded.add(func_name)
                                newly_loaded.append(func_name)
                            else:
                                log_event(f"[WARN] Failed to load external function: {func_name}")
                                still_to_load.append((func_name, file_path))
                        except Exception as e:
                            log_event(f"[ERROR] Loading {func_name}: {e}")
                            still_to_load.append((func_name, file_path))
                    else:
                        log_event(f"[WARN] External function file not found: {file_path}")
                        still_to_load.append((func_name, file_path))
            
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
    status_var.set("Test Mode" if TEST_MODE else "Idle")
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
        
        # Parse condition 
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

def safe_exit():
    global stop_threads
    try:
        stop_threads = True
        
        try:
            if not TEST_MODE:
                send_command("SAFE_STATE")
                time.sleep(0.1)
        except Exception:
            pass
            
        if ser and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass
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

# ===== INITIALIZE AFTER CLI PROCESSING =====
# Now initialize serial after CLI args have been processed
initialize_serial()

# Start serial reader thread
reader_thread = threading.Thread(target=serial_reader, daemon=True)
reader_thread.start()

# Start plot updater
update_plots()

# Handle window close
root.protocol("WM_DELETE_WINDOW", safe_exit)

# ===== Main Entry Point =====
if __name__ == "__main__":
    # Process remaining CLI args 
    if len(remaining_args) >= 1:
        try:
            port = remaining_args[0]
            if port and not TEST_MODE:
                if ser:
                    ser.close()
                time.sleep(0.1)
                globals()['SERIAL_PORT'] = port
                initialize_serial()
                print(f"[INFO] Using serial port: {SERIAL_PORT}")
        except Exception as e:
            print(f"[WARN] Failed to switch serial port: {e}")
            
    if len(remaining_args) >= 2:
        program_path = remaining_args[1]
        if os.path.exists(program_path):
            # Set the path after GUI is created
            root.after(100, lambda: program_path_var.set(program_path))
            print(f"[INFO] Program will be loaded: {program_path}")

    # Update GUI to reflect CLI test mode setting
    if TEST_MODE:
        root.after(50, lambda: [test_mode_var.set(True), update_title(), update_simulation_controls(), status_var.set("Test Mode"), update_status_color()])

    # Now set up GUI with proper test mode state
    mode_text = "TEST MODE" if TEST_MODE else "HARDWARE MODE"
    print(f"[INFO] FusorAutoRun V9 started - Full JSON/CSV variable support enabled - {mode_text}")
    
    root.mainloop()