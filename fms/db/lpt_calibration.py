from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum
from ..utils.general_utils import LimitStatus
from sqlalchemy.orm import relationship
from .base import Base

class LPTCalibration(Base):
    """
    ---------------------------
    LPT Calibration table 1.7.1
    ---------------------------

    Columns
    -------
    lpt_id : String(50)
        Primary Key. LPT Identifier.
    set_id : String(50)
        Foreign Key. Set Identifier linking to ManifoldStatus table.
    certification : String(50)
        Certification identifier for the LPT calibration.
    base_resistance : Float
        Base resistance value for the LPT when calculating the pressure, in Ohm.
    signal : JSON
        List of voltages used to calculate the pressure, in mV.
    resistance : JSON
        List of resistance values used to calculate the temperature, in Ohm.
    base_signal : Float
        Base signal value for the LPT when calculating the temperature, in mV.
    p_calculated : JSON
        List of calculated pressure values, in bar.
    temp_calculated : JSON
        List of calculated temperature values, in °C.
    within_limits : Enum(LimitStatus)
        Status indicating if the signal at which the LPT reads 0.2 [bar] is within defined limits.
    file_reference : String(50)
        Reference to the calibration file.

    Relationships
    -------------
    coefficients : LPTCoefficients
        One-to-many relationship with LPTCoefficients table.
    manifold : ManifoldStatus
        One-to-one relationship with ManifoldStatus table.
    """
    __tablename__ = 'lpt_calibration'  

    lpt_id = Column(String(50), primary_key=True, nullable=False)
    set_id = Column(String(50), ForeignKey('manifold_status.set_id'), nullable=True, unique=True) 
    certification = Column(String(50), nullable=True)
    base_resistance = Column(Float, nullable=True) 
    signal = Column(JSON, nullable=True)
    resistance = Column(JSON, nullable=True)
    base_signal = Column(Float, nullable=True)
    p_calculated = Column(JSON, nullable=True)
    temp_calculated = Column(JSON, nullable=True)
    within_limits = Column(Enum(LimitStatus, native_enum = False), nullable=True, )
    file_reference = Column(String(50), nullable=True)

    coefficients = relationship("LPTCoefficients", back_populates="calibration")
    manifold = relationship("ManifoldStatus", back_populates="lpt")