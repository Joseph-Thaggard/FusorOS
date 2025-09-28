import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import csv
from datetime import datetime
import os

class ScrollableFrame:
    """A scrollable frame that can be used for any content that might overflow"""
    
    def __init__(self, parent, width=None, height=None):
        # Create main container
        self.container = ttk.Frame(parent)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.container, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        
        # Create the scrollable frame
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Configure scrolling
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # Create canvas window
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Configure canvas
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Set size constraints if provided
        if width:
            self.canvas.configure(width=width)
        if height:
            self.canvas.configure(height=height)
        
        # Bind canvas resize to adjust frame width
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        # Bind mousewheel scrolling
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        
        # Pack elements
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
    def _on_canvas_configure(self, event):
        """Handle canvas resize"""
        # Update the scroll region
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # Update frame width to fill canvas
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def pack(self, **kwargs):
        """Pack the container"""
        self.container.pack(**kwargs)
    
    def pack_forget(self):
        """Hide the container"""
        self.container.pack_forget()

class FunctionLibraryManager:
    """Manages external function libraries"""
    
    def __init__(self):
        self.library_paths = []
        self.available_functions = {}  # function_name -> file_path
        self.function_metadata = {}    # function_name -> {description, parameters}
        
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
                    
                    self.available_functions[func_name] = file_path
                    
                    # Try to extract metadata from function file
                    metadata = self.extract_function_metadata(file_path)
                    self.function_metadata[func_name] = metadata
                    
        except Exception as e:
            print(f"Error scanning library {library_path}: {e}")
    
    def extract_function_metadata(self, file_path):
        """Extract metadata from function file"""
        metadata = {"description": "", "parameters": []}
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                
            # Look for metadata in comments at the top
            for line in lines[:10]:  # Check first 10 lines
                line = line.strip()
                if line.startswith('# Description:'):
                    metadata["description"] = line[14:].strip()
                elif line.startswith('# Parameters:'):
                    params = line[13:].strip()
                    if params:
                        metadata["parameters"] = [p.strip() for p in params.split(',')]
                        
        except Exception:
            pass
            
        return metadata
    
    def get_available_functions(self):
        """Get list of available function names"""
        return list(self.available_functions.keys())
    
    def get_function_info(self, func_name):
        """Get information about a specific function"""
        if func_name in self.available_functions:
            return {
                "path": self.available_functions[func_name],
                "metadata": self.function_metadata.get(func_name, {})
            }
        return None

class CommandBlock:
    """Represents a single command block in the visual programming interface"""
    
    def __init__(self, block_type, x=0, y=0, **kwargs):
        self.block_type = block_type
        self.x = x
        self.y = y
        self.width = 150
        self.height = 60
        self.parameters = kwargs
        self.canvas_id = None
        self.text_id = None
        self.arrow_id = None
        self.manual_connections = []
        self.incoming_connections = []
        
        # Add function linking support
        self.function_file_path = None  # Path to external function file
        self.is_external_function = False
        
    def get_command_text(self):
        """Generate the actual command text for this block"""
        if self.block_type == "variable_define":
            var_name = self.parameters.get("var_name", "myVar")
            var_value = self.parameters.get("var_value", "0")
            return f"SET_VAR {var_name}={var_value}"
        if self.block_type == "valve_control":
            valve = self.parameters.get("valve", "fuel")
            state = self.parameters.get("state", "open")
            action = "OPEN" if state == "open" else "CLOSE"
            return f"{action}_{valve.upper()}_VALVE"
            
        elif self.block_type == "delay":
            duration = self.parameters.get("duration", 1.0)
            return f"DELAY {duration}"
            
        elif self.block_type == "hv_control":
            voltage = self.parameters.get("voltage", 0)
            return f"SET_HV {voltage}"
            
        elif self.block_type == "pump_control":
            state = self.parameters.get("state", "on")
            return f"PUMP_{'ON' if state == 'on' else 'OFF'}"
            
        elif self.block_type == "mfc_control":
            setpoint = self.parameters.get("setpoint", 0)
            return f"SET_MFC {setpoint}"
            
        elif self.block_type == "wait_condition":
            condition = self.parameters.get("condition", "pressure")
            operator = self.parameters.get("operator", "<")
            value = self.parameters.get("value", 100)
            return f"WAIT {condition.upper()}{operator}{value}"
            
        elif self.block_type == "safe_state":
            return "SAFE_STATE"
            
        elif self.block_type == "comment":
            text = self.parameters.get("text", "Comment")
            return f"# {text}"
            
        elif self.block_type == "start":
            return "# START"
            
        elif self.block_type == "end":
            return "# END"
            
        elif self.block_type == "function_call":
            func_name = self.parameters.get("function_name", "my_function")
            args = self.parameters.get("arguments", "")
            if args:
                return f"CALL_FUNCTION {func_name}({args})"
            else:
                return f"CALL_FUNCTION {func_name}()"
                
        elif self.block_type == "function_define":
            func_name = self.parameters.get("function_name", "my_function")
            return f"DEFINE_FUNCTION {func_name}"
            
        elif self.block_type == "function_return":
            return "RETURN_FUNCTION"
            
        elif self.block_type == "loop_start":
            loop_type = self.parameters.get("loop_type", "while")
            if loop_type == "while":
                condition = self.parameters.get("condition", "pressure")
                operator = self.parameters.get("operator", "<")
                value = self.parameters.get("value", 100)
                return f"WHILE {condition.upper()}{operator}{value}"
            elif loop_type == "for":
                var_name = self.parameters.get("var_name", "i")
                start_val = self.parameters.get("start_value", 0)
                end_val = self.parameters.get("end_value", 10)
                return f"FOR {var_name} FROM {start_val} TO {end_val}"
            elif loop_type == "repeat":
                count = self.parameters.get("repeat_count", 5)
                return f"REPEAT {count} TIMES"
                
        elif self.block_type == "loop_end":
            return "END_LOOP"
            
        elif self.block_type == "conditional":
            condition = self.parameters.get("condition", "pressure")
            operator = self.parameters.get("operator", "<")
            value = self.parameters.get("value", 100)
            return f"IF {condition.upper()}{operator}{value}"
            
        elif self.block_type == "else_block":
            return "ELSE"
            
        elif self.block_type == "endif_block":
            return "END_IF"
            
        return "UNKNOWN_COMMAND"
    
    def get_display_text(self):
        """Get text to display on the block in the GUI"""
        if self.block_type == "valve_control":
            valve = self.parameters.get("valve", "fuel")
            state = self.parameters.get("state", "open")
            return f"{state.title()}\n{valve.title()} Valve"
            
        elif self.block_type == "delay":
            duration = self.parameters.get("duration", 1.0)
            return f"Wait\n{duration}s"
            
        elif self.block_type == "hv_control":
            voltage = self.parameters.get("voltage", 0)
            return f"Set HV\n{voltage}kV"
            
        elif self.block_type == "pump_control":
            state = self.parameters.get("state", "on")
            return f"Pump\n{state.title()}"
            
        elif self.block_type == "mfc_control":
            setpoint = self.parameters.get("setpoint", 0)
            return f"Set MFC\n{setpoint}%"
            
        elif self.block_type == "wait_condition":
            condition = self.parameters.get("condition", "pressure")
            operator = self.parameters.get("operator", "<")
            value = self.parameters.get("value", 100)
            return f"Wait Until\n{condition} {operator} {value}"
            
        elif self.block_type == "safe_state":
            return "Safe\nState"
            
        elif self.block_type == "comment":
            text = self.parameters.get("text", "Comment")
            return f"# {text[:15]}..."
            
        elif self.block_type == "start":
            return "START"
            
        elif self.block_type == "end":
            return "END"
            
        elif self.block_type == "function_call":
            func_name = self.parameters.get("function_name", "my_function")
            external_indicator = " [EXT]" if self.is_external_function else ""
            return f"Call\n{func_name}(){external_indicator}"
            
        elif self.block_type == "function_define":
            func_name = self.parameters.get("function_name", "my_function")
            return f"Define\n{func_name}"
            
        elif self.block_type == "function_return":
            return "Return"
            
        elif self.block_type == "loop_start":
            loop_type = self.parameters.get("loop_type", "while")
            if loop_type == "while":
                condition = self.parameters.get("condition", "pressure")
                operator = self.parameters.get("operator", "<")
                value = self.parameters.get("value", 100)
                return f"While\n{condition}{operator}{value}"
            elif loop_type == "for":
                var_name = self.parameters.get("var_name", "i")
                end_val = self.parameters.get("end_value", 10)
                return f"For {var_name}\nto {end_val}"
            elif loop_type == "repeat":
                count = self.parameters.get("repeat_count", 5)
                return f"Repeat\n{count} times"
                
        elif self.block_type == "loop_end":
            return "End Loop"
            
        elif self.block_type == "conditional":
            condition = self.parameters.get("condition", "pressure")
            operator = self.parameters.get("operator", "<")
            value = self.parameters.get("value", 100)
            return f"If\n{condition}{operator}{value}"
            
        elif self.block_type == "else_block":
            return "Else"
            
        elif self.block_type == "endif_block":
            return "End If"
            
        return "Unknown"

