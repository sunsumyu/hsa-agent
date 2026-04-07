import java.io.*;
import java.net.*;

public class SimpleRedisClient {
    public static void main(String[] args) {
        String host = "192.168.68.172";
        int port = 6379;
        System.out.println("Connecting to " + host + ":" + port + "...");
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 5000);
            socket.setSoTimeout(5000);
            OutputStream out = socket.getOutputStream();
            InputStream in = socket.getInputStream();
            
            // Send PING (No AUTH)
            String cmd = "PING\r\n";
            System.out.println("Sending: PING (no AUTH)");
            out.write(cmd.getBytes());
            out.flush();
            
            // Read response
            BufferedReader reader = new BufferedReader(new InputStreamReader(in));
            String response = reader.readLine();
            System.out.println("REDIS_RESPONSE: " + response);
            
        } catch (Exception e) {
            System.err.println("ERROR: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
