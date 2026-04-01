# Optuna CTS Optimizer

A toolset for automating the optimization of Clock Tree Synthesis (CTS) parameters using Optuna. This framework helps find the best combination of buffer/inverter VT types and drive strengths to minimize latency while meeting skew constraints.

## 🚀 Quick Start

### 1. Extract Usable Cells
The optimizer needs a list of available cells from your library. Extract them from an existing `clock.log`:

```bash
./extract_usable_cells_parameterized.py /path/to/clock.log
```
This generates `usable_buffers.list` and `usable_inverters.list`.

### 2. Run Optimization
The consolidated `run_optuna_optimizer.py` handles both SQLite (local) and PostgreSQL (shared) backends.

**Using SQLite (Default):**
```bash
./run_optuna_optimizer.py \
    --wa-name my_bob_workspace \
    --base-var design.var \
    --block-name my_block \
    --source-dir /path/to/reference/run/main/ \
    --trials 50
```

**Using PostgreSQL:**
```bash
./run_optuna_optimizer.py \
    --wa-name my_bob_workspace \
    --base-var design.var \
    --block-name my_block \
    --source-dir /path/to/reference/run/main/ \
    --db-type postgres \
    --db-host 10.x.x.x \
    --db-name optuna_db \
    --db-user optuna_user \
    --db-pass my_password
```

## 🛠️ Tool Components

### `run_optuna_optimizer.py`
The main driver. It:
1. Suggests VT types and drive strength ranges via Optuna.
2. Filters cells based on suggestions.
3. Generates trial-specific `.var` files.
4. Invokes the flow script.
5. Parses `clock.log` to calculate the objective (Latency + Skew Penalty).

### `run_flow_parameterized.sh`
The execution wrapper for Bob. It:
- Sets up the environment and Bob run.
- **Critical:** Uses symbolic links for prerequisites (`setup`, `placeopt`, `libgen`, `floorplan`, `syn`) to avoid full workspace clones, saving massive disk space and time.
- Polls the job status and handles intermittent "INVALID" states.

### `extract_usable_cells_parameterized.py`
A utility to parse `clock.log` and generate the required cell list files.

## 📊 Configuration

| Argument | Description |
|----------|-------------|
| `--vts` | List of VT types to explore (e.g., `--vts ULVT LVT SVT`). |
| `--skew-limit`| Maximum allowable skew (ns). Violations add a heavy penalty to the objective. |
| `--trials` | Number of trials to run in this process. |
| `--run-prefix`| Prefix for naming trial directories (e.g., `opt_v2`). |

---
*Note: Ensure you have the `optuna` and `psycopg2` (for Postgres) Python packages installed.*
