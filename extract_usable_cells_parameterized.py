#!/usr/bin/env python3
"""
Extract usable buffers and inverters from a clock.log file.
Useful for pre-filtering cell lists for CTS optimization.
"""

import argparse
import logging
import os
import re
import sys
from typing import List, Set, Tuple

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def extract_cells_from_log(log_path: str) -> Tuple[List[str], List[str]]:
    """
    Parses a clock.log file to extract the full list of usable buffers and inverters.
    """
    if not os.path.exists(log_path):
        logger.error(f"Source log file not found: {log_path}")
        sys.exit(1)
        
    logger.info(f"Extracting usable cells from: {log_path}")
    
    buffers: Set[str] = set()
    inverters: Set[str] = set()
    
    # Strip log prefixes (e.g., timestamps)
    prefix_pattern = re.compile(r'^[\d-]+\s+[\d:]+:\w+:\s*')
    
    current_mode = None 
    stop_phrases = ["Total number of", "List of unusable"]
    garbage = {"List", "Total", "number", "of", "usable", "unusable", "buffers:", "inverters:", "buffers", "inverters"}

    with open(log_path, 'r') as f:
        for line in f:
            clean_line = prefix_pattern.sub('', line).strip()
            
            # Identify current list
            if "List of usable buffers:" in clean_line:
                current_mode = 'buffers'
                parts = clean_line.split("List of usable buffers:")
                if len(parts) > 1:
                    cells = [c for c in parts[1].split() if c and c[0].isalpha() and c not in garbage]
                    buffers.update(cells)
                continue
            elif "List of usable inverters:" in clean_line:
                current_mode = 'inverters'
                parts = clean_line.split("List of usable inverters:")
                if len(parts) > 1:
                    cells = [c for c in parts[1].split() if c and c[0].isalpha() and c not in garbage]
                    inverters.update(cells)
                continue
            
            # Mode transitions
            if current_mode:
                if any(phrase in clean_line for phrase in stop_phrases) or not clean_line or clean_line[0] in '-=':
                    current_mode = None
                    continue

                cells = [c for c in clean_line.split() if c and c[0].isalpha() and c not in garbage]
                if not cells:
                    current_mode = None
                    continue

                if current_mode == 'buffers':
                    buffers.update(cells)
                else:
                    inverters.update(cells)

    sorted_buffers = sorted(list(buffers))
    sorted_inverters = sorted(list(inverters))
    
    logger.info(f"Found {len(sorted_buffers)} unique buffers and {len(sorted_inverters)} unique inverters.")
    return sorted_buffers, sorted_inverters

def save_list(cells: List[str], filename: str):
    try:
        with open(filename, 'w') as f:
            for cell in cells:
                f.write(f"{cell}\n")
        logger.info(f"Wrote {len(cells)} cells to {filename}")
    except IOError as e:
        logger.error(f"Failed to write to {filename}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Extract usable cells from clock.log")
    parser.add_argument("log", help="Path to clock.log")
    parser.add_argument("--buf-out", default="usable_buffers.list", help="Buffer list output file")
    parser.add_argument("--inv-out", default="usable_inverters.list", help="Inverter list output file")

    args = parser.parse_args()

    bufs, invs = extract_cells_from_log(args.log)
    
    if not bufs: logger.warning("No buffers extracted.")
    if not invs: logger.warning("No inverters extracted.")
        
    save_list(bufs, args.buf_out)
    save_list(invs, args.inv_out)

if __name__ == "__main__":
    main()
