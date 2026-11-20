import copy,csv,hashlib,io,json
import pytest
from app import store
from app.errors import DomainError
from app.pipeline import calculate,execute,load_sample
from app.seal import build_seal,business_checksum,canonical
def test_checksum_stable_across_reruns(sample):
    "同源重跑只改运行记录，业务校验值不变"
    a,b=calculate(sample),calculate(sample)
    b["manifest"]["generated_at"]="2030-01-01T00:00:00+00:00";b["manifest"]["elapsed_ms"]=99999
    assert business_checksum(a)==business_checksum(b)
def test_checksum_covers_quarantine(sample):
    run=calculate(sample);tampered=copy.deepcopy(run)
    tampered["stages"][-1]["cumulative_quarantine"]=[]
    assert business_checksum(tampered)!=business_checksum(run)
def test_checksum_covers_intake(sample):
    run=calculate(sample);tampered=copy.deepcopy(run)
    tampered["stages"][0]["metrics"]["quarantine"]=0
    assert business_checksum(tampered)!=business_checksum(run)
def test_checksum_covers_final_rows(sample):
    run=calculate(sample);tampered=copy.deepcopy(run)
    tampered["stages"][-1]["rows"][0]["expected"]="0.00"
    assert business_checksum(tampered)!=business_checksum(run)
def test_checksum_covers_input_digest():
    assert business_checksum(calculate(load_sample("dirty.csv")))!=business_checksum(calculate(load_sample("clean.csv")))
def test_checksum_covers_parameters(sample):
    assert business_checksum(calculate(sample))!=business_checksum(calculate(sample,{"retention_rate":"0.06"}))
def test_not_ready_cannot_seal(sample):
    run=calculate(sample);run["stages"][-1]["metrics"]["ready"]=False
    with pytest.raises(DomainError) as e: build_seal(run)
    assert e.value.code=="NOT_READY"
def test_seal_created_then_reused(client,sample):
    "同一来源重试不能重复封存"
    run=execute(sample);url=f"/api/runs/{run['run_id']}/seal"
    first=client.post(url);assert first.status_code==201 and first.get_json()["created"] is True
    retry=client.post(url);assert retry.status_code==200 and retry.get_json()["created"] is False
    assert retry.get_json()["business_sha256"]==first.get_json()["business_sha256"]
    with store.connect() as db: assert db.execute("SELECT COUNT(*) FROM seals").fetchone()[0]==1
def test_rerun_same_source_not_sealed_twice(client,sample):
    "现场刷新证据：同源重跑后再封存仍只有一份"
    run=execute(sample);client.post(f"/api/runs/{run['run_id']}/seal")
    rerun=execute(sample)
    assert rerun["run_id"]==run["run_id"]
    assert client.post(f"/api/runs/{rerun['run_id']}/seal").status_code==200
    with store.connect() as db: assert db.execute("SELECT COUNT(*) FROM seals").fetchone()[0]==1
def test_seal_result_separates_run_record(client,sample):
    "业务校验值与运行记录分开，且校验值可复核重算"
    run=execute(sample)
    payload=client.post(f"/api/runs/{run['run_id']}/seal").get_json()
    assert set(payload["run_record"])=={"run_id","generated_at","elapsed_ms","sealed_at"}
    assert "generated_at" not in json.dumps(payload["facts"]) and "elapsed_ms" not in json.dumps(payload["facts"])
    assert hashlib.sha256(canonical(payload["facts"]).encode()).hexdigest()==payload["business_sha256"]
def test_get_seal_404_then_200(client,sample):
    run=execute(sample);url=f"/api/runs/{run['run_id']}/seal"
    assert client.get(url).status_code==404
    client.post(url)
    assert client.get(url).status_code==200
def test_failed_seal_keeps_previous(client,sample,monkeypatch):
    "归档失败保留旧版"
    run=execute(sample);url=f"/api/runs/{run['run_id']}/seal"
    first=client.post(url).get_json()
    def boom(_): raise DomainError("ARCHIVE_FAIL","模拟归档失败")
    monkeypatch.setattr(store,"build_seal",boom)
    assert client.post(url).status_code==422
    assert client.get(url).get_json()["business_sha256"]==first["business_sha256"]
def test_archive_csv_has_seal_and_run_record(client):
    "证据导出自带业务校验值、可重算事实与分开的运行记录"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    rows=list(csv.reader(io.StringIO(client.get(f"/api/runs/{p['run_id']}/archive").data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256"
    seal_rows=[r for r in rows[1:] if r[3]=="seal"];record_rows=[r for r in rows[1:] if r[3]=="run_record"]
    checksum=next(r[6] for r in seal_rows if r[5]=="business_sha256")
    facts=next(r[6] for r in seal_rows if r[5]=="facts")
    assert hashlib.sha256(facts.encode()).hexdigest()==checksum
    assert {r[5] for r in record_rows}=={"generated_at","elapsed_ms"}
