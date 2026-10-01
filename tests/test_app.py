import queries


def test_all_tables_loaded(fake_redis):
    for meta in queries.TABLES.values():
        assert fake_redis.scard(f"all:{meta['prefix']}") == 1000, meta["prefix"]


def test_pages_render(client):
    for path in ("/", "/browse", "/tasks", "/ask"):
        assert client.get(path).status_code == 200, path


def test_dashboard_redirect(client):
    assert client.get("/dashboard").status_code == 301


def test_healthz(client):
    assert client.get("/healthz").get_json()["status"] == "ok"


def test_dashboard_api(client):
    j = client.get("/api/dashboard").get_json()
    assert j["stats"]["tables"] == 13
    assert j["stats"]["total_rows"] == 13000
    assert j["properties_per_city"] and j["companies_per_sector"]


def test_browse_every_table(client):
    for name in queries.TABLES:
        j = client.get(f"/api/browse/{name}?page_size=5").get_json()
        assert j["total"] == 1000 and len(j["rows"]) == 5, name


def test_browse_clamps_input(client):
    j = client.get("/api/browse/students?page_size=99999&page=-4&sort_dir=bogus").get_json()
    assert j["page_size"] == 250 and j["page"] == 1 and j["sort_dir"] == "asc"
    assert client.get("/api/browse/nope").status_code == 404
    # junk numbers must not 500
    assert client.get("/api/browse/students?page=abc").status_code == 200


def test_browse_search(client):
    j = client.get("/api/browse/students?search=zzzz-no-match").get_json()
    assert j["total"] == 0


def test_task_top_n(client):
    rows = client.get("/api/task/3?n=3").get_json()
    gpas = [float(r["gpa"]) for r in rows]
    assert len(rows) == 3 and gpas == sorted(gpas, reverse=True)
    assert client.get("/api/task/3?n=abc").status_code == 200


def test_task_filter(client):
    rows = client.get("/api/task/2?university=UKH&major=Computer Science").get_json()
    assert all(r["university"] == "UKH" and r["major"] == "Computer Science" for r in rows)


def test_crud_roundtrip(client):
    sid = "S99999"
    base = {"student_id": sid, "full_name": "Test User", "university": "UKH",
            "major": "Computer Science", "gpa": "3.9"}
    assert client.post("/api/task/4", json={"action": "create", **base}).status_code == 200
    assert client.post("/api/task/4", json={"action": "read", "student_id": sid}).get_json()["full_name"] == "Test User"
    client.post("/api/task/4", json={"action": "update", "student_id": sid, "major": "Data Science"})
    rows = client.get("/api/task/2?university=UKH&major=Data Science").get_json()
    assert sid in [r["student_id"] for r in rows]
    client.post("/api/task/4", json={"action": "delete", "student_id": sid})
    assert "error" in client.post("/api/task/4", json={"action": "read", "student_id": sid}).get_json()
    assert client.post("/api/task/4", json={"action": "drop", "student_id": sid}).status_code == 400


def test_read_only_blocks_writes(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "READ_ONLY", True)
    r = client.post("/api/task/4", json={"action": "delete", "student_id": "S001"})
    assert r.status_code == 403
    assert client.post("/api/task/4", json={"action": "read", "student_id": "S001"}).status_code == 200


def test_ask_validation(client):
    assert client.get("/api/ask?q=").status_code == 400
    assert client.get("/api/ask?q=" + "x" * 400).status_code == 400
    j = client.get("/api/ask?q=average gpa at UKH").get_json()
    assert "elapsed_ms" in j and j["intent"] != "unknown"


def test_ft_escape():
    assert queries.core._ft_escape("c++ @x") == r"c\+\+ \@x"


def test_every_task_endpoint_ok(client):
    for n in (1, 5, 6, 7, 8, 9, 10):
        r = client.get(f"/api/task/{n}")
        assert r.status_code == 200, n
    assert client.get("/api/task/1").get_json()["student"] == 1000