class BlockPalette:
    """Enhanced palette with scrollable content"""
    
    def __init__(self, parent_frame):
        self.main_frame = ttk.LabelFrame(parent_frame, text="Command Blocks", padding=5)
        
        # Create scrollable frame for the palette content
        self.scrollable_palette = ScrollableFrame(self.main_frame, height=400)
        self.scrollable_palette.pack(fill="both", expand=True)
        
        self.create_palette()
        
    def create_palette(self):
        """Create the palette of draggable blocks with scrollable notebook"""
        
        # Create notebook for categories
        self.notebook = ttk.Notebook(self.scrollable_palette.scrollable_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # Basic Operations Tab
        basic_frame = ttk.Frame(self.notebook)
        self.notebook.add(basic_frame, text="Basic")
        var_frame = ttk.Frame(self.notebook)
        self.notebook.add(var_frame, text="Variables")
        
        variable_blocks = [
            ("variable_define", "Set Variable", "#00CED1"),
        ]
        
        self.create_block_buttons(var_frame, variable_blocks)
        
        basic_blocks = [
            ("start", "Start", "#28a745"),
            ("valve_control", "Valve Control", "#FF6B6B"),
            ("mfc_control", "MFC Control", "#FFA500"),
            ("delay", "Delay", "#4ECDC4"),
            ("hv_control", "High Voltage", "#45B7D1"),
            ("pump_control", "Pump Control", "#96CEB4"),
            ("wait_condition", "Wait Condition", "#FECA57"),
            ("safe_state", "Safe State", "#FF9FF3"),
            ("comment", "Comment", "#DDA0DD"),
            ("end", "End", "#dc3545")
        ]
        
        self.create_block_buttons(basic_frame, basic_blocks)
        
        # Functions Tab
        func_frame = ttk.Frame(self.notebook)
        self.notebook.add(func_frame, text="Functions")
        
        function_blocks = [
            ("function_define", "Define Function", "#8A2BE2"),
            ("function_call", "Call Function", "#9370DB"),
            ("function_return", "Return", "#BA55D3")
        ]
        
        self.create_block_buttons(func_frame, function_blocks)
        
        # Loops & Conditionals Tab
        loop_frame = ttk.Frame(self.notebook)
        self.notebook.add(loop_frame, text="Loops & Logic")
        
        loop_blocks = [
            ("loop_start", "Loop Start", "#FF4500"),
            ("loop_end", "Loop End", "#FF6347"),
            ("conditional", "If Condition", "#32CD32"),
            ("else_block", "Else", "#90EE90"),
            ("endif_block", "End If", "#98FB98")
        ]
        
        self.create_block_buttons(loop_frame, loop_blocks)
        
    def create_block_buttons(self, parent_frame, block_list):
        """Create buttons for a list of blocks"""
        row = 0
        for block_type, display_name, color in block_list:
            btn = tk.Button(
                parent_frame,
                text=display_name,
                bg=color,
                fg="white",
                font=("Arial", 9, "bold"),
                width=12,
                height=2,
                command=lambda bt=block_type: self.create_block(bt)
            )
            btn.grid(row=row, column=0, pady=2, sticky="ew")
            parent_frame.grid_columnconfigure(0, weight=1)
            row += 1

    def create_block(self, block_type):
        """Create a new block and add it to the canvas"""
        self.parent_app.add_block(block_type)

class CanvasSettingsDialog:
    """Dialog for configuring canvas settings"""
    
    def __init__(self, parent, current_width, current_height):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Canvas Settings")
        self.dialog.geometry("300x200")
        
        self.width = current_width
        self.height = current_height
        self.result = None
        
        # Width setting
        ttk.Label(self.dialog, text="Canvas Width:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.width_var = tk.IntVar(value=current_width)
        ttk.Spinbox(self.dialog, from_=1000, to=10000, increment=500, textvariable=self.width_var, width=15).grid(row=0, column=1, padx=10, pady=5)
        
        # Height setting
        ttk.Label(self.dialog, text="Canvas Height:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.height_var = tk.IntVar(value=current_height)
        ttk.Spinbox(self.dialog, from_=1000, to=10000, increment=500, textvariable=self.height_var, width=15).grid(row=1, column=1, padx=10, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel_clicked).pack(side="left", padx=5)
        
        # Center the dialog
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
    def ok_clicked(self):
        self.result = (self.width_var.get(), self.height_var.get())
        self.dialog.destroy()
        
    def cancel_clicked(self):
        self.dialog.destroy()

class FusorCommandGenerator:
    """Main application class with enhanced scrollable GUI and full functionality"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Fusor Command File Generator v6 - Complete Integration")
        self.root.geometry("1600x1000")
        
        self.blocks = []
        self.selected_block = None
        self.drag_data = {"x": 0, "y": 0}
        
        # Function library manager
        self.function_library = FunctionLibraryManager()
        
        # Grid settings
        self.grid_size = 20
        self.show_grid = True
        
        # Connection mode
        self.connection_mode = False
        self.connection_start_block = None
        
        # Canvas dimensions (configurable)
        self.canvas_width = 2000
        self.canvas_height = 2000
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the enhanced user interface with scrollable elements"""
        
        # Main container with better proportions
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create main paned window for better space management
        main_paned = ttk.PanedWindow(main_frame, orient="horizontal")
        main_paned.pack(fill="both", expand=True)
        
        # Left panel - make it scrollable
        left_container = ttk.Frame(main_paned, width=350)
        main_paned.add(left_container, weight=0)
        
        # Create scrollable left panel
        self.left_scrollable = ScrollableFrame(left_container, width=340)
        self.left_scrollable.pack(fill="both", expand=True)
        
        # Function Library Manager in scrollable area
        library_frame = ttk.LabelFrame(self.left_scrollable.scrollable_frame, text="Function Libraries", padding=10)
        library_frame.pack(fill="x", pady=(0, 5))
        
        # Library path entry and controls
        lib_path_frame = ttk.Frame(library_frame)
        lib_path_frame.pack(fill="x", pady=(0, 5))
        
        self.lib_path_var = tk.StringVar()
        ttk.Entry(lib_path_frame, textvariable=self.lib_path_var, width=20).pack(side="left", expand=True, fill="x")
        ttk.Button(lib_path_frame, text="Browse", command=self.browse_library, width=8).pack(side="right", padx=(2, 0))
        
        lib_buttons_frame = ttk.Frame(library_frame)
        lib_buttons_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(lib_buttons_frame, text="Add Library", command=self.add_library).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(lib_buttons_frame, text="Refresh", command=self.refresh_libraries).pack(side="right", expand=True, fill="x", padx=(2, 0))
        
        # Available functions list with better sizing
        ttk.Label(library_frame, text="Available Functions:").pack(anchor="w")
        functions_frame = ttk.Frame(library_frame)
        functions_frame.pack(fill="x", pady=(0, 5))
        
        self.functions_listbox = tk.Listbox(functions_frame, height=5, font=("Courier", 9))
        functions_scrollbar = ttk.Scrollbar(functions_frame, orient="vertical", command=self.functions_listbox.yview)
        self.functions_listbox.configure(yscrollcommand=functions_scrollbar.set)
        
        self.functions_listbox.pack(side="left", fill="both", expand=True)
        functions_scrollbar.pack(side="right", fill="y")
        
        ttk.Button(library_frame, text="Add Function Call", command=self.add_external_function_call).pack(fill="x")
        
        # Block palette - now scrollable
        self.palette = BlockPalette(self.left_scrollable.scrollable_frame)
        self.palette.parent_app = self
        self.palette.main_frame.pack(fill="x", pady=(0, 10))
        
        # Properties panel - scrollable
        properties_container = ttk.LabelFrame(self.left_scrollable.scrollable_frame, text="Properties", padding=5)
        properties_container.pack(fill="x", pady=(0, 10))
        
        # Create scrollable properties frame
        self.properties_scrollable = ScrollableFrame(properties_container, height=300)
        self.properties_scrollable.pack(fill="both", expand=True)
        
        self.properties_frame = self.properties_scrollable.scrollable_frame
        
        # Center panel for canvas
        center_container = ttk.Frame(main_paned)
        main_paned.add(center_container, weight=2)
        
        # Canvas for visual programming
        canvas_frame = ttk.LabelFrame(center_container, text="Program Canvas", padding=5)
        canvas_frame.pack(fill="both", expand=True)
        
        self.canvas = tk.Canvas(
            canvas_frame,
            bg="white",
            scrollregion=(0, 0, self.canvas_width, self.canvas_height)
        )
        
        # Scrollbars for canvas
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        h_scrollbar.pack(side="bottom", fill="x")
        v_scrollbar.pack(side="right", fill="y")
        
        # Bind canvas events
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Button-3>", self.on_right_click)
        
        # Right panel for controls and output
        right_container = ttk.Frame(main_paned, width=400)
        main_paned.add(right_container, weight=1)
        
        # Create scrollable right panel
        self.right_scrollable = ScrollableFrame(right_container, width=390)
        self.right_scrollable.pack(fill="both", expand=True)
        
        # Control buttons
        control_frame = ttk.LabelFrame(self.right_scrollable.scrollable_frame, text="Controls", padding=10)
        control_frame.pack(fill="x", pady=(0, 10))
        
        # Create a grid of control buttons for better organization
        buttons_frame = ttk.Frame(control_frame)
        buttons_frame.pack(fill="x")
        
        # Row 0
        ttk.Button(buttons_frame, text="Clear All", command=self.clear_all).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(buttons_frame, text="Generate Commands", command=self.generate_commands).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        # Row 1
        ttk.Button(buttons_frame, text="Validate Program", command=self.validate_program).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(buttons_frame, text="Clear Connections", command=self.clear_connections).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        
        # Row 2
        ttk.Button(buttons_frame, text="Save Program", command=self.save_program).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(buttons_frame, text="Load Program", command=self.load_program).grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        
        # Row 3
        ttk.Button(buttons_frame, text="Export to CSV", command=self.export_csv).grid(row=3, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(buttons_frame, text="Canvas Settings", command=self.configure_canvas).grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        
        # Configure grid weights
        for i in range(2):
            buttons_frame.grid_columnconfigure(i, weight=1)
        
        # Connection mode toggle
        connection_frame = ttk.Frame(control_frame)
        connection_frame.pack(fill="x", pady=(10, 2))
        self.connection_var = tk.BooleanVar(value=False)
        self.connection_btn = ttk.Checkbutton(
            connection_frame, 
            text="Connection Mode", 
            variable=self.connection_var,
            command=self.toggle_connection_mode
        )
        self.connection_btn.pack(side="left")
        
        self.connection_status = ttk.Label(connection_frame, text="")
        self.connection_status.pack(side="right")
        
        # Grid toggle
        grid_frame = ttk.Frame(control_frame)
        grid_frame.pack(fill="x", pady=2)
        self.grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            grid_frame, 
            text="Show Grid", 
            variable=self.grid_var,
            command=self.toggle_grid
        ).pack(side="left")
        
        # Command preview with better sizing
        preview_frame = ttk.LabelFrame(self.right_scrollable.scrollable_frame, text="Generated Commands", padding=10)
        preview_frame.pack(fill="both", expand=True)
        
        # Create text area with scrollbars
        text_container = ttk.Frame(preview_frame)
        text_container.pack(fill="both", expand=True)
        
        self.command_text = tk.Text(
            text_container,
            wrap="word",
            font=("Courier", 9),
            height=25
        )
        
        text_scrollbar_v = ttk.Scrollbar(text_container, orient="vertical", command=self.command_text.yview)
        text_scrollbar_h = ttk.Scrollbar(text_container, orient="horizontal", command=self.command_text.xview)
        self.command_text.configure(yscrollcommand=text_scrollbar_v.set, xscrollcommand=text_scrollbar_h.set)
        
        self.command_text.grid(row=0, column=0, sticky="nsew")
        text_scrollbar_v.grid(row=0, column=1, sticky="ns")
        text_scrollbar_h.grid(row=1, column=0, sticky="ew")
        
        text_container.grid_rowconfigure(0, weight=1)
        text_container.grid_columnconfigure(0, weight=1)
        
        # Initialize empty properties panel
        self.update_properties_panel()
        
        # Draw initial grid
        self.draw_grid()
        
        # Update functions list
        self.update_functions_list()

    def configure_canvas(self):
        """Open dialog to configure canvas size"""
        dialog = CanvasSettingsDialog(self.root, self.canvas_width, self.canvas_height)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            self.canvas_width, self.canvas_height = dialog.result
            self.canvas.configure(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
            self.draw_grid()
            messagebox.showinfo("Success", f"Canvas resized to {self.canvas_width}x{self.canvas_height}")

    def browse_library(self):
        """Browse for function library directory"""
        path = filedialog.askdirectory(title="Select Function Library Directory")
        if path:
            self.lib_path_var.set(path)
    
    def add_library(self):
        """Add a function library directory"""
        path = self.lib_path_var.get().strip()
        if not path:
            messagebox.showerror("Error", "Please select a library directory.")
            return
            
        if not os.path.isdir(path):
            messagebox.showerror("Error", "Directory does not exist.")
            return
            
        if self.function_library.add_library_path(path):
            self.update_functions_list()
            messagebox.showinfo("Success", f"Added library: {os.path.basename(path)}")
        else:
            messagebox.showwarning("Warning", "Library already added or invalid directory.")
    
    def refresh_libraries(self):
        """Refresh function libraries"""
        self.function_library.available_functions.clear()
        self.function_library.function_metadata.clear()
        
        for lib_path in self.function_library.library_paths:
            self.function_library.scan_library(lib_path)
            
        self.update_functions_list()
        messagebox.showinfo("Success", "Function libraries refreshed.")
    
    def update_functions_list(self):
        """Update the functions listbox"""
        self.functions_listbox.delete(0, tk.END)
        
        functions = self.function_library.get_available_functions()
        for func_name in sorted(functions):
            metadata = self.function_library.function_metadata.get(func_name, {})
            description = metadata.get("description", "")
            display_text = f"{func_name}"
            if description:
                display_text += f" - {description}"
            self.functions_listbox.insert(tk.END, display_text)
    
    def add_external_function_call(self):
        """Add a function call block for selected external function"""
        selection = self.functions_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a function from the list.")
            return
            
        # Get selected function name (before the " - " if description exists)
        selected_text = self.functions_listbox.get(selection[0])
        func_name = selected_text.split(" - ")[0].strip()
        
        # Create function call block
        base_x = self.canvas.canvasx(200)
        base_y = self.canvas.canvasy(100 + len(self.blocks) * 80)
        x, y = self.snap_to_grid(base_x, base_y)
        
        block = CommandBlock("function_call", x, y)
        block.parameters = {"function_name": func_name, "arguments": ""}
        block.is_external_function = True
        block.function_file_path = self.function_library.available_functions.get(func_name)
        
        self.blocks.append(block)
        self.draw_block(block)
        self.draw_arrows()
        self.generate_commands()
        
        messagebox.showinfo("Success", f"Added external function call: {func_name}")

    def snap_to_grid(self, x, y):
        """Snap coordinates to grid"""
        snapped_x = round(x / self.grid_size) * self.grid_size
        snapped_y = round(y / self.grid_size) * self.grid_size
        return snapped_x, snapped_y
        
    def draw_grid(self):
        """Draw grid lines on canvas"""
        self.canvas.delete("grid_line")
        
        if not self.show_grid:
            return
            
        # Draw vertical lines
        for x in range(0, self.canvas_width, self.grid_size):
            self.canvas.create_line(x, 0, x, self.canvas_height, fill="lightgray", tags="grid_line")
            self.canvas.tag_lower("grid_line")
            
        # Draw horizontal lines
        for y in range(0, self.canvas_height, self.grid_size):
            self.canvas.create_line(0, y, self.canvas_width, y, fill="lightgray", tags="grid_line")
            self.canvas.tag_lower("grid_line")

    def toggle_grid(self):
        """Toggle grid visibility"""
        self.show_grid = self.grid_var.get()
        self.draw_grid()
        
    def toggle_connection_mode(self):
        """Toggle connection mode for creating custom arrows"""
        self.connection_mode = self.connection_var.get()
        if self.connection_mode:
            self.connection_status.config(text="Click blocks to connect", foreground="blue")
        else:
            self.connection_status.config(text="")
            self.connection_start_block = None

    def on_canvas_click(self, event):
        """Handle canvas click events"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        
        # Find clicked block
        clicked_block = self.find_block_at_position(x, y)
        
        if self.connection_mode and clicked_block:
            # Handle connection mode clicks
            if self.connection_start_block is None:
                # Start connection
                self.connection_start_block = clicked_block
                self.connection_status.config(text=f"From: {clicked_block.block_type} → Click target")
                self.highlight_block_for_connection(clicked_block, "start")
            else:
                # Complete connection
                if clicked_block != self.connection_start_block:
                    self.create_manual_connection(self.connection_start_block, clicked_block)
                    self.connection_status.config(text="Connection created!")
                else:
                    self.connection_status.config(text="Cannot connect block to itself")
                
                # Clear highlights and reset
                self.canvas.delete("connection_highlight")
                self.connection_start_block = None
                self.root.after(2000, lambda: self.connection_status.config(text="Click blocks to connect"))
            return
        
        # Normal selection mode
        if clicked_block:
            self.selected_block = clicked_block
            self.drag_data["x"] = x - clicked_block.x
            self.drag_data["y"] = y - clicked_block.y
            self.update_properties_panel()
        else:
            self.selected_block = None
            self.update_properties_panel()
        
        self.highlight_selected_block()

    def on_canvas_drag(self, event):
        """Handle canvas drag events"""
        if self.selected_block:
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)
            
            # Snap to grid
            new_x, new_y = self.snap_to_grid(x - self.drag_data["x"], y - self.drag_data["y"])
            
            # Update block position
            dx = new_x - self.selected_block.x
            dy = new_y - self.selected_block.y
            
            self.selected_block.x = new_x
            self.selected_block.y = new_y
            
            # Move canvas items
            self.canvas.move(self.selected_block.canvas_id, dx, dy)
            self.canvas.move(self.selected_block.text_id, dx, dy)
            
            # Update arrows in real-time
            self.draw_arrows()

    def on_canvas_release(self, event):
        """Handle canvas release events"""
        if self.selected_block:
            # Final snap to grid and update sequence
            self.draw_arrows()
            self.generate_commands()

    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.draw_grid()

    def on_right_click(self, event):
        """Handle right-click for connection mode"""
        if not self.connection_mode:
            return
            
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        
        # Find clicked block
        clicked_block = self.find_block_at_position(x, y)
        
        if clicked_block:
            if self.connection_start_block is None:
                # Start connection
                self.connection_start_block = clicked_block
                self.connection_status.config(text=f"From: {clicked_block.block_type} → Click target")
            else:
                # Complete connection
                if clicked_block != self.connection_start_block:
                    self.create_manual_connection(self.connection_start_block, clicked_block)
                    self.connection_status.config(text="Connection created!")
                else:
                    self.connection_status.config(text="Cannot connect block to itself")
                
                # Reset
                self.connection_start_block = None
                self.root.after(2000, lambda: self.connection_status.config(text="Click blocks to connect"))

    def find_block_at_position(self, x, y):
        """Find block at given position"""
        for block in self.blocks:
            if (block.x <= x <= block.x + block.width and
                block.y <= y <= block.y + block.height):
                return block
        return None
    
    def highlight_block_for_connection(self, block, connection_type):
        """Highlight a block during connection creation"""
        color = "green" if connection_type == "start" else "orange"
        self.canvas.create_rectangle(
            block.x - 5, block.y - 5,
            block.x + block.width + 5, block.y + block.height + 5,
            outline=color,
            width=3,
            tags="connection_highlight"
        )

    def create_manual_connection(self, from_block, to_block):
        """Create a manual connection between two blocks"""
        if to_block not in from_block.manual_connections:
            from_block.manual_connections.append(to_block)
            to_block.incoming_connections.append(from_block)
            self.draw_arrows()

    def highlight_selected_block(self):
        """Highlight the selected block"""
        # Remove previous highlights
        self.canvas.delete("highlight")
        
        if self.selected_block:
            # Add highlight rectangle
            self.canvas.create_rectangle(
                self.selected_block.x - 3, self.selected_block.y - 3,
                self.selected_block.x + self.selected_block.width + 3,
                self.selected_block.y + self.selected_block.height + 3,
                outline="red",
                width=3,
                tags="highlight"
            )

    def get_parallel_sequences(self):
        """Group blocks into parallel sequences based on X position"""
        if not self.blocks:
            return []
            
        # Group blocks by X position (with tolerance for slight variations)
        x_tolerance = self.grid_size * 2  # Allow 2 grid units of tolerance
        sequences = {}
        
        for block in self.blocks:
            # Find existing sequence with similar X position
            found_sequence = False
            for seq_x in sequences.keys():
                if abs(block.x - seq_x) <= x_tolerance:
                    sequences[seq_x].append(block)
                    found_sequence = True
                    break
            
            if not found_sequence:
                sequences[block.x] = [block]
        
        # Sort blocks within each sequence by Y position
        for x_pos in sequences:
            sequences[x_pos].sort(key=lambda b: b.y)
            
        # Return sequences sorted by X position
        return [sequences[x] for x in sorted(sequences.keys())]
    
    def draw_arrows(self):
        """Draw arrows connecting blocks in parallel sequences and manual connections"""
        # Remove existing arrows
        self.canvas.delete("arrow")
        
        # Draw automatic sequence arrows
        sequences = self.get_parallel_sequences()
        
        for seq_idx, sequence in enumerate(sequences):
            # Draw vertical arrows within each sequence
            for i in range(len(sequence) - 1):
                current_block = sequence[i]
                next_block = sequence[i + 1]
                
                # Check if blocks are in the same column (vertical connection)
                if abs(current_block.x - next_block.x) <= self.grid_size * 2:
                    # Only draw automatic arrow if no manual connection exists
                    if next_block not in current_block.manual_connections:
                        self.draw_arrow(current_block, next_block, "blue", "auto")
                else:
                    # Horizontal arrow (right) - for blocks that moved horizontally
                    if next_block not in current_block.manual_connections:
                        self.draw_horizontal_arrow(current_block, next_block, "blue", "auto")
        
        # Draw manual connections
        for block in self.blocks:
            for target_block in block.manual_connections:
                self.draw_arrow(block, target_block, "red", "manual")
        
        # Draw parallel execution indicators
        self.draw_parallel_indicators(sequences)
    
    def draw_arrow(self, from_block, to_block, color, arrow_type):
        """Draw a single arrow between two blocks"""
        # Calculate connection points
        from_x = from_block.x + from_block.width // 2
        from_y = from_block.y + from_block.height
        to_x = to_block.x + to_block.width // 2
        to_y = to_block.y
        
        # Adjust for manual connections to avoid overlap
        if arrow_type == "manual":
            # Connect from right side to left side for manual connections
            from_x = from_block.x + from_block.width
            from_y = from_block.y + from_block.height // 2
            to_x = to_block.x
            to_y = to_block.y + to_block.height // 2
        
        # Draw different arrow styles
        if arrow_type == "manual":
            # Dashed line for manual connections
            dash_pattern = (5, 5)
            width = 3
        else:
            # Solid line for automatic connections
            dash_pattern = ()
            width = 2
        
        # Create arrow
        arrow_id = self.canvas.create_line(
            from_x, from_y,
            to_x, to_y,
            fill=color,
            width=width,
            arrow=tk.LAST,
            arrowshape=(10, 12, 5),
            dash=dash_pattern,
            tags="arrow"
        )
        
        # Add label for manual connections
        if arrow_type == "manual":
            mid_x = (from_x + to_x) // 2
            mid_y = (from_y + to_y) // 2
            self.canvas.create_text(
                mid_x, mid_y - 10,
                text="custom",
                font=("Arial", 8),
                fill=color,
                tags="arrow"
            )
        
        return arrow_id
    
    def draw_horizontal_arrow(self, from_block, to_block, color, arrow_type):
        """Draw horizontal or L-shaped arrow"""
        start_x = from_block.x + from_block.width
        start_y = from_block.y + from_block.height // 2
        end_x = to_block.x
        end_y = to_block.y + to_block.height // 2
        
        # Draw L-shaped connection if there's vertical offset
        if abs(start_y - end_y) > 10:
            # Draw L-shaped path: horizontal then vertical
            mid_x = start_x + (end_x - start_x) // 2
            
            # Horizontal segment
            self.canvas.create_line(
                start_x + 5, start_y,
                mid_x, start_y,
                fill=color,
                width=2,
                tags="arrow"
            )
            
            # Vertical segment
            self.canvas.create_line(
                mid_x, start_y,
                mid_x, end_y,
                fill=color,
                width=2,
                tags="arrow"
            )
            
            # Final horizontal segment with arrow
            arrow_id = self.canvas.create_line(
                mid_x, end_y,
                end_x - 5, end_y,
                fill=color,
                width=2,
                arrow=tk.LAST,
                arrowshape=(10, 12, 5),
                tags="arrow"
            )
        else:
            # Straight horizontal arrow
            arrow_id = self.canvas.create_line(
                start_x + 5, start_y,
                end_x - 5, end_y,
                fill=color,
                width=2,
                arrow=tk.LAST,
                arrowshape=(10, 12, 5),
                tags="arrow"
            )
    
    def draw_parallel_indicators(self, sequences):
        """Draw visual indicators showing parallel execution"""
        if len(sequences) <= 1:
            return
            
        # Draw dashed lines to show parallel sequences
        for i, sequence in enumerate(sequences):
            if not sequence:
                continue
                
            # Draw sequence label
            first_block = sequence[0]
            self.canvas.create_text(
                first_block.x + first_block.width // 2,
                first_block.y - 25,
                text=f"Sequence {i + 1}",
                font=("Arial", 10, "bold"),
                fill="purple",
                tags="arrow"
            )
            
            # Draw vertical dashed line for the entire sequence
            if len(sequence) > 1:
                start_y = sequence[0].y - 15
                end_y = sequence[-1].y + sequence[-1].height + 15
                
                # Create dashed line effect
                line_x = first_block.x + first_block.width // 2
                dash_length = 10
                current_y = start_y
                
                while current_y < end_y:
                    next_y = min(current_y + dash_length, end_y)
                    if (current_y - start_y) // dash_length % 2 == 0:  # Every other dash
                        self.canvas.create_line(
                            line_x - 3, current_y,
                            line_x - 3, next_y,
                            fill="purple",
                            width=2,
                            tags="arrow"
                        )
                    current_y = next_y

    def update_properties_panel(self):
        """Update the properties panel based on selected block"""
        # Clear existing widgets
        for widget in self.properties_frame.winfo_children():
            widget.destroy()
            
        if not self.selected_block:
            ttk.Label(self.properties_frame, text="Select a block to edit properties").pack()
            return
            
        block = self.selected_block
        
        ttk.Label(self.properties_frame, text=f"Block Type: {block.block_type.replace('_', ' ').title()}").pack(anchor="w")
        
        # Show external function indicator
        if block.is_external_function:
            ttk.Label(self.properties_frame, text="[EXTERNAL FUNCTION]", foreground="red", font=("Arial", 8, "bold")).pack(anchor="w")
            if block.function_file_path:
                ttk.Label(self.properties_frame, text=f"File: {os.path.basename(block.function_file_path)}", font=("Arial", 8)).pack(anchor="w")
        
        ttk.Separator(self.properties_frame, orient="horizontal").pack(fill="x", pady=5)
        
        # Create parameter controls based on block type
        if block.block_type == "valve_control":
            self.create_valve_controls(block)
        elif block.block_type == "delay":
            self.create_delay_controls(block)
        elif block.block_type == "hv_control":
            self.create_hv_controls(block)
        elif block.block_type == "pump_control":
            self.create_pump_controls(block)
        elif block.block_type == "mfc_control":
            self.create_mfc_controls(block)
        elif block.block_type == "wait_condition":
            self.create_wait_controls(block)
        elif block.block_type == "comment":
            self.create_comment_controls(block)
        elif block.block_type == "function_call":
            self.create_function_call_controls(block)
        elif block.block_type == "function_define":
            self.create_function_define_controls(block)
        elif block.block_type == "loop_start":
            self.create_loop_start_controls(block)
        elif block.block_type == "conditional":
            self.create_conditional_controls(block)
        elif block.block_type == "variable_define":  # ADD THIS
            self.create_variable_define_controls(block)
        elif block.block_type in ["start", "end", "safe_state", "function_return", "loop_end", "else_block", "endif_block"]:
            ttk.Label(self.properties_frame, text="No configurable properties").pack(anchor="w")
            
        # Show connections info
        self.show_connection_info(block)
            
        # Delete button
        ttk.Separator(self.properties_frame, orient="horizontal").pack(fill="x", pady=10)
        ttk.Button(self.properties_frame, text="Delete Block", command=self.delete_selected_block).pack(fill="x")

    def create_valve_controls(self, block):
        """Create controls for valve block"""
        ttk.Label(self.properties_frame, text="Valve:").pack(anchor="w")
        valve_var = tk.StringVar(value=block.parameters.get("valve", "fuel"))
        valve_combo = ttk.Combobox(self.properties_frame, textvariable=valve_var, values=["fuel", "vacuum"])
        valve_combo.pack(fill="x", pady=(0, 10))
        
        ttk.Label(self.properties_frame, text="Action:").pack(anchor="w")
        state_var = tk.StringVar(value=block.parameters.get("state", "open"))
        state_combo = ttk.Combobox(self.properties_frame, textvariable=state_var, values=["open", "close"])
        state_combo.pack(fill="x")
        
        def update_valve():
            block.parameters["valve"] = valve_var.get()
            block.parameters["state"] = state_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        valve_combo.bind("<<ComboboxSelected>>", lambda e: update_valve())
        state_combo.bind("<<ComboboxSelected>>", lambda e: update_valve())
        
    def create_delay_controls(self, block):
        """Create controls for delay block"""
        ttk.Label(self.properties_frame, text="Duration (seconds):").pack(anchor="w")
        duration_var = tk.DoubleVar(value=block.parameters.get("duration", 1.0))
        duration_spin = ttk.Spinbox(
            self.properties_frame,
            from_=0.1, to=3600.0, increment=0.1,
            textvariable=duration_var,
            format="%.1f"
        )
        duration_spin.pack(fill="x")
        
        def update_delay():
            block.parameters["duration"] = duration_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        duration_var.trace("w", lambda *args: update_delay())
        
    def create_hv_controls(self, block):
        """Create controls for high voltage block"""
        ttk.Label(self.properties_frame, text="Voltage (kV):").pack(anchor="w")
        voltage_var = tk.IntVar(value=block.parameters.get("voltage", 0))
        voltage_spin = ttk.Spinbox(
            self.properties_frame,
            from_=0, to=50, increment=1,
            textvariable=voltage_var
        )
        voltage_spin.pack(fill="x")
        
        def update_hv():
            block.parameters["voltage"] = voltage_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        voltage_var.trace("w", lambda *args: update_hv())
        
    def create_pump_controls(self, block):
        """Create controls for pump block"""
        ttk.Label(self.properties_frame, text="Action:").pack(anchor="w")
        state_var = tk.StringVar(value=block.parameters.get("state", "on"))
        state_combo = ttk.Combobox(self.properties_frame, textvariable=state_var, values=["on", "off"])
        state_combo.pack(fill="x")
        
        def update_pump():
            block.parameters["state"] = state_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        state_combo.bind("<<ComboboxSelected>>", lambda e: update_pump())
        
    def create_mfc_controls(self, block):
        """Create controls for MFC (Mass Flow Controller) block"""
        ttk.Label(self.properties_frame, text="MFC Setpoint (0-100%):").pack(anchor="w")
        setpoint_var = tk.IntVar(value=block.parameters.get("setpoint", 0))
        setpoint_spin = ttk.Spinbox(
            self.properties_frame,
            from_=0, to=100, increment=1,
            textvariable=setpoint_var
        )
        setpoint_spin.pack(fill="x")
        
        # Add label to show current value
        value_label = ttk.Label(self.properties_frame, text=f"Current: {setpoint_var.get()}%")
        value_label.pack(anchor="w", pady=(2, 0))
        
        def update_mfc():
            setpoint_value = setpoint_var.get()
            block.parameters["setpoint"] = setpoint_value
            value_label.config(text=f"Current: {setpoint_value}%")
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        setpoint_var.trace("w", lambda *args: update_mfc())
        
    def create_wait_controls(self, block):
        """Create controls for wait condition block"""
        ttk.Label(self.properties_frame, text="Wait for:").pack(anchor="w")
        condition_var = tk.StringVar(value=block.parameters.get("condition", "pressure"))
        condition_combo = ttk.Combobox(
            self.properties_frame,
            textvariable=condition_var,
            values=["pressure", "flow", "hv_voltage", "hv_current"]
        )
        condition_combo.pack(fill="x", pady=(0, 5))
        
        ttk.Label(self.properties_frame, text="Operator:").pack(anchor="w")
        operator_var = tk.StringVar(value=block.parameters.get("operator", "<"))
        operator_combo = ttk.Combobox(
            self.properties_frame,
            textvariable=operator_var,
            values=["<", "<=", ">", ">=", "=="]
        )
        operator_combo.pack(fill="x", pady=(0, 5))
        
        ttk.Label(self.properties_frame, text="Value:").pack(anchor="w")
        value_var = tk.DoubleVar(value=block.parameters.get("value", 100))
        value_entry = ttk.Entry(self.properties_frame, textvariable=value_var)
        value_entry.pack(fill="x")
        
        def update_wait():
            block.parameters["condition"] = condition_var.get()
            block.parameters["operator"] = operator_var.get()
            block.parameters["value"] = value_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        condition_combo.bind("<<ComboboxSelected>>", lambda e: update_wait())
        operator_combo.bind("<<ComboboxSelected>>", lambda e: update_wait())
        value_var.trace("w", lambda *args: update_wait())
        
    def create_comment_controls(self, block):
        """Create controls for comment block"""
        ttk.Label(self.properties_frame, text="Comment:").pack(anchor="w")
        text_var = tk.StringVar(value=block.parameters.get("text", "Enter comment here"))
        text_entry = ttk.Entry(self.properties_frame, textvariable=text_var)
        text_entry.pack(fill="x")
        
        def update_comment():
            block.parameters["text"] = text_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        text_var.trace("w", lambda *args: update_comment())
    
    def create_function_call_controls(self, block):
        """Create controls for function call block with argument support"""
        if block.is_external_function:
            ttk.Label(self.properties_frame, text="External Function Call", font=("Arial", 10, "bold")).pack(anchor="w")
            
        ttk.Label(self.properties_frame, text="Function Name:").pack(anchor="w")
        func_name_var = tk.StringVar(value=block.parameters.get("function_name", "my_function"))
        
        # Create combobox with available functions
        available_functions = [""] + self.function_library.get_available_functions()
        func_combo = ttk.Combobox(self.properties_frame, textvariable=func_name_var, values=available_functions)
        func_combo.pack(fill="x", pady=(0, 5))
        
        # Show function info and parameters if available
        func_info_frame = ttk.Frame(self.properties_frame)
        func_info_frame.pack(fill="x", pady=(0, 5))
        
        def update_param_fields():
            # Clear existing parameter fields
            for widget in func_info_frame.winfo_children():
                widget.destroy()
            
            # Check if this is an external function with metadata
            if func_name_var.get() in self.function_library.get_available_functions():
                func_info = self.function_library.get_function_info(func_name_var.get())
                if func_info:
                    metadata = func_info.get("metadata", {})
                    
                    # Show description
                    if metadata.get("description"):
                        ttk.Label(func_info_frame, text=f"Description: {metadata['description']}", 
                                font=("Arial", 8), wraplength=200).pack(anchor="w")
                    
                    # Show expected parameters
                    if metadata.get("parameters"):
                        ttk.Label(func_info_frame, text=f"Parameters: {', '.join(metadata['parameters'])}", 
                                font=("Arial", 8), wraplength=200).pack(anchor="w")
        
        update_param_fields()
        
        ttk.Label(self.properties_frame, text="Arguments:").pack(anchor="w")
        ttk.Label(self.properties_frame, text="(comma-separated values, e.g., 100, 5)", 
                font=("Arial", 8)).pack(anchor="w")
        args_var = tk.StringVar(value=block.parameters.get("arguments", ""))
        args_entry = ttk.Entry(self.properties_frame, textvariable=args_var)
        args_entry.pack(fill="x")
        
        # Add example based on function
        example_frame = ttk.Frame(self.properties_frame)
        example_frame.pack(fill="x", pady=(2, 0))
        
        def show_example():
            for widget in example_frame.winfo_children():
                widget.destroy()
                
            func_name = func_name_var.get()
            if "pressure" in func_name.lower():
                ttk.Label(example_frame, text="Example: 100, 5 (target=100, tolerance=5)", 
                        font=("Arial", 8), foreground="gray").pack(anchor="w")
            elif "flow" in func_name.lower():
                ttk.Label(example_frame, text="Example: 50 (setpoint=50)", 
                        font=("Arial", 8), foreground="gray").pack(anchor="w")
        
        show_example()
        
        def update_function_call():
            new_func_name = func_name_var.get()
            block.parameters["function_name"] = new_func_name
            block.parameters["arguments"] = args_var.get()
            
            # Update external function status
            if new_func_name in self.function_library.get_available_functions():
                block.is_external_function = True
                block.function_file_path = self.function_library.available_functions.get(new_func_name)
            else:
                block.is_external_function = False
                block.function_file_path = None
            
            update_param_fields()
            show_example()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        func_name_var.trace("w", lambda *args: update_function_call())
        args_var.trace("w", lambda *args: update_function_call())
        
    def create_function_define_controls(self, block):
        """Create controls for function define block"""
        ttk.Label(self.properties_frame, text="Function Name:").pack(anchor="w")
        func_name_var = tk.StringVar(value=block.parameters.get("function_name", "my_function"))
        func_name_entry = ttk.Entry(self.properties_frame, textvariable=func_name_var)
        func_name_entry.pack(fill="x")
        
        def update_function_define():
            block.parameters["function_name"] = func_name_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        func_name_var.trace("w", lambda *args: update_function_define())
        
    def create_loop_start_controls(self, block):
        """Create controls for loop start block"""
        ttk.Label(self.properties_frame, text="Loop Type:").pack(anchor="w")
        loop_type_var = tk.StringVar(value=block.parameters.get("loop_type", "while"))
        loop_type_combo = ttk.Combobox(
            self.properties_frame,
            textvariable=loop_type_var,
            values=["while", "for", "repeat"],
            state="readonly"
        )
        loop_type_combo.pack(fill="x", pady=(0, 5))
        
        # Container for dynamic controls
        self.loop_controls_frame = ttk.Frame(self.properties_frame)
        self.loop_controls_frame.pack(fill="x", pady=(0, 5))
        
        def update_loop_controls():
            # Clear existing controls
            for widget in self.loop_controls_frame.winfo_children():
                widget.destroy()
                
            loop_type = loop_type_var.get()
            
            if loop_type == "while":
                ttk.Label(self.loop_controls_frame, text="While condition:").pack(anchor="w")
                
                condition_var = tk.StringVar(value=block.parameters.get("condition", "pressure"))
                condition_combo = ttk.Combobox(
                    self.loop_controls_frame,
                    textvariable=condition_var,
                    values=["pressure", "flow", "hv_voltage", "hv_current", "temperature"]
                )
                condition_combo.pack(fill="x", pady=(0, 2))
                
                operator_var = tk.StringVar(value=block.parameters.get("operator", "<"))
                operator_combo = ttk.Combobox(
                    self.loop_controls_frame,
                    textvariable=operator_var,
                    values=["<", "<=", ">", ">=", "==", "!="]
                )
                operator_combo.pack(fill="x", pady=(0, 2))
                
                value_var = tk.DoubleVar(value=block.parameters.get("value", 100))
                value_entry = ttk.Entry(self.loop_controls_frame, textvariable=value_var)
                value_entry.pack(fill="x")
                
                def update_while():
                    block.parameters.update({
                        "loop_type": "while",
                        "condition": condition_var.get(),
                        "operator": operator_var.get(),
                        "value": value_var.get()
                    })
                    self.redraw_block(block)
                    self.generate_commands()
                
                condition_combo.bind("<<ComboboxSelected>>", lambda e: update_while())
                operator_combo.bind("<<ComboboxSelected>>", lambda e: update_while())
                value_var.trace("w", lambda *args: update_while())
                
            elif loop_type == "for":
                ttk.Label(self.loop_controls_frame, text="Variable name:").pack(anchor="w")
                var_name_var = tk.StringVar(value=block.parameters.get("var_name", "i"))
                var_name_entry = ttk.Entry(self.loop_controls_frame, textvariable=var_name_var)
                var_name_entry.pack(fill="x", pady=(0, 2))
                
                ttk.Label(self.loop_controls_frame, text="Start value:").pack(anchor="w")
                start_var = tk.IntVar(value=block.parameters.get("start_value", 0))
                start_entry = ttk.Entry(self.loop_controls_frame, textvariable=start_var)
                start_entry.pack(fill="x", pady=(0, 2))
                
                ttk.Label(self.loop_controls_frame, text="End value:").pack(anchor="w")
                end_var = tk.IntVar(value=block.parameters.get("end_value", 10))
                end_entry = ttk.Entry(self.loop_controls_frame, textvariable=end_var)
                end_entry.pack(fill="x")
                
                def update_for():
                    block.parameters.update({
                        "loop_type": "for",
                        "var_name": var_name_var.get(),
                        "start_value": start_var.get(),
                        "end_value": end_var.get()
                    })
                    self.redraw_block(block)
                    self.generate_commands()
                
                var_name_var.trace("w", lambda *args: update_for())
                start_var.trace("w", lambda *args: update_for())
                end_var.trace("w", lambda *args: update_for())
                
            elif loop_type == "repeat":
                ttk.Label(self.loop_controls_frame, text="Repeat count:").pack(anchor="w")
                count_var = tk.IntVar(value=block.parameters.get("repeat_count", 5))
                count_entry = ttk.Entry(self.loop_controls_frame, textvariable=count_var)
                count_entry.pack(fill="x")
                
                def update_repeat():
                    block.parameters.update({
                        "loop_type": "repeat",
                        "repeat_count": count_var.get()
                    })
                    self.redraw_block(block)
                    self.generate_commands()
                
                count_var.trace("w", lambda *args: update_repeat())
        
        def on_loop_type_change():
            update_loop_controls()
            
        loop_type_combo.bind("<<ComboboxSelected>>", lambda e: on_loop_type_change())
        update_loop_controls()  # Initialize with current values
        
    def create_conditional_controls(self, block):
        """Create controls for conditional block"""
        ttk.Label(self.properties_frame, text="If condition:").pack(anchor="w")
        condition_var = tk.StringVar(value=block.parameters.get("condition", "pressure"))
        condition_combo = ttk.Combobox(
            self.properties_frame,
            textvariable=condition_var,
            values=["pressure", "flow", "hv_voltage", "hv_current", "temperature"]
        )
        condition_combo.pack(fill="x", pady=(0, 5))
        
        ttk.Label(self.properties_frame, text="Operator:").pack(anchor="w")
        operator_var = tk.StringVar(value=block.parameters.get("operator", "<"))
        operator_combo = ttk.Combobox(
            self.properties_frame,
            textvariable=operator_var,
            values=["<", "<=", ">", ">=", "==", "!="]
        )
        operator_combo.pack(fill="x", pady=(0, 5))
        
        ttk.Label(self.properties_frame, text="Value:").pack(anchor="w")
        value_var = tk.DoubleVar(value=block.parameters.get("value", 100))
        value_entry = ttk.Entry(self.properties_frame, textvariable=value_var)
        value_entry.pack(fill="x")
        
        def update_conditional():
            block.parameters["condition"] = condition_var.get()
            block.parameters["operator"] = operator_var.get()
            block.parameters["value"] = value_var.get()
            self.redraw_block(block)
            self.draw_arrows()
            self.generate_commands()
            
        condition_combo.bind("<<ComboboxSelected>>", lambda e: update_conditional())
        operator_combo.bind("<<ComboboxSelected>>", lambda e: update_conditional())
        value_var.trace("w", lambda *args: update_conditional())
        
        def create_variable_define_controls(self, block):
            """Create controls for variable definition block"""
            ttk.Label(self.properties_frame, text="Variable Name:").pack(anchor="w")
            var_name_var = tk.StringVar(value=block.parameters.get("var_name", "myVar"))
            var_name_entry = ttk.Entry(self.properties_frame, textvariable=var_name_var)
            var_name_entry.pack(fill="x", pady=(0, 5))
            
            ttk.Label(self.properties_frame, text="Value:").pack(anchor="w")
            ttk.Label(self.properties_frame, text="(number or {variable})", 
                    font=("Arial", 8), foreground="gray").pack(anchor="w")
            var_value_var = tk.StringVar(value=block.parameters.get("var_value", "0"))
            var_value_entry = ttk.Entry(self.properties_frame, textvariable=var_value_var)
            var_value_entry.pack(fill="x")
            
            def update_variable():
                block.parameters["var_name"] = var_name_var.get()
                block.parameters["var_value"] = var_value_var.get()
                self.redraw_block(block)
                self.generate_commands()
            
            var_name_var.trace("w", lambda *args: update_variable())
            var_value_var.trace("w", lambda *args: update_variable())
        
    def show_connection_info(self, block):
        """Show connection information for the selected block"""
        ttk.Separator(self.properties_frame, orient="horizontal").pack(fill="x", pady=5)
        ttk.Label(self.properties_frame, text="Connections:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # Outgoing connections
        if block.manual_connections:
            ttk.Label(self.properties_frame, text="Connects to:").pack(anchor="w")
            for target in block.manual_connections:
                conn_frame = ttk.Frame(self.properties_frame)
                conn_frame.pack(fill="x", pady=1)
                
                ttk.Label(conn_frame, text=f"→ {target.block_type}").pack(side="left")
                ttk.Button(
                    conn_frame, 
                    text="Remove", 
                    width=8,
                    command=lambda t=target: self.remove_connection(block, t)
                ).pack(side="right")
        
        # Incoming connections
        if block.incoming_connections:
            ttk.Label(self.properties_frame, text="Connected from:").pack(anchor="w")
            for source in block.incoming_connections:
                ttk.Label(self.properties_frame, text=f"← {source.block_type}").pack(anchor="w")
        
        if not block.manual_connections and not block.incoming_connections:
            ttk.Label(self.properties_frame, text="No custom connections", foreground="gray").pack(anchor="w")
    
    def remove_connection(self, from_block, to_block):
        """Remove a manual connection between blocks"""
        if to_block in from_block.manual_connections:
            from_block.manual_connections.remove(to_block)
        if from_block in to_block.incoming_connections:
            to_block.incoming_connections.remove(from_block)
        
        self.draw_arrows()
        self.update_properties_panel()
        self.generate_commands()
        
    def redraw_block(self, block):
        """Redraw a block after parameter changes"""
        # Remove existing canvas items
        if block.canvas_id:
            self.canvas.delete(block.canvas_id)
        if block.text_id:
            self.canvas.delete(block.text_id)
            
        # Redraw
        self.draw_block(block)
        self.highlight_selected_block()

    def add_block(self, block_type):
        """Add a new block to the canvas"""
        # Create block at center of visible area, snapped to grid
        base_x = self.canvas.canvasx(200)
        base_y = self.canvas.canvasy(100 + len(self.blocks) * 80)
        x, y = self.snap_to_grid(base_x, base_y)
        
        block = CommandBlock(block_type, x, y)
        
        # Set default parameters based on block type
        if block_type == "valve_control":
            block.parameters = {"valve": "fuel", "state": "open"}
        elif block_type == "delay":
            block.parameters = {"duration": 1.0}
        elif block_type == "hv_control":
            block.parameters = {"voltage": 0}
        elif block_type == "pump_control":
            block.parameters = {"state": "on"}
        elif block_type == "mfc_control":
            block.parameters = {"setpoint": 0}
        elif block_type == "wait_condition":
            block.parameters = {"condition": "pressure", "operator": "<", "value": 100}
        elif block_type == "comment":
            block.parameters = {"text": "Enter comment here"}
        elif block_type == "function_call":
            block.parameters = {"function_name": "my_function", "arguments": ""}
        elif block_type == "function_define":
            block.parameters = {"function_name": "my_function"}
        elif block_type == "variable_define":
            block.parameters = {"var_name": "myVar", "var_value": "0"}
        elif block_type == "loop_start":
            block.parameters = {"loop_type": "while", "condition": "pressure", "operator": "<", "value": 100, 
                              "var_name": "i", "start_value": 0, "end_value": 10, "repeat_count": 5}
        elif block_type == "conditional":
            block.parameters = {"condition": "pressure", "operator": "<", "value": 100}
        elif block_type in ["start", "end", "safe_state", "function_return", "loop_end", "else_block", "endif_block"]:
            block.parameters = {}
        
        self.blocks.append(block)
        self.draw_block(block)
        self.draw_arrows()
        self.generate_commands()

    def draw_block(self, block):
        """Draw a block on the canvas"""
        # Color mapping
        colors = {
            "start": "#28a745",
            "valve_control": "#FF6B6B",
            "mfc_control": "#FFA500",
            "delay": "#4ECDC4",
            "hv_control": "#45B7D1",
            "pump_control": "#96CEB4",
            "wait_condition": "#FECA57",
            "safe_state": "#FF9FF3",
            "comment": "#DDA0DD",
            "end": "#dc3545",
            "function_define": "#8A2BE2",
            "function_call": "#9370DB" if not block.is_external_function else "#FF1493",
            "function_return": "#BA55D3",
            "loop_start": "#FF4500",
            "loop_end": "#FF6347",
            "conditional": "#32CD32",
            "else_block": "#90EE90",
            "endif_block": "#98FB98"
        }
        
        color = colors.get(block.block_type, "#CCCCCC")
        
        # Draw rectangle
        block.canvas_id = self.canvas.create_rectangle(
            block.x, block.y,
            block.x + block.width, block.y + block.height,
            fill=color,
            outline="black",
            width=2,
            tags="block"
        )
        
        # Draw text
        block.text_id = self.canvas.create_text(
            block.x + block.width/2, block.y + block.height/2,
            text=block.get_display_text(),
            font=("Arial", 9, "bold"),
            fill="white",
            tags="block"
        )

    def delete_selected_block(self):
        """Delete the currently selected block"""
        if self.selected_block:
            block = self.selected_block
            
            # Remove all connections involving this block
            for target in block.manual_connections[:]:
                self.remove_connection(block, target)
            
            for source in block.incoming_connections[:]:
                self.remove_connection(source, block)
            
            # Remove from canvas
            self.canvas.delete(block.canvas_id)
            self.canvas.delete(block.text_id)
            
            # Remove from blocks list
            self.blocks.remove(block)
            self.selected_block = None
            
            # Update UI
            self.canvas.delete("highlight")
            self.draw_arrows()
            self.update_properties_panel()
            self.generate_commands()

    def clear_all(self):
        """Clear all blocks from the canvas"""
        for block in self.blocks:
            self.canvas.delete(block.canvas_id)
            self.canvas.delete(block.text_id)
            
        self.blocks.clear()
        self.selected_block = None
        self.connection_start_block = None
        self.canvas.delete("highlight")
        self.canvas.delete("arrow")
        self.canvas.delete("connection_highlight")
        self.update_properties_panel()
        self.generate_commands()

    def clear_connections(self):
        """Clear all manual connections"""
        for block in self.blocks:
            block.manual_connections.clear()
            block.incoming_connections.clear()
        self.draw_arrows()
        self.update_properties_panel()
        self.generate_commands()

    def validate_program(self):
        """Validate the program structure"""
        errors = []
        warnings = []
        
        # Check for matching function definitions and returns
        function_starts = [b for b in self.blocks if b.block_type == "function_define"]
        function_returns = [b for b in self.blocks if b.block_type == "function_return"]
        
        if len(function_starts) != len(function_returns):
            errors.append(f"Function definitions ({len(function_starts)}) don't match returns ({len(function_returns)})")
        
        # Check for matching loop starts and ends
        loop_starts = [b for b in self.blocks if b.block_type == "loop_start"]
        loop_ends = [b for b in self.blocks if b.block_type == "loop_end"]
        
        if len(loop_starts) != len(loop_ends):
            errors.append(f"Loop starts ({len(loop_starts)}) don't match loop ends ({len(loop_ends)})")
        
        # Check for matching if/else/endif
        if_blocks = [b for b in self.blocks if b.block_type == "conditional"]
        endif_blocks = [b for b in self.blocks if b.block_type == "endif_block"]
        
        if len(if_blocks) != len(endif_blocks):
            errors.append(f"If statements ({len(if_blocks)}) don't match endif blocks ({len(endif_blocks)})")
        
        # Check for function calls without definitions
        function_calls = [b for b in self.blocks if b.block_type == "function_call"]
        defined_functions = [b.parameters.get("function_name", "") for b in function_starts]
        external_functions = self.function_library.get_available_functions()
        
        for call_block in function_calls:
            func_name = call_block.parameters.get("function_name", "")
            if func_name and func_name not in defined_functions and func_name not in external_functions:
                warnings.append(f"Function '{func_name}' is called but not defined or found in libraries")
        
        # Check external function availability
        external_calls = [b for b in self.blocks if b.is_external_function]
        for call_block in external_calls:
            func_name = call_block.parameters.get("function_name", "")
            if func_name not in external_functions:
                errors.append(f"External function '{func_name}' not found in any library")
        
        # Display results
        result_text = "Program Validation Results:\n\n"
        
        if not errors and not warnings:
            result_text += "✓ Program structure is valid!"
        else:
            if errors:
                result_text += "ERRORS:\n"
                for error in errors:
                    result_text += f"• {error}\n"
                result_text += "\n"
            
            if warnings:
                result_text += "WARNINGS:\n"
                for warning in warnings:
                    result_text += f"• {warning}\n"
        
        # Add library info
        if self.function_library.library_paths:
            result_text += "\nLIBRARY INFO:\n"
            result_text += f"Libraries loaded: {len(self.function_library.library_paths)}\n"
            result_text += f"Functions available: {len(self.function_library.get_available_functions())}\n"
            result_text += f"External calls: {len([b for b in self.blocks if b.is_external_function])}\n"
        
        messagebox.showinfo("Validation Results", result_text)

    def parse_function_definitions(self, sequences):
        """Parse function definitions from sequences"""
        functions = {}
        
        for sequence in sequences:
            i = 0
            while i < len(sequence):
                block = sequence[i]
                if block.block_type == "function_define":
                    func_name = block.parameters.get("function_name", "unknown_function")
                    
                    # Find matching return block
                    func_blocks = []
                    j = i + 1
                    while j < len(sequence):
                        if sequence[j].block_type == "function_return":
                            break
                        func_blocks.append(sequence[j])
                        j += 1
                    
                    functions[func_name] = func_blocks
                    i = j + 1  # Skip past the return block
                else:
                    i += 1
        
        return functions

    def parse_main_execution_sequences(self, sequences):
        """Extract main execution sequences, excluding function definitions"""
        main_sequences = []
        
        for sequence in sequences:
            main_blocks = []
            i = 0
            while i < len(sequence):
                block = sequence[i]
                
                if block.block_type == "function_define":
                    # Skip function definition and its body
                    j = i + 1
                    while j < len(sequence):
                        if sequence[j].block_type == "function_return":
                            break
                        j += 1
                    i = j + 1  # Skip past the return block
                else:
                    main_blocks.append(block)
                    i += 1
            
            if main_blocks:
                main_sequences.append(main_blocks)
        
        return main_sequences

    def process_block_sequence(self, sequence, indent_level=0, add_step_numbers=False):
        """Process a sequence of blocks with proper structure handling"""
        commands = []
        
        if not sequence:
            return commands
        
        loop_stack = []
        conditional_stack = []
        step_counter = 1
        
        i = 0
        while i < len(sequence):
            block = sequence[i]
            indent = "    " * indent_level
            
            # Handle loop structures
            if block.block_type == "loop_start":
                if add_step_numbers:
                    commands.append(f"{indent}# Step {step_counter}: Loop Start")
                    step_counter += 1
                else:
                    commands.append(f"{indent}# Loop start: {block.get_display_text()}")
                
                commands.append(f"{indent}{block.get_command_text()}")
                loop_stack.append(block)
                indent_level += 1
                
            elif block.block_type == "loop_end":
                if loop_stack:
                    loop_block = loop_stack.pop()
                    indent_level = max(0, indent_level - 1)
                    indent = "    " * indent_level
                    
                    if add_step_numbers:
                        commands.append(f"{indent}# Step {step_counter}: Loop End")
                        step_counter += 1
                    
                    commands.append(f"{indent}END_LOOP  # End of {loop_block.parameters.get('loop_type', 'while')} loop")
            
            # Handle conditional structures
            elif block.block_type == "conditional":
                if add_step_numbers:
                    commands.append(f"{indent}# Step {step_counter}: Conditional")
                    step_counter += 1
                else:
                    commands.append(f"{indent}# Conditional: {block.get_display_text()}")
                
                commands.append(f"{indent}{block.get_command_text()}")
                conditional_stack.append(block)
                indent_level += 1
                
            elif block.block_type == "else_block":
                if conditional_stack:
                    indent_level = max(0, indent_level - 1)
                    indent = "    " * indent_level
                    
                    if add_step_numbers:
                        commands.append(f"{indent}# Step {step_counter}: Else")
                        step_counter += 1
                    
                    commands.append(f"{indent}ELSE")
                    indent_level += 1
                    
            elif block.block_type == "endif_block":
                if conditional_stack:
                    conditional_stack.pop()
                    indent_level = max(0, indent_level - 1)
                    indent = "    " * indent_level
                    
                    if add_step_numbers:
                        commands.append(f"{indent}# Step {step_counter}: End If")
                        step_counter += 1
                    
                    commands.append(f"{indent}END_IF")
            
            # Handle regular command blocks
            elif block.block_type not in ["function_define", "function_return"]:
                if add_step_numbers:
                    commands.append(f"{indent}# Step {step_counter}: {block.block_type.replace('_', ' ').title()}")
                    step_counter += 1
                elif block.block_type != "comment" or block.parameters.get("text", "").strip():
                    commands.append(f"{indent}# {block.get_display_text()}")
                
                commands.append(f"{indent}{block.get_command_text()}")
                
                # Handle custom connections
                if block.manual_connections:
                    for target in block.manual_connections:
                        commands.append(f"{indent}# Custom connection triggers:")
                        commands.append(f"{indent}#   → {target.block_type}: {target.get_display_text()}")
            
            i += 1
        
        return commands

    def generate_execution_summary(self, sequences):
        """Generate execution summary"""
        commands = ["# === EXECUTION SUMMARY ==="]
        
        for i, sequence in enumerate(sequences):
            if sequence:
                commands.append(f"# Sequence {i + 1}: {len(sequence)} blocks")
                for j, block in enumerate(sequence):
                    features = []
                    if block.manual_connections:
                        targets = [t.block_type for t in block.manual_connections]
                        features.append(f"→ {', '.join(targets)}")
                    if block.incoming_connections:
                        sources = [s.block_type for s in block.incoming_connections]
                        features.append(f"← {', '.join(sources)}")
                    
                    feature_str = f" ({', '.join(features)})" if features else ""
                    commands.append(f"#   {j + 1}. {block.block_type.replace('_', ' ').title()}{feature_str}")
        
        return commands

    def generate_validation_warnings(self):
        """Generate validation warnings"""
        commands = ["", "# === VALIDATION NOTES ==="]
        
        # Check for unmatched structures
        loop_starts = len([b for b in self.blocks if b.block_type == "loop_start"])
        loop_ends = len([b for b in self.blocks if b.block_type == "loop_end"])
        if loop_starts != loop_ends:
            commands.append(f"# WARNING: Unmatched loops ({loop_starts} starts, {loop_ends} ends)")
        
        if_blocks = len([b for b in self.blocks if b.block_type == "conditional"])
        endif_blocks = len([b for b in self.blocks if b.block_type == "endif_block"])
        if if_blocks != endif_blocks:
            commands.append(f"# WARNING: Unmatched conditionals ({if_blocks} ifs, {endif_blocks} endifs)")
        
        func_defs = len([b for b in self.blocks if b.block_type == "function_define"])
        func_returns = len([b for b in self.blocks if b.block_type == "function_return"])
        if func_defs != func_returns:
            commands.append(f"# WARNING: Unmatched functions ({func_defs} definitions, {func_returns} returns)")
        
        # Check for proper function structure
        function_warnings = self.validate_function_structures()
        commands.extend(function_warnings)
        
        # Check for proper loop nesting
        loop_warnings = self.validate_loop_nesting()
        commands.extend(loop_warnings)
        
        if (loop_starts == loop_ends and if_blocks == endif_blocks and 
            func_defs == func_returns and not function_warnings and not loop_warnings):
            commands.append("# All program structures are properly matched and nested")
        
        return commands

    def validate_function_structures(self):
        """Validate function definition structures"""
        warnings = []
        sequences = self.get_parallel_sequences()
        
        for seq_idx, sequence in enumerate(sequences):
            func_depth = 0
            for block in sequence:
                if block.block_type == "function_define":
                    if func_depth > 0:
                        warnings.append(f"# WARNING: Nested function definition in sequence {seq_idx + 1}")
                    func_depth += 1
                elif block.block_type == "function_return":
                    if func_depth == 0:
                        warnings.append(f"# WARNING: Function return without definition in sequence {seq_idx + 1}")
                    func_depth = max(0, func_depth - 1)
        
        return warnings

    def validate_loop_nesting(self):
        """Validate loop nesting structures"""
        warnings = []
        sequences = self.get_parallel_sequences()
        
        for seq_idx, sequence in enumerate(sequences):
            loop_stack = []
            for block in sequence:
                if block.block_type == "loop_start":
                    loop_stack.append(block)
                elif block.block_type == "loop_end":
                    if not loop_stack:
                        warnings.append(f"# WARNING: Loop end without start in sequence {seq_idx + 1}")
                    else:
                        loop_stack.pop()
            
            if loop_stack:
                warnings.append(f"# WARNING: Unclosed loops in sequence {seq_idx + 1}")
        
        return warnings

    def generate_commands(self):
        """Generate command text from blocks with integrated AutoRun support"""
        commands = []
        sequences = self.get_parallel_sequences()
        
        commands.append("# Generated Fusor Command Sequence v6 - Complete Integration")
        commands.append(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        commands.append(f"# Canvas Size: {self.canvas_width}x{self.canvas_height}")
        commands.append(f"# Total blocks: {len(self.blocks)}")
        commands.append(f"# Parallel sequences: {len(sequences)}")
        
        # Add function library information
        if self.function_library.library_paths:
            commands.append(f"# Function libraries: {len(self.function_library.library_paths)}")
            commands.append(f"# Available external functions: {len(self.function_library.get_available_functions())}")
        
        # Count features
        total_connections = sum(len(block.manual_connections) for block in self.blocks)
        function_defs = len([b for b in self.blocks if b.block_type == "function_define"])
        function_calls = len([b for b in self.blocks if b.block_type == "function_call"])
        loops = len([b for b in self.blocks if b.block_type == "loop_start"])
        conditionals = len([b for b in self.blocks if b.block_type == "conditional"])
        external_function_calls = [b for b in self.blocks if b.is_external_function]
        
        commands.append(f"# Custom Connections: {total_connections}")
        commands.append(f"# Functions Defined: {function_defs}")
        commands.append(f"# Function Calls: {function_calls}")
        commands.append(f"# External Function Calls: {len(external_function_calls)}")
        commands.append(f"# Loops: {loops}")
        commands.append(f"# Conditionals: {conditionals}")
        commands.append("")
        
        # AutoRun compatible format - Library paths
        if self.function_library.library_paths:
            commands.append("# === AUTORUN CONFIGURATION ===")
            commands.append("# [AUTORUN:LIBRARIES]")
            for lib_path in self.function_library.library_paths:
                commands.append(f"# LIBRARY_PATH={lib_path}")
            commands.append("# [/AUTORUN:LIBRARIES]")
            commands.append("")
        
        # AutoRun compatible format - External function mappings
        if external_function_calls:
            commands.append("# [AUTORUN:EXTERNAL_FUNCTIONS]")
            for block in external_function_calls:
                func_name = block.parameters.get("function_name")
                func_path = block.function_file_path
                if func_name and func_path:
                    commands.append(f"# FUNCTION_MAP={func_name}:{func_path}")
            commands.append("# [/AUTORUN:EXTERNAL_FUNCTIONS]")
            commands.append("")
        
        # Parse and separate function definitions from main execution
        parsed_functions = self.parse_function_definitions(sequences)
        main_sequences = self.parse_main_execution_sequences(sequences)
        
        # Generate function definitions first
        if parsed_functions:
            commands.append("# === FUNCTION DEFINITIONS ===")
            for func_name, func_blocks in parsed_functions.items():
                commands.append(f"")
                commands.append(f"FUNCTION {func_name}:")
                commands.append(f"    # Function: {func_name}")
                
                # Process function body with proper structure handling
                func_commands = self.process_block_sequence(func_blocks, indent_level=1)
                commands.extend(func_commands)
                
                commands.append(f"    RETURN")
                commands.append(f"END_FUNCTION")
            commands.append("")
        
        # Show custom connections summary
        if total_connections > 0:
            commands.append("# === CUSTOM CONNECTION MAP ===")
            for block in self.blocks:
                if block.manual_connections:
                    for target in block.manual_connections:
                        commands.append(f"# {block.block_type} → {target.block_type}")
            commands.append("")
        
        # Generate main program execution
        commands.append("# === MAIN PROGRAM EXECUTION ===")
        commands.append("")
        
        if len(main_sequences) == 1 and total_connections == 0 and not parsed_functions:
            # Simple sequential execution
            sequence = main_sequences[0]
            commands.append("# Simple sequential execution:")
            main_commands = self.process_block_sequence(sequence, indent_level=0, add_step_numbers=True)
            commands.extend(main_commands)
        else:
            # Complex execution with advanced features
            commands.append("# ADVANCED EXECUTION MODE")
            commands.append("# Supports functions, loops, conditionals, and parallel sequences")
            commands.append("")
            
            # Process each main sequence
            for seq_idx, sequence in enumerate(main_sequences):
                if not sequence:
                    continue
                    
                commands.append(f"# === SEQUENCE {seq_idx + 1} ===")
                
                seq_commands = self.process_block_sequence(sequence, indent_level=0)
                commands.extend(seq_commands)
                commands.append("")
        
        # Add execution summary
        commands.extend(self.generate_execution_summary(sequences))
        
        # Add validation warnings
        commands.extend(self.generate_validation_warnings())
        
        command_text = "\n".join(commands)
        
        # Update preview
        self.command_text.delete(1.0, tk.END)
        self.command_text.insert(1.0, command_text)
        
        return command_text

    def save_program(self):
        """Save the current program to a JSON file"""
        if not self.blocks:
            messagebox.showwarning("Warning", "No blocks to save!")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            program_data = {
                "version": "6.0",
                "created": datetime.now().isoformat(),
                "canvas_size": {"width": self.canvas_width, "height": self.canvas_height},
                "function_libraries": self.function_library.library_paths,
                "blocks": [],
                "connections": []
            }
            
            for block in self.blocks:
                block_data = {
                    "type": block.block_type,
                    "x": block.x,
                    "y": block.y,
                    "parameters": block.parameters,
                    "is_external_function": block.is_external_function,
                    "function_file_path": block.function_file_path
                }
                program_data["blocks"].append(block_data)
            
            # Save connections
            for i, block in enumerate(self.blocks):
                for target in block.manual_connections:
                    target_idx = self.blocks.index(target)
                    program_data["connections"].append({
                        "from": i,
                        "to": target_idx
                    })
                
            try:
                with open(filename, 'w') as f:
                    json.dump(program_data, f, indent=2)
                messagebox.showinfo("Success", f"Program saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save program: {e}")

    def load_program(self):
        """Load a program from a JSON file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    program_data = json.load(f)
                    
                # Clear existing blocks
                self.clear_all()
                
                # Load canvas size if available
                if "canvas_size" in program_data:
                    self.canvas_width = program_data["canvas_size"].get("width", 2000)
                    self.canvas_height = program_data["canvas_size"].get("height", 2000)
                    self.canvas.configure(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
                
                # Load function libraries
                for lib_path in program_data.get("function_libraries", []):
                    if os.path.isdir(lib_path):
                        self.function_library.add_library_path(lib_path)
                
                self.update_functions_list()
                
                # Load blocks
                for block_data in program_data.get("blocks", []):
                    x, y = self.snap_to_grid(block_data["x"], block_data["y"])
                    block = CommandBlock(
                        block_data["type"],
                        x, y,
                        **block_data["parameters"]
                    )
                    
                    # Restore external function properties
                    block.is_external_function = block_data.get("is_external_function", False)
                    block.function_file_path = block_data.get("function_file_path")
                    
                    self.blocks.append(block)
                    self.draw_block(block)
                
                # Load connections
                for conn in program_data.get("connections", []):
                    from_block = self.blocks[conn["from"]]
                    to_block = self.blocks[conn["to"]]
                    self.create_manual_connection(from_block, to_block)
                    
                self.draw_arrows()
                self.generate_commands()
                messagebox.showinfo("Success", f"Program loaded from {filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load program: {e}")

    def export_csv(self):
        """Export commands to CSV file with AutoRun compatibility"""
        if not self.blocks:
            messagebox.showwarning("Warning", "No blocks to export!")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export to CSV"
        )
        
        if filename:
            try:
                sequences = self.get_parallel_sequences()
                
                with open(filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # AutoRun header section
                    writer.writerow(['# Fusor AutoRun Program v6'])
                    writer.writerow([f'# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
                    writer.writerow([f'# Canvas Size: {self.canvas_width}x{self.canvas_height}'])
                    writer.writerow([f'# Total blocks: {len(self.blocks)}'])
                    
                    # Function library information for AutoRun
                    if self.function_library.library_paths:
                        writer.writerow(['# === AUTORUN CONFIGURATION ==='])
                        for lib_path in self.function_library.library_paths:
                            writer.writerow([f'# LIBRARY_PATH={lib_path}'])
                        writer.writerow([''])
                    
                    # External function mappings for AutoRun
                    external_functions = [b for b in self.blocks if b.is_external_function and b.block_type == "function_call"]
                    if external_functions:
                        writer.writerow(['# === EXTERNAL FUNCTION MAPPINGS ==='])
                        for block in external_functions:
                            func_name = block.parameters.get("function_name")
                            func_path = block.function_file_path
                            writer.writerow([f'# FUNCTION_MAP={func_name}:{func_path}'])
                        writer.writerow([''])
                    
                    # Main data header
                    writer.writerow(['Sequence', 'Step', 'Block_Type', 'Command', 'Parameters', 
                                   'X_Position', 'Y_Position', 'Connections', 'Is_External', 'Function_File'])
                    
                    # Export block data
                    for seq_idx, sequence in enumerate(sequences):
                        for step_idx, block in enumerate(sequence):
                            connections = ', '.join([t.block_type for t in block.manual_connections])
                            writer.writerow([
                                seq_idx + 1,
                                step_idx + 1,
                                block.block_type,
                                block.get_command_text(),
                                json.dumps(block.parameters),
                                block.x,
                                block.y,
                                connections,
                                block.is_external_function,
                                block.function_file_path or ""
                            ])
                    
                    # Add AutoRun execution instructions
                    writer.writerow([''])
                    writer.writerow(['# === AUTORUN EXECUTION INSTRUCTIONS ==='])
                    writer.writerow(['# 1. Load this file in AutoRun v2.0 or later'])
                    writer.writerow(['# 2. AutoRun will automatically detect library paths'])
                    writer.writerow(['# 3. External functions will be resolved from mapped files'])
                    writer.writerow(['# 4. Execute with: autorun.exe -f ' + os.path.basename(filename)])
                    
                messagebox.showinfo("Success", f"Program exported to {filename} with AutoRun compatibility")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export CSV: {e}")

    def run(self):
        """Start the application"""
        self.root.mainloop()

if __name__ == "__main__":
    app = FusorCommandGenerator()
    app.run()