import java.sql.*;

public class CheckMySql {
    public static void main(String[] args) {
        String url = "jdbc:mysql://192.168.68.172:3308/fylqz_platform_new?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=GMT%2B8";
        String user = "root";
        String pass = "62901990552";
        
        try {
            try {
                Class.forName("com.mysql.cj.jdbc.Driver");
            } catch (ClassNotFoundException e) {
                Class.forName("com.mysql.jdbc.Driver");
            }
            try (Connection conn = DriverManager.getConnection(url, user, pass);
                 Statement stmt = conn.createStatement();
                 ResultSet rs = stmt.executeQuery("SELECT count(*) FROM fqz_all_yy_yd")) {
                
                if (rs.next()) {
                    System.out.println("TOTAL_COUNT:" + rs.getLong(1));
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
