from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class FMSFRTests(Base):
    """
    -----------------------------------
    FMS Flow Restrictor Tests Table 1.2
    -----------------------------------

    Columns
    -------
    id : Integer
        Primary Key, unique Test ID.
    fms_id : String
        Foreign Key, FMS ID (references the main FMS table).
    test_id : String
        Test Identifier.
    lpt_pressure : JSON
        List of LPT pressures recorded during the test, in bar.
    lpt_voltage : JSON
        List of LPT voltages recorded during the test, in mV.
    logtime : JSON
        List of timestamps corresponding to the recorded data points, in ISO 8601 format.
    anode_flow : JSON
        List of anode flow rates recorded during the test, in mg/s.
    cathode_flow : JSON
        List of cathode flow rates recorded during the test, in mg/s.
    total_flow : JSON
        List of total flow rates recorded during the test, in mg/s.
    ac_ratio : JSON
        List of anode to cathode flow ratios recorded during the test.
    tv_power : JSON
        List of TV power readings recorded during the test, in W.
    tv_temp : JSON
        List of TV temperature readings recorded during the test, in °C.
    inlet_pressure : Float
        Inlet pressure of the FMS during the test, in bar.
    outlet_pressure : Float
        Outlet pressure of the FMS during the test, in bar.
    trp_temp : Float
        TRP temperature of the FMS during the test, in °C.
    date : DateTime
        Date of the test.
    remark : String
        Additional remarks about the test.
    gas_type : String
        Type of gas used during the test.

    Relationships
    -------------
    fms_main : relationship
        One-to-many relationship with the FMSMain table.
    """
    __tablename__ = 'fms_fr_tests' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    fms_id = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=False)
    test_id = Column(String(50), nullable=False)
    lpt_pressure = Column(JSON, nullable=True)
    lpt_voltage = Column(JSON, nullable=True)
    logtime = Column(JSON, nullable=False)
    anode_flow = Column(JSON, nullable=True)
    cathode_flow = Column(JSON, nullable=True)
    total_flow = Column(JSON, nullable=True)
    ac_ratio = Column(JSON, nullable=True)
    tv_power = Column(JSON, nullable=True)
    tv_temp = Column(JSON, nullable=True)
    inlet_pressure = Column(Float, nullable=True)
    outlet_pressure = Column(Float, nullable=True)
    trp_temp = Column(Float, nullable=True)
    date = Column(DateTime, nullable=False)
    remark = Column(String(255), nullable=True)
    gas_type = Column(String(50), nullable=True)

    fms_main = relationship("FMSMain", back_populates="fr_tests")
