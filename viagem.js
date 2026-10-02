const process = require('process');

let apiKey = process.env.GOOGLE_MAPS_API_KEY || "";
const urlRotas = "https://routes.googleapis.com/directions/v2:computeRoutes";

const descMin = 11 * 60;
const jornMax = 10 * 60;
const velParado = 5;
const limRet = 30;
const fCam = 1.2;
const eixos = 5;

const stSefaz = {
    "100": "Autorizado o uso do MDF-e",
    "101": "Cancelamento de MDF-e homologado",
    "110": "Uso denegado",
    "132": "Encerramento de MDF-e homologado",
    "217": "MDF-e não consta na base de dados da SEFAZ",
};

const zonaUrb = {
    dias: [1, 2, 3, 4, 5], 
    janelas: [
        { ini: { h: 5, m: 0 }, fim: { h: 9, m: 0 } },
        { ini: { h: 17, m: 0 }, fim: { h: 21, m: 0 } }
    ],
    pbtMin: 10000,
};

function passo(n, tit) {
    console.log(`\n[ETAPA ${n}] ${tit}`);
}

function linha(rot, val) {
    console.log(`  ${rot.padEnd(28, ' ')}${val}`);
}

function ok(msg) {
    console.log(`  [OK] ${msg}`);
}

function falha(msg) {
    console.log(`  [FALHA] ${msg}`);
}

function aviso(msg) {
    console.log(`  [AVISO] ${msg}`);
}

function fmtDur(mins) {
    const h = Math.floor(mins / 60);
    const r = Math.floor(mins % 60);
    return `${h}h${String(r).padStart(2, '0')}min`;
}

function calcDv(base) {
    let s = 0;
    let p = 2;
    for (let i = base.length - 1; i >= 0; i--) {
        s += parseInt(base[i]) * p;
        p = (p === 9) ? 2 : p + 1;
    }
    const rest = s % 11;
    return (rest === 0 || rest === 1) ? 0 : 11 - rest;
}

function geraChave(uf, aamm, cnpj, serie, num, cod) {
    const base = `${String(uf).padStart(2, '0')}${aamm}${cnpj}58${String(serie).padStart(3, '0')}${String(num).padStart(9, '0')}1${String(cod).padStart(8, '0')}`;
    return base + calcDv(base);
}

function valChave(ch) {
    if (ch.length !== 44 || !/^\d+$/.test(ch)) {
        return "A chave precisa ter 44 dígitos numéricos.";
    }
    if (ch.substring(20, 22) !== "58") {
        return "O modelo do documento não é 58 (MDF-e).";
    }
    if (parseInt(ch[43]) !== calcDv(ch.substring(0, 43))) {
        return "Dígito verificador inválido.";
    }
    return null;
}

function consultSefaz(c) {
    return c.status_sefaz;
}

function persDesc(c) {
    const fim = new Date(c.agora.getTime() - c.h_jornada * 3600000);
    const ini = new Date(fim.getTime() - c.h_desc * 3600000);
    return [[ini, fim]];
}

function posVeic(c) {
    const ag = c.agora;
    const par = c.m_parado;
    const pos = [{ data: new Date(ag.getTime() - (par + 10) * 60000), vel: 80, ign: 1 }];
    for (let m = par; m >= 0; m -= 10) {
        pos.push({ data: new Date(ag.getTime() - m * 60000), vel: 0, ign: 1 });
    }
    return pos;
}

function maiorDesc(pers) {
    let blocos = [];
    pers.sort((a, b) => a[0] - b[0]);
    for (let [ini, fim] of pers) {
        if (blocos.length > 0 && ini <= blocos[blocos.length - 1][1]) {
            blocos[blocos.length - 1][1] = new Date(Math.max(blocos[blocos.length - 1][1].getTime(), fim.getTime()));
        } else {
            blocos.push([ini, fim]);
        }
    }
    if (blocos.length === 0) return 0;
    const [ini, fim] = blocos[blocos.length - 1];
    return Math.floor((fim - ini) / 60000);
}

function tempoPar(pos) {
    let ini = null;
    for (let i = pos.length - 1; i >= 0; i--) {
        if (pos[i].vel <= velParado && pos[i].ign === 1) {
            ini = pos[i].data;
        } else {
            break;
        }
    }
    if (ini === null) return 0;
    return Math.floor((pos[pos.length - 1].data - ini) / 60000);
}

