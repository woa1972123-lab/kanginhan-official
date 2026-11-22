"""Kang In Han official site: standard library only. Python 3.9+."""
import os, json, re, secrets, sqlite3, shutil, hmac, time, mimetypes, hashlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote, parse_qs, quote
from http.cookies import SimpleCookie
BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DATA_DIR',str(BASE/'data'))).resolve(); DATA.mkdir(parents=True,exist_ok=True)
UPLOAD=DATA/'uploads'; UPLOAD.mkdir(exist_ok=True)
PASS=os.environ.get('ADMIN_PASSWORD')
SECRET=os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
SESSIONS={}; ATTEMPTS={}
DB=DATA/'site.sqlite3'
SEED=[('rock','내가 나를 버렸다','ROCK','살아온 세월 속에서 잊고 지냈던 자신을 돌아보는 강렬한 록 발라드.'),('life','인생역전','ROCK','다시 일어서는 삶의 희망. 내 인생의 전성기는 지금부터다.'),('longing','그리움은 늙지도 않더라','BALLAD','세월이 흘러도 가슴에 남은 사랑과 그리움.'),('soju','쓰다… 소주처럼…','BLUES','한 잔에 지난 세월을 담은 인생 블루스.'),('ballad','내가 나를 버렸다 (Ballad)','BALLAD','지나온 삶을 담담하게 돌아보는 감성 발라드 버전.')]
def conn():
    db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row;return db
