import numpy as np
import re
from scipy.stats import ttest_ind
import json
import os
from IPython.display import display
import ipywidgets as widgets
from pandas.io.formats.style import Styler
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression
from pandas.io.formats.style import Styler
import ipyvuetify as v
import pandas as pd
from typing import Any
from .enums import LimitStatus

def close_stats(d1: list[float], d2: list[float], rtol: float = 1e-1, atol: float = 1e-1) -> bool:
    mean_close = abs(np.mean(d1) - np.mean(d2)) <= max(rtol * max(abs(np.mean(d1)), abs(np.mean(d2))), atol)
    std_close = abs(np.std(d1) - np.std(d2)) <= max(rtol * max(abs(np.std(d1)), abs(np.std(d2))), atol)
    return mean_close and std_close

def compare_distributions(data1: list[float], data2: list[float], alpha=0.05) -> bool | None:
    """
    Compares two distributions for significant difference.
    
    Returns:
        True  → distributions are similar
        False → significant difference found
        None  → insufficient data
    """
    # t_stat, p_value = ttest_ind(data1, data2, equal_var=True)

    # if p_value < alpha:
    #     print(p_value, alpha)
    #     return False
    
    if close_stats(data1, data2):  # Pass x to close_stats
        return True

    return False

def compare_value_to_distribution(value: float, distribution: list[float], rtol: float = 1e-4, atol: float = 1e-8) -> LimitStatus:
    """
    Compare a single value to a distribution and return LimitStatus.

    - Returns TRUE if the value is clearly within mean ± std (with tolerances)
    - Returns ON_LIMIT if it's near the edge (within tolerance range)
    - Returns FALSE if it's outside the expected range
    """
    if len(distribution) == 0:
        raise ValueError("Distribution must not be empty")

    mean = np.mean(distribution)
    std = np.std(distribution)
    threshold = max(rtol * max(abs(mean), abs(value)), atol)

    lower_bound = mean - std
    upper_bound = mean + std

    if lower_bound + threshold < value < upper_bound - threshold:
        return LimitStatus.TRUE
    elif abs(value - lower_bound) <= threshold or abs(value - upper_bound) <= threshold:
        return LimitStatus.ON_LIMIT
    else:
        return LimitStatus.FALSE

def get_chunk_size(n: int, max_chunk: int | None = None) -> int:
    """
    Return a divisor of n to use as chunk size.
    If max_chunk is given, return the largest divisor <= max_chunk.
    Otherwise, return roughly half of n (or closest smaller divisor).
    """
    divisors = [i for i in range(2, n) if n % i == 0]  # skip 1
    if not divisors:
        return n  # prime, use full width

    if max_chunk:
        divisors = [d for d in divisors if d <= max_chunk]
        return divisors[-1] if divisors else n

    # Default: pick roughly half
    half = n // 2
    smaller_divisors = [d for d in divisors if d <= half]
    return smaller_divisors[-1] if smaller_divisors else divisors[0]

def display_df_in_chunks(df: pd.DataFrame | pd.io.formats.style.Styler, chunk_size: int = 15) -> None:
    """
    Display a wide DataFrame in fixed-size column chunks, stacked vertically.
    Works with both regular DataFrames and Styler objects.
    """

    # Handle Styler objects
    if isinstance(df, Styler):
        styler = df
        df = styler.data
    else:
        styler = None

    n_cols = df.shape[1]

    for start in range(0, n_cols, chunk_size):
        chunk = df.iloc[:, start:start + chunk_size]
        if styler:
            display(chunk.style)
        else:
            display(chunk)
                
def list_json_files() -> list:
    """
    List all JSON files in the 'json_cache' directory without the '.json' extension.
    
    Returns:
        list: List of JSON file names without extension.
    """
    json_cache_dir = os.path.join(os.getenv('APPDATA'), 'json_cache')
    if not os.path.exists(json_cache_dir):
        os.makedirs(json_cache_dir)
    return [f for f in os.listdir(json_cache_dir) if f.endswith('.json')]

def load_from_json(file_name: str, directory: str = "appdata") -> dict[str, Any]:
    """
    Load data from a JSON file.
    
    Args:
        file_name (str): Path to the JSON file.
        
    Returns:
        dict: Parsed JSON data.
    """

    if directory == "appdata":
        json_cache_dir = os.path.join(os.getenv('APPDATA'), 'json_cache')
    else:
        json_cache_dir = directory

    if not os.path.exists(json_cache_dir):
        os.makedirs(json_cache_dir)

    if not file_name.endswith('.json'):
        file_name += '.json'

    file_path = os.path.join(json_cache_dir, file_name)
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist.")
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_to_json(data: dict[str, Any], file_name: str, directory: str = "appdata") -> None:
    """
    Save data to a JSON file.
    
    Args:
        data (dict): Data to save.
        file_name (str): Path to the JSON file.
    """
    if directory == "appdata":
        json_cache_dir = os.path.join(os.getenv('APPDATA'), 'json_cache')
    else:
        json_cache_dir = directory
    if not os.path.exists(json_cache_dir):
        os.makedirs(json_cache_dir)
    
    file_name = os.path.join(json_cache_dir, file_name if file_name.endswith('.json') else f"{file_name}.json")
    with open(file_name, 'w') as f:
        json.dump(data, f, indent=4)

