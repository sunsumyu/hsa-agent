import java.sql.*;

public class CheckMultipleDataRanges {
    public static void main(String[] args) {
        String url = "jdbc:clickhouse://127.0.0.1:8123/default";
        String user = "default";
        String pass = "";
        
        String[] tables = {"fqz_all_yy_yd", "fqz_gz_jzsj_all_ql", "fqz_ptzy_hosp", "fqz_ztk_psn_yearly"};
        
        try {
            Class.forName("ru.yandex.clickhouse.ClickHouseDriver");
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement()) {
                
                for (String table : tables) {
                    System.out.println("Checking table: " + table);
                    try (ResultSet rs = stmt.executeQuery("SELECT min(setl_time), max(setl_time), count(*) FROM " + table)) {
                        if (rs.next()) {
                            System.out.println("  Min Date: " + rs.getString(1));
                            System.out.println("  Max Date: " + rs.getString(2));
                            System.out.println("  Total Rows: " + rs.getLong(3));
                        }
                    } catch (Exception e) {
                        // try other date column names if setl_time fails
                        try (ResultSet rs = stmt.executeQuery("SELECT count(*) FROM " + table)) {
                            if (rs.next()) {
                                System.out.println("  Total Rows (no setl_time): " + rs.getLong(1));
                            }
                        } catch (Exception e2) {
                            System.out.println("  Error: " + e2.getMessage());
                        }
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
