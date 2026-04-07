import java.sql.*;

public class GetMySqlSchema {
    public static void main(String[] args) {
        String url = "jdbc:mysql://192.168.68.172:3308/fylqz_platform_new?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=GMT+8";
        String user = "root";
        String pass = "62901990552";
        
        String[] tables = {"fqz_all_yy_yd", "fqz_ptzy_hosp", "fqz_ptzy_tcq_yydj"};
        
        try {
            Class.forName("com.mysql.cj.jdbc.Driver");
            try (Connection conn = DriverManager.getConnection(url, user, pass)) {
                for (String table : tables) {
                    System.out.println("SCHEMA_START:" + table);
                    try (Statement stmt = conn.createStatement();
                         ResultSet rs = stmt.executeQuery("DESCRIBE " + table)) {
                        while (rs.next()) {
                            System.out.println(rs.getString("Field") + ":" + rs.getString("Type") + ":" + rs.getString("Null") + ":" + rs.getString("Key"));
                        }
                    } catch (Exception e) {
                        System.out.println("ERROR:" + e.getMessage());
                    }
                    System.out.println("SCHEMA_END:" + table);
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
