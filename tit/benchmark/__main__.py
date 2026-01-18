#!/usr/bin/env python3
"""
Entry point for running the benchmark module as a script.

Usage:
    python -m tit.benchmark         # Show help
    python -m tit.benchmark charm   # Run charm benchmark
    python -m tit.benchmark --help  # Show help
"""

import sys
import argparse
from pathlib import Path


def main():
    """Main entry point for the benchmark module CLI."""
    parser = argparse.ArgumentParser(
        prog="tit.benchmark",
        description="TI-Toolbox Benchmarking Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available benchmarks:
  charm     Benchmark SimNIBS charm (m2m) creation with Ernie data
  recon     Benchmark FreeSurfer recon-all with Ernie data
  dicom     Benchmark DICOM to NIfTI conversion
  flex      Benchmark flex-search optimization with multi-start (1,3,5 runs)

Examples:
  # Run charm benchmark (m2m creation)
  python -m tit.benchmark charm
  
  # Run recon-all benchmark
  python -m tit.benchmark recon
  
  # Run flex-search benchmark with multi-start
  python -m tit.benchmark flex
  
  # Run any benchmark in summary mode
  python -m tit.benchmark charm --no-debug
  
  # Show help for specific benchmark
  python -m tit.benchmark charm --help
""",
    )

    parser.add_argument(
        "benchmark",
        choices=["charm", "recon", "dicom", "flex"],
        nargs="?",
        help="Benchmark to run",
    )

    # If no arguments or just --help, show help
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ["-h", "--help"]):
        parser.print_help()
        sys.exit(0)

    # Parse first argument
    args, remaining = parser.parse_known_args()

    if args.benchmark == "charm":
        from tit.benchmark.charm import main as charm_main

        sys.argv = [sys.argv[0]] + remaining
        charm_main()
    elif args.benchmark == "recon":
        from tit.benchmark.recon import main as recon_main

        sys.argv = [sys.argv[0]] + remaining
        recon_main()
    elif args.benchmark == "dicom":
        from tit.benchmark.dicom import main as dicom_main

        sys.argv = [sys.argv[0]] + remaining
        dicom_main()
    elif args.benchmark == "flex":
        from tit.benchmark.flex import main as flex_main

        sys.argv = [sys.argv[0]] + remaining
        flex_main()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
