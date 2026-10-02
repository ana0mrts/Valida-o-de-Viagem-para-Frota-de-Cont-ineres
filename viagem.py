import os
import sys
from datetime import datetime, time, timedelta

import requests

api_key = ""
try:
    from google.colab import userdata
    api_key = userdata.get("GOOGLE_MAPS_API_KEY")
except (ImportError, Exception):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

url_rotas = "https://routes.googleapis.com/directions/v2:computeRoutes"

desc_min = 11 * 60
jorn_max = 10 * 60
vel_parado = 5
lim_ret = 30
f_cam = 1.2
eixos = 5

st_sefaz = {
    "100": "Autorizado o uso do MDF-e",
    "101": "Cancelamento de MDF-e homologado",
    "110": "Uso denegado",
    "132": "Encerramento de MDF-e homologado",
    "217": "MDF-e não consta na base de dados da SEFAZ",
}

zona_urb = {
    "dias": (0, 1, 2, 3, 4),
    "janelas": [(time(5, 0), time(9, 0)), (time(17, 0), time(21, 0))],
    "pbt_min": 10000,
}

def passo(n, tit):
    print(f"\n[ETAPA {n}] {tit}")

def linha(rot, val):
    print(f"  {rot:<28}{val}")

def ok(msg):
    print(f"  [OK] {msg}")

def falha(msg):
    print(f"  [FALHA] {msg}")

def aviso(msg):
    print(f"  [AVISO] {msg}")

def fmt_dur(mins):
    h, r = divmod(int(mins), 60)
    return f"{h}h{r:02d}min"

def calc_dv(base):
    s = 0
    p = 2
    for d in reversed(base):
        s += int(d) * p
        p = 2 if p == 9 else p + 1
    rest = s % 11
    return 0 if rest in (0, 1) else 11 - rest

def gera_chave(uf, aamm, cnpj, serie, num, cod):
    base = f"{uf:02d}{aamm}{cnpj}58{serie:03d}{num:09d}1{cod:08d}"
    return base + str(calc_dv(base))

def val_chave(ch):
    if len(ch) != 44 or not ch.isdigit():
        return "A chave precisa ter 44 dígitos numéricos."
    if ch[20:22] != "58":
        return "O modelo do documento não é 58 (MDF-e)."
    if int(ch[43]) != calc_dv(ch[:43]):
        return "Dígito verificador inválido."
    return None

def consult_sefaz(c):
    return c["status_sefaz"]

def pers_desc(c):
    fim = c["agora"] - timedelta(hours=c["h_jornada"])
    ini = fim - timedelta(hours=c["h_desc"])
    return [(ini, fim)]

def pos_veic(c):
    ag = c["agora"]
    par = c["m_parado"]
    pos = [{"data": ag - timedelta(minutes=par + 10), "vel": 80, "ign": 1}]
    for m in range(par, -1, -10):
        pos.append({"data": ag - timedelta(minutes=m), "vel": 0, "ign": 1})
    return pos

