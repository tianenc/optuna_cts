import re
import sys

def parse_skew_report(file_path):
    """
    Parses a Cadence Innovus skew report to find the Max Latency (Max ID)
    and Skew for the primary setup.late timing corner.
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # This regex is built to find the 'ssgnp...setup.late' line and
        # capture the 5th and 10th columns of data.
        pattern = re.compile(
            r"^ssgnp_.*:setup\.late\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+)\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+)",
            re.MULTILINE
        )

        match = pattern.search(content)

        if match:
            max_latency = float(match.group(1))
            skew = float(match.group(2))
            
            print(f"Successfully parsed report: {file_path}")
            print(f"  Max Latency (Max ID): {max_latency} ns")
            print(f"  Skew:                 {skew} ns")
            
            # --- MODIFIED: Added return statement ---
            # This allows the function to be imported and used by other scripts.
            return max_latency, skew
        else:
            print(f"Error: Could not find the 'ssgnp...setup.late' corner in the report.")
            # --- MODIFIED: Added return statement ---
            return None, None

    except FileNotFoundError:
        print(f"Error: Report file not found at '{file_path}'")
        # --- MODIFIED: Added return statement ---
        return None, None
    except Exception as e:
        print(f"An error occurred: {e}")
        # --- MODIFIED: Added return statement ---
        return None, None

if __name__ == "__main__":
    # This block allows the script to still be run standalone for testing
    if len(sys.argv) != 2:
        print("Usage: python3 parse_cts_report.py <path_to_report_file>")
        print("\nExample: python3 parse_cts_report.py clock_POSTCTS_report_ccopt_skew_groups.txt")
    else:
        report_file = sys.argv[1]
        parse_skew_report(report_file)