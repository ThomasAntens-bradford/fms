from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum, Boolean
from ..utils.general_utils import LimitStatus
from sqlalchemy.orm import relationship
from .base import Base

class FMSTestResults(Base):
    """
    --------------------------
    FMS Test Results table 1.8.1
    --------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    fms_id : String(50)
        Foreign Key. FMS Identifier linking to FMSMain table.
    parameter_name : String(50)
        Name of the test parameter.
    parameter_value : Float
        Value of the test parameter.
    parameter_json : JSON
        JSON field for complex parameter data.
    parameter_unit : String(20)
        Unit of the test parameter.
    lower : Boolean
        Indicates if the parameter is below the parameter_value (so < [value]).
    equal : Boolean
        Indicates if the parameter is equal to the parameter_value.
    larger : Boolean
        Indicates if the parameter is above the parameter_value (so > [value]).
    within_limits : Enum(LimitStatus)
        Status indicating if the parameter is within defined limits.
    automated_entry : Boolean
        Indicates if the entry was made automatically.

    Relationships
    -------------
    fms_main : FMSMain
        Many-to-one relationship with FMSMain table.
    """

    __tablename__ = 'fms_test_results' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    fms_id = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=False)
    parameter_name = Column(String(50), nullable=False)
    parameter_value = Column(Float, nullable=True)
    parameter_json = Column(JSON, nullable=True)
    parameter_unit = Column(String(20), nullable=True)
    lower = Column(Boolean, default=False)
    equal = Column(Boolean, default=True)
    larger = Column(Boolean, default=False)
    within_limits = Column(Enum(LimitStatus, native_enum=False), nullable=True)
    automated_entry = Column(Boolean, default=False, nullable=True)

    fms_main = relationship("FMSMain", back_populates="test_results")