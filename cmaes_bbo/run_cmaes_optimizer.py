#!/usr/bin/env python3
"""
CMA-ES Black Box Optimizer for Silicon Flows
Optimizes continuous parameters (e.g., target slack, max transition, etc.) 
using the Covariance Matrix Adaptation Evolution Strategy (CMA-ES) via Optuna.
"""

import argparse
import logging
import os
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import optuna
from optuna.samplers import CmaEsSampler

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class BBOConfig:
    wa_name: str
    base_var: str
    study_name: str
    run_prefix: str
    script_path: str
    block_name: str
    source_dir: str
    trials: int
    storage_url: str
    # CMA-ES optimized parameters: name -> (min, max)
    params_config: Dict[str, Tuple[float, float]]

class CMAESObjective:
    def __init__(self, config: BBOConfig):
        self.config = config

    def __call__(self, trial: optuna.Trial) -> float:
        trial_num = trial.number
        
        # Suggest continuous parameters for CMA-ES
        overrides_list = []
        for param_name, (low, high) in self.config.params_config.items():
            val = trial.suggest_float(param_name, low, high)
            # Formatting as Tcl set_config_property for Bob flows
            overrides_list.append(f"set_config_property {param_name} {val:.6f}")

        run_name = f"{self.config.run_prefix}_trial_{trial_num}"
        var_file = f"vars_{run_name}.var"

        # Read base configuration
        if not os.path.exists(self.config.base_var):
            logger.error(f"Base var file {self.config.base_var} missing.")
            return float('inf')

        with open(self.config.base_var, 'r') as f:
            base_content = f.read()

        overrides_content = "\n# --- CMA-ES BBO Overrides ---\n" + "\n".join(overrides_list)
        
        # We'll save the trial-specific var file in the study directory
        with open(var_file, 'w') as f:
            f.write(base_content + overrides_content)

        logger.info(f"Starting CMA-ES Trial {trial_num}: {run_name}")
        os.makedirs("logs", exist_ok=True)
        bash_log = f"logs/{run_name}.log"

        try:
            # Reusing the standard flow interface: 
            # run_flow.sh <run_name> <var_file> <wa_name> <block_name> <source_dir>
            # Note: The flow script expects var_file relative to its execution dir or with path
            subprocess.run([
                self.config.script_path, run_name, "../../" + var_file,
                self.config.wa_name, self.config.block_name, self.config.source_dir
            ], check=True, stdout=open(bash_log, 'w'), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            logger.warning(f"Flow script failed for trial {trial_num}. Checking logs for partial results...")

        # --- Result Parsing ---
        # Objective: Extract the metric to minimize (e.g., Power, WNS, Area)
        # This part requires design-specific parsing of the Bob/Innovus reports.
        score = self._parse_result(run_name)
        
        return score if score is not None else float('inf')

    def _parse_result(self, run_name: str) -> Optional[float]:
        """
        Parses trial results from the workspace. 
        Update this with your specific report parsing logic.
        """
        # Placeholder example: Parse power from a generic report location
        # report_path = os.path.join(self.config.wa_name, 'run', run_name, 'main', 'pnr', 'power', 'reports', 'total.rpt')
        logger.info(f"Objective parsing for {run_name} is currently a placeholder.")
        return 0.0 

def main():
    parser = argparse.ArgumentParser(description="CMA-ES Black Box Optimizer for Silicon Flows")
    
    # Required parameters
    parser.add_argument("--wa-name", required=True, help="Bob Workspace Name")
    parser.add_argument("--base-var", required=True, help="Base .var file path")
    parser.add_argument("--block-name", required=True, help="Design block name")
    parser.add_argument("--source-dir", required=True, help="Reference directory for symlinks")
    
    # Study configuration
    parser.add_argument("--study-name", default="cmaes_bbo_study", help="Optuna study name")
    parser.add_argument("--trials", type=int, default=50, help="Number of trials")
    parser.add_argument("--run-prefix", default="cmaes", help="Prefix for trial run names")
    parser.add_argument("--db-type", choices=["sqlite", "postgres"], default="sqlite")
    parser.add_argument("--db-name", default="cmaes_study.db")
    
    # Flow script
    parser.add_argument("--script", default="../run_flow_parameterized.sh", help="Path to flow execution script")

    args = parser.parse_args()

    # Define the search space for CMA-ES (example parameters)
    params_config = {
        "pnr.innovus.target_slack": (-0.1, 0.1),
        "pnr.innovus.max_transition": (0.05, 0.3),
        "pnr.innovus.max_capacitance": (0.1, 1.0),
    }

    # Storage setup
    if args.db_type == "sqlite":
        storage_url = f"sqlite:///{args.db_name}"
    else:
        # Placeholder for Postgres URL construction
        storage_url = f"postgresql://user:pass@host/{args.db_name}"

    config = BBOConfig(
        wa_name=args.wa_name,
        base_var=args.base_var,
        study_name=args.study_name,
        run_prefix=args.run_prefix,
        script_path=args.script,
        block_name=args.block_name,
        source_dir=args.source_dir,
        trials=args.trials,
        storage_url=storage_url,
        params_config=params_config
    )

    # Initialize Optuna with the CMA-ES sampler
    # CMA-ES is particularly strong for continuous parameter optimization.
    sampler = CmaEsSampler()
    
    study = optuna.create_study(
        study_name=config.study_name,
        storage=config.storage_url,
        sampler=sampler,
        load_if_exists=True,
        direction="minimize"
    )

    objective = CMAESObjective(config)
    logger.info(f"CMA-ES Optimization session started: {config.study_name}")
    study.optimize(objective, n_trials=config.trials)

if __name__ == "__main__":
    main()
