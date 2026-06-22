import os
import json
import glob

history_dir = "e:/chain/hsa-agent/data/bench_history/*.json"
files = glob.glob(history_dir)

print(f"Found {len(files)} benchmark files.")
high_score_files = []

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
            # calculate average success score
            success_scores = []
            for case in data:
                if 'scores' in case and 'success' in case['scores']:
                    success_scores.append(case['scores']['success'])
            
            if success_scores:
                avg_success = sum(success_scores) / len(success_scores)
                if avg_success > 0:
                    high_score_files.append((f, avg_success, success_scores))
    except Exception as e:
        pass

# Sort by avg_success descending
high_score_files.sort(key=lambda x: x[1], reverse=True)

print("\n--- TOP HISTORICAL RUNS ---")
for f, avg, scores in high_score_files[:15]:
    basename = os.path.basename(f)
    print(f"File: {basename} | Avg Success: {avg:.2f} | Scores: {scores}")
