# OpenEvolve AlgoTune Benchmark Report: Gemini Flash 2.5 Experiment

## Executive Summary

This report documents the comprehensive evaluation of Google's Gemini Flash 2.5 model using OpenEvolve to optimize code across 8 AlgoTune benchmark tasks. The experiment ran for 114.6 minutes with a 100% success rate, discovering significant algorithmic improvements in 2 out of 8 tasks, including a remarkable 189.94x speedup for 2D convolution operations.

## Experiment Configuration

### Model Settings
- **Model**: Google Gemini Flash 2.5 (`google/gemini-2.5-flash`)
- **Temperature**: 0.4 (optimal based on prior tuning)
- **Max Tokens**: 16,000
- **Evolution Strategy**: Diff-based evolution
- **API Provider**: OpenRouter

### Evolution Parameters
- **Iterations per task**: 100
- **Checkpoint interval**: Every 10 iterations
- **Population size**: 1,000 programs
- **Number of islands**: 4 (for diversity)
- **Migration interval**: Every 20 generations

### Evaluation Settings
- **Cascade evaluation**: Enabled with 3 stages
- **Stage 2 timeout**: 200 seconds
- **Number of trials**: 5 test cases per evaluation
- **Timing runs**: 3 runs + 1 warmup per trial
- **Total executions per evaluation**: 16

## Critical Issue and Resolution

### The Data Size Problem
Initially, all tasks were timing out during Stage 2 evaluation despite individual runs taking only ~60 seconds. Investigation revealed:

- **Root cause**: Each evaluation actually performs 16 executions (5 trials × 3 timing runs + warmup)
- **Original calculation**: 60 seconds × 16 = 960 seconds > 200-second timeout
- **Solution**: Reduced data_size parameters by factor of ~16

### Adjusted Data Sizes
| Task | Original | Adjusted | Reduction Factor |
|------|----------|----------|-----------------|
| affine_transform_2d | 2000 | 100 | 20x |
| convolve2d_full_fill | 20 | 5 | 4x |
| eigenvectors_complex | 400 | 25 | 16x |
| fft_cmplx_scipy_fftpack | 1500 | 95 | 15.8x |
| fft_convolution | 2000 | 125 | 16x |
| lu_factorization | 400 | 25 | 16x |
| polynomial_real | 8000 | 500 | 16x |
| psd_cone_projection | 600 | 35 | 17.1x |

## Results Overview

### Performance Summary
| Task | Speedup | Combined Score | Runtime (s) | Status |
|------|---------|----------------|-------------|---------|
| convolve2d_full_fill | **189.94x** 🚀 | 0.955 | 643.2 | ✅ |
| psd_cone_projection | **2.37x** 🔥 | 0.975 | 543.5 | ✅ |
| eigenvectors_complex | 1.074x | 0.974 | 1213.2 | ✅ |
| lu_factorization | 1.062x | 0.987 | 727.9 | ✅ |
| affine_transform_2d | 1.053x | 0.939 | 577.5 | ✅ |
| polynomial_real | 1.036x | 0.801 | 2181.3 | ✅ |
| fft_cmplx_scipy_fftpack | 1.017x | 0.984 | 386.5 | ✅ |
| fft_convolution | 1.014x | 0.987 | 605.6 | ✅ |

### Key Metrics
- **Total runtime**: 114.6 minutes
- **Success rate**: 100% (8/8 tasks)
- **Tasks with significant optimization**: 2/8 (25%)
- **Tasks with minor improvements**: 6/8 (75%)
- **Average time per task**: 14.3 minutes

## Detailed Analysis of Optimizations

### 1. convolve2d_full_fill - 189.94x Speedup (Major Success)

**Original Implementation:**
```python
def solve(self, problem):
    a, b = problem
    result = signal.convolve2d(a, b, mode=self.mode, boundary=self.boundary)
    return result
```

**Evolved Implementation:**
```python
def solve(self, problem):
    a_in, b_in = problem
    # Ensure inputs are float64 and C-contiguous for optimal performance with FFT
    a = a_in if a_in.flags['C_CONTIGUOUS'] and a_in.dtype == np.float64 else np.ascontiguousarray(a_in, dtype=np.float64)
    b = b_in if b_in.flags['C_CONTIGUOUS'] and b_in.dtype == np.float64 else np.ascontiguousarray(b_in, dtype=np.float64)
    result = signal.fftconvolve(a, b, mode=self.mode)
    return result
```

**Key Optimizations:**
- **Algorithmic change**: Switched from `convolve2d` (O(n⁴)) to `fftconvolve` (O(n²log n))
- **Memory optimization**: Ensured C-contiguous memory layout for FFT efficiency
- **Type optimization**: Explicit float64 dtype for numerical stability

### 2. psd_cone_projection - 2.37x Speedup (Moderate Success)

