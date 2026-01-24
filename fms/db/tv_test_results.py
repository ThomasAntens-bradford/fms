from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class TVTestResults(Base):
    """
    -----------------------------
    TV Test Results table 1.6.2.1
    -----------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    test_reference : String(50)
        Foreign Key. Test Reference linking to TVTestRuns table.
    parameter_name : String(50)
        Name of the test parameter.
    parameter_value : Float
        Value of the test parameter.
    unit : String(20)
        Unit of the test parameter.

    Relationships
    -------------
    test_runs : TVTestRuns
        Many-to-one relationship with TVTestRuns table.
    """
    __tablename__ = 'tv_test_results' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_reference = Column(String(50), ForeignKey('tv_test_runs.test_reference'), nullable=False)
    parameter_name = Column(String(50), nullable=False)
    parameter_value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)

    test_runs = relationship("TVTestRuns", back_populates="test_results")