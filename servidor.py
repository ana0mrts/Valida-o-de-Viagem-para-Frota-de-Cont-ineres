"""Servidor local do Score de Compradores (somente biblioteca padrão).

Uso:  python3 servidor.py                 -> http://127.0.0.1:8000
      python3 servidor.py --host 0.0.0.0  -> acessível na rede da empresa
"""
import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from score import DadosInvalidos, calc_score

PASTA = Path(__file__).parent
MAX_BODY = 1_000_000  # 1 MB
log = logging.getLogger("servidor")


class Handler(BaseHTTPRequestHandler):
    server_version = "ScoreServer"

    def _enviar(self, status: int, corpo: bytes, tipo: str):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, status: int, obj: dict):
        self._enviar(status, json.dumps(obj, ensure_ascii=False).encode(),
                     "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._enviar(200, (PASTA / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/saude":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"erro": "Não encontrado."})

    def do_POST(self):
        if self.path != "/api/score":
            return self._json(404, {"erro": "Não encontrado."})
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            if not 0 < tamanho <= MAX_BODY:
                return self._json(413, {"erro": "Corpo ausente ou grande demais."})
            dados = json.loads(self.rfile.read(tamanho))
            self._json(200, calc_score(dados).to_dict())
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"erro": "JSON inválido."})
        except DadosInvalidos as e:
            self._json(422, {"erro": str(e)})
        except Exception:
            log.exception("Erro inesperado")
            self._json(500, {"erro": "Erro interno."})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Servindo em http://%s:%d", a.host, a.port)
    try:
        ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        log.info("Encerrado.")
