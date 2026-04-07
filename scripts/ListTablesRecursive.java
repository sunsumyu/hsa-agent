import java.sql.*;

public class ListTablesRecursive {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://127.0.0.1:8123/";
        String user = "default";
        String pass = "";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement()) {
                
                System.out.println("LIST_TABLES_START");
                ResultSet rs = stmt.executeQuery("SHOW DATABASES");
                while (rs.next()) {
                    String db = rs.getString(1);
                    System.out.println("Database: " + db);
                    try (Statement stmt2 = conn.createStatement();
                         ResultSet rs2 = stmt2.executeQuery("SHOW TABLES IN " + db)) {
                        while (rs2.next()) {
                            System.out.println("  Table: " + rs2.getString(1));
                        }
                    }
                }
                System.out.println("LIST_TABLES_END");
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
