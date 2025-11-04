import os, sys
import re
import json
import random
from abc import ABC, abstractmethod

# Ensure parent directory is on sys.path for 'openevolve' package resolution
_this_dir = os.path.dirname(__file__)
_parent_dir = os.path.abspath(os.path.join(_this_dir, ".."))
if _parent_dir not in sys.path:
    sys.path.append(_parent_dir)

from typing import Callable
import importlib.util


def _get_append_hpp_code() -> Callable:
    """Return the append_hpp_code function by loading the module from file path."""
    module_path = os.path.join(_parent_dir, "openevolve", "ccode", "append_hpp_code.py")
    spec = importlib.util.spec_from_file_location("append_hpp_code_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load append_hpp_code from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.append_hpp_code


def _get_evaluator_evaluate() -> Callable:
    """Return the evaluate function from openevolve/mapping/evaluator.py via file path."""
    module_path = os.path.join(_parent_dir, "openevolve", "mapping", "evaluator.py")
    spec = importlib.util.spec_from_file_location("evaluator_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load evaluate from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


# Remove relative import that can break in some runners; we dynamically import above

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Messages will propagate to root logger which handles console and file output


class Node(ABC):
    "A representation of a node in the MCTS tree."

    @abstractmethod
    def find_children(self):
        "All possible successors of this node."
        return set()

    @abstractmethod
    def find_random_child(self):
        "Randomly choose a child of this node."
        return None

    @abstractmethod
    def is_terminal(self):
        "Returns True if the node has no children."
        return False

    @abstractmethod
    def reward(self):
        "The reward for this node."
        return 0


class LLMNode(Node):
    prompt = ""
    _node_counter = 0

    def __init__(self, previous_state_dict, planner, evolver, output_dir, openevolve=False, parent=None, depth: int = 0):
        self.previous_state_dict = previous_state_dict
        self.parent = parent
        self.planner = planner
        self.evolver = evolver
        self.openevolve = openevolve
        # Depth tracking (for logging/tracking purposes)
        self.depth = depth

        self.output_dir = output_dir

        # Initialize state dict
        self.state_dict = previous_state_dict.copy()

        # Generate unique node ID and path for directory naming
        LLMNode._node_counter += 1
        self.node_id = LLMNode._node_counter
        self.node_path = self._generate_node_path()
        self.state = None  # to be set later
        self.plan = None
        self.proposed_changes = None
        self.children = None
        self._reward_cache = None
        self._initialized = False

    def _generate_node_path(self):
        """Generate a path string that represents the tree structure."""
        if self.parent is None:
            return "root"

        parent_path = self.parent.node_path
        node_type = self.__class__.__name__.replace("Node", "").lower()
        return f"{parent_path} -> {node_type}_{self.node_id}"

    def _save_state_to_directory(self):
        """Save the current state to a directory with separate files."""
        # Create directory structure
        dir_path = os.path.join(self.output_dir, f"node_{self.node_id}")
        os.makedirs(dir_path, exist_ok=True)

        try:
            # Save metadata
            with open(f"{dir_path}/metadata.txt", 'w', encoding='utf-8') as f:
                f.write(f"Node Type: {self.__class__.__name__}\n")
                f.write(f"Node ID: {self.node_id}\n")
                f.write(f"Depth: {self.depth}\n")
                f.write(f"Node Path: {self.node_path}\n")
                f.write(f"Prompt: {self.prompt}\n")
                f.write("=" * 50 + "\n")
                f.write("PLAN:\n")
                f.write("=" * 50 + "\n")
                f.write(str(self.plan))
                f.write("\n" + "=" * 50 + "\n")
                f.write("PROPOSED CHANGES:\n")
                f.write("=" * 50 + "\n")
                f.write(str(self.proposed_changes))

            # Save each file in the state dict
            for filename, content in self.state.items():
                with open(f"{dir_path}/{filename}", 'w', encoding='utf-8') as f:
                    f.write(content)

            logger.info("Saved node state to directory: %s", dir_path)
        except Exception as e:
            logger.error("Failed to save state to directory %s: %s", dir_path, e)

    def ensure_initialized(self):
        if not self._initialized:
            self.state = self.make_a_move(self.state_dict)
            self._save_state_to_directory()
            self._initialized = True

    def find_children(self):
        if not self.children:
            # Do NOT initialize children here. They are lazy.
            # 9 choices: (Area/Delay/Balanced) × (match_phase.cpp/match_phase_exact.cpp/match_drop_phase.cpp)
            state_or_dict = self.state if self._initialized else self.state_dict
            self.children = {
                AreaMatchPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                AreaMatchPhaseExactNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                AreaMatchDropPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                DelayMatchPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                DelayMatchPhaseExactNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                DelayMatchDropPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                BalancedMatchPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                BalancedMatchPhaseExactNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
                BalancedMatchDropPhaseNode(state_or_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1),
            }
        return self.children

    def find_random_child(self):
        node_classes = [
            AreaMatchPhaseNode, AreaMatchPhaseExactNode, AreaMatchDropPhaseNode,
            DelayMatchPhaseNode, DelayMatchPhaseExactNode, DelayMatchDropPhaseNode,
            BalancedMatchPhaseNode, BalancedMatchPhaseExactNode, BalancedMatchDropPhaseNode
        ]
        return random.choice(node_classes)(self.state if self._initialized else self.state_dict, self.planner, self.evolver, self.output_dir, openevolve=self.openevolve, parent=self, depth=self.depth + 1)

    def is_terminal(self):
        # No longer using depth-based termination for rollouts
        # This method is kept for compatibility but always returns False
        return False

    def reward(self):
        self.ensure_initialized()
        if self._reward_cache is not None:
            return self._reward_cache

        try:
            # Prepare absolute paths to evolved source files under this node
            node_dir = os.path.abspath(os.path.join(self.output_dir, f"node_{self.node_id}"))
            file_names = ["match_phase.cpp", "match_phase_exact.cpp", "match_drop_phase.cpp"]
            program_paths = []
            for name in file_names:
                path = os.path.join(node_dir, name)
                if os.path.exists(path):
                    program_paths.append(path)

            if not program_paths:
                self._reward_cache = 0.0
                # Persist minimal reward info
                try:
                    os.makedirs(node_dir, exist_ok=True)
                    reward_info_path = os.path.join(node_dir, "reward.json")
                    with open(reward_info_path, 'w', encoding='utf-8') as f:
                        json.dump({"overall_score": None, "reward": self._reward_cache, "reason": "no program paths"}, f, ensure_ascii=False, indent=2)
                    with open(os.path.join(node_dir, "metadata.txt"), 'a', encoding='utf-8') as f:
                        f.write("\n" + "=" * 50 + "\n")
                        f.write("REWARD:\n")
                        f.write("=" * 50 + "\n")
                        f.write(str(self._reward_cache) + "\n")
                except Exception:
                    pass
                return self._reward_cache

            # Dynamically import evaluator.evaluate
            evaluate_fn = _get_evaluator_evaluate()
            result = evaluate_fn(program_paths)

            # Expect a dict with 'overall_score' (higher is better). Convert to reward in [0, 1).
            overall_score = result.get("overall_score") if isinstance(result, dict) else None
            if overall_score is None:
                self._reward_cache = 0.0
            else:
                try:
                    score_val = float(overall_score)
                    if score_val < 0:
                        # Guard: ensure positive domain
                        score_val = 0.0
                    self._reward_cache = score_val / (1.0 + score_val)
                except Exception:
                    self._reward_cache = 0.0

            # Persist reward info alongside node artifacts
            try:
                os.makedirs(node_dir, exist_ok=True)
                reward_payload = {
                    "overall_score": overall_score,
                    "reward": self._reward_cache,
                    "raw_result": result if isinstance(result, dict) else {"raw": result},
                }
                reward_info_path = os.path.join(node_dir, "reward.json")
                with open(reward_info_path, 'w', encoding='utf-8') as f:
                    json.dump(reward_payload, f, ensure_ascii=False, indent=2)

                # Also append to metadata.txt for quick inspection
                with open(os.path.join(node_dir, "metadata.txt"), 'a', encoding='utf-8') as f:
                    f.write("\n" + "=" * 50 + "\n")
                    f.write("REWARD:\n")
                    f.write("=" * 50 + "\n")
                    f.write(str(self._reward_cache) + "\n")
            except Exception:
                # Do not let persistence failures break reward computation
                pass
        except Exception as e:
            logger.error("Failed to compute reward for node %s: %s", self.node_id, e)
            self._reward_cache = 0.0

        return self._reward_cache

    def make_a_move(self, previous_state_dict):
        # Get the target file for this node
        target_file = getattr(self, 'target_file', None)
        assert target_file is not None, "Node must have a target_file attribute"
        
        # Planner proposes a plan based on the context and prompt
        planner_output = self.planner.get_output(previous_state_dict["context"] + self.prompt)

        # Extract the JSON dict from the plan output
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', planner_output, re.DOTALL)
        if json_match:
            try:
                plan_dict = json.loads(json_match.group(1))
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON in the plan output") from exc
        else:
            raise ValueError("No JSON found in the plan output")

        # Assertions: plan must have evolution_step and target_file must match
        assert "evolution_step" in plan_dict, f"Plan must contain 'evolution_step' field. Got keys: {list(plan_dict.keys())}"
        assert "target_file" in plan_dict, f"Plan must contain 'target_file' field. Got keys: {list(plan_dict.keys())}"
        assert plan_dict["target_file"] == target_file, f"Plan target_file '{plan_dict['target_file']}' does not match node target_file '{target_file}'"
        
        expected_files = {"match_phase.cpp", "match_phase_exact.cpp", "match_drop_phase.cpp"}
        assert target_file in expected_files, f"Target file {target_file} is not in expected files: {expected_files}"

        # Convert plan format to {filename: plan_description} for evolver
        # Plan format from planner: {target_file, persona, evolution_step}
        evolution_step = plan_dict["evolution_step"]
        self.plan = {
            target_file: json.dumps(evolution_step, indent=2)
        }

        # Evolver proposes changes for the target file
        self.proposed_changes = {}
        new_state = {}

        # Ensure node directory for persisting temporary files
        node_dir = os.path.join(self.output_dir, f"node_{self.node_id}")
        os.makedirs(node_dir, exist_ok=True)

        # Process the target file
        initial_code = previous_state_dict[target_file]

        if not self.openevolve:
            # Evolver returns JSON with evolved_file_content; extract and use only that
            evolver_input = f"Plan for {target_file}: {self.plan[target_file]}\n\nCurrent content:\n{initial_code}"
            evolver_output = self.evolver.get_output(evolver_input)

            evolved_content = None
            try:
                # Support code-fenced JSON or raw JSON
                evo_json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", evolver_output)
                if evo_json_match:
                    evo_json = json.loads(evo_json_match.group(1))
                else:
                    evo_json = json.loads(evolver_output)
                evolved_content = evo_json.get("evolved_file_content", "")
            except Exception:
                # Fallback: if parsing fails, use raw output as content
                evolved_content = evolver_output

            self.proposed_changes[target_file] = "Replaced with evolved file content"
            new_state[target_file] = evolved_content
        else:
            # Use openevolve.run_evolution for evolution
            from openevolve import run_evolution as _oe_run_evolution

            output_dir = os.path.join(node_dir, f"openevolve_output_{target_file.split('.')[0]}")
            config_path = os.path.join(_this_dir, "openevolve_config.yaml")
            # Persist initial code to a file and pass its path to OpenEvolve
            candidate_path = os.path.join(node_dir, f"initial_{target_file}")
            try:
                with open(candidate_path, 'w', encoding='utf-8') as f:
                    f.write(initial_code)
            except Exception as e:
                logger.error("Failed to write candidate file for %s: %s", target_file, e)
                self.proposed_changes[target_file] = f"Failed to write candidate: {e}"
                new_state[target_file] = initial_code
            else:
                try:
                    result = _oe_run_evolution(
                        initial_program=candidate_path,
                        evaluator=f"{_parent_dir}/openevolve/mapping/evaluator.py",
                        config=config_path,
                        output_dir=output_dir,
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
                        self.proposed_changes[target_file] = "OpenEvolve succeeded but best_code not found, kept original"
                    else:
                        self.proposed_changes[target_file] = "Evolved via OpenEvolve"

                    new_state[target_file] = evolved_content
                except Exception as e:
                    # Report error and keep original content; no fallback
                    logger.error("OpenEvolve run_evolution failed for %s: %s", target_file, e)
                    self.proposed_changes[target_file] = f"OpenEvolve failed: {e}"
                    new_state[target_file] = initial_code

        # Copy other files unchanged
        expected_files_set = {"match_phase.cpp", "match_phase_exact.cpp", "match_drop_phase.cpp"}
        for other_file in expected_files_set:
            if other_file != target_file:
                self.proposed_changes[other_file] = "No changes planned"
                new_state[other_file] = previous_state_dict[other_file]

        # Merge evolved sources into a new mapping_all.hpp and update context
        try:
            node_dir = os.path.join(self.output_dir, f"node_{self.node_id}")
            os.makedirs(node_dir, exist_ok=True)

            # Write evolved/current files to disk under this node directory
            file_order = [
                ("match_phase.cpp", 50),
                ("match_phase_exact.cpp", 152),
                ("match_drop_phase.cpp", 167),
            ]

            source_paths = {}
            for fname, _ in file_order:
                if fname in new_state:
                    path = os.path.join(node_dir, fname)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_state[fname])
                    source_paths[fname] = path

            output_mapping_path = os.path.join(node_dir, "mapping_all.hpp")

            current_base = None
            for fname, n_val in file_order:
                if fname not in source_paths:
                    continue
                append_fn = _get_append_hpp_code()
                append_fn(output_mapping_path, source_paths[fname], n_val, mapping_hpp_path=current_base)
                current_base = output_mapping_path

            if os.path.exists(output_mapping_path):
                with open(output_mapping_path, 'r', encoding='utf-8') as f:
                    merged_context = f.read()
                new_state["context"] = merged_context
            else:
                # Fallback to previous context if merge did not produce output
                new_state["context"] = previous_state_dict.get("context", "")
        except Exception as e:
            logger.error("Failed to merge mapping files for node %s: %s", self.node_id, e)
            new_state["context"] = previous_state_dict.get("context", "")

        return new_state


# 9 node classes: (Area/Delay/Balanced) × (match_phase.cpp/match_phase_exact.cpp/match_drop_phase.cpp)

class AreaMatchPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as an Area Optimizer. Your target evolution point file is: match_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_phase.cpp"


class AreaMatchPhaseExactNode(LLMNode):
    prompt = "\n\nYou are acting as an Area Optimizer. Your target evolution point file is: match_phase_exact.cpp. Propose a single evolution step for this file."
    target_file = "match_phase_exact.cpp"


class AreaMatchDropPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as an Area Optimizer. Your target evolution point file is: match_drop_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_drop_phase.cpp"


class DelayMatchPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as a Delay Optimizer. Your target evolution point file is: match_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_phase.cpp"


class DelayMatchPhaseExactNode(LLMNode):
    prompt = "\n\nYou are acting as a Delay Optimizer. Your target evolution point file is: match_phase_exact.cpp. Propose a single evolution step for this file."
    target_file = "match_phase_exact.cpp"


class DelayMatchDropPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as a Delay Optimizer. Your target evolution point file is: match_drop_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_drop_phase.cpp"


class BalancedMatchPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as a Balanced Optimizer. Your target evolution point file is: match_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_phase.cpp"


class BalancedMatchPhaseExactNode(LLMNode):
    prompt = "\n\nYou are acting as a Balanced Optimizer. Your target evolution point file is: match_phase_exact.cpp. Propose a single evolution step for this file."
    target_file = "match_phase_exact.cpp"


class BalancedMatchDropPhaseNode(LLMNode):
    prompt = "\n\nYou are acting as a Balanced Optimizer. Your target evolution point file is: match_drop_phase.cpp. Propose a single evolution step for this file."
    target_file = "match_drop_phase.cpp"


class CodeNode(LLMNode):
    def make_a_move(self, previous_state_dict):
        # For initial code node, the current state is the provided initial dict
        self.plan = {
            "match_phase.cpp": "Initial code - no plan needed",
            "match_phase_exact.cpp": "Initial code - no plan needed",
            "match_drop_phase.cpp": "Initial code - no plan needed",
        }
        self.proposed_changes = {
            "match_phase.cpp": "No changes - using initial code",
            "match_phase_exact.cpp": "No changes - using initial code",
            "match_drop_phase.cpp": "No changes - using initial code",
        }
        return previous_state_dict
