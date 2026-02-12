import optuna
import pandas as pd
import matplotlib.pyplot as plt
import os
import urllib.parse

# ==========================================
# CONFIGURATION
# ==========================================

# Database connection parameters
db_user = "optuna"
raw_password = "NbUQ*BP+RtT;3oAX" 
db_password = urllib.parse.quote_plus(raw_password)
db_host = "10.44.0.72"
db_port = "5432"
db_name = "test_db" 

STORAGE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
STUDY_NAME = "gcpu_smu_svd_pipe_v1"

# Directory containing your trial logs
LOGS_BASE_DIR = "/usr/local/google/gcpu/prj-cad/tianenc/gcpu_smu_svd_pipe_parameterized/optuna_cts/20251111_gcpu_smu_svd_pipe/run" 
LOG_FILENAME = "clock.log"

# ==========================================

def get_optuna_data(db_url, study_name):
    """
    Connects to the Optuna database and extracts the trial numbers and objective values.
    Returns a dictionary: {trial_number: objective_value}
    """
    print(f"Connecting to Optuna study '{study_name}'...")
    try:
        study = optuna.load_study(study_name=study_name, storage=db_url)
        # Get dataframe with only the necessary attributes to save memory
        df = study.trials_dataframe(attrs=('number', 'value', 'state'))
        
        # Filter for only COMPLETE trials to avoid plotting failed/pruned ones
        df_complete = df[df['state'] == 'COMPLETE']
        
        # Create a dictionary mapping trial number to its objective score
        scores_dict = dict(zip(df_complete['number'], df_complete['value']))
        print(f"Successfully loaded {len(scores_dict)} completed trials from database.")
        return scores_dict
        
    except Exception as e:
        print(f"Database connection error: {e}")
        print("Please ensure your DB parameters are correct and the PostgreSQL server is reachable.")
        return {}

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

def main():
    # 1. Fetch Objective Scores from DB
    optuna_scores = get_optuna_data(STORAGE_URL, STUDY_NAME)
    if not optuna_scores:
        return
        
    # Sort trials to ensure the plot goes left-to-right properly
    trials = sorted(optuna_scores.keys())
    
    # Lists to hold the aligned data
    plot_trials = []
    plot_obj_scores = []
    plot_latencies = []
    plot_skews = []
    
    print("\nScanning log files...")
    # 2. Extract Data from Log Files
    for trial_num in trials:
        # Formulate the path to match the specified directory structure
        trial_folder = f"gcpu_smu_svd_pipe_v1_trial_{trial_num}"
        log_path = os.path.join(LOGS_BASE_DIR, trial_folder, "main", "pnr", "clock", "logs", LOG_FILENAME)
        
        if os.path.exists(log_path):
            log_data = parse_clock_log(log_path)
            if log_data:
                latency, skew = log_data
                plot_trials.append(trial_num)
                plot_obj_scores.append(optuna_scores[trial_num])
                plot_latencies.append(latency)
                plot_skews.append(skew)
                print(f"  Trial {trial_num}: Extracted Max Latency = {latency}, Skew = {skew}")
            else:
                print(f"  [!] Log parsed but no valid skew/latency data found in: {log_path}")
        else:
            print(f"  [!] Log file not found: {log_path}")

    if not plot_trials:
        print("\nNo overlapping data found between Optuna DB and log files. Cannot generate plot.")
        return
        
    print(f"\nPlotting data for {len(plot_trials)} trials...")

    # 3. Create the Subplots
    # Create 2 subplots sharing the same X-axis
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # --- Top Plot: Objective Score ---
    color_obj = '#2ca02c' # Green
    
    ax1.set_ylabel('Objective Score', color=color_obj, fontsize=12, fontweight='bold')
    ax1.plot(plot_trials, plot_obj_scores, marker='o', linestyle='-', color=color_obj, linewidth=2, label='Objective Score (DB)')
    ax1.tick_params(axis='y', labelcolor=color_obj)
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.legend(loc='upper right', frameon=True, shadow=True)
    ax1.set_title(f'Study: {STUDY_NAME} - Optimization vs Log Extraction', pad=20, fontsize=14, fontweight='bold')

    # --- Bottom Plot: Max Skew & Max Latency ---
    color_skew = '#1f77b4' # Blue
    color_lat = '#d62728' # Red
    
    ax2.set_xlabel('Trial Number', fontsize=12, fontweight='bold')
    
    # Left Y-Axis of Bottom Plot: Max Skew
    ax2.set_ylabel('Max Skew', color=color_skew, fontsize=12, fontweight='bold')
    line2, = ax2.plot(plot_trials, plot_skews, marker='^', linestyle='--', color=color_skew, linewidth=2, label='Max Skew (Log)')
    # Add Skew Baseline
    line_base_skew = ax2.axhline(y=0.06, color=color_skew, linestyle=':', linewidth=2, alpha=0.6, label='Skew Baseline (0.06)')
    
    ax2.tick_params(axis='y', labelcolor=color_skew)
    ax2.grid(True, linestyle=':', alpha=0.7)

    # Right Y-Axis of Bottom Plot: Max Latency
    ax3 = ax2.twinx()  
    ax3.set_ylabel('Max Latency', color=color_lat, fontsize=12, fontweight='bold')
    line3, = ax3.plot(plot_trials, plot_latencies, marker='s', linestyle='-', color=color_lat, linewidth=2, label='Max Latency (Log)')
    # Add Latency Baseline
    line_base_lat = ax3.axhline(y=0.105, color=color_lat, linestyle=':', linewidth=2, alpha=0.6, label='Latency Baseline (0.105)')
    
    ax3.tick_params(axis='y', labelcolor=color_lat)

    # Combine legends for the bottom plot (including baselines)
    lines_bottom = [line2, line_base_skew, line3, line_base_lat]
    labels_bottom = [l.get_label() for l in lines_bottom]
    ax2.legend(lines_bottom, labels_bottom, loc='upper right', frameon=True, shadow=True)

    # Adjust spacing and save
    plt.tight_layout()
    
    # Save the figure instead of showing it
    output_filename = f"{STUDY_NAME}_plot.png"
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"\nPlot successfully saved to: {output_filename}")

if __name__ == "__main__":
    main()