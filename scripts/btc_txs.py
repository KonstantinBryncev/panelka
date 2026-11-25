import requests
from datetime import datetime, timezone, timedelta

def satoshi_to_btc(sat):
    return sat / 100_000_000

def get_btc_to_rub_rate():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=rub"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()['bitcoin']['rub']

def get_transactions(address):
    url = f"https://blockstream.info/api/address/{address}/txs"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def main():
    address = input("Вбиваем адрес: ").strip()
    print(f"Адрес для получения информации: {address}")

    txs = get_transactions(address)
    if not txs:
        print("Транзакций по адресу не найдено")
        return

    btc_to_rub = get_btc_to_rub_rate()

    moscow_tz = timezone(timedelta(hours=3))
    print("Последние две транзакции:")

    for tx in txs[:2]:
        block_time = tx["status"].get("block_time")
        if block_time:
            dt = datetime.fromtimestamp(block_time, moscow_tz)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S МСК")
        else:
            time_str = "Время не указано"

        confirmations = 0
        if tx["status"]["confirmed"]:
            # Кол-во подтверждений = текущий блок (по API) - блок с транзакцией +1
            current_block_resp = requests.get("https://blockstream.info/api/blocks/tip/height")
            current_block_resp.raise_for_status()
            current_block_height = int(current_block_resp.text)
            confirmations = current_block_height - tx["status"]["block_height"] + 1

        # Подсчёт входящих и исходящих сатоши с твоего адреса
        sent_sats = 0
        received_sats = 0

        # Адреса отправителей (vin)
        sender_addresses = set()
        for vin in tx.get("vin", []):
            prevout = vin.get("prevout")
            if prevout:
                sender_addr = prevout.get("scriptpubkey_address")
                if sender_addr:
                    sender_addresses.add(sender_addr)
                if sender_addr == address:
                    sent_sats += prevout["value"]

        # Адреса получателей (vout)
        recipient_addresses = set()
        for vout in tx.get("vout", []):
            addr = vout.get("scriptpubkey_address")
            if addr:
                recipient_addresses.add(addr)
            if addr == address:
                received_sats += vout["value"]

        net_sats = received_sats - sent_sats
        net_btc = satoshi_to_btc(net_sats)
        net_rub = net_btc * btc_to_rub

        # Определяем тип операции
        op_type = "Пополнение" if net_sats > 0 else "Списание"

        # Считаем адрес для взаимодействия — адреса, кроме твоего
        if op_type == "Пополнение":
            interacting_addresses = sender_addresses - {address}
        else:
            interacting_addresses = recipient_addresses - {address}

        # Для компактности выводим первые 3 адреса
        interacting_addresses = list(interacting_addresses)
        addresses_display = ", ".join(interacting_addresses[:3]) if interacting_addresses else "Неизвестно"

        print(f"Время: {time_str}")
        print(f"Тип операции: {op_type}")
        print(f"Сумма: {abs(net_btc):.8f} BTC / {abs(net_rub):.2f} ₽")
        print(f"Подтверждений: {confirmations}")
        print(f"Кошелёк(и) взаимодействия: {addresses_display}")
        print("-" * 50)

if __name__ == "__main__":
    main()