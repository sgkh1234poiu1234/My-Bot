import time
import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

API_KEY = 'ocRWtLBHxNzXqTtbit0QFMAdleha0Q0vkvnnVJ35B6eNLqemQqyc4c9bVJvKlnkZ'
API_SECRET = 'LCwMnG9MiaRleZdgMPFP5n0qLqjnhfU6E7Y2oOSXeJlge6CAYHITTIqcZgIX4tMb'

client = Client(API_KEY, API_SECRET)

ROUND_DURATION = 0.01  # مدة الجولة بالثواني
MAX_COINS_FOR_FILTER = 300  # عدد العملات الصاعدة المرشحة بعد الفلترة
MAX_COINS = 10  # عدد العملات المختارة للتداول

MAX_RETRIES = 5  # محاولات إعادة التنفيذ قبل التوقف
RETRY_DELAY = 1  # فترة الانتظار بين المحاولات بالثواني

MIN_TRADE_AMOUNT = {}  # سيتم تعبئتها بالحد الأدنى للكمية لكل عملة من API

def retry_on_exception(func, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    attempt = 0
    while attempt < retries:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"خطأ في {func.__name__}: {e}")
            attempt += 1
            time.sleep(delay)
    print(f"فشل {retries} محاولات في {func.__name__}")
    return None

def get_min_trade_amount(symbol):
    # جلب الحد الأدنى لكمية الطلب من معلومات السوق لكل زوج عملات
    info = retry_on_exception(client.get_symbol_info, symbol)
    if info:
        for filt in info['filters']:
            if filt['filterType'] == 'LOT_SIZE':
                return float(filt['minQty'])
    return 0.0

def init_min_trade_amount():
    exchange_info = retry_on_exception(client.get_exchange_info)
    if exchange_info:
        for symbol_info in exchange_info['symbols']:
            symbol = symbol_info['symbol']
            MIN_TRADE_AMOUNT[symbol] = get_min_trade_amount(symbol)

def get_all_prices():
    prices = retry_on_exception(client.get_all_tickers)
    if prices:
        return {item['symbol']: float(item['price']) for item in prices}
    return {}

def get_balance():
    account = retry_on_exception(client.get_account)
    if account:
        balances = account['balances']
        return {b['asset']: float(b['free']) for b in balances if float(b['free']) > 0}
    return {}

def get_top_300_upcoins(prices_start, prices_now):
    upcoins = []
    for symbol, start_price in prices_start.items():
        if symbol.endswith('USDT'):
            current_price = prices_now.get(symbol, 0)
            if current_price > start_price:
                upcoins.append((symbol, current_price, start_price))
    upcoins.sort(key=lambda x: (x[1]-x[2])/x[2], reverse=True)  # ترتيب حسب نسبة الصعود
    return upcoins[:MAX_COINS_FOR_FILTER]

def filter_min_trade_amount(upcoins):
    filtered = []
    balance = get_balance()
    usdt_balance = balance.get('USDT', 0)
    portion_per_coin = usdt_balance / MAX_COINS if MAX_COINS > 0 else 0
    for coin in upcoins:
        symbol = coin[0]
        min_qty = MIN_TRADE_AMOUNT.get(symbol, 0)
        price = coin[1]
        qty = portion_per_coin / price if price > 0 else 0
        if qty >= min_qty:
            filtered.append(coin)
    return filtered[:MAX_COINS]

def place_order(symbol, side, quantity):
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        print(f"تم تنفيذ {side} على {symbol} بكمية {quantity}")
        return order
    except BinanceAPIException as e:
        print(f"خطأ في تنفيذ الأمر على {symbol}: {e}")
        return None

def trading_round():
    prices_start = get_all_prices()
    time.sleep(ROUND_DURATION)
    prices_end = get_all_prices()

    upcoins = get_top_300_upcoins(prices_start, prices_end)
    filtered_coins = filter_min_trade_amount(upcoins)
    balance = get_balance()
    usdt_balance = balance.get('USDT', 0)
    portion_per_coin = usdt_balance / MAX_COINS if MAX_COINS > 0 else 0

    # شراء بداية الجولة
    for coin in filtered_coins:
        symbol = coin[0]
        price = coin[1]
        qty = portion_per_coin / price if price > 0 else 0
        qty = max(qty, MIN_TRADE_AMOUNT.get(symbol, 0))
        place_order(symbol, 'BUY', qty)

    time.sleep(ROUND_DURATION)

    # إغلاق نهاية الجولة (بيع)
    for coin in filtered_coins:
        symbol = coin[0]
        balance = get_balance()
        asset = symbol.replace('USDT', '')
        qty = balance.get(asset, 0)
        if qty > 0:
            place_order(symbol, 'SELL', qty)

def main():
    init_min_trade_amount()
    print("بدأ التداول الآلي.")
    while True:
        trading_round()

if __name__ == "__main__":
    main()
