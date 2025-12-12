from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from .base import Base

class FRCertification(Base):
    """
    --------------------------------
    FR Certification table 1.7.2_3.1
    --------------------------------

    Columns
    -------
    part_id : Integer
        Primary Key. Identifier for the part.
    certification : String(50)
        Certification type of the part.
    drawing : String(50)
        Drawing number associated with the part.
    cathode_fr_id : Integer
        Foreign Key. Identifier linking to CathodeFR table.
    anode_fr_id : Integer
        Foreign Key. Identifier linking to AnodeFR table.
    part_name : String(50)
        Name of the part.

    Relationships
    -------------
    cathode_fr : CathodeFR
        Many-to-one relationship with CathodeFR table.
    anode_fr : AnodeFR
        Many-to-one relationship with AnodeFR table.
    """

    __tablename__ = 'fr_certification' 

    part_id = Column(Integer, primary_key=True, nullable=False)
    certification = Column(String(50), nullable=False)
    drawing = Column(String(50), nullable=False)
    cathode_fr_id = Column(Integer, ForeignKey('cathode_fr.fr_id'), nullable=True)
    anode_fr_id = Column(Integer, ForeignKey('anode_fr.fr_id'), nullable=True)
    part_name = Column(String(50), nullable=False)
    
    cathode_fr = relationship("CathodeFR", back_populates="certification")
    anode_fr = relationship("AnodeFR", back_populates="certification")