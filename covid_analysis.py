import os, sys
import datetime as dt
sys.path.append('/Users/andy/Work/GitHub/countryinfo')
from countryinfo import CountryInfo
import pandas as pd
import numpy as np
import bokeh
from bokeh.layouts import layout, column, gridplot
from bokeh.plotting import figure, output_file, show
from bokeh.models import ColumnDataSource, HoverTool, NumeralTickFormatter
import bokeh.palettes as bpals
from bokeh.models.widgets import CheckboxGroup

def read_settings():

    f = open('web_settings')
    ftp_loc = f.readline().rstrip('\n')
    user = f.readline().rstrip('\n')
    pw = f.readline().rstrip('\n')
    local_dir = f.readline().rstrip('\n')
    f.close()

    return ftp_loc, user, pw, local_dir

def update_local_data():
    local_dir = read_settings()[3]
    pwd = os.getcwd()
    os.chdir(local_dir + 'COVID-19')
    os.system('git fetch')
    os.system('git pull origin')
    os.chdir(pwd)

def upload_to_ftp(out_html):
    from ftplib import FTP
    from pathlib import Path

    print('Uploading to FTP')

    file_path = Path(out_html)

    ftp_loc, user, pw, local_dir = read_settings()

    with FTP(ftp_loc,  user, pw) as ftp, open(file_path, 'rb') as file:
        ftp.cwd('htdocs')
        ftp.storbinary(f'STOR {file_path.name}', file)

def days_since(df, threshold):
    '''
    For a given pandas dataframe, calculates days since the first day that >=5 deaths were recorded
    :param df: pandas dataframe. Must contain fields called 'Country' and 'Values'
    :param threshold: integer (usually 5)
    :return: pandas dataframe with an extra column
    '''
    df['DaysSince'] = 0
    for cntry in df['Country'].unique():
        # print(cntry)
        days_since = 0
        for index, row in df[df['Country'] == cntry].iterrows():
            if row['Values'] < threshold:
                days_since = 0
            else:
                days_since += 1
                df.loc[index, 'DaysSince'] = days_since

    return df

def getData(type, countries, threshold):

    update_local_data()

    local_dir = read_settings()[3]

    if type == 'deaths':
        ifile = local_dir + "COVID-19/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"
    elif type == 'cases':
        ifile = local_dir + "COVID-19/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"

    death_df = pd.read_csv(ifile)
    death_df = death_df.rename(columns={'Province/State': 'Province', 'Country/Region': 'Country'})
    cntry_deaths = death_df.groupby('Country').sum()
    cntry_deaths = cntry_deaths.reset_index()
    data2plot = pd.melt(cntry_deaths, id_vars='Country', value_vars=cntry_deaths.columns[3:], var_name='Date', value_name='Values')
    data2plot['Date'] = pd.to_datetime(data2plot['Date'])
    data2plot['DateString'] = [x.strftime('%Y-%m-%d') for x in data2plot['Date']]

    if countries == 'all':
        countries = data2plot.Country.unique()

    subset = data2plot[data2plot['Country'].isin(countries)]

    if 'Rest of World' in countries:
        subset_other = data2plot[~data2plot['Country'].isin(countries)]
        other = subset_other.groupby('Date').sum()
        tmp = pd.DataFrame({'Country': ['Rest of World' for i in np.arange(other.__len__())],
                      'Date': other.index,
                      'Values': other.Values,
                      'DateString': [x.strftime('%Y-%m-%d') for x in other.index]
                      })
        subset = subset.append(tmp)
        subset = subset.reset_index()

    subset = days_since(subset.copy(), threshold)
    subset = subset.assign(DailyChange=subset.groupby('Country')['Values'].diff())
    subset = subset.join(subset.groupby('Date')['DailyChange'].sum(), on='Date', rsuffix='_dailyGlobalTot')
    subset = subset.assign(CntryPercOfGlobal=100 * (subset.DailyChange / subset.DailyChange_dailyGlobalTot))
    subset = subset.drop(columns=['DailyChange_dailyGlobalTot'])

    subset_reshaped = subset.pivot(index='Date', columns='Country')
    subset_reshaped.columns = subset_reshaped.columns.map('_'.join)
    subset_reshaped.columns = [cn.replace('Values_','') for cn in subset_reshaped.columns]
    subset_reshaped.reset_index()
    # subset_reshaped['newDate'] = subset_reshaped.index

    source = ColumnDataSource(subset_reshaped)

    return source, subset


