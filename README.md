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
├── evolve/                    # MCTS-based multi-operator parallel evolution
│   ├── main.py                # Entry point: Scheduler + Evolver LLM pipeline
│   ├── mcts.py                # Standard MCTS (select/expand/simulate/backprop)
│   ├── node.py                # LLMNode: AreaNode / DelayNode / BalancedNode
│   ├── prompts.py             # System prompts for Scheduler & Evolver
│   └── query_llm.py           # LLM API client (OpenAI-compatible)
│
├── evolve_single/             # Single-point sequential evolution (main framework)
│   ├── main.py                # Entry point: Planner → Evolver iterative loop
│   ├── proactive_single_point_evolve.py  # Core loop with adaptive signals
│   ├── prompts_optimized.py   # Optimized prompts with trend/stagnation/diversity signals
│   └── query_llm.py           # LLM API client
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
./build/mapping/emap \
    third-party/mockturtle/experiments/benchmarks/adder.aig \
    third-party/mockturtle/experiments/cell_libraries/asap7.genlib \
    adder.v
```

**Output:**
```
[i] processing adder.aig
resyn runtime: 0.01
[i] area: 102.80, gates: 887, depth: 130
mapping runtime: 0.01
```

### 3. Run Algorithm Evolution

```bash
# Single-point sequential evolution (recommended)
cd evolve_single
python main.py

# MCTS-based parallel evolution
cd evolve
python main.py
```

The evolution framework will:
1. **Plan**: Analyze current code and historical trends → select operator + strategy
2. **Evolve**: Modify the selected `EVOLVE-BLOCK` code region
3. **Evaluate**: Build → Equivalence check → Benchmark → Score
4. **Decide**: Accept improvement or revert based on dual-criteria policy

---

## ⚙️ Configuration

### LLM Backend (`evolve_single/query_llm.py` / `evolve/query_llm.py`)

Configure your LLM endpoint via environment variables or directly in code:
```python
MODEL = "deepseek-v3-241226"          # Model name
API_KEY = "your-api-key"              # API key
BASE_URL = "https://api.example.com"  # OpenAI-compatible endpoint
```

### Evolution Parameters (`evolve_single/main.py`)

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

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
