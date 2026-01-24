from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum, DateTime
from ..utils.enums import TVTestParameters
from sqlalchemy.orm import relationship
from .base import Base


class TVTestRuns(Base):
    """
    ------------------------
    TV Test Runs table 1.6.2
    ------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    test_reference : String(50)
        Unique Test Reference identifier for the test run.
    tv_id : Integer
        Foreign Key. TV Identifier linking to TVStatus table.
    welded : Boolean
        Indicates if the TV was already welded when the test was conducted.
    plot_path : String(255)
        Path to the plot generated from the test.
    opening_temp : Float
        Opening temperature recorded during the test, in °C.
    hysteresis : Float  
        Hysteresis value recorded during the test, in °C.
    remark : String(255)
        Additional remarks about the test run.
    used_temp : Enum(TVTestParameters)
        Enum indicating the temperature parameter used to determine the opening temperature.
    date : DateTime
        Date of the test run.

    Relationships
    -------------
    status : TVStatus
        Many-to-one relationship with TVStatus table.
    test_results : TVTestResults
        One-to-many relationship with TVTestResults table.
    """
    __tablename__ = 'tv_test_runs' 

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_reference = Column(String(50), nullable=False, unique=True)
    tv_id = Column(Integer, ForeignKey('tv_status.tv_id'), nullable=False) 
    welded = Column(Boolean, nullable=False, default=False)
    plot_path = Column(String(255), nullable=True)
    opening_temp = Column(Float, nullable=True)
    hysteresis = Column(Float, nullable=True)  
    remark = Column(String(255), nullable=True)
    used_temp = Column(Enum(TVTestParameters, native_enum=False), nullable=True)
    date = Column(DateTime, nullable=True)

    status = relationship("TVStatus", back_populates="test_runs")
    test_results = relationship("TVTestResults", back_populates="test_runs")