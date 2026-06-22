import os

def read_last_lines(filepath, num_lines=200):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    
    # Read the last N lines efficiently
    with open(filepath, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        
        buffer_size = 8192
        lines = []
        position = file_size
        
        while position > 0 and len(lines) <= num_lines:
            read_size = min(buffer_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)
            
            # Count newlines in chunk
            newlines = chunk.count(b'\n')
            lines.insert(0, chunk)
            
            if len(lines) * 10 > num_lines:  # approximation
                # check actual line count
                combined = b''.join(lines)
                if combined.count(b'\n') > num_lines:
                    break
        
        combined = b''.join(lines)
        all_lines = combined.split(b'\n')
        last_lines = all_lines[-num_lines:]
        for line in last_lines:
            try:
                print(line.decode('utf-8', errors='ignore'))
            except Exception as e:
                print(f"[Error decoding line]: {e}")

if __name__ == "__main__":
    read_last_lines(r"C:\Users\AREN\.codex\.sandbox\sandbox.log", 200)