def delete_json_file(file_name: str, directory: str = "appdata") -> None:
    """
    Delete a JSON file if it exists.

    Args:
        file_name (str): Path to the JSON file.
    """
    if directory == "appdata":
        json_cache_dir = os.path.join(os.getenv('APPDATA'), 'json_cache')
    else:
        json_cache_dir = directory
    file_name = os.path.join(json_cache_dir, file_name if file_name.endswith('.json') else f"{file_name}.json")
    if os.path.exists(file_name):
        os.remove(file_name)

def extract_total_amount(text: str) -> int | None:
    text_lower = text.lower()
    text_lower = re.sub(r'[^\x00-\x7F]+', ',', text_lower)
    number_matches = list(re.finditer(r'\b\d{1,3},000\b', text_lower))

    totaal_match = re.search(r'totaal aantal', text_lower)
    if not totaal_match or not number_matches:
        return None

    return int(number_matches[0].group().replace(',', '')[:-3])

def find_intersections(x_flow: list[float], total_flow_rate: list[float], x_spec: list[float], min_flow_rate: list[float],\
                        max_flow_rate: list[float], resolution: int = 100) -> dict:
    """
    Find all (x, y) points where total_flow_rate crosses min_flow_rate or max_flow_rate,
    and compute slopes of all three curves over the refined domain.

    Parameters:
        x_flow (array-like): X-values for total flow rate (green line).
        total_flow_rate (array-like): Y-values for total flow rate.
        x_spec (array-like): X-values for spec lines.
        min_flow_rate (array-like): Y-values for minimum spec line.
        max_flow_rate (array-like): Y-values for maximum spec line.
        resolution (int): Number of points in fine-grained domain.

    Returns:
        dict: {
            'intersections': [(x1, y1), (x2, y2), ...],
            'flow_slope': array of slopes,
            'min_slope': array of slopes,
            'max_slope': array of slopes
        }
    """
    # Create fine-grained common domain
    x_min = max(min(x_flow), min(x_spec))
    x_max = min(max(x_flow), max(x_spec))
    x_fine = np.linspace(x_min, x_max, resolution)

    # Interpolate all curves onto fine domain
    flow_interp = interp1d(x_flow, total_flow_rate, bounds_error=False, fill_value=np.nan)
    min_interp = interp1d(x_spec, min_flow_rate, bounds_error=False, fill_value=np.nan)
    max_interp = interp1d(x_spec, max_flow_rate, bounds_error=False, fill_value=np.nan)

    flow_vals = flow_interp(x_fine)
    min_vals = min_interp(x_fine)
    max_vals = max_interp(x_fine)

    # Compute slopes using finite differences
    dx = np.diff(x_fine)
    flow_slope = np.diff(flow_vals) / dx
    min_slope = np.diff(min_vals) / dx
    max_slope = np.diff(max_vals) / dx

    # Find intersections
    intersections = []

    def detect_crossings(diff_array, y_array):
        for i in range(len(diff_array) - 1):
            if np.isnan(diff_array[i]) or np.isnan(diff_array[i+1]):
                continue
            if diff_array[i] * diff_array[i+1] < 0:
                t = abs(diff_array[i]) / (abs(diff_array[i]) + abs(diff_array[i+1]))
                x_cross = x_fine[i] + t * (x_fine[i+1] - x_fine[i])
                y_cross = y_array[i] + t * (y_array[i+1] - y_array[i])
                intersections.append((x_cross, y_cross))

    detect_crossings(flow_vals - min_vals, flow_vals)
    detect_crossings(flow_vals - max_vals, flow_vals)

    return {
        'intersections': intersections,
        'flow_slope': np.average(flow_slope),
        'min_slope': np.average(min_slope),
        'max_slope': np.average(max_slope)
    }

def get_slope(x: list[float], y: list[float], resolution: int = 100) -> float:
    """
    Calculate the average slope of y with respect to x using finite differences.

    Parameters:
        x (array-like): X-values.
        y (array-like): Y-values.

    Returns:
        float: Average slope (dy/dx).
    """
    x = np.array(x)
    y = np.array(y)

    x_fine = np.linspace(min(x), max(x), resolution)
    y_interp = interp1d(x, y, bounds_error=False, fill_value="extrapolate")
    y_fine = y_interp(x_fine)
    dx = np.diff(x_fine)
    dy = np.diff(y_fine)
    slopes = dy / dx
    return np.mean(slopes)


