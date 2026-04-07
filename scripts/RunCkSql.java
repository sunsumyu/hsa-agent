import java.nio.file.Files;
import java.nio.file.Paths;
import java.sql.*;
import java.util.Properties;

public class RunCkSql {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://121.196.219.211:8123/default";
        String user = "default";
        String pass = "zmjk2018";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            String sqlContent = new String(Files.readAllBytes(Paths.get("hsa-db/src/main/resources/sql/clickhouse_ddl.sql")));
            String[] sqls = sqlContent.split(";");
            
            try (Connection conn = DriverManager.getConnection(url, user, pass)) {
                Statement stmt = conn.createStatement();
                for (String sql : sqls) {
                    if (sql.trim().isEmpty()) continue;
                    System.out.println("Executing: " + sql.trim().substring(0, Math.min(50, sql.trim().length())) + "...");
                    stmt.execute(sql.trim());
                    System.out.println("Success.");
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
