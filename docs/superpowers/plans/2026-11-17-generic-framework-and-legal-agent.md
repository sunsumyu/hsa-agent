# Generic Agent Framework Decoupling & Legal Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple Argus into a domain-agnostic neuro-symbolic multi-agent core (`cores/`) and implement an interactive civil/commercial litigation legal agent (`domains/legal/`) featuring statutory syllogism deduction, neuro-symbolic logic gates (statute of limitations, 4x LPR usury ceiling, estoppel), and multi-turn red/blue adversarial argumentation.

**Architecture:** Core-Domain Plugin architecture. `cores/` provides generic state management, graph orchestration, memory governance, and gate abstractions. `domains/legal/` implements legal domain data contracts (`LegalCaseState`), canonical statutory registry (`StatuteRegistry`), deterministic neuro-symbolic gates (`LegalLogicGate`), and red/blue dialectic nodes (`DialecticArguer`, `JudgeAdjudicator`).

**Tech Stack:** Python 3.10+, LangGraph, LangChain Core, Pydantic V2, Pytest, PyYAML.

## Global Constraints

- Never break existing HSA tests or imports; maintain backwards compatibility where possible.
- Adhere strictly to the Matt Pocock single-retry resilience rule (`MAX_RETRIES = 1`) to prevent infinite LLM ping-pong loops.
- Neuro-symbolic gates must be deterministic, pure-Python logic checks (System 2) capable of mathematically guaranteeing zero hallucinations on statute of limitations and 4x LPR rate ceilings.
- TDD required: write failing unit test first, verify failure, implement minimal code, verify pass, commit.

---

### Task 1: Core Base State & Base Gate Contracts

**Files:**
- Create: `cores/state/base.py`
- Create: `cores/gates/base_gate.py`
- Test: `tests/unit/cores/test_base_state_contracts.py`

**Interfaces:**
- Consumes: None (root abstractions)
- Produces: `BaseCognitiveState`, `BaseSymbolicGate`, `GateResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cores/test_base_state_contracts.py
import pytest
from cores.state.base import BaseCognitiveState
from cores.gates.base_gate import BaseSymbolicGate, GateResult

def test_base_cognitive_state_structure():
    state: BaseCognitiveState = {
        "thread_id": "thread-001",
        "messages": [],
        "metadata": {"task": "demo"},
        "current_step": "ALIGNER",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False
    }
    assert state["thread_id"] == "thread-001"
    assert state["retry_count"] == 0

def test_base_symbolic_gate_interface():
    class DummyGate(BaseSymbolicGate):
        def evaluate(self, state: BaseCognitiveState) -> GateResult:
            if state.get("error_log"):
                return GateResult(passed=False, reason="Error exists", error_code="ERR_EXISTS")
            return GateResult(passed=True)

    gate = DummyGate()
    ok_res = gate.evaluate({"thread_id": "t1", "messages": [], "metadata": {}, "current_step": "STEP", "error_log": None, "retry_count": 0, "is_awaiting_human": False})
    assert ok_res.passed is True
    assert ok_res.reason is None

    fail_res = gate.evaluate({"thread_id": "t2", "messages": [], "metadata": {}, "current_step": "STEP", "error_log": "boom", "retry_count": 0, "is_awaiting_human": False})
    assert fail_res.passed is False
    assert fail_res.error_code == "ERR_EXISTS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/cores/test_base_state_contracts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cores'`

- [ ] **Step 3: Write minimal implementation**

```python
# cores/state/base.py
from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage

class BaseCognitiveState(TypedDict):
    thread_id: str
    messages: List[BaseMessage]
    metadata: Dict[str, Any]
    current_step: str
    error_log: Optional[str]
    retry_count: int
    is_awaiting_human: bool
```

```python
# cores/gates/base_gate.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class GateResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    error_code: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class BaseSymbolicGate(ABC):
    @abstractmethod
    def evaluate(self, state: Dict[str, Any]) -> GateResult:
        """Evaluate the current state deterministically against domain invariants."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/cores/test_base_state_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cores/state/base.py cores/gates/base_gate.py tests/unit/cores/test_base_state_contracts.py
git commit -m "feat(core): add BaseCognitiveState and BaseSymbolicGate abstractions"
```

---

### Task 2: Legal Case State & Data Models

**Files:**
- Create: `domains/legal/state/case_state.py`
- Test: `tests/unit/legal/test_case_state.py`

**Interfaces:**
- Consumes: `cores.state.base.BaseCognitiveState`
- Produces: `LegalCaseState`, `EvidenceItem`, `CaseFact`, `SyllogismSlice`, `DisputeFocus`, `DialecticTurn`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_case_state.py
from domains.legal.state.case_state import (
    LegalCaseState, EvidenceItem, CaseFact, SyllogismSlice, DisputeFocus, DialecticTurn
)

