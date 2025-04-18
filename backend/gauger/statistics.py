from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import scipy

from .yahoo_finance import download_all, download, period, all_tickers


def divide_by_rolling_ma(
    series: pd.Series, window: int, return_rolling_ma=False
) -> pd.Series:
    if return_rolling_ma:
        rolling_ma = series.rolling(window=window).mean()
        return (series / rolling_ma).dropna(), rolling_ma
    else:
        return (series / series.rolling(window=window).mean()).dropna()


def pdf_ratio(series: pd.Series, window: int) -> callable:
    p_ratio = divide_by_rolling_ma(series, window)
    return density_function(list(p_ratio))


def bet_ratios_martingale_from_pdf(
    p: callable,
    min_bet: float = 1.0 / 128,
    max_bet: float = 1.0 / 2,
    n_samples_integral: int = 1000,
) -> Dict:
    n_multiples = np.log2(max_bet / min_bet)
    assert n_multiples.is_integer(), "max_bet / min_bet should be a power of 2."
    prob_underperform = integral(p, start=0, end=1)
    n_regions = n_multiples + 1
    prob_per_region = prob_underperform / n_regions

    p_ratio2bet_ratio = {1: min_bet}
    curr_bet_ratio = 2 * min_bet
    p_cum_region = 0
    x = np.linspace(0, 1, n_samples_integral)
    i = len(x) - 1
    while (curr_bet_ratio < max_bet + 1e-6) and (i > 0):
        p_cum_region += (x[i] - x[i - 1]) * p(x[i - 1])
        if p_cum_region > prob_per_region:
            p_ratio2bet_ratio[x[i - 1]] = curr_bet_ratio
            p_cum_region -= prob_per_region
            curr_bet_ratio *= 2
        i -= 1

    return p_ratio2bet_ratio


def bet_ratios_martingale(
    price: pd.Series,
    window: int,
    min_bet: float = 1.0 / 128,
    max_bet: float = 1.0 / 4,
    n_samples_integral: int = 1000,
) -> Dict:
    p = pdf_ratio(price, window)
    return bet_ratios_martingale_from_pdf(p, min_bet, max_bet, n_samples_integral)


def win_rate(price: pd.Series, window: int) -> float:
    p_ratio = divide_by_rolling_ma(price, window)

    p = density_function(list(p_ratio))

    return integral(p, p_ratio.iloc[-1])


def win_rates_all(
    start_date: str,
    end_date: str = None,
    key: str = "Close",
):
    if end_date is None:
        start_date, end_date = period(start_date)

    df, tickers = download_all(start_date, end_date)

    win_rates = {}
    for ticker in tickers:
        window2win_rate = {}
        for window in [20, 50, 100, 200]:
            df_mean = df[key][ticker].to_frame("price_ratio")
            window2win_rate[window] = win_rate(df_mean["price_ratio"], window)
        win_rates[ticker] = window2win_rate

    return win_rates


def density_function(x: List[float]):
    return scipy.stats.gaussian_kde(x)


def integral(p: callable, start: float, end=2, n_samples=1000):
    x = np.linspace(start, end, n_samples)
    return np.sum([(x[i] - x[i - 1]) * p(x[i - 1]) for i in range(1, len(x))])


def nearest_index(axis, value):
    return min(range(len(axis)), key=lambda i: abs(axis[i] - value))


def merge_dataframes(list_dataframes):
    merged_df = list_dataframes[0]
    for d in list_dataframes[1:]:
        merged_df = pd.merge(
            merged_df, d, left_index=True, right_index=True, how="inner"
        )
    return merged_df


def stock_data(
    tickers: List[str],
    start_date: str,
    end_date: str = None,
    return_moving_average=False,
):
    df = download(tickers, start_date, end_date)
    df.dropna(inplace=True)

    data = {}
    for ticker in tickers:
        df_by_window = [
            df["Close"][ticker].to_frame("price"),
            df["Volume"][ticker].to_frame("volume"),
        ]
        if return_moving_average:
            for i, window in enumerate([20, 50, 100, 200]):
                price_ratio, price_ma = divide_by_rolling_ma(
                    df["Close"][ticker], window, True
                )
                price_ratio = price_ratio.to_frame(f"price_ratio_{window}ma")
                price_ma = price_ma.to_frame(f"price_{window}ma")

                merged_df = merge_dataframes([price_ratio, price_ma])
                df_by_window.append(merged_df)

        data[ticker] = merge_dataframes(df_by_window)

    return data


def all_stock_data(
    start_date: str,
    end_date: str = None,
    return_moving_average=True,
):
    tickers = all_tickers()
    return stock_data(tickers, start_date, end_date, return_moving_average)


def distribution(
    pdf: callable, x_range: Tuple[float, float], n_points: int = 1_000, drop_thresh=1e-2
) -> Tuple[List[float], List[float]]:
    """Returns x and y values for pdf
    Args:
        pdf: probability density function p such that p(x) returns probability value
        x_range: tuple of (x_start, x_end)
        n_points: number of points on x axis
        drop_thresh: threshold for probability under which is dropped

    Returns:
        x: List of float representing x values
        y: List of float representing y values
    """
    x_start, x_end = x_range
    x = np.linspace(x_start, x_end, n_points)
    y = [pdf(i)[0] for i in x]

    if drop_thresh > 0:
        x = [x[i] for i in range(len(x)) if y[i] > drop_thresh]
        y = [y[i] for i in range(len(y)) if y[i] > drop_thresh]

    return x, y
