import java.sql.*;

public class CheckDataRange {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://127.0.0.1:8123/default";
        String user = "default";
        String pass = "";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement()) {
                
                ResultSet rs = stmt.executeQuery("SELECT min(setl_time), max(setl_time), count(*) FROM default.fqz_all_yy_yd");
                if (rs.next()) {
                    System.out.println("DATA_RANGE_START");
                    System.out.println("Min Date: " + rs.getString(1));
                    System.out.println("Max Date: " + rs.getString(2));
                    System.out.println("Total Rows: " + rs.getLong(3));
                    System.out.println("DATA_RANGE_END");
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
