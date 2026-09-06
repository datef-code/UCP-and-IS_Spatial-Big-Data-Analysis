import tempfile
from pathlib import Path

import datakit as dk


def test_workflow_end_to_end(tmp_path):
    src = tmp_path / "data_raw"
    (src / "fdic").mkdir(parents=True)
    for year in (1994, 1995, 1996):
        (src / "fdic" / f"fdic_sod_{year}.csv").write_text(
            "BRNUM,CERT,DEPSUMBR\n1,10,1000\n2,20,2000\n", encoding="utf-8"
        )

    out = tmp_path / "output"
    plan = dk.CleanPlan().drop_na(["BRNUM"]).fill("DEPSUMBR", method="median")
    scheme = dk.MappingScheme().derive("DEPSUMBR_K", "DEPSUMBR / 1000")

    results = dk.Workflow(out).run(
        src,
        group="fdic_sod_#",
        roles={"BRNUM": dk.Role.KEY, "CERT": dk.Role.KEY},
        clean_plan=plan,
        mapping_scheme=scheme,
        assertions=[{"name": "DEPSUMBR 非负", "check": "no_negative", "field": "DEPSUMBR"}],
    )

    # 各阶段报告均落盘
    assert (out / "01_discover" / "catalog.json").exists()
    assert (out / "02_profile" / "profile.json").exists()
    assert (out / "03_clean" / "decisions.md").exists()
    assert (out / "04_validate" / "comparison.json").exists()
    assert (out / "05_map" / "map.json").exists()
    assert (out / "pipeline.log").exists()

    assert results["profile1"]["rows"] == 6  # 3 文件 × 2 行
    assert results["validation"]["passed"] is True
