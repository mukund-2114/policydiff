import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import csv
import io

from app.routers.audit import csv_response, safe_cell


def test_a_cell_that_could_run_as_a_formula_becomes_text():
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("+cmd") == "'+cmd"
    assert safe_cell("-5") == "'-5"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("30 days") == "30 days"
    assert safe_cell(None) == ""
    assert safe_cell(0.9) == "0.9"


def test_csv_has_a_header_a_byte_order_mark_and_escaped_commas():
    r = csv_response("x.csv", ["a", "b"], [["one, two", '=HYPERLINK("x")']])
    body = r.body.decode("utf-8")
    assert body.startswith("﻿")
    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
    assert rows == [["a", "b"], ["one, two", '\'=HYPERLINK("x")']]
    assert "attachment" in r.headers["content-disposition"]
