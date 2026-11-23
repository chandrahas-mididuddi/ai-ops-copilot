from ai_ops_copilot.evaluator import load_golden, render_markdown, run_eval


def test_golden_set_loads():
    incidents = load_golden()
    assert len(incidents) == 8
    assert {i["id"] for i in incidents} == {f"inc-0{n}" for n in range(1, 9)}


def test_eval_passes_all_golden_incidents(tmp_path):
    summary = run_eval(audit_path=str(tmp_path / "audit.jsonl"))
    assert summary["total"] == 8
    assert summary["passed"] == 8, summary
    assert summary["pass_rate"] == 1.0
    assert summary["grounded"] == 8
    assert summary["remediation_match"] == 8
    assert summary["gating_correct"] == 8


def test_eval_report_renders(tmp_path):
    summary = run_eval(audit_path=str(tmp_path / "audit.jsonl"))
    md = render_markdown(summary)
    assert "Passed: 8 (100%)" in md
    assert "inc-01" in md
    assert "scale_checkout" in md
    assert "| inc-08 | escalate_oncall | escalate_oncall |" in md
