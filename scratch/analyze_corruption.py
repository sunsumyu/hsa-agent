
import sys

def analyze_file(filepath):
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
        
        lines = content.split(b'\n')
        for i, line in enumerate(lines):
            try:
                line.decode('utf-8')
            except UnicodeDecodeError:
                print(f"Line {i+1} has UnicodeDecodeError: {line}")
                continue
            
            decoded_line = line.decode('utf-8')
            if '"' in decoded_line:
                # Count quotes that are not escaped
                # Simple count for now, might need more logic if there are escaped quotes
                quotes_count = decoded_line.count('"')
                if quotes_count % 2 != 0:
                    print(f"Line {i+1} has odd number of quotes ({quotes_count}): {decoded_line}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_file(r'E:\chain\hsa-agent\app\schema_injector.py')
