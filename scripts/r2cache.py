"""Tiny R2 (Cloudflare S3-compatible) cache for downloaded market data.
- Needs secrets R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and the account id (R2_ACCOUNT_ID or the existing CLOUDFLARE_ACCOUNT_ID); without them every call is a no-op (tests still run).
- Objects are gzip-compressed JSON in bucket R2_BUCKET (default sentinel-data).
- Size guard: refuses to save once the bucket would exceed R2_MAX_GB (default 9 GB), so it stays in the free 10 GB.
- Never raises: any R2 problem is printed and the caller just downloads from Alpaca as before."""
import os, io, gzip, json

BUCKET = os.environ.get("R2_BUCKET", "sentinel-data")
MAX_BYTES = float(os.environ.get("R2_MAX_GB", "9")) * 1e9
_c = [None, False]

def client():
    if _c[1]: return _c[0]
    _c[1] = True
    acct = os.environ.get("R2_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")   # same account id the site deploy uses
    kid, sec = os.environ.get("R2_ACCESS_KEY_ID"), os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (acct and kid and sec): print("r2cache: no R2 secrets, cache off", flush=True); return None
    try:
        import boto3
        _c[0] = boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com", aws_access_key_id=kid, aws_secret_access_key=sec, region_name="auto")
    except Exception as e: print("r2cache: client error", e, flush=True)
    return _c[0]

def load(key):
    c = client()
    if not c: return None
    try:
        obj = c.get_object(Bucket=BUCKET, Key=key)
        data = json.loads(gzip.decompress(obj["Body"].read()))
        print(f"r2cache: loaded {key}", flush=True); return data
    except Exception as e:
        if "NoSuchKey" not in str(e) and "404" not in str(e): print("r2cache: load error", key, str(e)[:200], flush=True)
        return None

def bucket_bytes(c):
    total, tok = 0, None
    while True:
        r = c.list_objects_v2(Bucket=BUCKET, **({"ContinuationToken": tok} if tok else {}))
        total += sum(o["Size"] for o in r.get("Contents", []))
        if not r.get("IsTruncated"): return total
        tok = r["NextContinuationToken"]

def save(key, obj):
    c = client()
    if not c: return False
    try:
        body = gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), 6)
        try: old = c.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
        except Exception: old = 0
        used = bucket_bytes(c)
        if used - old + len(body) > MAX_BYTES:
            print(f"r2cache: NOT saving {key}: bucket would be {(used - old + len(body)) / 1e9:.2f} GB (limit {MAX_BYTES / 1e9:.0f} GB)", flush=True); return False
        c.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/gzip")
        print(f"r2cache: saved {key} ({len(body) / 1e6:.1f} MB, bucket ~{(used - old + len(body)) / 1e9:.2f} GB)", flush=True); return True
    except Exception as e:
        print("r2cache: save error", key, str(e)[:200], flush=True); return False
