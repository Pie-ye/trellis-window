from server.checklist_parse import parse_checklist


def test_checked_and_unchecked():
    md = """
# Title
- [x] done one
- [ ] open two
- [X] done three
"""
    r = parse_checklist(md)
    assert r.maintained is True
    assert r.total == 3
    assert r.checked == 2
    assert abs(r.ratio - 2 / 3) < 1e-9
    assert r.unchecked_samples == ["open two"]


def test_empty_unmaintained():
    r = parse_checklist("# no boxes\n\nparagraph")
    assert r.maintained is False
    assert r.total == 0
    assert r.ratio is None


def test_ignores_code_fence():
    md = """
- [x] real
```
- [ ] fake in fence
```
- [ ] real open
"""
    r = parse_checklist(md)
    assert r.total == 2
    assert r.checked == 1
    assert r.unchecked_samples == ["real open"]
