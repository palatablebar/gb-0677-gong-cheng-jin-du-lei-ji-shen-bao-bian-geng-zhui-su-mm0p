import hashlib,json
from app.errors import DomainError
INTAKE_KEYS=("input","accepted","quarantine","duplicate","blank","repeated_headers","encoding")
RECONCILE_KEYS=("input","accepted_inputs","quarantine_inputs","output_records","excluded","balanced")
def business_facts(run):
    """封存身份只含业务事实：批次标识、输入摘要、规则与参数、最终行、累计隔离、批次对账。
    生成时刻与耗时属于运行记录，不进入封存身份，同源重跑因此得到同一校验值。"""
    meta=run["manifest"];final=run["stages"][-1]
    intake=run["stages"][0]["metrics"];reconcile=run["stages"][-2]["metrics"]
    return {"run_id":run["run_id"],"input_sha256":meta["input_sha256"],"rule_version":meta["rule_version"],"parameters":meta["parameters"],
        "rows":final["rows"],"quarantine":final.get("cumulative_quarantine",[]),
        "intake":{key:intake[key] for key in INTAKE_KEYS},
        "reconciliation":{key:reconcile[key] for key in RECONCILE_KEYS}}
def canonical(facts):
    return json.dumps(facts,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
def business_checksum(run):
    return hashlib.sha256(canonical(business_facts(run)).encode("utf-8")).hexdigest()
def run_record(run):
    meta=run["manifest"]
    return {"run_id":run["run_id"],"generated_at":meta["generated_at"],"elapsed_ms":meta["elapsed_ms"]}
def build_seal(run):
    if not run["stages"][-1]["metrics"].get("ready"): raise DomainError("NOT_READY","批次未通过归档校验，不能封存")
    return {"business_sha256":business_checksum(run),"facts":business_facts(run),"run_record":run_record(run)}