def maior_desc(pers):
    blocos = []
    for ini, fim in sorted(pers):
        if blocos and ini <= blocos[-1][1]:
            blocos[-1][1] = max(blocos[-1][1], fim)
        else:
            blocos.append([ini, fim])
    if not blocos:
        return 0
    ini, fim = blocos[-1]
    return int((fim - ini).total_seconds() // 60)

def tempo_par(pos):
    ini = None
    for p in reversed(pos):
        if p["vel"] <= vel_parado and p["ign"] == 1:
            ini = p["data"]
        else:
            break
    if ini is None:
        return 0
    return int((pos[-1]["data"] - ini).total_seconds() // 60)

def consult_rota(orig, dest):
    if not api_key:
        return None

    corpo = {
        "origin": {"location": {"latLng": {"latitude": orig[0], "longitude": orig[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "extraComputations": ["TOLLS"],
        "routeModifiers": {"vehicleInfo": {"emissionType": "DIESEL"}},
    }
    cab = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.travelAdvisory.tollInfo",
    }

    try:
        resp = requests.post(url_rotas, json=corpo, headers=cab, timeout=15)
        resp.raise_for_status()
        rotas = resp.json().get("routes")
    except requests.RequestException as e:
        aviso(f"Erro na Routes API: {e}")
        return None

    if not rotas:
        aviso("A Routes API não retornou nenhuma rota.")
        return None

    rota = rotas[0]
    segs = int(float(rota["duration"].rstrip("s")))

    ped = None
    info = rota.get("travelAdvisory", {}).get("tollInfo")
    if info and info.get("estimatedPrice"):
        preco = info["estimatedPrice"][0]
        val = int(preco.get("units", "0")) + preco.get("nanos", 0) / 1e9
        ped = (preco["currencyCode"], val)

    return {
        "dist_km": rota.get("distanceMeters", 0) / 1000,
        "dur_min": segs // 60,
        "pedagio": ped,
    }

def passa_restr(cheg, pbt):
    if pbt < zona_urb["pbt_min"]:
        return False
    if cheg.weekday() not in zona_urb["dias"]:
        return False
    for ini, fim in zona_urb["janelas"]:
        if ini <= cheg.time() < fim:
            return True
    return False

def etapa_mdfe(c):
    passo(1, "Validação do MDF-e")
    linha("Placa:", c["placa"])
    linha("Chave de acesso:", c["chave"])

    err = val_chave(c["chave"])
    if err:
        falha(err)
        return False
    ok("Estrutura e dígito verificador da chave estão certos.")

    cod = consult_sefaz(c)
    linha("Retorno da SEFAZ:", f"{cod} - {st_sefaz.get(cod, 'desconhecido')}")
    if cod != "100":
        falha("MDF-e sem autorização de uso.")
        return False
    ok("Manifesto autorizado.")
    return True

def etapa_desc(c):
    passo(2, "Descanso do motorista")
    linha("Motorista:", c["motorista"])

    dur = maior_desc(pers_desc(c))
    linha("Descanso apurado:", fmt_dur(dur))
    if dur < desc_min:
        alta = desc_min - dur
        falha(f"Descanso insuficiente, faltam {fmt_dur(alta)}.")
        return False
    ok("Descanso mínimo cumprido.")
    return True

def etapa_telem(c):
    passo(3, "Telemetria do veículo")
    linha("PBT:", f"{c['pbt_kg']:,} kg".replace(",", "."))

    par = tempo_par(pos_veic(c))
    linha("Tempo parado agora:", fmt_dur(par))
    if par >= lim_ret:
        aviso(f"Veículo retido há {par} minutos (possível congestionamento).")
    else:
        ok("Sem retenção.")
    return par

def etapa_rota_func(c, par_min):
    passo(4, "Rota, restrições e jornada")
    aprov = True

    rota = consult_rota(c["origem"], c["destino"])
    if rota:
        ok("Rota calculada pela Google Routes API.")
        base_m = int(rota["dur_min"] * f_cam)
        linha("Distância:", f"{rota['dist_km']:.0f} km")
    else:
        aviso("Usando tempo de viagem fixo (sem API ou falha na chave).")
        base_m = c["fallback_min"]

    linha("Origem:", c["orig_txt"])
    linha("Destino:", c["dest_txt"])
    linha("Tempo de percurso:", fmt_dur(base_m))

    if rota and rota["pedagio"]:
        moeda, val = rota["pedagio"]
        linha("Pedágio (carro):", f"{moeda} {val:.2f}")
        linha(f"Pedágio ({eixos} eixos, aprox.):", f"{moeda} {val * eixos:.2f}")

    total = base_m + par_min
    cheg = c["agora"] + timedelta(minutes=total)
    linha("Chegada prevista:", cheg.strftime("%d/%m/%Y %H:%M"))

    if passa_restr(cheg, c["pbt_kg"]):
        falha(f"Passagem às {cheg.strftime('%H:%M')} cai na restrição de caminhões.")
        aprov = False

    if cheg.time() < c["fab_abre"]:
        aviso("Chegada antes da abertura da fábrica.")
    elif cheg.time() > c["fab_fecha"]:
        falha("Chegada depois do fechamento da fábrica.")
        aprov = False
    else:
        ok("Chegada dentro da janela da fábrica.")

    proj = c["h_jornada"] * 60 + total
    if proj > jorn_max:
        exc = proj - jorn_max
        falha(f"Jornada passa do limite em {fmt_dur(exc)}.")
        aprov = False
    else:
        ok(f"Jornada dentro do limite (sobram {fmt_dur(jorn_max - proj)}).")

    return aprov

def montar_cenario(nome):
    c = {
        "descricao": "Viagem regular",
        "agora": datetime(2026, 9, 29, 10, 0),
        "placa": "ABC1D23",
        "pbt_kg": 45000,
        "motorista": "Carlos Eduardo Menezes",
        "origem": (-23.9600, -46.3300),
        "destino": (-22.7397, -47.6476),
        "orig_txt": "Terminal de Contêineres, Santos/SP",
        "dest_txt": "Fábrica, Piracicaba/SP",
        "status_sefaz": "100",
        "h_desc": 12,
        "h_jornada": 2,
        "m_parado": 30,
        "fab_abre": time(6, 0),
        "fab_fecha": time(18, 0),
        "fallback_min": 240,
    }

    if nome == "sem_descanso":
        c["descricao"] = "Motorista com pouco descanso"
        c["h_desc"] = 8
    elif nome == "mdfe_cancelado":
        c["descricao"] = "MDF-e cancelado na SEFAZ"
        c["status_sefaz"] = "101"
    elif nome == "jornada_estourada":
        c["descricao"] = "Motorista já rodou quase a jornada toda"
        c["h_jornada"] = 9
    elif nome != "liberada":
        return None

    c["chave"] = gera_chave(35, "2609", "12345678000195", 1, 1001, 40000001)
    return c

def main():
    nome = sys.argv[1] if len(sys.argv) > 1 else "liberada"
    c = montar_cenario(nome)
    if c is None:
        print("Cenário inválido. Use: liberada, sem_descanso, mdfe_cancelado ou jornada_estourada")
        return 1

    print(f"\n=== VALIDAÇÃO DE VIAGEM: {c['descricao'].upper()} ===")
    linha("Data/hora:", c["agora"].strftime("%d/%m/%Y %H:%M"))
    if not api_key:
        aviso("GOOGLE_MAPS_API_KEY não definida. A usar tempo de fallback.")

    lib = False
    if etapa_mdfe(c) and etapa_desc(c):
        par = etapa_telem(c)
        lib = etapa_rota_func(c, par)

    print()
    if lib:
        print(">> STATUS: VIAGEM LIBERADA\n")
    else:
        print(">> STATUS: VIAGEM BLOQUEADA\n")
    
    return 0 if lib else 1

if __name__ == "__main__":
    sys.exit(main())
