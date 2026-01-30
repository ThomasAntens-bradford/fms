from __future__ import annotations
from typing import TYPE_CHECKING, Any

# Third party imports
from IPython.display import display
import ipywidgets as widgets
import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from scipy.stats import norm
from sqlalchemy import func
import io
from datetime import datetime

# Local imports
from fms import FMSDataStructure
from fms.utils.general_utils import display_df_in_chunks, field
from fms.utils.specs import fms_specifications
from fms.utils.enums import LimitStatus, LPTCoefficientParameters
from fms.db import (
    ManifoldStatus, 
    LPTCalibration, 
    LPTCoefficients, 
    AnodeFR, 
    CathodeFR, 
    FRCertification, 
    FMSMain
)
import sharedBE as be
if TYPE_CHECKING:
    from sqlalchemy.orm import Session

class ManifoldQuery:
    """
    Base class for querying manifold-related data and performing analyses.
    Queries on the Manifold, FRs and LPTs are supported in this class.

    Attributes
    ----------
    session : Session
        SQLAlchemy session for database interaction.
    fms_entry : FMSMain
        FMS entry associated with the manifold.
    min_radius : float
        Minimum acceptable radius for FRs.
    max_radius : float
        Maximum acceptable radius for FRs.
    ref_thickness : float
        Reference thickness for FRs.
    thickness_tol : float
        Tolerance for thickness deviation.
    anode_reference_orifice : float
        Reference orifice diameter for anode FRs.
    cathode_reference_orifice : float
        Reference orifice diameter for cathode FRs.
    anode_target_15 : float
        Target flow rate for anode FRs at 15 bar.
    anode_target_24 : float
        Target flow rate for anode FRs at 24 bar.
    cathode_target_15 : float
        Target flow rate for cathode FRs at 15 bar.
    cathode_target_24 : float
        Target flow rate for cathode FRs at 24 bar.
    pressure_threshold : float
        Specified pressure at which the LPT signal is checked.
    signal_tolerance : float
        Tolerance for LPT signal deviation at the pressure threshold.
    signal_threshold : float
        Maximum signal at which the LPT should read the threshold pressure.
    anode_fs_error : float
        Full scale error for anode FRs.
    cathode_fs_error : float
        Full scale error for cathode FRs.
    reading_error : float
        Reading error for FR measurements.
    xenon_density : float
        Density of xenon gas.
    krypton_density : float
        Density of krypton gas.
    manifold : ManifoldStatus
        Manifold status instance associated with the FMS entry.
    set_id : str | None
        Set ID of the manifold.
    set_id_from_fms : str | None
        Set ID obtained from the FMS entry.
    lpt_certification : str | None
        LPT certification string for the associated manifold.
    actions : list[str]
        List of available actions in the UI or process.
    value : str
        Current selected action or value.
    anode : bool
        Boolean indicating whether anode operations are active.
    all_lpts : list[LPTCalibration]
        List of all LPT calibration entries from the database.
    all_lpt_certifications : list[str]
        List of all unique LPT certifications, marking the current one.
    lpt_count_dict : dict[str, int]
        Dictionary mapping each LPT certification to its count in the database.
    manifold_cert_counts : list[tuple[str, int]]
        List of tuples with manifold certification and count of associated manifolds.
    manifold_assembly_certs : list[tuple[str, str]]
        List of tuples mapping assembly certifications to concatenated set IDs.
    fr_part_certs : list[tuple[str, str, int]]
        List of tuples mapping flow restrictor certifications to part names and counts.
    all_anodes : list
        List to hold all anode FR instances.
    all_cathodes : list
        List to hold all cathode FR instances.
    all_frs : list
        List to hold all flow restrictor instances.
    output : Any
        Placeholder for any output data generated during processing.

    Methods
    -------
    manifold_query_field():
        Create interactive widgets for querying manifold data.
    manifold_set_status():
        Display the status of the current manifold (set).
    get_color(column, value, fr_entry):
        Determine the color coding for FR parameters based on limits.
    fr_remark_field(fr_entry):
        Create a clean input field for FR test remarks with properly styled widgets.
    fr_status(fr_id):
        Display the status of a specific flow restrictor (FR).
    plot_fr_results(fr_entry, fr_type):
        Plot flow rate results for a given FR entry.
    fr_certification_field(fr_id):
        Create interactive widgets for FR certification analysis (characteristics per certification).
    hagen_poiseuille(gas_type, flow_rate, thickness, orifice_diameter, viscosity):
        Calculate pressure drop using the Hagen-Poiseuille equation.
    fr_correction_simulation():
        Simulate FR correction based on orifice and thickness variations.
        Create interactive widgets for FR correction simulation.
    fr_trend_analysis(certification, fr_entry, fr_type, plot_histograms):
        Perform trend analysis on FR data based on certification.
    fr_flow_analysis(certification, fr_entry, fr_type, plot, correction):
        Perform flow analysis on FR data based on certification.
    get_new_ref(r_target, model, tolerance):
        Calculate new reference orifice diameter based on target flow rate (for simulation).
    ratio_analysis(show_errors, plot):
        Perform anode-cathode ratio analysis for the FRs.
    flow_vs_TO(fr_entry, fr_type):
        Analyze flow rate versus thickness/orifice diameter ratio for FRs.
    fr_correlation_analysis(certification, fr_entry, fr_type):
        Analyze the correlations of radius, thickness and orifice diameter with flow rate,
        for the FRs.
    pressure_drop_orifice(fr_entry, fr_type):
        Analyze the trend of Hagen-Poiseuille vs orifice diameter of the FRs.
    select_ratio():
        Helper function for selecting the anode-cathode ratio for which matches
        should be found.
    match_flow_restrictors(ratio, tolerance):
        Finds the next match of anode and cathode based on specified anode-cathode ratio,
        uses the Hopcroft-Karp algorithm to find maximum matching in a bipartite graph.
    lpt_certification_field(lpt_id):
        Create interactive widgets for LPT certification analysis.
    lpt_investigation(certification, lpt_id):
        Plots the signal at which the LPT reads the pressure threshold for each LPT,
        in a histogram.
    plot_lpt_calibration(lpt_id):
        Plot the calibration curve for a specific LPT, showing pressure vs signal
        and temperature vs resistance.
    get_lpt_status(signal, pressures):
        Determine the status of the LPT based on the signal threshold.
    query_lpt_status(all_lpts, current_lpt, certification):
        Determines which LPTs are out of spec based on the signal threshold.
    get_certifications():
        Display certification summaries for manifolds, flow restrictors and LPTs.
    """

    def __init__(self, session: "Session" = None, local: bool = True, fms_entry: FMSMain = None, min_radius: float = 0.22, max_radius: float = 0.25, ref_thickness: float = 0.25, 
                 thickness_tol: float = 0.01, anode_reference_orifice: float = 0.07095, cathode_reference_orifice: float = 0.01968,
                 anode_target_15: float = 3.006, anode_target_24: float = 4.809, cathode_target_15: float = 0.231, cathode_target_24: float = 0.370, 
                 pressure_threshold: float = 0.2, signal_tolerance: float = 0.05, signal_threshold: float = 7.5, anode_fs: float = 20, cathode_fs: float = 2,
                 fs_error: float = 0.001, reading_error: float = 0.005, xenon_density: float = 5.894, krypton_density: float = 3.749):
        
        self.fms = FMSDataStructure(local = local)
        if not bool(session):
            self.session = self.fms.Session()
        else:
            self.session = session

        self.fms_entry: type[FMSMain] = fms_entry
        self.signal_threshold = signal_threshold
        self.min_radius = min_radius
        self.max_radius = max_radius
        self.signal_tolerance = signal_tolerance
        self.pressure_threshold = pressure_threshold
        self.ref_thickness = ref_thickness
        self.thickness_tol = thickness_tol
        self.xenon_density = xenon_density
        self.krypton_density = krypton_density
        self.anode_reference_orifice = anode_reference_orifice
        self.cathode_reference_orifice = cathode_reference_orifice
        self.anode_target_15 = anode_target_15
        self.all_anodes = []
        self.all_cathodes = []
        self.anode_target_24 = anode_target_24
        self.cathode_target_15 = cathode_target_15
        self.cathode_target_24 = cathode_target_24
        self.lpt_certification = None
        self.output = None
        self.all_frs: list[AnodeFR | CathodeFR] = []

        self.anode_fs_error = fs_error*anode_fs
        self.cathode_fs_error = fs_error*cathode_fs
        self.reading_error = reading_error

        if self.fms_entry:
            self.manifold: "ManifoldStatus" = self.fms_entry.manifold[0] if self.fms_entry.manifold else None
            self.set_id = self.manifold.set_id if self.manifold else None
            self.set_id_from_fms = self.fms_entry.manifold_id if self.fms_entry else None

            if not self.set_id and not self.set_id_from_fms:
                print("No manifold associated with this FMS entry.")
                return
            
            if not self.manifold:
                self.set_id = self.set_id_from_fms
                self.manifold = self.session.query(ManifoldStatus).filter_by(set_id=self.set_id).first()

            lpt: "LPTCalibration" = self.manifold.lpt[0] if self.manifold and self.manifold.lpt else None
            self.lpt_certification = lpt.certification if lpt else None
            
        else:
            self.set_id = None
            self.manifold = None

        self.actions = ['Status', "FR Matching", 'Anode FR', 'Cathode FR', 'LPT', 'Certifications']
        self.value = 'Status'
        self.anode = True

    def _get_all_lpts(self) -> None:
        if not hasattr(self, "all_lpts"):
            self.all_lpts = self.session.query(LPTCalibration).all()
            self.all_lpt_certifications: list[str] = list(set([i.certification if not i.certification == self.lpt_certification else i.certification + ' (Current)' \
                                                    for i in self.all_lpts if i.certification]))
            
            self.lpt_count_dict = {}
            for cert in self.all_lpt_certifications:
                cert_clean = cert.replace(' (Current)', '')
                count = len([i for i in self.all_lpts if i.certification == cert_clean])
                self.lpt_count_dict[cert_clean] = count

    def _get_all_manifolds_with_sets(self) -> list[ManifoldStatus]:
        if not hasattr(self, "all_sets") or not self.all_sets:
            manifolds = self.session.query(ManifoldStatus).filter(ManifoldStatus.set_id != None).all()
            self.all_sets = manifolds
        return self.all_sets

    def _get_all_certifications(self) -> None:
        if not hasattr(self, "manifold_cert_counts") or not self.manifold_assembly_certs:
            self.manifold_cert_counts = self.session.query(
                ManifoldStatus.certification,
                func.count(ManifoldStatus.manifold_id)
            ).group_by(ManifoldStatus.certification).all()

            self.manifold_assembly_certs: list[ManifoldStatus] = (
                self.session.query(
                    ManifoldStatus.assembly_certification,
                    func.group_concat(ManifoldStatus.set_id) 
                )
                .group_by(ManifoldStatus.assembly_certification)
                .all()
            )

            self.fr_part_certs: list[FRCertification] = (
                self.session.query(
                    FRCertification.certification,
                    FRCertification.part_name,
                    func.count(FRCertification.part_id)
                )
                .group_by(
                    FRCertification.certification,
                    FRCertification.part_name
                )
                .all()
            )

    def manifold_query_field(self) -> None:
        """
        Create interactive widgets for querying manifold data.
        Creates dropdown widgets for selecting a manifold set ID, query type,
        dynamic action based on the query type, and serial ID.
        Displays the selected manifold status or performs analyses based on user selections.
        """
        if not self.set_id and self.fms_entry:
            print("No manifold associated with this FMS entry.")
            return

        manifold_field = widgets.Dropdown(
            description='Set ID:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'},
            value=self.set_id if self.set_id else None,
            disabled=True if self.set_id else False,
            options=sorted([m.set_id for m in self._get_all_manifolds_with_sets()], reverse=True) if not self.set_id else [self.set_id]
        )

        query_field = widgets.Dropdown(
            options=self.actions if self.set_id else ["FR Matching", "Anode FR", "Cathode FR", "LPT", "Certifications"],
            description='Query Type:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'},
            value=self.value if self.set_id else None
        )

        dynamic_field = widgets.Dropdown(
            options=[],
            description='Select Action:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'}
        )

        serial_field = widgets.Dropdown(
            options=[],
            description='Select ID:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '80px'}
        )

        def on_serial_change(change: dict) -> None:
            serial_val = change['new']
            # Clear dynamic field options/value whenever serial changes
            dynamic_field.options = []
            dynamic_field.value = None
            
            # If an FR is selected and the query is Anode FR or Cathode FR, allow 'Status'
            if query_field.value in ('Anode FR', 'Cathode FR') and serial_val:
                dynamic_field.options = ['Status', 'Trend Analysis']
                dynamic_field.value = 'Status'
            elif query_field.value in ('Anode FR', 'Cathode FR'):
                dynamic_field.options = ['Trend Analysis']
                dynamic_field.value = None
            elif query_field.value == 'LPT' and serial_val:
                dynamic_field.options = ['LPT Calibration', 'LPT Investigation']
                dynamic_field.value = None

        serial_field.observe(on_serial_change, names='value')

        self.output = widgets.Output()

        def get_dynamic_callable(action: str) -> callable | None:
            if action == 'Status':
                return lambda: self.fr_status(serial_field.value)
            elif action == 'Trend Analysis':
                return lambda: self.fr_certification_field(serial_field.value)
            elif action == 'LPT Calibration':
                return lambda: self.plot_lpt_calibration(serial_field.value)
            elif action == 'LPT Investigation':
                return lambda: self.lpt_certification_field(serial_field.value)
            elif action == 'Certifications':
                return lambda: self.get_certifications()
            
        def on_manifold_change(change: dict) -> None:
            new_set_id = change['new']
            self._get_all_lpts()
            with self.output:
                self.output.clear_output()
                if new_set_id:
                    self.set_id = new_set_id
                    self.manifold = self.session.query(ManifoldStatus).filter_by(set_id=new_set_id).first()
                    lpt: "LPTCalibration" = self.manifold.lpt[0] if self.manifold and self.manifold.lpt else None
                    self.lpt_certification = lpt.certification if lpt else None
                    self.all_lpt_certifications = list(set([i.certification if not i.certification == self.lpt_certification else i.certification + ' (Current)' \
                                        for i in self.all_lpts if i.certification]))
                    query_field.options = self.actions
                    query_field.value = None
                    dynamic_field.value = None
                    serial_field.options = []
                    serial_field.value = None

        def on_query_change(change: dict) -> None:
            choice = change['new']
            with self.output:
                self.output.clear_output()

            if choice == 'Status':
                dynamic_field.options = []
                dynamic_field.value = None
                serial_field.options = []
                serial_field.value = None
                with self.output:
                    self.manifold_set_status()
            elif choice in ('Anode FR', 'Cathode FR'):
                self.anode = (choice == 'Anode FR')  
                self.all_frs = self.session.query(AnodeFR if self.anode else CathodeFR).all()
                serial_field.options = sorted([fr.fr_id for fr in self.all_frs if fr.fr_id], key = lambda x: int(x.split("-")[-1]), reverse=True)
                fr: AnodeFR | CathodeFR = self.manifold.anode[0] if self.anode and self.manifold and self.manifold.anode else \
                        (self.manifold.cathode[0] if not self.anode and self.manifold and self.manifold.cathode else None)
                serial_field.value = None if not self.manifold else (fr.fr_id if fr else None)
                dynamic_field.options = ['Status', 'Trend Analysis'] if serial_field.value else ['Trend Analysis']
                dynamic_field.value = None if not serial_field.value else 'Status'
            elif choice == 'LPT':
                self._get_all_lpts()
                serial_field.options = [lpt.lpt_id for lpt in self.all_lpts if lpt.lpt_id]
                lpt: "LPTCalibration" = self.manifold.lpt[0] if self.manifold and self.manifold.lpt else None
                serial_field.value = lpt.lpt_id if lpt else None
                dynamic_field.value = None
                dynamic_field.description = "Select Action:"
            elif choice == 'Certifications':
                dynamic_field.options = []
                dynamic_field.description = "Select Action:"
                dynamic_field.value = None
                with self.output:
                    self.output.clear_output()
                    self.get_certifications()
            elif choice == "FR Matching":
                dynamic_field.options = []
                dynamic_field.description = "Select Action:"
                dynamic_field.value = None
                with self.output:
                    self.output.clear_output()
                    self.select_ratio()

        query_field.observe(on_query_change, names='value')

        def on_dynamic_change(change: dict) -> None:
            action = dynamic_field.value
            with self.output:
                self.output.clear_output()
                if action:
                    func = get_dynamic_callable(action)
                    if func:
                        func()

        dynamic_field.observe(on_dynamic_change, names='value')
        manifold_field.observe(on_manifold_change, names='value')

        self.manifold_form = widgets.VBox([
            widgets.HTML('<h3>Manifold Investigation</h3>'),
            manifold_field,
            query_field,
            serial_field,
            dynamic_field,
            self.output
        ])

        display(self.manifold_form)

        # Initial display if manifold exists
        if self.manifold:
            with self.output:
                self.output.clear_output()
                self.manifold_set_status()

    def manifold_set_status(self) -> None:
        """
        Display the status of the current manifold (set).
        """
        if self.manifold:
            columns = [c.name for c in ManifoldStatus.__table__.columns]
            values = [getattr(self.manifold, c) for c in columns]
            df = pd.DataFrame({"Field": columns, "Value": values})
            display_df_in_chunks(df)

    def get_color(self, column: str, value: float, fr_entry: AnodeFR | CathodeFR) -> str:
        """
        Determine the color coding for FR parameters based on limits.
        """
        if column == 'radius':
            if value and (value < self.min_radius or value > self.max_radius):
                return 'red'
            else:
                return 'black'
        elif column == 'thickness':
            if value and abs(value - self.ref_thickness) > self.thickness_tol:
                return 'red'
            else:
                return 'black'
        elif column == 'orifice_diameter' or column == 'deviation':
            if fr_entry.deviation >= 10:
                return 'red'
        return 'black'
    
    def fr_remark_field(self, fr_entry: AnodeFR | CathodeFR) -> None:
        """
        Create a clean input field for FR test remarks with properly styled widgets.
        """
        label_width = '150px'
        field_width = '600px'
        
        title = widgets.HTML("<h3>Add or change remark if necessary</h3>")
        remark = fr_entry.remark

        def field(description):
            return {
                'description': description,
                'style': {'description_width': label_width},
                'layout': widgets.Layout(width=field_width, height='50px')
            }

        # Remark input
        remark_widget = widgets.Textarea(**field("Remark:"), value = remark if remark else "")

        # Submit button
        submit_button = widgets.Button(
            description="Submit",
            button_style="success",
            layout=widgets.Layout(width='150px', margin='10px 0px 0px 160px')  # align under field
        )

        submitted = {'done': False}
        output = widgets.Output()

        # Form layout
        form = widgets.VBox([
            title,
            widgets.HBox([remark_widget]),
            submit_button,
            output
        ], layout=widgets.Layout(
            border='1px solid #ccc',
            padding='20px',
            width='fit-content',
            gap='15px',
            background_color="#f9f9f9"
        ))

        display(form)

        # Submission handler
        def on_submit_clicked(b):
            with output:
                output.clear_output()
                new_remark = remark_widget.value.strip()
                if not new_remark:
                    print("Please enter a remark before submitting.")
                    return

                if new_remark == remark:
                    print("Already submitted!")
                else:
                    fr_entry.remark = new_remark
                    self.session.commit()
                    print("Remark Submitted!")
                    with self.output:
                        self.output.clear_output()
                        self.fr_status(fr_id = fr_entry.fr_id)
                
        submit_button.on_click(on_submit_clicked)

            
    def fr_status(self, fr_id: str = None) -> None:
        """
        Display the status of a specific flow restrictor (FR).
        Shows FR parameters and status in a styled DataFrame and plots flow rate results.
        """
        model = AnodeFR if self.anode else CathodeFR
        fr_type = "Anode" if self.anode else "Cathode"

        if self.manifold:
            m_entry = self.manifold.anode if self.anode else self.manifold.cathode
            inside_manifold = bool(m_entry and fr_id == m_entry[0].fr_id)

            if inside_manifold:
                if not m_entry:
                    print(f"No {fr_type} entries found for this manifold.")
                    return
                fr_entry = m_entry[0]
                anode_fr_entry = self.manifold.anode 
                cathode_fr_entry = self.manifold.cathode
            else:
                fr_entry = self.session.query(model).filter_by(fr_id=fr_id).first()
                if not fr_entry:
                    print(f"No FR entry found with ID {fr_id}.")
                    return
                anode_fr_entry = self.session.query(AnodeFR).filter_by(fr_id=fr_id).all() if self.anode else None
                cathode_fr_entry = self.session.query(CathodeFR).filter_by(fr_id=fr_id).all() if not self.anode else None
        else:
            fr_entry = self.session.query(model).filter_by(fr_id=fr_id).first()
            if not fr_entry:
                print(f"No FR entry found with ID {fr_id}.")
                return
            anode_fr_entry = self.session.query(AnodeFR).filter_by(fr_id=fr_id).all() if self.anode else None
            cathode_fr_entry = self.session.query(CathodeFR).filter_by(fr_id=fr_id).all() if not self.anode else None

        self.fr_remark_field(fr_entry)
        columns = [c.name for c in fr_entry.__table__.columns if c.name not in ('pressures', 'flow_rates', 'pressure_drop', 'tools', 'extra_tests')]
        values = [round(getattr(fr_entry, c), 3) if isinstance(getattr(fr_entry, c), (float, int)) else getattr(fr_entry, c) for c in columns]
        df = pd.DataFrame({"Field": columns, "Value": values})

        tools: list[dict[str, str]] = fr_entry.tools
        all_tools = be.tools.get_all_test_tools()
        tool_cols = be.tools.__columns__
        df_data = []

        def get_data(tool: be.db.TestingTools, column: str):
            value = getattr(tool, column)
            if isinstance(value, (datetime,)):
                return value.strftime("%d-%m-%Y")
            elif column == "description":
                return " ".join(value.split("_")).title()
            return value

        for tool in tools:
            model = tool.get("model")
            serial = tool.get("serial_number")
            description = tool.get("description")
            matching_tool = next(
                (t for t in all_tools if t.model == model and t.serial_number == serial and t.description == description),
                None
            )
            if matching_tool is None:
                continue  

            df_row = {" ".join(c.name.split("_")).title(): get_data(matching_tool, c.name) for c in tool_cols if c.name != "id"}
            df_data.append(df_row)

        tools_df = pd.DataFrame(df_data)

        def style_value(val, row):
            col_name = row['Field']
            return f'color: {self.get_color(col_name, val, fr_entry)}'
        
        def format_numeric(x):
            return f"{x:.3f}" if isinstance(x, (float, int)) else x

        styled_df = df.style.format({"Value": format_numeric}).apply(
            lambda row: [style_value(row['Value'], row) if col == 'Value' else '' for col in df.columns],
            axis=1
        )

        display(styled_df)
        display(widgets.HTML(f"<h2>Tools used for testing FR {fr_entry.fr_id}</h2>"))
        display(tools_df.style.hide(axis='index'))

        anode_fr_entry = anode_fr_entry[0] if anode_fr_entry else None
        cathode_fr_entry = cathode_fr_entry[0] if cathode_fr_entry else None
        self.anode_flows = anode_fr_entry.flow_rates if anode_fr_entry else []
        self.cathode_flows = cathode_fr_entry.flow_rates if cathode_fr_entry else []
        self.anode_pressures = anode_fr_entry.pressures if anode_fr_entry else []
        self.cathode_pressures = cathode_fr_entry.pressures if cathode_fr_entry else []
        self.anode_pressure_drops = anode_fr_entry.pressure_drop if anode_fr_entry else []
        self.cathode_pressure_drops = cathode_fr_entry.pressure_drop if cathode_fr_entry else []
        self.extra_flows: dict[str, list[float]] = anode_fr_entry.extra_tests if fr_type == "Anode" else cathode_fr_entry.extra_tests

        if self.anode_flows or self.cathode_flows:
            # plt.plot(self.cathode_pressures, self.cathode_pressure_drops)
            # plt.show()
            self.plot_fr_results(fr_entry, fr_type)

    def plot_fr_results(self, fr_entry: AnodeFR | CathodeFR, fr_type: str) -> None:
        """
        Plot flow rate and pressure drop results for a given FR entry.
        If pressure drops are available, show two subplots side by side.
        Otherwise, show a single flow rate plot.
        """
        gas_type = fr_entry.gas_type
        ratio_spec = self.manifold.ac_ratio_specified if self.manifold else 13

        has_pressure_drops = bool((self.anode_pressure_drops or self.cathode_pressure_drops))

        if has_pressure_drops:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6), sharey=False)
        else:
            fig, ax1 = plt.subplots(figsize=(8, 6))
            ax2 = None  # no second axis

        # --- LEFT PANEL: Flow vs Pressure ---
        if self.anode_flows and self.cathode_flows:
            ax1.plot(
                self.anode_pressures, self.anode_flows,
                linestyle='-', color='tab:blue',
                label=f'Anode Flow Rate [mg/s {gas_type}]'
            )
            ax1.plot(
                self.cathode_pressures, self.cathode_flows,
                linestyle='-', color='tab:orange',
                label=f'Cathode Flow Rate [mg/s {gas_type}]'
            )
            ax1.set_xlabel('Pressure [bar]')
            ax1.set_ylabel(f'Flow Rate [mg/s {gas_type}]')
            ax1.grid(True)

            # Right axis for ratio
            ax1_ratio = ax1.twinx()
            ratio = np.array(self.anode_flows) / np.array(self.cathode_flows)
            ax1_ratio.plot(
                self.anode_pressures, ratio,
                linestyle='--', color='tab:green',
                label='Anode/Cathode Ratio'
            )
            ax1_ratio.axhline(y=ratio_spec+0.5, color='r', linestyle='-', label=f'Ratio Tolerance: {ratio_spec}')
            ax1_ratio.axhline(y=ratio_spec-0.5, color='r', linestyle='-')
            ax1_ratio.set_ylabel('Anode/Cathode Ratio')
            ax1_ratio.set_ylim(ratio_spec - 3, ratio_spec + 3)

            # Combine legends
            lines, labels = ax1.get_legend_handles_labels()
            lines2, labels2 = ax1_ratio.get_legend_handles_labels()
            ax1.legend(lines + lines2, labels + labels2, loc='lower center', bbox_to_anchor=(0.5, -0.35), ncol=2)
        else:
            flows = self.anode_flows if self.anode_flows else self.cathode_flows
            pressures = self.anode_pressures if self.anode_flows else self.cathode_pressures
            label = 'Anode' if self.anode_flows else 'Cathode'
            ax1.plot(
                pressures, flows,
                linestyle='-', color='tab:blue',
                label=f'{label} Flow Rate [mg/s {gas_type}]'
            )
            for test_id, flows in self.extra_flows.items():
                ax1.plot(
                    pressures, flows,
                    linestyle='-', color=plt.get_cmap('tab10')(hash(test_id) % 10),
                    label=f'Extra Test: {test_id.replace("_", " ").title()}'
                )

            ax1.set_xlabel('Pressure [bar]')
            ax1.set_ylabel(f'Flow Rate [mg/s {gas_type}]')
            ax1.grid(True)
            ax1.legend(loc='lower center', bbox_to_anchor=(0.5, -0.3), ncol=2)

        ax1.set_title('Flow Rate vs Pressure')

        # --- RIGHT PANEL: Pressure Drop vs Pressure ---
        if has_pressure_drops and ax2:
            if self.anode_pressure_drops and self.cathode_pressure_drops:
                ax2.plot(
                    self.anode_pressures, self.anode_pressure_drops,
                    linestyle='-', color='tab:blue',
                    label='Anode Pressure Drop [Pa]'
                )
                ax2.plot(
                    self.cathode_pressures, self.cathode_pressure_drops,
                    linestyle='-', color='tab:orange',
                    label='Cathode Pressure Drop [Pa]'
                )
                ax2.set_yticks(np.arange(0, max(max(self.anode_pressure_drops), max(self.cathode_pressure_drops)) + 10, 10))
            else:
                pressure_drops = self.anode_pressure_drops if self.anode_pressure_drops else self.cathode_pressure_drops
                pressures = self.anode_pressures if self.anode_pressure_drops else self.cathode_pressures
                label = 'Anode' if self.anode_pressure_drops else 'Cathode'
                if pressure_drops:
                    ax2.plot(
                        pressures, pressure_drops,
                        linestyle='-', color='tab:blue',
                        label=f'{label} Pressure Drop [Pa]'
                    )
                    step_size = 2 if self.anode_pressure_drops else 10
                    ax2.set_yticks(np.arange(0, max(pressure_drops) + step_size, step_size))
            ax2.set_xlabel('Pressure [bar]')
            ax2.set_ylabel('Pressure Drop [Pa]')
            ax2.grid(True)
            ax2.legend(loc='lower center', bbox_to_anchor=(0.5, -0.25), ncol=2)

            ax2.set_title('Pressure Drop vs Pressure')

        # --- FIGURE TITLE ---
        fig.suptitle(
            f'Flow Rate and Pressure Drop {gas_type} in {fr_type} {fr_entry.fr_id}, '
            f'Temperature: {fr_entry.temperature} [°C]', fontsize=14
        )
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        plt.show()

    def get_anodes_with_flow_rates(self):
        self.all_anodes = self.session.query(AnodeFR).filter(AnodeFR.flow_rates != None).all()

    def get_cathodes_with_flow_rates(self):
        self.all_cathodes = self.session.query(CathodeFR).filter(CathodeFR.flow_rates != None).all()

    def _get_certifications_from_frs(self, fr_list: list[AnodeFR | CathodeFR]) -> list[str]:
        return list(set(
            ["-".join(i.fr_id.split("-")[:-1]) for i in fr_list]
        ))

    def fr_certification_field(self, fr_id: str = None) -> None:
        """
        Create interactive widgets for FR certification analysis (characteristics per certification).
        Allows selection of certification, analysis type, and plotting options.
        """
        if self.manifold and not fr_id:
            if self.anode:
                fr_entry = self.manifold.anode[0] if self.manifold.anode else None
                fr_type = "Anode"
            else:
                fr_entry = self.manifold.cathode[0] if self.manifold.cathode else None
                fr_type = "Cathode"
            
            if not fr_entry:
                print(f"No {fr_type} entries found for this manifold.")
                return
        elif fr_id:
            fr_entry = self.session.query(AnodeFR if self.anode else CathodeFR).filter_by(fr_id=fr_id).first()
            if not fr_entry:
                print(f"No FR entry found with ID {fr_id}.")
                return
            fr_type = "Anode" if self.anode else "Cathode"
        else:
            fr_entry = None
            fr_type = "Anode" if self.anode else "Cathode"

        self.fr_current_certification = "-".join(fr_entry.fr_id.split("-")[:-1]) if fr_entry else None
        self.all_fr_certifications = list(set(
            ["-".join(i.fr_id.split("-")[:-1]) if "-".join(i.fr_id.split("-")[:-1]) != self.fr_current_certification 
            else self.fr_current_certification + " (Current)" for i in self.all_frs]
        ))

        certification_field = widgets.SelectMultiple(
            options=['all'] + self.all_fr_certifications,
            description='Select Certification:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value=('all',)
        )

        analysis_type = widgets.Dropdown(
            options=['Dimensional Analysis', 'Flow Analysis', 'Correlation Analysis'],
            description='Analysis Type:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value='Dimensional Analysis'
        )

        histogram_toggle = widgets.Checkbox(
            value=False,
            description='Plot Histograms',
            indent=False
        )

        show_errors = widgets.Checkbox(
            value=False,
            description='Show Errors',
            indent=False
        )

        flow_type_analysis = widgets.Dropdown(
            options=["Flow vs Orifice", "Ratio Analysis", "Flow vs T/O", "Pressure Drop", "FR Correction Simulation"],
            description='Flow Analysis Type:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value="Flow vs Orifice"
        )

        output = widgets.Output()

        def get_flow_callable(flow_type: str) -> callable | None:
            if flow_type == 'Flow vs Orifice':
                certifications = certification_field.value
                if certifications:
                    certifications = [i.replace(" (Current)", "") for i in certifications]
                    if "all" in certifications:
                        certifications = "all"
                else:
                    certifications = "all"
                return lambda: self.fr_flow_analysis(
                    certifications,
                    fr_type = fr_type,
                    fr_entry = fr_entry,
                    error=show_errors.value
                )
            elif flow_type == 'Ratio Analysis':
                return lambda: self.ratio_analysis(show_errors.value)
            elif flow_type == 'Flow vs T/O':
                return lambda: self.flow_vs_TO(fr_entry=fr_entry, fr_type=fr_type)
            elif flow_type == 'Pressure Drop':
                return lambda: self.pressure_drop_orifice(fr_entry=fr_entry, fr_type=fr_type)
            elif flow_type == 'FR Correction Simulation':
                self.get_anodes_with_flow_rates()
                self.get_cathodes_with_flow_rates()
                return lambda: self.fr_correction_simulation()

        def run_flow_analysis() -> None:
            func = get_flow_callable(flow_type_analysis.value)
            with output:
                if func:
                    func()

        def run_analysis() -> None:
            certifications = certification_field.value
            if certifications:
                certifications = [i.replace(" (Current)", "") for i in certifications]
                if "all" in certifications:
                    certifications = "all"
            else:
                certifications = "all"
            with output:
                output.clear_output()
                if analysis_type.value == 'Dimensional Analysis':
                    display(histogram_toggle)
                    self.fr_trend_analysis(certifications, fr_entry, fr_type, histogram_toggle.value)
                elif analysis_type.value == 'Flow Analysis':
                    flow_form = widgets.VBox([flow_type_analysis, show_errors])
                    display(flow_form)
                    run_flow_analysis()
                elif analysis_type.value == 'Correlation Analysis':
                    self.fr_correlation_analysis(certifications, fr_entry, fr_type)

        # Observers
        certification_field.observe(lambda change: run_analysis(), names='value')
        histogram_toggle.observe(lambda change: run_analysis(), names='value')
        analysis_type.observe(lambda change: run_analysis(), names='value')
        show_errors.observe(lambda change: run_analysis(), names='value')
        flow_type_analysis.observe(lambda change: run_analysis(), names='value')

        form = widgets.VBox([
            widgets.HTML('<h3>Select Batch for Comparison</h3>'),
            certification_field,
            analysis_type,
            output
        ])
        display(form)

        with output:
            output.clear_output()
            run_analysis()

    def hagen_poiseuille(self, gas_type: str, flow_rate: float, thickness: float, orifice_diameter: float, viscosity: float = 1e-6) -> float | None:
        """
        Calculate the pressure drop across an orifice using the Hagen-Poiseuille equation.
        Args:
            gas_type (str): Type of gas ('Xe' for Xenon, 'Kr' for Krypton).
            flow_rate (float): Flow rate in mg/s.
            thickness (float): Thickness of the orifice in mm.
            orifice_diameter (float): Diameter of the orifice in mm.
            viscosity (float): Dynamic viscosity of the gas in Pa.s (default is 1e-6 Pa.s).
        Returns:
            float | None: Calculated pressure drop in bar, or None if gas type is invalid.
        """
        pressure_drop = viscosity*flow_rate*thickness/orifice_diameter**4*1000/self.xenon_density if gas_type == "Xe" \
            else viscosity*flow_rate*thickness/orifice_diameter**4*1000/self.krypton_density if gas_type == "Kr" else None
        return pressure_drop
    
    def fr_correction_simulation(self) -> None:
        """
        Simulate the effect of orifice diameter and thickness variations on flow rates and ratios.
        """
        all_anodes = self.session.query(AnodeFR).filter(AnodeFR.flow_rates != None, AnodeFR.allocated == None, AnodeFR.set_id == None).all()
        all_cathodes = self.session.query(CathodeFR).filter(CathodeFR.flow_rates != None, CathodeFR.allocated == None, CathodeFR.set_id == None).all()
        standard_ratio = 13

        # Batch selection widgets
        anode_batch_field = widgets.Dropdown(
            description='Anode Batch:',
            layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'},
            options=['all'] + list(set(["-".join(a.fr_id.split("-")[:-1]) for a in all_anodes])),
            value='all'
        )

        cathode_batch_field = widgets.Dropdown(
            description='Cathode Batch:',
            layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'},
            options=['all'] + list(set(["-".join(c.fr_id.split("-")[:-1]) for c in all_cathodes])),
            value='all'
        )

        # Function to compute batch means for default widget values
        def batch_mean_orifice(batch, fr_list):
            selected = [fr.orifice_diameter for fr in fr_list if batch == 'all' or fr.fr_id.startswith(batch)]
            return float(np.mean(selected)), float(np.std(selected)) if selected else (0.0, 0.0)

        batch_anode = batch_mean_orifice(anode_batch_field.value, all_anodes)
        batch_cathode = batch_mean_orifice(cathode_batch_field.value, all_cathodes)

        # Orifice and tolerance widgets (default to batch mean)
        anode_orifice_field = widgets.FloatText(
            description='Anode Orifice [mm]:',
            layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'},
            value=batch_anode[0]
        )
        cathode_orifice_field = widgets.FloatText(
            description='Cathode Orifice [mm]:',
            layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'},
            value=batch_cathode[0]
        )
        anode_tolerance_field = widgets.FloatText(
            description='Anode Tolerance [mm]:', layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'}, value=batch_anode[1]
        )
        cathode_tolerance_field = widgets.FloatText(
            description='Cathode Tolerance [mm]:', layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'}, value=batch_cathode[1]
        )

        thickness_field = widgets.FloatText(
            description='Thickness [mm]:', layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'}, value=self.ref_thickness
        )
        thickness_tol_field = widgets.FloatText(
            description='Std Dev Thickness [mm]:', layout=widgets.Layout(width='300px'),
            style={'description_width': '150px'}, value=0.01
        )

        perform_button = widgets.Button(
            description='Perform Simulation', button_style='success',
            layout=widgets.Layout(width='200px', margin='10px 0px 0px 0px')
        )
        output = widgets.Output()

        # Update widget defaults when batch changes
        def update_orifice_defaults(change):
            batch_anode = batch_mean_orifice(anode_batch_field.value, all_anodes)
            batch_cathode = batch_mean_orifice(cathode_batch_field.value, all_cathodes)
            anode_orifice_field.value = batch_anode[0]
            anode_tolerance_field.value = batch_anode[1]
            cathode_orifice_field.value = batch_cathode[0]
            cathode_tolerance_field.value = batch_cathode[1]

        anode_batch_field.observe(update_orifice_defaults, names='value')
        cathode_batch_field.observe(update_orifice_defaults, names='value')

        # Simulation function
        def simulate_and_plot(anode_batch, cathode_batch,
                            anode_orifice, cathode_orifice,
                            anode_tol, cathode_tol,
                            ref_thickness, thickness_tol,
                            color, label_suffix):
            selected_anodes = [a for a in all_anodes if anode_batch == 'all' or a.fr_id.startswith(anode_batch)]
            selected_cathodes = [c for c in all_cathodes if cathode_batch == 'all' or c.fr_id.startswith(cathode_batch)]
            if not selected_anodes or not selected_cathodes:
                print(f"No FRs selected for batches: {anode_batch}, {cathode_batch}")
                return

            # Compute flow and ratio models for selected batches
            anode_relations, _ = self.fr_flow_analysis(certification = 'all', fr_entry = None, fr_type = 'Anode', return_models=True, plot = False, correction = True)
            cathode_relations, _ = self.fr_flow_analysis(certification = 'all', fr_entry = None, fr_type = 'Cathode', return_models=True, plot = False, correction = True)
            model_or, anode_models, cathode_models = self.ratio_analysis(error = False, plot = False, anode_batch=anode_batch, cathode_batch=cathode_batch)

            # Build anode and cathode dictionaries
            anode_dict, cathode_dict = {}, {}
            np.random.seed(42)
            for a in selected_anodes:
                orifice = np.random.normal(anode_orifice, anode_tol)
                thickness = np.random.normal(ref_thickness, thickness_tol)
                flows, ratios = [], []
                for i, p in enumerate(a.pressures):
                    flow = anode_relations[i][0].predict([[orifice]])
                    pressure_drop = self.hagen_poiseuille(a.gas_type, flow[0], thickness, orifice)
                    ratio = anode_models[i].predict([[orifice, pressure_drop]])
                    flows.append(flow[0])
                    ratios.append(ratio[0])
                anode_dict[a.fr_id] = {'flow_rates': flows, 'ratios': ratios, 'orifice': orifice}

            for c in selected_cathodes:
                orifice = np.random.normal(cathode_orifice, cathode_tol)
                thickness = np.random.normal(ref_thickness, thickness_tol)
                flows, ratios = [], []
                for i, p in enumerate(c.pressures):
                    flow = cathode_relations[i][0].predict([[orifice]])
                    pressure_drop = self.hagen_poiseuille(c.gas_type, flow[0], thickness, orifice)
                    ratio = cathode_models[i].predict([[orifice, pressure_drop]])
                    flows.append(flow[0])
                    ratios.append(ratio[0])
                cathode_dict[c.fr_id] = {'flow_rates': flows, 'ratios': ratios, 'orifice': orifice}

            # Compute final ratios
            final_ratios = []
            for a_data in anode_dict.values():
                for c_data in cathode_dict.values():
                    or_based_ratio = model_or.predict([[a_data['orifice'] / c_data['orifice']]])[0]
                    combined_ratios = (np.array(a_data['flow_rates']) / np.array(c_data['flow_rates']) +
                                    np.array(a_data['ratios']) + np.array(c_data['ratios'])) / 3
                    final_ratios.extend([(or_based_ratio + r) / 2 for r in combined_ratios])

            mean_ratio = np.mean(final_ratios)
            std_ratio = np.std(final_ratios) * 1.5
            x_vals = np.linspace(min(final_ratios) - 0.4 * (max(final_ratios) - min(final_ratios)),
                                max(final_ratios) + 0.4 * (max(final_ratios) - min(final_ratios)), 300)
            plt.plot(x_vals, norm.pdf(x_vals, mean_ratio, std_ratio), color=color,
                    label=f'{label_suffix}\nMean={mean_ratio:.3f},  Std={std_ratio:.3f}, \nAnode Batch: {anode_batch},\nCathode Batch: {cathode_batch}')

            return anode_dict, cathode_dict
        
        # Button callback
        def on_perform_clicked(b):
            with output:
                output.clear_output()
                plt.figure(figsize=(10, 6))
                simulated_anodes, simulated_cathodes = simulate_and_plot(
                    anode_batch_field.value, cathode_batch_field.value,
                    anode_orifice_field.value, cathode_orifice_field.value,
                    anode_tolerance_field.value, cathode_tolerance_field.value,
                    thickness_field.value, thickness_tol_field.value,
                    'red', 'Adjusted Values'
                )
                plt.axvline(x=standard_ratio - 0.5, color='green', linestyle='--', label='Standard Ratio: 13')
                plt.axvline(x=standard_ratio + 0.5, color='green', linestyle='--')
                plt.title('Simulated Distribution of Anode/Cathode Ratios')
                plt.xlabel('Anode/Cathode Ratio')
                plt.ylabel('Density')
                plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.35), ncol=2)
                plt.grid(True)
                plt.show()
                self.match_flow_restrictors(simulated_anode_fr = simulated_anodes, simulated_cathode_fr = simulated_cathodes)

        perform_button.on_click(on_perform_clicked)

        form = widgets.VBox([
            widgets.HTML('<h3>FR Correction Simulation</h3>'),
            widgets.HBox([anode_batch_field, cathode_batch_field]),
            widgets.HBox([anode_orifice_field, anode_tolerance_field]),
            widgets.HBox([cathode_orifice_field, cathode_tolerance_field]),
            widgets.HBox([thickness_field, thickness_tol_field]),
            perform_button,
            output
        ])
        display(form)

    def fr_trend_analysis(self, certification: str, fr_entry: AnodeFR | CathodeFR, fr_type: str, plot_histogram: bool = True) -> None:
        """
        Perform trend analysis on FR dimensional parameters (thickness, radius, orifice diameter).
        Plots distributions of parameters for all FRs in the specified certification batch,
        comparing anodes and cathodes, and highlighting the specific FR entry if provided.
        Args:
            certification (str): Certification batch to analyze ('all' for all batches).
            fr_entry (AnodeFR | CathodeFR): Specific FR entry to highlight in the
                analysis (can be None).
            fr_type (str): Type of FR ('Anode' or 'Cathode').
            plot_histogram (bool): Whether to plot histograms (True) or Gaussian fits (False).
        """
        if certification == 'all':
            all_anodes = self.session.query(AnodeFR).all()
            all_cathodes = self.session.query(CathodeFR).all()
        else:
            all_anodes = self.session.query(AnodeFR).filter(AnodeFR.fr_id.like(f"{certification}-%")).all()
            all_cathodes = self.session.query(CathodeFR).filter(CathodeFR.fr_id.like(f"{certification}-%")).all()

        # Collect values
        anode_thicknesses = [fr.thickness for fr in all_anodes if fr.thickness is not None]
        cathode_thicknesses = [fr.thickness for fr in all_cathodes if fr.thickness is not None]
        
        anode_radii = [fr.radius for fr in all_anodes if fr.radius is not None]
        cathode_radii = [fr.radius for fr in all_cathodes if fr.radius is not None]
        
        anode_orifices = [fr.orifice_diameter for fr in all_anodes if fr.orifice_diameter is not None]
        cathode_orifices = [fr.orifice_diameter for fr in all_cathodes if fr.orifice_diameter is not None]

        thickness = fr_entry.thickness if fr_entry and fr_entry.thickness is not None else None
        radius = fr_entry.radius if fr_entry and fr_entry.radius is not None else None
        orifice_diameter = fr_entry.orifice_diameter if fr_entry and fr_entry.orifice_diameter is not None else None

        anode_reference_orifice = self.anode_reference_orifice
        cathode_reference_orifice = self.cathode_reference_orifice 
        reference_thickness = self.ref_thickness

        plt.figure(figsize=(18, 6))
        
        for idx, (anode_data, cathode_data, label, val, ref_anode, ref_cathode, spec_min, spec_max) in enumerate([
            (anode_thicknesses, cathode_thicknesses, 'Thickness', thickness, reference_thickness, reference_thickness,\
              reference_thickness - self.thickness_tol, reference_thickness + self.thickness_tol),
            (anode_radii, cathode_radii, 'Radius', radius, None, None, self.min_radius, self.max_radius),
            (anode_orifices, cathode_orifices, 'Orifice Diameter', orifice_diameter, anode_reference_orifice, cathode_reference_orifice, None, None)
        ]):
            plt.subplot(1, 3, idx+1)

            mean_anode = np.mean(anode_data)
            std_anode = np.std(anode_data)
            mean_cathode = np.mean(cathode_data)
            std_cathode = np.std(cathode_data)

            if plot_histogram:
                plt.hist(anode_data, bins=20, alpha=0.3, color='blue', density=True, label='Anodes')
                plt.hist(cathode_data, bins=20, alpha=0.3, color='red', density=True, label='Cathodes')
            else:
                for data, color, lbl in [(anode_data, 'blue', 'Anodes'), (cathode_data, 'red', 'Cathodes')]:
                    if not bool(data):
                        continue
                    mean_val = np.mean(data)
                    std_val = np.std(data)
                    data_range = max(data) - min(data)
                    x_vals = np.linspace(min(data)-0.2*data_range, max(data)+0.2*data_range, 200)
                    plt.plot(x_vals, norm.pdf(x_vals, mean_val, std_val), color=color, label=f'{lbl} Gaussian')

            # FR entry and reference/spec lines
            if val:
                plt.axvline(val, color='black', linestyle='--', label=f'FR Entry: {fr_entry.fr_id} = {val:.4f} [mm]')
            if ref_anode:
                plt.axvline(ref_anode, color='green', linestyle='-', label=f'Reference: {ref_anode} [mm]')
            if ref_cathode and not label == 'Thickness':
                plt.axvline(ref_cathode, color='purple', linestyle='-', label=f'Reference: {ref_cathode} [mm]')
            if spec_min:
                plt.axvline(spec_min, color='orange', linestyle='--', label='Min Spec')
            if spec_max:
                plt.axvline(spec_max, color='orange', linestyle='-', label='Max Spec')

            plt.title(
                f'{label} Distribution of {certification}\n'
                f'Anodes: mean={mean_anode:.4f}, std={std_anode:.4f}\n'
                f'Cathodes: mean={mean_cathode:.4f}, std={std_cathode:.4f}',
            wrap = True)
            plt.grid(True)
            plt.xlabel(f'{label} [mm]')
            plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.45), ncol=2)

        plt.tight_layout()
        plt.show()

    def fr_flow_analysis(self, certification: str | list[str], fr_type: str, return_models: bool = False,
                        error: bool = False, plot: bool = True, correction: bool = False, fr_entry: AnodeFR | CathodeFR = None) -> list[tuple]:
        """
        Perform FR flow rate analysis for anodes/cathodes, based on provided batches. Performs linear regression to classify FRs as outliers.

        :param certification: single certification or list of certifications that should be included in the analysis
        :param fr_type: 'Anode' or 'Cathode'
        :param return_models: if True, returns the linear regression models instead of plotting
        :param error: if True, includes error bars in the plots
        :param plot: if True, generates the plots
        :param correction: if True, uses corrected FR data for analysis
        :param fr_entry: specific FR entry to include in the analysis (can be None)
        :Returns: list of tuples containing (model, predictions, coefficients, intercept, R^2 score, residuals) for each pressure of interest
        :rtype: list[tuple]
        """
        if not bool(self.all_anodes) and fr_type == "Anode":
            self.get_anodes_with_flow_rates()
        if not bool(self.all_cathodes) and fr_type == "Cathode":
            self.get_cathodes_with_flow_rates()

        all_frs_raw = self.all_anodes if fr_type == "Anode" else self.all_cathodes
        pressures_of_interest = next((i.pressures for i in all_frs_raw if i.pressures), [1.5, 2.4])

        def check_flow(value: float, residuals: np.array) -> bool:
            mean = np.mean(residuals)
            std = np.std(residuals)
            if std == 0:
                return True
            return abs((value - mean) / std) < 3.5

        cert_list = None
        if isinstance(certification, str):
            cert_list = None if certification.lower() == 'all' else [certification]
        else:
            cert_list = certification

        filtered_frs = all_frs_raw if cert_list is None else [
            i for i in all_frs_raw if "-".join(i.fr_id.split("-")[:-1]) in cert_list
        ]
        title_cert = ", ".join(cert_list) if cert_list else None

        if correction and not filtered_frs:
            filtered_frs = all_frs_raw

        filtered_frs = [fr for fr in filtered_frs if fr.flow_rates and fr.orifice_diameter and fr.pressures]
        if not any(fr.flow_rates for fr in filtered_frs):
            print("Filtered FR subset has no flow rates. Analysis cannot be performed.")
            return []

        title_base = []
        for _ in pressures_of_interest:
            if fr_entry:
                if title_cert:
                    title_base.append(f'{fr_type} {fr_entry.fr_id} Flow, Compared to {title_cert}')
                else:
                    title_base.append(f'{fr_type} {fr_entry.fr_id} Flow')
            else:
                title_base.append(f'FR Flow Rates from batch: {title_cert}' if title_cert else 'All FRs Flow')

        orifice_list, flow_lists, error_lists, cert_labels, fr_ids = [], [[] for _ in pressures_of_interest], [[] for _ in pressures_of_interest], [], []
        flow_averages, flow_stds = [], []

        # Add batch FRs
        for fr in filtered_frs:
            cert_label = "-".join(fr.fr_id.split("-")[:-1])
            if fr_entry and fr.fr_id == fr_entry.fr_id:
                continue
            orifice_list.append(fr.orifice_diameter)
            cert_labels.append(cert_label)
            fr_ids.append(fr.fr_id)
            for i, p_val in enumerate(pressures_of_interest):
                idx = np.argmin(np.abs(np.array(fr.pressures) - p_val))
                flow = fr.flow_rates[idx]
                flow_lists[i].append(flow)
                error_lists[i].append(
                    max(self.anode_fs_error if fr_type == "Anode" else self.cathode_fs_error,
                        self.reading_error * flow) if error else 0
                )

        # Add current FR entry
        fr_entry_is_outlier = [False] * len(pressures_of_interest)
        if fr_entry and fr_entry.orifice_diameter and fr_entry.flow_rates and fr_entry.pressures:
            orifice_list.append(fr_entry.orifice_diameter)
            cert_labels.append("Current FR Entry")
            fr_ids.append(fr_entry.fr_id)
            for i, p_val in enumerate(pressures_of_interest):
                idx = np.argmin(np.abs(np.array(fr_entry.pressures) - p_val))
                flow = fr_entry.flow_rates[idx]
                flow_lists[i].append(flow)
                error_lists[i].append(
                    max(self.anode_fs_error if fr_type == "Anode" else self.cathode_fs_error,
                        self.reading_error * flow) if error else 0
                )

        # Fit models
        n_pressures = len(pressures_of_interest)
        models = []
        for i in range(n_pressures):
            X = np.array(orifice_list).reshape(-1, 1)
            y = np.array(flow_lists[i])
            model = LinearRegression().fit(X, y)
            residuals = model.predict(X) - y
            models.append((model, model.predict(X), model.coef_, model.intercept_, model.score(X, y), residuals))
            # Check if fr_entry is an outlier at this pressure
            if fr_entry:
                idx = -1  # fr_entry is last in list
                fr_entry_is_outlier[i] = not check_flow(residuals[idx], residuals)

        # Compute averages and stds
        for i in range(n_pressures):
            flow_averages.append(np.mean(flow_lists[i]))
            flow_stds.append(np.std(flow_lists[i]))

        # Plotting
        reference_pressures = [1.5, 2.4]
        reference_values = [self.anode_target_15 if fr_type == "Anode" else self.cathode_target_15,
                            self.anode_target_24 if fr_type == "Anode" else self.cathode_target_24]
        reference_orifice = self.anode_reference_orifice if fr_type == "Anode" else self.cathode_reference_orifice

        if plot:
            plt.figure(figsize=(18, 5 * n_pressures), layout="constrained")
        cmap = plt.get_cmap("tab20")
        base_colors = {cert: cmap(i % 20) for i, cert in enumerate(dict.fromkeys(cert_labels))}
        outlier_ids = set()
        outlier_color_map = {}
        outlier_cmap = plt.get_cmap("Set1")

        for i, p_val in enumerate(pressures_of_interest):
            if plot:
                plt.subplot(n_pressures, 2, i + 1)
            for j, od in enumerate(orifice_list):
                flow = flow_lists[i][j]
                fr_id = fr_ids[j]
                # Determine if this point is an outlier
                is_outlier = not check_flow(models[i][-1][j], models[i][-1])
                if fr_entry and j == len(orifice_list) - 1 and fr_entry_is_outlier[i]:
                    is_outlier = True

                if is_outlier:
                    if fr_id not in outlier_color_map:
                        outlier_color_map[fr_id] = outlier_cmap(len(outlier_color_map) % outlier_cmap.N)
                    if plot:
                        plt.scatter([od], [flow], color=outlier_color_map[fr_id], marker='s', zorder=10)
                    outlier_ids.add(fr_id)
                else:
                    if plot:
                        plt.scatter([od], [flow], color=base_colors[cert_labels[j]], zorder=5)

            if plot:
                plt.plot(orifice_list, models[i][1], color='blue')
            if p_val in reference_pressures:
                ref_idx = reference_pressures.index(p_val)
                if plot:
                    plt.scatter([reference_orifice], [reference_values[ref_idx]], color='red', marker='x', s=100, zorder=1000)

            if plot:
                plt.title(
                    title_base[i]
                    + f' @ {p_val} [bar]\n μ={flow_averages[i]:.3f}, σ={flow_stds[i]:.3f} | '
                    f'm_dot = {models[i][2][0]:.3f}*OD + {models[i][3]:.3f} | R²={models[i][4]:.3f}',
                    pad=12
                )
                plt.grid(True)
                plt.xlabel('Orifice Diameter [mm]')
                plt.ylabel(f'Flow @ {p_val} [bar] [mg/s]')

        # Build legend
        handles, labels = [], []
        handles.append(plt.Line2D([0], [0], color='blue'))
        labels.append("Regression Line")
        handles.append(plt.Line2D([0], [0], color='red', marker='x', linestyle='None', markersize=8))
        labels.append("Reference Point")
        for fr_id in sorted(outlier_ids):
            if fr_entry and fr_id == fr_entry.fr_id and any(fr_entry_is_outlier):
                label = f"Outlier: {fr_id} (Current Entry)"
            else:
                label = f"Outlier: {fr_id}"
            handles.append(plt.Line2D([0], [0], color=outlier_color_map[fr_id], marker='s', linestyle='None'))
            labels.append(label)
        for cert, color in base_colors.items():
            if cert != "Current FR Entry":
                handles.append(plt.Line2D([0], [0], color=color, marker='o', linestyle='None'))
                labels.append(cert)
        if "Current FR Entry" in base_colors and not any(fr_entry_is_outlier):
            handles.append(plt.Line2D([0], [0], color=base_colors["Current FR Entry"], marker='o', linestyle='None'))
            labels.append("Current FR Entry")

        if plot:
            fig = plt.gcf()
            fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, 0.4), ncol=8, fontsize=10)
            plt.show()
        elif not plot and not return_models:
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            img_bytes = buf.getvalue()
            plt.close()
            return img_bytes

        if return_models:
            return models, outlier_ids


    def ratio_analysis(self, error: bool = False, plot: bool = True, anode_batch: str = 'all', cathode_batch: str = 'all') -> tuple:
        """
        Perform ratio analysis between anode and cathode flow rates.
        Args:
            error (bool): Whether to include error analysis.
            plot (bool): Whether to generate plots.
        Returns:
            tuple: Tuple containing overall ratio model, anode models, and cathode models.
        """
        all_anodes = self.session.query(AnodeFR).filter(AnodeFR.flow_rates != None).all() if anode_batch == 'all' \
            else self.session.query(AnodeFR).filter(AnodeFR.flow_rates != None).filter(AnodeFR.fr_id.like(f"{anode_batch}-%")).all()
        all_cathodes = self.session.query(CathodeFR).filter(CathodeFR.flow_rates != None).all() if cathode_batch == 'all' \
            else self.session.query(CathodeFR).filter(CathodeFR.flow_rates != None).filter(CathodeFR.fr_id.like(f"{cathode_batch}-%")).all()

        if not anode_batch == 'all' and not all_anodes:
            all_anodes = self.session.query(AnodeFR).filter(AnodeFR.flow_rates != None).all()
        if not cathode_batch == 'all' and not all_cathodes:
            all_cathodes = self.session.query(CathodeFR).filter(CathodeFR.flow_rates != None).all()

        ratios = []
        min_ratios = []
        max_ratios = []
        standard_ratio = 13.0

        for anode in all_anodes:
            anode_flow = np.array(anode.flow_rates)
            anode_errors = np.maximum(self.anode_fs_error, self.reading_error * anode_flow) if error else None
            anode_min = anode_flow - anode_errors if error else None
            anode_max = anode_flow + anode_errors if error else None

            for cathode in all_cathodes:
                cathode_flow = np.array(cathode.flow_rates)
                cathode_errors = np.maximum(self.cathode_fs_error, self.reading_error * cathode_flow) if error else None
                cathode_min = cathode_flow - cathode_errors if error else None
                cathode_max = cathode_flow + cathode_errors if error else None

                # Element-wise ratio
                ratio_array = anode_flow / cathode_flow
                ratios.extend(ratio_array)

                if error:
                    ratio_min_array = anode_min / cathode_max
                    ratio_max_array = anode_max / cathode_min
                    min_ratios.extend(ratio_min_array)
                    max_ratios.extend(ratio_max_array)

        if plot:
            plt.figure(figsize=(10, 6))

            mean_ratio = np.mean(ratios)
            std_ratio = np.std(ratios)
            x_vals = np.linspace(min(ratios)-0.2*(max(ratios)-min(ratios)), max(ratios)+0.2*(max(ratios)-min(ratios)), 300)
            plt.plot(x_vals, norm.pdf(x_vals, mean_ratio, std_ratio), color='blue', label=f'Element-wise Ratios\nMean={mean_ratio:.3f}, Std={std_ratio:.3f}')
            plt.axvline(x=standard_ratio-0.5, color='green', linestyle='--', label='Standard Ratio: 13')
            plt.axvline(x=standard_ratio+0.5, color='green', linestyle='--')
            plt.axvline(x=mean_ratio, color='tab:blue', linestyle='-', label='Mean Ratio')

            if error:
                mean_min = np.mean(min_ratios)
                std_min = np.std(min_ratios)
                x_vals_min = np.linspace(min(min_ratios)-0.2*(max(min_ratios)-min(min_ratios)), max(min_ratios)+0.2*(max(min_ratios)-min(min_ratios)), 300)
                plt.plot(x_vals_min, norm.pdf(x_vals_min, mean_min, std_min), color='red', label=f'Min Ratio\nMean={mean_min:.3f}, Std={std_min:.3f}')

                mean_max = np.mean(max_ratios)
                std_max = np.std(max_ratios)
                x_vals_max = np.linspace(min(max_ratios)-0.2*(max(max_ratios)-min(max_ratios)), max(max_ratios)+0.2*(max(max_ratios)-min(max_ratios)), 300)
                plt.plot(x_vals_max, norm.pdf(x_vals_max, mean_max, std_max), color='orange', label=f'Max Ratio\nMean={mean_max:.3f}, Std={std_max:.3f}')

            plt.title('Gaussian Distribution of Element-wise Anode/Cathode Flow Ratios')
            plt.xlabel('Flow Ratio')
            plt.ylabel('Probability Density')
            plt.grid(True)
            plt.legend()
            plt.show()

        model_or, anode_models, cathode_models = self.ratio_trend_analysis(all_anodes, all_cathodes, plot=plot)
        return model_or, anode_models, cathode_models

    def get_anode_tolerance(self, min: float, max: float, anode_ref: float, cathode_ref: float) -> float:
        """
        Calculate the anode tolerance based on min/max ratio specifications and reference values.
        """
        return (anode_ref - min*cathode_ref) - min*(2*anode_ref - (min + max)*cathode_ref)/(min - max)
    
    def get_cathode_tolerance(self, min: float, max: float, anode_ref: float, cathode_ref: float) -> float:
        """
        Calculate the cathode tolerance based on min/max ratio specifications and reference values.
        """
        return (2*anode_ref - (min + max)*cathode_ref)/(min - max)

    def get_ref_difference(self, r_target: float, anode_ref: float, cathode_ref: float) -> float:
        """
        Calculate the reference difference based on target ratio and reference values.
        """
        return (r_target*cathode_ref-anode_ref)/(r_target + 1)
    
    def get_new_ref(self, r_target: float, model, tol: float = 0.5) -> tuple | None:
        """
        Calculate new reference orifice diameter based on target ratio and regression model.
        Args:
            r_target (float): Target flow ratio.
            model (LinearRegression): Regression model for flow ratio.
            tol (float): Tolerance for ratio specification.
        Returns:
            tuple | None: Tuple containing nominal, max, and min reference orifice diameters,
                or None if calculation fails.
        """
        x = np.arange(0, 0.1, 0.00001).reshape(-1, 1)
        y = model.predict(x)
        min_tol = r_target - tol
        max_tol = r_target + tol
        idx_nominal = np.argmin(np.abs(y - r_target))
        x_nominal = x[idx_nominal][0]
        idx_min = np.argmin(np.abs(y - min_tol))
        x_min = x[idx_min][0]
        idx_max = np.argmin(np.abs(y - max_tol))
        x_max = x[idx_max][0]
        if x_nominal and x_min and x_max:
            return x_nominal, x_max, x_min
        else:
            return None

    def ratio_trend_analysis(self, all_anodes: list[AnodeFR], all_cathodes: list[CathodeFR], plot: bool = True) -> tuple:
        """
        Perform trend analysis on flow ratios between anodes and cathodes.
        Args:
            all_anodes (list[AnodeFR]): List of all anode FRs.
            all_cathodes (list[CathodeFR]): List of all cathode FRs.
            plot (bool): Whether to generate plots.
        Returns:
            tuple: Tuple containing overall ratio model, anode models, and cathode models.
        """
        # Store ratios per orifice and pressure
        anode_agg = {}
        cathode_agg = {}
        orifice_ratios = []
        ratios_all = []
        pressures = next((i.pressures for i in all_anodes if i.pressures), [1.5, 2.4])

        for anode in all_anodes:
            for cathode in all_cathodes:
                ratio = np.array(anode.flow_rates) / np.array(cathode.flow_rates)
                orifice_ratio = anode.orifice_diameter / cathode.orifice_diameter
                orifice_ratios.extend([orifice_ratio] * len(ratio))
                ratios_all.extend(ratio)
                for i, p in enumerate(pressures):
                    key = (anode.fr_id, p)
                    if key not in anode_agg:
                        anode_agg[key] = {'orifice': anode.orifice_diameter, 'pressure_drop': anode.pressure_drop[i], 'ratio': []}
                    anode_agg[key]['ratio'].append(ratio[i])

                    key = (cathode.fr_id, p)
                    if key not in cathode_agg:
                        cathode_agg[key] = {'orifice': cathode.orifice_diameter, 'pressure_drop': cathode.pressure_drop[i], 'ratio': []}
                    cathode_agg[key]['ratio'].append(ratio[i])

        model_or = LinearRegression().fit(np.array(orifice_ratios).reshape(-1, 1), np.array(ratios_all))
        y_pred_or = model_or.predict(np.array(orifice_ratios).reshape(-1, 1))

        anode_models = []
        anode_xs = []
        anode_ratios = []
        cathode_xs = []
        cathode_ratios = []
        cathode_models = []

        # Build models per pressure
        for pressure in pressures:
            x_anode = np.array([[v['orifice'], v['pressure_drop']] for (fid, pr), v in anode_agg.items() if pr == pressure])
            y_anode = np.array([np.mean(v['ratio']) for (fid, pr), v in anode_agg.items() if pr == pressure])
            if len(x_anode) > 0:
                model_a = LinearRegression().fit(x_anode, y_anode)
                anode_models.append(model_a)
                anode_xs.append(x_anode)
                anode_ratios.append(y_anode)

            x_cathode = np.array([[v['orifice'], v['pressure_drop']] for (fid, pr), v in cathode_agg.items() if pr == pressure])
            y_cathode = np.array([np.mean(v['ratio']) for (fid, pr), v in cathode_agg.items() if pr == pressure])
            if len(x_cathode) > 0:
                model_c = LinearRegression().fit(x_cathode, y_cathode)
                cathode_models.append(model_c)
                cathode_xs.append(x_cathode)
                cathode_ratios.append(y_cathode)

        if plot:
            # Orifice ratio plot
            plt.figure(figsize=(8, 6))
            plt.scatter(orifice_ratios, ratios_all, alpha=0.5)
            plt.plot(orifice_ratios, y_pred_or, color='black',
                     label=f'y={model_or.coef_[0]:.2f}*OR + {model_or.intercept_:.2f} | R²={model_or.score(np.array(orifice_ratios).reshape(-1, 1), ratios_all):.3f}')
            plt.axhline(y=13.5, color='r', linestyle='--', label='Ratio Spec: 13 ± 0.5')
            plt.axhline(y=12.5, color='r', linestyle='--')
            reference_value = y_pred_or[np.argmin(np.abs(np.array(orifice_ratios) - (self.anode_reference_orifice / self.cathode_reference_orifice)))]
            plt.axvline(self.anode_reference_orifice / self.cathode_reference_orifice, color='g', linestyle='--',
                        label=f"Reference OR = ({self.anode_reference_orifice / self.cathode_reference_orifice:.3f}, {reference_value:.3f})")
            plt.xlabel('Anode/Cathode Orifice Diameter Ratio')
            plt.ylabel('Flow Ratio')
            plt.title('Flow Ratio vs Orifice Diameter Ratio')
            plt.grid(True)
            plt.legend()
            plt.show()

        if plot:
            colors = ['tab:green', 'tab:purple', 'tab:gray']
            n_rows = (len(anode_models) + 1) // 2
            fig, axs = plt.subplots(n_rows, 2, figsize=(16, 6 * n_rows))
            axs = axs.flatten()

            # Plot each pressure (model corresponds to same index in pressures list)
            for idx, (model_a, x_a, y_a) in enumerate(zip(anode_models, anode_xs, anode_ratios)):
                p = pressures[idx]
                ax = axs[idx]
                ax.scatter(x_a[:, 0], y_a, color='tab:blue', alpha=0.7, label='Measured Ratios')
                ax.axhline(y=13.5, color='r', linestyle='--', label='Ratio Spec: 13 ± 0.5')
                ax.axhline(y=12.5, color='r', linestyle='--')
                ax.set_yticks(np.arange(10, 16, 0.5))
                # Generate PD lines based on range of PD in this dataset
                pd_values = np.percentile(x_a[:, 1], [0, 50, 100])
                for j, pd_fixed in enumerate(pd_values):
                    X_line = np.column_stack((np.linspace(x_a[:, 0].min(), x_a[:, 0].max(), 100), np.full(100, pd_fixed)))
                    y_line = model_a.predict(X_line)
                    ax.plot(X_line[:, 0], y_line, color=colors[j], label=f'PD={pd_fixed:.2f} Pa')

                coef = model_a.coef_
                intercept = model_a.intercept_
                r2 = model_a.score(x_a, y_a)
                ax.set_title(f"Anode - Pressure {p} Pa | y={coef[0]:.2f}*OD + {coef[1]:.2f}*PD + {intercept:.2f} | R²={r2:.3f}")
                ax.set_xlabel("Orifice Diameter [mm]")
                ax.set_ylabel("Flow Ratio")
                ax.grid(True)
                ax.set_ylim(10, 16)
                ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.4), ncol=3)

            plt.tight_layout()
            plt.show()

            # Cathode models
            n_rows = (len(cathode_models) + 1) // 2
            fig, axs = plt.subplots(n_rows, 2, figsize=(16, 6 * n_rows))
            axs = axs.flatten()

            for idx, (model_c, x_c, y_c) in enumerate(zip(cathode_models, cathode_xs, cathode_ratios)):
                p = pressures[idx]
                ax = axs[idx]
                ax.scatter(x_c[:, 0], y_c, color='tab:orange', alpha=0.7, label='Measured Ratios')
                ax.axhline(y=13.5, color='r', linestyle='--', label='Ratio Spec: 13 ± 0.5')
                ax.axhline(y=12.5, color='r', linestyle='--')

                pd_values = np.percentile(x_c[:, 1], [0, 50, 100])
                for j, pd_fixed in enumerate(pd_values):
                    X_line = np.column_stack((np.linspace(x_c[:, 0].min(), x_c[:, 0].max(), 100), np.full(100, pd_fixed)))
                    y_line = model_c.predict(X_line)
                    ax.plot(X_line[:, 0], y_line, color=colors[j], label=f'PD={pd_fixed:.2f} Pa')

                coef = model_c.coef_
                intercept = model_c.intercept_
                r2 = model_c.score(x_c, y_c)
                ax.set_title(f"Cathode - Pressure {p} Pa | y={coef[0]:.2f}*OD + {coef[1]:.2f}*PD + {intercept:.2f} | R²={r2:.3f}")
                ax.set_xlabel("Orifice Diameter [mm]")
                ax.set_ylabel("Flow Ratio")
                ax.grid(True)
                ax.set_ylim(10, 16)
                ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.4), ncol=3)

            plt.tight_layout()
            plt.show()

        return model_or, anode_models, cathode_models

    def fr_correlation_analysis(self, certification: str, fr_entry: AnodeFR | CathodeFR, fr_type: str) -> None:
        """
        Perform correlation analysis between FR dimensional parameters and flow rates.
        Plots 3D scatter plots of flow rates at 1.5 and 2
        Args:
            certification (str): Certification batch to analyze ('all' for all batches).
            fr_entry (AnodeFR | CathodeFR): Specific FR entry to highlight in the
                analysis (can be None).
            fr_type (str): Type of FR ('Anode' or 'Cathode').
        """
        if certification == 'all':
            all_frs = self.all_frs
        else:
            all_frs = [i for i in self.all_frs if "-".join(i.fr_id.split("-")[:-1]) == certification]

        # Collect valid FRs
        data = [
            (
                fr.orifice_diameter,
                fr.thickness,
                fr.radius,
                fr.flow_rates[np.argmin(np.abs(np.array(fr.pressures) - 1.5))] if fr.flow_rates else None,
                fr.flow_rates[np.argmin(np.abs(np.array(fr.pressures) - 2.4))] if fr.flow_rates else None
            )
            for fr in all_frs
            if fr.orifice_diameter is not None and fr.thickness is not None and fr.radius is not None and fr.flow_rates
        ]

        if not data:
            print("No valid FR data for correlation analysis.")
            return

        orifices, thicknesses, radii, flows15, flows24 = zip(*data)

        # Compute proper correlations: flow vs x-axis variables
        corr15_or_th = np.corrcoef(orifices, flows15)[0, 1], np.corrcoef(thicknesses, flows15)[0, 1]
        corr15_or_r = np.corrcoef(orifices, flows15)[0, 1], np.corrcoef(radii, flows15)[0, 1]
        corr24_or_th = np.corrcoef(orifices, flows24)[0, 1], np.corrcoef(thicknesses, flows24)[0, 1]
        corr24_or_r = np.corrcoef(orifices, flows24)[0, 1], np.corrcoef(radii, flows24)[0, 1]

        # Create 3D subplots
        fig = plt.figure(figsize=(14, 12))

        # Adjust subplot spacing to prevent clipping
        plt.subplots_adjust(left=0.12, right=0.95, top=0.95, bottom=0.08, wspace=0.3, hspace=0.3)

        # 1. Flow @1.5 vs Orifice & Thickness
        ax1 = fig.add_subplot(221, projection='3d')
        ax1.scatter(orifices, thicknesses, flows15, c=flows15, cmap='viridis', alpha=0.8)
        ax1.set_xlabel('Orifice Diameter [mm]')
        ax1.set_ylabel('Thickness [mm]')
        ax1.set_zlabel('Flow @ 1.5 [bar] [mg/s]', labelpad=10)
        ax1.set_title(f'{fr_type} Flow @ 1.5 [bar]\nCorr Flow-Orifice: {corr15_or_th[0]:.3f}, Flow-Thickness: {corr15_or_th[1]:.3f}')
        ax1.grid(True)
        ax1.view_init(elev=25, azim=45)

        # 2. Flow @1.5 vs Orifice & Radius
        ax2 = fig.add_subplot(222, projection='3d')
        ax2.scatter(orifices, radii, flows15, c=flows15, cmap='plasma', alpha=0.8)
        ax2.set_xlabel('Orifice Diameter [mm]')
        ax2.set_ylabel('Radius [mm]')
        ax2.set_zlabel('Flow @ 1.5 [bar] [mg/s]', labelpad=10)
        ax2.set_title(f'{fr_type} Flow @ 1.5 [bar]\nCorr Flow-Orifice: {corr15_or_r[0]:.3f}, Flow-Radius: {corr15_or_r[1]:.3f}')
        ax2.grid(True)
        ax2.view_init(elev=25, azim=45)

        # 3. Flow @2.4 vs Orifice & Thickness
        ax3 = fig.add_subplot(223, projection='3d')
        ax3.scatter(orifices, thicknesses, flows24, c=flows24, cmap='viridis', alpha=0.8)
        ax3.set_xlabel('Orifice Diameter [mm]')
        ax3.set_ylabel('Thickness [mm]')
        ax3.set_zlabel('Flow @ 2.4 [bar] [mg/s]', labelpad=10)
        ax3.set_title(f'{fr_type} Flow @ 2.4 [bar]\nCorr Flow-Orifice: {corr24_or_th[0]:.3f}, Flow-Thickness: {corr24_or_th[1]:.3f}')
        ax3.grid(True)
        ax3.view_init(elev=25, azim=45)

        # 4. Flow @2.4 vs Orifice & Radius
        ax4 = fig.add_subplot(224, projection='3d')
        ax4.scatter(orifices, radii, flows24, c=flows24, cmap='plasma', alpha=0.8)
        ax4.set_xlabel('Orifice Diameter [mm]')
        ax4.set_ylabel('Radius [mm]')
        ax4.set_zlabel('Flow @ 2.4 [bar] [mg/s]', labelpad=10)
        ax4.set_title(f'{fr_type} Flow @ 2.4 [bar]\nCorr Flow-Orifice: {corr24_or_r[0]:.3f}, Flow-Radius: {corr24_or_r[1]:.3f}')
        ax4.grid(True)
        ax4.view_init(elev=25, azim=45)

        plt.tight_layout()
        plt.show(block=False)

        plt.ion()
        plt.show()

    def flow_vs_TO(self, fr_entry: AnodeFR | CathodeFR = None, fr_type: str = 'Anode') -> None:
        """
        Analyze and plot flow rate versus Thickness/Orifice ratio for FRs.
        Args:
            fr_entry (AnodeFR | CathodeFR): Specific FR entry to highlight in the
                analysis (can be None).
            fr_type (str): Type of FR ('Anode' or 'Cathode').
        """
        all_frs = [i for i in self.all_frs if i.flow_rates and i.thickness is not None and i.orifice_diameter is not None]
        all_pressures = sorted({p for fr in all_frs for p in fr.pressures if fr.pressures})
        n_rows = (len(all_pressures) + 1) // 2
        fig, axs = plt.subplots(n_rows, 2, figsize=(18, 7 * n_rows))
        axs = axs.flatten()
        
        for idx, p_target in enumerate(all_pressures):
            TO_list = []
            flow_list = []
            for fr in all_frs:
                if fr.thickness is not None and fr.orifice_diameter is not None and fr.flow_rates:
                    TO = fr.thickness / fr.orifice_diameter
                    p_idx = np.argmin(np.abs(np.array(fr.pressures) - p_target))
                    flow = fr.flow_rates[p_idx]
                    TO_list.append(TO)
                    flow_list.append(flow)
            
            TO_array = np.array(TO_list).reshape(-1, 1)
            flow_array = np.array(flow_list)

            model = LinearRegression().fit(TO_array, flow_array)
            y_pred = model.predict(TO_array)
            coef = model.coef_
            intercept = model.intercept_
            
            ax = axs[idx]
            ax.scatter(TO_list, flow_list, alpha=0.6, label='All FRs')
            ax.plot(TO_list, y_pred, color='blue', label=f'Regression Line')
            
            # Plot current FR if provided
            if fr_entry and fr_entry.thickness is not None and fr_entry.orifice_diameter is not None and fr_entry.flow_rates:
                TO_current = fr_entry.thickness / fr_entry.orifice_diameter
                p_idx = np.argmin(np.abs(np.array(fr_entry.pressures) - p_target))
                flow_current = fr_entry.flow_rates[p_idx]
                ax.scatter([TO_current], [flow_current], color='red',
                        label=f'{fr_type} {fr_entry.fr_id}\nTO: {TO_current:.3f}, Flow: {flow_current:.3f}')
            
            ax.set_title(f'Pressure: {p_target} bar | Flow = {coef[0]:.3f}*TO + {intercept:.3f} | R²={model.score(TO_array, flow_array):.3f}')
            ax.set_xlabel('Thickness/Orifice Ratio')
            ax.set_ylabel('Flow Rate [mg/s]')
            ax.grid(True)
            ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.3), ncol=2)

        for j in range(idx + 1, len(axs)):
            fig.delaxes(axs[j])

        plt.tight_layout()
        plt.show()

    def pressure_drop_orifice(self, fr_entry: AnodeFR | CathodeFR = None, fr_type: str = 'Anode') -> None:
        """
        Analyze and plot pressure drop versus orifice diameter for FRs.
        Args:
            fr_entry (AnodeFR | CathodeFR): Specific FR entry to highlight in the
            analysis (can be None).
            fr_type (str): Type of FR ('Anode' or 'Cathode').
        """
        pressures = fr_entry.pressures if fr_entry and fr_entry.pressures else next((i.pressures for i in self.all_frs if i.pressures), [1.5, 2.4])
        if not pressures:
            pressures = [1, 1.5, 2, 2.4]

        current_orifice = fr_entry.orifice_diameter if fr_entry and fr_entry.orifice_diameter is not None else None
        current_pressure_drops = fr_entry.pressure_drop if fr_entry and fr_entry.pressure_drop is not None else None

        all_orifices = np.array([fr.orifice_diameter for fr in self.all_frs if fr.orifice_diameter is not None and fr.pressure_drop is not None])
        all_pressure_drops = {}
        for i, p in enumerate(pressures):
            all_pressure_drops[str(p)] = [fr.pressure_drop[i] for fr in self.all_frs if fr.orifice_diameter is not None and fr.pressure_drop is not None]

        n_rows = (len(pressures) + 1) // 2
        fig, axs = plt.subplots(n_rows, 2, figsize=(18, 7 * n_rows))
        axs = axs.flatten()

        for i, p in enumerate(pressures):
            y = np.array(all_pressure_drops[str(p)])
            X = all_orifices.reshape(-1, 1)
            model = LinearRegression().fit(X, y)
            y_pred = model.predict(X)
            coef = model.coef_
            intercept = model.intercept_

            ax = axs[i]
            ax.scatter(all_orifices, y, alpha=0.6, label='All FRs')
            ax.plot(all_orifices, y_pred, color='blue', label='Regression Line')
            if current_orifice and current_pressure_drops:
                ax.scatter([current_orifice], [current_pressure_drops[i]], color='red',
                        label=f'{fr_type} {fr_entry.fr_id}\nOD: {current_orifice:.3f}, ΔP: {current_pressure_drops[i]:.3f}')
            ax.set_title(f'Pressure drop @ Pressure of {p} bar | ΔP = {coef[0]:.3f}*OD + {intercept:.3f} | R²={model.score(X, y):.3f}')
            ax.set_xlabel('Orifice Diameter [mm]')
            ax.set_ylabel('Pressure Drop [Pa]')
            ax.grid(True)
            ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.45), ncol=2)

        # Remove unused axes if any
        for j in range(i + 1, len(axs)):
            fig.delaxes(axs[j])

        plt.tight_layout()
        plt.show()

    def select_ratio(self) -> None:
        """
        Create an interactive widget to select a flow restrictor ratio
        and display matching flow restrictor pairs.
        """
        ratio_field = widgets.BoundedFloatText(
            value=13.0,
            min=1,
            max=10000000,
            step=0.1,
        )

        self.get_anodes_with_flow_rates()
        self.get_cathodes_with_flow_rates()

        certs_anode = self._get_certifications_from_frs(fr_list = self.all_anodes)
        certs_cathode = self._get_certifications_from_frs(fr_list = self.all_cathodes)
        all_certs = certs_anode + certs_cathode
        cert_options = sorted(all_certs, key = lambda x: (int(x.split("-")[0][1:]), int(x.split("-")[1])), reverse = True)

        exclude_certifications_field = widgets.SelectMultiple(
            options = [None] + cert_options,
            value = ("C25-0412", ) if "C25-0412" in cert_options else None,
            **field("Exclude Certification:")
        )

        exclude_outliers_box = widgets.Checkbox(
            value = True,
            **field("Exclude Outliers:"),
            indent=True
        )

        output = widgets.Output()
        def on_ratio_change(change):
            with output:
                output.clear_output()
                ratio = ratio_field.value
                if not ratio:
                    print("Please select a valid A/C-Ratio!")
                    return
                anode_certifications = [i for i in certs_anode if i not in exclude_certifications_field.value] if\
                      bool(exclude_certifications_field.value) else certs_anode
                cathode_certifications = [i for i in certs_cathode if i not in exclude_certifications_field.value] if\
                      bool(exclude_certifications_field.value) else certs_cathode
                exclude_outliers = exclude_outliers_box.value
                self.match_flow_restrictors(ratio = ratio, anode_certifications = anode_certifications,\
                                            cathode_certifications = cathode_certifications, exclude_outliers = exclude_outliers)

        ratio_field.observe(on_ratio_change, names='value')
        exclude_certifications_field.observe(on_ratio_change, names = 'value')
        exclude_outliers_box.observe(on_ratio_change, names='value')
        form = widgets.VBox([
            widgets.HTML('<h3>Match Flow Restrictors by Ratio</h3>'),
            widgets.HBox([widgets.HTML('Select Ratio (default 13): '), ratio_field]),
            widgets.VBox([exclude_certifications_field, exclude_outliers_box]),
            output
        ])
        display(form)
        with output:
            output.clear_output()
            anode_certifications = [i for i in certs_anode if i not in exclude_certifications_field.value] if\
                  bool(exclude_certifications_field.value) else certs_anode
            cathode_certifications = [i for i in certs_cathode if i not in exclude_certifications_field.value] if\
                 bool(exclude_certifications_field.value) else certs_cathode
            exclude_outliers = exclude_outliers_box.value
            self.match_flow_restrictors(ratio = 13.0, anode_certifications = anode_certifications,\
                                         cathode_certifications = cathode_certifications, exclude_outliers = exclude_outliers)


    def _get_fr_outliers(self, certifications: list[str], fr_type: str, exclude_outliers: bool = True) -> dict[str, list[str]]:
        """
        Identify outlier flow restrictors based on certifications and flow rates.
        Args:
            certifications (list[str]): List of certification batches to consider.
            fr_type (str): Type of FR ('Anode' or 'Cathode').
        Returns:
            dict[str, list[str]]: Dictionary with outlier FR IDs per certification.
        """
        outlier_dict = {}
        if not bool(certifications) or not exclude_outliers:
            return outlier_dict
        
        for cert in certifications:
            _, outliers = self.fr_flow_analysis(certification = cert, fr_type = fr_type, plot = False, return_models = True)
            if len(outliers) > 0:
                outlier_dict[cert] = outliers

        return outlier_dict
    
    def _fr_id_sort_key(self, fr_id: str):
        parts = fr_id.split("-")
        return (int(parts[0][1:]), int(parts[1]), int(parts[2]))

    def match_flow_restrictors(self, anode_certifications: list[str], cathode_certifications: list[str], ratio: float = 13, tolerance: float = 0.5,
                            simulated_anode_fr: dict = None, simulated_cathode_fr: dict = None, exclude_outliers: bool = True) -> None:
        """
        Match flow restrictors based on a specified ratio using weighted bipartite matching.
        Closer matches to the target ratio are preferred.

        Args:
            ratio (float): The target ratio to match flow restrictors.
            tolerance (float): Allowed deviation from the target ratio.
            simulated_anode_fr (dict): Optional pre-simulated anode flow data.
            simulated_cathode_fr (dict): Optional pre-simulated cathode flow data.
        """

        outlier_anode_dict = self._get_fr_outliers(certifications = anode_certifications, fr_type = "Anode", exclude_outliers = exclude_outliers)
        outlier_cathode_dict = self._get_fr_outliers(certifications = cathode_certifications, fr_type = "Cathode", exclude_outliers = exclude_outliers)

        # Fetch database records if no simulated data is provided
        if simulated_anode_fr is None:
            anode_fr = [i for i in self.all_anodes if not bool(i.set_id) and bool(i.flow_rates) and not bool(i.allocated) and\
                         "-".join(i.fr_id.split("-")[:-1]) in anode_certifications]
        else:
            anode_fr = None

        if simulated_cathode_fr is None:
            cathode_fr = [i for i in self.all_cathodes if not bool(i.set_id) and bool(i.flow_rates) and not bool(i.allocated) and\
                          "-".join(i.fr_id.split("-")[:-1]) in cathode_certifications]
        else:
            cathode_fr = None

        self.fr_matching_dict = {}
        self.fr_matching_ratios = {}
        flat_data = []
        anodes_with_zero, cathodes_with_zero = [], []

        fr_map: dict[str, AnodeFR | CathodeFR] = {}
        # Helper function to process pairs
        def process_pairs(anodes: list[AnodeFR], cathodes: list[CathodeFR], sim_flag=False):
            for a_id, a_obj in (anodes if sim_flag else [(x.fr_id, x) for x in anodes]):
                if sim_flag:
                    a_flow = np.atleast_1d(np.array(a_obj.get("flow_rates", []), dtype=float))
                    a_press = a_obj.get("pressures", [])
                else:
                    a_flow = np.atleast_1d(np.array(a_obj.flow_rates, dtype=float))
                    a_press = a_obj.pressures
                    fr_map[a_id] = a_obj

                if a_flow.size == 0:
                    continue

                batch = "-".join(a_id.split("-")[:1])
                if batch in outlier_anode_dict and a_id in outlier_anode_dict[batch]:
                    continue

                self.fr_matching_dict[a_id] = []
                self.fr_matching_ratios[a_id] = {}

                for c_id, c_obj in (cathodes if sim_flag else [(x.fr_id, x) for x in cathodes]):
                    if sim_flag:
                        c_flow = np.atleast_1d(np.array(c_obj.get("flow_rates", []), dtype=float))
                        c_press = c_obj.get("pressures", [])
                    else:
                        c_flow = np.atleast_1d(np.array(c_obj.flow_rates, dtype=float))
                        c_press = c_obj.pressures
                        fr_map[c_id] = c_obj
 
                    if c_flow.size == 0:
                        continue

                    batch = "-".join(c_id.split("-")[:1])
                    if batch in outlier_cathode_dict and c_id in outlier_cathode_dict[batch]:
                        continue

                    min_len = min(len(a_flow), len(c_flow))
                    a_slice = a_flow[:min_len]
                    c_slice = c_flow[:min_len]

                    if np.any(a_slice == 0):
                        if not sim_flag and a_id not in anodes_with_zero:
                            idx = np.where(a_slice == 0)[0][0]
                            print(f"Anode {a_id} has zero flow rate for pressure {a_press[idx]} [bar]; skipping.")
                            anodes_with_zero.append(a_id)
                        continue

                    if np.any(c_slice == 0):
                        if not sim_flag and c_id not in cathodes_with_zero:
                            idx = np.where(c_slice == 0)[0][0]
                            print(f"Cathode {c_id} has zero flow rate for pressure {c_press[idx]} [bar]; skipping.")
                            cathodes_with_zero.append(c_id)
                        continue

                    ratio_vec = a_slice / c_slice
                    if np.all((ratio_vec >= ratio - tolerance) & (ratio_vec <= ratio + tolerance)):
                        self.fr_matching_dict[a_id].append(c_id)
                        self.fr_matching_ratios[a_id][c_id] = ratio_vec

                        row = {"Anode ID": a_id, "Cathode ID": c_id}
                        for i, r in enumerate(ratio_vec, start=1):
                            row[f"Ratio {i}"] = r
                        flat_data.append(row)

        # Process data
        simulation = False
        if simulated_anode_fr and simulated_cathode_fr:
            simulation = True
            process_pairs(simulated_anode_fr.items(), simulated_cathode_fr.items(), sim_flag=True)
        else:
            # Sort anodes and cathodes for deterministic processing
            anode_fr = sorted(anode_fr, key=lambda x: self._fr_id_sort_key(x.fr_id))
            cathode_fr = sorted(cathode_fr, key=lambda x: self._fr_id_sort_key(x.fr_id))
            process_pairs(anode_fr, cathode_fr)

        if not flat_data:
            print(f"No valid flow restrictor pairs found for ratio {ratio}.")
            return

        print(f"Tried matching with: {len(anode_fr)} Anodes and "
            f"{len(cathode_fr)} Cathodes")

        # --- Build weighted bipartite graph ---
        G = nx.Graph()
        for a_id in sorted(self.fr_matching_ratios.keys(), key=self._fr_id_sort_key):
            for c_id in sorted(self.fr_matching_ratios[a_id].keys(), key=self._fr_id_sort_key):
                # Weight = mean absolute deviation from target ratio
                ratio_vec = self.fr_matching_ratios[a_id][c_id]
                weight = np.mean(np.abs(ratio_vec - ratio)**2)
                G.add_edge(a_id, c_id, weight=weight)
            
        # Weighted maximum matching
        matching = nx.algorithms.min_weight_matching(G, weight='weight')
        anode_ids = set(self.fr_matching_ratios.keys())  

        matching_dict: dict[str, str] = {}
        for u, v in matching:
            if u in anode_ids:
                matching_dict[u] = v
            else:
                matching_dict[v] = u

        def sort_df_by_fr_id(s: pd.Series):
            parts = s.str.split("-")
            return pd.DataFrame({
                "p0": parts.str[0].str[1:].astype(int),
                "p1": parts.str[1].astype(int),
                "p2": parts.str[2].astype(int)
            }).apply(tuple, axis=1)

        max_match_data = []
        lpt_match_data = []
        for a_id in matching_dict:
            c_id = matching_dict[a_id]
            ratios = self.fr_matching_ratios[a_id][c_id]
            lpt_match_data.append({"anode": fr_map[a_id], "cathode": fr_map[c_id], "ratios": ratios})
            row = {"Anode ID": a_id, "Cathode ID": c_id}
            for i, r in enumerate(ratios, start=1):
                row[f"Ratio {i}"] = r
            max_match_data.append(row)

        df_max = pd.DataFrame(max_match_data)
        df_max = df_max.sort_values(by="Anode ID", key=sort_df_by_fr_id)
        df_max.insert(0, "Match #", range(1, len(df_max) + 1))

        format_dict = {col: "{:.2f}" for col in df_max.columns if col.startswith("Ratio")}
        styled_df = df_max.style.format(format_dict).hide(axis='index')

        temperature = 22

        lpt_match_df = self.match_sets_to_lpt(matching_list = lpt_match_data, temperature=temperature)

        matching_yield = len(lpt_match_df)/min(len(anode_fr), len(cathode_fr))*100
        print(f"Matching yield: {matching_yield:.2f} %")

        dropdown = widgets.Dropdown(
            options = [("All Sets", "all")] + [(f"Set {i}", idx) for idx, i in enumerate(lpt_match_df["(Potential) Set ID"].tolist())],
            value = "all",
            **field("Analyse Set: ")
        )

        plot_output = widgets.Output()
        plot_output.layout = widgets.Layout(height="1000px", width="100%")

        display(
            widgets.VBox([
                widgets.HTML("<h3>Maximum FR Matches (left) and Maximum Matches with LPTs w.r.t. LPT Voltage spec.</h3>"), 
                widgets.HBox([
                    widgets.HTML(styled_df.to_html()), 
                    widgets.HTML(
                        lpt_match_df
                        .style
                        .hide(axis="index")
                        .hide(subset=["flow", "voltages"], axis="columns")
                        .to_html()
                    )
                ]),
                dropdown,
                plot_output
            ])
        )

        # pos = nx.bipartite_layout(G, top_nodes)
        # degrees = dict(G.degree())
        # node_sizes = [300 + 50 * degrees[n] for n in G.nodes()]
        # node_colors = ['tab:blue' if n in top_nodes else 'tab:orange' for n in G.nodes()]

        # plt.figure(figsize=(12, 8))
        # nx.draw(G, pos,
        #         with_labels=True,
        #         node_size=node_sizes,
        #         node_color=node_colors,
        #         edge_color='gray',
        #         font_size=8,
        #         width=1.2)
        # plt.title("Weighted Bipartite Graph of Anode–Cathode Pairings")
        # plt.axis('off')
        # plt.show()

        def on_dropdown_change(change: dict):
            set_ = dropdown.value
            if set_ == "all":
                self._plot_match_results(output=plot_output, match_ratio = ratio, lpt_match_df=lpt_match_df, fr_map = fr_map, temperature = temperature)
            else:
                entry = lpt_match_df.iloc[[set_]]
                self._plot_match_results(output=plot_output, match_ratio = ratio, lpt_match_df=entry, fr_map = fr_map, temperature = temperature)

        dropdown.observe(on_dropdown_change, names="value")

        self._plot_match_results(output=plot_output, match_ratio = ratio, lpt_match_df=lpt_match_df, fr_map = fr_map, temperature = temperature)

    def _plot_match_results(self, output: widgets.Output, match_ratio: float, lpt_match_df: pd.DataFrame, fr_map: dict[str, AnodeFR | CathodeFR], temperature: float = 22):
        with output:
            output.clear_output()
            fig, (ax_flow, ax_ratio) = plt.subplots(1, 2, figsize=(16, 6))

            all_ratios = []

            for idx in range(len(lpt_match_df)):
                match_flow = lpt_match_df["flow"].iloc[idx]
                match_margin = lpt_match_df["Worst Margin"].iloc[idx]
                cathode = lpt_match_df["Cathode ID"].iloc[idx]
                anode = lpt_match_df["Anode ID"].iloc[idx]
                ratios = self.fr_matching_ratios[anode][cathode]
                set_id = lpt_match_df["(Potential) Set ID"].iloc[idx]
                anode_obj = fr_map[anode]

                all_ratios.extend(ratios)

                flow_line, = ax_flow.plot(
                    fms_specifications["lpt_voltages"],
                    match_flow,
                    label=f"Set {set_id} – match {lpt_match_df["Match #"].iloc[idx]}, margin: {match_margin}"
                )

                ax_ratio.plot(
                    anode_obj.pressures,
                    ratios,
                    color=flow_line.get_color(),
                )

            ax_flow.plot(
                fms_specifications["lpt_voltages"],
                fms_specifications["min_flow_rates"],
                linestyle="--",
                label="Min Flow Rate Spec"
            )
            ax_flow.plot(
                fms_specifications["lpt_voltages"],
                fms_specifications["max_flow_rates"],
                linestyle="--",
                label="Max Flow Rate Spec"
            )

            ax_flow.set_ylim(0, 6)
            ax_flow.set_title(
                f"Flow Rate [mg/s {anode_obj.gas_type}] vs LPT Voltage [mV]. \n LPT Reference Temperature: {temperature} ⁰C"
            )
            ax_flow.set_xlabel("LPT Voltage [mV]")
            ax_flow.set_ylabel(f"Flow Rate [mg/s {anode_obj.gas_type}]")
            ax_flow.grid(True)

            ax_ratio.set_ylim(min(all_ratios) - 4, max(all_ratios) + 3)
            ax_ratio.axhline(match_ratio + 0.5, label=f"Ratio: {match_ratio} ± 0.5", color="tab:red", linestyle="--")
            ax_ratio.axhline(match_ratio - 0.5, color="tab:red", linestyle="--")

            ax_ratio.set_title("A/C Ratios vs Inlet Pressure")
            ax_ratio.set_xlabel("Inlet Pressure [barA]")
            ax_ratio.set_ylabel("Anode-to-Cathode Ratio")
            ax_ratio.grid(True)

            # Legends
            handles_flow, labels_flow = ax_flow.get_legend_handles_labels()
            handles_ratio, labels_ratio = ax_ratio.get_legend_handles_labels()
            fig.legend(
                handles_flow + handles_ratio,
                labels_flow + labels_ratio,
                loc="lower center",
                bbox_to_anchor=(0.5, -0.25),
                ncol = max(len(lpt_match_df) // 4, 1)
            )

            plt.tight_layout()
            plt.show()

    def _handle_individual_set(self, flow_rates: list[float], voltages: list[float], order: int = 3) -> dict[str, Any]:
        flow_rates = np.array(flow_rates)
        voltages = np.array(voltages)
        polyfit = np.polyfit(voltages, flow_rates, order)

        lpt_voltages: list[float] = fms_specifications["lpt_voltages"]
        max_flow_rates: list[float] = fms_specifications["max_flow_rates"]
        min_flow_rates: list[float] = fms_specifications["min_flow_rates"]
        calculated_total_flows = np.polyval(polyfit, lpt_voltages).flatten().tolist()
        max_margin = np.array(max_flow_rates) - np.array(calculated_total_flows)
        min_margin = np.array(calculated_total_flows) - np.array(min_flow_rates)
        fr_data = {"set_id": "", "fms": "", "tot_flow": calculated_total_flows,
                "max_deviation": np.average(max_margin),
                "min_deviation": np.average(min_margin),
                "worst_margin": np.min(np.minimum(max_margin, min_margin)),
                "individual_pass": 1 if all(min_f <= calc_f <= max_f 
                        for min_f, max_f, calc_f in zip(min_flow_rates, max_flow_rates, calculated_total_flows)) else 0
                    }
        return fr_data

    def _build_set_matching_dict(
        self,
        matching_list: list[dict[str, Any]],
        good_lpts: list[LPTCalibration],
        temperature: float,
    ) -> tuple[dict[tuple[str, str], dict[str, dict[str, Any]]], dict[tuple[str, str], Any]]:
        """
        Build the mapping from (anode_id, cathode_id) set identifiers to
        LPT candidates and their associated matching data.

        Returns:
            set_matching_dict: {(anode_id, cathode_id): {lpt_id: {...}}}
            set_id_map: mapping from (anode_id, cathode_id) to existing set_id (if any)
        """
        set_matching_dict: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        set_id_map: dict[tuple[str, str], Any] = {}

        for _set in matching_list:
            anode_fr: AnodeFR = _set.get("anode")
            cathode_fr: CathodeFR = _set.get("cathode")
            set_identifier = (anode_fr.fr_id, cathode_fr.fr_id)
            pressures = anode_fr.pressures
            anode_flow_rates = np.array(anode_fr.flow_rates)
            cathode_flow_rates = np.array(cathode_fr.flow_rates)
            tot_flow_rates = anode_flow_rates + cathode_flow_rates
            set_matching_dict[set_identifier] = {}
            set_id_map[set_identifier] = _set.get("set_id", None)
            ratios = _set.get("ratios", [])
            for lpt in good_lpts:
                # if lpt.set_id or lpt.lpt_id.startswith("N"):
                #     continue
                if lpt.set_id:
                    continue
                voltages = self.calculate_lpt_voltage(
                    lpt=lpt,
                    pressures=pressures,
                    temperature=temperature,
                )
                fr_data = self._handle_individual_set(tot_flow_rates, voltages)
                if fr_data.get("individual_pass") == 1:
                    tot_flow = fr_data.get("tot_flow", [])
                    worst_margin = fr_data.get("worst_margin")
                    set_matching_dict[set_identifier][lpt.lpt_id] = {
                        "worst_margin": worst_margin,
                        "tot_flow": tot_flow,
                        "voltages": voltages,
                        "ratios": ratios
                    }

        return set_matching_dict, set_id_map

    def _build_lpt_matching_dataframe(
        self,
        set_matching_dict: dict[tuple[str, str], dict[str, dict[str, Any]]],
        set_id_map: dict[tuple[str, str], Any],
        max_set: int,
    ) -> pd.DataFrame:
        """
        From the per-set matching dictionary, build the final LPT matching
        DataFrame using maximum weight matching.
        """
        G = nx.Graph()
        for set_id in set_matching_dict:
            for lpt_id in set_matching_dict[set_id]:
                weight = set_matching_dict[set_id][lpt_id]["worst_margin"]
                G.add_edge(set_id, lpt_id, weight=weight)

        matching = nx.algorithms.max_weight_matching(G, weight="weight")
        set_ids = list(set_matching_dict.keys())
        matching_dict: dict[tuple[str, str], str] = {}
        for u, v in matching:
            if u in set_ids:
                matching_dict[u] = v
            else:
                matching_dict[v] = u

        max_match_data = []
        for idx, set_id in enumerate(sorted(matching_dict, key=lambda x: self._fr_id_sort_key(x[0]))):
            lpt_id = matching_dict[set_id]
            worst_margin = set_matching_dict[set_id][lpt_id]["worst_margin"]
            flow = set_matching_dict[set_id][lpt_id]["tot_flow"]
            voltages = set_matching_dict[set_id][lpt_id]["voltages"]
            ratios = set_matching_dict[set_id][lpt_id]["ratios"]
            set_id_check = set_id_map[set_id]
            set_id_entry = set_id_check if set_id_check else max_set + idx + 1
            row = {
                "(Potential) Set ID": set_id_entry,
                "Anode ID": set_id[0],
                "Cathode ID": set_id[1],
                "LPT ID": lpt_id,
                "flow": flow,
                "Worst Margin": f"{worst_margin:.3f}",
                "voltages": voltages
            }
            for idx, i in enumerate(ratios):
                row[f"Ratio {idx + 1}"] = f"{i:.2f}"

            max_match_data.append(row)

        lpt_match_df = pd.DataFrame(max_match_data)
        lpt_match_df.sort_values(
            by="(Potential) Set ID", key=lambda x: x.apply(int),
        )
        lpt_match_df.insert(0, "Match #", range(1, len(lpt_match_df) + 1))

        return lpt_match_df

    def match_sets_to_lpt(self, matching_list: list[dict[str, Any]], temperature: float = 22) -> pd.DataFrame | plt.figure:
        """
        Function that matches existing FR pairs to an LPT that makes sure the LPT Slope spec is met.

        :param matching_list: List of dictionaries where each entry contains the anode_id, cathode_id and corresponding flow rates.
        :type matching_list: list[dict[str, Any]]
        :param temperature: LPT Reference Temperature.
        :type temperature: float
        """
        good_lpts = self.query_lpt_status(get_good_lpts=True)
        self._get_all_manifolds_with_sets()
        max_set = max([int(i.set_id) for i in self.all_sets])

        set_matching_dict, set_id_map = self._build_set_matching_dict(
            matching_list=matching_list,
            good_lpts=good_lpts,
            temperature=temperature,
        )

        lpt_match_df = self._build_lpt_matching_dataframe(
            set_matching_dict=set_matching_dict,
            set_id_map=set_id_map,
            max_set=max_set,
        )

        return lpt_match_df


    def lpt_certification_field(self, lpt_id: str = None) -> None:
        """
        Create an interactive widget to select LPT certification batch
        and display LPT investigation plots.
        Args:
            lpt_id (str): Specific LPT ID to investigate (optional).
        """
        certification_field = widgets.Dropdown(
            options=['all'] + self.all_lpt_certifications,
            description='Select Certification:',
            layout=widgets.Layout(width='350px'),
            style={'description_width': '150px'},
            value='all'
        )

        output = widgets.Output()

        def on_certification_change(change):
            certification = change['new'].replace(' (Current)', '') if change['new'] else 'all'
            with output:
                output.clear_output()
                self.lpt_investigation(certification, lpt_id)

        certification_field.observe(on_certification_change, names='value')
        form = widgets.VBox([
            widgets.HTML('<h3>Select Batch for Comparison</h3>'),
            certification_field,
            output
        ])
        display(form)

        with output:
            output.clear_output()
            self.lpt_investigation('all', lpt_id)

    def lpt_investigation(self, certification: str = 'all', lpt_id: str = None, get_lpts: bool = False) -> None:
        """
        Perform LPT investigation by plotting voltage distributions at which the pressure threshold is read.
        Args:
            certification (str): Certification batch to analyze ('all' for all batches).
            lpt_id (str): Specific LPT ID to investigate (optional).
        """
        self._get_all_lpts()
        if self.manifold and not lpt_id:
            lpt = self.manifold.lpt[0] if self.manifold.lpt else None
            if self.fms_entry:
                lpt_from_fms = self.fms_entry.lpt_id
            else:
                lpt_from_fms = None
            if not lpt and not lpt_from_fms:
                print("No LPT associated with this manifold.")
                return
            if not lpt:
                lpt = self.session.query(LPTCalibration).filter_by(lpt_id=lpt_from_fms).first()
            
            if not lpt:
                print("No LPT calibration data found.")
                return
        elif lpt_id:
            lpt = self.session.query(LPTCalibration).filter_by(lpt_id=lpt_id).first()
            if not lpt:
                print(f"No LPT calibration data found for LPT ID: {lpt_id}.")
                return
        else:
            lpt = None
            lpt_from_fms = None

        lpt_id = lpt.lpt_id if lpt else None
        signal = lpt.signal if lpt else None
        pressures = lpt.p_calculated if lpt else None
        
        all_signals = []
        all_lpts = self.all_lpts if certification == 'all' else [i for i in self.all_lpts if i.certification == certification]
        for l in all_lpts:
            if l.signal and l.p_calculated:
                all_signals.append(l.signal[np.argmin(np.abs(np.array(l.p_calculated)-self.pressure_threshold))])

        if pressures and signal:
            zero_p_voltage = signal[np.argmin(np.abs(np.array(pressures)-self.pressure_threshold))]
        if certification == 'all':
            title = f'LPT Voltage @ {self.pressure_threshold} [bar] Distribution, LPT: {lpt_id}' if lpt else 'LPT Voltage Distribution of All LPTs'
        else:
            title = f'LPT Voltage @ {self.pressure_threshold} [bar] Distribution, LPT: {lpt_id} ({self.lpt_certification})\nCompared to \
                    {certification}' if lpt else f'LPT Voltage Distribution of {certification}'

        if not get_lpts:
            plt.figure(figsize=(10, 5))
            plt.hist(all_signals, bins=40, edgecolor='black')
            if lpt:
                plt.axvline(zero_p_voltage, color='red', linestyle='--', label=f'LPT {lpt_id} Voltage @ {self.pressure_threshold} [bar]: {zero_p_voltage:.2f} [mV]')
            plt.axvline(self.signal_threshold, color='red', linestyle='-', label='Max Voltage: 7.5 [mV]')
            plt.title(title)
            plt.xlabel('Voltage [mV]')
            plt.ylabel('Count')
            plt.grid(True)
            plt.legend(loc='lower center', bbox_to_anchor = (0.5,-0.25))
            plt.show()

        self.query_lpt_status(all_lpts, lpt, certification)


    def plot_lpt_calibration(self, lpt_id: str = None) -> None:
        """
        Plot LPT calibration data including signal vs calculated pressure
        and calculated temperature vs resistance.
        Args:
            lpt_id (str): Specific LPT ID to plot (optional).
        """
        
        if not lpt_id:
            lpt = self.manifold.lpt[0] if self.manifold.lpt else None
            if self.fms_entry:
                lpt_from_fms = self.fms_entry.lpt_id
            else:
                lpt_from_fms = None
            if not lpt and not lpt_from_fms:
                print("No LPT associated with this manifold.")
                return
            if not lpt and lpt_from_fms:
                lpt = self.session.query(LPTCalibration).filter_by(lpt_id=lpt_from_fms).first()
            
            if not lpt:
                print("No LPT calibration data found.")
                return
        else:
            lpt = self.session.query(LPTCalibration).filter_by(lpt_id=lpt_id).first()
            if not lpt:
                print(f"No LPT calibration data found for LPT ID: {lpt_id}.")
                return
        
        signal = lpt.signal
        resistance = lpt.resistance
        p_calculated = lpt.p_calculated
        temp_calculated = lpt.temp_calculated
        base_signal = lpt.base_signal
        base_resistance = lpt.base_resistance
        coefficients: list[LPTCoefficients] = lpt.coefficients if lpt.coefficients else None
        if coefficients:
            pressure_coeffs = [coeff.parameter_value for coeff in coefficients if coeff.parameter_name.endswith('_p')]
            temperature_coeffs = [coeff.parameter_value for coeff in coefficients if coeff.parameter_name.endswith('_t')]
        else:
            pressure_coeffs = []
            temperature_coeffs = []

        if not (signal and resistance and p_calculated and temp_calculated and pressure_coeffs and temperature_coeffs):
            print("Incomplete LPT calibration data.")
            return

        field_names = sorted(list(set([i.value.split("_")[0] for i in LPTCoefficientParameters if i != LPTCoefficientParameters.LPT_ID])), key=lambda x: (x[0], x[-1]))  

        df = pd.DataFrame({
            "Field": field_names,
            "Coefficient_P": pressure_coeffs,
            "Coefficient_T": temperature_coeffs
        })
        display(df)

        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        plt.plot(signal, p_calculated, label='Calculated Pressure')
        plt.title(f'Signal vs Calculated Pressure, Base Resistance: {base_resistance} [Ohm]\nLPT: {lpt.lpt_id}')
        plt.xlabel('Signal [mV]')
        plt.ylabel('Calculated Pressure [bar]')
        plt.grid(True)

        plt.subplot(1, 2, 2)
        plt.plot(resistance, temp_calculated, label='Calculated Temperature')
        plt.title(f'Resistance vs Calculated Temperature, Base Signal: {base_signal} [mV]\nLPT: {lpt.lpt_id}')
        plt.xlabel('Resistance [Ohm]')
        plt.ylabel('Calculated Temperature [°C]')
        plt.grid(True)

        plt.tight_layout()
        plt.show()

    def calculate_lpt_voltage(self, lpt: str | LPTCalibration, pressures: list[float], temperature: float = 22) -> list[float]:
        """
        Function that interpolates the LPT Calibration to find the expected
        LPT Voltage output at given pressures and temperature.
        
        :param lpt_id: The identifier of the considered LPT.
        :type lpt_id: str
        :param temperature: The reference temperature used to find the LPT resistance.
        :type temperature: float
        :param pressures: List of pressures that need to be converted to voltage outputs.
        :type pressures: list[float]
        :return: Returns a list of LPT voltage outputs, same size as the input pressures.
        :rtype: list[float]
        """
        self._get_all_lpts()
        lpt_entry = lpt if isinstance(lpt, LPTCalibration) else next((i for i in self.all_lpts if i.lpt_id == lpt), None)
        if not lpt_entry:
            print(f"No data found for {lpt.lpt_id if isinstance(lpt, LPTCalibration) else lpt}")
            return
        
        lpt_coefficients: list[LPTCoefficients] = lpt_entry.coefficients
        if not lpt_coefficients:
            print(f"No coefficient data found for {lpt.lpt_id if isinstance(lpt, LPTCalibration) else lpt}")
            return
        
        calibrated_temp = np.array(lpt_entry.temp_calculated)
        resistance = np.array(lpt_entry.resistance)
        p_coeffs = [i for i in lpt_coefficients if i.parameter_name.endswith("_p")]
        p_coeffs = sorted(
            p_coeffs,
            key=lambda x: (
                x.parameter_name.split("_")[0][0].upper(),                 
                int(''.join(filter(str.isdigit, x.parameter_name.split("_")[0])))  
            )
        )
        p_coeffs = [i.parameter_value for i in p_coeffs]
        temp_idx = np.argmin(np.abs(calibrated_temp - temperature))
        resistance = resistance[temp_idx]
        possible_U = np.linspace(0, 200, 3000)
        U = []
        for i in pressures:
            trial_p = self.fms.manifold_data.calculate_pressure(R = resistance, U = possible_U, c = p_coeffs)
            actual_U = possible_U[np.argmin(np.abs(trial_p - i))]
            U.append(actual_U)
        return U

    def get_lpt_status(self, signal: np.ndarray, pressures: np.ndarray) -> dict:
        """
        Determine the LPT status based on signal and pressure data.
        Args:
            signal (np.ndarray): Array of signal values.
            pressures (np.ndarray): Array of pressure values.
        Returns:
            dict: Dictionary containing 'status' and 'signal' keys.
        """
        if not signal or not pressures or len(signal) != len(pressures):
            raise ValueError("Signal and pressure arrays must be non-empty and of equal length.")

        pressures = np.asarray(pressures)
        signal = np.asarray(signal)

        check_idx = np.argmin(np.abs(pressures - self.pressure_threshold))
        check_signal = signal[check_idx]
        adjusted_signal = check_signal + self.signal_tolerance
        status_dict = {
            'status': None,
            'signal': adjusted_signal
        }

        if adjusted_signal < self.signal_threshold:
            status_dict['status'] = LimitStatus.TRUE
        elif np.isclose(adjusted_signal, self.signal_threshold, atol=1e-3):
            status_dict['status'] = LimitStatus.ON_LIMIT
        else:
            status_dict['status'] = LimitStatus.FALSE

        return status_dict

    def query_lpt_status(self, certification: str = 'all', get_good_lpts: bool = False) -> list[LPTCalibration]:
        """
        Query the LPT status from the database.

        :param get_good_lpts: Whether to return only the LPTs within spec.
        :return: List of LPTCalibration entries that fall within spec.
        :rtype: list[LPTCalibration]
        """
        self._get_all_lpts()
        lpt_status = self.all_lpts
        # check = lpt_status.filter_by(lpt_id = 'P339637').first()
        # print(self.get_lpt_status(check.signal, check.p_calculated)['signal'])
        if get_good_lpts:
            return [entry for entry in lpt_status if entry.within_limits == LimitStatus.TRUE]
        
        lpt_within_limits = [entry.within_limits for entry in lpt_status if entry.within_limits]
        if lpt_within_limits:
            lpt_status = [entry for entry in lpt_status if entry.within_limits == LimitStatus.FALSE]
        else:
            for entry in lpt_status:
                entry.within_limits = self.get_lpt_status(entry.signal, entry.p_calculated)['status']
            lpt_status = [entry for entry in lpt_status if entry.within_limits == LimitStatus.FALSE]
        signals = [self.get_lpt_status(entry.signal, entry.p_calculated)['signal'] for entry in lpt_status]
        amount = len(lpt_status)
        allocated = {entry.lpt_id: entry.manifold.allocated if entry.manifold else None for entry in lpt_status}
        percentage = amount/(len(self.all_lpts) or 1) * 100


        allocated_to_fms = [allocated.get(entry.lpt_id, None) for entry in lpt_status]
        serials = {'serial_number': [entry.lpt_id for entry in lpt_status], 'allocated_to_fms': allocated_to_fms, 'signal': signals}
        df = pd.DataFrame([serials['serial_number'], serials['allocated_to_fms'], serials['signal']],
                index=['serial_number', 'allocated_to_fms', 'signal'])
        if not certification == 'all':
            print(f"LPTs out of spec in {certification}")
        print(f"Amount of LPTs out of limits: {amount}")
        print(f"Percentage of LPTs out of limits: {percentage:.2f}%")
        print("Serials of LPTs out of limits:")            
        display_df_in_chunks(df)

    def get_certifications(self) -> None:
        """
        Display certification summary for all parts related to the manifold in a concise overview.
        """
        self._get_all_certifications()
        # Filter out None certifications and build DataFrames
        manifold_df = pd.DataFrame(
            [(c, count) for c, count in self.manifold_cert_counts if c is not None],
            columns=['certification', 'count']
        )

        manifold_assembly_df = pd.DataFrame(
            [(c, s) for c, s in self.manifold_assembly_certs if c is not None],
            columns=['certification', 'set_ids']
        )

        lpt_df = pd.DataFrame(
            [(c, count) for c, count in self.lpt_count_dict.items() if c is not None],
            columns=['certification', 'count']
        )

        fr_part_df = pd.DataFrame(
            [(c, part, count) for c, part, count in self.fr_part_certs if c is not None],
            columns=['certification', 'part_name', 'count']
        )

        # Create Output widgets for each DataFrame
        manifold_out = widgets.Output()
        manifold_assembly_out = widgets.Output()
        lpt_out = widgets.Output()
        fr_part_out = widgets.Output()

        # Display DataFrames in the Output widgets
        with manifold_out:
            display(manifold_df)

        with manifold_assembly_out:
            display(manifold_assembly_df)

        with lpt_out:
            display(lpt_df)

        with fr_part_out:
            display(fr_part_df)

        # Build VBox layout
        form = widgets.VBox([
            widgets.HTML('<h3>Certification Summary</h3>'),

            widgets.HTML('<h4>Manifold Certifications</h4>'),
            manifold_out,

            widgets.HTML('<h4>Manifold Assembly Certifications</h4>'),
            manifold_assembly_out,

            widgets.HTML('<h4>LPT Certifications</h4>'),
            lpt_out,

            widgets.HTML('<h4>FR Part Certifications</h4>'),
            fr_part_out,
        ])

        display(form)

