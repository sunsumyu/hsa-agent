import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class RegexTester {
    public static void main(String[] args) {
        String regex = "\"content\"\\s*:\\s*null";
        Pattern pattern = Pattern.compile(regex, Pattern.DOTALL);
        
        String bodyString = "{\n" +
                "  \"role\": \"assistant\",\n" +
                "  \"content\": null,\n" +
                "  \"tool_calls\": []\n" +
                "}";

        System.out.println(">>> 原始测试文本:\n" + bodyString);
        
        if (pattern.matcher(bodyString).find()) {
            System.out.println("!!! [MATCHED] 成功匹配到 content:null");
            String newBody = bodyString.replaceAll(regex, "\"content\":\"\"");
            System.out.println(">>> 替换后结果:\n" + newBody);
            
            if (newBody.contains("\"content\":\"\"") && !newBody.contains("\"content\": null")) {
                System.out.println(">>> [SUCCESS] 正则替换逻辑验证通过！");
            } else {
                System.out.println(">>> [FAILURE] 替换后结果不符合预期！");
                System.exit(1);
            }
        } else {
            System.out.println(">>> [FAILURE] 正则匹配失败！");
            System.exit(1);
        }
    }
}
