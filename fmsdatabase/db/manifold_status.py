from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from ..utils.general_utils import ManifoldProgressStatus
from .base import Base

class ManifoldStatus(Base):
    """
    -------------------------
    Manifold Status table 1.7
    -------------------------

    Columns
    -------
    manifold_id : Integer
        Primary Key. Auto-incrementing identifier.
    set_id : Integer
        Unique Set Identifier.
    allocated : String(50)
        Foreign Key. FMS Identifier linking to FMSMain table.
    certification : String(50)
        Certification identifier for the manifold.
    drawing : String(50)
        Drawing reference for the manifold.
    assembly_drawing : String(50)
        Assembly drawing reference for the manifold.
    assembly_certification : String(50)
        Assembly certification identifier for the manifold.
    status : Enum(ManifoldProgressStatus)
        Status indicating the progress of the manifold.
    ac_ratio : Float
        Actual AC ratio of the manifold.
    ac_ratio_specified : Float
        Specified AC ratio of the manifold.

    Relationships
    -------------
    fms_main : FMSMain
        One-to-one relationship with FMSMain table.
    lpt : LPTCalibration
        One-to-one relationship with LPTCalibration table.
    anode : AnodeFR
        One-to-one relationship with AnodeFR table.
    cathode : CathodeFR
        One-to-one relationship with CathodeFR table.
    """
    __tablename__ = 'manifold_status'

    manifold_id = Column(Integer, autoincrement=True, primary_key=True, nullable=False)
    set_id = Column(Integer, nullable=True, unique=True)
    allocated = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=True, unique=True) 
    certification = Column(String(50), nullable=True)
    drawing = Column(String(50), nullable=True)
    assembly_drawing = Column(String(50), nullable=True)
    assembly_certification = Column(String(50), nullable=True)
    status = Column(Enum(ManifoldProgressStatus, native_enum=False), nullable=True)
    ac_ratio = Column(Float, nullable=True)
    ac_ratio_specified = Column(Float, nullable=True)

    fms_main = relationship("FMSMain", back_populates="manifold")
    lpt = relationship("LPTCalibration", back_populates="manifold")
    anode = relationship("AnodeFR", back_populates="manifold")
    cathode = relationship("CathodeFR", back_populates="manifold")