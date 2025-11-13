import shutil
import sys
import argparse
import os
import re
import json
import yaml
from datetime import datetime
from typing import Callable, Dict, Any, Tuple, List
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
    evolution_context += f"**Evolution Point**: {evolution_step.get('evolution_point_id', 'None')}\n"
    evolution_context += f"**Objective**: {evolution_step.get('objective', 'None')}\n"
    evolution_context += f"**Direction and Strategy**: {evolution_step.get('direction_and_strategy', 'None')}\n"
    evolution_context += f"**Expected Impact**: {evolution_step.get('expected_impact', 'None')}\n"
    evolution_context += f"**Constraints**: {evolution_step.get('constraints', 'None')}\n"
    evolution_context += f"**Rationale**: {evolution_step.get('rationale', 'None')}\n"
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
    parser.add_argument("--model", type=str, default="qwen3-coder-plus", help="Model name")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--base-url", type=str, default="https://dashscope.aliyuncs.com/compatible-mode/v1", help="API base URL")
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
        "history": [],
    }


def build_planner_context(code_context, history=None):
    """
    Build context string for planner that includes code and previous iteration metrics.

    Args:
        code_context: The merged code context (mapping_all.hpp content)
        history: List of previous iteration results (dictionaries)

    Returns:
        (context_string, must_switch_module_flag: bool, previous_module: Optional[str])
    """
    context_parts = []
    last_entry = None
    if history:
        last_entry = history[-1]

    if last_entry:
        context_parts.append("## Previous Iteration Results")
        prev_json = {
            "chosen_module": last_entry.get("module", "None"),
            "chosen_strategy": last_entry.get("strategy", "None"),
            "area_score": last_entry.get("area_score", "None"),
            "delay_score": last_entry.get("delay_score", "None"),
            "overall_score": last_entry.get("overall_score", "None"),
            "failed_rate": last_entry.get("failed_rate", "None"),
        }
        context_parts.append("```json")
        try:
            context_parts.append(json.dumps(prev_json, ensure_ascii=False, indent=2))
        except Exception:
            context_parts.append("{\n  \"error\": \"failed to serialize previous results\"\n}")
        context_parts.append("```")
        context_parts.append("")

    # Add adaptive & diversity signals if history available
    must_switch_module = False
    previous_module_val = None
    if history:
        try:
            lookback_k = min(5, len(history))
            recent = history[-lookback_k:]
            delay_improvements = sum(1 for h in recent if isinstance(h.get("delay_score"), (int, float)) and (h.get("delay_score") or 0.0) > 0.0)
            area_improvements = sum(1 for h in recent if isinstance(h.get("area_score"), (int, float)) and (h.get("area_score") or 0.0) > 0.0)
            avg_delay = sum((h.get("delay_score") or 0.0) for h in recent) / max(1, len(recent))
            avg_area = sum((h.get("area_score") or 0.0) for h in recent) / max(1, len(recent))
            if delay_improvements == 0 and area_improvements == 0:
                objective_hint = "Balanced"
            elif avg_delay > 0 and avg_area > 0:
                objective_hint = "Balanced"
            elif avg_area > avg_delay:
                objective_hint = "Area Priority"
            else:
                objective_hint = "Delay Priority"

            # Module usage statistics
            from collections import Counter

            modules = [h.get("module") for h in history if h.get("module")]
            previous_module_val = modules[-1] if modules else None
            usage_counter = Counter(modules)
            all_modules = ["match_phase.cpp", "match_phase_exact.cpp", "match_drop_phase.cpp"]
            unexplored = [m for m in all_modules if usage_counter.get(m, 0) == 0]
            consecutive_same = 0
            if modules:
                for m in reversed(modules):
                    if m == previous_module_val:
                        consecutive_same += 1
                    else:
                        break
            # Stagnation: no improvements in recent window (independent of consecutive count)
            last_k_no_improve = delay_improvements == 0 and area_improvements == 0
            # Strict switch rule: if stagnation persists and same module is being reused frequently
            stagnation = last_k_no_improve
            must_switch_module = stagnation and consecutive_same >= 3

            # Recommend explore: unexplored first else least used different from last
            if unexplored:
                recommended_explore = unexplored[:2]
            else:
                # sort by usage ascending excluding current last module
                others = [m for m in all_modules if m != previous_module_val]
                recommended_explore = sorted(others, key=lambda x: usage_counter.get(x, 0))[:2]

            # Candidate weights heuristic: penalize fatigue on current module
            candidate_weights = {}
            for m in all_modules:
                base = 1.0
                fatigue_penalty = max(0, consecutive_same - 2) * 0.15 if modules and m == modules[-1] else 0.0
                explore_bonus = 0.3 if m in recommended_explore else 0.0
                candidate_weights[m] = round(base - fatigue_penalty + explore_bonus, 3)

            context_parts.append("## Adaptive & Diversity Signals")
            context_parts.append(f"Recent window size: {lookback_k}")
            context_parts.append(f"Avg area_score: {avg_area:.6f} | Avg delay_score: {avg_delay:.6f}")
            context_parts.append(f"Area improvements in window: {area_improvements} | Delay improvements in window: {delay_improvements}")
            context_parts.append(f"Objective Hint: {objective_hint}")
            context_parts.append(f"Module usage: {dict(usage_counter)}")
            context_parts.append(f"Consecutive same module: {consecutive_same}")
            context_parts.append(f"Unexplored modules: {unexplored if unexplored else 'None'}")
            context_parts.append(f"Recommended explore: {recommended_explore}")
            context_parts.append(f"Stagnation (no improvement in window): {stagnation}")
            context_parts.append(f"Must switch module (strict rule): {must_switch_module}")
            # Provide machine-readable JSON for planner
            diversity_json = {
                "objective_hint": objective_hint,
                "module_usage": dict(usage_counter),
                "consecutive_same_module": consecutive_same,
                "previous_module": previous_module_val,
                "unexplored_modules": unexplored,
                "recommended_explore": recommended_explore,
                "stagnation": stagnation,
                "last_k_no_improve": last_k_no_improve,
                "must_switch_module": must_switch_module,
                "candidate_weights": candidate_weights,
            }
            context_parts.append("```json")
            context_parts.append(json.dumps(diversity_json, ensure_ascii=False, indent=2))
            context_parts.append("```")
            context_parts.append("")
        except Exception as e:
            context_parts.append(f"<!-- diversity signals error: {e} -->")

    # Add the code context
    context_parts.append("## Current Code Context")
    context_parts.append(code_context)

    return "\n".join(context_parts), must_switch_module, previous_module_val


