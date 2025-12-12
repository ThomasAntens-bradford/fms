from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum
from ..utils.general_utils import FMSProgressStatus
from sqlalchemy.orm import relationship
from .base import Base

class FMSLimits(Base):
    """
    -----------------------
    FMS Limits Table 1.8
    -----------------------
    
    Columns
    -------
    id : Integer
        Primary Key, unique Limit ID.
    fms_id : String
        Foreign Key, FMS ID (references the main FMS table).
    limits : JSON
        JSON field to store various limit parameters for the FMS.

    Relationships
    -------------
    fms_main : relationship
        Many-to-one relationship with the FMSMain table.
    """

    __tablename__ = 'fms_limits' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    fms_id = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=False, unique=True)
    limits = Column(JSON, nullable=True)

    fms_main = relationship("FMSMain", back_populates="limits")