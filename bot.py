import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from prettytable import PrettyTable
from datetime import datetime

# === CONFIGURAÇÃO ===
BITUNIX_PAIRS_URL = "https://fapi.bitunix.com/api/v1/futures/market/trading_pairs"
BITUNIX_FUNDING_URL = "https://fapi.bitunix.com/api/v1/futures/market/funding_rate?symbol={}"
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol={}"

# Configuração do Telegram
TELEGRAM_TOKEN = "7675636483:AAHmLQZuawOwO2jKFYZURMZH_7v2pTYOTNw"
TELEGRAM_CHAT_ID = "-4892041521"

session_bitunix = requests.Session()
session_binance = requests.Session()

TIMEOUT = 10

# Códigos de cor ANSI
AMARELO = "\033[93m"
AZUL = "\033[94m"
RESET = "\033[0m"

moedas_ordenadas = []


def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"❌ Erro ao enviar para Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Exceção ao enviar para Telegram: {e}")


def obter_pares_bitunix():
    try:
        response = session_bitunix.get(BITUNIX_PAIRS_URL, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("code") == 0:
            return [item["symbol"] for item in data.get("data", []) if "symbol" in item]
    except Exception as e:
        print("❌ Erro ao buscar pares Bitunix:", e)
    return []


def obter_funding_bitunix(symbol):
    try:
        url = BITUNIX_FUNDING_URL.format(symbol)
        response = session_bitunix.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if (
            isinstance(data, dict)
            and data.get("code") == 0
            and data.get("data", {}).get("fundingRate") is not None
        ):
            return float(data["data"]["fundingRate"])
    except:
        pass
    return None


def obter_funding_binance(symbol):
    try:
        url = BINANCE_FUNDING_URL.format(symbol)
        response = session_binance.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("lastFundingRate") is not None:
            funding = float(data["lastFundingRate"]) * 100

            next_funding_time = data.get("nextFundingTime")
            if next_funding_time:
                next_funding_dt = datetime.fromtimestamp(next_funding_time / 1000)
                agora = datetime.now()
                diff = next_funding_dt - agora

                if diff.total_seconds() < 0:
                    tempo_restante = "Agora"
                else:
                    horas, resto = divmod(diff.total_seconds(), 3600)
                    minutos, _ = divmod(resto, 60)
                    tempo_restante = f"em {int(horas)}h {int(minutos)}min"

                next_funding_str = next_funding_dt.strftime('%H:%M:%S')
                info_funding = f"{next_funding_str} ({tempo_restante})"
            else:
                info_funding = "N/A"

            return funding, info_funding
    except:
        pass
    return None, None


def gerar_link_historico_binance(symbol):
    return "https://www.binance.com/en/futures/funding-history/perpetual/funding-fee-history"


def gerar_link_bitunix(symbol):
    return f"https://www.bitunix.com/pt-br/contract-trade/{symbol}/fund-fee"


def comparar_funding(symbol):
    try:
        funding_bitunix = obter_funding_bitunix(symbol)
        funding_binance, horario_funding = obter_funding_binance(symbol)

        if funding_bitunix is not None and funding_binance is not None:
            diff = abs(funding_binance - funding_bitunix)
            if diff >= 0.02:
                return (symbol, funding_bitunix, funding_binance, diff, horario_funding)
    except:
        pass
    return None


def main():
    global moedas_ordenadas
    print("🔍 Buscando pares disponíveis na Bitunix...")
    pares_bitunix = obter_pares_bitunix()
    print(f"✅ {len(pares_bitunix)} pares encontrados.\n")

    print("🔁 Comparando taxas de funding com a Binance (diferença >= 0.02%):\n")
    resultados = []

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(comparar_funding, symbol) for symbol in pares_bitunix]
        for future in as_completed(futures):
            resultado = future.result()
            if resultado:
                resultados.append(resultado)

    if resultados:
        tabela = PrettyTable()
        tabela.field_names = ["#", "Moeda", "Bitunix (%)", "Binance (%)", "Diferença (%)", "Próx. Funding Binance"]

        moedas_ordenadas = []

        mensagem_telegram = "<b>🤑 Oportunidades de Funding Detectadas:</b>\n\n"

        for i, (symbol, fund_btx, fund_bnb, diff, horario_funding) in enumerate(
            sorted(resultados, key=lambda x: x[3], reverse=True), start=1
        ):
            tabela.add_row([
                i,
                f"{AMARELO}{symbol}{RESET}",
                f"{fund_btx:.6f}",
                f"{fund_bnb:.6f}",
                f"{AZUL}{diff:.6f}{RESET}",
                horario_funding
            ])

            moedas_ordenadas.append(symbol)

            link_binance = gerar_link_historico_binance(symbol)
            link_bitunix = gerar_link_bitunix(symbol)

            mensagem_telegram += (
                f"#{i} - <b>{symbol}</b>\n"
                f"Bitunix: {fund_btx:.6f}% | Binance: {fund_bnb:.6f}%\n"
                f"💰 Diferença: <b>{diff:.6f}%</b>\n"
                f"⏰ Próx. Funding Binance: {horario_funding}\n"
                f"🔗 <a href='{link_bitunix}'>Bitunix</a> | <a href='{link_binance}'>Binance Histórico</a>\n\n"
            )

        print(tabela)
        enviar_telegram(mensagem_telegram)
        print("\n🚀 Sinais enviados para o Telegram.")

    else:
        moedas_ordenadas = []
        aviso = "⚠️ Nenhuma arbitragem acima de 0.02% foi detectada."
        print(aviso)
        enviar_telegram(aviso)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
        print("\n⏳ Aguardando 5 minutos para próxima checagem...\n")
        time.sleep(300)
