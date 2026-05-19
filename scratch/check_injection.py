import sys
import os

# 确保能加载 app 模块
sys.path.append(os.getcwd())

from app.skills.schema_injector import schema_injector

question = "核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？"
injected_content = schema_injector.inject(question, top_k=8)

print("="*50)
print("RAW INJECTED CONTENT FOR QA-11:")
print("="*50)
print(injected_content)
print("="*50)
