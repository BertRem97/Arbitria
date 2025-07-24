import argparse
import sys
import json
import asyncio
import importlib
import os.path
import time
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes, Job, CallbackContext, MessageHandler, filters, ContextTypes
from python_bitvavo_api.bitvavo import Bitvavo


parser = argparse.ArgumentParser()
parser.add_argument('--run', action='store_true')
parser.add_argument('--backtest', action='store_true')
args = parser.parse_args()

config = r"C:\Users\User\AppData\Local\Programs\Python\Python311\userconfig.json"
operator_id = 854251

if os.path.exists(config):
    with open(config, "r") as f:
        data = json.load(f)
        strategy_path = data['strategy']
        markets = data['Markets']
        timeframe = data['Tijdsframe']
        take_profit = data['Take-profit']
        stop_loss = data['Stop-loss']
        eur_per_trade = data['Bedrag per trade']
        chat_id = data['Telegram chat ID']
        api_key = data['Api-key']
        token = data['Telegram token']
        api_secret = data['Api-secret']

bitvavo = Bitvavo({
    'APIKEY': api_key,
    'APISECRET': api_secret,
    'RESTURL': "https://api.bitvavo.com/v2",
    'WSURL': "wss://ws.bitvavo.com/v2/",
})

module_naam = os.path.splitext(os.path.basename(strategy_path))[0]  # bijv. 'Arbitria_StrategyMA'
spec = importlib.util.spec_from_file_location(module_naam, strategy_path)
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)

# Nu kun je functies gebruiken die in dat script staan
strategy = strategy_module.Strategy(configfile=config)
writebuyorder = {}
bot = telegram.Bot(token=token)
orderbook_path = r"C:\Users\User\AppData\Local\Programs\Python\Python311\orderbook.json"


async def timeout_sessie(chat_id):
    try:
        await asyncio.sleep(900)  # 15 minuten
        await self._bot.send_message(chat_id=chat_id, text="⏰ Tijd is verstreken. Order niet meer uitvoerbaar.")
        sys.exit()  # Hele programma stoppen
    except asyncio.CancelledError:
        pass


def maak_knoppen():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ja", callback_data="ja")],
        [InlineKeyboardButton("Neen", callback_data="nee")]
    ])

async def place_market_order(market=None, amount=None, side=None):
    if strategy._placesellorders:
        for order in strategy._placesellorders:
            for k, v in order.items():
                market = k
                id = v['Id']
                amount = v['amount']
                initial_price = float(v['buyprice'])
                selling_price = float(v['selling_price'])
                profit = round(selling_price-initial_price,3)
                cancel_order = bitvavo.cancelOrder(market, id, operator_id)
                sell_order = bitvavo.placeOrder(market, "sell", "market", {'amount': amount, 'operatorId': operator_id})
                if 'error' in cancel_order:
                    error_message = f"Fout bij annuleren van stoploss order: {id}"
                    await bot.send_message(chat_id=chat_id, text=error_message)

                if 'error' in sell_order:
                    error_message = f"Fout bij het verkopen van: {market}\n" \
                                    f"Hoeveelheid: {amount}"
                    await bot.send_message(chat_id=chat_id, text=error_message)

                else:
                    success_message = f"Verkoop order: {market} succesvol\n" \
                                      f"€{profit} winst!"
                    await bot.send_message(chat_id=chat_id, text=success_message)

    if market and amount and side:
        order = bitvavo.placeOrder(market, "buy", 'market', {'amount': amount})
        writebuyorder = {"market": market, "amount": order["fills"][0]["amount"], "price": order["fills"][0]["price"]}

        if 'error' in order:
            error_message = f"Fout bij plaatsen koop order: {order['error']}"
            await bot.send_message(chat_id=chat_id, text=error_message)

        else:
            success_message = "Kooporder succesvol!"
            await bot.send_message(chat_id=chat_id, text=success_message)
            await place_stop_loss()

def koopgenerator(signals):
    for signal in signals:
        yield signal

