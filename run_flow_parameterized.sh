#!/bin/bash
# Consolidated Flow Execution Script for CTS Trials
# Handles workspace setup via symlinks and submits Bob jobs.

# --- ANSI Color Codes ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $1"; }
log_succ() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# --- Argument Validation ---
if [ "$#" -ne 5 ]; then
  log_err "Missing arguments."
  echo "Usage: $0 <run_name> <var_file> <wa_name> <block_name> <source_dir_base>"
  exit 1
fi

RUN_NAME=$1
VAR_FILE=$2
WA_NAME=$3
BLOCK_NAME=$4
SOURCE_DIR_BASE=$5

# --- Environment Setup ---
log_info "Setting up environment..."
module purge
module load internal/bob linux/slurm > /dev/null 2>&1
source /usr/local/google/gcpu/tools/altair/flowtracer/vov/2021.2.0/common/etc/vovrc.sh

if [ ! -d "$WA_NAME" ]; then
  log_err "Workspace directory $WA_NAME not found."
  exit 1
fi

cd "$WA_NAME/run/" || exit

# --- Create Bob Run ---
log_info "Creating Bob run: $RUN_NAME"
bob create -s pnr --var "$VAR_FILE" --run_dir "$RUN_NAME" --block "$BLOCK_NAME" --verbose info

# --- Symbolic Link Logic ---
PNR_SOURCE="${SOURCE_DIR_BASE}/pnr"
PNR_DEST="${RUN_NAME}/main/pnr"
DIRS_TO_LINK_PNR=( "setup" "placeopt" "libgen" "floorplan" )

log_info "Linking PNR prerequisites..."
for dir in "${DIRS_TO_LINK_PNR[@]}"; do
  rm -rf "${PNR_DEST}/${dir}"
  ln -s "${PNR_SOURCE}/${dir}" "${PN_DEST}/${dir}"
done

log_info "Linking SYN prerequisites..."
ln -sfv "${SOURCE_DIR_BASE}/syn" "${RUN_NAME}/main/syn" > /dev/null

# --- Execution & Polling ---
log_info "Force-validating upstream nodes..."
PREREQ_NODES="pnr/libgen pnr/setup pnr/floorplan pnr/placeopt"
bob update status -f -i -b "$BLOCK_NAME" -r "$RUN_NAME" --force_validate $PREREQ_NODES

log_info "Submitting job: pnr/clock"
bob run -r "$RUN_NAME" --node pnr/clock

# Polling Loop
MAX_RETRIES=5
RETRY_COUNT=0

while true; do
  status=$(bob info -r "$RUN_NAME" -O '@JOBNAME@ @STATUS@' | grep "pnr/clock" | awk '{print $2}' | tr -d '[:space:]')
  
  case "$status" in
    VALID)
      log_succ "Job pnr/clock completed successfully."
      exit 0
      ;;
    FAILED)
      log_err "Job pnr/clock FAILED."
      exit 1
      ;;
    INVALID)
      ((RETRY_COUNT++))
      if [ "$RETRY_COUNT" -gt "$MAX_RETRIES" ]; then
        log_err "Job keeps reverting to INVALID. Aborting."
        exit 1
      fi
      log_warn "Job INVALID (Retry $RETRY_COUNT/$MAX_RETRIES). Re-submitting..."
      bob update status -f -i -b "$BLOCK_NAME" -r "$RUN_NAME" --force_validate $PREREQ_NODES
      bob run -r "$RUN_NAME" --node pnr/clock --force
      sleep 10
      ;;
    *)
      log_info "pnr/clock status: $status. Waiting 5 minutes..."
      sleep 300
      ;;
  esac
done
