import java.sql.*;

public class CheckDbConfig {
    public static void main(String[] args) {
        // Try various common local/internal URLs
        String[] urls = {
            "jdbc:mysql://172.18.27.30:15137/its?useSSL=false&characterEncoding=UTF-8&serverTimezone=GMT%2B8",
            "jdbc:mysql://127.0.0.1:3306/its?useSSL=false&serverTimezone=GMT%2B8",
            "jdbc:mysql://127.0.0.1:3306/hsa_audit?useSSL=false&serverTimezone=GMT%2B8"
        };
        String[] users = {"chuangzhi", "root", "root"};
        String[] passes = {"test@123", "root", "root"};

        for (int i = 0; i < urls.length; i++) {
            System.out.println("Trying connection: " + urls[i]);
            try (Connection conn = DriverManager.getConnection(urls[i], users[i], passes[i])) {
                System.out.println("Connection Success!");
                Statement stmt = conn.createStatement();
                ResultSet rs = stmt.executeQuery("SELECT db_code, db_host, db_port, dbs_name, db_type FROM t_sys_ds_config");
                System.out.println("--- t_sys_ds_config data ---");
                while (rs.next()) {
                    System.out.format("CODE: %s, HOST: %s, PORT: %s, NAME: %s, TYPE: %s%n",
                            rs.getString("db_code"),
                            rs.getString("db_host"),
                            rs.getString("db_port"),
                            rs.getString("dbs_name"),
                            rs.getString("db_type"));
                }
                return; 
            } catch (SQLException e) {
                System.err.println("Failed: " + e.getMessage());
            }
        }
        System.err.println("All connection attempts failed.");
    }
}