async def send_buysignal(application):
    bot = application.bot
    try:
        signal = next(application.koopgen)
        application.huidig_signaal = signal  # sla dit op voor gebruik in tekst_handler

        markt = signal.get('market')
        prijs_per_eenheid = signal.get('huidige_marktprijs')
        totaal = signal.get('orderprijs')


        buy_message = f"Koopsignaal:\nValuta: {markt}\nPrijs per eenheid: €{round(prijs_per_eenheid, 2)}\n\n " \
                      f"Totaalbedrag: €{totaal}\n" \
                      f"Je hebt €{check_balance()} beschikbaar, wil je deze aankoop bevestigen?"

        await bot.send_message(chat_id=chat_id, text=buy_message, reply_markup=maak_knoppen())

    except StopIteration:
        await bot.send_message(chat_id=chat_id, text="Geen koopsignalen meer.")
        sys.exit()

async def manage_orders(application):
    bot = application.bot
    if strategy._placesellorders:
        await place_market_order()

    if strategy._buysignals:
        application.koopgen = koopgenerator(strategy._buysignals)
        await send_buysignal(application)

    else:
        sys.exit()


async def tekst_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    antwoord = update.message.text.lower()
    application = context.application  # nodig om toegang tot koopgen/huidig_signaal te krijgen

    if antwoord == "ja":
        signaal = application.huidig_signaal
        markt = signaal.get('market')
        bedrag = signaal.get('orderprijs')
        await place_market_order(market=markt, amount=bedrag, side='buy')

    elif antwoord == "nee":
        await send_buysignal(application)

    else:
        await update.message.reply_text("Antwoord ongeldig. Typ 'ja' of 'nee'.")


async def knop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    application = context.application
    query = update.callback_query
    await query.answer()

    keuze = query.data
    signaal = application.huidig_signaal
    market = signaal.get('market')
    amount = signaal.get('orderprijs')

    if keuze == "ja":
        await place_market_order(market=market, amount=amount, side='buy')
        sys.exit()

    elif keuze == "nee":
        await send_buysignal(application)


async def place_stop_loss():
    data = strategy._buysignals[strategy._index]
    market = data['market']
    amount = data['hoeveelheid']
    stop_loss = data['stop_loss']
    stop_loss_limit = data['stop_limit']

    stop_loss_order = bitvavo.placeOrder(market, 'sell', 'stopLossLimit', {
        'amount': amount,
        'price': stop_loss_limit,
        'triggerType': 'price',
        'stopPrice': stop_loss_price,
        'triggerAmount': stop_loss_price,
        'triggerReference': 'bestBid',
        'operatorId': operator_id
    })

    if 'error' in stop_loss_order:
        print(f"Fout bij plaatsen stop-loss order: {stop_loss_order['error']}")
        await bot.send_message(chat_id=chat_id,
                                     text=f"Fout bij het plaatsen van stop-loss order: {stop_loss_order['error']}")

    else:
        print(f"Stop-loss order succesvol geplaatst!")
        await bot.send_message(chat_id=chat_id,
                                     text=(f"Stop-loss order succesvol geplaatst!"))

        writebuyorder["Id"] = stop_loss_order["orderId"]
        if os.path.exists(orderbook_path):
            try:
                with open(orderbook_path, 'r') as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []

            except json.JSONDecodeError:
                data = []
        else:
            data = []
        data.append(writebuyorder)

        with open(orderbook_path, 'w') as f:
            json.dump(data, f, indent=4)

        return stop_loss_order

def check_balance():
    balance = bitvavo.balance({'symbol': 'EUR'})
    if 'error' in balance:
        print(f"Fout bij ophalen balans: {balance['error']}")
    else:
        for item in balance:
            if item['symbol'] == 'EUR':
                available_balance = float(item['available'])
                return available_balance
    return 0.0



if __name__ == "__main__":
    while True:
        strategy.populate_orders(orderbook=orderbook_path)
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CallbackQueryHandler(knop_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tekst_handler))
        loop = asyncio.get_event_loop()
        loop.run_until_complete(manage_orders(app))
        app.run_polling()
        time.sleep(900)

    if args.backtest:
        strategy.run_backtest()
