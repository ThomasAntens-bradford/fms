import os
import re
import io

from IPython.display import display
import ipywidgets as widgets
from datetime import datetime
from sqlalchemy.orm import Session
from docxtpl import DocxTemplate, InlineImage, RichText
from docx2pdf import convert
from docx.shared import Mm

from .. import FMSDataStructure
from ..db import AnodeFR, CathodeFR
from ..utils.general_utils import show_modal_popup, field
import sharedBE as be
from .query.manifold_query import ManifoldQuery


class FRTRSGenerator:
    def __init__(self, local: bool = True, save_path: str = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\10 - Documents\TRS"):
        self.fms_data = FMSDataStructure(local = local)
        self.fr_data = self.fms_data.fr_data
        self.fr_sql = self.fms_data.fr_sql
        self.context = {}
        self.save_path = save_path
        self.template_path = os.path.join(os.path.dirname(__file__), "templates", "fr_trs_template.docx")
        self.session: "Session" = self.fms_data.Session()
        self.author = self.fms_data.author
        self.dates: list[datetime] = []

        self.anode_reference_orifice = self.fr_data.anode_reference_orifice
        self.cathode_reference_orifice = self.fr_data.cathode_reference_orifice
        self.orifice_tolerance = 0.003
        self.reference_thickness = self.fr_data.reference_thickness
        self.thickness_tolerance = self.fr_data.thickness_tolerance
        self.min_radius = self.fr_sql.min_radius
        self.max_radius = self.fr_sql.max_radius

        # self.all_anodes: list[AnodeFR] = self.session.query(AnodeFR).filter(AnodeFR.trs_reference == None).all()
        # self.all_cathodes: list[CathodeFR] = self.session.query(CathodeFR).filter(CathodeFR.trs_reference == None).all()
        self.all_anodes: list[AnodeFR] = self.session.query(AnodeFR).all()
        self.all_cathodes: list[CathodeFR] = self.session.query(CathodeFR).all()

        self.anode_certifications = list(set(["-".join(entry.fr_id.split("-")[:-1]) for entry in self.all_anodes]))
        self.cathode_certifications = list(set(["-".join(entry.fr_id.split("-")[:-1]) for entry in self.all_cathodes]))
        self.output = widgets.Output()
        self.plot_output = widgets.Output()
        self.container = widgets.VBox()
        display(self.container)

    def start_generation(self):
        anode_widget = widgets.SelectMultiple(
            options=self.anode_certifications,
            description="Anode Batches to Include:",
            disabled=False,
            layout=widgets.Layout(width="600px", height="300px"),
            style={'description_width': '250px'}
        )
        cathode_widget = widgets.SelectMultiple(
            options=self.cathode_certifications,
            description="Cathode Batches to Include:",
            disabled=False,
            layout=widgets.Layout(width="600px", height="300px"),
            style={'description_width': '250px'}
        )

        generate_button = widgets.Button(
            description="Generate TRS",
            button_style = 'info',
            layout=widgets.Layout(width="300px", height="50px")
        )

        fr_widget = widgets.HBox([anode_widget, cathode_widget])
        form = widgets.VBox([
            fr_widget,
            widgets.VBox([], layout = widgets.Layout(height = "50px")),
            self.get_reference_values(),
            widgets.VBox([], layout = widgets.Layout(height = "50px")),
            generate_button,
            self.output,
            self.plot_output
        ],
        layout = widgets.Layout(justify_content = 'flex-start'))

        self.container.children = self.container.children + (form,)

        def on_generate_clicked(b):
            if not anode_widget.value and not cathode_widget.value:
                with self.output:
                    self.output.clear_output()
                    print("Please select at least one batch for either the anode or the cathode FR, or both.")
                    return

            self.generate_trs(anode_widget.value, cathode_widget.value)

        generate_button.on_click(on_generate_clicked)

    def generate_trs(self, anode_batches, cathode_batches):
        
        relevant_anodes = [entry for entry in self.all_anodes if "-".join(entry.fr_id.split("-")[:-1]) in anode_batches]
        relevant_cathodes = [entry for entry in self.all_cathodes if "-".join(entry.fr_id.split("-")[:-1]) in cathode_batches]


        if any(not bool(entry.flow_rates) for entry in relevant_anodes + relevant_cathodes):
            show_modal_popup("Some selected FRs in the selected batches do not have flow rate data. \n" \
                                "These FRs will be excluded from the TRS, do you want to continue?",\
                                      continue_action = lambda: self.finalize_trs(relevant_anodes, relevant_cathodes, anode_batches, cathode_batches))                    
            return
        else:
            self.finalize_trs(relevant_anodes, relevant_cathodes, anode_batches, cathode_batches)

    def get_tools(self, anodes: list[AnodeFR], cathodes: list[CathodeFR]) -> list[dict[str, str]]:
        all_frs = anodes + cathodes
        all_used_tools = []

        def format_value(tool: be.db.TestingTools, column: str):
            value = getattr(tool, column)
            if isinstance(value, (datetime,)):
                return value.strftime("%d-%m-%Y")
            elif column == "description":
                return " ".join(value.split("_")).title()
            return value
        
        for fr in all_frs:
            tools = fr.tools
            for tool in tools:
                description = tool.get("description")
                model = tool.get("model")
                serial = tool.get("serial_number")

                tool_entry = be.tools.get_tool_by_attributes(model = model, description = description, serial_number = serial)

                if tool_entry:
                    complete_tool_entry = {c.name: format_value(tool=tool_entry, column=c.name) for c in be.tools.__columns__}
                    if not complete_tool_entry in all_used_tools:
                        all_used_tools.append(complete_tool_entry)
        
        return all_used_tools
    
    def get_reference_values(self) -> None:

        anode_reference_orifice = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.001,
            value = self.anode_reference_orifice,
            **field("Anode Orifice Ref:")
        )
        cathode_reference_orifice = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.001,
            value = self.cathode_reference_orifice,
            **field("Cathode Orifice Ref:")
        )
        orifice_tolerance = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.001,
            value = self.orifice_tolerance,
            **field("Orifice Tol:")
        )
        orifice_row = widgets.HBox([anode_reference_orifice, cathode_reference_orifice, orifice_tolerance])
        thickness_reference = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.01,
            value = self.reference_thickness,
            **field("Reference Thickness:")
        )
        thickness_tol = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.01,
            value = self.thickness_tolerance,
            **field("Thickness Tol:")
        )
        thickness_row = widgets.HBox([thickness_reference, thickness_tol])
        min_radius = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.01,
            value = self.min_radius,
            **field("Min Radius:")
        )
        max_radius = widgets.BoundedFloatText(
            min = 0,
            max = 1,
            step = 0.01,
            value = self.max_radius,
            **field("Max Radius:")
        )
        radius_row = widgets.HBox([min_radius, max_radius])

        form = widgets.VBox([
            widgets.HTML("<h4>Please enter / change the reference values of the FR dimensions and their tolerances.</h4>"),
            orifice_row, 
            thickness_row,
            radius_row
        ])

        widget_map = {
            anode_reference_orifice: "anode_reference_orifice",
            cathode_reference_orifice: "cathode_reference_orifice",
            orifice_tolerance: "orifice_tolerance",
            thickness_reference: "thickness_reference",
            thickness_tol: "thickness_tolerance",
            min_radius: "min_radius",
            max_radius: "max_radius"
        }
        def _set_widget_silently(widget, value):
            observers = widget._trait_notifiers.get("value", {}).copy() if hasattr(widget, "_trait_notifiers") else {}
            for cb in observers:
                widget.unobserve(cb, names="value")
            
            widget.value = value 

            for cb in observers:
                widget.observe(cb, names="value")

        def on_field_change(change, widget: widgets.Widget):
            if change["name"] != "value":
                return

            if change["old"] == change["new"]:
                return

            key = widget_map[widget]
            new = change["new"]
            ref = getattr(self, widget_map[widget])

            if "radius" in key:
                if 'max' in key:
                    if widget.value <= self.min_radius:
                        with self.output:
                            self.output.clear_output()
                            print("Maximum radius cannot be lower than or equal to minimum radius.")
                            widget.value = ref
                            return
                elif 'min' in key:
                    if widget.value >= self.min_radius:
                        with self.output:
                            self.output.clear_output()
                            print("Minimum radius cannot be higher than or equal to maximum radius.")
                            widget.value = ref
                            return  

            if ref != 0 and abs((new - ref) / ref) * 100 < 120:
                setattr(self, widget_map[widget], new)
                return

            with self.output:
                self.output.clear_output()
                show_modal_popup(
                    f"{new} [mm] deviates quite a lot with the designed {" ".join(widget_map[widget].split("_")).title()}, do you want to continue?",
                    cancel_action=lambda: _set_widget_silently(widget, ref),
                    continue_action=lambda: setattr(self, widget_map[widget], new),
                )
            
        for i in widget_map:
            i.observe(lambda x, widget = i: on_field_change(change = x, widget = widget))

        return form

    def _color_if_out_of_bounds(self, value, low, high):
        if not value:
            return ""
        if value < low or value > high:
            rt = RichText()
            rt.add(f"{value:.3f}", color="FF0000")
            return rt
        return f"{value:.3f}"

    def _get_new_filename(self) -> str:
        """
        Generates a new unique filename for the report based on existing entries in the database.
        Returns:
            str: The generated filename.
        """
        all_filenames = os.listdir(self.save_path)
        with self.output:
            for name in all_filenames:
                print(name)
        filenames = [name for name in all_filenames if name.startswith("FMS-LP-BE-TRS-") and name.endswith(".docx")]
        numbers = []
        for name in filenames:
            match = re.findall(r"\b\d{4}\b", name)
            if match:
                numbers.extend(map(int, match))

        new_num = str(max(numbers) + 1 if numbers else 1).zfill(4)
        doc_ref = f"FMS-LP-BE-TRS-{new_num}"
        filename = f"{doc_ref}-i1-0 - FR Testing 20025.10.18-R4-001_005.docx"
        return doc_ref, filename
    
    def _process_fr_context(self, frs: list[AnodeFR | CathodeFR], type: str = "Anode") -> list[dict[str, str]]:
        """
        Docstring for _process_fr_context
        
        :param frs: List of AnodeFR or CathodeFR objects to process
        :type frs: list[AnodeFR | CathodeFR]
        :return: List of dictionaries containing processed FR data
        :rtype: list[dict[str, str]]
        """
        columns = AnodeFR.__table__.columns
        fr_context = []
        if not bool(frs):
            return fr_context
        for entry in frs:
            entry_dict = {}
            if entry.date:
                self.dates.append(entry.date)
            for c in columns:
                if c.name == "orifice_diameter":
                    low = self.anode_reference_orifice - self.orifice_tolerance if type == "Anode" else self.cathode_reference_orifice - self.orifice_tolerance
                    high = self.anode_reference_orifice + self.orifice_tolerance if type == "Anode" else self.cathode_reference_orifice + self.orifice_tolerance
                    entry_dict[c.name] = f"{getattr(entry, c.name):.4f}"
                    if low and high:
                        entry_dict["c"] = "C" if low <= getattr(entry, c.name) <= high else "F"
                elif c.name == "thickness":
                    low = self.reference_thickness - self.thickness_tolerance
                    high = self.reference_thickness + self.thickness_tolerance
                    entry_dict[c.name] = self._color_if_out_of_bounds(getattr(entry, c.name), low, high)
                elif c.name == "radius":
                    entry_dict[c.name] = self._color_if_out_of_bounds(getattr(entry, c.name), self.min_radius, self.max_radius)
                elif c.name == "fr_id":
                    entry_dict["serial"] = entry.fr_id.split("-")[-1]
                    entry_dict["certification"] = "-".join(entry.fr_id.split("-")[:-1])
                elif c.name == "deviation":
                    entry_dict["dev"] = f'{getattr(entry, c.name):.2f}'
                elif c.name == "drawing":
                    entry_dict[c.name] = getattr(entry, c.name).replace(",", ".")
                elif c.name != "flow_rates":
                    entry_dict[c.name] = f'{getattr(entry, c.name):.2f}' if isinstance(getattr(entry, c.name), float) else getattr(entry, c.name)
                else:
                    for i, p in enumerate(entry.pressures):
                        entry_dict[f"flowrate{str(p).replace('.', '')}"] = f"{entry.flow_rates[i]:.3f}"
            fr_context.append(entry_dict)
        return fr_context

    def finalize_trs(self, anodes: list[AnodeFR], cathodes: list[CathodeFR], anode_batches: list[str], cathode_batches: list[str]):
        with self.output:
            print("Generating TRS...")

        remove_anodes = [entry for entry in anodes if not bool(entry.flow_rates)]
        remove_cathodes = [entry for entry in cathodes if not bool(entry.flow_rates)]

        relevant_anodes = [i for i in anodes if i not in remove_anodes]
        relevant_cathodes = [i for i in cathodes if i not in remove_cathodes]

        self.context["author"] = self.author
        self.context["an_ref"] = self.anode_reference_orifice
        self.context["cat_ref"] = self.cathode_reference_orifice
        self.context["orifice_tolerance"] = self.orifice_tolerance
        self.context["nominal_thickness"] = self.reference_thickness
        self.context["thickness_tolerance"] = self.thickness_tolerance
        self.context["min_radius"] = self.min_radius
        self.context["max_radius"] = self.max_radius

        self.template = DocxTemplate(self.template_path)
        manifold_query = ManifoldQuery(session = self.session)

        self.context["anode"] = self._process_fr_context(relevant_anodes, type = "Anode")
        self.context["cathode"] = self._process_fr_context(relevant_cathodes, type = "Cathode")
        self.context["start_date"] = min(self.dates).strftime("%#d.%b.%Y").upper() if self.dates else ""
        self.context["end_date"] = max(self.dates).strftime("%#d.%b.%Y").upper() if self.dates else ""

        anode_batch_groups = {
            "-".join(cert.fr_id.split("-")[:-1]): [entry for entry in relevant_anodes if\
                                          entry.fr_id.startswith("-".join(cert.fr_id.split("-")[:-1]))]
            for cert in anodes
        }

        cathode_batch_groups = {
            "-".join(cert.fr_id.split("-")[:-1]): [entry for entry in relevant_cathodes if\
                                          entry.fr_id.startswith("-".join(cert.fr_id.split("-")[:-1]))]
            for cert in cathodes
        }

        exclusion_parts = []
        exclusion_list = []
        exclusion_count = 0
        frs_excluded = False

        if remove_anodes:
            frs_excluded = True
            for cert in anode_batches:
                serials = []
                for entry in remove_anodes:
                    if entry.fr_id.startswith(cert):
                        if cert not in exclusion_list:
                            exclusion_list.append(cert)
                        serials.append(entry.fr_id.split("-")[-1])
                        exclusion_count += 1
                if serials:
                    exclusion_parts.append(f"from {cert}, {', '.join(serials)}")

        if remove_cathodes:
            frs_excluded = True
            for cert in cathode_batches:
                serials = []
                for entry in remove_cathodes:
                    if entry.fr_id.startswith(cert):
                        if cert not in exclusion_list:
                            exclusion_list.append(cert)
                        serials.append(entry.fr_id.split("-")[-1])
                        exclusion_count += 1
                if serials:
                    exclusion_parts.append(f"from {cert}, {', '.join(serials)}")

        if exclusion_parts:
            exclusion_string = ", ".join(exclusion_parts)
            if exclusion_count == 1:
                exclusion_string = exclusion_string[0].upper() + exclusion_string[1:] + " is excluded from this TRS."
            else:
                exclusion_string = exclusion_string[0].upper() + exclusion_string[1:] + " are excluded from this TRS."
        else:
            exclusion_string = ""

        self.context["exclusion_string"] = exclusion_string
        self.context["frs_excluded"] = frs_excluded

        tools = self.get_tools(relevant_anodes, relevant_cathodes)
        self.context["tools"] = tools
        batches = []

        def process_groups(group_dict: dict[str, list[AnodeFR | CathodeFR]]):
            for cert, frs in group_dict.items():
                fr_ids = [int(entry.fr_id.split("-")[-1]) for entry in frs]
                if fr_ids:
                    min_fr_id = min(fr_ids)
                    max_fr_id = max(fr_ids)
                    data = {
                        "certification": cert,
                        "min_serial": min_fr_id,
                        "max_serial": max_fr_id,
                        "part_numbers": list(set([entry.drawing for entry in frs]))
                    }
                    if cert in exclusion_list:
                        data["exclusion"] = True
                    batches.append(data)

        process_groups(anode_batch_groups)
        process_groups(cathode_batch_groups)

        self.context['batches'] = sorted(batches, key=lambda x: (int(x['certification'].split('-')[0][1:]), int(x['certification'].split('-')[-1])))

        generation_date = datetime.now().date()
        self.context["date_header"] = generation_date.strftime("%#d.%b.%Y").upper()

        testers = ", ".join(list(set([entry.operator for entry in relevant_anodes + relevant_cathodes])))
        self.context["testers"] = testers

        tools = self.get_tools(relevant_anodes, relevant_cathodes)
        self.context["tools"] = tools

        anode_plot = manifold_query.fr_flow_analysis(certification = anode_batches, fr_type = "Anode", error = False, plot = False)
        cathode_plot = manifold_query.fr_flow_analysis(certification = cathode_batches, fr_type = "Cathode", error = False, plot = False)

        cathode_table_count = 1 if bool(relevant_cathodes) else 0
        anode_table_count =  cathode_table_count + 1
        cathode_figure_count = 2 if bool(relevant_cathodes) else 0
        anode_figure_count = cathode_figure_count + 1

        if bool(anode_plot):
            self.context["anode_plot"] = InlineImage(self.template, io.BytesIO(anode_plot), width=Mm(300))
        if bool(cathode_plot):
            self.context["cathode_plot"] = InlineImage(self.template, io.BytesIO(cathode_plot), width=Mm(300))

        self.context["anode_figure_caption"] = f"Figure {anode_figure_count} - Anode Flow Rate Analysis for Batches: {', '.join(anode_batches)}"
        self.context["cathode_figure_caption"] = f"Figure {cathode_figure_count} - Cathode Flow Rate Analysis for Batches: {', '.join(cathode_batches)}"
        self.context["anode_table_caption"] = f"Table {anode_table_count} - Anode Flow Restrictors Dimensional Measurements"
        self.context["cathode_table_caption"] = f"Table {cathode_table_count} - Cathode Flow Restrictors Dimensional Measurements"

        # with self.plot_output:
        #     display(widgets.Image(value = anode_plot, format = "png"))
        #     display(widgets.Image(value = cathode_plot, format = "png"))


        self.context["part_numbers"] = list(set([entry.drawing for entry in relevant_anodes + relevant_cathodes]))

        trs_reference, word_filename = self._get_new_filename()
        self.context["trs_reference"] = trs_reference

        all_keys = self.template.get_undeclared_template_variables()
        missing_keys = [k for k in all_keys if k not in self.context]

        if missing_keys and not ("end_date" in missing_keys or "start_date" in missing_keys):
            with self.output:
                for i in missing_keys:
                    print(f"Missing key in context: {i}")

        self.template.render(self.context)
        save_path = os.path.join(self.save_path, word_filename)
        self.template.save(save_path)

        with self.output:
            self.output.clear_output()
            print(f"TRS generated and saved to: {save_path}")

if __name__ == "__main__":
    generator = FRTRSGenerator()
    print(generator.anode_certifications)