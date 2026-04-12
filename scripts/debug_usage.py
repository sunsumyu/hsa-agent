import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv()

def test_usage():
    llm = ChatOpenAI(
        model="qwen-plus",
        api_key=os.getenv("BAILIAN_API_KEY"),
        base_url=os.getenv("BAILIAN_BASE_URL")
    )
    
    res = llm.invoke([HumanMessage(content="Hi")])
    print(f"Content: {res.content}")
    print(f"Usage Metadata: {res.usage_metadata}")

if __name__ == "__main__":
    test_usage()
