import java.sql.*;
import java.util.*;

public class CheckClickHouse {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://121.196.219.211:8123/default";
        String user = "default";
        String pass = "zmjk2018";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement();
                 ResultSet rs = stmt.executeQuery("SELECT count() FROM fqz_all_yy_yd")) {
                
                if (rs.next()) {
                    System.out.println("CK_TOTAL_COUNT:" + rs.getLong(1));
                }
            } catch (Exception e) {
                 System.out.println("CK_ERROR:" + e.getMessage());
                 e.printStackTrace();
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
