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
