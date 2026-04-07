import java.sql.*;
import java.util.*;

public class ListTables {
    public static void main(String[] args) {
        String url = "jdbc:mysql://192.168.68.172:3308/its_db?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=GMT%2B8";
        String user = "root";
        String pass = "62901990552";
        
        try {
            Class.forName("com.mysql.cj.jdbc.Driver");
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
