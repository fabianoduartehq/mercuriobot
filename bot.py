import os
import json
import random
from datetime import datetime, timedelta
import zoneinfo
import numpy as np
from skyfield.api import load
from atproto import Client

def load_messages():
    """Carrega o arquivo JSON de mensagens externas."""
    with open('messages.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def pick_message(msg_data):
    """Retorna uma mensagem (se for lista, escolhe uma aleatória)."""
    if isinstance(msg_data, list):
        return random.choice(msg_data)
    return msg_data

def get_full_mercury_periods(years: list):
    """
    Calcula os períodos completos de Mercúrio (pré-sombra, retrógrado, pós-sombra)
    para uma lista de anos usando Skyfield + DE421.

    Retorna uma lista de dicionários com:
      - pre_shadow_start : date  (início da Zona de Sombra Pré-Retrógrada)
      - retro_start      : date  (estação retrógrada — início do retrógrado pleno)
      - retro_end        : date  (estação direta — fim do retrógrado pleno)
      - post_shadow_end  : date  (fim da Zona de Sombra Pós-Retrógrada)

    Conceito astronômico das Zonas de Sombra:
      PRÉ-SOMBRA:  Mercúrio avança pelo segmento do zodíaco que vai percorrer ao
                   contrário durante o retrógrado. Começa quando cruza o grau
                   exato da estação direta (fim do retrógrado) e termina na
                   estação retrógrada (início do retrógrado pleno).
      PÓS-SOMBRA:  Após o retrógrado, Mercúrio retoma o avanço e precisa
                   "reconquistar" os graus percorridos ao contrário. Começa na
                   estação direta e termina quando ultrapassa o grau exato da
                   estação retrógrada (início do retrógrado).
    """
    planets = load('de421.bsp')
    earth   = planets['earth']
    mercury = planets['mercury']
    ts      = load.timescale()

    # Janela de varredura: ano_min-1 até ano_max+1 para capturar sombras que
    # transbordam para anos adjacentes
    min_year = min(years)
    max_year = max(years)
    scan_start = datetime(min_year - 1, 1, 1)
    total_days = (max_year - min_year + 3) * 366 + 5
    dates = [scan_start + timedelta(days=i) for i in range(total_days)]
    t = ts.utc(
        [d.year  for d in dates],
        [d.month for d in dates],
        [d.day   for d in dates],
    )

    _, eclon, _ = earth.at(t).observe(mercury).apparent().ecliptic_latlon()
    eclon_deg = eclon.degrees  # 0..360

    # Diferença diária de longitude eclíptica (positivo = direto, negativo = retrógrado)
    diff = np.diff(eclon_deg)
    diff[diff < -300] += 360   # corrige salto na fronteira 360°/0°
    diff[diff > 300]  -= 360

    is_retro = diff < 0

    # ── Detecta períodos retrógrados ──────────────────────────────────────────
    raw_periods = []
    in_retro    = False
    r_start_idx = None

    for i, retro in enumerate(is_retro):
        if retro and not in_retro:
            in_retro    = True
            r_start_idx = i
        elif not retro and in_retro:
            in_retro = False
            raw_periods.append((r_start_idx, i))

    # ── Calcula as sombras para cada período retrógrado ───────────────────────
    result = []
    for r_start_idx, r_end_idx in raw_periods:
        retro_start = dates[r_start_idx].date()
        retro_end   = dates[r_end_idx].date()

        # Filtra apenas os anos solicitados
        if retro_start.year not in years and retro_end.year not in years:
            continue

        # Longitudes dos pontos de estação
        lon_retro_start = eclon_deg[r_start_idx]  # grau onde começa o retrógrado
        lon_retro_end   = eclon_deg[r_end_idx]    # grau onde termina (estação direta)

        # ── PRÉ-SOMBRA: varredura backward a partir de r_start_idx ───────────
        # Buscamos o dia (antes do retrógrado) em que Mercúrio cruzou
        # lon_retro_end indo para frente.
        pre_shadow_start = retro_start - timedelta(days=21)  # fallback conservador
        try:
            for i in range(r_start_idx - 1, max(0, r_start_idx - 90), -1):
                lon_i = eclon_deg[i]
                # Normaliza possíveis diferenças de wraparound
                delta = lon_retro_end - lon_i
                if delta > 180:
                    delta -= 360
                elif delta < -180:
                    delta += 360
                if delta >= 0:        # lon_i <= lon_retro_end: cruzou para baixo
                    pre_shadow_start = dates[i + 1].date()
                    break
        except Exception:
            pass  # mantém fallback

        # ── PÓS-SOMBRA: varredura forward a partir de r_end_idx ─────────────
        # Buscamos o dia (após o retrógrado) em que Mercúrio ultrapassou
        # lon_retro_start retomando o movimento direto.
        post_shadow_end = retro_end + timedelta(days=21)  # fallback conservador
        try:
            for i in range(r_end_idx, min(len(dates) - 1, r_end_idx + 90)):
                lon_i = eclon_deg[i]
                delta = lon_i - lon_retro_start
                if delta > 180:
                    delta -= 360
                elif delta < -180:
                    delta += 360
                if delta >= 0:        # lon_i >= lon_retro_start: reconquistou
                    post_shadow_end = dates[i].date()
                    break
        except Exception:
            pass  # mantém fallback

        result.append({
            'pre_shadow_start': pre_shadow_start,
            'retro_start'     : retro_start,
            'retro_end'       : retro_end,
            'post_shadow_end' : post_shadow_end,
        })

    return result


def determine_today_announcement(today_date):
    """
    Determina a mensagem do dia baseada na fase astronômica de Mercúrio.

    Hierarquia de prioridade (da maior para a menor):
      1. Dia 0 — Início do Retrógrado Pleno
      2. Contagem regressiva pré-retrógrado (10 → 1 dias)
      3. Dia 0 — Fim do Retrógrado Pleno (estação direta)
      4. Contagem regressiva de saída do retrógrado (7 → 1 dias)
      5. Retrógrado Pleno ativo (centro do período)
      6. Zona de Sombra Pós-Retrógrada
      7. Zona de Sombra Pré-Retrógrada
      8. Movimento Direto Pleno
    """
    messages = load_messages()
    # Carrega períodos do ano corrente e do próximo para cobrir virada de ano
    periods = get_full_mercury_periods([today_date.year, today_date.year + 1])

    for p in periods:
        pre_shadow_start = p['pre_shadow_start']
        retro_start      = p['retro_start']
        retro_end        = p['retro_end']
        post_shadow_end  = p['post_shadow_end']

        days_to_retro_start = (retro_start - today_date).days
        days_to_retro_end   = (retro_end   - today_date).days

        # 1. Dia 0: Entrada em Retrógrado
        if days_to_retro_start == 0:
            return pick_message(messages["retrograde_start_event"])

        # 2. Contagem Regressiva Pré-Retrógrado (10 a 1 dias antes)
        if 1 <= days_to_retro_start <= 10:
            default_header = "🚨 COMEÇA AMANHÃ:" if days_to_retro_start == 1 else f"⚠️ FALTAM {days_to_retro_start} DIAS:"
            header = messages.get("pre_retrograde_headers", {}).get(
                str(days_to_retro_start), default_header
            )
            phrase = pick_message(messages.get("pre_retrograde_phrases", []))
            return f"{header} {phrase}"

        # 3. Dia 0: Saída do Retrógrado (estação direta)
        if days_to_retro_end == 0:
            return pick_message(messages["retrograde_end_event"])

        # 4. Contagem Regressiva de Saída (0 a 7 dias antes do fim do retrógrado)
        # last_retro_day é a véspera da estação direta (o último dia do retrógrado)
        days_to_last_retro_day = (retro_end - timedelta(days=1) - today_date).days
        if 0 <= days_to_last_retro_day <= 7 and today_date >= retro_start:
            default_header = "🚨 TERMINA HOJE:" if days_to_last_retro_day == 0 else f"⏳ RESTAM {days_to_last_retro_day} DIAS:"
            header = messages.get("exit_retrograde_headers", {}).get(
                str(days_to_last_retro_day), default_header
            )
            phrase = pick_message(messages.get("exit_retrograde_phrases", []))
            return f"{header} {phrase}"

        # 5. Retrógrado Pleno (centro, fora das contagens)
        if retro_start < today_date < retro_end:
            return pick_message(messages["active_retrograde_daily"])

        # 6. Zona de Sombra Pós-Retrógrada
        if retro_end < today_date <= post_shadow_end:
            return pick_message(messages["post_retrograde_shadow_daily"])

        # 7. Zona de Sombra Pré-Retrógrada (antes da contagem de 10 dias)
        if pre_shadow_start <= today_date < retro_start and days_to_retro_start > 10:
            return pick_message(messages["pre_retrograde_shadow_daily"])

    # 8. Movimento Direto Pleno
    return pick_message(messages["direct_motion_daily"])


BSKY_POST_LIMIT = 300  # Limite de caracteres do Bluesky

def main():
    try:
        # Fuso horário configurável via variável TZ (padrão: America/Sao_Paulo)
        tz_name = os.environ.get("TZ", "America/Sao_Paulo")
        try:
            tz    = zoneinfo.ZoneInfo(tz_name)
            today = datetime.now(tz).date()
        except Exception:
            print(f"Aviso: Fuso horário '{tz_name}' inválido. Usando UTC.")
            today = datetime.now().date()

        handle   = os.environ.get("BSKY_HANDLE")
        password = os.environ.get("BSKY_PASSWORD")

        if not handle or not password:
            raise ValueError("Variáveis de ambiente BSKY_HANDLE e BSKY_PASSWORD são obrigatórias.")

        announcement = determine_today_announcement(today)

        # Valida o limite de 300 caracteres do Bluesky
        if len(announcement) > BSKY_POST_LIMIT:
            print(f"AVISO: Mensagem muito longa ({len(announcement)} chars). Truncando para {BSKY_POST_LIMIT}.")
            announcement = announcement[:BSKY_POST_LIMIT]

        client = Client()
        client.login(handle, password)

        # Prevenção de duplicatas baseada na DATA do último post enviado
        feed = client.get_author_feed(actor=handle, limit=1)
        if feed.feed:
            last_created_at = getattr(feed.feed[0].post.record, 'createdAt', '')
            if last_created_at:
                last_post_date = last_created_at.split('T')[0]
                if last_post_date == str(today):
                    print(f"Já foi publicado um post hoje ({today}). Pulando para evitar duplicatas.")
                    return

        client.send_post(announcement)
        print(f"Publicado com sucesso hoje ({today}): {announcement}")

    except ValueError as e:
        print(f"ERRO DE CONFIGURAÇÃO: {e}")
        raise
    except Exception as e:
        print(f"ERRO INESPERADO: {e}")
        raise

if __name__ == "__main__":
    main()
