# MappingEvolve (LODCE)

> **LLM-Driven Technology Mapping Algorithm Kernel Evolution Framework**
>
> Let LLMs evolve C++ technology mapping kernels — not generate scripts, but directly rewrite the `compare_map` logic inside production-grade EDA algorithms.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![C++17](https://img.shields.io/badge/C++-17-00599C.svg)](https://en.cppreference.com/w/cpp/17)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB.svg)](https://www.python.org/)

---

## 📖 Overview

**MappingEvolve** is a hierarchical LLM-driven framework that automatically evolves the core algorithm kernels of technology mapping in logic synthesis. Instead of using LLMs as script generators, it lets them directly modify C++ source code within designated `EVOLVE-BLOCK` regions, then validates each modification through a three-stage pipeline: **Compilation → Equivalence Checking → QoR Evaluation**.

| Metric | Improvement |
|--------|-------------|
| vs. OpenEvolve (direct evolution) | **11.5×** higher reward |
| vs. ABC (area) | **10.04%** area reduction |
| Equivalence failures | **0%** (vs. 9% for OpenEvolve) |

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Planner LLM  │────▶│  Evolver LLM  │────▶│  Evaluator       │
│  (Scheduler)  │     │  (Code Writer)│     │  Build + CEC +   │
│               │◀────│               │◀────│  QoR Scoring     │
└──────────────┘     └──────────────┘     └─────────────────┘
      ▲                                            │
      └──────────── Reward Feedback ───────────────┘
```

The framework modifies three algorithmic operators within `EVOLVE-BLOCK` regions:

| Operator | File | Role |
|----------|------|------|
| **Match Phase** | `match_phase.cpp` | Delay/area-flow optimization with dual-mode compare |
| **Exact Match** | `match_phase_exact.cpp` | ELA-based exact area with switch-activity awareness |
| **Drop Phase** | `match_drop_phase.cpp` | Phase unification across complemented outputs |

---

## 📁 Project Structure

```
MappingEvolve/
│
├── evolve_single/             # Single-point sequential evolution (main framework)
│   ├── proactive_single_point_evolve.py  # Entry: Planner → Evolver iterative loop
│   ├── prompts_optimized.py   # Optimized prompts with trend/stagnation/diversity signals
│   ├── query_llm.py           # LLM API client
│   └── openevolve_config.yaml # OpenEvolve configuration
│
├── mapping/                   # C++ Technology Mapper + Python Evaluator
│   ├── mapping.hpp            # Core mapper (based on mockturtle)
│   ├── main.cpp               # CLI + ISCAS85/EPFL benchmark harness
│   ├── match_phase.cpp        # Operator 1: delay/area-flow optimization
│   ├── match_phase_exact.cpp  # Operator 2: exact area optimization
│   ├── match_drop_phase.cpp   # Operator 3: phase unification
│   ├── evaluator.py           # Build → Run → Score evaluation pipeline
│   └── CMakeLists.txt
│
├── openevolve/                # OpenEvolve integration
│   ├── ccode/                 # C++ template code & assembly utilities
│   ├── configs/               # Evolution configurations
│   └── examples/              # OpenEvolve usage examples
│
├── output/                    # Evolution run outputs (proactive_evolve_*/)
├── scripts/                   # Analysis utilities (aggregation, plotting)
├── third-party/mockturtle/    # mockturtle logic synthesis library (submodule)
├── build.sh                   # Build script
├── CMakeLists.txt             # Top-level CMake
└── requirements.txt           # Python dependencies
```

---

## 🔧 Prerequisites

### System
- **Linux** (Ubuntu 20.04+ recommended)
- **GCC 9+** or Clang 10+ with C++17 support
- **CMake 3.16+**
- **CUDA 11.8 / 12.1** (for PyTorch, optional for evolution)

### Python
```bash
# CUDA 12.1
pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121
pip install -f https://data.pyg.org/whl/torch-2.4.0+cu121.html torch_scatter==2.1.2

# CUDA 11.8
pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu118
pip install -f https://data.pyg.org/whl/torch-2.4.0+cu118.html torch_scatter==2.1.2
```

Install remaining dependencies:
```bash
pip install -r requirements.txt
```

### C++ Libraries
The mockturtle submodule is included — no separate installation needed:
```bash
git submodule update --init --recursive
```

### OpenEvolve (Evolver Component)
MappingEvolve uses OpenEvolve as its code evolution engine:
```bash
pip install openevolve==0.2.18
```

---

## 🚀 Quick Start

### 1. Build the Mapper

```bash
./build.sh
# Or manually:
# mkdir build && cd build && cmake .. && make -j$(nproc)
```

### 2. Run Technology Mapping

```bash
./build/mapping/mapping \
    third-party/mockturtle/experiments/cell_libraries/asap7.genlib \
    third-party/mockturtle/experiments/benchmarks/adder.aig \
    adder.v
```

**Output:**
```
[i] WARNING: 11 gates IGNORED (e.g., OA333x2_ASAP7_75t_R), too many inputs for the library settings
{"area": 92.420000, "gates": 890.000000, "delay": 2574.359997, "depth": 128.000000, "runtime": 0.055223, "nec": 0.000000}
```

### 3. Run MappingEvolve (Planner + OpenEvolve Evolver)

```bash
# Configure LLM credentials in evolve_single/openevolve_config.yaml first
python3 evolve_single/proactive_single_point_evolve.py --openevolve
```

The evolution framework follows the hierarchical Planner→Evolver→Evaluator loop:
1. **Planner** (LLM): Analyzes recent performance history and adaptive signals → selects operator + strategy
2. **Evolver** (OpenEvolve): Receives the Planner's evolution plan → population-based code evolution within `EVOLVE-BLOCK` regions
3. **Evaluator**: Merges evolved operator with unchanged operators → Build → Equivalence Check (ABC `cec`) → QoR Scoring on ISCAS85
4. **Decide**: Dual-criteria acceptance policy (reward threshold + delay protection) → accept or revert

### 4. Run OpenEvolve Baselines (Standalone)

To reproduce the paper's OpenEvolve baseline (directly evolve a single operator without Planner guidance).

> **Note**: The local `openevolve/` directory shadows the pip-installed `openevolve` package.  
> Use `python3 -c "from openevolve.cli import main; main()"` to invoke the CLI.

```bash
cd MappingEvolve

# Evolve MatchPhase operator for 90 iterations
nohup python3 -c "from openevolve.cli import main; main()" \
    --config evolve_single/openevolve_config.yaml \
    --output output/openevolve_match_phase \
    --iterations 90 \
    openevolve/mapping/match_phase.cpp \
    openevolve/mapping/evaluator.py \
    > openevolve.log 2>&1 &

# Evolve MatchPhaseExact operator
nohup python3 -c "from openevolve.cli import main; main()" \
    --config evolve_single/openevolve_config.yaml \
    --output output/openevolve_match_phase_exact \
    --iterations 90 \
    openevolve/mapping/match_phase_exact.cpp \
    openevolve/mapping/evaluator.py \
    > openevolve_exact.log 2>&1 &

# Evolve MatchDropPhase operator
nohup python3 -c "from openevolve.cli import main; main()" \
    --config evolve_single/openevolve_config.yaml \
    --output output/openevolve_match_drop_phase \
    --iterations 90 \
    openevolve/mapping/match_drop_phase.cpp \
    openevolve/mapping/evaluator.py \
    > openevolve_drop.log 2>&1 &
```

Alternatively, use `--openevolve` flag in MappingEvolve for Planner-guided evolution:
```bash
python3 evolve_single/proactive_single_point_evolve.py --openevolve
```

---

## ⚙️ Configuration

### LLM Backend (`evolve_single/query_llm.py` / `evolve/query_llm.py`)

Configure your LLM endpoint via environment variables or directly in code:
```python
MODEL = "deepseek-v3-241226"          # Model name
API_KEY = "your-api-key"              # API key
BASE_URL = "https://api.example.com"  # OpenAI-compatible endpoint
```

### Evolution Parameters (`evolve_single/proactive_single_point_evolve.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_iterations` | 30 | Total evolution iterations |
| `initial_temperature` | 1.0 | Temperature for LLM sampling |
| `revert_threshold` | -0.1 | Minimum reward to accept a change |
| `window_size` | 5 | Sliding window for trend analysis |

### Mapper Parameters (`mapping/mapping.hpp`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cut_limit` | 49 | Maximum cut size for enumeration |
| `area_rounds` | 3 | Number of area optimization rounds |
| `exact_area_rounds` | 2 | Number of exact area rounds |
| `mapping_type` | AreaOnly | Mapping mode (AreaOnly / DelayOnly) |

---

## 📊 Output Structure

Each evolution run produces a timestamped directory:
```
output/proactive_evolve_llm_deepseek-v3_20251118_105209/
├── log.txt                     # Full run log
├── summary.json                # Best reward & iteration
├── iter_1/
│   ├── planner_input.txt       # Full context sent to Planner
│   ├── planner_output.txt      # Raw Planner response
│   ├── plan.json               # Parsed evolution plan
│   ├── evolver_output.txt      # Raw Evolver response
│   ├── evolved_*.cpp           # Evolved operator code
│   ├── reward.json             # Evaluation scores
│   └── evolved_mapping/        # Assembled full mapping code
├── iter_2/ ...
└── iter_N/ ...
```

---

## 🧪 Evaluation & Scoring

The evaluation pipeline runs on standard benchmarks:

| Benchmark Suite | Circuits |
|-----------------|----------|
| **ISCAS85** | c17, c432, c499, c880, c1355, c1908, c2670, c3540, c5315, c6288, c7552 |
| **EPFL** | adder, arbiter, bar, cavlc, ctrl, dec, div, int2float, log2, max, mem_ctrl, multiplier, priority, router, sin, sqrt, square, voting, i2c, mem_ctrl |

**Scoring Function**: $S_{overall} = 0.5 \cdot S_{area} + 0.5 \cdot S_{delay}$

**Safety Guarantees**:
- Compilation failure → penalty (-0.5)
- Equivalence check failure (ABC `cec`) → penalty (-0.4 to -0.5)
- Degradation below threshold → rejected and reverted

---

## 📈 Analysis Tools

```bash
# Aggregate results across multiple runs
python scripts/aggregate_evolution_results.py

# Plot reward curves
python scripts/plot_rewards.py
```

---

## 🙏 Acknowledgments

This project builds upon:
- [mockturtle](https://github.com/lsils/mockturtle) — C++ logic synthesis framework
- [OpenEvolve](https://github.com/OpenEvolve/openevolve) — Code evolution library
- [ABC](https://github.com/berkeley-abc/abc) — System for sequential synthesis and verification
- ASAP7 standard cell library

---

## � Citation

If you use MappingEvolve in your research, please cite our paper:

```bibtex
@inproceedings{fu2026mappingevolve,
  author    = {Fu, Rongliang and Liu, Yi and Xu, Qiang and Ho, Tsung-Yi},
  booktitle = {Proceedings of the 63rd ACM/IEEE Design Automation Conference (DAC)},
  title     = {{MappingEvolve}: {LLM}-Driven Code Evolution for Technology Mapping},
  year      = {2026},
  volume    = {},
  number    = {},
  pages     = {1-7},
  doi       = {10.1145/3770743.3803988}
}
```

## �📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
