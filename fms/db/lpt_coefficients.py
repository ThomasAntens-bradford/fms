from sqlalchemy import Column, Integer, String, JSON, ForeignKey,Float
from sqlalchemy.orm import relationship
from .base import Base

class LPTCoefficients(Base):
    """
    ------------------------------
    LPT Coefficients table 1.7.1.1
    ------------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    lpt_id : String(50)
        Foreign Key. LPT Identifier linking to LPTCalibration table.
    parameter_name : String(50)
        Name of the coefficient parameter.
    parameter_value : Float
        Value of the coefficient parameter.

    Relationships
    -------------
    calibration : LPTCalibration
        Many-to-one relationship with LPTCalibration table.
    """
    __tablename__ = 'lpt_coefficients'  # table 1.7.1.1

    id = Column(Integer, primary_key=True, autoincrement=True)
    lpt_id = Column(String(50), ForeignKey('lpt_calibration.lpt_id'), nullable=False) 
    parameter_name = Column(String(50), nullable=False)
    parameter_value = Column(Float, nullable=False) 

    calibration = relationship("LPTCalibration", back_populates="coefficients")