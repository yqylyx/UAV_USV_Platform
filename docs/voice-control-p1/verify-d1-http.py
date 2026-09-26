"""Local real-ASR smoke. Requires supplied audio and environment credentials; no audio/text export."""
import argparse, hashlib, http.cookiejar, json, os, pathlib, time, urllib.request, urllib.error, urllib.parse, uuid

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audio',required=True);parser.add_argument('--mime',choices=['audio/mpeg','audio/webm'],required=True);parser.add_argument('--base',default='http://localhost:15174');parser.add_argument('--output',required=True);parser.add_argument('--request-id');parser.add_argument('--expect-code');args=parser.parse_args()
    u=urllib.parse.urlparse(args.base)
    if u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1') or u.username: raise SystemExit('Local HTTP only')
    audio=pathlib.Path(args.audio).read_bytes()
    if not 1<=len(audio)<=5242880: raise SystemExit('Audio size outside D1 limits')
    username=os.environ['D1_TEST_USERNAME'];password=os.environ['D1_TEST_PASSWORD']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path,body=None,headers=None):
        req=urllib.request.Request(args.base.rstrip('/')+path,data=body,headers=headers or {})
        try: response=opener.open(req,timeout=140)
        except urllib.error.HTTPError as e: response=e
        with response: return response.status,json.loads(response.read()),dict(response.headers)
    status,_,_=request('/api/auth/login',json.dumps({'username':username,'password':password}).encode(),{'Content-Type':'application/json'})
    if status!=200:raise SystemExit('Login failed; credentials are not printed')
    try:
        status,csrf,_=request('/api/auth/csrf');assert status==200
        rid=args.request_id or str(uuid.uuid4())
        try: assert str(uuid.UUID(rid)) == rid and rid == rid.lower()
        except (AssertionError,ValueError): raise SystemExit('request-id must be a lowercase UUID')
        boundary='d1-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="requestId"\r\n\r\n{rid}\r\n--{boundary}\r\nContent-Disposition: form-data; name="locale"\r\n\r\nzh-CN\r\n--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="audio"\r\nContent-Type: {args.mime}\r\n\r\n').encode()+audio+f'\r\n--{boundary}--\r\n'.encode()
        headers={'Content-Type':'multipart/form-data; boundary='+boundary,'X-Request-ID':rid,'Idempotency-Key':rid,csrf['data']['headerName']:csrf['data']['token']}
        started=time.perf_counter();status,first,_=request('/api/voice/intelligence/transcriptions',body,headers);elapsed=time.perf_counter()-started
        result={'requestId':rid,'audioSha256':hashlib.sha256(audio).hexdigest(),'status':status,'code':first.get('code'),'elapsedSeconds':elapsed,'result':'FAIL'}
        if args.expect_code:
            assert status==409 and first.get('code')==args.expect_code
            result.update(result='PASS_EXPECTED_ERROR',identicalReplay=None)
        elif status==200:
            data=first['data'];assert data['requestId']==rid and data['provider']=='local-asr'
            replay_status,replay,_=request('/api/voice/intelligence/transcriptions',body,headers)
            assert replay_status==200 and replay==first
            result.update(result='PASS_HTTP_SMOKE',durationMs=data['durationMs'],model=data['model'],textCodePoints=len(data['text']),identicalReplay=True)
        out=pathlib.Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
        if result['result']=='FAIL':raise SystemExit(1)
    finally:
        try:request('/api/auth/logout',b'{}',{'Content-Type':'application/json',csrf['data']['headerName']:csrf['data']['token']})
        except Exception:pass
if __name__=='__main__':main()
