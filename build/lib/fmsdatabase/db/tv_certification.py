from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum, JSON, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class TVCertification(Base):
    """
    ----------------------------
    TV Certification table 1.6.1
    ----------------------------

    Columns
    -------
    part_id : Integer
        Primary Key. Auto-incrementing identifier.
    certification : String(50)
        Certification identifier for the TV part.
    drawing : String(50)
        Drawing reference for the TV part.
    part_name : String(50)
        Name of the TV part.
    tv_id : Integer
        Foreign Key. TV Identifier linking to TVStatus table.
    nominal_dimensions : JSON
        List of nominal dimensions of the TV part.
    dimensions : JSON
        List of actual dimensions of the TV part.
    min_dimensions : JSON
        List of minimum acceptable dimensions for the TV part.
    max_dimensions : JSON
        List of maximum acceptable dimensions for the TV part.
    date : DateTime
        Date of the certification.

    Relationships
    -------------
    status : TVStatus
        Many-to-one relationship with TVStatus table.
    """
    __tablename__ = 'tv_certification' 

    part_id = Column(Integer, primary_key=True, autoincrement=True)
    certification = Column(String(50), nullable=False)
    drawing = Column(String(50), nullable=False)
    part_name = Column(String(50), nullable=False)
    tv_id = Column(Integer, ForeignKey('tv_status.tv_id'), nullable=True)
    nominal_dimensions = Column(JSON, nullable = True)
    dimensions = Column(JSON, nullable = True)
    min_dimensions = Column(JSON, nullable = True)
    max_dimensions = Column(JSON, nullable = True)
    date = Column(DateTime, nullable=True)

    status = relationship("TVStatus", back_populates="certifications")