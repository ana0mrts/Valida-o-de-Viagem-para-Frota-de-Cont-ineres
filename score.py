from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

log = logging.getLogger("score")

LIMITE_APROVACAO = 70.0  #pontualidade mínima (%)


class DadosInvalidos(ValueError):
    """Entrada malformada (CNPJ, datas, estrutura)."""


@dataclass
class Resultado:
    cnpj: str
    aprovado: bool
    motivo: str
    score: float | None = None
    atrasos: int = 0
    total: int = 0
    faturas: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


#validações

def _dv(base: str, pesos: list[int]) -> int:
    r = sum(int(d) * p for d, p in zip(base, pesos)) % 11
    return 0 if r < 2 else 11 - r


def normalizar_cnpj(valor: Any, exigir_dv: bool = False) -> str:
    """Retorna só os 14 dígitos. Com exigir_dv=True confere os dígitos verificadores."""
    cnpj = re.sub(r"\D", "", str(valor or ""))
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        raise DadosInvalidos("CNPJ deve ter 14 dígitos válidos.")
    if exigir_dv:
        p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        p2 = [6] + p1
        if int(cnpj[12]) != _dv(cnpj[:12], p1) or int(cnpj[13]) != _dv(cnpj[:13], p2):
            raise DadosInvalidos("CNPJ com dígitos verificadores inválidos.")
    return cnpj


def _para_data(valor: Any, campo: str) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return datetime.strptime(valor.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass
    raise DadosInvalidos(f"Data inválida em '{campo}': {valor!r} (use AAAA-MM-DD).")


#cálculo

def calc_score(
    comprador: dict,
    hoje: date | None = None,
    exigir_dv: bool = False,
    historico_vazio_aprova: bool = False,
) -> Resultado:
    """Calcula o score. Nunca imprime; devolve um Resultado estruturado.

    - vistoria ausente = reprovada (padrão seguro).
    - fatura sem pagamento e vencida conta como atraso; ainda no prazo é ignorada.
    - histórico vazio reprova, a menos que historico_vazio_aprova=True.
    """
    if not isinstance(comprador, dict):
        raise DadosInvalidos("Comprador deve ser um objeto/dicionário.")

    hoje = hoje or date.today()
    cnpj = normalizar_cnpj(comprador.get("cnpj"), exigir_dv)
    log.info("Analisando comprador %s", cnpj)

    if comprador.get("vistoria") is not True:
        return Resultado(cnpj, False, "Vistoria reprovada ou pendente.")

    historico = comprador.get("historico") or []
    if not isinstance(historico, list):
        raise DadosInvalidos("'historico' deve ser uma lista.")

    faturas, atrasos = [], 0
    for i, f in enumerate(historico, 1):
        if not isinstance(f, dict):
            raise DadosInvalidos(f"Fatura {i} malformada.")
        termo = _para_data(f.get("termo"), f"fatura {i}.termo")
        if termo is None:
            raise DadosInvalidos(f"Fatura {i} sem data de vencimento ('termo').")
        pagamento = _para_data(f.get("pagamento"), f"fatura {i}.pagamento")

        if pagamento is None:
            if hoje <= termo:
                continue  #ainda no prazo: não entra na conta
            atrasada, situacao = True, "Não paga (vencida)"
        else:
            atrasada = pagamento > termo
            situacao = "Atrasada" if atrasada else "Em dia"

        atrasos += atrasada
        faturas.append({
            "termo": termo.isoformat(),
            "pagamento": pagamento.isoformat() if pagamento else None,
            "situacao": situacao,
        })

    total = len(faturas)
    if total == 0:
        if historico_vazio_aprova:
            return Resultado(cnpj, True, "Sem histórico; aprovado por política.", 100.0)
        return Resultado(cnpj, False, "Sem histórico de faturas para avaliar.")

    score = (total - atrasos) / total * 100
    aprovado = score >= LIMITE_APROVACAO
    motivo = "Comprador bom." if aprovado else "Comprador ruim (muitos atrasos)."
    log.info("Score %.0f%% (%d atrasos em %d) aprovado=%s", score, atrasos, total, aprovado)
    return Resultado(cnpj, aprovado, motivo, round(score, 1), atrasos, total, faturas)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    casos = {
        "BOM": {"cnpj": "12345678000195", "vistoria": True, "historico": [
            {"termo": "2026-08-10", "pagamento": "2026-08-09"},
            {"termo": "2026-08-20", "pagamento": "2026-08-20"}]},
        "RUIM": {"cnpj": "98765432000110", "vistoria": True, "historico": [
            {"termo": "2026-08-10", "pagamento": "2026-08-15"},
            {"termo": "2026-08-20", "pagamento": "2026-08-28"}]},
        "VISTORIA REPROVADA": {"cnpj": "55443322000188", "vistoria": False, "historico": []},
    }
    for nome, c in casos.items():
        r = calc_score(c)
        print(f"{nome}: aprovado={r.aprovado} score={r.score} -> {r.motivo}")
