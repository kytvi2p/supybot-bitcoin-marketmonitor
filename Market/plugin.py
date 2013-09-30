###
# Copyright (c) 2011, remote
# Copyright (c) 2011, nanotube
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
from supybot import conf
from supybot import world

import re
import json
import time
import traceback

#TBB headers
headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; rv:17.0) Gecko/20100101 Firefox/17.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8 gzip,'
                    'deflate en-us,en;q=0.5'
          }
def getNonNegativeFloat(irc, msg, args, state, type='floating point number'):
    try:
        v = float(args[0])
        if v < 0:
            raise ValueError, "only non-negative numbers allowed."
        state.args.append(v)
        del args[0]
    except ValueError:
        state.errorInvalid(type, args[0])

def getCurrencyCode(irc, msg, args, state, type='currency code'):
    v = args[0]
    m = re.search(r'^([A-Za-z]{3})$', v)
    if m is None:
        state.errorInvalid(type, args[0])
        return
    state.args.append(m.group(1).upper())
    del args[0]

addConverter('nonNegativeFloat', getNonNegativeFloat)
addConverter('currencyCode', getCurrencyCode)

class Market(callbacks.Plugin):
    """Add the help for "@plugin help Market" here
    This should describe *how* to use this plugin."""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(Market, self)
        self.__parent.__init__(irc)
        self.lastdepthfetch = 0
        self.mdepth = None

    def _getMarketDepth(self):
        if world.testing: # avoid hammering mtgox api when testing.
            self.mdepth = json.load(open('/tmp/mtgox.depth.json'))['return']
            return
        try:
            if time.time() - self.lastdepthfetch > self.registryValue('fullDepthCachePeriod'):
                data = utils.web.getUrl('http://data.mtgox.com/api/1/BTCUSD/depth/full',
                        headers = headers)
                self.mdepth = json.loads(data)
                self.mdepth = self.mdepth['return']
                self.mdepth['bids'].reverse() # bids are listed in ascending order
                self.lastdepthfetch = time.time()
        except:
            pass # oh well, try again later.

    def _getMtgoxTicker(self, currency):
        if not world.testing or currency != 'USD':
            json_data = utils.web.getUrl("https://data.mtgox.com/api/2/BTC%s/money/ticker" % 
                (currency.upper(),), headers = headers)
            ticker = json.loads(json_data)
            ftj = utils.web.getUrl("http://data.mtgox.com/api/2/BTC%s/money/ticker_fast" %
                (currency.upper(),), headers = headers)
            tf = json.loads(ftj)
            if ticker['result'] != 'error' and tf['result'] != 'error': # use fast ticker where available
                ticker['data']['buy']['value'] = tf['data']['buy']['value']
                ticker['data']['sell']['value'] = tf['data']['sell']['value']
                ticker['data']['last']['value'] = tf['data']['last']['value']
        else:
            ticker = json.load(open('/tmp/mtgox.ticker.json'))
        if ticker['result'] == 'error':
             stdticker = {'error':ticker['error']}
        else:
            stdticker = {'bid': ticker['data']['buy']['value'],
                                'ask': ticker['data']['sell']['value'],
                                'last': ticker['data']['last']['value'],
                                'vol': ticker['data']['vol']['value'],
                                'low': ticker['data']['low']['value'],
                                'high': ticker['data']['high']['value'],
                                'avg': ticker['data']['vwap']['value']}
        return stdticker

    def _getBtceTicker(self, currency):
        if currency.lower() == 'ltc':
            pair = 'ltc_btc'
        else:
            pair = 'btc_%s' % (currency.lower(),)
        json_data = utils.web.getUrl("https://btc-e.com/api/2/%s/ticker" %
                (pair,), headers = headers)
        ticker = json.loads(json_data)
        if ticker.has_key('error'):
            stdticker = {'error':ticker['error']}
        else:
            ticker = ticker['ticker']
            if currency.lower() == 'ltc':
                stdticker = {'bid': round(1.0/ticker['buy'],6),
                                'ask': round(1.0/ticker['sell'],6),
                                'last': round(1.0/ticker['last'],6),
                                'vol': ticker['vol'],
                                'low': round(1.0/ticker['high'],6),
                                'high': round(1.0/ticker['low'],6),
                                'avg': round(1.0/ticker['avg'],6)}
            else:
                stdticker = {'bid': ticker['sell'],
                                'ask': ticker['buy'],
                                'last': ticker['last'],
                                'vol': ticker['vol_cur'],
                                'low': ticker['low'],
                                'high': ticker['high'],
                                'avg': ticker['avg']}
        return stdticker

    def _getBitstampTicker(self, currency):
        json_data = utils.web.getUrl('https://www.bitstamp.net/api/ticker/',
                headers = headers)
        ticker = json.loads(json_data)
        if currency != 'USD':
            stdticker = {'error':'unsupported currency'}
        else:
            stdticker = {'bid': ticker['bid'],
                                'ask': ticker['ask'],
                                'last': ticker['last'],
                                'vol': ticker['volume'],
                                'low': ticker['low'],
                                'high': ticker['high'],
                                'avg': None}
        return stdticker

    def _getBitfinexTicker(self, currency):
        if currency.lower() == 'ltc':
            pair = 'ltcbtc'
        else:
            pair = 'btc%s' % (currency.lower(),)
        json_data = utils.web.getUrl("https://bitfinex.com/api/v1/ticker/%s" %
                (pair,), headers = headers)
        spotticker = json.loads(json_data)
        json_data = utils.web.getUrl("https://bitfinex.com/api/v1/today/%s" %
                (pair,), headers = headers)
        dayticker = json.loads(json_data)
        if spotticker.has_key('message') or dayticker.has_key('message'):
            stdticker = {'error':spotticker.get('message') or dayticker.get('message')}
        else:
            if currency.lower() == 'ltc':
                stdticker = {'bid': round(1.0/float(spotticker['ask']),6),
                                'ask': round(1.0/float(spotticker['bid']),6),
                                'last': round(1.0/float(spotticker['last_price']),6),
                                'vol': dayticker['volume'],
                                'low': round(1.0/float(dayticker['high']),6),
                                'high': round(1.0/float(dayticker['low']),6),
                                'avg': None}
            else:
                stdticker = {'bid': spotticker['bid'],
                                'ask': spotticker['ask'],
                                'last': spotticker['last_price'],
                                'vol': dayticker['volume'],
                                'low': dayticker['low'],
                                'high': dayticker['high'],
                                'avg': None}
        return stdticker

    def _getBtcdeTicker(self, currency):
        json_data = utils.web.getUrl("http://api.bitcoincharts.com/v1/markets.json",
                headers = headers)

        ticker = json.loads(json_data)
        trades = utils.web.getUrl('http://api.bitcoincharts.com/v1/trades.csv?symbol=btcdeEUR',
                headers = headers)
        last = float(trades[0].split(',')[1])
        if currency != 'EUR':
            stdticker = {'error':'unsupported currency'}
        else:
            ticker = filter(lambda x: x['symbol'] == 'btcdeEUR', ticker)[0]
            stdticker = {'bid': ticker['bid'],
                                'ask': ticker['ask'],
                                'last': last,
                                'vol': ticker['volume'],
                                'low': ticker['low'],
                                'high': ticker['high'],
                                'avg': ticker['avg']}
        return stdticker

    def _getCbxTicker(self, currency):
        json_data = utils.web.getUrl("http://api.bitcoincharts.com/v1/markets.json",
                headers = headers)

        ticker = json.loads(json_data)
        cbx = json.loads(utils.web.getUrl('http://campbx.com/api/xticker.php',
            headers = headers))

        if currency != 'USD':
            stdticker = {'error':'unsupported currency'}
        else:
            ticker = filter(lambda x: x['symbol'] == 'cbxUSD', ticker)[0]
            stdticker = {'bid': cbx['Best Bid'],
                                'ask': cbx['Best Ask'],
                                'last': cbx['Last Trade'],
                                'vol': ticker['volume'],
                                'low': ticker['low'],
                                'high': ticker['high'],
                                'avg': ticker['avg']}
        return stdticker

    def _sellbtc(self, bids, value):
        n_coins = value
        total = 0.0
        top = 0.0
        all = False
        for bid in bids:
            if n_coins <= bid['amount']: # we don't have enough
                total += n_coins * bid['price']
                top = bid['price']
                break
            else: # we can eat the entire order
                n_coins -= bid['amount']
                total += bid['amount'] * bid['price']
        else:
            all = True
        return({'n_coins':n_coins, 'total':total, 'top':top, 'all':all})

    def _sellusd(self, bids, value):
        n_coins = 0.0
        total = value
        top = 0.0
        all = False
        for bid in bids:
            if total <= bid['amount'] * bid['price']: 
                n_coins += total / bid['price']
                top = bid['price']
                break
            else: # we can eat the entire order
                n_coins += bid['amount']
                total -= bid['amount'] * bid['price']
        else:
            all = True
        return({'n_coins':n_coins, 'total':total, 'top':top, 'all':all})

    def sell(self, irc, msg, args, optlist, value):
        """[--usd] <value>
        
        Calculate the effect on the market depth of a market sell order of
        <value> bitcoins. If '--usd' option is given, <value> denotes the 
        size of the order in USD.
        """
        self._getMarketDepth()
        try:
            bids = self.mdepth['bids']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return
        if dict(optlist).has_key('usd'):
            r = self._sellusd(bids, value)
            if r['all']:
                irc.reply("This order would exceed the size of the order book. "
                        "You would sell %.8g bitcoins for a total of %.4f USD and "
                        "take the price to 0."
                        " | Data vintage: %.4f seconds"
                        % (r['n_coins'], value - r['total'], (time.time() - self.lastdepthfetch),))
            else:
                irc.reply("A market order to sell %.4f USD worth of bitcoins right "
                        "now would sell %.8g bitcoins and would take the last "
                        "price down to %.4f USD, resulting in an average price of "
                        "%.4f USD/BTC."
                        " | Data vintage: %.4f seconds"
                        % (value, r['n_coins'], r['top'],(value/r['n_coins']), (time.time() - self.lastdepthfetch),))
        else:
            r = self._sellbtc(bids, value)
            if r['all']:
                irc.reply("This order would exceed the size of the order book. "
                        "You would sell %.8g bitcoins, for a total of %.4f USD and "
                        "take the price to 0."
                        " | Data vintage: %.4f seconds"
                        % (value - r['n_coins'], r['total'], (time.time() - self.lastdepthfetch),))
            else:
                irc.reply("A market order to sell %.8g bitcoins right now would "
                        "net %.4f USD and would take the last price down to %.4f USD, "
                        "resulting in an average price of %.4f USD/BTC."
                        " | Data vintage: %.4f seconds"
                        % (value, r['total'], r['top'], (r['total']/value), (time.time() - self.lastdepthfetch)))
    sell = wrap(sell, [getopts({'usd': '',}), 'nonNegativeFloat'])

    def _buybtc(self, asks, value):
        n_coins = value
        total = 0.0
        top = 0.0
        all = False
        for ask in asks:
            if n_coins <= ask['amount']: # we don't have enough
                total += n_coins * ask['price']
                top = ask['price']
                break
            else: # we can eat the entire order
                n_coins -= ask['amount']
                total += ask['amount'] * ask['price']
                top = ask['price']
        else:
            all = True
        return({'n_coins':n_coins, 'total':total, 'top':top, 'all':all})

    def _buyusd(self, asks, value):
        n_coins = 0.0
        total = value
        top = 0.0
        all = False
        for ask in asks:
            if total <= ask['amount'] * ask['price']: 
                n_coins += total / ask['price']
                top = ask['price']
                break
            else: # we can eat the entire order
                n_coins += ask['amount']
                total -= ask['amount'] * ask['price']
                top = ask['price']
        else:
            all = True
        return({'n_coins':n_coins, 'total':total, 'top':top, 'all':all})

    def buy(self, irc, msg, args, optlist, value):
        """[--usd] <value>
        
        Calculate the effect on the market depth of a market buy order of
        <value> bitcoins. If '--usd' option is given, <value> denotes the 
        size of the order in USD.
        """
        self._getMarketDepth()
        try:
            asks =self.mdepth['asks']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return
        if dict(optlist).has_key('usd'):
            r = self._buyusd(asks, value)
            if r['all']:
                irc.reply("This order would exceed the size of the order book. "
                        "You would buy %.8g bitcoins for a total of %.4f USD and "
                        "take the price to %.4f."
                        " | Data vintage: %.4f seconds"
                        % (r['n_coins'], value - r['total'], r['top'], (time.time() - self.lastdepthfetch),))
            else:
                irc.reply("A market order to buy %.4f USD worth of bitcoins right "
                        "now would buy %.8g bitcoins and would take the last "
                        "price up to %.4f USD, resulting in an average price of "
                        "%.4f USD/BTC."
                        " | Data vintage: %.4f seconds"
                        % (value, r['n_coins'], r['top'],(value/r['n_coins']), (time.time() - self.lastdepthfetch),))
        else:
            r = self._buybtc(asks, value)
            if r['all']:
                irc.reply("This order would exceed the size of the order book. "
                        "You would buy %.8g bitcoins, for a total of %.4f USD and "
                        "take the price to %.4f."
                        " | Data vintage: %.4f seconds"
                        % (value - r['n_coins'], r['total'], r['top'], (time.time() - self.lastdepthfetch),))
            else:
                irc.reply("A market order to buy %.8g bitcoins right now would "
                        "take %.4f USD and would take the last price up to %.4f USD, "
                        "resulting in an average price of %.4f USD/BTC."
                        " | Data vintage: %.4f seconds"
                        % (value, r['total'], r['top'], (r['total']/value), (time.time() - self.lastdepthfetch),))
    buy = wrap(buy, [getopts({'usd': '',}), 'nonNegativeFloat'])


    def asks(self, irc, msg, args, optlist, pricetarget):
        """[--over] <pricetarget>
        
        Calculate the amount of bitcoins for sale at or under <pricetarget>.
        If '--over' option is given, find coins or at or over <pricetarget>.
        """
        self._getMarketDepth()
        response = "under"
        if dict(optlist).has_key('over'):
            f = lambda price,pricetarget: price >= pricetarget
            response = "over"
        else:
            f = lambda price,pricetarget: price <= pricetarget
        n_coins = 0.0
        total = 0.0
        try:
            asks =self.mdepth['asks']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return
        for ask in asks:
            if f(ask['price'], pricetarget):
                n_coins += ask['amount']
                total += (ask['amount'] * ask['price'])

        irc.reply("There are currently %.8g bitcoins offered at "
                "or %s %s USD, worth %s USD in total."
                " | Data vintage: %.4f seconds"
                % (n_coins, response, pricetarget, total, (time.time() - self.lastdepthfetch),))
    asks = wrap(asks, [getopts({'over': '',}), 'nonNegativeFloat'])

    def bids(self, irc, msg, args, optlist, pricetarget):
        """[--under] <pricetarget>
        
        Calculate the amount of bitcoin demanded at or over <pricetarget>.
        If '--under' option is given, find coins or at or under <pricetarget>.
        """
        self._getMarketDepth()
        response = "over"
        if dict(optlist).has_key('under'):
            f = lambda price,pricetarget: price <= pricetarget
            response = "under"
        else:
            f = lambda price,pricetarget: price >= pricetarget
        n_coins = 0.0
        total = 0.0
        try:
            bids =self.mdepth['bids']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return
        for bid in bids:
            if f(bid['price'], pricetarget):
                n_coins += bid['amount']
                total += (bid['amount'] * bid['price'])

        irc.reply("There are currently %.8g bitcoins demanded at "
                "or %s %s USD, worth %s USD in total."
                " | Data vintage: %.4f seconds"
                % (n_coins, response, pricetarget, total, (time.time() - self.lastdepthfetch),))
    bids = wrap(bids, [getopts({'under': '',}), 'nonNegativeFloat'])

    def obip(self, irc, msg, args, width):
        """<width>
        
        Calculate the "order book implied price", by finding the weighted
        average price of coins <width> BTC up and down from the spread.
        """
        self._getMarketDepth()
        try:
            asks =self.mdepth['asks']
            bids = self.mdepth['bids']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return

        b = self._buybtc(asks, width)
        s = self._sellbtc(bids, width)
        if b['all'] or s['all']:
            irc.error("The width provided extends past the edge of the order book. Please use a smaller width.")
            return
        obip = (b['total'] + s['total'])/2.0/width
        irc.reply("The weighted average price of BTC, %s coins up and down from the spread, is %.5f USD."
                " | Data vintage: %.4f seconds"
                % (width, obip,(time.time() - self.lastdepthfetch),))
    obip = wrap(obip, ['nonNegativeFloat'])

    def baratio(self, irc, msg, args):
        """takes no arguments
        
        Calculate the ratio of total usd volume of bids to total btc volume of asks.
        """
        self._getMarketDepth()
        try:
            asks =self.mdepth['asks']
            bids = self.mdepth['bids']
        except KeyError:
            irc.error("Failure to retrieve order book data. Try again later.")
            return

        totalasks = 0
        for ask in asks:
            totalasks += ask['amount']
        totalbids = 0
        for bid in bids:
            totalbids += bid['amount'] * bid['price']
        ratio = totalbids / totalasks
        irc.reply("Total bids: %d USD. Total asks: %d BTC. Ratio: %.5f USD/BTC."
                " | Data vintage: %.4f seconds"
                % (totalbids, totalasks, ratio, (time.time() - self.lastdepthfetch),))
    baratio = wrap(baratio)

    def ticker(self, irc, msg, args, optlist):
        """[--bid|--ask|--last|--high|--low|--avg|--vol] [--currency XXX] [--market mtgox|btce|bitstamp]
        
        Return pretty-printed ticker. Default market is Mtgox. 
        If one of the result options is given, returns only that numeric result
        (useful for nesting in calculations).
        
        If '--currency XXX' option  is given, returns ticker for that three-letter currency code.
        It is up to you to make sure that the three letter code you enter is a valid currency
        that is traded on mtgox. Default currency is USD.
        """
        supportedmarkets = {'mtgox':'MtGox','btce':'BTC-E', 'bitstamp':'Bitstamp',
                'bitfinex':'Bitfinex', 'btcde':'Bitcoin.de', 'cbx':'CampBX'}
        od = dict(optlist)
        currency = od.pop('currency', 'USD')
        market = od.pop('market','mtgox').lower()
        if market not in supportedmarkets.keys():
            irc.error("This is not one of the supported markets. Please choose one of %s." % (supportedmarkets.keys(),))
            return
        if len(od) > 1:
            irc.error("Please only choose at most one result option at a time.")
            return
        dispatch = {'mtgox':self._getMtgoxTicker, 'btce':self._getBtceTicker,
                'bitstamp':self._getBitstampTicker, 'bitfinex': self._getBitfinexTicker,
                'btcde':self._getBtcdeTicker, 'cbx':self._getCbxTicker}
        try:
            ticker = dispatch[market](currency)
        except:
            irc.error("Failure to retrieve ticker. Try again later.")
            traceback.print_exc()
            return
        if ticker.has_key('error'):
            irc.error('Error retrieving ticker. Details: %s' % (ticker['error'],))
            return

        if len(od) == 0:
            irc.reply("%s BTC%s ticker | Best bid: %s, Best ask: %s, Bid-ask spread: %.5f, Last trade: %s, "
                "24 hour volume: %s, 24 hour low: %s, 24 hour high: %s, 24 hour vwap: %s" % \
                (supportedmarkets[market], currency, ticker['bid'], ticker['ask'],
                float(ticker['ask']) - float(ticker['bid']), ticker['last'],
                ticker['vol'], ticker['low'], ticker['high'],
                ticker['avg']))
        else:
            key = od.keys()[0]
            irc.reply(ticker[key])
    ticker = wrap(ticker, [getopts({'bid': '','ask': '','last': '','high': '',
            'low': '', 'avg': '', 'vol': '', 'currency': 'currencyCode', 'market': 'something'})])

    def goxlag(self, irc, msg, args, optlist):
        """[--raw]
        
        Retrieve mtgox order processing lag. If --raw option is specified
        only output the raw number of seconds. Otherwise, dress it up."""
        try:
            json_data = utils.web.getUrl("https://mtgox.com/api/2/money/order/lag", headers = headers)

            lag = json.loads(json_data)
            lag_secs = lag['data']['lag_secs']
        except:
            irc.error("Problem retrieving gox lag. Try again later.")
            return

        if dict(optlist).has_key('raw'):
            irc.reply("%s" % (lag_secs,))
            return
        
        result = "MtGox lag is %s seconds." % (lag_secs,)
        
        au = lag_secs / 499.004784
        meandistance = {0: "... nowhere, really",
                        0.0001339: "to the other side of the Earth, along the surface",
                        0.0024: "across the outer diameter of Saturn's rings",
                        0.00257: "from Earth to Moon",
                        0.002819: "from Jupiter to its third largest moon, Io",
                        0.007155: "from Jupiter to its largest moon, Ganymede",
                        0.00802: "from Saturn to its largest moon, Titan",
                        0.012567: "from Jupiter to its second largest moon, Callisto",
                        0.016: "one full loop along the orbit of the Moon around Earth",
                        0.0257: 'ten times between Earth and Moon',
                        0.0689: "approximately the distance covered by Voyager 1 in one week",
                        0.0802: "ten times between Saturn and Titan",
                        0.12567: "ten times between Jupiter and Callisto",
                        0.2540: 'between Earth and Venus at their closest approach',
                        0.257: 'one hundred times between Earth and Moon',
                        0.2988: 'approximately the distance covered by Voyager 1 in one month',
                        0.39: 'from the Sun to Mercury',
                        0.72: 'from the Sun to Venus',
                        1: 'from the Sun to Earth',
                        1.52: 'from the Sun to Mars',
                        2.77: 'from the Sun to Ceres (in the main asteroid belt)',
                        5.2: 'from the Sun to Jupiter',
                        9.54: 'from the Sun to Saturn',
                        19.18: 'from the Sun to Uranus',
                        30.06: 'from the Sun to Neptune',
                        39.44: 'from the Sun to Pluto (Kuiper belt)',
                        100: 'from the Sun to heliopause (out of the solar system!)'}
        import operator
        distances = meandistance.keys()
        diffs = map(lambda x: abs(operator.__sub__(x, au)), distances)
        bestdist = distances[diffs.index(min(diffs))]
        objectname = meandistance[bestdist]
        result += " During this time, light travels %s AU. You could have sent a bitcoin %s (%s AU)." % (au, objectname, bestdist)
        irc.reply(result)
    goxlag = wrap(goxlag, [getopts({'raw': ''})])

Class = Market


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
