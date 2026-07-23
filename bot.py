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

def get_retrograde_periods(year: int):
    """Calcula todos os períodos retrógrados de Mercúrio para um determinado ano usando Skyfield + DE421."""
    planets = load('de421.bsp')
    earth = planets['earth']
    mercury = planets['mercury']
    ts = load.timescale()
    
    start_date = datetime(year, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(367)]
    t = ts.utc([d.year for d in dates], [d.month for d in dates], [d.day for d in dates])
    
    _, eclon, _ = earth.at(t).observe(mercury).apparent().ecliptic_latlon()
    eclon_degrees = eclon.degrees
    
    diff = np.diff(eclon_degrees)
    diff[diff < -300] += 360
    diff[diff > 300] -= 360
    
    is_retrograde = diff < 0
    
    periods = []
    in_retrograde = False
    p_start = None
    
    for i, retrograde in enumerate(is_retrograde):
        current_day = dates[i].date()
        if retrograde and not in_retrograde:
            in_retrograde = True
            p_start = current_day
        elif not retrograde and in_retrograde:
            in_retrograde = False
            periods.append((p_start, current_day))
            
    if in_retrograde:
        periods.append((p_start, dates[-1].date()))
        
    return periods

def determine_today_announcement(today_date):
    """Determina a mensagem baseada no arquivo messages.json juntando cabeçalho + frase aleatória."""
    messages = load_messages()
    periods = get_retrograde_periods(today_date.year) + get_retrograde_periods(today_date.year + 1)
    
    for start_date, end_date in periods:
        days_to_start = (start_date - today_date).days
        days_to_end = (end_date - today_date).days
        
        # 1. Dia 0: Entra em Retrógrado (Caos Total!)
        if days_to_start == 0:
            return pick_message(messages["retrograde_start_event"])
            
        # 2. Contagem Regressiva Pré-Retrógrado (10 a 1 dias)
        if 1 <= days_to_start <= 10:
            header = messages.get("pre_retrograde_headers", {}).get(str(days_to_start), f"⚠️ FALTAM {days_to_start} DIAS:")
            phrase = pick_message(messages.get("pre_retrograde_phrases", []))
            return f"{header} {phrase}"
            
        # 3. Dia 0: Sai de Retrógrado (Euforia!)
        if days_to_end == 0:
            return pick_message(messages["retrograde_end_event"])
            
        # 4. Contagem Regressiva para Sair do Retrógrado (7 a 1 dias)
        if 1 <= days_to_end <= 7 and today_date >= start_date:
            header = messages.get("exit_retrograde_headers", {}).get(str(days_to_end), f"⏳ RESTAM {days_to_end} DIAS:")
            phrase = pick_message(messages.get("exit_retrograde_phrases", []))
            return f"{header} {phrase}"

    # Se não houver evento ou contagem ativa:
    is_currently_retrograde = False
    for start_date, end_date in periods:
        if start_date <= today_date < end_date:
            is_currently_retrograde = True
            break
            
    if is_currently_retrograde:
        return pick_message(messages["active_retrograde_daily"])
    else:
        return pick_message(messages["direct_motion_daily"])

BSKY_POST_LIMIT = 300  # Limite de caracteres do Bluesky

def main():
    try:
        # Fuso horário configurável via variável TZ (padrão: America/Sao_Paulo)
        tz_name = os.environ.get("TZ", "America/Sao_Paulo")
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            today = datetime.now(tz).date()
        except Exception:
            print(f"Aviso: Fuso horário '{tz_name}' inválido. Usando UTC.")
            today = datetime.now().date()

        handle = os.environ.get("BSKY_HANDLE")
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
