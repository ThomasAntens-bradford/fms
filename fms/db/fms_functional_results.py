from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum
from ..utils.general_utils import LimitStatus
from sqlalchemy.orm import relationship
from .base import Base

class FMSFunctionalResults(Base):

    """
    -----------------------------------
    FMS Functional Results Table 1.3.1
    -----------------------------------

    Columns
    -------
    id : Integer
        Primary Key, unique Result ID.
    test_id : String
        Foreign Key, Test ID (references the FMS Functional Tests table).
    logtime : Float
        Timestamp corresponding to the recorded data point.
    parameter_name : String
        Name of the functional parameter recorded.
    parameter_value : Float
        Value of the functional parameter recorded.
    parameter_unit : String
        Unit of the functional parameter recorded.

    Relationships
    -------------
    main_tests : relationship
        Many-to-one relationship with the FMSFunctionalTests table.
    """
    __tablename__ = 'fms_functional_results' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String(50), ForeignKey('fms_functional.test_id'), nullable=False)
    logtime = Column(Float, nullable=False)
    parameter_name = Column(String(50), nullable=False)
    parameter_value = Column(Float, nullable=True)
    parameter_unit = Column(String(20), nullable=True)

    main_tests = relationship("FMSFunctionalTests", back_populates="functional_results")