async function consultRota(orig, dest) {
    if (!apiKey) return null;

    const corpo = {
        origin: { location: { latLng: { latitude: orig[0], longitude: orig[1] } } },
        destination: { location: { latLng: { latitude: dest[0], longitude: dest[1] } } },
        travelMode: "DRIVE",
        routingPreference: "TRAFFIC_AWARE",
        extraComputations: ["TOLLS"],
        routeModifiers: { vehicleInfo: { emissionType: "DIESEL" } },
    };
    const cab = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": apiKey,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.travelAdvisory.tollInfo",
    };

    try {
        const resp = await fetch(urlRotas, {
            method: "POST",
            headers: cab,
            body: JSON.stringify(corpo)
        });
        if (!resp.ok) throw new Error(`HTTP error! status: ${resp.status}`);
        const data = await resp.json();
        const rotas = data.routes;
        if (!rotas || rotas.length === 0) {
            aviso("A Routes API não retornou nenhuma rota.");
            return null;
        }

        const rota = rotas[0];
        const segs = parseInt(rota.duration.replace("s", ""));

        let ped = null;
        const info = rota.travelAdvisory?.tollInfo;
        if (info && info.estimatedPrice) {
            const preco = info.estimatedPrice[0];
            const val = parseFloat(preco.units || "0") + (preco.nanos || 0) / 1e9;
            ped = [preco.currencyCode, val];
        }

        return {
            dist_km: (rota.distanceMeters || 0) / 1000,
            dur_min: Math.floor(segs / 60),
            pedagio: ped,
        };
    } catch (e) {
        aviso(`Erro na Routes API: ${e.message}`);
        return null;
    }
}

function passaRestr(cheg, pbt) {
    if (pbt < zonaUrb.pbtMin) return false;
    const diaSemana = cheg.getDay(); 
    if (!zonaUrb.dias.includes(diaSemana)) return false;

    const hCheg = cheg.getHours();
    const mCheg = cheg.getMinutes();
    const totalMinCheg = hCheg * 60 + mCheg;

    for (let j of zonaUrb.janelas) {
        const iniMin = j.ini.h * 60 + j.ini.m;
        const fimMin = j.fim.h * 60 + j.fim.m;
        if (totalMinCheg >= iniMin && totalMinCheg < fimMin) {
            return true;
        }
    }
    return false;
}

function etapaMdfe(c) {
    passo(1, "Validação do MDF-e");
    linha("Placa:", c.placa);
    linha("Chave de acesso:", c.chave);

    const err = valChave(c.chave);
    if (err) {
        falha(err);
        return false;
    }
    ok("Estrutura e dígito verificador da chave estão certos.");

    const cod = consultSefaz(c);
    linha("Retorno da SEFAZ:", `${cod} - ${stSefaz[cod] || 'desconhecido'}`);
    if (cod !== "100") {
        falha("MDF-e sem autorização de uso.");
        return false;
    }
    ok("Manifesto autorizado.");
    return true;
}

function etapaDesc(c) {
    passo(2, "Descanso do motorista");
    linha("Motorista:", c.motorista);

    const dur = maiorDesc(persDesc(c));
    linha("Descanso apurado:", fmtDur(dur));
    if (dur < descMin) {
        const alta = descMin - dur;
        falha(`Descanso insuficiente, faltam ${fmtDur(alta)}.`);
        return false;
    }
    ok("Descanso mínimo cumprido.");
    return true;
}

function etapaTelem(c) {
    passo(3, "Telemetria do veículo");
    linha("PBT:", `${c.pbt_kg.toLocaleString('de-DE')} kg`);

    const par = tempoPar(posVeic(c));
    linha("Tempo parado agora:", fmtDur(par));
    if (par >= limRet) {
        aviso(`Veículo retido há ${par} minutos (possível congestionamento).`);
    } else {
        ok("Sem retenção.");
    }
    return par;
}

