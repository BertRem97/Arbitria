from python_bitvavo_api.bitvavo import Bitvavo
import pandas as pd
import numpy as np
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
import asyncio
import sys
import ta
import os
import json
import argparse
from datetime import datetime, date
import random

class Strategy:
    def __init__(self, configfile):
        today = datetime.now().strftime("%Y-%m-%d")
        if configfile is not None:
            with open(configfile, 'r') as f:
                data = json.load(f)
                stop_loss_percentage = data['Stop-loss']
                take_profit_percentage = data['Take-profit']
                eur_per_trade = data['Bedrag per trade']
                interval = data['Tijdsframe']
                markets = data['Markets']
                api_secret = data['Api-secret']
                api_key = data['Api-key']

        self._placesellorders = []
        self._placebuyorders = []
        self._buysignals = []
        self._backtest_log = r"C:\Users\User\PycharmProjects\pythonProject1\BOT\Bitvavo\ActingBotBitvavo\Backtest strategy MA {}.json".format(str(today))
        self._data_frame = []
        self._stop_loss_percentage = stop_loss_percentage
        self._take_profit_percentage = take_profit_percentage
        self._eur_per_trade = eur_per_trade
        self._interval = interval
        self._markets = markets
        self._api_secret = "b04eead8ef090230f1e430503379989947414e07c994bce7db682b726e2b66a044b29500990376463866999b729f0db5fab925aacc902e66371cc9bef228615c"
        self._api_key = "54aa9b533f6fa6b3483bef9475edc5b55d0cf7daa5da893be43d9cdfe8aaa87d"
        self._bitvavo_sign = Bitvavo({
            'APIKEY': api_key,
            'APISECRET': api_secret,
            'RESTURL': "https://api.bitvavo.com/v2",
            'WSURL': "wss://ws.bitvavo.com/v2/",
            })

        for market in self._markets:
            response = self._bitvavo_sign.candles(market, interval, {'limit': 1440})
            if isinstance(response, dict):
                if response['errorCode'] == 205:
                    print(f"Aandeel {market} niet gevonden")

            df = pd.DataFrame(response,
                              columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df[['open', 'high', 'low', 'close', 'volume']] = df[
                ['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
            df = df.set_index('timestamp')
            df = df.sort_index()
            df['market'] = market

            df['SMA_50'] = ta.trend.sma_indicator(df['close'], window=50)
            df['SMA_20'] = ta.trend.sma_indicator(df['close'], window=20)
            df['SMA_200'] = ta.trend.sma_indicator(df['close'], window=200)

            df['EMA_8'] = ta.trend.ema_indicator(df['close'], window=8)
            df['EMA_13'] = ta.trend.ema_indicator(df['close'], window=13)
            df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
            df['EMA_55'] = ta.trend.ema_indicator(df['close'], window=55)
            df['EMA_89'] = ta.trend.ema_indicator(df['close'], window=89)

            df['EMA_8_above_EMA_13'] = df['EMA_8'] > df['EMA_13']
            df['EMA_13_above_EMA_21'] = df['EMA_13'] > df['EMA_21']
            df['EMA_21_above_EMA_55'] = df['EMA_21'] > df['EMA_55']
            df['EMA_55_above_EMA_89'] = df['EMA_55'] > df['EMA_89']

            df['EMA_above'] = (df['EMA_8_above_EMA_13'] &
                               df['EMA_13_above_EMA_21'] &
                               df['EMA_21_above_EMA_55'] &
                               df['EMA_55_above_EMA_89'])

            df['EMA_below'] = (~df['EMA_8_above_EMA_13'])

            self._data_frame.append(df)


    def populate_orders(self, orderbook):
        print('test')
        buy_orders = []
        for df in self._data_frame:
            market = df['market'][0]
            current_price = (lambda x: float(x.get('price')) if x.get('price') else None)\
                (self._bitvavo_sign.tickerPrice({'market': market}))


            last_row = df.iloc[-1]
            if last_row['EMA_above'] and current_price:
                quantity = round(self._eur_per_trade / current_price, 3)
                amount = round(quantity * current_price, 2)
                stop_loss_price = current_price / (1 + (self._stop_loss_percentage / 100))
                take_profit_price = current_price * (1 + (self._take_profit_percentage / 100))
                limit_price = stop_loss_price * 0.99

                num_decimals_sl = 0 if self._stop_loss_price >= 1000 else \
                    1 if stop_loss_price >= 1000 < 10000 else \
                    2 if stop_loss_price >= 100 < 1000 else \
                    3 if stop_loss_price >= 10 < 100 else \
                    4 if stop_loss_price >= 1 < 10 else \
                    5 if stop_loss_price < 1 else None

                num_decimals_tp = 0 if self._take_profit_price >= 1000 else \
                    1 if take_profit_price >= 1000 < 10000 else \
                    2 if take_profit_price >= 100 < 1000 else \
                    3 if take_profit_price >= 10 < 100 else \
                    4 if take_profit_price >= 1 < 10 else \
                    5 if take_profit_price < 1 else None

                num_decimals_lp = 0 if limit_price >= 1000 else \
                    1 if limit_price >= 1000 < 10000 else \
                    2 if limit_price >= 100 < 1000 else \
                    3 if limit_price >= 10 < 100 else \
                    4 if limit_price >= 1 < 10 else \
                    5 if limit_price < 1 else None

                stop_loss_price = round(self._stop_loss_price, num_decimals_sl)
                take_profit_price = round(self._take_profit_price, num_decimals_tp)
                limit_price = round(limit_price, num_decimals_lp)
                buy_order = {'market': market, "hoeveelheid": quantity, "orderprijs": amount,
                                             "take_profit": self._take_profit_price, "stop_loss": stop_loss_price,
                                             "stop_limit": limit_price,
                                             "huidige_marktprijs": current_price}

                buy_orders.append(buy_order)
                self._buysignals = (order for order in buy_orders)


                open_orders = self._bitvavo_sign.ordersOpen({})
                if os.path.exists(orderbook) and orderbook is not None:
                    today = date.today()
                    with open(orderbook, 'r') as f:
                        orders = json.load(f)
                        for order in orders:
                            profit = round(
                                (float(current_price) - float(order['price'])) / float(
                                    order['price']) * 100, 2)

                            x = bitvavo.getOrder(market, order['Id'])
                            if not 'errorCode' in x:
                                orderId = x['orderId']
                                status = x['status']
                                ordertype = x['orderType']
                                fee = x['feePaid']
                                filled = x['filledAmountQuote']

                                if status == 'filled' and orderId == order['Id'] and ordertype == 'stopLossLimit':
                                    loss = float(filled) - float(fee) - float(order['total_paid'])
                                    order['type'] = 'Sold'
                                    order['date'] = str(today)
                                    order['eur_loss'] = loss

                                    with open(orderbook, 'w') as f:
                                        json.dump(orders, f, indent=4)

                                else:
                                    for i in open_orders:
                                        if isinstance(order, dict) and i['orderId'] == order['Id']:
                                            order['huidige_marktprijs'] = current_price
                                            order['profit_percentage'] = "{}%".format(profit)

                                        if last_row['EMA_below'] and profit >= 2:
                                            data = {"market": market, "amount": order["amount"],
                                                    "Id": order["Id"],
                                                    "total_paid": order["total_paid"]}

                                            self._placesellorders.append(data)

    def run_backtest(self):
        buy_orders = []
        open_orders = []
        sell_orders = []
        stoploss_orders = []
        for df in self._data_frame:
            market = df['market'][0]
            for index, row in df.iterrows():
                order_number = random.randint(100, 999)

                if row['EMA_above']:
                    buy_order = {'type': 'Bought', 'strategy': 'Long bullish', 'symbol': row['market'],
                                 'time': str(index.to_pydatetime()),
                                 'closing_price': float(row['close']),
                                 'order': order_number}

                    buy_orders.append(buy_order)
                    open_orders.append(buy_order)

                if open_orders is not None:
                    for i in open_orders:
                        date_format = '%Y-%m-%d %H:%M:%S'
                        date_obj = datetime.strptime(i['time'], date_format)
                        stop_limit = float(i['closing_price']) * 0.98
                        profit = round((float(row['close']) - float(i['closing_price'])) / float(i['closing_price']) * 100,2)
                        stop_loss_price = round(row['close'] / (1 + (self._stop_loss_percentage / 100)), 3)
                        limit_price = round(stop_loss_price / 1.01, 3)
                        take_profit_price = round(row['close'] * (1 + (self._take_profit_percentage / 100)), 3)

                        if i['type'] == 'Bought' and i['symbol'] == row['market'] and \
                                profit <= -self._stop_loss_percentage and index.to_pydatetime() > date_obj \
                                and i['strategy'] == 'Long bullish':

                            stoploss_order = {'type': 'Stoploss', "symbol": row['market'], 'order': i['order'],
                                              'time': str(index.to_pydatetime()),
                                              'closing_price': float(row['close']),
                                              'aankoopprijs': float(i['closing_price']),
                                              'aankoopdatum': str(i['time']),
                                              'percentage_loss': profit}

                            stoploss_orders.append(stoploss_order)
                            open_orders.remove(i)

                        elif i['type'] == 'Bought' and i['symbol'] == row['market'] and i[
                            'strategy'] == 'Long bullish' and row['EMA_below'] \
                                and index.to_pydatetime() > date_obj and profit > 0:

                            sell_order = {'type': 'Sold', 'symbol': row['market'],
                                          'time': str(index.to_pydatetime()),
                                          'closing_price': float(row['close']),
                                          'aankoopdatum': str(i['time']),
                                          'aankoopprijs': float(i['closing_price']),
                                          'percentage_gain': profit,
                                          'order': i['order']}

                            sell_orders.append(sell_order)
                            open_orders.remove(i)


            if buy_orders:
                buy_orders = [order for order in buy_orders if order['symbol'] == market]
                sell_orders = [order for order in sell_orders if order['symbol'] == market]
                stoploss_orders = [order for order in stoploss_orders if order['symbol'] == market]

                potential_market = False
                avg_p = round((lambda x: sum(x) / len(sell_orders))(i['percentage_gain'] for i in sell_orders), 2) \
                    if sell_orders else 0

                max_p = round((lambda x: max(x))(i['percentage_gain'] for i in sell_orders), 2) \
                    if sell_orders else 0

                amount_lost = round((self._eur_per_trade - self._eur_per_trade / (1 + self._stop_loss_percentage / 100)) * len(stoploss_orders), 2)

                total_avgp_return = round(len(sell_orders) * self._eur_per_trade * (1+avg_p/100), 2)
                inleg = self._eur_per_trade * len(sell_orders)
                profit = total_avgp_return - inleg

                potential_market = True if profit > amount_lost else False

            with open(self._backtest_log, "a+") as f:
                f.write(f"-----------{market}--------------\n"
                        f"Entries: {len(buy_orders)}\nWins: {len(sell_orders)}\nLosses: {len(stoploss_orders)}\n"
                        f"Open orders: {len(open_orders)}\n"
                        f"Average profit: {avg_p}%\n"
                        f"Maximum profit: {max_p}%\n"
                        f"Success rate per trade: {round(len(sell_orders) / len(buy_orders) * 100, 2)}%\n"
                        f"Potential market: {potential_market}\n"
                        f"Gemiddelde gerealiseerde winst: €{round(profit - amount_lost, 2)}\n")
