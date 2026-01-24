from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, DateTime, Enum, Boolean
from ..utils.enums import FRStatus
from sqlalchemy.orm import relationship
from .base import Base

class CathodeFR(Base):
    """
    -----------------------------------
    Cathode Flow Restrictor Table 1.7.3
    -----------------------------------

    Columns
    -------
    fr_id : String
        Primary Key, unique Flow Restrictor ID.
    set_id : String
        Foreign Key, Manifold Set ID (references the main manifold table).
    drawing : String
        String describing the drawing identifier of the FR.
    thickness : Float
        Thickness in mm.
    temperature : Float
        Testing temperature in °C.
    orifice_diameter : Float
        Orifice diameter in mm.
    deviation : Float
        Percentage deviation from the standard orifice size (0.07095 mm).
    pressure_drop : JSON
        Pressure drops calculated using the Hagen-Poiseuille equation
        at the measured flow rates [pd1, pd2, ..., pdn] in Pa.
    radius : Float
        Radius in mm.
    pressures : JSON
        Measured pressures at different flow rates [p1, p2, ..., pn], usually just [1, 1.5, 2, 2.4] in bar.
    flow_rates : JSON
        Measured flow rates [f1, f2, ..., fn] in mg/s.
    extra_tests : JSON
        Additional tests conducted on the FR.
    date : DateTime
        Date of testing.
    status_geometry : Enum(FRStatus)
        Geometry status (DIFF_THICKNESS, DIFF_ORIFICE, DIFF_GEOMETRY, OK).
    status : Enum(FRStatus)
        Overall flow restrictor status (e.g., DIFF_FLOWRATE).
    remark : String
        Additional remarks.
    gas_type : String
        Gas used during testing.
    allocated : String
        FMS to which this restrictor is allocated.
    testing_completed : Boolean
        Whether testing has been completed.
    operator : String
        Operator who conducted the testing.
    trs_reference : String
        TRS reference document identifier.
    tools : JSON
        List of components used to test the FR.

    Relationships
    -------------
    certification : relationship
        One-to-many relationship with the FRCertification table.
    manifold : relationship
        One-to-one relationship with the ManifoldStatus table.
    """
    __tablename__ = 'cathode_fr' 

    fr_id = Column(String(50), primary_key=True, unique=True, nullable=False)
    set_id = Column(String(50), ForeignKey('manifold_status.set_id'), nullable=True, unique=True) 
    drawing = Column(String(50), nullable=True)
    thickness = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    orifice_diameter = Column(Float, nullable=True)
    deviation = Column(Float, nullable=True)
    pressure_drop = Column(JSON, nullable=True)
    radius = Column(Float, nullable=True)
    pressures = Column(JSON, nullable=True)
    flow_rates = Column(JSON, nullable=True)
    extra_tests = Column(JSON, nullable=True)
    date = Column(DateTime, nullable=True)
    remark = Column(String(255), nullable=True)
    status_geometry = Column(Enum(FRStatus, native_enum=False), nullable=True)
    status = Column(Enum(FRStatus, native_enum=False), nullable=True)
    gas_type = Column(String(50), nullable=True)
    allocated = Column(String(50), nullable=True)
    testing_completed = Column(Boolean, default=False)
    operator = Column(String(50), nullable=True)
    trs_reference = Column(String(100), nullable=True)
    tools = Column(JSON, nullable=True)

    certification = relationship("FRCertification", back_populates="cathode_fr")
    manifold = relationship("ManifoldStatus", back_populates="cathode")
