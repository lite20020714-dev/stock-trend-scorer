"""Command-line interface: holdings management plus trend screening output.

Usage:
    stock-trend-scorer add <code> [--market JP|US]
    stock-trend-scorer remove <code> [--market JP|US]
    stock-trend-scorer list
    stock-trend-scorer scan <code> [<code> ...] [--codes-file PATH] [--period 6mo] [--verbose]
    stock-trend-scorer scan --random N --universe jp|us [--period 6mo] [--verbose]
    stock-trend-scorer watch [--period 6mo] [--verbose]
    stock-trend-scorer backtest <code> [<code> ...] | --random N --universe jp|us [--output PATH] [--mode discovery|watch]
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import backtest as bt
from .market import detect_market, normalize_code
from .portfolio.repository import (
    AmbiguousHoldingError,
    DuplicateHoldingError,
    HoldingNotFoundError,
    HoldingsRepository,
)
from .scoring import CLASSIFICATION_DOWN, CLASSIFICATION_UP, TrendScorer
from .screening import ScreeningError, ScreeningResult, score_codes
from .universe import load_universe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-trend-scorer", description="保有銘柄の管理とトレンドスクリーニング")
    parser.add_argument("--file", type=Path, default=None, help="保有銘柄ファイルのパス(省略時は既定の保存先)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="銘柄を追加")
    add_parser.add_argument("code", help="銘柄コード(例: 7203, AAPL)")
    add_parser.add_argument("--market", choices=["JP", "US"], default=None, help="市場を明示指定(省略時は自動判定)")

    remove_parser = subparsers.add_parser("remove", help="銘柄を削除")
    remove_parser.add_argument("code", help="銘柄コード")
    remove_parser.add_argument("--market", choices=["JP", "US"], default=None, help="市場を明示指定")

    subparsers.add_parser("list", help="保有銘柄一覧を表示")

    scan_parser = subparsers.add_parser("scan", help="新規発掘: 指定銘柄から上昇トレンド候補をスクリーニング")
    _add_code_selection_args(scan_parser)
    scan_parser.add_argument("--period", default="1y", help="取得期間(例: 6mo, 1y, 2y。既定: 1y。52週高値の算出に約1年分のデータが必要)")
    scan_parser.add_argument("--verbose", action="store_true", help="指標ごとのスコアも表示")

    watch_parser = subparsers.add_parser("watch", help="保有監視: 保有銘柄の下落トレンドを検知")
    watch_parser.add_argument("--period", default="1y", help="取得期間(例: 6mo, 1y, 2y。既定: 1y。52週高値の算出に約1年分のデータが必要)")
    watch_parser.add_argument("--verbose", action="store_true", help="指標ごとのスコアも表示")

    backtest_parser = subparsers.add_parser(
        "backtest", help="バックテスト: 過去の基準時点ごとにスコアを算出し、その後の値動きをCSVに記録"
    )
    _add_code_selection_args(backtest_parser)
    backtest_parser.add_argument("--output", "-o", type=Path, default=None, help="出力CSVのパス(既定: backtest_YYYYMMDD_HHMMSS.csv)")
    backtest_parser.add_argument("--mode", choices=["discovery", "watch"], default="discovery", help="スコアリングモード(既定: discovery)")
    backtest_parser.add_argument("--config", type=Path, default=None, help="重み・閾値の設定JSON(省略時は既定値)")
    backtest_parser.add_argument("--start-months", type=int, default=bt.DEFAULT_START_MONTHS_AGO, help=f"最も古い基準時点(何ヶ月前か。既定: {bt.DEFAULT_START_MONTHS_AGO})")
    backtest_parser.add_argument("--end-months", type=int, default=bt.DEFAULT_END_MONTHS_AGO, help=f"最も新しい基準時点(何ヶ月前か。既定: {bt.DEFAULT_END_MONTHS_AGO})")
    backtest_parser.add_argument("--step-months", type=int, default=bt.DEFAULT_STEP_MONTHS, help=f"基準時点の間隔(月。既定: {bt.DEFAULT_STEP_MONTHS})")
    backtest_parser.add_argument("--horizon-months", type=int, default=bt.DEFAULT_HORIZON_MONTHS, help=f"評価期間(月。既定: {bt.DEFAULT_HORIZON_MONTHS})")
    backtest_parser.add_argument("--period", default=bt.DEFAULT_FETCH_PERIOD, help=f"価格データの取得期間(既定: {bt.DEFAULT_FETCH_PERIOD})")

    return parser


def _add_code_selection_args(parser: argparse.ArgumentParser) -> None:
    """Target-code options shared by `scan` and `backtest`."""
    parser.add_argument("codes", nargs="*", help="銘柄コード(複数指定可)")
    parser.add_argument("--codes-file", type=Path, default=None, help="銘柄コード一覧ファイル(1行1コード)")
    parser.add_argument("--random", type=int, default=None, metavar="N", help="ユニバースからN件をランダム抽出(--universe必須)")
    parser.add_argument("--universe", choices=["jp", "us"], default=None, help="--random時の対象銘柄ユニバース(jp: JPX日経400, us: S&P500)")


def _add(repo: HoldingsRepository, args: argparse.Namespace) -> int:
    market = args.market or detect_market(args.code)
    code = normalize_code(args.code, market)
    try:
        repo.add(code, market)
    except DuplicateHoldingError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    print(f"追加しました: {code} ({market})")
    return 0


def _remove(repo: HoldingsRepository, args: argparse.Namespace) -> int:
    code = normalize_code(args.code, args.market or detect_market(args.code))
    try:
        repo.remove(code, args.market)
    except (HoldingNotFoundError, AmbiguousHoldingError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    print(f"削除しました: {code}")
    return 0


def _list(repo: HoldingsRepository) -> int:
    holdings = repo.list()
    if not holdings:
        print("保有銘柄はありません")
        return 0
    for holding in holdings:
        print(f"{holding.code}\t{holding.market}")
    return 0


def _read_codes_file(path: Path) -> list[str]:
    codes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            codes.append(line)
    return codes


def _dedupe(items: list) -> list:
    seen: set = set()
    unique = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _format_results_table(results: list[ScreeningResult], verbose: bool = False) -> str:
    header = f"{'CODE':<10}{'MARKET':<8}{'SCORE':>8}  {'PRICE':>12}  {'52W HIGH%':>10}  CLASSIFICATION"
    lines = [header, "-" * len(header)]
    for result in results:
        score = result.score
        lines.append(
            f"{score.code:<10}{result.market:<8}{score.total_score:>8.3f}  "
            f"{score.current_price:>12.2f}  {score.week52_high_pct:>9.2f}%  {score.classification}"
        )
        if verbose:
            for indicator in score.indicators:
                lines.append(f"    - {indicator.name:<14}{indicator.score:>7.3f}")
    return "\n".join(lines)


def _print_errors(errors: list[ScreeningError]) -> None:
    if not errors:
        return
    print()
    print("取得・計算できなかった銘柄:")
    for error in errors:
        print(f"  {error.code} ({error.market}): {error.message}")


def _scan_random_pairs(args: argparse.Namespace) -> list[tuple[str, str]] | None:
    if args.codes or args.codes_file:
        print("エラー: --random は銘柄コード指定や --codes-file と同時に指定できません", file=sys.stderr)
        return None
    if not args.universe:
        print("エラー: --random を使う場合は --universe jp|us を指定してください", file=sys.stderr)
        return None
    if args.random <= 0:
        print("エラー: --random には1以上の値を指定してください", file=sys.stderr)
        return None

    market = args.universe.upper()
    universe_codes = load_universe(market)
    sample_size = min(args.random, len(universe_codes))
    sampled = random.sample(universe_codes, sample_size)
    return _dedupe([(code, market) for code in sampled])


def _scan_explicit_pairs(args: argparse.Namespace) -> list[tuple[str, str]] | None:
    raw_codes = list(args.codes)
    if args.codes_file:
        raw_codes.extend(_read_codes_file(args.codes_file))

    if not raw_codes:
        print("エラー: 銘柄コードを指定してください(引数、--codes-file、または --random)", file=sys.stderr)
        return None

    normalized_pairs = []
    for code in raw_codes:
        market = detect_market(code)
        normalized_pairs.append((normalize_code(code, market), market))
    return _dedupe(normalized_pairs)


def _select_pairs(args: argparse.Namespace) -> list[tuple[str, str]] | None:
    return _scan_random_pairs(args) if args.random is not None else _scan_explicit_pairs(args)


def _scan(args: argparse.Namespace) -> int:
    pairs = _select_pairs(args)
    if pairs is None:
        return 1

    scorer = TrendScorer(mode="discovery")
    results, errors = score_codes(pairs, scorer=scorer, is_held=False, period=args.period)
    results.sort(key=lambda r: r.score.total_score, reverse=True)

    candidates = [r for r in results if r.score.classification == CLASSIFICATION_UP]
    print(f"新規発掘スキャン: {len(results)}件中 上昇トレンド候補 {len(candidates)}件")
    print()
    print(_format_results_table(results, verbose=args.verbose))
    _print_errors(errors)
    return 0


def _watch(repo: HoldingsRepository, args: argparse.Namespace) -> int:
    holdings = repo.list()
    if not holdings:
        print("保有銘柄はありません")
        return 0

    pairs = [(h.code, h.market) for h in holdings]
    scorer = TrendScorer(mode="watch")
    results, errors = score_codes(pairs, scorer=scorer, is_held=True, period=args.period)
    results.sort(key=lambda r: r.score.total_score)

    warnings = [r for r in results if r.score.classification == CLASSIFICATION_DOWN]
    print(f"保有銘柄監視: {len(results)}件中 下落トレンド警告 {len(warnings)}件")
    print()
    print(_format_results_table(results, verbose=args.verbose))
    _print_errors(errors)
    return 0


def _print_backtest_errors(errors: list[bt.BacktestError]) -> None:
    """Summarize skipped samples per (code, reason) rather than one line per base date."""
    if not errors:
        return
    grouped: dict[tuple[str, str, str], int] = {}
    for error in errors:
        key = (error.code, error.market, error.message)
        grouped[key] = grouped.get(key, 0) + 1
    print()
    print(f"スキップしたサンプル: {len(errors)}件")
    for (code, market, message), count in grouped.items():
        print(f"  {code} ({market}): {message} ({count}件)")


def _backtest(args: argparse.Namespace) -> int:
    pairs = _select_pairs(args)
    if pairs is None:
        return 1
    try:
        base_dates = bt.generate_base_dates(
            pd.Timestamp.today(),
            start_months_ago=args.start_months,
            end_months_ago=args.end_months,
            step_months=args.step_months,
        )
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    if args.end_months < args.horizon_months:
        print(
            f"警告: --end-months ({args.end_months}) が --horizon-months ({args.horizon_months}) より小さいため、"
            "評価期間が現在を超える基準時点はスキップされます",
            file=sys.stderr,
        )

    scorer = TrendScorer(mode=args.mode, config_path=args.config)
    print(
        f"バックテスト: {len(pairs)}銘柄 × {len(base_dates)}時点 "
        f"({base_dates[0]:%Y-%m-%d} 〜 {base_dates[-1]:%Y-%m-%d}, 評価期間 {args.horizon_months}ヶ月)"
    )
    records, errors = bt.run_backtest(
        pairs,
        scorer=scorer,
        base_dates=base_dates,
        horizon_months=args.horizon_months,
        is_held=args.mode == "watch",
        period=args.period,
        on_progress=lambda i, n, code: print(f"  [{i}/{n}] {code}", file=sys.stderr),
    )

    if not records:
        print("有効なサンプルがありませんでした")
        _print_backtest_errors(errors)
        return 1

    df = bt.records_to_dataframe(records)
    output = args.output or Path(f"backtest_{datetime.now():%Y%m%d_%H%M%S}.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows the Japanese classification labels correctly.
    df.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"サンプル数: {len(df)}件 → {output}")
    print()
    print(f"スコア帯別サマリー(リターンは%、{args.horizon_months}ヶ月後):")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(bt.summarize_by_score_band(df).to_string())
    _print_backtest_errors(errors)
    return 0


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        return _scan(args)
    if args.command == "backtest":
        return _backtest(args)

    repo = HoldingsRepository(path=args.file)
    if args.command == "add":
        return _add(repo, args)
    if args.command == "remove":
        return _remove(repo, args)
    if args.command == "list":
        return _list(repo)
    return _watch(repo, args)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
