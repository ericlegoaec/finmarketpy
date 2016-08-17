__author__ = 'saeedamen'

#
# Copyright 2016 Cuemacro
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# See the License for the specific language governing permissions and limitations under the License.
#

"""
Backtest

Conducts backtest for strategies trading assets. Assumes we have an input of total returns. Reports historical return statistics
and returns time series.

"""

import numpy

from findatapy.util import LoggerManager

class Backtest:

    def __init__(self):
        self.logger = LoggerManager().getLogger(__name__)
        self._pnl = None
        self._portfolio = None
        return

    def calculate_trading_PnL(self, br, asset_a_df, signal_df):
        """
        calculate_trading_PnL - Calculates P&L of a trading strategy and statistics to be retrieved later

        Parameters
        ----------
        br : BacktestRequest
            Parameters for the backtest specifying start date, finish data, transaction costs etc.

        asset_a_df : pandas.DataFrame
            Asset prices to be traded

        signal_df : pandas.DataFrame
            Signals for the trading strategy
        """

        calculations = Calculations()
        # signal_df.to_csv('e:/temp0.csv')
        # make sure the dates of both traded asset and signal are aligned properly
        asset_df, signal_df = asset_a_df.align(signal_df, join='left', axis = 'index')

        # only allow signals to change on the days when we can trade assets
        signal_df = signal_df.mask(numpy.isnan(asset_df.values))    # fill asset holidays with NaN signals
        signal_df = signal_df.fillna(method='ffill')                # fill these down
        asset_df = asset_df.fillna(method='ffill')                  # fill down asset holidays

        returns_df = calculations.calculate_returns(asset_df)
        tc = br.spot_tc_bp

        signal_cols = signal_df.columns.values
        returns_cols = returns_df.columns.values

        pnl_cols = []

        for i in range(0, len(returns_cols)):
            pnl_cols.append(returns_cols[i] + " / " + signal_cols[i])

        # do we have a vol target for individual signals?
        if hasattr(br, 'signal_vol_adjust'):
            if br.signal_vol_adjust is True:
                risk_engine = RiskEngine()

                if not(hasattr(br, 'signal_vol_resample_type')):
                    br.signal_vol_resample_type = 'mean'

                if not(hasattr(br, 'signal_vol_resample_freq')):
                    br.signal_vol_resample_freq = None

                leverage_df = risk_engine.calculate_leverage_factor(returns_df, br.signal_vol_target, br.signal_vol_max_leverage,
                                               br.signal_vol_periods, br.signal_vol_obs_in_year,
                                               br.signal_vol_rebalance_freq, br.signal_vol_resample_freq,
                                               br.signal_vol_resample_type)

                signal_df = pandas.DataFrame(
                    signal_df.values * leverage_df.values, index = signal_df.index, columns = signal_df.columns)

                self._individual_leverage = leverage_df     # contains leverage of individual signal (before portfolio vol target)

        _pnl = calculations.calculate_signal_returns_with_tc_matrix(signal_df, returns_df, tc = tc)
        _pnl.columns = pnl_cols

        # portfolio is average of the underlying signals: should we sum them or average them?
        if hasattr(br, 'portfolio_combination'):
            if br.portfolio_combination == 'sum':
                 portfolio = pandas.DataFrame(data = _pnl.sum(axis = 1), index = _pnl.index, columns = ['Portfolio'])
            elif br.portfolio_combination == 'mean':
                 portfolio = pandas.DataFrame(data = _pnl.mean(axis = 1), index = _pnl.index, columns = ['Portfolio'])
        else:
            portfolio = pandas.DataFrame(data = _pnl.mean(axis = 1), index = _pnl.index, columns = ['Portfolio'])

        portfolio_leverage_df = pandas.DataFrame(data = numpy.ones(len(_pnl.index)), index = _pnl.index, columns = ['Portfolio'])


        # should we apply vol target on a portfolio level basis?
        if hasattr(br, 'portfolio_vol_adjust'):
            if br.portfolio_vol_adjust is True:
                risk_engine = RiskEngine()

                portfolio, portfolio_leverage_df = risk_engine.calculate_vol_adjusted_returns(portfolio, br = br)

        self._portfolio = portfolio
        self._signal = signal_df                            # individual signals (before portfolio leverage)
        self._portfolio_leverage = portfolio_leverage_df    # leverage on portfolio

        # multiply portfolio leverage * individual signals to get final position signals
        length_cols = len(signal_df.columns)
        leverage_matrix = numpy.repeat(portfolio_leverage_df.values.flatten()[numpy.newaxis,:], length_cols, 0)

        # final portfolio signals (including signal & portfolio leverage)
        self._portfolio_signal = pandas.DataFrame(
            data = numpy.multiply(numpy.transpose(leverage_matrix), signal_df.values),
            index = signal_df.index, columns = signal_df.columns)

        if hasattr(br, 'portfolio_combination'):
            if br.portfolio_combination == 'sum':
                pass
            elif br.portfolio_combination == 'mean':
                self._portfolio_signal = self._portfolio_signal / float(length_cols)
        else:
            self._portfolio_signal = self._portfolio_signal / float(length_cols)

        self._pnl = _pnl                                                            # individual signals P&L

        # TODO FIX very slow - hence only calculate on demand
        _pnl_trades = None
        # _pnl_trades = calculations.calculate_individual_trade_gains(signal_df, _pnl)
        self._pnl_trades = _pnl_trades

        self._ret_stats_pnl = RetStats()
        self._ret_stats_pnl.calculate_ret_stats(self._pnl, br.ann_factor)

        self._portfolio.columns = ['Port']
        self._ret_stats_portfolio = RetStats()
        self._ret_stats_portfolio.calculate_ret_stats(self._portfolio, br.ann_factor)

        self._cumpnl = calculations.create_mult_index(self._pnl)                             # individual signals cumulative P&L
        self._cumpnl.columns = pnl_cols

        self._cumportfolio = calculations.create_mult_index(self._portfolio)                 # portfolio cumulative P&L
        self._cumportfolio.columns = ['Port']

    def get_backtest_output(self):
        return

    def get_pnl(self):
        """
        get_pnl - Gets P&L returns

        Returns
        -------
        pandas.Dataframe
        """
        return self._pnl

    def get_pnl_trades(self):
        """
        get_pnl_trades - Gets P&L of each individual trade per signal

        Returns
        -------
        pandas.Dataframe
        """

        if self._pnl_trades is None:
            calculations = Calculations()
            self._pnl_trades = calculations.calculate_individual_trade_gains(self._signal, self._pnl)

        return self._pnl_trades

    def get_pnl_desc(self):
        """
        get_pnl_desc - Gets P&L return statistics in a string format

        Returns
        -------
        str
        """
        return self._ret_stats_signals.summary()

    def get_pnl_ret_stats(self):
        """
        get_pnl_ret_stats - Gets P&L return statistics of individual strategies as class to be queried

        Returns
        -------
        TimeSeriesDesc
        """

        return self._ret_stats_pnl

    def get_cumpnl(self):
        """
        get_cumpnl - Gets P&L as a cumulative time series of individual assets

        Returns
        -------
        pandas.DataFrame
        """

        return self._cumpnl

    def get_cumportfolio(self):
        """
        get_cumportfolio - Gets P&L as a cumulative time series of portfolio

        Returns
        -------
        pandas.DataFrame
        """

        return self._cumportfolio

    def get_portfolio_pnl(self):
        """
        get_portfolio_pnl - Gets portfolio returns in raw form (ie. not indexed into cumulative form)

        Returns
        -------
        pandas.DataFrame
        """

        return self._portfolio

    def get_portfolio_pnl_desc(self):
        """
        get_portfolio_pnl_desc - Gets P&L return statistics of portfolio as string

        Returns
        -------
        pandas.DataFrame
        """

        return self._ret_stats_portfolio.summary()

    def get_portfolio_pnl_ret_stats(self):
        """
        get_portfolio_pnl_ret_stats - Gets P&L return statistics of portfolio as class to be queried

        Returns
        -------
        RetStats
        """

        return self._ret_stats_portfolio

    def get_individual_leverage(self):
        """
        get_individual_leverage - Gets leverage for each asset historically

        Returns
        -------
        pandas.DataFrame
        """

        return self._individual_leverage

    def get_porfolio_leverage(self):
        """
        get_portfolio_leverage - Gets the leverage for the portfolio

        Returns
        -------
        pandas.DataFrame
        """

        return self._portfolio_leverage

    def get_porfolio_signal(self):
        """
        get_portfolio_signal - Gets the signals (with individual leverage & portfolio leverage) for each asset, which
        equates to what we would trade in practice

        Returns
        -------
        DataFrame
        """

        return self._portfolio_signal

    def get_signal(self):
        """
        get_signal - Gets the signals (with individual leverage, but excluding portfolio leverage) for each asset

        Returns
        -------
        pandas.DataFrame
        """

        return self._signal


