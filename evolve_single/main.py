import sys
import argparse
import os
from datetime import datetime

CUR_DIR = os.path.dirname(os.path.abspath(__file__))

from mcts import MCTS
from node import CodeNode
from query_llm import DeepSeekModelCalls, QwenModelCalls
from prompts import PLANNER_SYSTEM_PROMPT, EVOLVER_SYSTEM_PROMPT

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--model", type=str, default="deepseek-v3-241226", help="Model name")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--base-url", type=str, default="https://ark.cn-beijing.volces.com/api/v3", help="API base URL")
    parser.add_argument("--iterations", type=int, default=20, help="Number of MCTS iterations")
    parser.add_argument("--openevolve", action="store_true", help="Use OpenEvolve")
    parser.add_argument("--rollout-iterations", type=int, default=1, help="Number of rollout iterations")

    return parser.parse_args()


def get_initial_code():
    # Read mapping_all.hpp
    with open(f"{CUR_DIR}/../openevolve/ccode/mapping_all.hpp", 'r', encoding='utf-8') as f:
        return f.read()


def create_model_calls(api_key, base_url, model_name, system_prompt):
    model_name_lower = model_name.lower()
    if "qwen" in model_name_lower:
        return QwenModelCalls(api_key=api_key, base_url=base_url, model_name=model_name, system_prompt=system_prompt)
    else:
        # Default to DeepSeekModelCalls for other models
        return DeepSeekModelCalls(api_key=api_key, base_url=base_url, model_name=model_name, system_prompt=system_prompt)


def main():

    args = parse_args()

    # Create output directory with format: output/mcts_states_{model}_{timestamp}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"output/mcts_states_{args.model}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    # Configure root logger to ensure both console and file output
    # This ensures all child loggers (from node.py, mcts.py, query_llm.py, etc.) log to both console and file
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Ensure root logger has a console handler (if not already present)
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
    
    # Set log file to log.txt in the output directory
    log_file = os.path.join(output_dir, "log.txt")
    
    # Check if file handler already exists for this log file
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

    # original code, (optional: feedback) -> plan (area, delay, balanced)
    planner = create_model_calls(api_key=args.api_key, base_url=args.base_url, model_name=args.model, system_prompt=PLANNER_SYSTEM_PROMPT)
    # evolver returns complete file content per plan
    evolver = create_model_calls(api_key=args.api_key, base_url=args.base_url, model_name=args.model, system_prompt=EVOLVER_SYSTEM_PROMPT)

    initial_code = get_initial_code()

    # Read the three additional mapping files
    with open(f"{CUR_DIR}/../openevolve/mapping/match_phase.cpp", 'r', encoding='utf-8') as f:
        match_phase = f.read()

    with open(f"{CUR_DIR}/../openevolve/mapping/match_phase_exact.cpp", 'r', encoding='utf-8') as f:
        match_phase_exact = f.read()

    with open(f"{CUR_DIR}/../openevolve/mapping/match_drop_phase.cpp", 'r', encoding='utf-8') as f:
        match_drop_phase = f.read()

    # Construct initial state as a dict, including the shared context
    initial_state = {
        "context": initial_code,
        "match_phase.cpp": match_phase,
        "match_phase_exact.cpp": match_phase_exact,
        "match_drop_phase.cpp": match_drop_phase,
    }

    # Initialize MCTS and root node
    mcts = MCTS(rollout_iterations=args.rollout_iterations)
    root_node = CodeNode(initial_state, planner, evolver, output_dir, openevolve=args.openevolve, depth=0)

    # Perform MCTS iterations
    for i in range(args.iterations):
        logger.info("Performing MCTS iteration %d/%d", i + 1, args.iterations)
        mcts.do_iteration(root_node)


if __name__ == "__main__":
    main()
