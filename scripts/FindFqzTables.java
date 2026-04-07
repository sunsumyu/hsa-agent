import java.sql.*;

public class FindFqzTables {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://127.0.0.1:8123/";
        String user = "default";
        String pass = "";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement();
                 ResultSet rs = stmt.executeQuery("SELECT database, name FROM system.tables WHERE name LIKE '%fqz%'")) {
                
                System.out.println("FQZ_TABLES_START");
                while (rs.next()) {
                    System.out.println("Database: " + rs.getString(1) + ", Table: " + rs.getString(2));
                }
                System.out.println("FQZ_TABLES_END");
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
