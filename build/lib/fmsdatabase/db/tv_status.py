from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from ..utils.general_utils import TVProgressStatus
from .base import Base

class TVStatus(Base):
    """
    -------------------
    TV Status table 1.6
    -------------------

    Columns
    -------
    tv_id : Integer
        Primary Key. Auto-incrementing identifier.
    allocated : String(50)
        Foreign Key. FMS Identifier linking to FMSMain table.
    pre_weld_opening_temp : Float
        Pre-weld opening temperature of the thermal valve, in °C.
    opening_temp : Float
        Opening temperature of the thermal valve, in °C.
    welded : Boolean
        Indicates if the thermal valve is welded.
    min_opening_temp : Float
        Minimum acceptable opening temperature, in °C.
    max_opening_temp : Float
        Maximum acceptable opening temperature, in °C.
    built_by : String(20)
        Name of the person who built the thermal valve.
    image_path : String(20)
        Path to the image of the thermal valve.
    electric_assembly_by : String(20)
        Name of the person who performed the electric assembly.
    coil_resistance : Float
        Specified coil resistance of the thermal valve, in Ohm.
    coil_resistance_measured : Float
        Measured coil resistance of the thermal valve, in Ohm.
    coil_inductance : Float
        Coil inductance of the thermal valve, in mH.
    coil_capacitance : Float
        Coil capacitance of the thermal valve, in nF.
    coil_completion_date : DateTime
        Date when the coil assembly was completed.
    rotation_nut : Float
        Rotation nut measurement, in degrees.
    start_date : DateTime
        Start date of the thermal valve manufacturing.
    end_date : DateTime
        End date of the thermal valve manufacturing.
    final_weld_gap : String(20)
        Final weld gap measurement, in mm.
    rotation_plunger : Float
        Rotation plunger measurement, in degrees.
    weld_gap : Float
        Weld gap measurement, in mm.
    gasket_gap : Float
        Gasket gap measurement, in mm.
    gasket_thickness : Float
        Gasket thickness measurement, in mm.
    surface_roughness : Float
        Surface roughness measurement, in microns.
    status : Enum(TVProgressStatus)
        Status indicating the progress of the thermal valve.
    remark : String(255)
        Additional remarks about the thermal valve.
    model : String(50)
        Model identifier of the thermal valve.
    revision : String(50)
        Revision identifier of the thermal valve (R#).

    Relationships
    -------------
    fms_main : FMSMain
        One-to-one relationship with FMSMain table.
    certifications : TVCertification
        One-to-many relationship with TVCertification table.
    test_runs : TVTestRuns
        One-to-many relationship with TVTestRuns table.
    coil_assembly : CoilAssembly
        One-to-one relationship with CoilAssembly table.
    tvac : TVTvac
        One-to-many relationship with TVTvac table.
    """
    __tablename__ = 'tv_status'

    tv_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    allocated = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=True) 
    pre_weld_opening_temp = Column(Float, nullable=True)
    opening_temp = Column(Float, nullable=True)
    welded = Column(Boolean, nullable=True)
    min_opening_temp = Column(Float, nullable=True)
    max_opening_temp = Column(Float, nullable=True)
    built_by = Column(String(20), nullable=True)
    image_path = Column(String(255), nullable=True)
    electric_assembly_by = Column(String(20), nullable=True)
    coil_resistance = Column(Float, nullable=True)
    coil_resistance_measured = Column(Float, nullable=True)
    coil_inductance = Column(Float, nullable=True)
    coil_capacitance = Column(Float, nullable=True)
    coil_completion_date = Column(DateTime, nullable=True) 
    rotation_nut = Column(Float, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    final_weld_gap = Column(String(20), nullable=True)
    rotation_plunger = Column(Float, nullable=True)
    weld_gap = Column(Float, nullable=True)
    gasket_gap = Column(Float, nullable=True)
    gasket_thickness = Column(Float, nullable=True)
    surface_roughness = Column(Float, nullable=True)
    status = Column(Enum(TVProgressStatus, native_enum=False), nullable=True)
    remark = Column(String(255), nullable=True)
    model = Column(String(50), nullable=True)
    revision = Column(String(50), nullable=True)

    fms_main = relationship("FMSMain", back_populates="thermal_valve")
    certifications = relationship("TVCertification", back_populates="status")
    test_runs = relationship("TVTestRuns", back_populates="status")
    coil_assembly = relationship("CoilAssembly", back_populates="tv_status")
    tvac = relationship("TVTvac", back_populates="status")