async function etapaRotaFunc(c, parMin) {
    passo(4, "Rota, restrições e jornada");
    let aprov = true;

    const rota = await consultRota(c.origem, c.destino);
    let baseM;
    if (rota) {
        ok("Rota calculada pela Google Routes API.");
        baseM = Math.floor(rota.dur_min * fCam);
        linha("Distância:", `${rota.dist_km.toFixed(0)} km`);
    } else {
        aviso("Usando tempo de viagem fixo (sem API ou falha na chave).");
        baseM = c.fallback_min;
    }

    linha("Origem:", c.orig_txt);
    linha("Destino:", c.dest_txt);
    linha("Tempo de percurso:", fmtDur(baseM));

    if (rota && rota.pedagio) {
        const [moeda, val] = rota.pedagio;
        linha("Pedágio (carro):", `${moeda} ${val.toFixed(2)}`);
        linha(`Pedágio (${eixos} eixos, aprox.):`, `${moeda} ${(val * eixos).toFixed(2)}`);
    }

    const total = baseM + parMin;
    const cheg = new Date(c.agora.getTime() + total * 60000);
    
    const dia = String(cheg.getDate()).padStart(2, '0');
    const mes = String(cheg.getMonth() + 1).padStart(2, '0');
    const ano = cheg.getFullYear();
    const hora = String(cheg.getHours()).padStart(2, '0');
    const min = String(cheg.getMinutes()).padStart(2, '0');
    linha("Chegada prevista:", `${dia}/${mes}/${ano} ${hora}:${min}`);

    if (passaRestr(cheg, c.pbt_kg)) {
        falha(`Passagem às ${hora}:${min} cai na restrição de caminhões.`);
        aprov = false;
    }

    const hChegTime = cheg.getHours() * 60 + cheg.getMinutes();
    const abreTime = c.fab_abre.h * 60 + c.fab_abre.m;
    const fechaTime = c.fab_fecha.h * 60 + c.fab_fecha.m;

    if (hChegTime < abreTime) {
        aviso("Chegada antes da abertura da fábrica.");
    } else if (hChegTime > fechaTime) {
        falha("Chegada depois do fechamento da fábrica.");
        aprov = false;
    } else {
        ok("Chegada dentro da janela da fábrica.");
    }

    const proj = c.h_jornada * 60 + total;
    if (proj > jornMax) {
        const exc = proj - jornMax;
        falha(`Jornada passa do limite em ${fmtDur(exc)}.`);
        aprov = false;
    } else {
        ok(`Jornada dentro do limite (sobram ${fmtDur(jornMax - proj)}).`);
    }

    return aprov;
}

function montarCenario(nome) {
    let c = {
        descricao: "Viagem regular",
        agora: new Date(2026, 8, 29, 10, 0), 
        placa: "ABC1D23",
        pbt_kg: 45000,
        motorista: "Carlos Eduardo Menezes",
        origem: [-23.9600, -46.3300],
        destino: [-22.7397, -47.6476],
        orig_txt: "Terminal de Contêineres, Santos/SP",
        dest_txt: "Fábrica, Piracicaba/SP",
        status_sefaz: "100",
        h_desc: 12,
        h_jornada: 2,
        m_parado: 30,
        fab_abre: { h: 6, m: 0 },
        fab_fecha: { h: 18, m: 0 },
        fallback_min: 240,
    };

    if (nome === "sem_descanso") {
        c.descricao = "Motorista com pouco descanso";
        c.h_desc = 8;
    } else if (nome === "mdfe_cancelado") {
        c.descricao = "MDF-e cancelado na SEFAZ";
        c.status_sefaz = "101";
    } else if (nome === "jornada_estourada") {
        c.descricao = "Motorista já rodou quase a jornada toda";
        c.h_jornada = 9;
    } else if (nome !== "liberada") {
        return null;
    }

    c.chave = geraChave(35, "2609", "12345678000195", 1, 1001, 40000001);
    return c;
}

async function main() {
    const args = process.argv.slice(2);
    const nome = args.length > 0 ? args[0] : "liberada";
    const c = montarCenario(nome);
    
    if (!c) {
        console.log("Cenário inválido. Use: liberada, sem_descanso, mdfe_cancelado ou jornada_estourada");
        process.exit(1);
    }

    console.log(`\n=== VALIDAÇÃO DE VIAGEM: ${c.descricao.toUpperCase()} ===`);
    const dia = String(c.agora.getDate()).padStart(2, '0');
    const mes = String(c.agora.getMonth() + 1).padStart(2, '0');
    const ano = c.agora.getFullYear();
    const hora = String(c.agora.getHours()).padStart(2, '0');
    const min = String(c.agora.getMinutes()).padStart(2, '0');
    linha("Data/hora:", `${dia}/${mes}/${ano} ${hora}:${min}`);

    if (!apiKey) {
        aviso("GOOGLE_MAPS_API_KEY não definida. A usar tempo de fallback.");
    }

    let lib = false;
    if (etapaMdfe(c) && etapaDesc(c)) {
        const par = etapaTelem(c);
        lib = await etapaRotaFunc(c, par);
    }

    console.log();
    if (lib) {
        console.log(">> STATUS: VIAGEM LIBERADA\n");
    } else {
        console.log(">> STATUS: VIAGEM BLOQUEADA\n");
    }

    process.exit(lib ? 0 : 1);
}

main();
