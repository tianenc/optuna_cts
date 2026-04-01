#!/usr/bin/env python3
"""
Optuna-based CTS Optimizer
Optimizes clock tree synthesis parameters by suggesting cell selections and drive strengths.
Supports both SQLite and PostgreSQL backends.
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional, Tuple

import optuna

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class OptimizerConfig:
    wa_name: str
    base_var: str
    study_name: str
    run_prefix: str
    script_path: str
    block_name: str
    source_dir: str
    trials: int
    skew_constraint: float
    storage_url: str
    vt_types: List[str]
    min_drive_range: Tuple[int, int]
    max_drive_range: Tuple[int, int]
    buffer_list_path: str = 'usable_buffers.list'
    inverter_list_path: str = 'usable_inverters.list'

class CTSObjective:
    def __init__(self, config: OptimizerConfig):
        self.config = config
        self.full_buffers = self._load_cells(config.buffer_list_path)
        self.full_inverters = self._load_cells(config.inverter_list_path)
        
        if not self.full_buffers or not self.full_inverters:
            logger.error("Required cell list files are missing or empty.")
            sys.exit(1)

    def _load_cells(self, filepath: str) -> List[str]:
        if not os.path.exists(filepath):
            logger.warning(f"File not found: {filepath}")
            return []
        with open(filepath, 'r') as f:
            return [line.strip() for line in f if line.strip()]

    def _filter_cells(self, cell_list: List[str], vt: str, min_d: int, max_d: int) -> List[str]:
        selected = []
        # Matches D1, D2, D0P5, etc.
        pattern = re.compile(r'D(\d+P\d+|\d+)')
        for cell in cell_list:
            if vt in cell:
                match = pattern.search(cell)
                if match:
                    try:
                        strength = float(match.group(1).replace('P', '.'))
                        if min_d <= strength <= max_d:
                            selected.append(cell)
                    except ValueError:
                        continue
        return selected

    def parse_clock_log(self, log_path: str) -> Tuple[Optional[float], Optional[float]]:
        """Extracts Max Latency and Skew from clock.log."""
        if not os.path.exists(log_path):
            return None, None

        max_skew = -1.0
        max_latency = -1.0
        found = False

        try:
            with open(log_path, 'r') as f:
                for line in f:
                    if "ssgnp_" in line and "CLK/" in line:
                        parts = line.split()
                        try:
                            # Robustly find data columns
                            base_idx = next(i for i, p in enumerate(parts) if p.startswith("ssgnp_"))
                            latency = float(parts[base_idx + 3])
                            skew = float(parts[base_idx + 4])
                            if skew > max_skew:
                                max_skew = skew
                                max_latency = latency
                                found = True
                        except (IndexError, ValueError, StopIteration):
                            continue
        except Exception as e:
            logger.error(f"Error parsing log {log_path}: {e}")
            
        return (max_latency, max_skew) if found else (None, None)

    def __call__(self, trial: optuna.Trial) -> float:
        trial_num = trial.number
        vt = trial.suggest_categorical('vt_type', self.config.vt_types)
        min_d = trial.suggest_int('min_drive', *self.config.min_drive_range)
        max_d = trial.suggest_int('max_drive', max(min_d, self.config.max_drive_range[0]), self.config.max_drive_range[1])

        run_name = f"{self.config.run_prefix}_trial_{trial_num}"
        var_file = f"vars_{run_name}.var"

        # Prepare overrides
        sel_bufs = self._filter_cells(self.full_buffers, vt, min_d, max_d)
        # Exclude standard INVD cells as requested in previous scripts
        inv_candidates = [c for c in self.full_inverters if not c.startswith('INV')]
        sel_invs = self._filter_cells(inv_candidates, vt, min_d, max_d)

        # Failsafe: Ensure we have enough cells
        if len(sel_bufs) < 5: sel_bufs = [c for c in self.full_buffers if vt in c][:10]
        if len(sel_invs) < 5: sel_invs = [c for c in inv_candidates if vt in c][:10]

        buf_str = " ".join(sel_bufs)
        inv_str = " ".join(sel_invs)

        # Read base var file
        if not os.path.exists(self.config.base_var):
            logger.error(f"Base var file {self.config.base_var} missing.")
            return float('inf')

        with open(self.config.base_var, 'r') as f:
            content = f.read()

        overrides = f"""