########################################################################################################################

"""
TradingModel

Abstract class which wraps around Backtest, providing conveninent functions for analaysis. Implement your own
subclasses of this for your own strategy. See strategyfxcta_example.py for a simple implementation of a FX trend following
strategy.

"""

import abc
import pandas
import datetime

from chartpy import Chart, Style, ChartConstants

from finmarketpy.economics import TechParams
from findatapy.timeseries import Calculations, RetStats, Filter

class TradingModel(object):

    #### Default parameters for outputting of results from trading model
    SAVE_FIGURES = True
    DEFAULT_PLOT_ENGINE = ChartConstants().chartfactory_default_engine
    SCALE_FACTOR = ChartConstants().chartfactory_scale_factor

    DUMP_CSV = ''
    DUMP_PATH = datetime.date.today().strftime("%Y%m%d") + ' '
    chart = Chart(engine=DEFAULT_PLOT_ENGINE)

    logger = LoggerManager().getLogger(__name__)

    def __init__(self):
        pass

    # to be implemented by every trading strategy
    @abc.abstractmethod
    def load_parameters(self):
        """
        load_parameters - Fills parameters for the backtest, such as start-end dates, transaction costs etc. To
        be implemented by subclass.
        """
        return

    @abc.abstractmethod
    def load_assets(self):
        """
        load_assets - Loads time series for the assets to be traded and also for data for generating signals.
        """
        return

    @abc.abstractmethod
    def construct_signal(self, spot_df, spot_df2, tech_params):
        """
        construct_signal - Constructs signal from pre-loaded time series

        Parameters
        ----------
        spot_df : pandas.DataFrame
            Market time series for generating signals

        spot_df2 : pandas.DataFrame
            Market time series for generated signals (can be of different frequency)

        tech_params : TechParams
            Parameters for generating signals
        """
        return

    ####### Generic functions for every backtest
    def construct_strategy(self, br = None):
        """
        construct_strategy - Constructs the returns for all the strategies which have been specified.

        - gets parameters form fill_backtest_request
        - market data from fill_assets

        """

        calculations = Calculations()

        # get the parameters for backtesting
        if hasattr(self, 'br'):
            br = self.br
        elif br is None:
            br = self.load_parameters()

        # get market data for backtest
        asset_df, spot_df, spot_df2, basket_dict = self.load_assets()

        if hasattr(br, 'tech_params'):
            tech_params = br.tech_params
        else:
            tech_params = TechParams()

        cumresults = pandas.DataFrame(index = asset_df.index)
        portleverage = pandas.DataFrame(index = asset_df.index)

        from collections import OrderedDict
        ret_statsresults = OrderedDict()

        # each portfolio key calculate returns - can put parts of the portfolio in the key
        for key in basket_dict.keys():
            asset_cut_df = asset_df[[x +'.close' for x in basket_dict[key]]]
            spot_cut_df = spot_df[[x +'.close' for x in basket_dict[key]]]

            self.logger.info("Calculating " + key)

            results, backtest = self.construct_individual_strategy(br, spot_cut_df, spot_df2, asset_cut_df, tech_params, key)

            cumresults[results.columns[0]] = results
            portleverage[results.columns[0]] = backtest.get_porfolio_leverage()
            ret_statsresults[key] = backtest.get_portfolio_pnl_ret_stats()

            # for a key, designated as the final strategy save that as the "strategy"
            if key == self.FINAL_STRATEGY:
                self._strategy_pnl = results
                self._strategy_pnl_ret_stats = backtest.get_portfolio_pnl_ret_stats()
                self._strategy_leverage = backtest.get_porfolio_leverage()
                self._strategy_signal = backtest.get_porfolio_signal()
                self._strategy_pnl_trades = backtest.get_pnl_trades()

        # get benchmark for comparison
        benchmark = self.construct_strategy_benchmark()

        cumresults_benchmark = self.compare_strategy_vs_benchmark(br, cumresults, benchmark)

        self._strategy_group_benchmark_ret_stats = ret_statsresults

        if hasattr(self, '_benchmark_ret_stats'):
            ret_statslist = ret_statsresults
            ret_statslist['Benchmark'] = (self._benchmark_ret_stats)
            self._strategy_group_benchmark_ret_stats = ret_statslist

        # calculate annualised returns
        years = calculations.average_by_annualised_year(calculations.calculate_returns(cumresults_benchmark))

        self._strategy_group_pnl = cumresults
        self._strategy_group_pnl_ret_stats = ret_statsresults
        self._strategy_group_benchmark_pnl = cumresults_benchmark
        self._strategy_group_leverage = portleverage
        self._strategy_group_benchmark_annualised_pnl = years

    def construct_individual_strategy(self, br, spot_df, spot_df2, asset_df, tech_params, key):
        """
        construct_individual_strategy - Combines the signal with asset returns to find the returns of an individual
        strategy

        Parameters
        ----------
        br : BacktestRequest
            Parameters for backtest such as start and finish dates

        spot_df : pandas.DataFrame
            Market time series for generating signals

        spot_df2 : pandas.DataFrame
            Secondary Market time series for generated signals (can be of different frequency)

        tech_params : TechParams
            Parameters for generating signals

        Returns
        -------
        cumportfolio : pandas.DataFrame
        backtest : Backtest
        """
        backtest = Backtest()

        signal_df = self.construct_signal(spot_df, spot_df2, tech_params, br)   # get trading signal
        backtest.calculate_trading_PnL(br, asset_df, signal_df)            # calculate P&L

        cumpnl = backtest.get_cumpnl()

        if br.write_csv: cumpnl.to_csv(self.DUMP_CSV + key + ".csv")

        cumportfolio = backtest.get_cumportfolio()

        if br.calc_stats:
            cumportfolio.columns = [key + ' ' + str(backtest.get_portfolio_pnl_desc()[0])]
        else:
            cumportfolio.columns = [key]

        return cumportfolio, backtest

    def compare_strategy_vs_benchmark(self, br, strategy_df, benchmark_df):
        """
        compare_strategy_vs_benchmark - Compares the trading strategy we are backtesting against a benchmark

        Parameters
        ----------
        br : BacktestRequest
            Parameters for backtest such as start and finish dates

        strategy_df : pandas.DataFrame
            Strategy time series

        benchmark_df : pandas.DataFrame
            Benchmark time series
        """

        include_benchmark = False
        calc_stats = False

        if hasattr(br, 'include_benchmark'): include_benchmark = br.include_benchmark
        if hasattr(br, 'calc_stats'): calc_stats = br.calc_stats

        if include_benchmark:
            ret_stats = RetStats()
            risk_engine = RiskEngine()
            filter = Filter()
            calculations = Calculations()

            # align strategy time series with that of benchmark
            strategy_df, benchmark_df = strategy_df.align(benchmark_df, join='left', axis = 0)

            # if necessary apply vol target to benchmark (to make it comparable with strategy)
            if hasattr(br, 'portfolio_vol_adjust'):
                if br.portfolio_vol_adjust is True:
                    benchmark_df = risk_engine.calculate_vol_adjusted_index_from_prices(benchmark_df, br = br)

            # only calculate return statistics if this has been specified (note when different frequencies of data
            # might underrepresent vol
            if calc_stats:
                benchmark_df = benchmark_df.fillna(method='ffill')
                ret_stats.calculate_ret_stats_from_prices(benchmark_df, br.ann_factor)
                benchmark_df.columns = ret_stats.summary()

            # realign strategy & benchmark
            strategy_benchmark_df = strategy_df.join(benchmark_df, how='inner')
            strategy_benchmark_df = strategy_benchmark_df.fillna(method='ffill')

            strategy_benchmark_df = filter.filter_time_series_by_date(br.plot_start, br.finish_date, strategy_benchmark_df)
            strategy_benchmark_df = calculations.create_mult_index_from_prices(strategy_benchmark_df)

            self._benchmark_pnl = benchmark_df
            self._benchmark_ret_stats = ret_stats

            return strategy_benchmark_df

        return strategy_df

    def get_strategy_name(self):
        return self.FINAL_STRATEGY

    def get_individual_leverage(self):
        return self._individual_leverage

    def get_strategy_group_pnl_trades(self):
        return self._strategy_pnl_trades

    def get_strategy_pnl(self):
        return self._strategy_pnl

    def get_strategy_pnl_ret_stats(self):
        return self._strategy_pnl_ret_stats

    def get_strategy_leverage(self):
        return self._strategy_leverage

    def get_strategy_group_benchmark_pnl(self):
        return self._strategy_group_benchmark_pnl

    def get_strategy_group_benchmark_ret_stats(self):
        return self._strategy_group_benchmark_ret_stats

    def get_strategy_leverage(self):
        return self._strategy_group_leverage

    def get_strategy_signal(self):
        return self._strategy_signal

    def get_benchmark(self):
        return self._benchmark_pnl

    def get_benchmark_ret_stats(self):
        return self._benchmark_ret_stats

    def get_strategy_group_benchmark_annualised_pnl(self):
        return self._strategy_group_benchmark_annualised_pnl

    #### Plotting

    def reduce_plot(self, data_frame):
        """
        reduce_plot - Reduces the frequency of a time series to every business day so it can be plotted more easily

        Parameters
        ----------
        data_frame: pandas.DataFrame
            Strategy time series

        Returns
        -------
        pandas.DataFrame
        """
        try:
            # make plots on every business day (will downsample intraday data)
            data_frame = data_frame.resample('B')
            data_frame = data_frame.fillna(method='pad')

            return data_frame
        except:
            return data_frame

    ##### Quick helper functions to plot aspects of the strategy such as P&L, leverage etc.
    def plot_individual_leverage(self):

        style = self.create_style("Leverage", "Individual Leverage")

        try:
            self.chart.plot(self.reduce_plot(self._individual_leverage), chart_type='line', style=style)
        except: pass

    def plot_strategy_group_pnl_trades(self):

        style = self.create_style("(bp)", "Individual Trade PnL")

        # zero when there isn't a trade exit
        # strategy_pnl_trades = self._strategy_pnl_trades * 100 * 100
        # strategy_pnl_trades = strategy_pnl_trades.dropna()

        # note only works with single large basket trade
        try:
            strategy_pnl_trades = self._strategy_pnl_trades.fillna(0) * 100 * 100
            self.chart.plot(self.reduce_plot(strategy_pnl_trades), chart_type='line', style=style)
        except: pass

    def plot_strategy_pnl(self):

        style = self.create_style("", "Strategy PnL")

        try:
            self.chart.plot(self.reduce_plot(self._strategy_pnl), chart_type='line', style=style)
        except: pass

    def plot_strategy_signal_proportion(self, strip = None):

        signal = self._strategy_signal

        # count number of long, short and flat periods in our sample
        long = signal[signal > 0].count()
        short = signal[signal < 0].count()
        flat = signal[signal == 0].count()

        keys = long.index

        # how many trades have there been (ignore size of the trades)
        trades = abs(signal - signal.shift(-1))
        trades = trades[trades > 0].count()

        df_trades = pandas.DataFrame(index = keys, columns = ['Trades'], data = trades)

        df = pandas.DataFrame(index = keys, columns = ['Long', 'Short', 'Flat'])

        df['Long'] = long
        df['Short']  = short
        df['Flat'] = flat

        if strip is not None: keys = [k.replace(strip, '') for k in keys]

        df.index = keys
        df_trades.index = keys
        # df = df.sort_index()

        style = self.create_style("", "")

        try:
            style.file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Strategy signal proportion).png'
            style.html_file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Strategy signal proportion).html'
            self.chart.plot(self.reduce_plot(df), chart_type='bar', style=style)

            style.file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Strategy trade no).png'
            style.html_file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Strategy trade no).html'
            self.chart.plot(self.reduce_plot(df_trades), chart_type='bar', style=style)

        except: pass

    def plot_strategy_leverage(self):
        style = self.create_style("Leverage", "Strategy Leverage")

        try:
            self.chart.plot(self.reduce_plot(self._strategy_leverage), chart_type='line', style=style)
        except: pass

    def plot_strategy_group_benchmark_pnl(self, strip = None):

        style = self.create_style("", "Group Benchmark PnL - cumulative")

        strat_list = self._strategy_group_benchmark_pnl.columns #.sort_values()

        for line in strat_list:
            self.logger.info(line)

        # plot cumulative line of returns
        self.chart.plot(self.reduce_plot(self._strategy_group_benchmark_pnl), style=style)

        # needs write stats flag turned on
        try:
            keys = self._strategy_group_benchmark_ret_stats.keys()
            ir = []

            for key in keys: ir.append(self._strategy_group_benchmark_ret_stats[key].inforatio()[0])

            if strip is not None: keys = [k.replace(strip, '') for k in keys]

            ret_stats = pandas.DataFrame(index = keys, data = ir, columns = ['IR'])
            # ret_stats = ret_stats.sort_index()
            style.file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Group Benchmark PnL - IR) ' + style.SCALE_FACTOR + '.png'
            style.html_file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (Group Benchmark PnL - IR) ' + style.SCALE_FACTOR + '.html'
            style.display_brand_label = False

            self.chart.plot(ret_stats, chart_type='bar', style=style)

        except: pass

    def plot_strategy_group_benchmark_annualised_pnl(self, cols = None):
        # TODO - unfinished, needs checking!

        if cols is None: cols = self._strategy_group_benchmark_annualised_pnl.columns

        style = self.create_style("", "Group Benchmark Annualised PnL")
        style.color = ['red', 'blue', 'purple', 'gray', 'yellow', 'green', 'pink']

        self.chart.plot(self.reduce_plot(self._strategy_group_benchmark_annualised_pnl[cols]), chart_type='line', style=style)


    def plot_strategy_group_leverage(self):

        style = self.create_style("Leverage", "Group Leverage")
        self.chart.plot(self.reduce_plot(self._strategy_group_leverage), chart_type='line', style=style)

    def plot_strategy_signals(self, date = None, strip = None):

        ######## plot signals
        strategy_signal = self._strategy_signal
        strategy_signal = 100 * (strategy_signal)

        if date is None:
            last_day = strategy_signal.ix[-1].transpose().to_frame()
        else:
            last_day = strategy_signal.ix[date].transpose().to_frame()

        if strip is not None:
            last_day.index = [x.replace(strip, '') for x in last_day.index]

        style = self.create_style("positions (% portfolio notional)", "Positions")
        self.chart.plot(last_day, chart_type='bar', style=style)

    def create_style(self, title, file_add):
        style = Style()

        style.title = self.FINAL_STRATEGY + " " + title
        style.display_legend = True
        style.scale_factor = self.SCALE_FACTOR

        if self.DEFAULT_PLOT_ENGINE not in ['plotly', 'cufflinks'] and self.SAVE_FIGURES:
            style.file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (' + file_add + ') ' + str(style.scale_factor) + '.png'

        style.html_file_output = self.DUMP_PATH + self.FINAL_STRATEGY + ' (' + file_add + ') ' + str(style.scale_factor) + '.html'

        try:
            style.silent_display = self.SILENT_DISPLAY
        except: pass

        return style

