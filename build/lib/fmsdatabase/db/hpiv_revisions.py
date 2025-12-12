from sqlalchemy import Column, Integer, Float, String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from .base import Base

class HPIVRevisions(Base):
    """
    --------------------------
    HPIV Revisions table 1.5.2
    --------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    hpiv_id : String(50)
        Foreign Key. HPIV Identifier linking to HPIVCertification table.
    part_name : String(100)
        Name of the part.
    part_number : String(50)
        Part number of the component.
    revision : String(50)
        Revision identifier of the part.

    Relationships
    -------------
    certification : HPIVCertification
        Many-to-one relationship with HPIVCertification table.
    """
    __tablename__ = 'hpiv_revisions'  

    id = Column(Integer, primary_key=True)
    hpiv_id = Column(String(50), ForeignKey('hpiv_certification.hpiv_id'), nullable=False)
    part_name = Column(String(100), nullable=False)
    part_number = Column(String(50), nullable=True)
    revision = Column(String(50), nullable=False)

    certification = relationship("HPIVCertification", back_populates="revisions")