# --- Optuna Overrides ---
bbappend pnr.innovus.ClockBuildClockTreePreCallback {{
    set_ccopt_property inverter_cells {{{inv_str}}}
    set_ccopt_property buffer_cells {{{buf_str}}}
}}
"""
        with open(var_file, 'w') as f:
            f.write(content + "\n" + overrides)

        logger.info(f"Starting Trial {trial_num}: {run_name}")
        os.makedirs("logs", exist_ok=True)
        bash_log = f"logs/{run_name}.log"

        try:
            with open(bash_log, 'w') as f:
                subprocess.run([
                    self.config.script_path, run_name, "../../" + var_file,
                    self.config.wa_name, self.config.block_name, self.config.source_dir
                ], check=True, stdout=f, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            logger.warning(f"Flow script failed for trial {trial_num}. Attempting to salvage data.")

        # Results parsing
        clock_log = os.path.join(self.config.wa_name, 'run', run_name, 'main', 'pnr', 'clock', 'logs', 'clock.log')
        latency, skew = self.parse_clock_log(clock_log)

        if latency is None:
            logger.error(f"Trial {trial_num} failed: No timing data found.")
            return float('inf')

        # Objective: Minimize latency with a heavy penalty for skew violations
        score = latency
        if skew > self.config.skew_constraint:
            penalty = (skew - self.config.skew_constraint) * 100
            score += penalty
            logger.info(f"Skew violation: {skew:.4f} > {self.config.skew_constraint}. Score: {score:.4f}")
        else:
            logger.info(f"Result: Latency={latency:.4f}, Skew={skew:.4f}")

        return score

def main():
    parser = argparse.ArgumentParser(description="Consolidated Optuna CTS Optimizer")
    
    # Required/Common
    parser.add_argument("--wa-name", required=True, help="Bob Workspace Name")
    parser.add_argument("--base-var", required=True, help="Base .var file")
    parser.add_argument("--block-name", required=True, help="Design block name")
    parser.add_argument("--source-dir", required=True, help="Reference directory for softlinks")
    
    # Storage
    parser.add_argument("--db-type", choices=["sqlite", "postgres"], default="sqlite", help="Backend DB type")
    parser.add_argument("--db-name", default="optuna_study.db", help="SQLite file or Postgres DB name")
    parser.add_argument("--db-host", help="Postgres host")
    parser.add_argument("--db-user", help="Postgres user")
    parser.add_argument("--db-pass", help="Postgres password")
    
    # Optimization
    parser.add_argument("--study-name", default="cts_opt_study", help="Optuna study name")
    parser.add_argument("--trials", type=int, default=30, help="Number of trials for this worker")
    parser.add_argument("--run-prefix", default="opt", help="Prefix for run names")
    parser.add_argument("--skew-limit", type=float, default=0.06, help="Skew constraint (ns)")
    parser.add_argument("--script", default="./run_flow_parameterized.sh", help="Path to flow script")
    parser.add_argument("--vts", nargs="+", default=["ULVT"], help="VT types to explore")

    args = parser.parse_args()

    # Construct Storage URL
    if args.db_type == "sqlite":
        storage_url = f"sqlite:///{args.db_name}"
    else:
        pw = urllib.parse.quote_plus(args.db_pass) if args.db_pass else ""
        storage_url = f"postgresql://{args.db_user}:{pw}@{args.db_host}/{args.db_name}"

    config = OptimizerConfig(
        wa_name=args.wa_name,
        base_var=args.base_var,
        study_name=args.study_name,
        run_prefix=args.run_prefix,
        script_path=args.script,
        block_name=args.block_name,
        source_dir=args.source_dir,
        trials=args.trials,
        skew_constraint=args.skew_limit,
        storage_url=storage_url,
        vt_types=args.vts,
        min_drive_range=(1, 8),
        max_drive_range=(1, 16)
    )

    objective = CTSObjective(config)
    
    study = optuna.create_study(
        study_name=config.study_name,
        storage=config.storage_url,
        load_if_exists=True,
        direction="minimize"
    )
    
    logger.info(f"Connected to study '{config.study_name}' via {args.db_type}")
    study.optimize(objective, n_trials=config.trials)

if __name__ == "__main__":
    main()