**Original Implementation:**
```python
def solve(self, problem):
    A = problem["matrix"]
    # Standard eigendecomposition
    eigvals, eigvecs = np.linalg.eig(A)
    eigvals = np.maximum(eigvals, 0)
    X = eigvecs @ np.diag(eigvals) @ eigvecs.T
    return {"projection": X}
```

**Evolved Implementation:**
```python
def solve(self, problem):
    A = problem["matrix"]
    # Use eigh for symmetric matrices for better performance and numerical stability
    eigvals, eigvecs = np.linalg.eigh(A)
    # Clip negative eigenvalues to zero
    eigvals = np.maximum(eigvals, 0)
    # Optimized matrix multiplication: multiply eigvecs with eigvals first
    X = (eigvecs * eigvals) @ eigvecs.T
    return {"projection": X}
```

**Key Optimizations:**
- **Specialized function**: Used `eigh` instead of `eig` for symmetric matrices
- **Optimized multiplication**: Changed from `eigvecs @ np.diag(eigvals) @ eigvecs.T` to `(eigvecs * eigvals) @ eigvecs.T`
- **Better numerical stability**: `eigh` guarantees real eigenvalues for symmetric matrices

### 3. Minor Optimizations (1.01x - 1.07x Speedup)

**affine_transform_2d (1.053x):**
```python
# Original
image = problem["image"]
matrix = problem["matrix"]

# Evolved
image = np.asarray(problem["image"], dtype=float)
matrix = np.asarray(problem["matrix"], dtype=float)
```
- Added explicit type conversion to avoid runtime type checking

**Other tasks** showed no visible code changes, suggesting:
- Speedups likely due to measurement variance
- Minor internal optimizations not visible in source
- Statistical noise in timing measurements

## What Worked Well

### 1. Evolution Discovery Capabilities
- Successfully discovered FFT-based convolution optimization (189x speedup)
- Found specialized functions for symmetric matrices (2.37x speedup)
- Identified memory layout optimizations

### 2. Configuration Optimizations
- Diff-based evolution worked better than full rewrites for Gemini
- Temperature 0.4 provided good balance between exploration and exploitation
- Island-based evolution maintained diversity

### 3. System Robustness
- 100% task completion rate after data size adjustment
- No crashes or critical failures
- Checkpoint system allowed progress tracking

## What Didn't Work

### 1. Limited Optimization Discovery
- 6 out of 8 tasks showed minimal improvements (<7%)
- Most baseline implementations were already near-optimal
- Evolution struggled to find improvements for already-optimized code

### 2. Initial Configuration Issues
- Original data_size values caused timeouts
- Required manual intervention to adjust parameters
- Cascade evaluation timing wasn't initially accounted for

### 3. Minor Perturbations vs Real Optimizations
- Many "improvements" were just measurement noise
- Small type conversions counted as optimizations
- Difficult to distinguish real improvements from variance

## Lessons Learned

### 1. Evaluation Complexity
- Must account for total execution count (trials × runs × warmup)
- Cascade evaluation adds significant overhead
- Timeout settings need careful calibration

### 2. Baseline Quality Matters
- Well-optimized baselines leave little room for improvement
- AlgoTune baselines already use efficient libraries (scipy, numpy)
- Major improvements only possible with algorithmic changes

### 3. Evolution Effectiveness
- Works best when alternative algorithms exist (convolve2d → fftconvolve)
- Can find specialized functions (eig → eigh)
- Struggles with micro-optimizations

## Recommendations for Future Experiments

### 1. Task Selection
- Include tasks with known suboptimal baseline implementations
- Add problems where multiple algorithmic approaches exist
- Consider more complex optimization scenarios

### 2. Configuration Tuning
- Pre-calculate total execution time for data sizing
- Consider reducing trials/runs for faster iteration
- Adjust timeout based on actual execution patterns

### 3. Model Comparison Setup
For comparing with other models (e.g., Claude, GPT-4):
- Use identical configuration parameters
- Run on same hardware for fair comparison
- Track both speedup and code quality metrics
- Document any model-specific adjustments needed

## Conclusion

The Gemini Flash 2.5 experiment demonstrated OpenEvolve's capability to discover significant algorithmic improvements when they exist. The system achieved a 189.94x speedup on 2D convolution by automatically discovering FFT-based methods and a 2.37x speedup on PSD projection through specialized matrix operations.

However, the experiment also revealed that for well-optimized baseline implementations, evolution produces minimal improvements. The 25% success rate for finding meaningful optimizations suggests that careful task selection is crucial for demonstrating evolutionary code optimization effectiveness.

### Next Steps
1. Run identical benchmark with alternative LLM models
2. Compare optimization discovery rates across models
3. Analyze code quality and correctness across different models
4. Document model-specific strengths and weaknesses

---

**Experiment Details:**
- Date: August 14, 2025
- Duration: 114.6 minutes
- Hardware: MacOS (Darwin 24.5.0)
- OpenEvolve Version: Current main branch
- API Provider: OpenRouter