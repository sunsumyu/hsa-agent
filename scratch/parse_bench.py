import json, sys, glob, os
files = sorted(glob.glob("data/bench_7dim_verbose_*.json"))
if not files:
    print("No bench file found"); sys.exit(1)
latest = files[-1]
print(f"Reading: {latest}")
data = json.load(open(latest, encoding="utf-8"))
for r in data:
    print(f"\n=== [{r['id']}] {r['tag']} ===")
    print(f"  agent_ok     : {r['agent_ok']}")
    print(f"  total_score  : {r['total_score']}/70")
    print(f"  actual_tokens: {r['actual']} (predicted {r['predicted']})")
    sc = r.get("scores", {})
    for dim in ["success","recall","precision","faithfulness","relevance","professionalism","interpretability"]:
        print(f"  {dim:<20}: {sc.get(dim, 'N/A')}/10")
    print(f"  advice       : {r.get('advice','')[:300]}")
