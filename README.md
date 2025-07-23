# LODCE

## Environment
- cuda 12.1 / 11.8
```
pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121
pip install -f https://data.pyg.org/whl/torch-2.4.0+cu121.html torch_scatter==2.1.2
```
Or
```
pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu118
pip install -f https://data.pyg.org/whl/torch-2.4.0+cu118.html torch_scatter==2.1.2
```

- deepgate
```
git clone git@github.com:zshi0616/python-deepgate.git
cd python-deepgate
bash install.sh
```

## Run
- Compile Simulator 
```
cd ./src/CondSim
g++ -O3 simulator.cpp -o simulator
```
跑wrapper_gt.py, wrapper.py是model，还不能用

## Mapping
- Build
``` bash
./build.sh
```

- Run
``` bash
> ./build/mapping/emap third-party/mockturtle/experiments/benchmarks/adder.aig third-party/mockturtle/experiments/cell_libraries/asap7.genlib adder.v

[i] WARNING: 11 gates IGNORED (e.g., OA333x2_ASAP7_75t_R), too many inputs for the library settings
[i] processing third-party/mockturtle/experiments/benchmarks/adder.aig
resyn runtime: 0.01
[i] area: 102.80000028759241, gates: 887, depth: 130
mapping runtime: 0.01
```