from sqlalchemy import Column, Integer, Float, String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from ..utils.general_utils import LimitStatus
from .base import Base

class HPIVCharacteristics(Base):
    """
    --------------------------------
    HPIV Characteristics table 1.5.1
    --------------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    hpiv_id : String(50)
        Foreign Key. HPIV Identifier linking to HPIVCertification table.
    parameter_name : String(50)
        Name of the characteristic parameter.
    parameter_value : Float
        Value of the characteristic parameter.
    min_value : Float
        Minimum acceptable value for the parameter.
    max_value : Float
        Maximum acceptable value for the parameter.
    unit : String(20)
        Unit of the characteristic parameter.
    within_limits : Enum(LimitStatus)
        Status indicating if the parameter is within defined limits.

    Relationships
    -------------
    certification : HPIVCertification
        Many-to-one relationship with HPIVCertification table.
    """
    __tablename__ = 'hpiv_characteristics' 

    id = Column(Integer, primary_key=True)
    hpiv_id = Column(String(50), ForeignKey('hpiv_certification.hpiv_id'), nullable=False)
    parameter_name = Column(String(50), nullable=False)
    parameter_value = Column(Float, nullable=False)
    min_value = Column(Float, nullable=False)
    max_value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    within_limits = Column(Enum(LimitStatus, native_enum=False), nullable=True)

    certification = relationship("HPIVCertification", back_populates="characteristics")