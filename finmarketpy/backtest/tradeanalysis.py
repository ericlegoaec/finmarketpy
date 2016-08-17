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
TradeAnalysis

Applies some basic trade analysis for a trading strategy (as defined by TradingModel). Use PyFolio to create some
basic trading statistics. Also allows you test multiple parameters for a specific strategy (like TC).

"""

pf = None

try:
    import pyfolio as pf
except: pass

import datetime

import matplotlib
import matplotlib.pyplot as plt
import pandas

from chartpy import Chart, Style, ChartConstants
from findatapy.timeseries import Calculations, Timezone
from findatapy.util.loggermanager import LoggerManager
from finmarketpy.backtest import Backtest

class TradeAnalysis(object):

    def __init__(self, engine = ChartConstants().chartfactory_default_engine):
        self.logger = LoggerManager().getLogger(__name__)
        self.DUMP_PATH = 'output_data/' + datetime.date.today().strftime("%Y%m%d") + ' '
        self.SCALE_FACTOR = 3
        self.DEFAULT_PLOT_ENGINE = engine
        self.chart = Chart(engine=self.DEFAULT_PLOT_ENGINE)

        return

    def run_strategy_returns_stats(self, trading_model):
        """
        run_strategy_returns_stats - Plots useful statistics for the trading strategy (using PyFolio)

        Parameters
        ----------
        trading_model : TradingModel
            defining trading strategy

        """

        pnl = trading_model.get_strategy_pnl()
        tz = Timezone()
        calculations = Calculations()

        # PyFolio assumes UTC time based DataFrames (so force this localisation)
        try:
            pnl = tz.localise_index_as_UTC(pnl)
        except: pass

        # set the matplotlib style sheet & defaults
        # at present this only works in Matplotlib engine
        try:
            matplotlib.rcdefaults()
            plt.style.use(ChartConstants().chartfactory_style_sheet['chartpy-pyfolio'])
        except: pass

        # TODO for intraday strategies, make daily

        # convert DataFrame (assumed to have only one column) to Series
        pnl = calculations.calculate_returns(pnl)
        pnl = pnl.dropna()
        pnl = pnl[pnl.columns[0]]
        fig = pf.create_returns_tear_sheet(pnl, return_fig=True)

        try:
            plt.savefig (trading_model.DUMP_PATH + "stats.png")
        except: pass

        plt.show()

    def run_tc_shock(self, strategy, tc = None):
        if tc is None: tc = [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2.0]

        parameter_list = [{'spot_tc_bp' : x } for x in tc]
        pretty_portfolio_names = [str(x) + 'bp' for x in tc]    # names of the portfolio
        parameter_type = 'TC analysis'                          # broad type of parameter name

        return self.run_arbitrary_sensitivity(strategy,
                                 parameter_list=parameter_list,
                                 pretty_portfolio_names=pretty_portfolio_names,
                                 parameter_type=parameter_type)

    ###### Parameters and signal generations (need to be customised for every model)
    def run_arbitrary_sensitivity(self, trading_model, parameter_list = None, parameter_names = None,
                                  pretty_portfolio_names = None, parameter_type = None):

        asset_df, spot_df, spot_df2, basket_dict = trading_model.fill_assets()

        port_list = None
        ret_stats_list = []

        for i in range(0, len(parameter_list)):
            br = trading_model.fill_backtest_request()

            current_parameter = parameter_list[i]

            # for calculating P&L
            for k in current_parameter.keys():
                setattr(br, k, current_parameter[k])

            trading_model.br = br   # for calculating signals

            signal_df = trading_model.construct_signal(spot_df, spot_df2, br.tech_params, br)

            backtest = Backtest()
            self.logger.info("Calculating... " + str(pretty_portfolio_names[i]))

            backtest.calculate_trading_PnL(br, asset_df, signal_df)
            ret_stats_list.append(backtest.get_portfolio_pnl_ret_stats())
            stats = str(backtest.get_portfolio_pnl_desc()[0])

            port = backtest.get_cumportfolio().resample('B').mean()
            port.columns = [str(pretty_portfolio_names[i]) + ' ' + stats]

            if port_list is None:
                port_list = port
            else:
                port_list = port_list.join(port)

        # reset the parameters of the strategy
        trading_model.br = trading_model.fill_backtest_request()

        style = Style()

        ir = [t.inforatio()[0] for t in ret_stats_list]

        # if we have too many combinations remove legend and use scaled shaded colour
        # if len(port_list) > 10:
            # style.color = 'Blues'
            # style.display_legend = False

        # plot all the variations
        style.resample = 'B'
        style.file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' ' + parameter_type + '.png'
        style.html_file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' ' + parameter_type + '.html'
        style.scale_factor = self.SCALE_FACTOR
        style.title = trading_model.FINAL_STRATEGY + ' ' + parameter_type

        self.chart.plot(port_list, chart_type='line', style=style)

        # plot all the IR in a bar chart form (can be easier to read!)
        style = Style()
        style.file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' ' + parameter_type + ' IR.png'
        style.html_file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' ' + parameter_type + ' IR.html'
        style.scale_factor = self.SCALE_FACTOR
        style.title = trading_model.FINAL_STRATEGY + ' ' + parameter_type
        summary = pandas.DataFrame(index = pretty_portfolio_names, data = ir, columns = ['IR'])

        self.chart.plot(summary, chart_type='bar', style=style)

        return port_list

    ###### Parameters and signal generations (need to be customised for every model)
    ###### Plot all the output seperately
    def run_arbitrary_sensitivity_separately(self, trading_model, parameter_list = None,
                                             pretty_portfolio_names = None, strip = None):

        # asset_df, spot_df, spot_df2, basket_dict = strat.fill_assets()
        final_strategy = trading_model.FINAL_STRATEGY

        for i in range(0, len(parameter_list)):
            br = trading_model.fill_backtest_request()

            current_parameter = parameter_list[i]

            # for calculating P&L
            for k in current_parameter.keys():
                setattr(br, k, current_parameter[k])

            trading_model.FINAL_STRATEGY = final_strategy + " " + pretty_portfolio_names[i]

            self.logger.info("Calculating... " + pretty_portfolio_names[i])
            trading_model.br = br
            trading_model.construct_strategy(br = br)

            trading_model.plot_strategy_pnl()
            trading_model.plot_strategy_leverage()
            trading_model.plot_strategy_group_benchmark_pnl(strip = strip)

        # reset the parameters of the strategy
        trading_model.br = trading_model.fill_backtest_request()
        trading_model.FINAL_STRATEGY = final_strategy

    def run_day_of_month_analysis(self, trading_model):
        from finmarketpy.economics.seasonality import Seasonality

        calculations = Calculations()
        seas = Seasonality()
        trading_model.construct_strategy()
        pnl = trading_model.get_strategy_pnl()

        # get seasonality by day of the month
        pnl = pnl.resample('B').mean()
        rets = calculations.calculate_returns(pnl)
        bus_day = seas.bus_day_of_month_seasonality(rets, add_average = True)

        # get seasonality by month
        pnl = pnl.resample('BM').mean()
        rets = calculations.calculate_returns(pnl)
        month = seas.monthly_seasonality(rets)

        self.logger.info("About to plot seasonality...")
        style = Style()

        # Plotting spot over day of month/month of year
        style.color = 'Blues'
        style.scale_factor = self.SCALE_FACTOR
        style.file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' seasonality day of month.png'
        style.html_file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' seasonality day of month.html'
        style.title = trading_model.FINAL_STRATEGY + ' day of month seasonality'
        style.display_legend = False
        style.color_2_series = [bus_day.columns[-1]]
        style.color_2 = ['red'] # red, pink
        style.linewidth_2 = 4
        style.linewidth_2_series = [bus_day.columns[-1]]
        style.y_axis_2_series = [bus_day.columns[-1]]

        self.chart.plot(bus_day, chart_type='line', style=style)

        style = Style()

        style.scale_factor = self.SCALE_FACTOR
        style.file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' seasonality month of year.png'
        style.html_file_output = self.DUMP_PATH + trading_model.FINAL_STRATEGY + ' seasonality month of year.html'
        style.title = trading_model.FINAL_STRATEGY + ' month of year seasonality'

        self.chart.plot(month, chart_type='line', style=style)

        return month




