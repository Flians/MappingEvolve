import concurrent.futures
import numpy as np

import concurrent.futures
import subprocess
import sys
import os
import shutil
from pathlib import Path
import time
import json
import traceback

CUR_DIR = os.path.dirname(os.path.abspath(__file__))


class BuildRunError(Exception):
    pass


def build_and_run_cmake_project(
    program_path: str | os.PathLike,
    project_dir: str | os.PathLike = f'{CUR_DIR}/../../',
    build_type: str = "Release",
    generator: str | None = None,
    target: str | None = None,
    exe_name_hint: str | None = 'emap',
    env: dict | None = None,
) -> str:
    """
    - program_path: Path to the program file
    - project_dir: 包含 CMakeLists.txt 的目录
    - build_type: Debug/Release/RelWithDebInfo/MinSizeRel
    - generator: 指定 CMake 生成器，如 "Ninja"、"Unix Makefiles"、"Ninja Multi-Config"、"Visual Studio 17 2022"；None 时自动选择
    - target: 构建的目标名；None 时构建默认目标
    - exe_name_hint: 可执行文件名提示，用于在 build 目录中定位输出；不提供时尝试自动搜索
    - env: 额外的环境变量
    返回：目标可执行文件运行后的标准输出（字符串）
    """

    # copy program to CUR_DIR/evolve.cpp
    shutil.copy(program_path, f"{project_dir}/mapping/evolve.cpp")

    project_dir = Path(project_dir).resolve()
    if not (project_dir / "CMakeLists.txt").exists():
        raise BuildRunError(f"CMakeLists.txt not found in {project_dir}")

    build_dir = project_dir / "build"
    build_dir.mkdir(exist_ok=True)

    chosen_generator = generator
    if chosen_generator is None:
        if os.name != "nt":
            chosen_generator = "Unix Makefiles"
        else:
            if shutil.which("ninja"):
                chosen_generator = "Ninja"

    cmake_config_cmd = ["cmake", "-S", str(project_dir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=" + build_type]
    if chosen_generator:
        cmake_config_cmd.extend(["-G", chosen_generator])

    # 配置
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        subprocess.run(
            cmake_config_cmd,
            check=True,
            cwd=str(project_dir),
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise BuildRunError(f"CMake configure failed:\n{e.stdout}") from e

    # 构建
    cmake_build_cmd = ["cmake", "--build", str(build_dir), "--config", build_type]
    if target:
        cmake_build_cmd.extend(["--target", target])

    try:
        build_proc = subprocess.run(
            cmake_build_cmd,
            check=True,
            cwd=str(project_dir),
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise BuildRunError(f"CMake build failed:\n{e.stdout}") from e

    # 寻找可执行文件
    exe_path = None

    def is_executable(p: Path) -> bool:
        if os.name == "nt":
            return p.suffix.lower() == ".exe" and p.is_file()
        return p.is_file() and os.access(p, os.X_OK)

    candidates: list[Path] = []

    # 常见输出目录尝试：对于多配置生成器（如 VS/Ninja Multi-Config）会在子目录下放置
    likely_dirs = [
        build_dir,
        build_dir / build_type,
        build_dir / "bin",
        build_dir / "src",
    ]

    for d in likely_dirs:
        if d.exists():
            for p in d.rglob("*"):
                if is_executable(p):
                    candidates.append(p)

    if exe_name_hint:
        # 按名称提示过滤
        filtered = [p for p in candidates if exe_name_hint.lower() in p.name.lower()]
        if filtered:
            exe_path = sorted(filtered, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    if exe_path is None and candidates:
        exe_path = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]

    if exe_path is None:
        raise BuildRunError("Executable not found in build outputs. Provide exe_name_hint or target.")

    # run
    try:
        run_proc = subprocess.run(
            [str(exe_path), f"{CUR_DIR}/../../third-party/mockturtle/experiments/cell_libraries/asap7.genlib"],
            check=True,
            cwd=str(exe_path.parent),
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return run_proc.stdout
    except subprocess.CalledProcessError as e:
        raise BuildRunError(f"Executable returned non-zero exit code:\n{e.stdout}") from e


# 将原先基于线程池的超时包装，改为编译并运行
def run_with_timeout_cmake(program_path: str, timeout_seconds: float) -> str:
    """
    program_path: CMake 项目路径（包含 CMakeLists.txt）
    返回：可执行文件的 stdout 字符串
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(build_and_run_cmake_project, program_path)
        try:
            result = future.result(timeout=timeout_seconds)
            return result
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"Build or run timed out after {timeout_seconds} seconds")
        except BuildRunError:
            raise
        except Exception as e:
            raise BuildRunError(f"Unexpected error: {e}") from e


def evaluate(program_path):
    """
    Evaluate the program by running it multiple times and checking how close
    it gets to the known global minimum.

    Args:
        program_path: Path to the program file

    Returns:
        Dictionary of metrics
    """
    # Known global minimum (approximate)
    GLOBAL_MIN_X = -1.704
    GLOBAL_MIN_Y = 0.678
    GLOBAL_MIN_VALUE = -1.519

    try:
        # Run multiple trials
        num_trials = 10
        area_values = []
        gates_values = []
        delay_values = []
        depth_values = []
        runtime_values = []
        nec_values = []
        success_count = 0

        for trial in range(num_trials):
            try:
                # Run with timeout
                result = run_with_timeout_cmake(program_path, timeout_seconds=360)
                result = json.loads(result)

                # Handle different result formats
                if isinstance(result, dict):
                    if len(result) == 6:
                        area, gates, delay, depth, runtime, nec = result.values()
                        print(f"Trial {trial}: Got 6 values, area: {area}, gates: {gates}, delay: {delay}, depth: {depth}, runtime: {runtime}, nec: {nec}")
                    else:
                        print(f"Trial {trial}: Invalid result format, expected dict with 6 values but got {len(result)}")
                        continue
                else:
                    print(f"Trial {trial}: Invalid result format, expected dict but got {type(result)}")
                    continue

                # Calculate metrics
                area_values.append(area)
                gates_values.append(gates)
                delay_values.append(delay)
                depth_values.append(depth)
                runtime_values.append(runtime)
                nec_values.append(nec)
                success_count += nec > 0

            except TimeoutError as e:
                print(f"Trial {trial}: {str(e)}")
                continue
            except IndexError as e:
                # Specifically handle IndexError which often happens with early termination checks
                print(f"Trial {trial}: IndexError - {str(e)}")
                print("This is likely due to a list index check before the list is fully populated.")
                continue
            except Exception as e:
                print(f"Trial {trial}: Error - {str(e)}")
                print(traceback.format_exc())
                continue

        # If all trials failed, return zero scores
        if success_count == 0:
            return {
                "area_score": 0.0,
                "delay_score": 0.0,
                "speed_score": 0.0,
                "combined_score": 0.0,
                "error": "All trials failed",
            }

        # Calculate metrics
        avg_value = float(np.mean(values))
        avg_distance = float(np.mean(distances))
        avg_time = float(np.mean(times)) if times else 1.0

        # Convert to scores (higher is better)
        value_score = float(1.0 / (1.0 + abs(avg_value - GLOBAL_MIN_VALUE)))  # Normalize and invert
        distance_score = float(1.0 / (1.0 + avg_distance))
        speed_score = float(1.0 / avg_time) if avg_time > 0 else 0.0

        # calculate standard deviation scores
        # get x_std_score
        x_std_score = float(1.0 / (1.0 + np.std(x_values)))
        # get y_std_score
        y_std_score = float(1.0 / (1.0 + np.std(y_values)))
        standard_deviation_score = (x_std_score + y_std_score) / 2.0

        # Normalize speed score (so it doesn't dominate)
        speed_score = float(min(speed_score, 10.0) / 10.0)

        # Add reliability score based on success rate
        reliability_score = float(success_count / num_trials)

        # Calculate a single combined score that prioritizes finding good solutions
        # over secondary metrics like speed and reliability
        # Value and distance scores (quality of solution) get 90% of the weight
        # Speed and reliability get only 10% combined
        combined_score = float(0.35 * value_score + 0.35 * distance_score + standard_deviation_score * 0.20 + 0.05 * speed_score + 0.05 * reliability_score)

        # Also compute an "overall" score that will be the primary metric for selection
        # This adds a bonus for finding solutions close to the global minimum
        # and heavily penalizes solutions that aren't finding the right region
        if distance_to_global < 1.0:  # Very close to the correct solution
            solution_quality = 1.0
        elif distance_to_global < 3.0:  # In the right region
            solution_quality = 0.5
        else:  # Not finding the right region
            solution_quality = 0.1

        # Overall score is dominated by solution quality but also factors in the combined score
        overall_score = 0.8 * solution_quality + 0.2 * combined_score

        return {
            "value_score": value_score,
            "distance_score": distance_score,
            "standard_deviation_score": standard_deviation_score,
            "speed_score": speed_score,
            "reliability_score": reliability_score,
            "combined_score": combined_score,
            "overall_score": overall_score,  # This will be the primary selection metric
            "success_rate": reliability_score,
        }
    except Exception as e:
        print(f"Evaluation failed completely: {str(e)}")
        print(traceback.format_exc())
        return {
            "value_score": 0.0,
            "distance_score": 0.0,
            "speed_score": 0.0,
            "combined_score": 0.0,
            "error": str(e),
        }


def evaluate_stage1(program_path):
    """Second stage evaluation with more thorough testing"""
    # Full evaluation as in the main evaluate function
    return evaluate(program_path)


def evaluate_stage2(program_path):
    """Second stage evaluation with more thorough testing"""
    # Full evaluation as in the main evaluate function
    return evaluate(program_path)


if __name__ == "__main__":
    path = "/home/flynn/workplace/lodce/openevolve/mapping/initial_program.cpp"  # 假设 func 目录下有 CMakeLists.txt
    try:
        output = run_with_timeout_cmake(path, timeout_seconds=360)
        print("Program output:", output)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