def make_timeseries_plot(subset, countries, settings):

    pal = settings['palette']

    p = figure(x_axis_type=settings['axis_type']['x'],
               y_axis_type=settings['axis_type']['y'],
               x_range=settings['x_range'],
               plot_width=700, plot_height=400,
               tools="xpan,xwheel_zoom,reset,crosshair,save",
               active_drag='xpan',
               active_scroll='xwheel_zoom')

    for cntry in countries:
        i = countries.index(cntry)
        srcdata = ColumnDataSource(subset[subset['Country'] == cntry])
        p.line(x=settings['data']['x'], y=settings['data']['y'], line_width=2, source=srcdata, color=pal[i], legend_label=cntry, name=cntry)
        p.circle(x=settings['data']['x'], y=settings['data']['y'], source=srcdata, color=pal[i], legend_label=cntry, name=cntry)

    p.yaxis.axis_label = settings['axis_label']['y']
    p.xaxis.axis_label = settings['axis_label']['x']
    p.title.text = settings['title']
    p.add_tools(
        HoverTool(tooltips=[("Name", "$name"), settings['hover'], ("Date", "@DateString")] ))
                          # formatters={"Date": "datetime"} )) #, mode='hline'))

    if settings['legend_loc']:
        p.legend.location = settings['legend_loc']  # "top_left"
        p.legend.label_text_font_size = '6pt'
        p.legend.glyph_height = 7
        p.legend.label_height = 7
    else:
        p.legend.visible = False

    return p

def make_stacked_plot(source, countries, settings):

    ########
    # Stacked area
    ########
    pal = settings['palette']

    s = figure(x_axis_type=settings['axis_type']['x'],
               y_axis_type=settings['axis_type']['y'],
               x_range=settings['x_range'],
               plot_width=700, plot_height=400,
               tools="xpan,xwheel_zoom,reset,crosshair,save",
               active_drag='xpan',
               active_scroll='xwheel_zoom')

    s.varea_stack(countries, x=settings['data']['x'], color=pal, source=source)
    s.vline_stack(countries, x=settings['data']['x'], color=pal, source=source)

    s.yaxis.formatter=NumeralTickFormatter(format="‘0,0’")
    s.yaxis.axis_label = settings['axis_label']['y']
    s.xaxis.axis_label = settings['axis_label']['x']
    s.title.text = settings['title']
    s.add_tools(
        HoverTool(tooltips=[("Name", "$name"), settings['hover']] ))

    if settings['legend_loc']:
        s.legend.location = settings['legend_loc']  # "top_left"
        s.legend.label_text_font_size = '6pt'
        s.legend.glyph_height = 7
        s.legend.label_height = 7

    return s

