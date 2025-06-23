# Create the app.py file content with dcc.Interval and callback
app_py_content = """
import dash
from dash import dcc
from dash import html
import plotly.express as px
import pandas as pd
import yfinance as yf
from datetime import datetime
import os
from dash.dependencies import Input, Output

# Ensure the Date column is in datetime format and set as index
def process_data(df):
    if isinstance(df.index, pd.DatetimeIndex):
        return df
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    return df

# Data Acquisition Function
def get_nifty_data():
    ticker = '^NSEI'
    end_date = datetime.now().strftime('%Y-%m-%d')
    # Fetch data starting from a reasonably old date to get enough historical data
    start_date = '2000-01-01'
    nifty_historical_data = yf.download(ticker, start=start_date, end=end_date)
    nifty_historical_data = process_data(nifty_historical_data)
    return nifty_historical_data

# Data Processing and Probability Calculation Function
def analyze_nifty_data(nifty_historical_data):
    # Calculate daily returns
    nifty_historical_data['Daily_Return'] = nifty_historical_data['Close'].pct_change()

    # Calculate yearly returns
    yearly_returns = nifty_historical_data['Close'].resample('Y').ffill().pct_change()
    yearly_returns = yearly_returns.dropna()

    # Calculate monthly returns for the current year
    current_year = pd.Timestamp('now').year
    current_year_data = nifty_historical_data[nifty_historical_data.index.year == current_year]
    monthly_returns_current_year = current_year_data['Close'].resample('M').ffill().pct_change()
    monthly_returns_current_year = monthly_returns_current_year.dropna()

    # Calculate the mean of historical yearly returns
    mean_yearly_return = yearly_returns.mean()

    # Identify periods of consecutive negative or zero returns
    negative_or_zero_returns = yearly_returns <= 0
    consecutive_periods = []
    start_year = None

    for i in range(len(negative_or_zero_returns)):
        if negative_or_zero_returns.iloc[i].item():
            if start_year is None:
                start_year = negative_or_zero_returns.index[i].year
        elif start_year is not None:
            consecutive_periods.append((start_year, negative_or_zero_returns.index[i-1].year))
            start_year = None

    if start_year is not None:
        consecutive_periods.append((start_year, negative_or_zero_returns.index[-1].year))

    # Calculate probabilities
    count_next_year_exceeds = 0
    count_next_two_years_exceeds = 0
    total_negative_or_zero_periods = len(consecutive_periods)

    for start_year, end_year in consecutive_periods:
        end_year_timestamp = pd.Timestamp(f'{end_year}-12-31')
        try:
            # Use method='nearest' to find the closest date if the exact date is not present
            end_year_index = yearly_returns.index.get_loc(end_year_timestamp, method='nearest')

            # Ensure the found index is within the bounds of the DataFrame
            if end_year_index < len(yearly_returns) and yearly_returns.index[end_year_index].year == end_year:
                # Check for the next year
                if end_year_index + 1 < len(yearly_returns):
                    next_year_return = yearly_returns.iloc[end_year_index + 1].item()
                    if next_year_return > mean_yearly_return.item():
                        count_next_year_exceeds += 1

                # Check for the next two years
                if end_year_index + 2 < len(yearly_returns):
                    next_two_years_return = yearly_returns.iloc[end_year_index + 2].item()
                    if next_year_return > mean_yearly_return.item() and next_two_years_return > mean_yearly_return.item():
                         count_next_two_years_exceeds += 1
        except KeyError:
             # If even the nearest method fails (unlikely for yearly data), skip this period
             continue

    probability_next_year_exceeds = count_next_year_exceeds / total_negative_or_zero_periods if total_negative_or_zero_periods > 0 else 0
    probability_next_two_years_exceeds = count_next_two_years_exceeds / total_negative_or_zero_periods if total_negative_or_zero_periods > 0 else 0

    return yearly_returns, monthly_returns_current_year, probability_next_year_exceeds, probability_next_two_years_exceeds, mean_yearly_return

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server # Needed for Gunicorn deployment

# Define the app layout
app.layout = html.Div(style={'font-family': 'Arial, sans-serif', 'padding': '20px'}, children=[
    html.H1("Nifty Index Return Dashboard", style={'textAlign': 'center', 'color': '#333'}),

    dcc.Interval(
        id='interval-component',
        interval=60*60*1000, # Update every hour (in milliseconds)
        n_intervals=0
    ),

    html.Div(style={'backgroundColor': '#f9f9f9', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
        html.H2("Historical Yearly Returns", style={'color': '#555'}),
        dcc.Graph(id='yearly-returns-graph')
    ]),

    html.Div(style={'backgroundColor': '#f9f9f9', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
        html.H2("Current Year Monthly Returns", style={'color': '#555'}),
        dcc.Graph(id='monthly-returns-graph')
    ]),

    html.Div(style={'backgroundColor': '#f9f9f9', 'padding': '15px', 'borderRadius': '5px'}, children=[
        html.H2("Mean Reversion Probabilities", style={'color': '#555'}),
        html.P("This section displays the probability of the Nifty index's return exceeding its historical average yearly return in the next one or two years, calculated based on historical periods of negative or zero returns.", style={'font-size': '14px', 'color': '#666'}),
        html.P(id='next-year-probability', style={'font-weight': 'bold'}),
        html.P(id='next-two-years-probability', style={'font-weight': 'bold'}),
        html.P(id='average-yearly-return', style={'font-style': 'italic'})
    ])
])

# Define callback to update data and graphs
@app.callback(
    [Output('yearly-returns-graph', 'figure'),
     Output('monthly-returns-graph', 'figure'),
     Output('next-year-probability', 'children'),
     Output('next-two-years-probability', 'children'),
     Output('average-yearly-return', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_data(n):
    nifty_data = get_nifty_data()
    yearly_returns, monthly_returns_current_year, probability_next_year_exceeds, probability_next_two_years_exceeds, mean_yearly_return = analyze_nifty_data(nifty_data)

    fig_yearly_returns = px.bar(yearly_returns.reset_index(), x=yearly_returns.index, y='^NSEI', title='Historical Yearly Returns',
                                color_discrete_sequence=px.colors.qualitative.Plotly) # Added color
    fig_yearly_returns.update_layout(xaxis_title='Year', yaxis_title='Return', hovermode='x unified') # Added hovermode

    fig_monthly_returns = px.bar(monthly_returns_current_year.reset_index(), x=monthly_returns_current_year.index, y='^NSEI', title='Current Year Monthly Returns',
                                 color_discrete_sequence=px.colors.qualitative.Plotly) # Added color
    fig_monthly_returns.update_layout(xaxis_title='Month', yaxis_title='Return', hovermode='x unified') # Added hovermode


    next_year_prob_text = f"Probability of next year exceeding mean return: {probability_next_year_exceeds:.2f}"
    next_two_years_prob_text = f"Probability of next two years exceeding mean return: {probability_next_two_years_exceeds:.2f}"
    average_yearly_return_text = f"Average Historical Yearly Return: {mean_yearly_return.item():.2f}"

    return fig_yearly_returns, fig_monthly_returns, next_year_prob_text, next_two_years_prob_text, average_yearly_return_text


# To run this app locally, uncomment the following:
# if __name__ == '__main__':
#     app.run_server(debug=True)
"""

# Write the app.py file
with open("app.py", "w") as f:
    f.write(app_py_content)

print("app.py updated with robust date lookup logic.")
