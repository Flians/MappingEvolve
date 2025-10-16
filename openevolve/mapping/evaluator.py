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
    program_path: str | os.PathLike | list[str | os.PathLike],
    project_dir: str | os.PathLike = f'{CUR_DIR}/../../',
    build_type: str = "Release",
    generator: str | None = None,
    target: str | None = None,
    exe_name_hint: str | None = 'mapping',
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

    # copy program to CUR_DIR/PROGRAM_NAME.tpp
    if not isinstance(program_path, list):
        program_path = [program_path]
    for p in program_path:
        tpp_name = os.path.basename(p).split(".")[0]
        shutil.copy(p, f"{project_dir}/mapping/{tpp_name}.tpp")

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
def run_with_timeout_cmake(program_path: str | list[str], timeout_seconds: float) -> str:
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


def evaluate(program_path: str | list[str]):
    """
    Evaluate the program by running it multiple times and checking how close
    it gets to the known global minimum.

    Args:
        program_path: Path to the program files

    Returns:
        Dictionary of metrics
    """

    try:
        # Run multiple trials
        num_trials = 1
        area_values = []
        gates_values = []
        delay_values = []
        depth_values = []
        runtime_values = []
        nec_values = []  # what is nec?
        failed_rate = 0

        for trial in range(num_trials):
            try:
                # Run with timeout
                result = run_with_timeout_cmake(program_path, timeout_seconds=1000)
                result = json.loads(result.splitlines()[-1])

                # Handle different result formats
                if isinstance(result, dict):
                    if len(result) == 6:
                        area, gates, delay, depth, runtime, nec = result['area'], result['gates'], result['delay'], result['depth'], result['runtime'], result['nec']
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
                failed_rate += nec

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
        if failed_rate == 1.0:
            return {
                "area_score": 0.0,
                "delay_score": 0.0,
                "speed_score": 0.0,
                "overall_score": 0.0,
                "error": "All trials failed",
            }

        # Calculate metrics
        alpha = 0.5
        avg_area = float(np.mean(area_values))
        avg_delay = float(np.mean(delay_values))
        avg_time = float(np.mean(runtime_values))
        overall_score = alpha * avg_area + (1 - alpha) * avg_delay

        return {
            "area_score": avg_area,
            "delay_score": avg_delay,
            "speed_score": avg_time,
            "overall_score": overall_score,  # This will be the primary selection metric
            "failed_rate": failed_rate,
        }
    except Exception as e:
        print(f"Evaluation failed completely: {str(e)}")
        print(traceback.format_exc())
        return {
            "area_score": 0.0,
            "delay_score": 0.0,
            "speed_score": 0.0,
            "overall_score": 0.0,
            "error": str(e),
        }


def evaluate_stage1(program_path):
    # Full evaluation as in the main evaluate function
    return evaluate(program_path)


def evaluate_stage2(program_path):
    # Full evaluation as in the main evaluate function
    return evaluate(program_path)


if __name__ == "__main__":
    all_names = ["match_phase", "match_phase_exact", "match_drop_phase"]
    paths = []
    for name in all_names:
        paths.append(f"./openevolve/mapping/{name}.cpp")
    try:
        output = evaluate(paths)  # run_with_timeout_cmake(path, timeout_seconds=400)
        print("Program output:", output)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
