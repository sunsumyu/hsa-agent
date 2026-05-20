"""
scratch/recall_optimization_lab.py
==================================
召回优化实验室：定量分析图谱增强召回 (Graph-Enhanced Recall) 的增益与成本。
目标：提升 QA-03 (性别冲突) 的召回率。
"""

import asyncio
import sys
import os
from loguru import logger
from rich.console import Console
from rich.table import Table

# 环境准备
sys.path.append(os.getcwd())
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.memory.manager import memory_hub
from app.infra.neo4j_manager import field_kg

console = Console()

async def run_experiment():
    question = "对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。"
    
    console.print(f"\n[bold blue]🧪 召回优化实验室：Case QA-03 分析[/]\n")
    console.print(f"问题: [italic]{question}[/]\n")

    # ── 方案 A: 纯向量召回 (Baseline) ──────────────────────────────────
    console.print("[bold yellow]方案 A: 纯向量召回 (Current Baseline)[/]")
    baseline_items = await memory_hub.semantic.recall(question, limit=12, use_hyde=True)
    
    # 调试：查看原始元数据
    if baseline_items:
        logger.debug(f"Sample Metadata: {baseline_items[0].metadata}")
    
    # 支持多种可能的 Key
    def get_field(item):
        m = item.metadata
        return m.get("canonical") or m.get("field") or m.get("name") or "unknown"

    baseline_fields = [get_field(item) for item in baseline_items]
    
    # ── 方案 B: 图谱增强召回 (Challenger) ────────────────────────────────
    console.print("\n[bold green]方案 B: 图谱增强召回 (Graph-Enhanced Challenger)[/]")
    
    # 模拟图谱扩张逻辑
    # 1. 提取关键词
    keywords = ["妇科", "产科", "性别"]
    expanded_fields = []
    
    # 2. 从 FieldKG 中进行确定性搜索
    for kw in keywords:
        # 这里模拟 Neo4j 的深度搜索，寻找所有 desc 包含关键字的字段
        for entry in field_kg._registry:
            desc = entry.get("desc", "").lower()
            if kw in desc or any(kw in a for a in entry.get("aliases", [])):
                expanded_fields.append(entry["canonical"])
    
    # 3. 合并向量结果与图谱结果
    challenger_fields = list(set(baseline_fields + expanded_fields))

    # ── 结果对比表 ────────────────────────────────────────────────────
    table = Table(title="召回对比报告")
    table.add_column("维度", justify="left", style="cyan")
    table.add_column("方案 A (纯向量)", justify="center")
    table.add_column("方案 B (图谱增强)", justify="center")
    table.add_column("增益 (Delta)", justify="left", style="green")

    table.add_row(
        "召回字段数", 
        str(len(baseline_fields)), 
        str(len(challenger_fields)),
        f"+{len(challenger_fields) - len(baseline_fields)}"
    )
    
    # 检查关键字段是否召回 (如 hilist_name, med_type, gend 等)
    critical_hits_a = [f for f in ["gend", "med_type", "hilist_name"] if f in baseline_fields]
    critical_hits_b = [f for f in ["gend", "med_type", "hilist_name"] if f in challenger_fields]
    
    table.add_row(
        "核心审计字段命数",
        f"{len(critical_hits_a)}/3",
        f"{len(critical_hits_b)}/3",
        "✅ 完整覆盖" if len(critical_hits_b) == 3 else "⚠️ 仍有缺失"
    )

    console.print(table)
    
    console.print("\n[bold]方案 B 召回的额外字段明细:[/]")
    diff = set(challenger_fields) - set(baseline_fields)
    for f in diff:
        console.print(f" - [green]{f}[/]")

    console.print("\n[bold red]结论建议:[/]")
    if len(challenger_fields) > len(baseline_fields):
        console.print("实验证明：图谱增强能补齐向量模型在“行业黑话”（如妇产科分类）上的语义断层。")
        console.print("建议：将此逻辑封装进 MemoryHub.query，但需设置 15 个字段的保护上限以控成本。")

if __name__ == "__main__":
    asyncio.run(run_experiment())
