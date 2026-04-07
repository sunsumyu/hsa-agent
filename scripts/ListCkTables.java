import java.sql.*;
import java.util.*;

public class ListCkTables {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://121.196.219.211:8123/default";
        String user = "default";
        String pass = "zmjk2018";
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement();
                 ResultSet rs = stmt.executeQuery("SHOW TABLES")) {
                
                List<String> tables = new ArrayList<>();
                while (rs.next()) {
                    tables.add(rs.getString(1));
                }
                
                System.out.println("TABLE_COUNTS_START");
                for (String table : tables) {
                    try (ResultSet countRs = stmt.executeQuery("SELECT count(*) FROM " + table)) {
                        if (countRs.next()) {
                            System.out.println(table + ":" + countRs.getLong(1));
                        }
                    } catch (Exception e) {
                        System.out.println(table + ":ERROR:" + e.getMessage());
                    }
                }
                System.out.println("TABLE_COUNTS_END");
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