def plot_distribution(array: list[float] | None = None, part_name: str | None = None, tv_id: int | None = None, value: float | None = None,\
                       nominal: float | None = None, bins: int = 50, title: str = "Distribution", xlabel: str = "Values", ylabel: str = "Frequency") -> None:
    """
    Plots a histogram/distribution of an array and marks a specific value and optional nominal value on it.
    
    Parameters:
        array (array-like): The data to plot.
        value (float): The specific value to indicate on the distribution.
        nominal (float): The nominal/target value to indicate on the distribution.
        bins (int): Number of bins for the histogram (more bins = narrower bars, closer spacing).
        title (str): Plot title.
        xlabel (str): X-axis label.
        ylabel (str): Y-axis label.
    """

    plt.close('all')
    array = np.array(array, dtype=float)

    plt.figure(figsize=(10, 5))
    plt.hist(array, bins=bins, alpha=0.7, color='skyblue', edgecolor='black')

    # Mark the actual value
    if value is not None:
        plt.axvline(value, color='red', linestyle='--', linewidth=2, label=f'{part_name} TV ID {tv_id}: {value} [mm]')

    # Mark the nominal value if provided
    if nominal is not None:
        plt.axvline(nominal, color='green', linestyle='-', linewidth=2, label=f'Nominal = {nominal}')

    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.3), ncol=2)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def plot_simulated_distribution(nominal: float, min_val: float, max_val: float, value: float | None = None, part_name: str | None = None, tv_id: int | None = None, \
                                bins: int = 50, title: str = "Simulated Distribution", xlabel: str = "Dimension [mm]", ylabel: str = "Frequency", n_samples: int = 10000) -> None:
    """
    Simulates a normal distribution based on a nominal, min, and max value, and plots it.
    
    Parameters:
        nominal (float): The nominal/target value (mean of the distribution).
        min_val (float): The minimum value (used to estimate std deviation).
        max_val (float): The maximum value (used to estimate std deviation).
        value (float): A specific value to mark on the distribution.
        bins (int): Number of bins for the histogram.
        n_samples (int): Number of samples to generate in the simulated distribution.
        title (str): Plot title.
        xlabel (str): X-axis label.
        ylabel (str): Y-axis label.
    """
    # Estimate standard deviation assuming 99.7% of values lie within min-max (3σ rule)
    sigma = (max_val - min_val) / 6
    np.random.seed(42)
    simulated_data = np.random.normal(loc=nominal, scale=sigma, size=n_samples)

    plt.figure(figsize=(10, 5))
    plt.hist(simulated_data, bins=bins, alpha=0.7, color='skyblue', edgecolor='black')

    # Mark the actual value
    if value is not None:
        plt.axvline(value, color='red', linestyle='--', linewidth=2,
                    label=f'{part_name} TV ID {tv_id}: {value}' if part_name and tv_id else f'Value: {value}')

    # Mark the nominal value
    plt.axvline(nominal, color='green', linestyle='-', linewidth=2, label=f'Nominal = {nominal}')

    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    # plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def linear_regression(X: np.ndarray | list, y: np.ndarray | list) -> tuple:
    """
    Perform linear regression on the given data.
    Parameters:
        X (array-like): Independent variable(s).
        y (array-like): Dependent variable.
    Returns:
        model: Trained LinearRegression model.
        y_pred: Predicted values.
        coef: Coefficients of the regression.
        intercept: Intercept of the regression.
    """
    X = np.array(X)
    y = np.array(y)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    model = LinearRegression()
    model.fit(X, y)
    y_pred = model.predict(X)
    coef = model.coef_
    intercept = model.intercept_
    return model, y_pred, coef, intercept

def show_modal_popup(message: str, continue_action: callable, cancel_action: callable = None) -> None:
    """
    Display a modal popup that floats above all other widgets.
    continue_action: function executed when 'Continue Anyway' is clicked.
    """
    dialog = v.Dialog(
        v_model=True,
        persistent=True,
        max_width="500px",
        style_="position: fixed; top: 20%; left: 50%; transform: translate(-50%, 0); z-index: 9999;"
    )

    card = v.Card(children=[
        v.CardTitle(children=["Confirmation Required"]),
        v.CardText(children=[message]),
        v.CardActions(children=[
            v.Spacer(),
            v.Btn(children=["Cancel"], color="grey", text=True),
            v.Btn(children=["Continue Anyway"], color="red", text=True)
        ])
    ])

    dialog.children = [card]

    # Button handlers
    def on_cancel(widget, event, data):
        dialog.v_model = False
        if cancel_action is not None:
            cancel_action()

    def on_continue(widget, event, data):
        dialog.v_model = False
        continue_action()

    card.children[-1].children[1].on_event('click', on_cancel)
    card.children[-1].children[2].on_event('click', on_continue)

    display(dialog)

def field(description, label_width = '180px', field_width = '350px'):
    return dict(
        description=description,
        layout=widgets.Layout(width=field_width),
        style={'description_width': label_width}
    )