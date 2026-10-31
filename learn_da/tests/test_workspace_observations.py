"""Reference solutions must survive the exact bounded Runner wire encoding."""
import importlib.util
from pathlib import Path

import pytest

from app.practice.observations import judge_observations
from app.workspace.content import refs_payload
from scripts.workspace_solutions import SOLUTIONS
from tests.test_workspace_content import SPECS, _replay, sandbox_root

_path = Path(__file__).resolve().parents[2] / "learn_da_runner/runner/learner_child.py"
_spec = importlib.util.spec_from_file_location("learner_wire", _path)
wire = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wire)


@pytest.mark.parametrize("slug", sorted(SPECS))
def test_reference_solutions_roundtrip_observation_contract(slug, sandbox_root):
    _, spec = SPECS[slug]
    for task in spec.tasks:
        namespace = _replay(spec, SOLUTIONS[slug], stop_at=task.cell_id)
        assertions = spec.assertions_for_cell(task.cell_id)
        variables, events = {}, []
        for item in assertions:
            if item["type"] == "call":
                value = namespace[item["function"]](*item.get("args", []), **item.get("kwargs", {}))
                events.append({"t":"call", "id":item["id"], "value":wire._serialize_var(value, 2_000_000)})
            elif item["type"] == "sql_rows":
                columns, rows = wire._fetch_sql_rows(item, namespace)
                events.append({"t":"rows", "id":item["id"], "columns":columns,
                               "rows":[[wire._jsonify_cell(c) for c in row] for row in rows]})
            else:
                variables[item["var"]] = wire._serialize_var(namespace[item["var"]], 2_000_000)
        events.append({"t":"vars", "vars":variables})
        prefix = True
        cells = []
        for cell in spec.cells:
            cells.append({"cellId":cell.cell_id, "status":"success" if prefix else "skipped"})
            if cell.cell_id == task.cell_id:
                prefix = False
        request = {"cells":[{"cellId":c.cell_id} for c in spec.cells], "stopAt":task.cell_id,
                   "assertions":assertions, "refs":refs_payload(spec.ref_names())}
        result = judge_observations(request, {"status":"success", "cells":cells,
                                  "executedUpto":task.cell_id, "observations":events})
        assert result["verdict"] == "passed", (slug, task.task_id, result["assertions"])
