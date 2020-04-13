import os, sys
import datetime as dt
sys.path.append('/Users/andy/Work/GitHub/countryinfo')
from countryinfo import CountryInfo
import pandas as pd
import numpy as np
import bokeh
from bokeh.layouts import layout, column, gridplot
from bokeh.plotting import figure, output_file, show
from bokeh.models import ColumnDataSource, HoverTool, DatetimeTickFormatter
import bokeh.palettes as bpals
from bokeh.models.widgets import CheckboxGroup

def read_web_settings():

    f = open('web_settings')
    user = f.readline().rstrip('\n')
    pw = f.readline().rstrip('\n')
    f.close()

    return user, pw

def update_local_data():
    pwd = os.getcwd()
    os.chdir('/Users/andy/Work/GitHub/COVID-19')
    os.system('git fetch')
    os.system('git pull origin')
    os.chdir(pwd)

def upload_to_ftp(out_html):
    from ftplib import FTP
    from pathlib import Path

    print('Uploading to FTP')

    file_path = Path(out_html)

    user, pw = read_web_settings()

    with FTP('ftp.plus.net',  user, pw) as ftp, open(file_path, 'rb') as file:
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

    if type == 'deaths':
        ifile = "/Users/andy/Work/GitHub/COVID-19/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"
    elif type == 'cases':
        ifile = "/Users/andy/Work/GitHub/COVID-19/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"

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

    subset_reshaped = subset.pivot(index='Date', columns='Country')
    subset_reshaped.columns = subset_reshaped.columns.map('_'.join)
    subset_reshaped.columns = [cn.replace('Values_','') for cn in subset_reshaped.columns]
    subset_reshaped.reset_index()
    # subset_reshaped['newDate'] = subset_reshaped.index

    source = ColumnDataSource(subset_reshaped)

    return source, subset

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
    start = dt.datetime(2020, 3, 8)
    end = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    p = figure(x_axis_type='datetime', x_range=(start, end), plot_width=700, plot_height=400) #, tooltips=TOOLTIPS)

    # Create the checkbox selection element, available carriers is a
    # list of all airlines in the data
    cntry_selection = CheckboxGroup(labels=countries, active=[0, 1])

    for cntry in countries:
        i = countries.index(cntry)
        srcdata = ColumnDataSource(subset[subset['Country'] == cntry])
        p.line(x='Date', y='Values', line_width=2, source=srcdata, color=pal[i], legend_label=cntry, name=cntry)
        p.circle(x='Date', y='Values', source=srcdata, color=pal[i], legend_label=cntry, name=cntry)

    p.yaxis.axis_label = 'Deaths'
    p.xaxis.axis_label = 'Date'
    p.legend.location = "top_left"
    p.title.text = "COVID-19 cumulative deaths per country"
    p.add_tools(
        HoverTool(tooltips=[("Name", "$name"), ("Deaths", "@Values{0,0}"), ("Date", "@DateString")],
                          formatters={"Date": "datetime"} )) #, mode='hline'))

    r = figure(y_axis_type="log", plot_width=700, plot_height=400, x_range=(0,45)) #, tooltips=TOOLTIPS)

    for cntry in countries:
        i = countries.index(cntry)
        src_cntry = ColumnDataSource(subset[subset['Country'] == cntry])
        r.line(x='DaysSince', y="Values", line_width=2, source=src_cntry, color=pal[i], legend_label=cntry, name=cntry)
        r.circle(x='DaysSince', y="Values", source=src_cntry, color=pal[i], legend_label=cntry, name=cntry)

    # r.line(x=np.arange(45), y=10+np.exp(np.arange(45)), legend_label='y=sqrt(x)', line_color="black", line_dash="dashed")
    r.yaxis.axis_label = 'Deaths (log scale)'
    r.xaxis.axis_label = 'Days Since >'+str(deaths_min_threshold)+' deaths recorded'
    # r.legend.location = "top_left"
    r.legend.visible = False
    r.title.text = "COVID-19 cumulative deaths per country (log scale)"
    r.add_tools(
        HoverTool(tooltips=[("Name", "$name"), ("Deaths", "@Values{0,0}"), ("Date", "@DateString")],
                          formatters={"Date": "datetime"} )) #, mode='hline'))
    # show(r)

    daily_deaths = figure(x_axis_type="datetime", x_range=(start, end), plot_width=700, plot_height=400)

    for cntry in countries:
        i = countries.index(cntry)
        df = subset[subset['Country'] == cntry]
        df = df.assign(DailyChange=df.loc[:, "Values"].diff())
        src_deaths_delta = ColumnDataSource(df)
        daily_deaths.line(x='Date', y="DailyChange", line_width=2, source=src_deaths_delta, color=pal[i], legend_label=cntry, name=cntry)
        daily_deaths.circle(x='Date', y="DailyChange", source=src_deaths_delta, color=pal[i], legend_label=cntry, name=cntry)

    daily_deaths.yaxis.axis_label = 'Daily Deaths'
    daily_deaths.xaxis.axis_label = 'Date'
    daily_deaths.legend.location = "top_left"
    daily_deaths.legend.label_text_font_size = '6pt'
    daily_deaths.legend.glyph_height = 7
    daily_deaths.legend.label_height = 7
    daily_deaths.title.text = "COVID-19 new daily deaths per country"
    daily_deaths.add_tools(
        HoverTool(tooltips=[("Name", "$name"), ("Deaths", "@DailyChange{0,0}"), ("Date", "@DateString")],
                          formatters={"Date": "datetime"} )) #, mode='hline'))

    ########
    # Stacked area
    ########
    # deaths_stack = figure(x_axis_type="datetime", x_range=(start, end), plot_width=700, plot_height=400)
    #
    # for cntry in countries:
    #     i = countries.index(cntry)
    #     df = subset[subset['Country'] == cntry]
    #     df = df.assign(DailyChange=df.loc[:, "Values"].diff())
    #     src_deaths_delta = ColumnDataSource(df)
    #     deaths_stack.varea_stack(x='Date', stackers="DailyChange", source=src_deaths_delta, color=pal[i], legend_label=cntry, name=cntry)
    #     # daily_deaths.circle(x='Date', y="DailyChange", source=src_deaths_delta, color=pal[i], legend_label=cntry, name=cntry)
    #
    # deaths_stack.yaxis.axis_label = 'Daily Deaths'
    # deaths_stack.xaxis.axis_label = 'Date'
    # deaths_stack.legend.location = "top_left"
    # deaths_stack.legend.label_text_font_size = '6pt'
    # deaths_stack.legend.glyph_height = 7
    # deaths_stack.legend.label_height = 7
    # deaths_stack.title.text = "COVID-19 new daily deaths per country"
    # deaths_stack.add_tools(
    #     HoverTool(tooltips=[("Name", "$name"), ("Deaths", "@DailyChange{0,0}"), ("Date", "@DateString")],
    #                       formatters={"Date": "datetime"} )) #, mode='hline'))

    ########
    # Cases
    ########

    s = figure(y_axis_type="log", plot_width=700, plot_height=400, x_range=(0,45)) #, tooltips=TOOLTIPS)

    for cntry in countries:
        i = countries.index(cntry)
        src_cases_cntry = ColumnDataSource(subset_cases[subset_cases['Country'] == cntry])
        s.line(x='DaysSince', y="Values", line_width=2, source=src_cases_cntry, color=pal[i], legend_label=cntry, name=cntry)
        s.circle(x='DaysSince', y="Values", source=src_cases_cntry, color=pal[i], legend_label=cntry, name=cntry)

    # s.line(x=np.arange(45), y=np.sqrt(np.arange(45)), legend_label='y=sqrt(x)', line_color="black", line_dash="dashed")
    s.yaxis.axis_label = 'Cases (log scale)'
    s.xaxis.axis_label = 'Days Since >'+str(cases_min_threshold)+' cases recorded'
    # s.legend.location = "top_left"
    s.legend.visible = False
    s.title.text = "COVID-19 cumulative cases per country (log scale)"
    s.add_tools(
        HoverTool(tooltips=[("Name", "$name"), ("Cases", "@Values{0,0}"), ("Date", "@DateString")],
                          formatters={"Date": "datetime"} )) #, mode='hline'))

    # Daily Change in cases bar charts
    cases_delta = figure(x_axis_type="datetime", x_range=(start, end), plot_width=700, plot_height=400) #, tooltips=TOOLTIPS)

    for cntry in countries:
        i = countries.index(cntry)
        df = subset_cases[subset_cases['Country'] == cntry]
        df = df.assign(foo=df.loc[:,"Date"])
        df = df.assign(DailyChange=df.loc[:, "Values"].diff())
        src_cases_delta = ColumnDataSource(df)
        cases_delta.line(x='Date', y="DailyChange", line_width=2, source=src_cases_delta, color=pal[i], legend_label=cntry, name=cntry)
        cases_delta.circle(x='Date', y="DailyChange", source=src_cases_delta, color=pal[i], legend_label=cntry, name=cntry)

    # s.line(x=np.arange(45), y=np.sqrt(np.arange(45)), legend_label='y=sqrt(x)', line_color="black", line_dash="dashed")
    cases_delta.yaxis.axis_label = 'Daily Reported Cases'
    cases_delta.xaxis.axis_label = 'Date'
    cases_delta.legend.location = "top_left"
    cases_delta.legend.label_text_font_size = '6pt'
    cases_delta.legend.glyph_height = 7
    cases_delta.legend.label_height = 7
    cases_delta.title.text = "COVID-19 new daily cases per country"
    cases_delta.add_tools(
        HoverTool(tooltips=[("Name", "$name"), ("Cases", "@DailyChange{0,0}"), ("Date", "@DateString")] )) #,
                          # formatters={"foo": "datetime"} )) #, mode='hline'))

    # put all the plots in a VBox
    # show(layout([[p], [r]]))
    show(gridplot([[s, cases_delta], [r,daily_deaths]], toolbar_location='right')) # [deaths_stack],
    # show(layout([[s], [cases_delta], [p], [r], [daily_deaths]]))

    upload_to_ftp(out_html)



if __name__ == '__main__':
    main()