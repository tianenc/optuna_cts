# CMA-ES Black Box Optimizer (BBO)

This sub-project implements a black-box optimization framework using the **Covariance Matrix Adaptation Evolution Strategy (CMA-ES)** via Optuna. 

## 🎯 Purpose
Unlike the CTS-specific optimizer which focuses on categorical cell selections, the CMA-ES BBO is designed for **continuous parameters** such as:
- Target slack
- Max transition constraints
- Capacitance limits
- Voltage/Clock settings

CMA-ES is a state-of-the-art derivative-free optimization algorithm particularly effective for non-convex, high-dimensional continuous search spaces.

## 🚀 Usage

### 1. Configure Search Space
Edit the `params_config` dictionary in `run_cmaes_optimizer.py` to define the parameters and their ranges:

```python
params_config = {
    "pnr.innovus.target_slack": (-0.1, 0.1),
    "pnr.innovus.max_transition": (0.05, 0.3),
}
```

### 2. Implement Result Parsing
Update the `_parse_result` method in `run_cmaes_optimizer.py` to extract your target metric (e.g., Power, WNS) from the flow reports.

### 3. Run the Optimizer
```bash
./run_cmaes_optimizer.py \
    --wa-name my_workspace \
    --base-var design.var \
    --block-name my_block \
    --source-dir /path/to/reference/main/ \
    --trials 50
```

## 🛠️ Integration
This tool reuses the robust `run_flow_parameterized.sh` script from the sibling directory to handle Bob job submission and prerequisite softlinking.

## 📊 Why CMA-ES?
CMA-ES adaptively learns the covariance matrix of the search distribution, allowing it to navigate narrow valleys or scale different dimensions independently, making it superior to standard Random Search or TPE for continuous physical design parameters.
