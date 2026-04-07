import java.nio.file.Files;
import java.nio.file.Paths;
import java.sql.*;
import java.util.Properties;

public class RunCkSqlV2 {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://127.0.0.1:8123/default";
        String user = "default";
        String pass = "";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            String sqlContent = new String(Files.readAllBytes(Paths.get("hsa-db/src/main/resources/sql/clickhouse_ddl.sql")));
            
            // Basic SQL parser (split by ;)
            String[] rawSqls = sqlContent.split(";");
            
            try (Connection conn = DriverManager.getConnection(url, user, pass)) {
                Statement stmt = conn.createStatement();
                for (String rawSql : rawSqls) {
                    String sql = rawSql.trim();
                    if (sql.isEmpty()) continue;
                    
                    // Filter out comments within the statement block for better reliability
                    StringBuilder cleanSql = new StringBuilder();
                    for (String line : sql.split("\n")) {
                        if (!line.trim().startsWith("--")) {
                            cleanSql.append(line).append("\n");
                        }
                    }
                    
                    String finalSql = cleanSql.toString().trim();
                    if (finalSql.isEmpty()) continue;
                    
                    System.out.println("Executing: " + finalSql.substring(0, Math.min(60, finalSql.length())) + "...");
                    try {
                        stmt.execute(finalSql);
                        System.out.println("Success.");
                    } catch (Exception ex) {
                        System.out.println("Partial Failure: " + ex.getMessage());
                        // Keep going if it's "Table already exists" or similar
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
