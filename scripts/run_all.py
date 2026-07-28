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
    ("FRED macro fetch",   "fetch_fred",     True),
    ("OME vision extract", "extract_ome",    False),
    ("Score computation",  "compute_scores",  True),
    ("Dashboard builder",  "build_dashboard", True),
]

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
