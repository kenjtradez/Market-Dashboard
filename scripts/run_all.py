"""
Run the whole pipeline in order. The GitHub Actions workflow calls this
too, so a local `python scripts/run_all.py` builds exactly what gets deployed.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# (label, module, required). Scoring runs after every input it reads.
STEPS = [
    ("Macro (FRED / Yahoo)",   "fetch_fred",         False),
    ("Options levels (Yahoo)", "fetch_options_yf",   False),
    ("CFTC COT positioning",   "fetch_cot",          False),
    ("Vol & range forecast",   "calc_vol_range",     False),
    ("Economic calendar",      "fetch_events",       False),
    ("Headlines & risk",       "fetch_geopolitical", False),
    ("Headline sentiment",     "fetch_sentiment",    False),
    ("Score computation",      "compute_scores",     True),
    ("Dashboard builder",      "build_dashboard",    True),
]


def main():
    results = []
    for label, module_name, required in STEPS:
        print(f"\n── {label} ──", flush=True)
        try:
            ok = bool(__import__(module_name).run())
        except Exception:
            traceback.print_exc()
            ok = False
        results.append((label, ok))
        if not ok and required:
            print(f"ABORTING: required step '{label}' failed")
            break

    print("\nPIPELINE SUMMARY")
    for label, ok in results:
        print(f"  {'OK ' if ok else 'FAIL'}  {label}")
    required_ok = all(ok for (label, ok), (_, _, req) in zip(results, STEPS) if req) and len(results) == len(STEPS)
    return 0 if required_ok else 1


if __name__ == "__main__":
    sys.exit(main())