with conn() as db:
    db.execute('CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,title TEXT NOT NULL,artist TEXT NOT NULL,genre TEXT NOT NULL,description TEXT,source TEXT,youtube TEXT,cover TEXT,created REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
    if not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
        for i,(k,title,genre,desc) in enumerate(SEED):
            db.execute('INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?)',(k,title,'강인한',genre,desc,f'seed_media/{k}.mp4',None,f'assets/{k}.jpg',time.time()-i))
        db.execute("INSERT INTO settings VALUES('seeded','1')")
    # Add this repository-backed release once, including for existing databases.
    if (BASE/'seed_media/heaven.mp4').is_file() and not db.execute("SELECT 1 FROM settings WHERE key='seed_heaven_v1'").fetchone():
        db.execute('INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?,?,?,?)',('heaven','하늘도 갈라놓을 수 없는 사랑','강인한','OTHER','Even Heaven Can’t Tear Us Apart','seed_media/heaven.mp4',None,'assets/stage.jpg',time.time()))
        db.execute("INSERT INTO settings VALUES('seed_heaven_v1','1')")
    # Register repository-backed music videos once, also on existing deployments.
    if not db.execute("SELECT 1 FROM settings WHERE key='release_20261122_v1'").fetchone():
        releases=[
            ('sojunew','쓰다… 소주처럼… (새 뮤직비디오)','BLUES',
             '강인한의 인생 블루스, 새롭게 편집한 뮤직비디오.','seed_media/kanginhan_homepage_mv1.mp4','assets/soju.jpg'),
            ('spanish','인생 산다는 게 뭘까 (스페인어 뮤직비디오)','OTHER',
             '강인한의 스페인어 뮤직비디오.','seed_media/kanginhan_spanish_mv-1.mp4','assets/stage.jpg'),
            ('lagrimas','검은 눈물 (Lágrimas Negras)','BLUES',
             '강인한의 라틴 블루스 뮤직비디오.','seed_media/kanginhan_lagrimas_negras_homepage.mp4','assets/rock.jpg'),
        ]
        for i,(vid,title,genre,desc,source,cover) in enumerate(releases):
            if (BASE/source).is_file():
                db.execute('INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?,?,?,?)',
                           (vid,title,'강인한',genre,desc,source,None,cover,time.time()+i+1))
        db.execute("INSERT INTO settings VALUES('release_20261122_v1','1')")
class APIError(Exception):
    def __init__(self,msg,status=400): self.msg=msg;self.status=status
class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def send_json(self,body,status=200,extra=None):
        data=json.dumps(body,ensure_ascii=False).encode('utf8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def token(self):
        try:c=SimpleCookie(self.headers.get('Cookie',''));return c['session'].value if 'session' in c else None
        except:return None
    def auth(self):return bool(PASS) and SESSIONS.get(self.token(),0)>time.time()
    def require(self):
        if not self.auth():raise APIError('관리자 로그인이 필요합니다.',401)
    def check_origin(self):
        origin=self.headers.get('Origin'); host=self.headers.get('Host')
        if origin and urlsplit(origin).netloc!=host:raise APIError('허용되지 않은 요청입니다.',403)
    def body(self,limit=65536):
        try:n=int(self.headers.get('Content-Length','0'))
        except:raise APIError('잘못된 요청')
        if not 0<n<=limit: self.close_connection=True;raise APIError('요청 크기가 올바르지 않습니다.',413)
        try:return json.loads(self.rfile.read(n))
        except:raise APIError('잘못된 데이터입니다.')
    def cookie(self,token,age):
        secure='; Secure' if self.headers.get('X-Forwarded-Proto')=='https' or os.environ.get('COOKIE_SECURE')=='1' else ''
        return f'session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'+secure
    def log_message(self,fmt,*args): print(fmt%args,flush=True)
    def get_path(self):return unquote(urlsplit(self.path).path)
    def serve(self,p,head=False,download_name=None):
        if not p.is_file():raise APIError('파일이 없습니다.',404)
        n=p.stat().st_size;start=0;end=n-1;partial=False
        if self.headers.get('Range'):
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
            if not m or not any(m.groups()):raise APIError('잘못된 재생 범위',416)
            a,b=m.groups();start=int(a) if a else max(0,n-int(b));end=min(n-1,int(b)) if a and b else n-1
            if start>end or start>=n:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{n}');self.send_header('Content-Length','0');self.end_headers();return
            partial=True
        self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-cache' if p.suffix=='.html' else 'public,max-age=3600')
        if download_name:
            self.send_header('Content-Disposition', "attachment; filename=\"Kang-In-Han.mp4\"; filename*=UTF-8''" + quote(download_name, safe=''))
        if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{n}')
        self.end_headers()
        if head:return
        with p.open('rb') as f:
            f.seek(start);remain=end-start+1
            while remain:
                b=f.read(min(remain,256*1024))
                if not b:break
                self.wfile.write(b);remain-=len(b)
    def download_video(self,vid,head=False):
        with conn() as db:
            row=db.execute('SELECT title,source,youtube FROM videos WHERE id=?',(vid,)).fetchone()
        if not row or row['youtube'] or not self.valid_media(row['source'],'video'):
            raise APIError('다운로드 가능한 영상이 없습니다.',404)
        source=row['source']
        path=UPLOAD/source[9:] if source.startswith('/uploads/') else BASE/source
        title=re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', row['title']).strip()[:100] or vid
        return self.serve(path,head,download_name='강인한 - '+title+'.mp4')
    def get(self,head=False):
        p=self.get_path()
        download=re.fullmatch(r'/download/([a-z0-9]+)',p)
        if download:return self.download_video(download.group(1),head)
        if p=='/api/videos':
            with conn() as db: rows=[dict(r) for r in db.execute('SELECT id,title,artist,genre,description,source,youtube,cover FROM videos ORDER BY created DESC')]
            for row in rows:
                row['downloadable']=bool(not row.get('youtube') and self.valid_media(row.get('source'),'video'))
                row['ready']=bool(row.get('youtube') or row['downloadable'])
            return self.send_json(rows)
        if p=='/api/session':return self.send_json({'authenticated':self.auth(),'configured':bool(PASS)})
        if p=='/':return self.serve(BASE/'index.html',head)
        if p.startswith('/uploads/'):
            name=p[9:]
            if not re.fullmatch(r'[a-f0-9]{32}\.(mp4|png|jpg|webp)',name):raise APIError('파일 없음',404)
            return self.serve(UPLOAD/name,head)
        if re.fullmatch(r'/(assets/[a-z]+\.jpg|seed_media/[a-z0-9_-]+\.mp4)',p):
            download_names={
                'kanginhan_homepage_mv1.mp4':'강인한_쓰다_소주처럼.mp4',
                'da_noko_ganda.mp4':'강인한_다_놓고_간다.mp4',
                'strong_cheongchunbyeolgok.mp4':'STRONG_청춘별곡_새리마스터.mp4',
                'billyeo_sseuneun_haneul.mp4':'강인한_빌려_쓰는_하늘.mp4',
                'kanginhan_spanish_mv-1.mp4':'강인한_인생산다는게뭘까_스페인어.mp4',
                'kanginhan_lagrimas_negras_homepage.mp4':'강인한_검은눈물_Lagrimas_Negras.mp4',
            }
            name=p[len('/seed_media/'):] if p.startswith('/seed_media/') else ''
            if parse_qs(urlsplit(self.path).query).get('download')==['1'] and name in download_names:
                return self.serve(BASE/p[1:],head,download_name=download_names[name])
            return self.serve(BASE/p[1:],head)
        raise APIError('페이지 없음',404)
    def upload(self):
        self.require();kind=parse_qs(urlsplit(self.path).query).get('kind',[''])[0];limit=500*1024*1024 if kind=='video' else 10*1024*1024
        try:n=int(self.headers.get('Content-Length','0'))
        except:raise APIError('파일 크기 오류')
        if kind not in ('video','image') or n<16 or n>limit:self.close_connection=True;raise APIError('허용된 파일 종류 또는 크기를 확인하세요.',413)
        first=self.rfile.read(min(n,32));remaining=n-len(first)
        ext=None
        if kind=='video' and first[4:8]==b'ftyp':ext='mp4'
        if kind=='image':
            if first.startswith(b'\xff\xd8\xff'):ext='jpg'
            elif first.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
            elif first[:4]==b'RIFF' and first[8:12]==b'WEBP':ext='webp'
        if not ext:self.close_connection=True;raise APIError('올바른 MP4 또는 이미지 파일을 선택하세요.')
        name=secrets.token_hex(16)+'.'+ext;p=UPLOAD/name;tmp=p.with_suffix('.partial')
        try:
            with tmp.open('wb') as f:
                f.write(first)
                while remaining:
                    chunk=self.rfile.read(min(1024*1024,remaining))
                    if not chunk:raise APIError('업로드가 중단되었습니다.')
                    f.write(chunk);remaining-=len(chunk)
            tmp.replace(p)
        finally:
            tmp.unlink(missing_ok=True)
        return self.send_json({'path':'/uploads/'+name})
    def valid_media(self,path,kind):
        if not isinstance(path,str):return False
        if path.startswith('/uploads/'):
            name=path[9:]; patt=r'[a-f0-9]{32}\.mp4' if kind=='video' else r'[a-f0-9]{32}\.(jpg|png|webp)'
            return bool(re.fullmatch(patt,name)) and (UPLOAD/name).is_file()
        if kind=='video':return bool(re.fullmatch(r'seed_media/[a-z0-9_-]+\.mp4',path)) and (BASE/path).is_file()
        return (bool(re.fullmatch(r'assets/[a-z]+\.jpg',path)) and (BASE/path).is_file()) or bool(re.fullmatch(r'https://i\.ytimg\.com/vi/[\w-]{11}/hqdefault\.jpg',path))
    def update(self,vid=None):
        self.require();b=self.body()
        if not isinstance(b,dict):raise APIError('잘못된 입력')
        title=str(b.get('title','')).strip();artist=str(b.get('artist','')).strip();genre=b.get('genre');desc=str(b.get('description',''));source=b.get('source');yt=b.get('youtube');cover=b.get('cover')
        if not title or len(title)>120 or not artist or len(artist)>80 or genre not in ('ROCK','BALLAD','BLUES','OTHER') or len(desc)>2000:raise APIError('제목, 가수명 또는 소개글을 확인하세요.')
        if yt:
            if not isinstance(yt,str) or not re.fullmatch(r'[\w-]{11}',yt):raise APIError('올바르지 않은 유튜브 영상입니다.')
            source=None
        elif not self.valid_media(source,'video'):raise APIError('영상 파일을 확인하세요.')
        else:yt=None
        if not self.valid_media(cover,'image'):raise APIError('썸네일을 확인하세요.')
        with conn() as db:
            if vid:
                if not db.execute('SELECT 1 FROM videos WHERE id=?',(vid,)).fetchone():raise APIError('영상 없음',404)
                db.execute('UPDATE videos SET title=?,artist=?,genre=?,description=?,source=?,youtube=?,cover=? WHERE id=?',(title,artist,genre,desc,source,yt,cover,vid))
            else:
                vid=secrets.token_hex(16);db.execute('INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?)',(vid,title,artist,genre,desc,source,yt,cover,time.time()))
        return self.send_json({'ok':True,'id':vid})
    def post(self):
        self.check_origin();p=self.get_path()
        if p=='/api/login':
            if not PASS: self.close_connection=True;raise APIError('관리자 암호 설정 전입니다.',503)
            ip=self.client_address[0];now=time.time();attempts=[t for t in ATTEMPTS.get(ip,[]) if now-t<300];ATTEMPTS[ip]=attempts
            if len(attempts)>=12:raise APIError('로그인 시도가 많습니다. 잠시 후 다시 시도하세요.',429)
            b=self.body();password=str(b.get('password','')) if isinstance(b,dict) else ''
            if not hmac.compare_digest(password.encode(),PASS.encode()):attempts.append(now);raise APIError('암호가 올바르지 않습니다.',401)
            ATTEMPTS.pop(ip,None);token=secrets.token_urlsafe(32);SESSIONS[token]=now+8*3600
            return self.send_json({'ok':True},extra={'Set-Cookie':self.cookie(token,28800)})
        if p=='/api/logout':SESSIONS.pop(self.token(),None);return self.send_json({'ok':True},extra={'Set-Cookie':self.cookie('',0)})
        if p=='/api/upload':return self.upload()
        if p=='/api/videos':return self.update()
        raise APIError('페이지 없음',404)
    def modify(self,delete=False):
        self.check_origin();self.require();m=re.fullmatch(r'/api/videos/([a-z0-9]+)',self.get_path())
        if not m:raise APIError('페이지 없음',404)
        if not delete:return self.update(m.group(1))
        with conn() as db:db.execute('DELETE FROM videos WHERE id=?',(m.group(1),))
        return self.send_json({'ok':True})
    def run_safe(self,func):
        try:func()
        except APIError as e:self.send_json({'error':e.msg},e.status)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:print(type(e).__name__,str(e),flush=True);self.close_connection=True;self.send_json({'error':'서버 요청 처리 오류'},500)
    def do_GET(self):self.run_safe(self.get)
    def do_HEAD(self):self.run_safe(lambda:self.get(True))
    def do_POST(self):self.run_safe(self.post)
    def do_PUT(self):self.run_safe(self.modify)
    def do_DELETE(self):self.run_safe(lambda:self.modify(True))
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'));host=os.environ.get('HOST','127.0.0.1')
    print(f'KANG IN HAN: http://{host}:{port}',flush=True)
    ThreadingHTTPServer((host,port),H).serve_forever()
