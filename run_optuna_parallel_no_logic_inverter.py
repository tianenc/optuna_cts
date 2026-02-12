import optuna
import os
import subprocess
import re
import logging
import sys
import urllib.parse
import argparse

# --- DEFAULT CONFIGURATION (Overridden by CLI args) ---
SCRIPT_PATH = './run_flow.sh'
WA_NAME = '20260114_gcpu_smu_svd_pipe'
BASE_VAR_FILE = 'gcpu_smu_svd_pipe.var'
STUDY_NAME = "gcpu_smu_svd_pipe_no_INVD_parallel_v1"
RUN_PREFIX = "optuna_run"  # Prefix for generated run_names
BLOCK_NAME = "gcpu_smu_svd_pipe" # Default block name
SOURCE_DIR_BASE = "/path/to/source/parent" # Default source path

# --- SQL CONFIGURATION ---
db_user = "optuna"
raw_password = "NbUQ*BP+RtT;3oAX" 
db_password = urllib.parse.quote_plus(raw_password)
db_host = "10.44.0.72"
db_port = "5432"
db_name = "test_db" 

STORAGE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

N_TRIALS_PER_WORKER = 30 
SKEW_CONSTRAINT = 0.06

# --- FILE PATHS ---
USABLE_INVERTERS_FILE = 'usable_inverters.list'
USABLE_BUFFERS_FILE = 'usable_buffers.list'


def load_cells_from_file(filepath):
    """Loads a list of cells from a file, one cell per line."""
    if not os.path.exists(filepath):
        # We don't exit here immediately to allow --help to run even if files are missing
        return []
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip()]

# Load lists globally
FULL_INVERTER_LIST = load_cells_from_file(USABLE_INVERTERS_FILE)
FULL_BUFFER_LIST = load_cells_from_file(USABLE_BUFFERS_FILE)


def filter_cells_by_criteria(full_cell_list, vt_choice, min_drive, max_drive):
    """Filters cells based on VT type and drive strength."""
    selected_cells = []
    drive_strength_pattern = re.compile(r'D(\d+P\d+|\d+)')

    for cell in full_cell_list:
        if vt_choice in cell:
            match = drive_strength_pattern.search(cell)
            if match:
                try:
                    strength_str = match.group(1)
                    strength = float(strength_str.replace('P', '.'))
                    if min_drive <= strength <= max_drive:
                        selected_cells.append(cell)
                except (ValueError, IndexError):
                    continue
    return selected_cells


def parse_clock_log(filepath):
    """
    Parses a single clock.log file to extract Max ID (Latency) and Skew.
    Tracks the maximum skew found to avoid grabbing 'early' corners or minor groups.
    Returns a tuple (max_latency, skew) or None if not found.
    """
    max_skew_found = -1.0
    associated_latency = -1.0
    found_valid_data = False
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Identify the row by checking for key identifiers
                if "ssgnp_" in line and "CLK/" in line:
                    parts = line.split()
                    try:
                        # Find exactly where the data starts to handle timestamps robustly
                        base_idx = next(i for i, part in enumerate(parts) if part.startswith("ssgnp_"))
                        
                        # base_idx + 0 = Half-corner
                        # base_idx + 1 = Skew Group
                        # base_idx + 2 = Min ID
                        # base_idx + 3 = Max ID (Latency)
                        # base_idx + 4 = Skew
                        
                        max_latency = float(parts[base_idx + 3])
                        skew = float(parts[base_idx + 4])
                        
                        # Keep the maximum skew found across all corners/groups
                        if skew > max_skew_found:
                            max_skew_found = skew
                            associated_latency = max_latency
                            found_valid_data = True
                            
                    except (IndexError, ValueError, StopIteration):
                        continue
                        
        if found_valid_data:
            return associated_latency, max_skew_found
            
    except Exception as e:
        print(f"  [!] Error reading {filepath}: {e}")
        
    return None



optuna.logging.set_verbosity(optuna.logging.INFO)


