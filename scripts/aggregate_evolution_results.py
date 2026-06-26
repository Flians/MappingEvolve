#!/usr/bin/env python3
import os
import json
import csv
import argparse
from typing import List, Dict, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DIRS = [
    os.path.join(ROOT, 'output', 'openevolve_match_phase'),
    os.path.join(ROOT, 'output', 'openevolve_match_phase_exact'),
    os.path.join(ROOT, 'output', 'openevolve_match_drop_phase'),
]

OP_MAP = {
    'openevolve_match_phase': 'match_phase',
    'openevolve_match_phase_exact': 'match_phase_exact',
    'openevolve_match_drop_phase': 'match_drop_phase',
}


def collect_checkpoint_rows(run_dir: str) -> List[Dict]:
    ck_root = os.path.join(run_dir, 'checkpoints')
    if not os.path.isdir(ck_root):
        return []
    rows = []
    for name in sorted(os.listdir(ck_root)):
        if not name.startswith('checkpoint_'):
            continue
        path = os.path.join(ck_root, name, 'best_program_info.json')
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                info = json.load(f)
        except Exception:
            continue
        it = info.get('current_iteration')
        metrics = info.get('metrics', {}) or {}
        rows.append(
            {
                'iteration': it,
                'oe_iters': it,  # baseline: OpenEvolve iterations equal to checkpoint iteration
                'overall_score': metrics.get('overall_score'),
                'combined_score': metrics.get('combined_score'),
                'speed_score': metrics.get('speed_score'),
                'area_score': metrics.get('area_score'),
                'delay_score': metrics.get('delay_score'),
                'failed_rate': metrics.get('failed_rate'),
            }
        )
    rows = [r for r in rows if r['iteration'] is not None]
    rows.sort(key=lambda r: r['iteration'])
    return rows


def write_csv(rows: List[Dict], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fieldnames = ['iteration', 'oe_iters', 'overall_score', 'combined_score', 'speed_score', 'area_score', 'delay_score', 'failed_rate']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collect_proactive_rows(run_dir: str) -> List[Dict]:
    """Collect rows from proactive evolve driver output.

    Expects subfolders iter_1, iter_2, ... each with reward.json containing
    keys: overall_score, reward, failed_rate, error_type, raw_result{overall_score}.
    """
    rows: List[Dict] = []
    if not os.path.isdir(run_dir):
        return rows
    for name in sorted(os.listdir(run_dir)):
        if not name.startswith('iter_'):
            continue
        try:
            it = int(name.split('_')[1])
        except Exception:
            continue
        reward_path = os.path.join(run_dir, name, 'reward.json')
        if not os.path.isfile(reward_path):
            continue
        try:
            with open(reward_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
        except Exception:
            continue
        overall = info.get('overall_score')
        # Fallback to raw_result.overall_score if top-level missing
        if overall is None:
            rr = info.get('raw_result') or {}
            overall = rr.get('overall_score')
        rows.append(
            {
                'iteration': it,
                'oe_iters': it * 3,  # ours: 3 OpenEvolve iterations per outer iteration
                'overall_score': overall,
                'combined_score': (info.get('raw_result') or {}).get('combined_score'),
                'speed_score': (info.get('raw_result') or {}).get('speed_score'),
                'area_score': (info.get('raw_result') or {}).get('area_score'),
                'delay_score': (info.get('raw_result') or {}).get('delay_score'),
                'failed_rate': info.get('failed_rate'),
                'reward': info.get('reward'),
                'error_type': info.get('error_type'),
            }
        )
    rows.sort(key=lambda r: r['iteration'])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', nargs='*', default=DEFAULT_DIRS, help='Paths to openevolve run directories (with checkpoints/*)')
    ap.add_argument('--ours', type=str, default='', help='Path to proactive evolve run directory (iter_*/reward.json) to export as ours.csv')
    ap.add_argument('--outdir', default=os.path.join(ROOT, 'MappingEvolve', 'figures', 'data'), help='Output directory for CSVs')
    args = ap.parse_args()

    combined_rows = []
    for run in args.runs:
        if not os.path.isdir(run):
            print(f'Skip non-dir: {run}')
            continue
        key = os.path.basename(run.rstrip(os.sep))
        op = OP_MAP.get(key, key)
        rows = collect_checkpoint_rows(run)
        if not rows:
            print(f'No checkpoints found in {run}')
            continue
        out_csv = os.path.join(args.outdir, f'{op}.csv')
        write_csv(rows, out_csv)
        for r in rows:
            r2 = dict(r)
            r2['op'] = op
            combined_rows.append(r2)
        print(f'Wrote {out_csv} ({len(rows)} rows)')

    # write combined
    if combined_rows:
        combined_csv = os.path.join(args.outdir, 'combined.csv')
        fieldnames = ['op', 'iteration', 'oe_iters', 'overall_score', 'combined_score', 'speed_score', 'area_score', 'delay_score', 'failed_rate']
        with open(combined_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in combined_rows:
                w.writerow(r)
        print(f'Wrote {combined_csv} ({len(combined_rows)} rows)')

    # export ours (proactive evolve) if provided
    if args.ours:
        ours_rows = collect_proactive_rows(args.ours)
        if ours_rows:
            ours_csv = os.path.join(args.outdir, 'ours.csv')
            # Include reward and error_type by extending fieldnames, but keep pgfplots compatibility
            fieldnames = ['iteration', 'oe_iters', 'overall_score', 'combined_score', 'speed_score', 'area_score', 'delay_score', 'failed_rate', 'reward', 'error_type']
            os.makedirs(os.path.dirname(ours_csv), exist_ok=True)
            with open(ours_csv, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in ours_rows:
                    w.writerow(r)
            print(f'Wrote {ours_csv} ({len(ours_rows)} rows)')
        else:
            print(f'No proactive iterations found in {args.ours}')


if __name__ == '__main__':
    main()
