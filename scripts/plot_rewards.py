#!/usr/bin/env python3
import os
import sys
import json
import argparse
from typing import Optional, Tuple, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_rewards_in_dir(root: str) -> Tuple[Optional[float], List[Tuple[str, float]]]:
    """
    Try to infer a representative reward for a run directory.
    Priority:
    1) summary.json -> best_reward
    2) max over all iter_*/reward.json -> reward
    3) fallback: compute reward from any found overall_score fields (score/(1+score))
    Returns (best_reward_or_none, detailed_list)
    detailed_list: list of (path, reward) pairs considered.
    """
    best_reward = None
    detailed: List[Tuple[str, float]] = []

    # 1) summary.json
    summary_path = os.path.join(root, "summary.json")
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict) and "best_reward" in s and isinstance(s["best_reward"], (int, float)):
                best_reward = float(s["best_reward"])
                detailed.append((summary_path, best_reward))
        except Exception:
            pass

    # 2) scan iter_*/reward.json
    for name in os.listdir(root):
        if not name.startswith("iter_"):
            continue
        iter_dir = os.path.join(root, name)
        if not os.path.isdir(iter_dir):
            continue
        reward_path = os.path.join(iter_dir, "reward.json")
        if os.path.isfile(reward_path):
            try:
                with open(reward_path, "r", encoding="utf-8") as f:
                    rj = json.load(f)
                if isinstance(rj, dict) and "reward" in rj and isinstance(rj["reward"], (int, float)):
                    r = float(rj["reward"])
                    detailed.append((reward_path, r))
                    if best_reward is None or r > best_reward:
                        best_reward = r
            except Exception:
                continue

    # 3) fallback: search any json holding overall_score and derive reward
    if best_reward is None:
        # Light recursive walk but capped
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                if not fn.endswith(".json"):
                    continue
                fpath = os.path.join(dirpath, fn)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                    if isinstance(obj, dict) and "overall_score" in obj:
                        sc = obj["overall_score"]
                        if isinstance(sc, (int, float)):
                            # reward = score / (1 + score) as in evaluate_state
                            r = float(sc) / (1.0 + float(sc)) if float(sc) >= 0 else max(-0.4, float(sc))
                            detailed.append((fpath, r))
                            if best_reward is None or r > best_reward:
                                best_reward = r
                except Exception:
                    continue
    return best_reward, detailed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="output/rewards_bar.png", help="Output image path for the bar chart")
    parser.add_argument("dirs", nargs="+", help="List of run directories to summarize")
    args = parser.parse_args()

    labels: List[str] = []
    rewards: List[float] = []
    missing: List[str] = []

    for d in args.dirs:
        d_abs = os.path.abspath(d)
        best_reward, detailed = find_rewards_in_dir(d_abs)
        label = os.path.basename(d_abs)
        if best_reward is None:
            missing.append(d)
            labels.append(label)
            rewards.append(0.0)
        else:
            labels.append(label)
            rewards.append(best_reward)
        # Print a short textual summary for the user
        print(f"{d}: best_reward={best_reward if best_reward is not None else 'N/A'}")
        if detailed:
            top_paths = ", ".join([os.path.relpath(p, d_abs) for p, _ in detailed[:3]])
            print(f"  samples: {top_paths}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    plt.figure(figsize=(max(10, len(labels) * 1.2), 5))
    bars = plt.bar(range(len(labels)), rewards, color="#4C78A8")
    plt.xticks(range(len(labels)), labels, rotation=20, ha='right')
    plt.ylabel("reward")
    plt.title("Best reward per run directory")
    # Label bars with values
    for rect, val in zip(bars, rewards):
        plt.text(rect.get_x() + rect.get_width()/2.0, rect.get_height(), f"{val:.3f}", ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved bar chart to {args.out}")
    if missing:
        print("Note: some directories lacked recognizable reward data, plotted as 0.0:")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
