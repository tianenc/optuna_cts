# Optuna CTS Optimizer

This project provides a framework for optimizing Clock Tree Synthesis (CTS) parameters using Optuna.

## 1. Extraction of Usable Cells

Before running the optimizer, you need to extract the list of usable buffers and inverters from an existing clock log. This ensures that the optimizer only suggests cells that are available in your library and valid for the current design.

Use `extract_usable_cells_parameterized.py` to generate these lists:

```bash
python3 extract_usable_cells_parameterized.py /path/to/your/clock.log --buf-out usable_buffers.list --inv-out usable_inverters.list
```

The output files (`usable_buffers.list` and `usable_inverters.list`) are required by the Optuna worker scripts.

## 2. Running the Flow (`run_flow_parameterized.sh`)

The `run_flow_parameterized.sh` script automates the creation of a Bob run and executes the `pnr/clock` node. 

### Softlinking Working Directories
For the flow to work correctly without a full workspace clone for every trial, the script softlinks key directories from a "golden" source directory into each trial's run directory.

- **PNR Directories:** `setup`, `placeopt`, `libgen`, `floorplan` are linked from `${SOURCE_DIR_BASE}/pnr` to `${RUN_NAME}/main/pnr`.
- **SYN Directory:** `syn` is linked from `${SOURCE_DIR_BASE}/syn` to `${RUN_NAME}/main/syn`.

**Note:** Ensure that `SOURCE_DIR_BASE` (passed as the 5th argument) points to the parent directory of `pnr/` and `syn/` in your reference workspace.

Usage:
```bash
./run_flow_parameterized.sh <run_name> <var_file> <wa_name> <block_name> <source_dir_base>
```

## 3. Optuna Parallel Optimization (`run_optuna_parallel_ULVT.py`)

The main entry point for parallel optimization is `run_optuna_parallel_ULVT.py`. This script suggests cell selections (VT type and drive strength ranges) and invokes the flow script.

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--wa-name` | The name of the Bob workspace where runs will be created. | `20260114_gcpu_smu_svd_pipe` |
| `--base-var` | The base `.var` file containing the design's default configuration. | `gcpu_smu_svd_pipe.var` |
| `--study-name` | The name of the Optuna study (stored in the SQLite DB). | `gcpu_smu_svd_pipe_no_INVD_parallel_v1` |
| `--run-prefix` | Prefix used for naming trial run directories and generated `.var` files. | `optuna_v1` |
| `--script-path` | Path to the bash script that executes the flow (e.g., `./run_flow_parameterized.sh`). | `./run_flow.sh` |
| `--block-name` | The name of the design block. | `gcpu_smu_svd_pipe` |
| `--source-dir` | The base path to the source/reference directory for softlinking. | `/path/to/source/parent` |
| `--trials` | Number of trials this worker should execute. | `30` |
| `--skew-constraint`| The skew constraint (in ns) used to calculate penalties in the objective function. | `0.06` |

Example:
```bash
python3 run_optuna_parallel_ULVT.py \
    --wa_name my_workspace \
    --base-var my_design.var \
    --study-name cts_optimization_v1 \
    --script-path ./run_flow_parameterized.sh \
    --source-dir /home/user/ws/source_wa/run/ \
    --trials 10
```
