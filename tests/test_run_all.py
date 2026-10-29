from eval.run_all import run_all


def test_run_all_writes_report(tmp_path):
    out = tmp_path / "report.md"
    results, ablations, robust = run_all(out=str(out), log=False)
    text = out.read_text(encoding="utf-8")
    assert "## Results" in text
    assert "## Ablations" in text
    assert "## Robustness" in text
    assert results["logreg"]["mean_macro_f1"] > results["majority"]["mean_macro_f1"]
    assert ablations["full (C=1)"]["delta"] == 0
