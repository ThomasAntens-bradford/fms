from __future__ import annotations
from typing import TYPE_CHECKING

# Third Party Imports
from IPython.display import display
import ipywidgets as widgets
import matplotlib.pyplot as plt
import pandas as pd

# Local Imports
from ..db import FMSMain, HPIVCertification, HPIVCharacteristics, HPIVRevisions
from .general_utils import HPIVParameters, LimitStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

class HPIVQuery:
    """
    Class to handle HPIV (High Pressure Isolation Valve) queries and visualizations.
    This class allows users to query HPIV data associated with a selected FMS entry using an integrated UI,
    visualize HPIV characteristics, and perform trend analysis on HPIV parameters.

    Attributes
    ----------
    session : Session
        Database session for querying HPIV data.
    fms_entry : FMSMain
        The selected FMS entry to query HPIV data for.
    certification : str | None
        The certification batch of the selected HPIV.
    characteristics : list[HPIVCharacteristics]
        List of characteristics associated with the selected HPIV.
    actions : list[str]
        List of available query actions.
    value : str
        The currently selected query action.
    all_hpivs : list[HPIVCertification]
        List of all HPIV instances in the database.
    all_certifications : list[str]
        List of all unique certification batches in the database.
    hpiv_id : str | None
        The ID of the selected HPIV.
    hpiv_from_fms : str | None
        The HPIV ID associated with the selected FMS entry.
    hpiv : HPIVCertification | None
        The selected HPIV instance.

    Methods
    -------
    hpiv_query_field()
        Creates an interactive UI for querying HPIV data.
    hpiv_status()
        Displays the status of the selected HPIV.
    hpiv_trend_analysis()
        Performs trend analysis on selected HPIV parameters.
    characteristic_trend(parameter1, parameter2, certification)
        Plots trend analysis for two selected HPIV parameters.
    evaluate_characteristics()
        Evaluates and visualizes a selected HPIV characteristic.
    plot_characteristic(parameter, certification)
        Plots the distribution of a selected HPIV characteristic across HPIVs.
        """

    def __init__(self, session: "Session", fms_entry: FMSMain = None):
        
        self.session = session
        self.fms_entry = fms_entry
        self.certification = None
        self.characteristics: list[HPIVCharacteristics] = []

        if self.fms_entry:
            self.hpiv: type[HPIVCertification] = self.fms_entry.hpiv[0] if self.fms_entry.hpiv else None
            self.hpiv_id = self.hpiv.hpiv_id if self.hpiv else None
            self.hpiv_from_fms = self.fms_entry.hpiv_id

            if not self.hpiv_id and not self.hpiv_from_fms:
                print("No HPIV associated with this FMS")
                return
            
            if not self.hpiv:
                self.hpiv_id = self.hpiv_from_fms
                self.hpiv = self.session.query(HPIVCertification).filter_by(hpiv_id = self.hpiv_id).first()

            self.characteristics = self.hpiv.characteristics
            self.certification = self.hpiv.certification if self.hpiv else None
        else:
            self.hpiv = None
            self.hpiv_id = None
            self.hpiv_from_fms = None
            self.characteristics = []
            self.certification = None

        self.actions = ["Status", "Characteristics", "Trend Analysis"]
        self.value = "Status"

        self.all_hpivs: list[HPIVCertification] = self.session.query(HPIVCertification).all()
        self.all_certifications = list(set(i.certification if not i.certification == self.certification else i.certification + \
                                           ' (Current)' if i.certification else None for i in self.all_hpivs if i.characteristics and i.certification))

    def hpiv_query_field(self) -> None:
        """
        Creates an interactive UI for querying HPIV data associated with the selected FMS entry.
        Displays dropdowns for selecting HPIV ID and query type, and shows results based on user selection.
        """
        if not self.hpiv_id and self.fms_entry:
            print("No HPIV associated with this FMS")
            return

        hpiv_field = widgets.Dropdown(
            description='HPIV ID:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'},
            value=self.hpiv_id if self.hpiv_id else None,
            disabled=True if self.hpiv_id else False,
            options=sorted([h.hpiv_id for h in self.all_hpivs if h.characteristics], key=lambda x: int(x.split('-')[-1])) if not self.hpiv_id else [self.hpiv_id]
        )

        query_field = widgets.Dropdown(
            options=self.actions if self.hpiv_id else ["Characteristics", "Trend Analysis"],
            description='Query Type:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'},
            value=self.value if self.hpiv_id else None
        )

        output = widgets.Output()

        def get_dynamic_callable(action: str) -> callable | None:
            if action == 'Status':
                return lambda: self.hpiv_status()
            elif action == 'Trend Analysis':
                return lambda: self.hpiv_trend_analysis()
            elif action == 'Characteristics':
                return lambda: self.evaluate_characteristics()
            
        def on_hpiv_change(change: dict) -> None:
            self.hpiv_id = hpiv_field.value
            self.hpiv = next((h for h in self.all_hpivs if h.hpiv_id == self.hpiv_id), None)
            self.characteristics = self.hpiv.characteristics if self.hpiv else []
            self.certification = self.hpiv.certification if self.hpiv else None
            self.all_certifications = list(set(i.certification if not i.certification == self.certification else i.certification + \
                                               ' (Current)' for i in self.all_hpivs if i.characteristics and i.certification))
            query_field.options = self.actions if self.hpiv_id else []
            query_field.value = 'Status' if self.hpiv_id else None
            with output:
                output.clear_output()
                if self.hpiv_id:
                    self.hpiv_status()

        def on_query_change(change: dict) -> None:
            action = query_field.value
            with output:
                output.clear_output()
                if action:
                    func = get_dynamic_callable(action)
                    if func:
                        func()

        query_field.observe(on_query_change, names='value')
        hpiv_field.observe(on_hpiv_change, names='value')

        form = widgets.VBox([
            widgets.HTML('<h3>HPIV Investigation</h3>'),
            hpiv_field,
            query_field,
            output
        ])

        display(form)

        if self.hpiv:
            with output:
                output.clear_output()
                self.hpiv_status()

    def hpiv_status(self) -> None:
        """
        Displays the status of the selected HPIV, including its characteristics and revisions.
        """
        color_map = {
            LimitStatus.TRUE: 'black',
            LimitStatus.FALSE: 'red',
            LimitStatus.ON_LIMIT: 'orange'
        }

        if self.hpiv:
            parameter_names = [i.parameter_name for i in self.characteristics]
            parameter_values = [i.parameter_value for i in self.characteristics]
            parameter_units = [f"[{i.unit}]" for i in self.characteristics]
            within_limits = [i.within_limits for i in self.characteristics]
            revisions: list[HPIVRevisions] = self.hpiv.revisions

            def format_value(v):
                if isinstance(v, (int, float)):
                    if abs(v) != 0 and (abs(v) < 0.001 or abs(v) > 1e5):
                        return f"{v:.3e}"
                    return round(v, 3)
                return v

            formatted_values = [format_value(v) for v in parameter_values]

            df = pd.DataFrame({
                "Parameter": parameter_names,
                "Value": formatted_values,
                "Unit": parameter_units
            })

            # Apply color styling to "Value" column based on within_limits
            def color_values(row: pd.Series) -> list[str]:
                i = row.name
                return [
                    f"color: {color_map[within_limits[i]]}" if col == "Value" else ""
                    for col in row.index
                ]

            styled_df = df.style.apply(color_values, axis=1)

            # Convert styled dataframe to HTML
            df_html = styled_df.to_html()

            # Convert revisions if they exist
            if revisions:
                revisions_df = pd.DataFrame([{
                    "Part Number": rev.part_number,
                    "Part Name": rev.part_name,
                    "Revision": rev.revision
                } for rev in revisions])

                rev_html = revisions_df.to_html(index=False)
                form = widgets.HBox([
                    widgets.HTML(value=df_html, layout=widgets.Layout(margin='10px')),
                    widgets.HTML(value=rev_html, layout=widgets.Layout(margin='10px'))
                ])
            else:
                form = widgets.HTML(value=df_html)

            display(form)

    def hpiv_trend_analysis(self) -> None:
        """
        Performs trend analysis on selected HPIV parameters.
        Provides an interactive UI for selecting parameters and certifications to analyze trends.
        """
        certification_field = widgets.Dropdown(
            options=['all'] + self.all_certifications,
            description='Choose Batch:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value='all'         
        )

        characteristic_1 = widgets.Dropdown(
            options=[i.value for i in HPIVParameters if not i == HPIVParameters.HPIV_ID],
            description='Choose Parameter:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value=HPIVParameters.RESPC_TIME.value       
        )

        characteristic_2 = widgets.Dropdown(
            options=[i.value for i in HPIVParameters if not i == characteristic_1.value and not i == HPIVParameters.HPIV_ID],
            description='Choose Parameter:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value=HPIVParameters.FLOWRATE.value      
        )

        output = widgets.Output()

        def on_char2_change(change: dict) -> None:
            characteristic_1.options = [i.value for i in HPIVParameters if not i == characteristic_2.value and not i == HPIVParameters.HPIV_ID]

        characteristic_2.observe(on_char2_change, names='value')

        def on_submit(change: dict) -> None:
            parameter1 = characteristic_1.value
            parameter2 = characteristic_2.value
            certification = certification_field.value.replace(' (Current)', '')
            with output:
                output.clear_output()
                self.characteristic_trend(parameter1, parameter2, certification)

        submit_button = widgets.Button(description="Generate")
        submit_button.on_click(on_submit)

        form = widgets.VBox([
            widgets.HTML('<h3>Choose Parameters for Trend Analysis</h3>'),
            certification_field,
            characteristic_1,
            characteristic_2,
            submit_button,
            output
        ])

        display(form)

        with output:
            output.clear_output()
            self.characteristic_trend(characteristic_1.value, characteristic_2.value, 'all')

    def characteristic_trend(self, parameter1: str, parameter2: str, certification: str) -> None:
        """
        Plots trend analysis for two selected HPIV parameters across all HPIVs or a specific certification batch.
        Args:
            parameter1 (str): The first HPIV parameter to analyze.
            parameter2 (str): The second HPIV parameter to analyze.
            certification (str): The certification batch to filter HPIVs by ('all' for all HPIVs).
        """
        parameter_check1 = next((i for i in self.characteristics if i.parameter_name == parameter1), None)
        if parameter_check1:
            parameter_value1 = parameter_check1.parameter_value
            within_limits1 = parameter_check1.within_limits
            unit1 = parameter_check1.unit

        parameter_check2 = next((i for i in self.characteristics if i.parameter_name == parameter2), None)
        if parameter_check2:
            parameter_value2 = parameter_check2.parameter_value
            within_limits2 = parameter_check2.within_limits
            unit2 = parameter_check2.unit

        pairs = []
        unit1_check = None
        unit2_check = None
        for hpiv in self.all_hpivs:
            if certification == "all" or hpiv.certification == certification:
                characteristics: list[HPIVCharacteristics] = hpiv.characteristics
                val1 = next((c.parameter_value for c in characteristics if c.parameter_name == parameter1), None)
                val2 = next((c.parameter_value for c in characteristics if c.parameter_name == parameter2), None)
                if not (unit1_check and unit2_check):
                    unit1_check = next((c.unit for c in characteristics if c.parameter_name == parameter1), None)
                    unit2_check = next((c.unit for c in characteristics if c.parameter_name == parameter2), None)
                if val1 is not None and val2 is not None:
                    pairs.append((val1, val2))

        all_parameter_values1, all_parameter_values2 = zip(*pairs) if pairs else ([], [])

        if parameter_check1 and parameter_check2:
            if certification == 'all':
                title = f"Trend Analysis of {parameter2} vs {parameter1}, {self.hpiv_id} Indicated,\n{parameter2}\
                      Limit: {within_limits2}, {parameter1} Limit: {within_limits1}"
            else:
                title = f"Trend Analysis of {parameter2} vs {parameter1}, {self.hpiv_id} ({self.certification}) Indicated,\nCompared to {certification}, {parameter2}\
                      Limit: {within_limits2},\n {parameter1} Limit: {within_limits1}"
        else:
            title = f"Trend Analysis of {parameter2} vs {parameter1} Across All HPIVs"
            unit1 = unit1_check if unit1_check else ''
            unit2 = unit2_check if unit2_check else ''
        plt.scatter(all_parameter_values1, all_parameter_values2, alpha=0.7)
        if parameter_check1 and parameter_check2:
            if parameter_value1 < 1e-4:
                parameter_value1 = f"{parameter_value1:.3E}"
            if parameter_value2 < 1e-4:
                parameter_value2 = f"{parameter_value2:.3E}"
            plt.scatter([parameter_value1], [parameter_value2], color='red', label = f'{self.hpiv_id}: {parameter_value1} [{unit1}], {parameter_value2} [{unit2}]')
        
            plt.legend(loc='lower center', bbox_to_anchor = (0.5,-0.25))
        plt.title(title)
        plt.ylabel(f"{parameter2} [{unit2}]")
        plt.xlabel(f"{parameter1} [{unit1}]")
        plt.grid(True)
        plt.show()

    def evaluate_characteristics(self) -> None:
        """
        Evaluates and visualizes a selected HPIV characteristic.
        Provides an interactive UI for selecting a characteristic and certification batch to analyze.
        """
        certification_field = widgets.Dropdown(
            options=['all'] + self.all_certifications,
            description='Choose Batch:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value='all'         
        )

        characteristic_field = widgets.Dropdown(
            options=[i.value for i in HPIVParameters if not i == HPIVParameters.HPIV_ID],
            description='Choose Parameter:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value=HPIVParameters.WEIGHT.value         
        )

        output = widgets.Output()

        def on_characteristic_change(change: dict) -> None:
            parameter = characteristic_field.value
            certification = certification_field.value.replace(' (Current)', '')
            with output:
                output.clear_output()
                self.plot_characteristic(parameter, certification)

        characteristic_field.observe(on_characteristic_change, names='value')
        certification_field.observe(on_characteristic_change, names='value')

        form = widgets.VBox([
            widgets.HTML('<h3>Choose a Parameter to Evaluate</h3>'),
            certification_field,
            characteristic_field,
            output
        ])

        display(form)

        with output:
            output.clear_output()
            self.plot_characteristic(HPIVParameters.WEIGHT.value, 'all')

    def plot_characteristic(self, parameter: str, certification: str) -> None:
        """
        Plots the distribution of a selected HPIV characteristic across HPIVs.
        Args:
            parameter (str): The HPIV parameter to plot.
            certification (str): The certification batch to filter HPIVs by ('all' for all HPIVs).
        """
        parameter_check = next((i for i in self.characteristics if i.parameter_name == parameter), None)
        if parameter_check:
            parameter_value = parameter_check.parameter_value
            within_limits = parameter_check.within_limits
            unit = parameter_check.unit
        else:
            characteristics: list[HPIVCharacteristics] = self.all_hpivs[0].characteristics if self.all_hpivs else []
            unit = next((i.unit for i in characteristics if i.parameter_name == parameter), '')

        all_characteristics: list[HPIVCharacteristics] = [j for i in self.all_hpivs for j in i.characteristics] if certification == 'all' else \
        [j for i in self.all_hpivs for j in i.characteristics if i.certification == certification]
        all_parameter_values = [i.parameter_value for i in all_characteristics if i.parameter_name == parameter]
        if certification == 'all':
            title = f"Distribution of {parameter} [{unit}], {self.hpiv_id} Indicated,\n{within_limits}" if parameter_check else \
                f"Distribution of {parameter} [{unit}] Across All HPIVs"
        else:
            title = f"Distribution of {parameter} [{unit}], {self.hpiv_id} ({self.certification}) Indicated,\n{within_limits}, Compared to {certification}" if parameter_check else \
                f"Distribution of {parameter} [{unit}] for {certification} HPIVs"
        plt.hist(all_parameter_values, bins=20, edgecolor='black')
        if parameter_check:
            plt.axvline(parameter_value, color='red', linestyle='--', label=f"{self.hpiv_id} {parameter}: {parameter_value} [{unit}]")
        
        plt.xlabel(f"{parameter} {unit}")
        plt.ylabel("Frequency")
        if parameter_check:
            plt.legend(loc='lower center', bbox_to_anchor=(0.5,-0.25))
        plt.title(title)
        plt.grid(True)
        plt.show()
