path = r"e:\chain\hsa-agent\app\reporting\report_renderer.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"File size: {len(content)}")
print(f"Contains 'boundary_block': {'boundary_block' in content}")
print(f"Contains 'boundary': {'boundary' in content}")

# Print lines with 'boundary'
for idx, line in enumerate(content.split('\n')):
    if 'boundary' in line.lower() or 'finding_count == 0' in line:
        print(f"Line {idx+1}: {line.strip()}")