def objective(trial):
    """The main objective function."""
    # Access globals set by argparse
    global SCRIPT_PATH, WA_NAME, BASE_VAR_FILE, RUN_PREFIX, SKEW_CONSTRAINT, BLOCK_NAME, SOURCE_DIR_BASE

    trial_num = trial.number
    
    # --- Optuna Suggestions ---
    vt_choice = trial.suggest_categorical('vt_type', ['ULVTLL', 'LVTLL', 'LVT', 'SVT'])
    min_drive = trial.suggest_int('min_drive_strength', 1, 8)
    max_drive = trial.suggest_int('max_drive_strength', min_drive, 16)
    
    # --- Dynamic Naming ---
    # We use the prefix to generate unique run_names and var_files
    run_name = f'{RUN_PREFIX}_trial_{trial_num}'
    var_file_name = f'vars_{RUN_PREFIX}_trial_{trial_num}.var'

    # Read base config
    if not os.path.exists(BASE_VAR_FILE):
        print(f"FATAL: Base var file not found at {BASE_VAR_FILE}")
        return float('inf')

    with open(BASE_VAR_FILE, 'r') as f:
        base_var_content = f.read()

    # --- Cell Filtering Logic ---
    selected_buffers = filter_cells_by_criteria(FULL_BUFFER_LIST, vt_choice, min_drive, max_drive)
    inverters_to_ban = [c for c in FULL_INVERTER_LIST if c.startswith('INV')]
    clock_inverter_candidates = [c for c in FULL_INVERTER_LIST if not c.startswith('INV')]
    selected_inverters = filter_cells_by_criteria(clock_inverter_candidates, vt_choice, min_drive, max_drive)

    # --- Failsafe ---
    MIN_CELL_COUNT = 6
    if len(selected_inverters) < MIN_CELL_COUNT:
        failsafe = [c for c in clock_inverter_candidates if vt_choice in c]
        selected_inverters = failsafe[:MIN_CELL_COUNT]
    if len(selected_buffers) < MIN_CELL_COUNT:
        failsafe = [c for c in FULL_BUFFER_LIST if vt_choice in c]
        selected_buffers = failsafe[:MIN_CELL_COUNT]

    buffers_str = " ".join(selected_buffers)
    allowed_inverters_str = " ".join(selected_inverters)

    # --- Generate Var File ---
    optuna_var_content = f"""
# --- Optuna Trial #{trial_num} Overrides ---
bbappend pnr.innovus.ClockBuildClockTreePreCallback {{
    puts "INFO (Optuna): Enforcing Clock Inverters Only (No INVD) and Buffers..."
    set_ccopt_property inverter_cells {{{allowed_inverters_str}}}
    set_ccopt_property buffer_cells {{{buffers_str}}}
}}
"""
    final_var_content = base_var_content + "\n" + optuna_var_content

    with open(var_file_name, 'w') as f:
        f.write(final_var_content)

    print(f"--- Starting Trial {trial_num} with run_name: {run_name} ---")
    log_file_path = f"logs/{run_name}.log"
    os.makedirs("logs", exist_ok=True)
    
    # --- Execute Bash Script ---
    # Passing 5 arguments: run_name, var_file, wa_name, block_name, source_dir
    try:
        with open(log_file_path, 'w') as log_file:
            subprocess.run(
                [
                    SCRIPT_PATH, 
                    run_name, 
                    "../../" + var_file_name, 
                    WA_NAME, 
                    BLOCK_NAME, 
                    SOURCE_DIR_BASE
                ], 
                check=True, universal_newlines=True,
                stdout=log_file, stderr=subprocess.STDOUT
            )
    except subprocess.CalledProcessError:
        print(f"Error running bash script. Check {log_file_path}")
        return float('inf')

    # --- Parse Results ---
    log_file_path_for_parsing = os.path.join(WA_NAME, 'run', run_name, 'main', 'pnr', 'clock', 'logs', 'clock.log')
    max_latency, skew = parse_clock_log(log_file_path_for_parsing)

    if max_latency is None or skew is None:
        print(f"Trial {trial_num} failed: Could not parse results.")
        return float('inf')

    # --- Objective Calculation ---
    objective_value = max_latency 
    if skew > SKEW_CONSTRAINT:
        penalty = (skew - SKEW_CONSTRAINT) * 100
        objective_value += penalty
        print(f"Applied skew penalty. Obj: {objective_value:.4f}")

    return objective_value


if __name__ == "__main__":
    # --- ARGUMENT PARSING ---
    parser = argparse.ArgumentParser(description="Run Optuna Worker")
    
    # Core Parameters
    parser.add_argument("--wa-name", default=WA_NAME, help="Workspace Name")
    parser.add_argument("--base-var", default=BASE_VAR_FILE, help="Base .var file path")
    parser.add_argument("--study-name", default=STUDY_NAME, help="Optuna Study Name")
    parser.add_argument("--run-prefix", default="optuna_v1", help="Prefix for run_name and var_file")
    
    # Script Execution Parameters
    parser.add_argument("--script-path", default=SCRIPT_PATH, help="Path to run_flow.sh")
    parser.add_argument("--block-name", default=BLOCK_NAME, help="Block name (e.g. gcpu_smu_svd_pipe)")
    parser.add_argument("--source-dir", default=SOURCE_DIR_BASE, help="Source directory base")
    
    # Optimization Parameters
    parser.add_argument("--trials", type=int, default=30, help="Number of trials")
    parser.add_argument("--skew-constraint", type=float, default=0.06, help="Skew constraint in ns")

    args = parser.parse_args()

    # Apply arguments to globals
    WA_NAME = args.wa_name
    BASE_VAR_FILE = args.base_var
    STUDY_NAME = args.study_name
    RUN_PREFIX = args.run_prefix
    SCRIPT_PATH = args.script_path
    BLOCK_NAME = args.block_name
    SOURCE_DIR_BASE = args.source_dir
    SKEW_CONSTRAINT = args.skew_constraint

    # --- Validation ---
    if not FULL_INVERTER_LIST or not FULL_BUFFER_LIST:
        print("ERROR: Cell list files (usable_*.list) not found or empty.")
        sys.exit(1)

    print(f"Worker connected to {STUDY_NAME}")
    print(f"Target WA: {WA_NAME} | Prefix: {RUN_PREFIX}")

    study = optuna.create_study(
        study_name=STUDY_NAME,
        storage=STORAGE_URL,
        load_if_exists=True,
        direction="minimize"
    )
    
    study.optimize(objective, n_trials=args.trials)