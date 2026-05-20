
import sys

def find_errors(filepath):
    with open(filepath, 'rb') as f:
        content = f.read()
    
    for i in range(len(content)):
        try:
            content[i:i+4].decode('utf-8')
        except UnicodeDecodeError as e:
            # This is not perfect but it will show us the neighborhood
            print(f"Error at byte {i}: {content[i:i+10]}")

if __name__ == "__main__":
    find_errors(r'E:\chain\hsa-agent\app\schema_injector.py')
