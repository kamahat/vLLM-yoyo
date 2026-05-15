#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess, json, urllib.parse

MODELS = {
    'qwen': 'qwen2.5-coder-7b',
    'unfilteredai': 'unfilteredai-1b',
    'badmistral': 'badmistral-1.5b',
    'imagegen': 'nsfw-gen-v2'
}

# Models served on port 8003 (image generation)
IMAGE_MODELS = {'imagegen'}

def get_active_model():
    # Check port 8000 (text models)
    try:
        r = subprocess.run(
            ['curl','-s','--connect-timeout','2','http://localhost:8000/v1/models'],
            capture_output=True, text=True, timeout=3)
        data = json.loads(r.stdout)
        if data.get('data'):
            return data['data'][0]['id'], True
    except:
        pass
    # Check port 8003 (image gen)
    try:
        r = subprocess.run(
            ['curl','-s','--connect-timeout','2','http://localhost:8003/health'],
            capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return 'nsfw-gen-v2', True
    except:
        pass
    return None, False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/status':
            model, ready = get_active_model()
            self._json(200, {'active': model, 'ready': ready})
        elif path.startswith('/switch/'):
            key = path.split('/')[-1]
            if key not in MODELS:
                self._json(400, {'error': 'unknown model'})
                return
            subprocess.Popen(['/usr/local/bin/vllm-switch', key])
            self._json(200, {'status': 'switching', 'model': key, 'name': MODELS[key]})
        else:
            self._json(404, {'error': 'not found'})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,OPTIONS')
        self.end_headers()

HTTPServer(('0.0.0.0', 8002), Handler).serve_forever()
