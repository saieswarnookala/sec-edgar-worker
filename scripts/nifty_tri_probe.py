"""One-off probe: which request shape does niftyindices.com answer from GitHub Actions? Prints status, final URL and the first bytes."""
import urllib.request, http.cookiejar, json
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
U = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"
BODY = '{"cinfo":"{\'name\':\'NIFTY 50\',\'startDate\':\'01-Oct-2026\',\'endDate\':\'20-Nov-2026\',\'indexName\':\'NIFTY 50\'}"}'
class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
for lbl, hdr, warm in (("doc headers", {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.niftyindices.com/reports/historical-data", "User-Agent": UA}, False),
                       ("doc headers + warm cookies", {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.niftyindices.com/reports/historical-data", "User-Agent": UA}, True),
                       ("+ accept/origin", {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.niftyindices.com/reports/historical-data", "User-Agent": UA, "Accept": "application/json, text/javascript, */*; q=0.01", "Origin": "https://www.niftyindices.com"}, True)):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedir())
    try:
        if warm: op.open(urllib.request.Request("https://www.niftyindices.com/reports/historical-data", headers={"User-Agent": UA}), timeout=40).read()
        r = op.open(urllib.request.Request(U, data=BODY.encode(), headers=hdr, method="POST"), timeout=40); b = r.read()
        print(lbl, "| status", r.status, "| url", r.geturl(), "| type", r.headers.get("Content-Type"), "|", b[:200])
    except urllib.error.HTTPError as e: print(lbl, "| HTTP", e.code, "| location", e.headers.get("Location"), "|", e.read()[:200])
    except Exception as e: print(lbl, "| ERR", e)