def prepare_evaluation_env(state_dict, iter_dir):
    """Copy evaluator and initial mapping files to iteration directory."""
    shutil.copy2(f'{PARENT_DIR}/mapping/evaluator.py', os.path.join(iter_dir, "evaluator.py"))
    shutil.copytree(f'{PARENT_DIR}/mapping', os.path.join(iter_dir, "initial_mapping"), dirs_exist_ok=True)

    file_order = [
        ("match_phase.cpp", 18),
        ("match_phase_exact.cpp", 120),
        ("match_drop_phase.cpp", 135),
    ]

    source_paths = {}
    for fname, _ in file_order:
        if fname in state_dict:
            path = os.path.join(iter_dir, 'initial_mapping', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(state_dict[fname])
            source_paths[fname] = path


def merge_mapping_files(state_dict, iter_dir):
    """Merge evolved source files into evolved_mapping_all.hpp and return updated context."""
    file_order = [
        ("match_phase.cpp", 18),
        ("match_phase_exact.cpp", 120),
        ("match_drop_phase.cpp", 135),
    ]

    source_paths = {}
    for fname, _ in file_order:
        if fname in state_dict:
            path = os.path.join(iter_dir, 'evolved_mapping', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(state_dict[fname])
            source_paths[fname] = path

    output_mapping_path = os.path.join(iter_dir, "evolved_mapping_all.hpp")
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
        path = os.path.join(iter_dir, 'evolved_mapping', name)
        if os.path.exists(path):
            program_paths.append(path)

    if not program_paths:
        return -1.0, None, None, None, None

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

        return reward, area_score, delay_score, overall_score, failed_rate
    except Exception as e:
        logger.error("Failed to evaluate iteration %d: %s", iteration, e)
        return -1.0, None, None, None, None


def evolve_single_iteration(state_dict, planner, evolver, output_dir, iteration, global_history):
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

    # Build planner context using global history (independent from state_dict)
    planner_context, must_switch_module_flag, previous_module_in_history = build_planner_context(state_dict['context'], history=global_history)

    planner_output = planner.get_output(planner_context)

    # Extract JSON from planner output with robustness to multiple blocks
    def _is_valid_plan(obj: Dict[str, Any]) -> bool:
        try:
            if not isinstance(obj, dict):
                return False
            if "chosen_evolution_point" not in obj or "chosen_strategy" not in obj or "evolution_step" not in obj:
                return False
            cep = obj.get("chosen_evolution_point", {})
            if not isinstance(cep, dict):
                return False
            cm = cep.get("chosen_module")
            return isinstance(cm, str) and len(cm) > 0
        except Exception:
            return False

    plan_dict = None
    fenced_blocks = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", planner_output)
    for block in fenced_blocks:
        try:
            candidate = json.loads(block)
            if _is_valid_plan(candidate):
                plan_dict = candidate
        except Exception:
            continue
    if plan_dict is None:
        # Fallback to raw JSON parse
        try:
            candidate = json.loads(planner_output)
            if _is_valid_plan(candidate):
                plan_dict = candidate
        except Exception as e:
            logger.error("No valid JSON plan found in planner output: %s", e)
            return state_dict, -1.0, None, None, None, None
    if plan_dict is None:
        logger.error("Planner output did not contain a valid plan JSON block")
        return state_dict, -1.0, None, None, None, None

    # Extract chosen evolution point and evolution step
    chosen_point = plan_dict.get("chosen_evolution_point", {})
    target_file = chosen_point.get("chosen_module", "")
    evolution_step = plan_dict.get("evolution_step", {})
    chosen_strategy = plan_dict.get("chosen_strategy", "Unknown")

    # Enforce must_switch_module via one lightweight retry if violated
    if must_switch_module_flag and previous_module_in_history and target_file == previous_module_in_history:
        logger.info("Must-switch violation detected (module=%s used consecutively under stagnation). Retrying planner once with explicit constraint.", target_file)
        retry_hint = (
            "\n\n[ENFORCEMENT NOTICE]\n"
            "Stagnation persists and the previous module '%s' was chosen again despite must_switch_module=true. "
            "You MUST choose a DIFFERENT module than '%s'. Prefer one of the recommended_explore modules from the diversity signals. "
            "Re-evaluate and output ONLY the corrected JSON plan." % (target_file, target_file)
        )
        # Append enforcement notice to original planner output context
        planner_output_retry = planner.get_output(planner_context + retry_hint)
        # Parse retry output using same logic
        fenced_blocks_retry = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", planner_output_retry)
        retry_plan = None
        for block in fenced_blocks_retry:
            try:
                cand = json.loads(block)

                # reuse validation function
                def _is_valid_plan(obj: Dict[str, Any]) -> bool:
                    if not isinstance(obj, dict):
                        return False
                    if "chosen_evolution_point" not in obj or "chosen_strategy" not in obj or "evolution_step" not in obj:
                        return False
                    cep = obj.get("chosen_evolution_point", {})
                    cm = cep.get("chosen_module") if isinstance(cep, dict) else None
                    return isinstance(cm, str) and len(cm) > 0 and cm != previous_module_in_history

                if _is_valid_plan(cand):
                    retry_plan = cand
            except Exception:
                continue
        if retry_plan is not None:
            plan_dict = retry_plan
            chosen_point = plan_dict.get("chosen_evolution_point", {})
            target_file = chosen_point.get("chosen_module", "")
            evolution_step = plan_dict.get("evolution_step", {})
            chosen_strategy = plan_dict.get("chosen_strategy", "Unknown")
            logger.info("Retry succeeded with new module: %s", target_file)
        else:
            logger.warning("Retry did not produce a valid switched module; proceeding with original selection (%s) and recording violation.", target_file)
            # Optionally could mark hist_entry later with violation flag (handled after evaluation)

    if not target_file or not evolution_step:
        logger.error("Planner output missing required fields")
        return state_dict, -1.0, None, None, None, None

    logger.info("Planner selected: %s with strategy: %s", target_file, chosen_strategy)

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
        return state_dict, -1.0, None, None, None, None
    # copy the evaluator.py to iter_dir
    prepare_evaluation_env(state_dict, iter_dir)

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
                    evaluator=os.path.join(iter_dir, "evaluator.py"),
                    config=cur_config_path,  # Use modified config with evolution_step
                    iterations=3,
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

    # Save evolver output
    with open(os.path.join(iter_dir, "evolver_output.txt"), 'w', encoding='utf-8') as f:
        f.write(evolver_output)
    with open(os.path.join(iter_dir, f"evolved_{target_file}"), 'w', encoding='utf-8') as f:
        f.write(evolved_content)

    # Step 3: Update state with evolved file
    new_state = state_dict.copy()
    new_state[target_file] = evolved_content

    # Step 4: Merge files and update context
    logger.info("Step 4: Merging files and updating context")
    new_context = merge_mapping_files(new_state, iter_dir)
    new_state["context"] = new_context

    # Step 5: Evaluate the evolved state
    logger.info("Step 5: Evaluating evolved code")
    reward, area_score, delay_score, overall_score, failed_rate = evaluate_state(output_dir, iteration)
    logger.info("Evaluation completed: reward=%.4f, area_score=%s, delay_score=%s, overall_score=%s, failed_rate=%s", reward, area_score, delay_score, overall_score, failed_rate)

    # Prepare this iteration history entry; do not decide acceptance here
    hist_entry = {
        "iteration": iteration,
        "module": target_file,
        "strategy": chosen_strategy,
        "area_score": area_score,
        "delay_score": delay_score,
        "overall_score": overall_score,
        "failed_rate": failed_rate,
        "must_switch_module": must_switch_module_flag,
        "switch_violation": must_switch_module_flag and previous_module_in_history and target_file == previous_module_in_history,
    }
    # Do not modify new_state['history'] here; managed by caller upon acceptance

    # Save metadata
    with open(os.path.join(iter_dir, "metadata.txt"), 'w', encoding='utf-8') as f:
        f.write(f"Iteration: {iteration}\n")
        f.write(f"Target File: {target_file}\n")
        f.write(f"Strategy: {chosen_strategy}\n")
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
    return new_state, reward, overall_score, area_score, delay_score, hist_entry


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
    best_delay = 0

    # Global history accumulates all iterations (accepted or reverted)
    global_history = []

    # Perform evolution iterations
    for i in range(args.iterations):
        evolved_state, reward, overall_score, area_score, delay_score, hist_entry = evolve_single_iteration(state_dict, planner, evolver, output_dir, i + 1, global_history)

        # Update best state if reward improved
        if reward > best_reward:
            best_reward = reward
            best_state = evolved_state.copy()
            best_iteration = i + 1
            if reward > 0:
                logger.info("🎉 New best SUCCESS: %.4f (overall_score: %s) at iteration %d", best_reward, overall_score, best_iteration)
            else:
                logger.info("📈 New best (least bad): %.4f (overall_score: %s) at iteration %d", best_reward, overall_score, best_iteration)
        # Multi-criteria acceptance logic
        accepted_by = None
        if reward >= args.revert_threshold:
            accepted = True
            accepted_by = "threshold"
        elif isinstance(delay_score, (int, float)) and delay_score is not None and delay_score > 0.9 * best_delay:
            accepted = True
            accepted_by = "delay_tradeoff"
        else:
            accepted = False
            accepted_by = "none"

        if best_delay > delay_score:
            best_delay = delay_score

        if hist_entry is None:
            hist_entry = {
                "iteration": i + 1,
                "module": None,
                "strategy": None,
                "area_score": None,
                "delay_score": None,
                "overall_score": None,
                "failed_rate": None,
            }
        hist_entry['accepted'] = accepted
        hist_entry['accepted_by'] = accepted_by
        global_history.append(hist_entry)
        # Trim global history (keep last 200 for wider diversity window)
        if len(global_history) > 200:
            global_history = global_history[-200:]

        if not accepted:
            logger.warning("⚠️  Reverting (accepted_by=%s, reward %.4f < %.2f)", accepted_by, reward, args.revert_threshold)
            state_dict = best_state.copy()
        else:
            logger.info("✅ Accepted via %s (reward %.4f)", accepted_by, reward)
            state_dict = evolved_state.copy()
            accepted_hist = list(state_dict.get('history', []))
            accepted_hist.append({k: hist_entry[k] for k in hist_entry if k not in ('accepted',)})
            state_dict['history'] = accepted_hist[-50:]

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
