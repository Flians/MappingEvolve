#!/usr/bin/env python3
"""
Python script to append [:-n] lines from a source hpp file to the end of mapping.hpp

Usage:
    python append_hpp_code.py <source_hpp_file> [n]

Arguments:
    source_hpp_file: Path to the source hpp file to read from
    n: Number of lines to exclude from the end

Example:
    python append_hpp_code.py /path/to/source.hpp 3
    This will append all but the last 3 lines from source.hpp to mapping.hpp
"""

import shutil
import sys
import os
from pathlib import Path
from typing import Optional


def append_hpp_code(output_mapping_path: str, source_file_path: str, n: int, mapping_hpp_path: Optional[str] = None):
    """
    Append [:-n] lines from source hpp file to mapping.hpp

    Args:
        source_file_path (str): Path to the source hpp file
        output_mapping_path (str): Path to the output mapping.hpp file
        n (int): Number of lines to exclude from the end
    """
    # Get the directory of this script (openevolve/ccode)
    if mapping_hpp_path is None or not os.path.exists(mapping_hpp_path):
        script_dir = Path(__file__).parent
        mapping_hpp_path = script_dir / "mapping.hpp"

    # Convert source path to Path object
    source_path = Path(source_file_path)

    # Check if source file exists
    if not source_path.exists():
        print(f"Error: Source file '{source_path}' does not exist.")
        return False

    try:
        # Read the source file
        with open(source_path, 'r', encoding='utf-8') as f:
            source_lines = f.readlines()

        # Get [:-n] lines (all but the last n lines)
        if n <= 0:
            lines_to_append = source_lines
        else:
            lines_to_append = source_lines[3:-n]

        # Check if there are lines to append
        if not lines_to_append:
            print(f"Warning: No lines to append.")
            return True

        # Copy the mapping file to output_mapping_path
        if mapping_hpp_path is not output_mapping_path:
            shutil.copy(mapping_hpp_path, output_mapping_path)

        # Prepare the content to append
        append_content = ''.join(lines_to_append)

        # Add a comment separator for clarity
        separator = f"\n\n// ===== Appended from {source_path.name} (excluding last {n} lines) =====\n"

        # Append to mapping.hpp
        with open(output_mapping_path, 'a', encoding='utf-8') as f:
            f.write(separator)
            f.write(append_content)

        print(f"Successfully appended {len(lines_to_append)} lines from '{source_path}' to '{mapping_hpp_path}'")

        return True

    except Exception as e:
        print(f"Error processing files: {e}")
        return False


def merge_all_codes(output_mapping_path: str, file_list: list[str]):
    """
    Merge multiple hpp files into mapping.hpp by appending [:-n] lines from each file

    Args:
        file_list (list[str]): List of paths to source hpp files
        output_mapping_path (str): Path to the output mapping.hpp file
        n (int): Number of lines to exclude from the end (default: 1)
    """
    current_out_file = None
    for source_file in file_list:
        n = 1
        if 'match_phase.' in source_file:
            n = 18
        elif 'match_phase_exact.' in source_file:
            n = 120
        elif 'match_drop_phase.' in source_file:
            n = 135
        else:
            continue
        success = append_hpp_code(output_mapping_path, source_file, n, mapping_hpp_path=current_out_file)
        current_out_file = output_mapping_path
        if not success:
            print(f"Failed to append from {source_file}")
            continue


if __name__ == "__main__":
    # Execute the append operation
    # success = append_hpp_code('openevolve/ccode/mapping_all.hpp', 'openevolve/mapping/match_phase.cpp', 18)
    success = merge_all_codes('openevolve/ccode/mapping_all.hpp', ['openevolve/mapping/match_phase.cpp', 'openevolve/mapping/match_phase_exact.cpp', 'openevolve/mapping/match_drop_phase.cpp'])

    if not success:
        sys.exit(1)
    else:
        print("Operation completed successfully!")
