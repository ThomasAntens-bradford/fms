from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum, Boolean, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class FMSAcceptanceTests(Base):
    """
    -------------------------------
    FMS Acceptance Tests Table 1.8
    -------------------------------

    Columns
    -------
    id : Integer
        Primary Key, unique Acceptance Test ID.
    fms_id : String
        Foreign Key, FMS ID (references the main FMS table).
    version : String
        Version of the procedure used.
    raw_json : JSON
        JSON field to store raw acceptance test data.
    report_generated : Boolean
        Indicates whether the acceptance test report has been generated.
    date_created : DateTime
        Date when the acceptance test entry was created.
    current_test_type : String
        Current type of test being processed.
    current_property_index : Integer
        Current index of the property being processed.
    current_subdict : String
        Current sub-dictionary being processed.

    Relationships
    -------------
    fms_main : relationship
        One-to-one relationship with the FMSMain table.
    """
    __tablename__ = 'fms_acceptance_tests' 

    id = Column(Integer, primary_key=True, autoincrement=True)
    fms_id = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    raw_json = Column(JSON, nullable=True)
    report_generated = Column(Boolean, default=False)
    date_created = Column(DateTime, nullable=True)
    current_test_type = Column(String(100), nullable=True)
    current_property_index = Column(Integer, nullable=True)
    current_subdict = Column(String(100), nullable=True)

    fms_main = relationship("FMSMain", back_populates="acceptance_tests")