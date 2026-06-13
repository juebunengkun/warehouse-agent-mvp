from __future__ import annotations

import argparse
from pathlib import Path

from dw_agent.graph import run_agent


DEMO_REQUIREMENT = (
    "做一个销售经营日报，按天、地区、渠道统计销售额、订单数、支付用户数和客单价。"
    "要求 T+1 每天早上刷新，可以查看近 30 天数据。"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the warehouse agent MVP.")
    parser.add_argument("--requirement", help="Natural language report requirement.")
    parser.add_argument("--demo", action="store_true", help="Run with a demo sales report requirement.")
    parser.add_argument("--output", help="Optional markdown output path.")
    args = parser.parse_args()

    requirement = args.requirement or DEMO_REQUIREMENT
    if not args.demo and not args.requirement:
        print("No requirement was provided. Running the demo requirement.\n")

    result = run_agent(requirement)
    report = result["final_report"]

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        print(f"Wrote report to {output_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