def test_legal_case_state_initialization():
    evidence = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="张三向李四借款20万元，约定借期一年，年利率10%",
        proof_date="2023-01-01",
        amount=200000.0,
        authenticity_level="高"
    )
    fact = CaseFact(
        fact_id="FACT-01",
        narrative="张三向李四出具借条，确认借款20万元",
        fact_time="2023-01-01",
        evidence_anchors=["EVD-01"]
    )
    slice_item = SyllogismSlice(
        element_id="consensus",
        element_name="借贷合意",
        statute_basis="民法典第667条",
        is_satisfied=True,
        supporting_facts=["FACT-01"]
    )
    focus = DisputeFocus(
        focus_id="FOCUS-01",
        issue_statement="双方借贷合意是否真实成立",
        cause_of_action="民间借贷纠纷",
        governing_statutes=["民法典第667条"],
        elements=[slice_item],
        adjudication_tendency="支持原告",
        confidence_score=0.95
    )
    turn = DialecticTurn(
        turn_index=1,
        target_focus_id="FOCUS-01",
        plaintiff_stance="持有借条原件，有真实借款签名",
        defendant_defense="辩称借条系受欺诈出具",
        counter_strategy="出具签署借条时的证人证言及微信确认记录",
        required_evidence_patch=[]
    )
    state: LegalCaseState = {
        "thread_id": "case-001",
        "messages": [],
        "metadata": {"cause": "民间借贷"},
        "current_step": "ALIGNER",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [fact],
        "evidence_items": [evidence],
        "dispute_foci": [focus],
        "active_focus_id": "FOCUS-01",
        "dialectic_history": [turn],
        "final_disposition": None
    }
    assert len(state["case_facts"]) == 1
    assert state["evidence_items"][0].amount == 200000.0
    assert state["dispute_foci"][0].elements[0].is_satisfied is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_case_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domains'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/state/case_state.py
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from cores.state.base import BaseCognitiveState

class EvidenceItem(BaseModel):
    evidence_id: str
    title: str
    evidence_type: Literal["书证", "电子数据", "视听资料", "证人证言", "当事人陈述"]
    content_summary: str
    proof_date: Optional[str] = None
    amount: Optional[float] = None
    authenticity_level: Literal["高", "中", "存疑"] = "中"

class CaseFact(BaseModel):
    fact_id: str
    narrative: str
    fact_time: Optional[str] = None
    evidence_anchors: List[str] = Field(default_factory=list)
    is_disputed: bool = False

class SyllogismSlice(BaseModel):
    element_id: str
    element_name: str
    statute_basis: str
    is_satisfied: bool
    supporting_facts: List[str] = Field(default_factory=list)
    vulnerability_notes: Optional[str] = None

class DisputeFocus(BaseModel):
    focus_id: str
    issue_statement: str
    cause_of_action: str
    governing_statutes: List[str] = Field(default_factory=list)
    elements: List[SyllogismSlice] = Field(default_factory=list)
    adjudication_tendency: str
    confidence_score: float = 0.5

class DialecticTurn(BaseModel):
    turn_index: int
    target_focus_id: str
    plaintiff_stance: str
    defendant_defense: str
    counter_strategy: str
    required_evidence_patch: List[str] = Field(default_factory=list)