#######################################################################################################################

"""
RiskEngine

Adjusts signal weighting according to risk constraints (volatility targeting)

"""

class RiskEngine(object):
    def calculate_vol_adjusted_index_from_prices(self, prices_df, br):
        """
        calculate_vol_adjusted_index_from_price - Adjusts an index of prices for a vol target

        Parameters
        ----------
        br : BacktestRequest
            Parameters for the backtest specifying start date, finish data, transaction costs etc.

        asset_a_df : pandas.DataFrame
            Asset prices to be traded

        Returns
        -------
        pandas.Dataframe containing vol adjusted index
        """

        calculations = Calculations()

        returns_df, leverage_df = self.calculate_vol_adjusted_returns(prices_df, br, returns=False)

        return calculations.create_mult_index(returns_df)

    def calculate_vol_adjusted_returns(self, returns_df, br, returns=True):
        """
        calculate_vol_adjusted_returns - Adjusts returns for a vol target

        Parameters
        ----------
        br : BacktestRequest
            Parameters for the backtest specifying start date, finish data, transaction costs etc.

        returns_a_df : pandas.DataFrame
            Asset returns to be traded

        Returns
        -------
        pandas.DataFrame
        """

        calculations = Calculations()

        if not returns: returns_df = calculations.calculate_returns(returns_df)

        if not (hasattr(br, 'portfolio_vol_resample_type')):
            br.portfolio_vol_resample_type = 'mean'

        if not (hasattr(br, 'portfolio_vol_resample_freq')):
            br.portfolio_vol_resample_freq = None

        leverage_df = self.calculate_leverage_factor(returns_df,
                                                     br.portfolio_vol_target, br.portfolio_vol_max_leverage,
                                                     br.portfolio_vol_periods, br.portfolio_vol_obs_in_year,
                                                     br.portfolio_vol_rebalance_freq, br.portfolio_vol_resample_freq,
                                                     br.portfolio_vol_resample_type)

        vol_returns_df = calculations.calculate_signal_returns_with_tc_matrix(leverage_df, returns_df, tc=br.spot_tc_bp)
        vol_returns_df.columns = returns_df.columns

        return vol_returns_df, leverage_df

    def calculate_leverage_factor(self, returns_df, vol_target, vol_max_leverage, vol_periods=60, vol_obs_in_year=252,
                                  vol_rebalance_freq='BM', data_resample_freq=None, data_resample_type='mean',
                                  returns=True, period_shift=0):
        """
        calculate_leverage_factor - Calculates the time series of leverage for a specified vol target

        Parameters
        ----------
        returns_df : DataFrame
            Asset returns

        vol_target : float
            vol target for assets

        vol_max_leverage : float
            maximum leverage allowed

        vol_periods : int
            number of periods to calculate volatility

        vol_obs_in_year : int
            number of observations in the year

        vol_rebalance_freq : str
            how often to rebalance

        vol_resample_type : str
            do we need to resample the underlying data first? (eg. have we got intraday data?)

        returns : boolean
            is this returns time series or prices?

        period_shift : int
            should we delay the signal by a number of periods?

        Returns
        -------
        pandas.Dataframe
        """

        calculations = Calculations()
        filter = Filter()

        if data_resample_freq is not None:
            return
            # TODO not implemented yet

        if not returns: returns_df = calculations.calculate_returns(returns_df)

        roll_vol_df = calculations.rolling_volatility(returns_df,
                                                      periods=vol_periods, obs_in_year=vol_obs_in_year).shift(
            period_shift)

        # calculate the leverage as function of vol target (with max lev constraint)
        lev_df = vol_target / roll_vol_df
        lev_df[lev_df > vol_max_leverage] = vol_max_leverage

        lev_df = filter.resample_time_series_frequency(lev_df, vol_rebalance_freq, data_resample_type)

        returns_df, lev_df = returns_df.align(lev_df, join='left', axis=0)

        lev_df = lev_df.fillna(method='ffill')
        lev_df.ix[0:vol_periods] = numpy.nan  # ignore the first elements before the vol window kicks in

        return lev_df