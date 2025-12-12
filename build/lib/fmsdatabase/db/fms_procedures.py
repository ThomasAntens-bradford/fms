from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.orm import relationship
from .base import Base

class FMSProcedures(Base):
    """
    --------------------------
    FMS Procedures table 2.0
    --------------------------

    Columns
    -------
    script_id : Integer
        Primary Key. Auto-incrementing identifier for each procedure script.
    script_name : String(100)
        Name of the procedure script.
    version : String(50)
        Version of the procedure script.
    script : JSON
        JSON field containing the procedure script details.
    """
    __tablename__ = 'fms_procedures' 

    script_id = Column(Integer, primary_key=True, autoincrement=True)
    script_name = Column(String(100), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    report_version = Column(String(50), nullable=False)
    script = Column(JSON, nullable=False)