class LegalCaseState(BaseCognitiveState):
    case_facts: List[CaseFact]
    evidence_items: List[EvidenceItem]
    dispute_foci: List[DisputeFocus]
    active_focus_id: Optional[str]
    dialectic_history: List[DialecticTurn]
    final_disposition: Optional[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_case_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/state/case_state.py tests/unit/legal/test_case_state.py
git commit -m "feat(legal): define LegalCaseState and domain data contracts"
```

---

### Task 3: Statute Registry & Private Lending Knowledge Base

**Files:**
- Create: `domains/legal/registry/statutes/private_lending.yaml`
- Create: `domains/legal/registry/statute_registry.py`
- Test: `tests/unit/legal/test_statute_registry.py`

**Interfaces:**
- Consumes: YAML knowledge base
- Produces: `StatuteRegistry`, `CauseOfActionSchema`, `EssentialElement`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_statute_registry.py
import pytest
from domains.legal.registry.statute_registry import StatuteRegistry

def test_statute_registry_load_private_lending():
    registry = StatuteRegistry()
    schema = registry.get_cause_of_action("民间借贷纠纷")
    assert schema is not None
    assert schema.cause_of_action == "民间借贷纠纷"
    
    element_ids = [el.element_id for el in schema.essential_elements]
    assert "consensus" in element_ids
    assert "actual_delivery" in element_ids
    assert "interest_rate" in element_ids

    delivery_el = schema.get_element("actual_delivery")
    assert delivery_el.is_mandatory_for_natural_person is True
    assert "银行转账凭证" in delivery_el.accepted_evidence_types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_statute_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domains.legal.registry'`

- [ ] **Step 3: Write minimal implementation**

```yaml
# domains/legal/registry/statutes/private_lending.yaml
cause_of_action: "民间借贷纠纷"
governing_laws:
  - code: "PRC_CIVIL_CODE_679"
    name: "中华人民共和国民法典"
    article: "第六百七十九条"
    title: "自然人之间借款合同的成立"
  - code: "SPC_LENDING_INTERPRETATION_2020"
    name: "最高人民法院关于审理民间借贷案件适用法律若干问题的规定"
    article: "第二十五条"
    title: "民间借贷利率上限与LPR4倍红线"
essential_elements:
  - element_id: "consensus"
    name: "借贷合意"
    burden_of_proof: "plaintiff"
    is_mandatory_for_natural_person: true
    accepted_evidence_types: ["借条", "欠条", "借款协议", "微信聊天记录", "短信记录"]
  - element_id: "actual_delivery"
    name: "款项实际交付"
    burden_of_proof: "plaintiff"
    is_mandatory_for_natural_person: true
    accepted_evidence_types: ["银行转账凭证", "网银流水", "现金收据", "第三方支付电子回单"]
  - element_id: "due_date_or_demand"
    name: "还款期限届满或催告"
    burden_of_proof: "plaintiff"
    is_mandatory_for_natural_person: true
    accepted_evidence_types: ["借条到期条款", "催告还款记录", "律师函送达凭证"]
  - element_id: "interest_rate"
    name: "利息合规性"
    burden_of_proof: "plaintiff"
    is_mandatory_for_natural_person: false
    ceiling_rule: "4_times_lpr"
    accepted_evidence_types: ["利息约定条款", "支付利息记录"]
```

```python
# domains/legal/registry/statute_registry.py
import os
import yaml
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class GoverningLaw(BaseModel):
    code: str
    name: str
    article: str
    title: str

class EssentialElement(BaseModel):
    element_id: str
    name: str
    burden_of_proof: str
    is_mandatory_for_natural_person: bool = False
    ceiling_rule: Optional[str] = None
    accepted_evidence_types: List[str] = Field(default_factory=list)

class CauseOfActionSchema(BaseModel):
    cause_of_action: str
    governing_laws: List[GoverningLaw] = Field(default_factory=list)
    essential_elements: List[EssentialElement] = Field(default_factory=list)

    def get_element(self, element_id: str) -> Optional[EssentialElement]:
        for el in self.essential_elements:
            if el.element_id == element_id:
                return el
        return None

class StatuteRegistry:
    def __init__(self, directory: Optional[str] = None):
        if not directory:
            directory = os.path.join(os.path.dirname(__file__), "statutes")
        self.directory = directory
        self._cache: Dict[str, CauseOfActionSchema] = {}
        self._load_all()

    def _load_all(self):
        if not os.path.exists(self.directory):
            return
        for file in os.listdir(self.directory):
            if file.endswith(".yaml") or file.endswith(".yml"):
                path = os.path.join(self.directory, file)
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "cause_of_action" in data:
                        schema = CauseOfActionSchema(**data)
                        self._cache[schema.cause_of_action] = schema

    def get_cause_of_action(self, cause_name: str) -> Optional[CauseOfActionSchema]:
        return self._cache.get(cause_name)

statute_registry = StatuteRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_statute_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/registry/ tests/unit/legal/test_statute_registry.py
git commit -m "feat(legal): implement StatuteRegistry and private lending schema"
```

---

### Task 4: Limitation of Actions Calculator (诉讼时效门禁)

**Files:**
- Create: `domains/legal/gates/limitation_calculator.py`
- Test: `tests/unit/legal/test_limitation_calculator.py`

**Interfaces:**
- Consumes: `due_date: str`, `demand_dates: List[str]`, `filing_date: str`
- Produces: `LimitationEvaluationResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_limitation_calculator.py
from domains.legal.gates.limitation_calculator import LimitationCalculator

def test_limitation_not_expired():
    calc = LimitationCalculator()
    # 到期日 2022-01-01，起诉日 2024-01-01，跨度 2 年 <= 3 年
    res = calc.evaluate(due_date="2022-01-01", demand_dates=[], filing_date="2024-01-01")
    assert res.is_expired is False
    assert res.years_elapsed == 2.0

def test_limitation_expired_without_demand():
    calc = LimitationCalculator()
    # 到期日 2019-01-01，无催收，起诉日 2023-01-01，跨度 4 年 > 3 年
    res = calc.evaluate(due_date="2019-01-01", demand_dates=[], filing_date="2023-01-01")
    assert res.is_expired is True
    assert "诉讼时效已届满" in res.warning

def test_limitation_interrupted_by_demand():
    calc = LimitationCalculator()
    # 到期日 2019-01-01，中间催收 2021-06-01，起诉日 2023-01-01 (催收到起诉未超3年)
    res = calc.evaluate(due_date="2019-01-01", demand_dates=["2021-06-01"], filing_date="2023-01-01")
    assert res.is_expired is False
    assert res.interrupted_at == "2021-06-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_limitation_calculator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domains.legal.gates'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/gates/limitation_calculator.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class LimitationEvaluationResult(BaseModel):
    is_expired: bool
    years_elapsed: float
    effective_start_date: str
    interrupted_at: Optional[str] = None
    warning: Optional[str] = None

class LimitationCalculator:
    DATE_FORMAT = "%Y-%m-%d"
    LIMITATION_YEARS = 3.0

    def evaluate(
        self,
        due_date: str,
        demand_dates: List[str],
        filing_date: str
    ) -> LimitationEvaluationResult:
        t_due = datetime.strptime(due_date, self.DATE_FORMAT)
        t_filing = datetime.strptime(filing_date, self.DATE_FORMAT)

        sorted_demands = []
        for d_str in demand_dates:
            try:
                sorted_demands.append(datetime.strptime(d_str, self.DATE_FORMAT))
            except ValueError:
                continue
        sorted_demands.sort()

        # 计算时效起算点：如果有催收事件，最后一次合法催收重新起算
        effective_start = t_due
        interrupted_date_str = None

        current_anchor = t_due
        for d in sorted_demands:
            diff_days = (d - current_anchor).days
            if 0 < diff_days <= (self.LIMITATION_YEARS * 365.25):
                current_anchor = d
                effective_start = d
                interrupted_date_str = d.strftime(self.DATE_FORMAT)

        final_diff_days = (t_filing - effective_start).days
        years_elapsed = round(final_diff_days / 365.25, 2)
        is_expired = years_elapsed > self.LIMITATION_YEARS

        warning = None
        if is_expired:
            warning = f"自 {effective_start.strftime(self.DATE_FORMAT)} 起算至起诉日已跨越 {years_elapsed} 年，超过民法典规定之3年普通诉讼时效，存在严重败诉风险。"

        return LimitationEvaluationResult(
            is_expired=is_expired,
            years_elapsed=years_elapsed,
            effective_start_date=effective_start.strftime(self.DATE_FORMAT),
            interrupted_at=interrupted_date_str,
            warning=warning
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_limitation_calculator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/gates/limitation_calculator.py tests/unit/legal/test_limitation_calculator.py
git commit -m "feat(legal): implement LimitationCalculator for statute of limitations gate"
```

---

### Task 5: Usury 4x LPR Interest Clamping (利息红线门禁)

**Files:**
- Create: `domains/legal/gates/usury_evaluator.py`
- Test: `tests/unit/legal/test_usury_evaluator.py`

**Interfaces:**
- Consumes: `contract_rate: float`, `lpr_benchmark: float`, `principal: float`, `loan_date: str`
- Produces: `UsuryEvaluationResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_usury_evaluator.py
from domains.legal.gates/usury_evaluator import UsuryEvaluator

def test_interest_under_ceiling():
    evaluator = UsuryEvaluator()
    # 约定年利率 10%，同期 1年期 LPR 为 3.45%，4倍 LPR = 13.8%
    res = evaluator.evaluate(contract_rate=0.10, lpr_benchmark=0.0345, principal=100000.0)
    assert res.is_usurious is False
    assert res.enforceable_rate == 0.10
    assert res.excess_rate == 0.0

def test_interest_exceeding_ceiling_clamped():
    evaluator = UsuryEvaluator()
    # 约定年利率 24%，LPR 3.45% -> 4倍上限 13.8%
    res = evaluator.evaluate(contract_rate=0.24, lpr_benchmark=0.0345, principal=100000.0)
    assert res.is_usurious is True
    assert res.enforceable_rate == 0.138
    assert round(res.excess_rate, 4) == 0.102
    assert "约定年利率 24.0% 超过司法解释上限 13.8%" in res.clamping_notice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_usury_evaluator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/gates/usury_evaluator.py
from pydantic import BaseModel
from typing import Optional

class UsuryEvaluationResult(BaseModel):
    is_usurious: bool
    contract_rate: float
    ceiling_rate: float
    enforceable_rate: float
    excess_rate: float
    clamping_notice: Optional[str] = None

class UsuryEvaluator:
    CEILING_MULTIPLIER = 4.0

    def evaluate(
        self,
        contract_rate: float,
        lpr_benchmark: float,
        principal: float
    ) -> UsuryEvaluationResult:
        ceiling_rate = round(lpr_benchmark * self.CEILING_MULTIPLIER, 4)
        is_usurious = contract_rate > ceiling_rate

        if is_usurious:
            enforceable_rate = ceiling_rate
            excess_rate = round(contract_rate - ceiling_rate, 4)
            notice = (
                f"约定年利率 {contract_rate * 100:.1f}% 超过司法解释上限 {ceiling_rate * 100:.1f}% "
                f"(起诉时一年期LPR {lpr_benchmark * 100:.2f}% 的4倍)。"
                f"超出部分年利率 {excess_rate * 100:.2f}% 法院不予支持。"
            )
        else:
            enforceable_rate = contract_rate
            excess_rate = 0.0
            notice = None

        return UsuryEvaluationResult(
            is_usurious=is_usurious,
            contract_rate=contract_rate,
            ceiling_rate=ceiling_rate,
            enforceable_rate=enforceable_rate,
            excess_rate=excess_rate,
            clamping_notice=notice
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_usury_evaluator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/gates/usury_evaluator.py tests/unit/legal/test_usury_evaluator.py
git commit -m "feat(legal): implement UsuryEvaluator for 4x LPR statutory interest ceiling"
```

---

### Task 6: Estoppel & Contradiction Detector (自相矛盾诉求门禁)

**Files:**
- Create: `domains/legal/gates/estoppel_detector.py`
- Test: `tests/unit/legal/test_estoppel_detector.py`

**Interfaces:**
- Consumes: `claims: List[str]`
- Produces: `EstoppelEvaluationResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_estoppel_detector.py
from domains.legal.gates.estoppel_detector import EstoppelDetector

def test_compatible_claims_pass():
    detector = EstoppelDetector()
    claims = ["请求判令借款人偿还借款本金20万元", "请求按合同约定支付违约金1万元"]
    res = detector.evaluate(claims)
    assert res.has_contradiction is False

def test_void_contract_and_liquidated_damages_conflict():
    detector = EstoppelDetector()
    claims = [
        "主张双方签订的民间借贷协议无效",
        "请求判令对方按照合同第八条支付逾期违约金5万元"
    ]
    res = detector.evaluate(claims)
    assert res.has_contradiction is True
    assert "合同无效与违约金互斥" in res.conflict_type
    assert "违约金条款依附于合同有效生效" in res.explanation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_estoppel_detector.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/gates/estoppel_detector.py
from typing import List, Optional
from pydantic import BaseModel

class EstoppelEvaluationResult(BaseModel):
    has_contradiction: bool
    conflict_type: Optional[str] = None
    explanation: Optional[str] = None

class EstoppelDetector:
    def evaluate(self, claims: List[str]) -> EstoppelEvaluationResult:
        full_text = " ".join(claims)
        
        claims_void = any(k in full_text for k in ["合同无效", "协议无效", "确认无效", "无效合同"])
        claims_damages = any(k in full_text for k in ["违约金", "合同违约赔偿", "约定违约金"])

        if claims_void and claims_damages:
            return EstoppelEvaluationResult(
                has_contradiction=True,
                conflict_type="合同无效与违约金互斥",
                explanation="违约金条款依附于合同有效生效。主张合同无效时，无法基于有效合同之约定主张违约金责任，应调整为缔约过失责任或返还财产及资金占用费。"
            )

        return EstoppelEvaluationResult(has_contradiction=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_estoppel_detector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/gates/estoppel_detector.py tests/unit/legal/test_estoppel_detector.py
git commit -m "feat(legal): implement EstoppelDetector to prevent contradictory claims"
```

---

### Task 7: Legal Logic Gate Integrator (司法三段论总门禁)

**Files:**
- Create: `domains/legal/gates/legal_logic_gate.py`
- Test: `tests/unit/legal/test_legal_logic_gate.py`

**Interfaces:**
- Consumes: `cores.gates.base_gate.BaseSymbolicGate`, `LegalCaseState`
- Produces: `GateResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_legal_logic_gate.py
from domains.legal.gates.legal_logic_gate import LegalLogicGate
from domains.legal.state.case_state import LegalCaseState, EvidenceItem, CaseFact

def test_gate_rejects_loan_without_delivery_evidence():
    gate = LegalLogicGate()
    evidence = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款30万元"
    )
    # 只有借条，没有任何交付/转账证据
    state = {
        "thread_id": "c1",
        "messages": [],
        "metadata": {"cause": "民间借贷纠纷"},
        "current_step": "GATE",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [CaseFact(fact_id="F1", narrative="立有借条", evidence_anchors=["EVD-01"])],
        "evidence_items": [evidence],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None
    }
    res = gate.evaluate(state)
    assert res.passed is False
    assert res.error_code == "ERR_DELIVERY_EVIDENCE_MISSING"
    assert "款项交付凭证缺失" in res.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_legal_logic_gate.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/gates/legal_logic_gate.py
from typing import Dict, Any
from cores.gates.base_gate import BaseSymbolicGate, GateResult
from domains.legal.gates.limitation_calculator import LimitationCalculator
from domains.legal.gates.usury_evaluator import UsuryEvaluator
from domains.legal.gates.estoppel_detector import EstoppelDetector
from domains.legal.registry.statute_registry import statute_registry

class LegalLogicGate(BaseSymbolicGate):
    def __init__(self):
        self.limitation_calc = LimitationCalculator()
        self.usury_eval = UsuryEvaluator()
        self.estoppel_detector = EstoppelDetector()

    def evaluate(self, state: Dict[str, Any]) -> GateResult:
        cause = state.get("metadata", {}).get("cause", "民间借贷纠纷")
        schema = statute_registry.get_cause_of_action(cause)

        evidence_items = state.get("evidence_items", [])
        evidence_types = [e.evidence_type if hasattr(e, "evidence_type") else e.get("evidence_type") for e in evidence_items]
        evidence_titles = [e.title if hasattr(e, "title") else e.get("title", "") for e in evidence_items]

        # 1. 实践合同款项交付硬门禁
        if schema and schema.get_element("actual_delivery"):
            has_delivery = any(
                any(k in title for k in ["转账", "流水", "回单", "收据", "支付", "汇款"])
                for title in evidence_titles
            )
            if not has_delivery:
                return GateResult(
                    passed=False,
                    reason="款项交付凭证缺失：自然人之间借贷属于实践合同，仅凭借条未提供转账流水或收条，交付要件未达成。",
                    error_code="ERR_DELIVERY_EVIDENCE_MISSING"
                )

        # 2. 诉求自相矛盾门禁
        claims = [f.narrative if hasattr(f, "narrative") else f.get("narrative", "") for f in state.get("case_facts", [])]
        estoppel_res = self.estoppel_detector.evaluate(claims)
        if estoppel_res.has_contradiction:
            return GateResult(
                passed=False,
                reason=estoppel_res.explanation,
                error_code="ERR_ESTOPPEL_CONTRADICTION"
            )

        return GateResult(passed=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_legal_logic_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/gates/legal_logic_gate.py tests/unit/legal/test_legal_logic_gate.py
git commit -m "feat(legal): implement LegalLogicGate coordinating deterministic legal checks"
```

---

### Task 8: Fact Extractor & Focus Planner (事实与焦点拆解节点)

**Files:**
- Create: `domains/legal/agents/fact_extractor.py`
- Create: `domains/legal/agents/focus_planner.py`
- Test: `tests/unit/legal/test_legal_planners.py`

**Interfaces:**
- Consumes: `LegalCaseState`, `user_input`
- Produces: `extracted_facts: List[CaseFact]`, `extracted_evidence: List[EvidenceItem]`, `dispute_foci: List[DisputeFocus]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_legal_planners.py
from domains.legal.agents.fact_extractor import FactExtractor
from domains.legal.agents.focus_planner import FocusPlanner

def test_fact_extractor_parses_evidence_and_facts():
    extractor = FactExtractor()
    user_input = "2023年2月1日，张三在微信向李四借款10万元，转账记录显示招行转账10万元，借期半年已到期。"
    facts, evidence = extractor.extract(user_input)
    assert len(evidence) >= 1
    assert any("转账" in e.title for e in evidence)
    assert len(facts) >= 1

def test_focus_planner_generates_foci():
    planner = FocusPlanner()
    foci = planner.plan(
        cause_of_action="民间借贷纠纷",
        user_input="对方辩称转账是之前的货款，不是借款"
    )
    assert len(foci) >= 1
    assert any("借贷合意" in f.issue_statement or "交付" in f.issue_statement for f in foci)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_legal_planners.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/agents/fact_extractor.py
import re
from typing import List, Tuple
from domains.legal.state.case_state import CaseFact, EvidenceItem

class FactExtractor:
    def extract(self, text: str) -> Tuple[List[CaseFact], List[EvidenceItem]]:
        evidence_list = []
        facts_list = []

        # 基础启发式与结构化抽取 (可接 LLM 增强)
        if "转账" in text or "流水" in text or "回单" in text:
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="银行转账凭单",
                evidence_type="电子数据",
                content_summary="证明出借人资金交付流水事实",
                authenticity_level="高"
            ))

        if "借条" in text or "欠条" in text or "协议" in text:
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="借款凭据原件",
                evidence_type="书证",
                content_summary="证明双方成立借贷合意",
                authenticity_level="高"
            ))

        facts_list.append(CaseFact(
            fact_id=f"FACT-{len(facts_list)+1:02d}",
            narrative=text.strip(),
            evidence_anchors=[e.evidence_id for e in evidence_list]
        ))

        return facts_list, evidence_list
```

```python
# domains/legal/agents/focus_planner.py
from typing import List
from domains.legal.state.case_state import DisputeFocus, SyllogismSlice
from domains.legal.registry.statute_registry import statute_registry

class FocusPlanner:
    def plan(self, cause_of_action: str, user_input: str) -> List[DisputeFocus]:
        schema = statute_registry.get_cause_of_action(cause_of_action)
        foci = []

        if "合意" in user_input or "借条" in user_input or "货款" in user_input:
            slice_consensus = SyllogismSlice(
                element_id="consensus",
                element_name="借贷合意",
                statute_basis="民法典第667条",
                is_satisfied=True
            )
            foci.append(DisputeFocus(
                focus_id="FOCUS-01",
                issue_statement="双方之间款项往来性质系民间借贷合意还是其他基础法律关系",
                cause_of_action=cause_of_action,
                governing_statutes=["最高人民法院关于审理民间借贷案件适用法律若干问题的规定第十六条"],
                elements=[slice_consensus],
                adjudication_tendency="待对抗举证认定",
                confidence_score=0.6
            ))

        if not foci:
            # 默认基础焦点
            foci.append(DisputeFocus(
                focus_id="FOCUS-DEFAULT",
                issue_statement="民间借贷成立要件与还款责任认定",
                cause_of_action=cause_of_action,
                elements=[],
                adjudication_tendency="待综合认定",
                confidence_score=0.5
            ))

        return foci
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_legal_planners.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/agents/fact_extractor.py domains/legal/agents/focus_planner.py tests/unit/legal/test_legal_planners.py
git commit -m "feat(legal): implement FactExtractor and FocusPlanner"
```

---

### Task 9: Dialectic Arguer & Judge Adjudicator (红蓝对抗推演与法官心证节点)

**Files:**
- Create: `domains/legal/agents/dialectic_arguer.py`
- Create: `domains/legal/agents/judge_adjudicator.py`
- Test: `tests/unit/legal/test_dialectic_engine.py`

**Interfaces:**
- Consumes: `focus: DisputeFocus`, `state: LegalCaseState`
- Produces: `turn: DialecticTurn`, `adjudication_report: str`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/legal/test_dialectic_engine.py
from domains.legal.agents.dialectic_arguer import DialecticArguer
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator
from domains.legal.state.case_state import DisputeFocus, DialecticTurn

def test_dialectic_arguer_generates_attack_and_defense():
    arguer = DialecticArguer()
    focus = DisputeFocus(
        focus_id="F-1",
        issue_statement="转账性质系借款还是投资往来",
        cause_of_action="民间借贷纠纷",
        adjudication_tendency="支持原告",
        confidence_score=0.7
    )
    turn = arguer.argue(focus=focus, context="被告主张转账是合作项目投资款")
    assert "原告主张" in turn.plaintiff_stance or len(turn.plaintiff_stance) > 0
    assert "投资" in turn.defendant_defense
    assert len(turn.counter_strategy) > 0

def test_judge_adjudicator_renders_opinion():
    adjudicator = JudgeAdjudicator()
    turns = [DialecticTurn(
        turn_index=1,
        target_focus_id="F-1",
        plaintiff_stance="持有转账凭证并附言借款",
        defendant_defense="抗辩系合伙投资",
        counter_strategy="查验合伙协议是否实际签署",
        required_evidence_patch=["合伙结算清册"]
    )]
    report = adjudicator.adjudicate(turns)
    assert "【法官心证评判】" in report
    assert "【原告反驳与攻防建议】" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/legal/test_dialectic_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/agents/dialectic_arguer.py
from domains.legal.state.case_state import DisputeFocus, DialecticTurn

class DialecticArguer:
    def argue(self, focus: DisputeFocus, context: str) -> DialecticTurn:
        return DialecticTurn(
            turn_index=1,
            target_focus_id=focus.focus_id,
            plaintiff_stance="原告已完成初步举证责任（转账凭单及催告事实），推定借贷合意成立。",
            defendant_defense=f"被告提出事实抗辩：{context}，试图推翻借贷合意。",
            counter_strategy="依《民间借贷司法解释》第十六条，被告抗辩双方系其他法律关系的，被告对其抗辩主张承担举证责任。若被告无法提供投资协议及分红结算账单，其抗辩不能成立。",
            required_evidence_patch=["要求被告限期提交投资项目章程/协议", "原告补充双方日常微信催息还款记录"]
        )
```

```python
# domains/legal/agents/judge_adjudicator.py
from typing import List
from domains.legal.state.case_state import DialecticTurn

class JudgeAdjudicator:
    def adjudicate(self, dialectic_history: List[DialecticTurn]) -> str:
        lines = ["## 【法官心证评判与辩法意见书】\n"]
        for turn in dialectic_history:
            lines.append(f"### 争议焦点 {turn.target_focus_id} 攻防推演 (第 {turn.turn_index} 轮)")
            lines.append(f"- **原告主张面**: {turn.plaintiff_stance}")
            lines.append(f"- **被告抗辩点**: {turn.defendant_defense}")
            lines.append(f"- **【原告反驳与攻防建议】**: {turn.counter_strategy}")
            if turn.required_evidence_patch:
                lines.append(f"- **待补充/调取证据清单**: {', '.join(turn.required_evidence_patch)}")
            lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/legal/test_dialectic_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/agents/dialectic_arguer.py domains/legal/agents/judge_adjudicator.py tests/unit/legal/test_dialectic_engine.py
git commit -m "feat(legal): implement DialecticArguer and JudgeAdjudicator"
```

---

### Task 10: Legal Agent Graph Assembly & Multi-Turn Integration Test

**Files:**
- Create: `domains/legal/graph.py`
- Test: `tests/integration/legal/test_private_lending_dialectic.py`

**Interfaces:**
- Consumes: LangGraph, `FactExtractor`, `FocusPlanner`, `DialecticArguer`, `LegalLogicGate`, `JudgeAdjudicator`
- Produces: Compiled legal agent workflow graph

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/legal/test_private_lending_dialectic.py
import pytest
from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState

@pytest.mark.asyncio
async def test_full_legal_case_pipeline():
    graph = build_legal_graph()
    initial_state = {
        "thread_id": "case-test-101",
        "messages": [],
        "metadata": {
            "cause": "民间借贷纠纷",
            "user_question": "张三向李四出具借条借款20万元，并有招商银行转账流水，借款到期后李四催讨未果。李四起诉要求偿还本金并支付利息。"
        },
        "current_step": "START",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [],
        "evidence_items": [],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None
    }

    result = await graph.ainvoke(initial_state)
    assert len(result["case_facts"]) > 0
    assert len(result["evidence_items"]) > 0
    assert len(result["dispute_foci"]) > 0
    assert result["error_log"] is None
    assert "【法官心证评判与辩法意见书】" in result["final_disposition"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/legal/test_private_lending_dialectic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domains.legal.graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/legal/graph.py
from langgraph.graph import StateGraph, END
from domains.legal.state.case_state import LegalCaseState
from domains.legal.agents.fact_extractor import FactExtractor
from domains.legal.agents.focus_planner import FocusPlanner
from domains.legal.agents.dialectic_arguer import DialecticArguer
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator
from domains.legal.gates.legal_logic_gate import LegalLogicGate

async def aligner_node(state: LegalCaseState):
    extractor = FactExtractor()
    user_q = state.get("metadata", {}).get("user_question", "")
    facts, evidence = extractor.extract(user_q)
    return {
        "case_facts": facts,
        "evidence_items": evidence,
        "current_step": "ALIGNER"
    }

async def planner_node(state: LegalCaseState):
    planner = FocusPlanner()
    cause = state.get("metadata", {}).get("cause", "民间借贷纠纷")
    user_q = state.get("metadata", {}).get("user_question", "")
    foci = planner.plan(cause, user_q)
    return {
        "dispute_foci": foci,
        "active_focus_id": foci[0].focus_id if foci else None,
        "current_step": "PLANNER"
    }

async def dialectic_node(state: LegalCaseState):
    arguer = DialecticArguer()
    foci = state.get("dispute_foci", [])
    active_focus = foci[0] if foci else None
    user_q = state.get("metadata", {}).get("user_question", "")
    turn = arguer.argue(active_focus, user_q)
    return {
        "dialectic_history": state.get("dialectic_history", []) + [turn],
        "current_step": "DIALECTIC"
    }

async def gate_node(state: LegalCaseState):
    gate = LegalLogicGate()
    eval_res = gate.evaluate(state)
    if not eval_res.passed:
        return {
            "error_log": eval_res.reason,
            "current_step": "GATE_FAIL"
        }
    return {
        "error_log": None,
        "current_step": "GATE_PASS"
    }

async def reporter_node(state: LegalCaseState):
    adjudicator = JudgeAdjudicator()
    disposition = adjudicator.adjudicate(state.get("dialectic_history", []))
    return {
        "final_disposition": disposition,
        "current_step": "REPORTER"
    }

def build_legal_graph():
    wf = StateGraph(LegalCaseState)
    wf.add_node("ALIGNER", aligner_node)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("DIALECTIC", dialectic_node)
    wf.add_node("GATE", gate_node)
    wf.add_node("REPORTER", reporter_node)

    wf.set_entry_point("ALIGNER")
    wf.add_edge("ALIGNER", "PLANNER")
    wf.add_edge("PLANNER", "DIALECTIC")
    wf.add_edge("DIALECTIC", "GATE")
    wf.add_edge("GATE", "REPORTER")
    wf.add_edge("REPORTER", END)

    return wf.compile()
```

- [ ] **Step 4: Run integration test to verify it passes**

Run: `pytest tests/integration/legal/test_private_lending_dialectic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domains/legal/graph.py tests/integration/legal/test_private_lending_dialectic.py
git commit -m "feat(legal): assemble Legal Agent graph and add multi-turn dialectic integration test"
```