def main():
    """
    Read in some data and plot COVID stats
    """
    countries = ['China', 'United Kingdom', 'Italy', 'Spain', 'US', 'Iran', 'Korea, South', 'Australia', 'Thailand', 'Russia', 'France', 'India', 'Belgium', 'Rest of World']
    out_html = 'covid-19_monitoring.html'

    deaths_min_threshold = 5
    cases_min_threshold = 50

    source, subset = getData('deaths', countries, deaths_min_threshold)
    source_cases, subset_cases = getData('cases', countries, cases_min_threshold)

    pal = bpals.Category20[len(countries)]
    bokeh.plotting.reset_output()
    output_file(out_html)

    # For plotting
    start = dt.datetime(2020, 1, 23)
    end = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start_last30d = end - dt.timedelta(days=30)

    ###################
    # Stacked area plot
    ###################
    stacked_plot_settings = {
        'title': "Stacked COVID-19 daily deaths per country",
        'data': {'x': 'Date', 'y': countries},
        'axis_type': {'x': 'datetime', 'y': 'linear'},
        'axis_label': {'x': 'Date', 'y': 'Daily Deaths'},
        'x_range': (start, end),
        'legend_loc': None,
        'hover': ("Deaths", "$y{0,0}"),
        'palette': pal
    }

    stk = make_stacked_plot(source, countries, stacked_plot_settings)

    cols2plot = ['CntryPercOfGlobal_' + x for x in countries]
    stacked_plot_settings = {
        'title': "COVID-19 daily deaths per country as a % of global total",
        'data': {'x': 'Date', 'y': cols2plot},
        'axis_type': {'x': 'datetime', 'y': 'linear'},
        'axis_label': {'x': 'Date', 'y': 'Daily Deaths'},
        'x_range': (stk.x_range), #end - dt.timedelta(days=30)
        'legend_loc': None,
        'hover': ("Deaths", "$y{0,0}"),
        'palette': pal
    }
    stk_perc = make_stacked_plot(source, cols2plot, stacked_plot_settings)

    ########
    # Cases
    ########

    cumul_cases_plot_settings = {
        'title': "COVID-19 cumulative cases per country (log scale)",
        'data': {'x':'DaysSince', 'y':'Values'},
        'axis_type': {'x':'linear', 'y':'log'},
        'axis_label': {'x':'Days Since >'+str(cases_min_threshold)+' cases recorded', 'y':'Cases (log scale)'},
        'x_range': (10,60),
        'hover': ("Cases", "@Values{0,0}"),
        'legend_loc': None,
        'palette': pal
    }

    cumul_cases = make_timeseries_plot(subset_cases, countries, cumul_cases_plot_settings)

    # Daily Change in cases bar charts
    daily_cases_plot_settings = {
        'title': "COVID-19 new daily cases per country",
        'data': {'x':'Date', 'y':'DailyChange'},
        'axis_type': {'x':'datetime', 'y':'linear'},
        'axis_label': {'x':'Date', 'y':'Daily Reported Cases'},
        'x_range': (stk.x_range),
        'hover': ("Cases", "@DailyChange{0,0}"),
        'legend_loc': 'top_left',
        'palette': pal
    }

    daily_cases = make_timeseries_plot(subset_cases, countries, daily_cases_plot_settings)

    #########
    # Deaths
    #########
    plot_settings = {
        'title': "COVID-19 cumulative deaths per country",
        'data': {'x': 'Date', 'y': 'Values'},
        'axis_type': {'x': 'datetime', 'y': 'linear'},
        'axis_label': {'x': 'Date', 'y': 'Cumulative Deaths'},
        'x_range': (cumul_cases.x_range),
        'legend_loc': None,
        'hover': ("Deaths", "@Values{0,0}"),
        'palette': pal
    }
    # Not currently used
    p = make_timeseries_plot(subset, countries, plot_settings)

    cumul_deaths_plot_settings = {
        'title': "COVID-19 cumulative deaths per country",
        'data': {'x': 'DaysSince', 'y': 'Values'},
        'axis_type': {'x': 'linear', 'y': 'log'},
        'axis_label': {'x': 'Days Since >'+str(deaths_min_threshold)+' deaths recorded', 'y': 'Deaths (log scale)'},
        'x_range': (cumul_cases.x_range),
        'hover': ("Deaths", "@Values{0,0}"),
        'legend_loc': None,
        'palette': pal
    }

    cumul_deaths = make_timeseries_plot(subset, countries, cumul_deaths_plot_settings)

    dailydeaths_plot_settings = {
        'title': "COVID-19 new daily deaths per country",
        'data': {'x':'Date', 'y':'DailyChange'},
        'axis_type': {'x':'datetime', 'y':'linear'},
        'axis_label': {'x':'Date', 'y':'Daily Deaths'},
        'x_range': (stk.x_range),
        'hover': ("Deaths", "@DailyChange{0,0}"),
        'legend_loc': None,
        'palette': pal
    }

    daily_deaths = make_timeseries_plot(subset, countries, dailydeaths_plot_settings)

    show(gridplot([ [stk, stk_perc], [cumul_deaths,daily_deaths], [cumul_cases, daily_cases] ], toolbar_location='right')) # [deaths_stack],

    upload_to_ftp(out_html)



if __name__ == '__main__':
    main()