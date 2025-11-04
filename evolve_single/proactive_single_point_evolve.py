import sys
import argparse
import os
import re
import json
from datetime import datetime
from typing import Callable
import importlib.util

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CUR_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from query_llm import DeepSeekModelCalls, QwenModelCalls
from prompts import PLANNER_SYSTEM_PROMPT_PROACTIVE, EVOLVER_SYSTEM_PROMPT_PROACTIVE

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_append_hpp_code() -> Callable:
    """Return the append_hpp_code function by loading the module from file path."""
    module_path = os.path.join(PARENT_DIR, "openevolve", "ccode", "append_hpp_code.py")
    spec = importlib.util.spec_from_file_location("append_hpp_code_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load append_hpp_code from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.append_hpp_code


def _get_evaluator_evaluate() -> Callable:
    """Return the evaluate function from openevolve/mapping/evaluator.py via file path."""
    module_path = os.path.join(PARENT_DIR, "openevolve", "mapping", "evaluator.py")
    spec = importlib.util.spec_from_file_location("evaluator_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load evaluate from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-v3-241226", help="Model name")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--base-url", type=str, default="https://ark.cn-beijing.volces.com/api/v3", help="API base URL")
    parser.add_argument("--iterations", type=int, default=20, help="Number of evolution iterations")
    return parser.parse_args()


def create_model_calls(api_key, base_url, model_name, system_prompt):
    model_name_lower = model_name.lower()
    if "qwen" in model_name_lower:
        return QwenModelCalls(api_key=api_key, base_url=base_url, model_name=model_name, system_prompt=system_prompt)
    else:
        return DeepSeekModelCalls(api_key=api_key, base_url=base_url, model_name=model_name, system_prompt=system_prompt)


def load_initial_files():
    """Load initial code files and return state dict."""
    with open(f"{CUR_DIR}/../openevolve/ccode/mapping_all.hpp", 'r', encoding='utf-8') as f:
        initial_code = f.read()

    with open(f"{CUR_DIR}/../openevolve/mapping/match_phase.cpp", 'r', encoding='utf-8') as f:
        match_phase = f.read()

    with open(f"{CUR_DIR}/../openevolve/mapping/match_phase_exact.cpp", 'r', encoding='utf-8') as f:
        match_phase_exact = f.read()

    with open(f"{CUR_DIR}/../openevolve/mapping/match_drop_phase.cpp", 'r', encoding='utf-8') as f:
        match_drop_phase = f.read()

    return {
        "context": initial_code,
        "match_phase.cpp": match_phase,
        "match_phase_exact.cpp": match_phase_exact,
        "match_drop_phase.cpp": match_drop_phase,
    }


def merge_mapping_files(state_dict, output_dir, iteration):
    """Merge evolved source files into mapping_all.hpp and return updated context."""
    file_order = [
        ("match_phase.cpp", 50),
        ("match_phase_exact.cpp", 152),
        ("match_drop_phase.cpp", 167),
    ]

    source_paths = {}
    for fname, _ in file_order:
        if fname in state_dict:
            path = os.path.join(output_dir, f"iter_{iteration}", fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(state_dict[fname])
            source_paths[fname] = path

    output_mapping_path = os.path.join(output_dir, f"iter_{iteration}", "mapping_all.hpp")
    append_fn = _get_append_hpp_code()

    current_base = None
    for fname, n_val in file_order:
        if fname not in source_paths:
            continue
        append_fn(output_mapping_path, source_paths[fname], n_val, mapping_hpp_path=current_base)
        current_base = output_mapping_path

    if os.path.exists(output_mapping_path):
        with open(output_mapping_path, 'r', encoding='utf-8') as f:
            return f.read()
    return state_dict.get("context", "")


def evaluate_state(output_dir, iteration):
    """Evaluate the evolved code and return reward."""
    iter_dir = os.path.join(output_dir, f"iter_{iteration}")
    file_names = ["match_phase.cpp", "match_phase_exact.cpp", "match_drop_phase.cpp"]
    program_paths = []
    
    for name in file_names:
        path = os.path.join(iter_dir, name)
        if os.path.exists(path):
            program_paths.append(path)

    if not program_paths:
        return 0.0, None

    try:
        evaluate_fn = _get_evaluator_evaluate()
        result = evaluate_fn(program_paths)
        overall_score = result.get("overall_score") if isinstance(result, dict) else None
        
        if overall_score is None:
            reward = 0.0
        else:
            try:
                score_val = float(overall_score)
                if score_val < 0:
                    score_val = 0.0
                reward = score_val / (1.0 + score_val)
            except Exception:
                reward = 0.0

        # Save reward info
        reward_info_path = os.path.join(iter_dir, "reward.json")
        with open(reward_info_path, 'w', encoding='utf-8') as f:
            json.dump({
                "overall_score": overall_score,
                "reward": reward,
                "raw_result": result if isinstance(result, dict) else {"raw": result},
            }, f, ensure_ascii=False, indent=2)

        return reward, overall_score
    except Exception as e:
        logger.error("Failed to evaluate iteration %d: %s", iteration, e)
        return 0.0, None


def evolve_single_iteration(state_dict, planner, evolver, output_dir, iteration):
    """Perform one evolution iteration: planner proposes -> evolver implements -> evaluate."""
    logger.info("=" * 60)
    logger.info("Starting evolution iteration %d", iteration)
    logger.info("=" * 60)

    # Step 1: Planner analyzes context and proposes evolution point and plan
    logger.info("Step 1: Planner analyzing context and proposing evolution step")
    context_with_files = (
        f"{state_dict['context']}\n\n"
        f"=== match_phase.cpp ===\n{state_dict['match_phase.cpp']}\n\n"
        f"=== match_phase_exact.cpp ===\n{state_dict['match_phase_exact.cpp']}\n\n"
        f"=== match_drop_phase.cpp ===\n{state_dict['match_drop_phase.cpp']}"
    )
    
    planner_output = planner.get_output(context_with_files)

    # Extract JSON from planner output
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', planner_output, re.DOTALL)
    if json_match:
        try:
            plan_dict = json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in planner output: %s", e)
            return state_dict, 0.0, None
    else:
        # Try parsing as raw JSON
        try:
            plan_dict = json.loads(planner_output)
        except json.JSONDecodeError as e:
            logger.error("No valid JSON found in planner output: %s", e)
            return state_dict, 0.0, None

    # Extract chosen evolution point and evolution step
    chosen_point = plan_dict.get("chosen_evolution_point", {})
    target_file = chosen_point.get("module", "")
    evolution_step = plan_dict.get("evolution_step", {})
    
    if not target_file or not evolution_step:
        logger.error("Planner output missing required fields")
        return state_dict, 0.0, None

    logger.info("Planner selected: %s with persona: %s", target_file, plan_dict.get("chosen_persona", "Unknown"))

    # Save planner output
    iter_dir = os.path.join(output_dir, f"iter_{iteration}")
    os.makedirs(iter_dir, exist_ok=True)
    with open(os.path.join(iter_dir, "planner_output.txt"), 'w', encoding='utf-8') as f:
        f.write(planner_output)
    with open(os.path.join(iter_dir, "plan.json"), 'w', encoding='utf-8') as f:
        json.dump(plan_dict, f, ensure_ascii=False, indent=2)

    # Step 2: Evolver implements the changes
    logger.info("Step 2: Evolver implementing changes to %s", target_file)
    initial_code = state_dict.get(target_file, "")
    if not initial_code:
        logger.error("Target file %s not found in state", target_file)
        return state_dict, 0.0, None

    evolver_input = (
        f"Plan for {target_file}: {json.dumps(evolution_step, indent=2)}\n\n"
        f"Current content:\n{initial_code}"
    )
    evolver_output = evolver.get_output(evolver_input)

    # Extract evolved content from evolver output
    evolved_content = None
    try:
        evo_json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", evolver_output)
        if evo_json_match:
            evo_json = json.loads(evo_json_match.group(1))
        else:
            evo_json = json.loads(evolver_output)
        evolved_content = evo_json.get("evolved_file_content", "")
    except Exception as e:
        logger.warning("Failed to parse evolver JSON, using raw output: %s", e)
        evolved_content = evolver_output

    if not evolved_content:
        logger.warning("No evolved content from evolver, keeping original")
        evolved_content = initial_code

    # Save evolver output
    with open(os.path.join(iter_dir, "evolver_output.txt"), 'w', encoding='utf-8') as f:
        f.write(evolver_output)
    with open(os.path.join(iter_dir, f"evolved_{target_file}"), 'w', encoding='utf-8') as f:
        f.write(evolved_content)

    # Step 3: Update state with evolved file
    new_state = state_dict.copy()
    new_state[target_file] = evolved_content

    # Step 4: Merge files and update context
    logger.info("Step 3: Merging files and updating context")
    new_context = merge_mapping_files(new_state, output_dir, iteration)
    new_state["context"] = new_context

    # Step 5: Evaluate the evolved state
    logger.info("Step 4: Evaluating evolved code")
    reward, overall_score = evaluate_state(output_dir, iteration)
    logger.info("Evaluation completed: reward=%.4f, overall_score=%s", reward, overall_score)

    # Save metadata
    with open(os.path.join(iter_dir, "metadata.txt"), 'w', encoding='utf-8') as f:
        f.write(f"Iteration: {iteration}\n")
        f.write(f"Target File: {target_file}\n")
        f.write(f"Persona: {plan_dict.get('chosen_persona', 'Unknown')}\n")
        f.write(f"Reward: {reward}\n")
        f.write(f"Overall Score: {overall_score}\n")
        f.write("=" * 50 + "\n")
        f.write("PLANNER OUTPUT:\n")
        f.write("=" * 50 + "\n")
        f.write(planner_output)
        f.write("\n" + "=" * 50 + "\n")
        f.write("EVOLVER OUTPUT:\n")
        f.write("=" * 50 + "\n")
        f.write(evolver_output)

    logger.info("Iteration %d completed", iteration)
    return new_state, reward, overall_score


def main():
    args = parse_args()

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"output/proactive_evolve_{args.model}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    console_handler_exists = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root_logger.handlers
    )
    
    if not console_handler_exists:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    log_file = os.path.join(output_dir, "log.txt")
    log_file_abs = os.path.abspath(log_file)
    file_handler_exists = any(
        isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == log_file_abs
        for h in root_logger.handlers
    )
    
    if not file_handler_exists:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    logger.info("Output directory: %s", output_dir)
    logger.info("Logging to both console and file: %s", log_file)

    # Create planner and evolver
    planner = create_model_calls(
        api_key=args.api_key,
        base_url=args.base_url,
        model_name=args.model,
        system_prompt=PLANNER_SYSTEM_PROMPT_PROACTIVE
    )
    evolver = create_model_calls(
        api_key=args.api_key,
        base_url=args.base_url,
        model_name=args.model,
        system_prompt=EVOLVER_SYSTEM_PROMPT_PROACTIVE
    )

    # Load initial state
    state_dict = load_initial_files()
    logger.info("Initial state loaded")

    # Track best state
    best_reward = 0.0
    best_state = state_dict.copy()

    # Perform evolution iterations
    for i in range(args.iterations):
        state_dict, reward, overall_score = evolve_single_iteration(
            state_dict, planner, evolver, output_dir, i + 1
        )
        
        # Update best state if reward improved
        if reward > best_reward:
            best_reward = reward
            best_state = state_dict.copy()
            logger.info("New best reward: %.4f (overall_score: %s)", best_reward, overall_score)

    # Save final summary
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            "total_iterations": args.iterations,
            "best_reward": best_reward,
            "model": args.model,
        }, f, ensure_ascii=False, indent=2)

    logger.info("Evolution completed. Best reward: %.4f", best_reward)


if __name__ == "__main__":
    main()

