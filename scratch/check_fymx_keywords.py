import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def run():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    try:
        # Get all distinct hilist_name from fqz_fymx_test
        res = client.execute("SELECT DISTINCT hilist_name FROM default.fqz_fymx_test LIMIT 200")
        with open("scratch/fymx_names.txt", "w", encoding="utf-8") as f:
            for row in res:
                # Remove tabs or whitespaces
                name = row[0].strip()
                # Print hex representation too
                hex_repr = name.encode('utf-8').hex()
                f.write(f"{name} | {hex_repr}\n")
        print("Done!")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    run()
