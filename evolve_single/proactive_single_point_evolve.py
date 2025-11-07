import sys
import argparse
import os
import re
import json
import yaml
from datetime import datetime
from typing import Callable, Dict, Any, Tuple
import importlib.util

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CUR_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from query_llm import DeepSeekModelCalls, QwenModelCalls
from prompts_optimized import PLANNER_SYSTEM_PROMPT_PROACTIVE, EVOLVER_SYSTEM_PROMPT_PROACTIVE

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


def _create_modified_config_with_evolution_step(iter_dir: str, original_config_path: str, evolution_step: Dict[str, Any]) -> str:
    """
    Create a config file with evolution_step incorporated into system_message.

    Args:
        iter_dir: Directory to save the modified config file
        original_config_path: Path to the original openevolve_config.yaml
        evolution_step: Dictionary containing evolution step details from planner

    Returns:
        Path to the created config file
    """
    # Load original config
    with open(original_config_path, 'r', encoding='utf-8') as f:
        config_dict = yaml.safe_load(f)

    # Store original system_message
    original_system_message = config_dict.get("prompt", {}).get("system_message", "")

    # Build evolution step context string
    evolution_context = "\n\n## Current Evolution Step (from Planner)\n"
    evolution_context += f"**Evolution Point**: {evolution_step.get('evolution_point_id', 'N/A')}\n"
    evolution_context += f"**Objective**: {evolution_step.get('objective', 'N/A')}\n"
    evolution_context += f"**Direction and Strategy**: {evolution_step.get('direction_and_strategy', 'N/A')}\n"
    evolution_context += f"**Expected Impact**: {evolution_step.get('expected_impact', 'N/A')}\n"
    evolution_context += f"**Constraints**: {evolution_step.get('constraints', 'N/A')}\n"
    evolution_context += f"**Rationale**: {evolution_step.get('rationale', 'N/A')}\n"
    evolution_context += "\n**Important**: Implement the modification described above while following all the rules and guidelines specified in this prompt.\n"

    # Modify system_message to include evolution step
    modified_system_message = original_system_message + evolution_context

    # Update config dict
    if "prompt" not in config_dict:
        config_dict["prompt"] = {}
    config_dict["prompt"]["system_message"] = modified_system_message

    # Create a config file
    cur_config_path = os.path.join(iter_dir, "openevolve_config.yaml")
    with open(cur_config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return cur_config_path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-v3-241226", help="Model name")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--base-url", type=str, default="https://ark.cn-beijing.volces.com/api/v3", help="API base URL")
    parser.add_argument("--iterations", type=int, default=30, help="Number of evolution iterations")
    parser.add_argument("--revert-threshold", type=float, default=-0.1, help="Revert to best state when reward is below this threshold")
    parser.add_argument("--openevolve", action="store_true", help="Use openevolve to evolve the code instead of LLM evolver")
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
        "prev_area_score": None,
        "prev_delay_score": None,
        "prev_overall_score": None,
        "prev_strategy": None,
    }


