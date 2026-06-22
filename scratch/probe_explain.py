import sqlglot
import sqlglot.expressions as exp

def probe_explain():
    sql = "EXPLAIN SELECT 1"
    try:
        expression = sqlglot.parse_one(sql, read="clickhouse")
        print(f"ROOT_TYPE: {type(expression)}")
        print(f"CLASSNAME: {expression.__class__.__name__}")
        print(f"IS_COMMAND: {isinstance(expression, exp.Command)}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    probe_explain()
