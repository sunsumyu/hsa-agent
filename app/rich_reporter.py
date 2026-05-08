import json
import os
from datetime import datetime
from typing import Dict, List, Any
from jinja2 import Template
from app.entity_extractor import extract_graph

class RichReportGenerator:
    """[V51.0] 专业医疗审计可视化引擎 - 仪表盘大改版"""
    
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <title>HSA 穿透式审计可视化控制台</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;700&family=Noto+Sans+SC:wght@300;500;700&display=swap" rel="stylesheet">
        <style>
            :root { 
                --primary: #1e293b; --accent: #10b981; --warning: #f59e0b; 
                --danger: #f43f5e; --bg: #f1f5f9; --card: #ffffff;
            }
            body { 
                font-family: 'Outfit', 'Noto Sans SC', sans-serif; 
                background: var(--bg); margin: 0; padding: 20px; color: var(--primary);
                line-height: 1.6;
            }
            .dashboard { max-width: 1300px; margin: 0 auto; display: grid; grid-template-columns: 1fr 350px; gap: 20px; }
            .main-panel { background: var(--card); padding: 30px; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
            .side-panel { display: flex; flex-direction: column; gap: 20px; }
            .glass-card { background: var(--card); padding: 25px; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
            
            .header { margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }
            .title-group h1 { margin: 0; font-size: 28px; font-weight: 700; color: #0f172a; }
            .title-group p { margin: 5px 0 0 0; color: #64748b; font-size: 14px; }
            
            .kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
            .kpi-card { padding: 20px; border-radius: 20px; background: #f8fafc; border: 1px solid #e2e8f0; }
            .kpi-card .val { font-size: 32px; font-weight: 800; display: block; margin-top: 5px; }
            .kpi-card .lbl { font-size: 13px; font-weight: 500; color: #64748b; }
            
            #graph-container { height: 600px; border-radius: 20px; background: #fafafa; border: 1px solid #f1f5f9; }
            #radar-container { height: 300px; }
            
            .finding-item { 
                background: #fdfdfd; padding: 20px; border-radius: 16px; margin-bottom: 15px;
                border: 1px solid #f1f5f9; transition: transform 0.2s;
            }
            .finding-item:hover { transform: translateY(-3px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); }
            .finding-item h4 { margin: 0 0 10px 0; color: var(--danger); font-size: 16px; display: flex; align-items: center; }
            .finding-item h4::before { content: '●'; margin-right: 10px; font-size: 12px; }
            
            .audit-tag { font-size: 12px; background: #eff6ff; color: #3b82f6; padding: 4px 10px; border-radius: 6px; font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="dashboard">
            <div class="main-panel">
                <div class="header">
                    <div class="title-group">
                        <h1>🔍 HSA 穿透审计决策中心</h1>
                        <p>端到端多模态稽核 - 工业级取证报告</p>
                    </div>
                    <div class="audit-tag">SESSION: {{ report_id }}</div>
                </div>

                <div class="kpi-row">
                    <div class="kpi-card">
                        <span class="lbl">涉案金额</span>
                        <span class="val" style="color: var(--danger);">¥{{ total_amount }}</span>
                    </div>
                    <div class="kpi-card">
                        <span class="lbl">违规线索条数</span>
                        <span class="val">{{ finding_count }}</span>
                    </div>
                    <div class="kpi-card">
                        <span class="lbl">审计置信度</span>
                        <span class="val" style="color: var(--accent);">{{ confidence }}%</span>
                    </div>
                </div>

                <div class="section-title" style="margin-bottom: 15px; font-weight: 700;">🔗 证据链穿透拓扑图</div>
                <div id="graph-container"></div>
                
                <div class="findings-list" style="margin-top: 30px;">
                    <div class="section-title" style="margin-bottom: 15px; font-weight: 700;">📜 审计发现明细</div>
                    {% for finding in findings %}
                    <div class="finding-item">
                        <h4>{{ finding.violation_type }}</h4>
                        <p style="font-size: 14px; margin-bottom: 10px;">{{ finding.evidence }}</p>
                        <div style="display: flex; gap: 10px;">
                            <span class="audit-tag" style="background: #fef2f2; color: #ef4444;">金额: ¥{{ finding.amount }}</span>
                            <span class="audit-tag" style="background: #f0fdf4; color: #16a34a;">次数: {{ finding.count }}</span>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="side-panel">
                <div class="glass-card">
                    <div class="section-title" style="margin-bottom: 15px; font-weight: 700;">🛡️ 风险五维建模</div>
                    <div id="radar-container"></div>
                </div>

                <div class="glass-card">
                    <div class="section-title" style="margin-bottom: 15px; font-weight: 700;">📅 审计时间轴</div>
                    <p style="font-size: 14px; color: #64748b;">
                        数据拉取: {{ timestamp }}<br>
                        AI 推演完成: {{ timestamp }}<br>
                        人工校验状态: <span style="color: var(--warning);">待审核</span>
                    </p>
                </div>
            </div>
        </div>

        <script>
            // 证据链图谱
            var graphChart = echarts.init(document.getElementById('graph-container'));
            var graphOption = {
                tooltip: {},
                animationDurationUpdate: 1500,
                animationEasingUpdate: 'quinticInOut',
                series: [{
                    type: 'graph',
                    layout: 'force',
                    symbolSize: 50,
                    roam: true,
                    label: { show: true, position: 'bottom', color: '#475569', fontSize: 11 },
                    force: { repulsion: 2000, edgeLength: [100, 150] },
                    data: {{ graph_data.nodes | tojson }},
                    links: {{ graph_data.edges | tojson }},
                    categories: {{ graph_data.categories | tojson }},
                    lineStyle: { opacity: 0.8, width: 2, curveness: 0.1, color: '#e2e8f0' }
                }]
            };
            graphChart.setOption(graphOption);

            // 风险雷达图 - 动态维度加载
            var radarChart = echarts.init(document.getElementById('radar-container'));
            var radarScores = {{ risk_scores | tojson }};
            var indicators = Object.keys(radarScores).map(k => ({ name: k, max: 100 }));
            var values = Object.values(radarScores);

            var radarOption = {
                radar: {
                    indicator: indicators,
                    shape: 'circle',
                    splitNumber: 4,
                    axisName: { color: '#64748b', fontSize: 10 },
                    splitLine: { lineStyle: { color: '#f1f5f9' } },
                    splitArea: { show: false }
                },
                series: [{
                    type: 'radar',
                    data: [{
                        value: values,
                        name: '风险概相',
                        areaStyle: { color: 'rgba(16, 185, 129, 0.2)' },
                        lineStyle: { color: '#10b981' },
                        itemStyle: { color: '#10b981' }
                    }]
                }]
            };
            radarChart.setOption(radarOption);

            window.addEventListener('resize', function() {
                graphChart.resize();
                radarChart.resize();
            });
        </script>
    </body>
    </html>
    """

    @classmethod
    def generate_html_report(cls, report_data: Dict[str, Any], output_path: str):
        # 1. 提取图谱数据
        findings_texts = [f["evidence"] for f in report_data.get("findings", [])]
        graph_data = extract_graph(findings_texts)
        
        # 2. 渲染 Jinja2 模板
        template = Template(cls.HTML_TEMPLATE)
        html_out = template.render(
            report_id=report_data.get("report_id", "HSA-AUTO"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_amount=f"{report_data.get('total_amount', 0):,.2f}",
            finding_count=report_data.get("finding_count", 0),
            confidence=report_data.get("confidence", 92),
            findings=report_data.get("findings", []),
            graph_data=graph_data,
            risk_scores=report_data.get("risk_scores", {})
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_out)
            
        return output_path
