"""
Orchestrator: run all pipeline steps in order.
  1. Fetch FRED macro data
  2. Extract OME data from screenshots (Claude vision)
  3. Compute blended scores
  4. Build static HTML dashboard
"""
import os
import sys
import traceback

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

STEPS = [
    ("FRED macro fetch",       "fetch_fred",        True),
    ("Options data (Yahoo)",   "fetch_options_yf",  False),
    ("OME vision extract",     "extract_ome",       False),
    ("Score computation",      "compute_scores",    True),
    ("Vol & range forecast",   "calc_vol_range",    False),
    ("Economic calendar",      "fetch_events",      False),
    ("CFTC COT positioning",   "fetch_cot",         False),
    ("Live prices (Yahoo)",    "fetch_oanda",       False),
    ("Geopolitical risk news", "fetch_geopolitical", False),
    ("News sentiment (GDELT)", "fetch_sentiment",   False),
    ("Dashboard builder",      "build_dashboard",   True),
]
# Previously this list only had 4 of the 10 steps the live GitHub Actions
# workflow (.github/workflows/build.yml) actually runs, so `python
# scripts/run_all.py` locally produced a materially different (more broken)
# dashboard than what gets deployed — missing options OI, vol/range forecast,
# COT, live prices, geopolitical risk, and sentiment. Now mirrors the workflow.

def main():
    print("=" * 60)
    print("  MARKET DASHBOARD — Daily Pipeline")
    print("=" * 60)
    print()

    results = []
    for label, module_name, required in STEPS:
        print(f"\n── {label} ──")
        try:
            module = __import__(module_name)
            ok = module.run()
            if ok:
                print(f"✓ {label} succeeded")
                results.append((label, True))
            else:
                print(f"✗ {label} failed (non-fatal)" if not required else f"✗ {label} FAILED")
                results.append((label, False))
                if required:
                    print("ABORTING: required step failed")
                    break
        except Exception as e:
            traceback.print_exc()
            results.append((label, False))
            if required:
                print(f"ABORTING: required step {label} failed: {e}")
                break

    print("\n" + "=" * 60)
    print("  PIPELINE SUMMARY")
    print("=" * 60)
    for label, ok in results:
        status = "✓" if ok else "✗"
        print(f"  {status}  {label}")
    print()

    all_ok = all(ok for _, ok in results)
    print(f"Overall: {'SUCCESS' if all_ok else 'PARTIAL'}")
    return all_ok

if __name__ == "__main__":
    main()
