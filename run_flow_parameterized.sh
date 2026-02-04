#!/bin/bash

# --- Check for five arguments ---
if [ "$#" -ne 5 ]; then
  echo "Error: Missing arguments."
  echo "Usage: $0 <run_name> <var_file> <wa_name> <block_name> <source_dir_base>"
  echo ""
  echo "Example:"
  echo "  $0 run1 vars.tcl my_wa_01 my_block /path/to/source/parent"
  exit 1
fi

# --- Assign arguments to variables ---
RUN_NAME=$1
VAR_FILE=$2
WA_NAME=$3
BLOCK_NAME=$4
SOURCE_DIR_BASE=$5  # This should be the path up to /main/

# --- Environment Setup ---
module purge
module load internal/bob
module load linux/slurm
source /usr/local/google/gcpu/tools/altair/flowtracer/vov/2021.2.0/common/etc/vovrc.sh

# --- Workspace Navigation ---
# Uncomment the clone line if your flow requires a fresh clone each time
# bob wa clone --from $SOURCE_DIR_BASE/../ --to $WA_NAME

if [ ! -d "$WA_NAME" ]; then
  echo "Error: Workspace directory $WA_NAME not found."
  exit 1
fi

cd "$WA_NAME/run/" || exit

# --- Create Bob Run ---
bob create --gui -s pnr --verbose debug --var "$VAR_FILE" --run_dir "$RUN_NAME" --block "$BLOCK_NAME"

# --- Symbolic Link Logic (PNR) ---
# Constructing paths based on parameters
PNR_SOURCE="${SOURCE_DIR_BASE}/pnr"
PNR_DEST="${RUN_NAME}/main/pnr"

DIRS_TO_LINK_PNR=( "setup" "placeopt" "libgen" "floorplan" )

echo "INFO: Setting up PNR symbolic links in $PNR_DEST..."
for dir in "${DIRS_TO_LINK_PNR[@]}"; do
  echo "  - Linking ${PNR_DEST}/${dir} -> ${PNR_SOURCE}/${dir}"
  rm -rf "${PNR_DEST}/${dir}"
  ln -s "${PNR_SOURCE}/${dir}" "${PNR_DEST}/${dir}"
done

# --- Symbolic Link Logic (SYN) ---
SYN_SOURCE="${SOURCE_DIR_BASE}"
SYN_DEST="${RUN_NAME}/main"

DIRS_TO_LINK_SYN=( "syn" )

echo "INFO: Setting up SYN symbolic links in $SYN_DEST..."
for dir in "${DIRS_TO_LINK_SYN[@]}"; do
  ln -sfv "$SYN_SOURCE/$dir" "${SYN_DEST}/${dir}"
done

# --- Re-validation and Run ---
echo "INFO: Performing initial force-validation for block: $BLOCK_NAME"
PREREQ_NODES="pnr/libgen pnr/setup pnr/floorplan pnr/placeopt"

bob update status -f -i -b "$BLOCK_NAME" -r "$RUN_NAME" --force_validate $PREREQ_NODES

echo "INFO: Submitting 'bob run' for pnr/clock..."
bob run -r "$RUN_NAME" --node pnr/clock

echo "INFO: Waiting 5 seconds for scheduler initialization..."
sleep 5

# --- Polling Loop ---
while true; do
  echo "--- Polling Job Status ($RUN_NAME) ---"
  all_statuses=$(bob info -r "$RUN_NAME" -O '@JOBNAME@ @STATUS@' | grep -v "#")
  
  # Get exact status of the target node
  clock_status=$(echo "$all_statuses" | awk -v node="pnr/clock" '$1 == node {print $2}' | tr -d '[:space:]')

  if [ "$clock_status" == "VALID" ]; then
    echo "INFO: pnr/clock is VALID. Process complete."
    break
  fi
  
  if [ "$clock_status" == "FAILED" ]; then
    echo "ERROR: The pnr/clock job FAILED."
    bob info -r "$RUN_NAME" --filter 'status==FAILED'
    exit 1
  fi

  # Check if prerequisites were invalidated by the tool
  prereq_statuses=$(echo "$all_statuses" | awk '$1 == "pnr/libgen" || $1 == "pnr/setup" || $1 == "pnr/floorplan" || $1 == "pnr/placeopt"')
  num_invalid=$(echo "$prereq_statuses" | grep -c "INVALID")
  
  if [ "$num_invalid" -gt 0 ]; then
    echo "INFO: $num_invalid prerequisite(s) became INVALID. Re-validating..."
    bob update status -f -i -b "$BLOCK_NAME" -r "$RUN_NAME" --force_validate $PREREQ_NODES
  fi
  
  echo "INFO: pnr/clock status is '$clock_status'. Sleeping 15s..."
  sleep 15
done