#!/usr/bin/env python3
"""
Deploy the built site to Tencent Cloud COS (static website hosting).

Pure standard library - no pip install needed.

Usage:
  export COS_SECRET_ID=AKIDxxxxxxxxxxxxxxxx
  export COS_SECRET_KEY=xxxxxxxxxxxxxxxx
  export COS_REGION=ap-shanghai
  export COS_BUCKET=mimi-vocab-1250000000      # format: name-appid

  python3 deploy_cos.py

Steps performed:
  1. create the bucket if missing, set ACL public-read
  2. enable static website hosting (index document = index.html)
  3. upload site/index.html
  4. probe the public URL and report whether it really serves the page
"""
import hashlib
import hmac
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(HERE), "site", "index.html")
UA = "mimi-vocab-deploy/1.0"


def env(name, default=None):
    v = os.environ.get(name, default)
    if not v:
        sys.exit("missing env var: " + name)
    return v


def sign(secret_key, secret_id, method, path, params, headers):
    """COS XML API signature, q-sign-algorithm=sha1."""
    now = int(time.time())
    key_time = "%d;%d" % (now - 60, now + 3600)

    def enc(s):
        return urllib.parse.quote(s, safe="")

    qp = sorted((k.lower(), enc(str(v))) for k, v in params.items() if k)
    hdr = sorted((k.lower(), enc(str(v))) for k, v in headers.items() if k)

    http_string = "%s\n%s\n%s\n%s\n" % (
        method.lower(),
        path,
        "&".join("%s=%s" % kv for kv in qp),
        "&".join("%s=%s" % kv for kv in hdr),
    )
    sha1_http = hashlib.sha1(http_string.encode("utf-8")).hexdigest()
    string_to_sign = "sha1\n%s\n%s\n" % (key_time, sha1_http)

    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()

    return (
        "q-sign-algorithm=sha1"
        "&q-ak=" + secret_id +
        "&q-sign-time=" + key_time +
        "&q-key-time=" + key_time +
        "&q-header-list=" + ";".join(k for k, _ in hdr) +
        "&q-url-param-list=" + ";".join(k for k, _ in qp) +
        "&q-signature=" + signature
    )


def cos_call(sid, skey, region, bucket, method, path="/", params=None, body=b"", content_type=""):
    params = params or {}
    host = "%s.cos.%s.myqcloud.com" % (bucket, region)
    url = "https://" + host + path + ("?" + urllib.parse.urlencode(params) if params else "")

    # headers that participate in the signature
    sig_headers = {"host": host}
    if content_type:
        sig_headers["content-type"] = content_type

    auth = sign(skey, sid, method, path, params, sig_headers)

    headers = {
        "Host": host,
        "Authorization": auth,
        "User-Agent": UA,
    }
    if content_type:
        headers["Content-Type"] = content_type
    if body:
        headers["Content-Length"] = str(len(body))

    req = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def probe(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "ignore")
            return r.status, len(body), ("<title>" in body)
    except Exception as e:
        return type(e).__name__, 0, False


def main():
    sid = env("COS_SECRET_ID")
    skey = env("COS_SECRET_KEY")
    region = os.environ.get("COS_REGION", "ap-shanghai")
    bucket = env("COS_BUCKET")

    if not os.path.exists(SITE):
        sys.exit("site/index.html not found - run build.py first")

    print("bucket : %s" % bucket)
    print("region : %s" % region)

    # 1. create bucket (ignore 409 = already exists and owned by you)
    st, _ = cos_call(sid, skey, region, bucket, "PUT")
    print("1. create bucket        -> %s" % ("ok" if st in (200, 409) else "HTTP %s" % st))

    # 2. public read (x-cos-acl must be inside the signature)
    host = "%s.cos.%s.myqcloud.com" % (bucket, region)
    params = {"acl": ""}
    headers = {"host": host, "x-cos-acl": "public-read"}
    auth = sign(skey, sid, "PUT", "/", params, headers)
    req = urllib.request.Request(
        "https://%s/?acl" % host, data=b"", method="PUT",
        headers={"Host": host, "Authorization": auth, "x-cos-acl": "public-read",
                 "User-Agent": UA, "Content-Length": "0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            st = r.status
    except urllib.error.HTTPError as e:
        st = e.code
    print("2. set public-read      -> %s" % ("ok" if st == 200 else "HTTP %s" % st))

    # 3. static website
    xml = ('<WebsiteConfiguration><IndexDocument><Suffix>index.html</Suffix></IndexDocument>'
           '<ErrorDocument><Key>index.html</Key></ErrorDocument></WebsiteConfiguration>')
    st, _ = cos_call(sid, skey, region, bucket, "PUT", "/", {"website": ""},
                     body=xml.encode("utf-8"), content_type="application/xml")
    print("3. enable static site   -> %s" % ("ok" if st == 200 else "HTTP %s" % st))

    # 4. upload
    data = open(SITE, "rb").read()
    st, _ = cos_call(sid, skey, region, bucket, "PUT", "/index.html", {},
                     body=data, content_type="text/html; charset=utf-8")
    print("4. upload index.html    -> %s  (%.0f KB)" % ("ok" if st == 200 else "HTTP %s" % st, len(data) / 1024))

    # 5. probe
    urls = [
        "https://%s.cos-website.%s.myqcloud.com/" % (bucket, region),
        "https://%s.cos.%s.myqcloud.com/index.html" % (bucket, region),
    ]
    print("\n5. public access probe:")
    ok = None
    for u in urls:
        s, n, html = probe(u)
        if html:
            print("   OK   %s   (%s, %d bytes)" % (u, s, n))
            ok = ok or u
        else:
            print("   --   %s   (%s)" % (u, s))

    print("")
    if ok:
        print("PUBLIC URL: " + ok)
    else:
        print("Neither default domain served the page.")
        print("COS default domains are often restricted to direct browsing - a custom")
        print("ICP-recorded domain may be required. Alternative that works out of the box:")
        print("Tencent CloudBase static hosting (gives a usable default domain).")


if __name__ == "__main__":
    main()
