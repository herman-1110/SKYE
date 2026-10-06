"""VIGI camera ONVIF check (Prompt 130, Part E2). Read-only.

1. GetSystemDateAndTime without credentials: tells whether ONVIF answers.
2. One authenticated GetProfiles + GetStreamUri per profile (WS-Security
   UsernameToken with PasswordDigest, user admin). A rejected login stops it;
   it never retries, because the camera locks the account after repeated
   failures.

The password comes from VIGI_CAMERA_PASSWORD (environment, or backend/.env)
and is never printed. Stream URIs are printed with any user:password@ part
removed.

    python onvif_probe.py [--host 192.168.0.101] [--ports 2020 80]
"""
import argparse
import base64
import datetime as dt
import hashlib
import http.client
import os
import re
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_password() -> str:
    pw = os.environ.get("VIGI_CAMERA_PASSWORD", "")
    if pw:
        return pw
    try:
        from dotenv import dotenv_values
        return dotenv_values(REPO / "backend" / ".env").get("VIGI_CAMERA_PASSWORD") or ""
    except ImportError:
        return ""


def _envelope(body: str, security: str = "") -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            f'<s:Header>{security}</s:Header><s:Body>{body}</s:Body></s:Envelope>')


def _security(password: str) -> str:
    nonce = secrets.token_bytes(16)
    created = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    return ('<Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" s:mustUnderstand="1">'
            '<UsernameToken><Username>admin</Username>'
            '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
            f'{digest}</Password>'
            f'<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</Nonce>'
            f'<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>'
            '</UsernameToken></Security>')


def _post(host: str, port: int, path: str, xml: str):
    conn = http.client.HTTPConnection(host, port, timeout=8)
    try:
        conn.request("POST", path, body=xml.encode(), headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    finally:
        conn.close()


def _tags(xml: str, tag: str) -> list:
    return re.findall(rf"<(?:\w+:)?{tag}[^>]*>(.*?)</(?:\w+:)?{tag}>", xml, re.S)


def _fault(xml: str) -> str:
    sub = re.findall(r"<(?:\w+:)?Value>([^<]+)</(?:\w+:)?Value>", xml)
    text = re.findall(r"<(?:\w+:)?Text[^>]*>([^<]+)</(?:\w+:)?Text>", xml)
    return f"{' / '.join(sub)} {text[0] if text else ''}".strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.101")
    ap.add_argument("--ports", type=int, nargs="+", default=[2020, 80])
    args = ap.parse_args()
    path = "/onvif/device_service"

    found = None
    for port in args.ports:
        try:
            status, xml = _post(args.host, port, path, _envelope("<tds:GetSystemDateAndTime/>"))
        except Exception as e:
            print(f"port {port}: {type(e).__name__}: {e}")
            continue
        utc = _tags(xml, "UTCDateTime")
        print(f"port {port}: HTTP {status}, ONVIF {'answers' if 'GetSystemDateAndTimeResponse' in xml else 'no answer'}"
              + (f", camera UTC {re.sub(r'<[^>]+>', ' ', utc[0]).split()}" if utc else ""))
        if "GetSystemDateAndTimeResponse" in xml:
            found = port
            break
    if found is None:
        print("ONVIF not answering on the ports tried.")
        return 0

    password = _load_password()
    if not password:
        print("VIGI_CAMERA_PASSWORD not set; skipping the authenticated part.")
        return 0
    status, xml = _post(args.host, found, path, _envelope("<trt:GetProfiles/>", _security(password)))
    if "GetProfilesResponse" not in xml:
        print(f"GetProfiles: HTTP {status}, fault: {_fault(xml) or '(none)'}. Not retrying.")
        return 1
    profiles = re.findall(r'<(?:\w+:)?Profiles[^>]*token="([^"]+)"', xml)
    print(f"profiles: {profiles}")
    for block in re.findall(r"<(?:\w+:)?Profiles\b.*?</(?:\w+:)?Profiles>", xml, re.S):
        token = re.search(r'token="([^"]+)"', block).group(1)
        enc = _tags(block, "Encoding")
        w, h = _tags(block, "Width"), _tags(block, "Height")
        fps = _tags(block, "FrameRateLimit")
        print(f"  {token}: encoding {enc[:1]}, {w[:1]}x{h[:1]}, frame rate limit {fps[:1]}")
        body = (f'<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>'
                f'<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>'
                f'<trt:ProfileToken>{token}</trt:ProfileToken></trt:GetStreamUri>')
        status, sx = _post(args.host, found, path, _envelope(body, _security(password)))
        uri = _tags(sx, "Uri")
        clean = re.sub(r"//[^/@]*@", "//", uri[0]) if uri else f"(HTTP {status}, {_fault(sx)})"
        print(f"    stream URI: {clean}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