def build_planner_context(code_context, prev_area_score, prev_delay_score, prev_overall_score, prev_strategy):
    """
    Build context string for planner that includes code and previous iteration metrics.

    Args:
        code_context: The merged code context (mapping_all.hpp content)
        prev_area_score: Previous iteration's area_score (None for first iteration or if evaluation failed)
        prev_delay_score: Previous iteration's delay_score (None for first iteration or if evaluation failed)
        prev_overall_score: Previous iteration's overall_score (None for first iteration or if evaluation failed)
        prev_strategy: Previous iteration's optimization strategy (None for first iteration)

    Returns:
        Formatted context string for the planner
    """
    context_parts = []

    # Add previous iteration metrics if this is not the first iteration
    # Check if we have any indication this is not the first iteration (strategy is set or any score is set)
    is_first_iteration = prev_strategy is None and prev_area_score is None and prev_delay_score is None and prev_overall_score is None

    if not is_first_iteration:
        context_parts.append("## Previous Iteration Results")
        context_parts.append("The following information is from the previous evolution iteration:")
        context_parts.append("")

        if prev_strategy is not None:
            context_parts.append(f"**Optimization Strategy Used**: {prev_strategy}")
        else:
            context_parts.append("**Optimization Strategy Used**: Not available")

        if prev_area_score is not None:
            context_parts.append(f"**Area Reduction**: {prev_area_score}")
        else:
            context_parts.append("**Area Reduction**: Not available (evaluation may have failed)")

        if prev_delay_score is not None:
            context_parts.append(f"**Delay Reduction**: {prev_delay_score}")
        else:
            context_parts.append("**Delay Reduction**: Not available (evaluation may have failed)")

        if prev_overall_score is not None:
            context_parts.append(f"**Overall Score**: {prev_overall_score}")
        else:
            context_parts.append("**Overall Score**: Not available (evaluation may have failed)")

        context_parts.append("")
        '''
        context_parts.append("Use this information to guide your next evolution step. Consider:")
        context_parts.append("- Whether the previous strategy was effective")
        context_parts.append("- Which metric (area/delay/overall) needs improvement")
        context_parts.append("- Whether to continue with the same strategy or try a different approach")
        context_parts.append("- Lower scores are better (for area, delay, and overall_score)")
        context_parts.append("")
        context_parts.append("=" * 60)
        context_parts.append("")
        '''

    # Add the code context
    context_parts.append("## Current Code Context")
    context_parts.append(code_context)

    return "\n".join(context_parts)


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
        return -1.0, None, None, None

    try:
        evaluate_fn = _get_evaluator_evaluate()
        result = evaluate_fn(program_paths)

        # Initialize default values
        reward = 0.0
        area_score = None
        delay_score = None
        overall_score = None
        failed_rate = None
        error_msg = None
        error_type = "unknown"

        if not isinstance(result, dict):
            # Evaluation result format error - most severe
            error_msg = "Evaluation result is not a dictionary"
            error_type = "format_error"
            reward = -0.5  # Most negative reward for format errors
            logger.warning("Evaluation result is not a dictionary: %s", result)
        else:
            # Check for compilation or execution errors
            if "error" in result:
                error_msg = result["error"]
                error_type = "compilation_error"
                reward = -0.5  # Most negative reward for compilation errors
                logger.warning("Evaluation returned error: %s", error_msg)
            else:
                # Check failed_rate for logical equivalence
                failed_rate = result.get("failed_rate", 1.0)  # Default to 1.0 (failed) if not present
                overall_score = result.get("overall_score")
                delay_score = result.get("delay_score")
                area_score = result.get("area_score")

                if failed_rate > 0:
                    # Code has logical equivalence failures - less severe than compilation error
                    error_msg = f"Logical equivalence failed (failed_rate: {failed_rate})"
                    error_type = "logical_error"
                    # Reward decreases with failed_rate: [-0.5, -0.4)
                    reward = -0.4 - failed_rate / 10.0
                    logger.warning("Code failed logical equivalence check: failed_rate=%.3f", failed_rate)
                elif overall_score is not None:
                    # Check if overall_score is valid
                    try:
                        score_val = float(overall_score)
                        if score_val < 0:
                            error_type = "performance_reduction"
                            reward = max(-0.4, score_val)
                            logger.warning("Performance reduction: overall_score=%.4f", score_val)
                        else:
                            error_type = "success"
                            # Convert score to reward using sigmoid-like function
                            # Better (higher) overall_score gets higher reward
                            reward = score_val / (1.0 + score_val)
                            logger.info("Valid improvement: overall_score=%.4f", score_val)
                    except (ValueError, TypeError):
                        error_msg = f"Invalid overall_score format: {overall_score}"
                        error_type = "score_format_error"
                        reward = -0.5
                        logger.warning("Invalid overall_score: %s", overall_score)
                else:
                    error_msg = "Missing overall_score in result"
                    error_type = "missing_score"
                    reward = -0.5
                    logger.warning("Missing overall_score in evaluation result")

        # Save detailed reward info
        reward_info_path = os.path.join(iter_dir, "reward.json")
        with open(reward_info_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    "overall_score": overall_score,
                    "reward": reward,
                    "failed_rate": failed_rate,
                    "error_msg": error_msg,
                    "error_type": error_type,
                    "is_valid_code": failed_rate is not None and failed_rate == 0,
                    "is_improvement": reward > 0 and error_type == "success",
                    "raw_result": result if isinstance(result, dict) else {"raw": result},
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        return reward, overall_score, area_score, delay_score
    except Exception as e:
        logger.error("Failed to evaluate iteration %d: %s", iteration, e)
        return -1.0, None, None, None


def evolve_single_iteration(state_dict, planner, evolver, output_dir, iteration):
    """Perform one evolution iteration: planner proposes -> evolver implements -> evaluate.

    Args:
        state_dict: Current state (may not be the best state)
        planner: Planner model instance
        evolver: LLM evolver model instance (or None if using openevolve)
        output_dir: Directory to save outputs
        iteration: Current iteration number
    """
    logger.info("=" * 60)
    logger.info("Starting evolution iteration %d", iteration)
    logger.info("=" * 60)

    # Step 1: Planner analyzes context and proposes evolution point and plan
    logger.info("Step 1: Planner analyzing context and proposing evolution step")

    # Get previous iteration metrics from state_dict
    prev_area_score = state_dict.get('prev_area_score')
    prev_delay_score = state_dict.get('prev_delay_score')
    prev_overall_score = state_dict.get('prev_overall_score')
    prev_strategy = state_dict.get('prev_strategy')

    # Build context with previous iteration info
    planner_context = build_planner_context(state_dict['context'], prev_area_score, prev_delay_score, prev_overall_score, prev_strategy)

    planner_output = planner.get_output(planner_context)

    # Extract JSON from planner output
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', planner_output, re.DOTALL)
    if json_match:
        try:
            plan_dict = json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in planner output: %s", e)
            return state_dict, -1.0, None, None, None
    else:
        # Try parsing as raw JSON
        try:
            plan_dict = json.loads(planner_output)
        except json.JSONDecodeError as e:
            logger.error("No valid JSON found in planner output: %s", e)
            return state_dict, -1.0, None, None, None

    # Extract chosen evolution point and evolution step
    chosen_point = plan_dict.get("chosen_evolution_point", {})
    target_file = chosen_point.get("module", "")
    evolution_step = plan_dict.get("evolution_step", {})

    if not target_file or not evolution_step:
        logger.error("Planner output missing required fields")
        return state_dict, -1.0, None, None, None

    logger.info("Planner selected: %s with strategy: %s", target_file, plan_dict.get("chosen_strategy", "Unknown"))

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
        logger.error("Target file %s not found in planning state", target_file)
        return state_dict, -1.0, None, None, None

    if evolver:
        # Use LLM evolver
        evolver_input = f"Plan for {target_file}: {json.dumps(evolution_step, indent=2)}\n\nCurrent content:\n{initial_code}"
        evolver_output = evolver.get_output(evolver_input)

        # Extract evolved content from evolver output
        evolved_content = initial_code  # Default fallback
        try:
            evo_json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", evolver_output)
            if evo_json_match:
                evo_json = json.loads(evo_json_match.group(1))
            else:
                evo_json = json.loads(evolver_output)

            evolved_content = evo_json.get("evolved_file_content", initial_code)
        except Exception as e:
            logger.warning("Failed to parse evolver JSON, keeping original: %s", e)

        # Save evolver output
        with open(os.path.join(iter_dir, "evolver_output.txt"), 'w', encoding='utf-8') as f:
            f.write(evolver_output)
        with open(os.path.join(iter_dir, f"evolved_{target_file}"), 'w', encoding='utf-8') as f:
            f.write(evolved_content)
    else:
        # Use openevolve.run_evolution for evolution
        logger.info("Using openevolve to evolve %s", target_file)
        from openevolve import run_evolution as _oe_run_evolution

        openevolve_output_dir = os.path.join(iter_dir, f"openevolve_output_{target_file.split('.')[0]}")
        original_config_path = os.path.join(CUR_DIR, "openevolve_config.yaml")

        # Create modified config with evolution_step incorporated into system_message
        cur_config_path = _create_modified_config_with_evolution_step(iter_dir, original_config_path, evolution_step)
        logger.info("Created config with evolution_step at %s", cur_config_path)

        # Persist initial code to a file and pass its path to OpenEvolve
        candidate_path = os.path.join(iter_dir, f"initial_{target_file}")
        try:
            with open(candidate_path, 'w', encoding='utf-8') as f:
                f.write(initial_code)
        except Exception as e:
            logger.error("Failed to write candidate file for %s: %s", target_file, e)
            evolved_content = initial_code
            evolver_output = f"Failed to write candidate: {e}"
        else:
            try:
                result = _oe_run_evolution(
                    initial_program=candidate_path,
                    evaluator=f"{PARENT_DIR}/openevolve/mapping/evaluator.py",
                    config=cur_config_path,  # Use modified config with evolution_step
                    output_dir=openevolve_output_dir,
                )
                # Extract best_code from EvolutionResult
                evolved_content = None
                if hasattr(result, '__dict__'):
                    result_dict = result.__dict__
                    if 'best_code' in result_dict:
                        evolved_content = result_dict['best_code']

                # Fallback to original content if best_code not found
                if evolved_content is None:
                    logger.warning("best_code not found in OpenEvolve result for %s, keeping original content", target_file)
                    evolved_content = initial_code
                    evolver_output = "OpenEvolve succeeded but best_code not found, kept original"
                else:
                    evolver_output = "Evolved via OpenEvolve"
                    logger.info("OpenEvolve successfully evolved %s", target_file)

            except Exception as e:
                # Report error and keep original content; no fallback
                logger.error("OpenEvolve run_evolution failed for %s: %s", target_file, e)
                evolver_output = f"OpenEvolve failed: {e}"
                evolved_content = initial_code

        # Save evolver output (openevolve status)
        with open(os.path.join(iter_dir, "evolver_output.txt"), 'w', encoding='utf-8') as f:
            f.write(evolver_output)
        with open(os.path.join(iter_dir, f"evolved_{target_file}"), 'w', encoding='utf-8') as f:
            f.write(evolved_content)

    # Step 3: Update state with evolved file
    new_state = state_dict.copy()
    new_state[target_file] = evolved_content

    # Step 4: Merge files and update context
    logger.info("Step 4: Merging files and updating context")
    new_context = merge_mapping_files(new_state, output_dir, iteration)
    new_state["context"] = new_context

    # Step 5: Evaluate the evolved state
    logger.info("Step 5: Evaluating evolved code")
    reward, overall_score, area_score, delay_score = evaluate_state(output_dir, iteration)
    logger.info("Evaluation completed: reward=%.4f, overall_score=%s, area_score=%s, delay_score=%s", reward, overall_score, area_score, delay_score)

    # Store scores and strategy for next iteration
    new_state['prev_area_score'] = area_score
    new_state['prev_delay_score'] = delay_score
    new_state['prev_overall_score'] = overall_score
    new_state['prev_strategy'] = plan_dict.get('chosen_strategy', 'Unknown')

    # Save metadata
    with open(os.path.join(iter_dir, "metadata.txt"), 'w', encoding='utf-8') as f:
        f.write(f"Iteration: {iteration}\n")
        f.write(f"Target File: {target_file}\n")
        f.write(f"Strategy: {plan_dict.get('chosen_strategy', 'Unknown')}\n")
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
    return new_state, reward, overall_score, area_score, delay_score


def main():
    args = parse_args()

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evolve_type = "openevolve" if args.openevolve else "llm"
    output_dir = f"output/proactive_evolve_{evolve_type}_{args.model}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    console_handler_exists = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root_logger.handlers)

    if not console_handler_exists:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    log_file = os.path.join(output_dir, "log.txt")
    log_file_abs = os.path.abspath(log_file)
    file_handler_exists = any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == log_file_abs for h in root_logger.handlers)

    if not file_handler_exists:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.info("Output directory: %s", output_dir)
    logger.info("Logging to both console and file: %s", log_file)
    logger.info("Evolution mode: %s", "openevolve" if args.openevolve else "LLM evolver")

    # Create planner and evolver (evolver only used if not using openevolve)
    planner = create_model_calls(api_key=args.api_key, base_url=args.base_url, model_name=args.model, system_prompt=PLANNER_SYSTEM_PROMPT_PROACTIVE)
    evolver = create_model_calls(api_key=args.api_key, base_url=args.base_url, model_name=args.model, system_prompt=EVOLVER_SYSTEM_PROMPT_PROACTIVE) if not args.openevolve else None

    # Load initial state
    state_dict = load_initial_files()
    logger.info("Initial state loaded")

    # Track best state
    best_reward = -1.0
    best_state = state_dict.copy()
    best_iteration = 0

    # Perform evolution iterations
    for i in range(args.iterations):
        evolved_state, reward, overall_score, area_score, delay_score = evolve_single_iteration(state_dict, planner, evolver, output_dir, i + 1)

        # Update best state if reward improved
        if reward > best_reward:
            best_reward = reward
            best_state = evolved_state.copy()
            best_iteration = i + 1
            if reward > 0:
                logger.info("🎉 New best SUCCESS: %.4f (overall_score: %s) at iteration %d", best_reward, overall_score, best_iteration)
            else:
                logger.info("📈 New best (least bad): %.4f (overall_score: %s) at iteration %d", best_reward, overall_score, best_iteration)
        # We either keep the new state (if it's good) or revert to best state (if it's bad)
        if reward < args.revert_threshold:
            logger.warning("⚠️  Severe failure (reward %.4f < %.2f), will continue from best state", reward, args.revert_threshold)
            state_dict = best_state.copy()  # Revert to best state
        else:
            logger.info("✅ Acceptable result (reward %.4f ≥ %.2f), using new state", reward, args.revert_threshold)
            state_dict = evolved_state.copy()  # Use new state

    # Save final summary
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(
            {
                "total_iterations": args.iterations,
                "best_reward": best_reward,
                "best_iteration": best_iteration,
                "model": args.model,
                "openevolve": args.openevolve,
                "revert_threshold": args.revert_threshold,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info("Evolution completed. Best reward: %.4f at iteration %d", best_reward, best_iteration)


if __name__ == "__main__":
    main()
