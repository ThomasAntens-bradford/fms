from sqlalchemy import JSON, Integer, Column, ForeignKey, String
from sqlalchemy.orm import relationship
from .base import Base

class CoilAssembly(Base):
    """
    ---------------------------
    Coil Assembly Table 1.6.3
    ---------------------------
    
    Columns
    -------
    id : Integer
        Primary Key, unique Coil Assembly ID.
    tv_id : Integer
        Foreign Key, TV Status ID (references the TV status table).
    context : JSON
        JSON field to store context information about the coil assembly, for report generation.
    adhesive_logs : JSON
        JSON field to store adhesive application logs.
    steps : JSON
        JSON field to store the steps involved in the coil assembly process.

    Relationships
    -------------
    tv_status : relationship
        One-to-one relationship with the TVStatus table.
    """

    __tablename__ = 'coil_assembly'  

    id = Column(Integer, primary_key=True, nullable=False)
    tv_id = Column(Integer, ForeignKey("tv_status.tv_id"), unique=True, nullable=False)
    version = Column(String(50), nullable=False)
    context = Column(JSON, nullable=True)
    adhesive_logs = Column(JSON, nullable=True)
    steps = Column(JSON, nullable=True)

    tv_status = relationship("TVStatus", back_populates="coil_assembly")