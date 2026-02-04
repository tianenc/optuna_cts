import os
import re
import sys
import argparse

def extract_cells_from_log(log_path):
    """
    Parses the clock.log file to extract the full list of usable buffers and inverters.
    Removes duplicates and handles log prefixes.
    """
    if not os.path.exists(log_path):
        print(f"FATAL ERROR: Source log file not found at '{log_path}'")
        sys.exit(1)
        
    print(f"Extracting usable cells from: {log_path}")
    
    buffers = set()
    inverters = set()
    
    # Regex to match log prefixes (e.g., "2026-01-27 14:12:02:DEBUG: ") to strip them
    prefix_pattern = re.compile(r'^[\d-]+\s+[\d:]+:\w+:\s*')
    
    # State tracking: None, 'buffers', 'inverters'
    current_mode = None 
    
    # Words/Phrases that indicate the end of the list or should be ignored
    stop_phrases = ["Total number of", "List of unusable", "unusable buffers", "unusable inverters"]
    garbage_words = {"List", "Total", "number", "of", "usable", "unusable", "buffers:", "inverters:", "buffers", "inverters"}

    with open(log_path, 'r') as f:
        for line in f:
            # Strip the timestamp/debug prefix
            clean_line = prefix_pattern.sub('', line).strip()
            
            # Check for Headers and switch mode
            if "List of usable buffers:" in clean_line:
                current_mode = 'buffers'
                # Extract cells on the same line as the header
                parts = clean_line.split("List of usable buffers:")
                if len(parts) > 1:
                    raw_cells = parts[1].split()
                    valid_cells = [c for c in raw_cells if c and c[0].isalpha() and c not in garbage_words]
                    buffers.update(valid_cells)
                continue
                
            elif "List of usable inverters:" in clean_line:
                current_mode = 'inverters'
                parts = clean_line.split("List of usable inverters:")
                if len(parts) > 1:
                    raw_cells = parts[1].split()
                    valid_cells = [c for c in raw_cells if c and c[0].isalpha() and c not in garbage_words]
                    inverters.update(valid_cells)
                continue
            
            # Handle list continuation or termination
            if current_mode:
                # STOP CONDITION 1: Explicit Stop Phrases found in the line
                if any(phrase in clean_line for phrase in stop_phrases):
                    current_mode = None
                    continue

                # STOP CONDITION 2: Formatting separators
                if not clean_line or clean_line.startswith('-') or clean_line.startswith('='):
                    current_mode = None
                    continue
                
                # STOP CONDITION 3: New "List of..." header
                if "List of usable" in clean_line:
                    current_mode = None
                    continue

                # Add continuation cells
                raw_cells = clean_line.split()
                if raw_cells:
                    # Filter out purely numeric tokens and known garbage words
                    valid_cells = [c for c in raw_cells if c and c[0].isalpha() and c not in garbage_words]
                    
                    # STOP CONDITION 4: If line has text but NO valid cells, assume it's a footer/junk line
                    if not valid_cells:
                        current_mode = None
                        continue

                    if current_mode == 'buffers':
                        buffers.update(valid_cells)
                    elif current_mode == 'inverters':
                        inverters.update(valid_cells)
                else:
                    current_mode = None

    sorted_buffers = sorted(list(buffers))
    sorted_inverters = sorted(list(inverters))
    
    print(f"  Found {len(sorted_buffers)} unique buffers.")
    print(f"  Found {len(sorted_inverters)} unique inverters.")
    
    return sorted_buffers, sorted_inverters

def write_list_to_file(cell_list, filename):
    try:
        with open(filename, 'w') as f:
            for cell in cell_list:
                f.write(f"{cell}\n")
        print(f"Successfully wrote {len(cell_list)} cells to {filename}")
    except IOError as e:
        print(f"Error writing to {filename}: {e}")

if __name__ == "__main__":
    # --- ARGUMENT PARSING ---
    parser = argparse.ArgumentParser(description="Extract usable buffers and inverters from a clock log file.")
    
    # Required positional argument for the log file
    parser.add_argument("source_log", help="Path to the source clock.log file")
    
    # Optional arguments for output files (defaults set to original hardcoded values)
    parser.add_argument("--buf-out", default="usable_buffers.list", help="Output file for buffers (default: usable_buffers.list)")
    parser.add_argument("--inv-out", default="usable_inverters.list", help="Output file for inverters (default: usable_inverters.list)")

    args = parser.parse_args()

    # --- EXECUTION ---
    buffers, inverters = extract_cells_from_log(args.source_log)
    
    if not buffers:
        print("WARNING: No buffers found in log. Check log format.")
    if not inverters:
        print("WARNING: No inverters found in log. Check log format.")
        
    write_list_to_file(buffers, args.buf_out)
    write_list_to_file(inverters, args.inv_out)