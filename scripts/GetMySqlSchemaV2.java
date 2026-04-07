import java.sql.*;
import java.util.ArrayList;
import java.util.List;

public class GetMySqlSchemaV2 {
    public static void main(String[] args) {
        String url = "jdbc:mysql://127.0.0.1:3308/fylqz_platform_new?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai&useUnicode=true&characterEncoding=UTF-8";
        String user = "root";
        String pass = "62901990552";
        
        try {
            Class.forName("com.mysql.cj.jdbc.Driver");
            try (Connection conn = DriverManager.getConnection(url, user, pass)) {
                List<String> tables = new ArrayList<>();
                try (ResultSet rs = conn.getMetaData().getTables("fylqz_platform_new", null, "%", new String[]{"TABLE"})) {
                    while (rs.next()) {
                        tables.add(rs.getString("TABLE_NAME"));
                    }
                }

                System.out.println("TOTAL_TABLES_FOUND:" + tables.size());

                for (String table : tables) {
                    System.out.println("\n--- TABLE_SCAN_START:" + table + " ---");
                    
                    System.out.println("[STRUCTURE]");
                    try (Statement stmt = conn.createStatement();
                         ResultSet rs = stmt.executeQuery("DESC " + table)) {
                        while (rs.next()) {
                            System.out.printf("%s | %s | %s | %s\n", 
                                rs.getString("Field"), rs.getString("Type"), 
                                rs.getString("Null"), rs.getString("Key"));
                        }
                    }

                    System.out.println("[SAMPLE_DATA]");
                    try (Statement stmt = conn.createStatement();
                         ResultSet rs = stmt.executeQuery("SELECT * FROM " + table + " LIMIT 3")) {
                        ResultSetMetaData meta = rs.getMetaData();
                        int cols = meta.getColumnCount();
                        int rowIdx = 1;
                        while (rs.next()) {
                            StringBuilder row = new StringBuilder("Row " + rowIdx++ + ": ");
                            for (int i = 1; i <= cols; i++) {
                                row.append(meta.getColumnName(i)).append("=").append(rs.getString(i)).append(", ");
                            }
                            System.out.println(row);
                        }
                    } catch (Exception e) {
                        System.out.println("DATA_ERROR:" + e.getMessage());
                    }
                    
                    System.out.println("--- TABLE_SCAN_END:" + table + " ---");
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
