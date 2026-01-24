from sqlalchemy import Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class HPIVCertification(Base):
    """
    ----------------------------
    HPIV Certification table 1.5
    ----------------------------
    
    Columns
    -------
    hpiv_id : String(50)
        Primary Key. HPIV Identifier.
    allocated : String(50)
        Foreign Key. FMS Identifier linking to FMSMain table.
    certification : String(50)
        Certification number of the HPIV.

    Relationships
    -------------
    characteristics : HPIVCharacteristics
        One-to-many relationship with HPIVCharacteristics table.
    fms_main : FMSMain
        Many-to-one relationship with FMSMain table.
    revisions : HPIVRevisions
        One-to-many relationship with HPIVRevisions table.
    """
    __tablename__ = 'hpiv_certification'
    hpiv_id = Column(String(50), primary_key=True)
    allocated = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=True) 
    certification = Column(String(50), nullable=True)
    characteristics = relationship("HPIVCharacteristics", back_populates="certification") 

    fms_main = relationship("FMSMain", back_populates="hpiv")
    revisions = relationship("HPIVRevisions", back_populates="certification") 